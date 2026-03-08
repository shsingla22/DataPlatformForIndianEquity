"""Report generation for dividend screener results.

Produces both terminal-friendly text and structured data for Showboat.
"""

import json
from typing import List

from dividend_screener.screener import CompanyMetrics


def format_table(ranked: List[CompanyMetrics]) -> str:
    """Format ranked companies as an ASCII table for terminal output."""
    lines = []
    header = (
        f"{'#':>3s}  {'Symbol':12s} {'Name':30s} {'Sector':18s} "
        f"{'MktCap':>10s} {'DivYld%':>7s} {'Payout%':>7s} "
        f"{'EG%':>6s} {'PE':>6s} {'D/E':>5s} {'Score':>6s}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    for i, m in enumerate(ranked, 1):
        lines.append(
            f"{i:3d}  {m.nse_symbol:12s} {m.name[:30]:30s} {m.sector[:18]:18s} "
            f"{m.market_cap:10,.0f} {m.dividend_yield_pct:7.2f} {m.dividend_payout_pct:7.1f} "
            f"{m.earnings_growth_pct:6.1f} {m.pe_ratio:6.1f} {m.debt_to_equity:5.2f} "
            f"{m.composite_score:6.1f}"
        )

    return "\n".join(lines)


def format_summary(all_metrics: List[CompanyMetrics],
                   ranked: List[CompanyMetrics]) -> str:
    """Generate a textual summary of the screening run."""
    lines = []
    lines.append("=" * 70)
    lines.append("DIVIDEND VALUE SCREENER – RESULTS SUMMARY")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"Companies analysed:        {len(all_metrics)}")

    avg_dy = sum(m.dividend_yield_pct for m in all_metrics) / len(all_metrics)
    avg_pe = sum(m.pe_ratio for m in all_metrics) / len(all_metrics)
    lines.append(f"Average dividend yield:    {avg_dy:.2f}%")
    lines.append(f"Average P/E ratio:         {avg_pe:.1f}x")
    lines.append("")

    lines.append(f"TOP {len(ranked)} PICKS")
    lines.append("-" * 70)
    lines.append("")
    lines.append(format_table(ranked))
    lines.append("")

    # Sector distribution
    sectors = {}
    for m in ranked:
        sectors[m.sector] = sectors.get(m.sector, 0) + 1
    lines.append("SECTOR DISTRIBUTION (Top picks)")
    lines.append("-" * 40)
    for sector, count in sorted(sectors.items(), key=lambda x: -x[1]):
        lines.append(f"  {sector[:35]:35s} {count}")
    lines.append("")

    # Score breakdown for top 5
    lines.append("SCORE BREAKDOWN – TOP 5")
    lines.append("-" * 70)
    lines.append(
        f"{'Symbol':12s} {'DivYld':>7s} {'Payout':>7s} {'Growth':>7s} "
        f"{'Valuation':>9s} {'BalSheet':>8s} {'TOTAL':>7s}"
    )
    for m in ranked[:5]:
        lines.append(
            f"{m.nse_symbol:12s} {m.score_div_yield:7.1f} {m.score_payout:7.1f} "
            f"{m.score_earnings_growth:7.1f} {m.score_valuation:9.1f} "
            f"{m.score_balance_sheet:8.1f} {m.composite_score:7.1f}"
        )

    return "\n".join(lines)


def to_json(ranked: List[CompanyMetrics]) -> str:
    """Serialize ranked companies to JSON for programmatic consumption."""
    records = []
    for i, m in enumerate(ranked, 1):
        records.append({
            "rank": i,
            "nse_symbol": m.nse_symbol,
            "name": m.name,
            "sector": m.sector,
            "market_cap_crores": round(m.market_cap),
            "dividend_yield_pct": round(m.dividend_yield_pct, 2),
            "dividend_payout_pct": round(m.dividend_payout_pct, 1),
            "earnings_growth_pct": round(m.earnings_growth_pct, 1),
            "pe_ratio": round(m.pe_ratio, 1),
            "debt_to_equity": round(m.debt_to_equity, 2),
            "roe_pct": round(m.roe_pct, 1),
            "composite_score": round(m.composite_score, 1),
            "scores": {
                "dividend_yield": round(m.score_div_yield, 1),
                "payout_ratio": round(m.score_payout, 1),
                "earnings_growth": round(m.score_earnings_growth, 1),
                "valuation": round(m.score_valuation, 1),
                "balance_sheet": round(m.score_balance_sheet, 1),
            },
        })
    return json.dumps(records, indent=2)
