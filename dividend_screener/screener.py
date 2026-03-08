"""Core screening engine for dividend value stocks.

Scoring criteria (each 0-100, weighted):
  1. Dividend Yield          (25%) – higher is better, capped at 10%
  2. Payout Ratio            (20%) – sweet spot 15-50%, penalise extremes
  3. Earnings Growth         (20%) – 3-year CAGR of net profit
  4. Valuation (Earnings Yield) (20%) – inverse P/E, higher is cheaper
  5. Balance Sheet Strength  (15%) – low debt-to-equity, high reserves

The module reads from the SQLite database created by the data platform,
computes metrics for each company across available fiscal years, scores
them, and returns a ranked list.
"""

import math
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dividend_screener.psu_classifier import classify

DB_PATH = str(Path(__file__).parent.parent / "data" / "financial_profiles.db")

# ── Scoring weights ──────────────────────────────────────────────────
W_DIV_YIELD = 0.25
W_PAYOUT = 0.20
W_EARNINGS_GROWTH = 0.20
W_VALUATION = 0.20
W_BALANCE_SHEET = 0.15


@dataclass
class CompanyMetrics:
    """Computed metrics for a single company."""
    company_id: int
    nse_symbol: str
    name: str
    sector: str
    market_cap: float  # crores
    ownership_type: str = ""  # "PSU" or "Private"

    # Latest year values
    latest_year: str = ""
    eps: float = 0.0
    dividend_payout_pct: float = 0.0
    net_profit: float = 0.0
    sales: float = 0.0
    opm_pct: float = 0.0

    # Derived metrics
    shares_crore: float = 0.0
    dps: float = 0.0
    implied_price: float = 0.0
    dividend_yield_pct: float = 0.0
    pe_ratio: float = 0.0
    earnings_yield_pct: float = 0.0
    earnings_growth_pct: float = 0.0  # 3-year CAGR
    debt_to_equity: float = 0.0
    roe_pct: float = 0.0

    # Component scores (0-100)
    score_div_yield: float = 0.0
    score_payout: float = 0.0
    score_earnings_growth: float = 0.0
    score_valuation: float = 0.0
    score_balance_sheet: float = 0.0
    composite_score: float = 0.0


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    if b is None or b == 0 or a is None:
        return default
    return a / b


def _score_dividend_yield(dy: float) -> float:
    """Higher yield → higher score.  Linear 0-10% mapped to 0-100."""
    if dy <= 0:
        return 0.0
    return min(dy / 10.0 * 100.0, 100.0)


def _score_payout(payout: float) -> float:
    """Sweet spot is 15-50%.  Below 10% or above 80% gets penalised."""
    if payout <= 0:
        return 0.0
    if payout < 10:
        return payout * 5.0  # 0-50
    if payout <= 50:
        return 100.0 - abs(payout - 30) * 1.0  # peak at 30%
    if payout <= 80:
        return max(0, 100.0 - (payout - 50) * 2.5)
    return max(0, 100.0 - (payout - 50) * 3.0)  # >80% harsh penalty


def _score_earnings_growth(cagr: float) -> float:
    """Positive growth is good.  Map -20% to +30% → 0-100."""
    clamped = max(-20.0, min(cagr, 30.0))
    return (clamped + 20.0) / 50.0 * 100.0


def _score_valuation(earnings_yield: float) -> float:
    """Higher earnings yield (lower PE) is better.  Map 0-15% → 0-100."""
    if earnings_yield <= 0:
        return 0.0
    return min(earnings_yield / 15.0 * 100.0, 100.0)


def _score_balance_sheet(de_ratio: float) -> float:
    """Lower D/E is better.  0 → 100, 2 → 0.  Negative equity → 0."""
    if de_ratio < 0:
        return 0.0
    if de_ratio > 2.0:
        return 0.0
    return (2.0 - de_ratio) / 2.0 * 100.0


def _get_fiscal_year_order_key(fy: str) -> Tuple[int, str]:
    """Parse 'Mar 2025' into (2025, 'Mar') for sorting."""
    parts = fy.strip().split()
    if len(parts) >= 2:
        month = parts[0]
        year_str = "".join(c for c in parts[1] if c.isdigit())
        try:
            return (int(year_str), month)
        except ValueError:
            pass
    return (0, fy)


def load_company_data(db_path: str = DB_PATH) -> List[CompanyMetrics]:
    """Load and compute metrics for all companies from the database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    companies = conn.execute(
        "SELECT id, name, nse_symbol, sector, market_cap_crores "
        "FROM companies WHERE market_cap_crores > 0 "
        "ORDER BY market_cap_crores DESC"
    ).fetchall()

    results = []

    for company in companies:
        cid = company["id"]
        mcap = company["market_cap_crores"] or 0
        symbol = company["nse_symbol"] or ""
        name = company["name"] or ""
        sector = company["sector"] or ""

        if mcap <= 0:
            continue

        # Get all P&L years, pick the standard ones (Mar/Dec YYYY)
        pl_rows = conn.execute(
            "SELECT fiscal_year, sales, net_profit, eps, "
            "dividend_payout_percent, opm_percent "
            "FROM profit_loss WHERE company_id = ? "
            "ORDER BY fiscal_year",
            (cid,)
        ).fetchall()

        # Filter to clean fiscal years only (e.g., 'Mar 2025', 'Dec 2024')
        clean_rows = []
        for row in pl_rows:
            fy = row["fiscal_year"]
            parts = fy.split()
            if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 4:
                clean_rows.append(row)

        if not clean_rows:
            continue

        # Sort by fiscal year
        clean_rows.sort(key=lambda r: _get_fiscal_year_order_key(r["fiscal_year"]))

        latest = clean_rows[-1]
        eps = latest["eps"]
        div_payout = latest["dividend_payout_percent"]
        net_profit = latest["net_profit"]
        sales = latest["sales"]
        opm = latest["opm_percent"]

        if not eps or eps <= 0 or not div_payout or div_payout <= 0:
            continue

        # ── Compute shares outstanding ───────────────────────────
        shares_cr = _safe_div(net_profit, eps)
        if shares_cr <= 0:
            continue

        # ── Derive key metrics ───────────────────────────────────
        dps = eps * div_payout / 100.0
        implied_price = _safe_div(mcap, shares_cr)
        div_yield = _safe_div(dps, implied_price) * 100.0 if implied_price > 0 else 0.0
        pe_ratio = _safe_div(implied_price, eps)
        earnings_yield = _safe_div(eps, implied_price) * 100.0 if implied_price > 0 else 0.0

        # ── Earnings growth (CAGR over available years) ──────────
        earnings_growth = 0.0
        profit_series = [(r["fiscal_year"], r["net_profit"])
                         for r in clean_rows if r["net_profit"] and r["net_profit"] > 0]
        if len(profit_series) >= 2:
            oldest_np = profit_series[0][1]
            newest_np = profit_series[-1][1]
            n_years = len(profit_series) - 1
            if oldest_np > 0 and newest_np > 0 and n_years > 0:
                earnings_growth = ((newest_np / oldest_np) ** (1.0 / n_years) - 1) * 100.0

        # ── Balance sheet metrics ────────────────────────────────
        bs = conn.execute(
            "SELECT equity_capital, reserves, borrowings, total_assets "
            "FROM balance_sheet WHERE company_id = ? "
            "ORDER BY fiscal_year DESC LIMIT 1",
            (cid,)
        ).fetchone()

        de_ratio = 0.0
        roe = 0.0
        if bs:
            equity = (bs["equity_capital"] or 0) + (bs["reserves"] or 0)
            borrowings = bs["borrowings"] or 0
            de_ratio = _safe_div(borrowings, equity) if equity > 0 else 99.0
            roe = _safe_div(net_profit, equity) * 100.0 if equity > 0 else 0.0

        # ── Scoring ──────────────────────────────────────────────
        s_dy = _score_dividend_yield(div_yield)
        s_po = _score_payout(div_payout)
        s_eg = _score_earnings_growth(earnings_growth)
        s_va = _score_valuation(earnings_yield)
        s_bs = _score_balance_sheet(de_ratio)

        composite = (
            s_dy * W_DIV_YIELD
            + s_po * W_PAYOUT
            + s_eg * W_EARNINGS_GROWTH
            + s_va * W_VALUATION
            + s_bs * W_BALANCE_SHEET
        )

        m = CompanyMetrics(
            company_id=cid,
            nse_symbol=symbol,
            name=name,
            sector=sector,
            market_cap=mcap,
            ownership_type=classify(symbol),
            latest_year=latest["fiscal_year"],
            eps=eps,
            dividend_payout_pct=div_payout,
            net_profit=net_profit,
            sales=sales,
            opm_pct=opm or 0.0,
            shares_crore=shares_cr,
            dps=dps,
            implied_price=implied_price,
            dividend_yield_pct=div_yield,
            pe_ratio=pe_ratio,
            earnings_yield_pct=earnings_yield,
            earnings_growth_pct=earnings_growth,
            debt_to_equity=de_ratio,
            roe_pct=roe,
            score_div_yield=s_dy,
            score_payout=s_po,
            score_earnings_growth=s_eg,
            score_valuation=s_va,
            score_balance_sheet=s_bs,
            composite_score=composite,
        )
        results.append(m)

    conn.close()
    return results


def rank_companies(metrics: List[CompanyMetrics],
                   top_n: int = 30) -> List[CompanyMetrics]:
    """Sort by composite score descending and return top N."""
    metrics.sort(key=lambda m: m.composite_score, reverse=True)
    return metrics[:top_n]
