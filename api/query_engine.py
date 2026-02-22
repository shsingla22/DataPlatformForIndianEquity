"""Natural language query engine for Indian equity financial data.

This module converts free-text questions into structured database queries.
It uses keyword matching, fuzzy company-name resolution, and intent
classification — no external LLM calls required.

Supported intents
-----------------
- **lookup**    : Fetch a specific metric for a company / year.
- **compare**   : Compare a metric across 2–5 companies.
- **rank**      : Top/bottom N companies by a metric.
- **trend**     : Year-over-year data for a company.
- **overview**  : Full financial snapshot (P&L + BS + CF).
- **list**      : List or search companies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from rapidfuzz import fuzz, process as fuzz_process

from api import database as db

# ---------------------------------------------------------------------------
# Metric catalogue – maps human-readable names to (table, column) pairs
# ---------------------------------------------------------------------------

METRIC_MAP: dict[str, tuple[str, str]] = {
    # Profit & Loss
    "revenue": ("profit_loss", "sales"),
    "sales": ("profit_loss", "sales"),
    "turnover": ("profit_loss", "sales"),
    "income": ("profit_loss", "sales"),
    "expenses": ("profit_loss", "expenses"),
    "expense": ("profit_loss", "expenses"),
    "operating profit": ("profit_loss", "operating_profit"),
    "ebitda": ("profit_loss", "operating_profit"),
    "operating margin": ("profit_loss", "opm_percent"),
    "opm": ("profit_loss", "opm_percent"),
    "opm %": ("profit_loss", "opm_percent"),
    "operating profit margin": ("profit_loss", "opm_percent"),
    "other income": ("profit_loss", "other_income"),
    "interest": ("profit_loss", "interest"),
    "interest cost": ("profit_loss", "interest"),
    "finance cost": ("profit_loss", "interest"),
    "depreciation": ("profit_loss", "depreciation"),
    "profit before tax": ("profit_loss", "profit_before_tax"),
    "pbt": ("profit_loss", "profit_before_tax"),
    "tax": ("profit_loss", "tax_percent"),
    "tax rate": ("profit_loss", "tax_percent"),
    "tax %": ("profit_loss", "tax_percent"),
    "net profit": ("profit_loss", "net_profit"),
    "pat": ("profit_loss", "net_profit"),
    "profit after tax": ("profit_loss", "net_profit"),
    "net income": ("profit_loss", "net_profit"),
    "profit": ("profit_loss", "net_profit"),
    "bottom line": ("profit_loss", "net_profit"),
    "eps": ("profit_loss", "eps"),
    "earnings per share": ("profit_loss", "eps"),
    "dividend": ("profit_loss", "dividend_payout_percent"),
    "dividend payout": ("profit_loss", "dividend_payout_percent"),
    "dividend %": ("profit_loss", "dividend_payout_percent"),
    # Balance Sheet
    "equity": ("balance_sheet", "equity_capital"),
    "equity capital": ("balance_sheet", "equity_capital"),
    "share capital": ("balance_sheet", "equity_capital"),
    "reserves": ("balance_sheet", "reserves"),
    "retained earnings": ("balance_sheet", "reserves"),
    "borrowings": ("balance_sheet", "borrowings"),
    "debt": ("balance_sheet", "borrowings"),
    "loans": ("balance_sheet", "borrowings"),
    "total debt": ("balance_sheet", "borrowings"),
    "other liabilities": ("balance_sheet", "other_liabilities"),
    "total liabilities": ("balance_sheet", "total_liabilities"),
    "liabilities": ("balance_sheet", "total_liabilities"),
    "fixed assets": ("balance_sheet", "fixed_assets"),
    "ppe": ("balance_sheet", "fixed_assets"),
    "property plant equipment": ("balance_sheet", "fixed_assets"),
    "cwip": ("balance_sheet", "cwip"),
    "capital work in progress": ("balance_sheet", "cwip"),
    "investments": ("balance_sheet", "investments"),
    "other assets": ("balance_sheet", "other_assets"),
    "total assets": ("balance_sheet", "total_assets"),
    "assets": ("balance_sheet", "total_assets"),
    # Cash Flow
    "cash from operations": ("cash_flow", "cash_from_operating"),
    "operating cash flow": ("cash_flow", "cash_from_operating"),
    "cfo": ("cash_flow", "cash_from_operating"),
    "cash from investing": ("cash_flow", "cash_from_investing"),
    "investing cash flow": ("cash_flow", "cash_from_investing"),
    "capex": ("cash_flow", "cash_from_investing"),
    "cash from financing": ("cash_flow", "cash_from_financing"),
    "financing cash flow": ("cash_flow", "cash_from_financing"),
    "net cash flow": ("cash_flow", "net_cash_flow"),
    "free cash flow": ("cash_flow", "net_cash_flow"),
    "fcf": ("cash_flow", "net_cash_flow"),
    # Market cap (in companies table)
    "market cap": ("companies", "market_cap_crores"),
    "market capitalization": ("companies", "market_cap_crores"),
    "mcap": ("companies", "market_cap_crores"),
    "market value": ("companies", "market_cap_crores"),
}

# Calculated ratios that need special handling
CALCULATED_RATIOS: dict[str, str] = {
    "debt to equity": "debt_to_equity",
    "de ratio": "debt_to_equity",
    "d/e ratio": "debt_to_equity",
    "leverage": "debt_to_equity",
    "return on equity": "roe",
    "roe": "roe",
    "return on assets": "roa",
    "roa": "roa",
    "net margin": "net_margin",
    "net profit margin": "net_margin",
    "profit margin": "net_margin",
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_COMPANY_CACHE: Optional[dict[str, dict]] = None
_SYMBOL_LIST: Optional[list[str]] = None
_NAME_TO_SYMBOL: Optional[dict[str, str]] = None


def _load_company_cache(db_path: Optional[str] = None) -> None:
    global _COMPANY_CACHE, _SYMBOL_LIST, _NAME_TO_SYMBOL
    companies, _ = db.search_companies(limit=1000, db_path=db_path)
    _COMPANY_CACHE = {}
    _SYMBOL_LIST = []
    _NAME_TO_SYMBOL = {}
    for c in companies:
        sym = c["nse_symbol"]
        _COMPANY_CACHE[sym.upper()] = c
        _SYMBOL_LIST.append(sym)
        _NAME_TO_SYMBOL[c["name"].lower()] = sym
    # Add common short forms
    _short_aliases: dict[str, str] = {
        "reliance": "RELIANCE",
        "tcs": "TCS",
        "infosys": "INFY",
        "infy": "INFY",
        "hdfc bank": "HDFCBANK",
        "hdfc": "HDFCBANK",
        "icici bank": "ICICIBANK",
        "icici": "ICICIBANK",
        "sbi": "SBIN",
        "state bank": "SBIN",
        "wipro": "WIPRO",
        "itc": "ITC",
        "kotak": "KOTAKBANK",
        "kotak bank": "KOTAKBANK",
        "axis bank": "AXISBANK",
        "axis": "AXISBANK",
        "bharti airtel": "BHARTIARTL",
        "airtel": "BHARTIARTL",
        "hul": "HINDUNILVR",
        "hindustan unilever": "HINDUNILVR",
        "bajaj finance": "BAJFINANCE",
        "maruti": "MARUTI",
        "sun pharma": "SUNPHARMA",
        "titan": "TITAN",
        "asian paints": "ASIANPAINT",
        "l&t": "LT",
        "larsen": "LT",
        "tata motors": "TMPV",
        "tata motors pv": "TMPV",
        "tata steel": "TATASTEEL",
        "tata power": "TATAPOWER",
        "tata consumer": "TATACONSUM",
        "tata elxsi": "TATAELXSI",
        "tata chemicals": "TATACHEM",
        "tata comm": "TATACOMM",
        "tata tech": "TATATECH",
        "tata": "TCS",
        "adani": "ADANIENT",
        "adani enterprises": "ADANIENT",
        "adani ports": "ADANIPORTS",
        "tech mahindra": "TECHM",
        "hcl tech": "HCLTECH",
        "power grid": "POWERGRID",
        "ntpc": "NTPC",
        "ultratech": "ULTRACEMCO",
        "ultratech cement": "ULTRACEMCO",
        "nestle": "NESTLEIND",
        "bajaj auto": "BAJAJ-AUTO",
        "britannia": "BRITANNIA",
        "cipla": "CIPLA",
        "dr reddy": "DRREDDY",
        "divis lab": "DIVISLAB",
        "grasim": "GRASIM",
        "m&m": "M&M",
        "mahindra": "M&M",
    }
    _NAME_TO_SYMBOL.update(_short_aliases)


def _ensure_cache(db_path: Optional[str] = None) -> None:
    if _COMPANY_CACHE is None:
        _load_company_cache(db_path)


def resolve_company(text: str, db_path: Optional[str] = None) -> Optional[str]:
    """Fuzzy-resolve a company name or symbol to an NSE symbol."""
    _ensure_cache(db_path)
    assert _COMPANY_CACHE is not None
    assert _NAME_TO_SYMBOL is not None
    assert _SYMBOL_LIST is not None

    text_clean = text.strip()

    # Exact symbol match
    if text_clean.upper() in _COMPANY_CACHE:
        return text_clean.upper()

    # Exact alias / name match
    if text_clean.lower() in _NAME_TO_SYMBOL:
        return _NAME_TO_SYMBOL[text_clean.lower()]

    # Fuzzy match against full company names
    candidates = list(_NAME_TO_SYMBOL.keys())
    match = fuzz_process.extractOne(
        text_clean.lower(), candidates, scorer=fuzz.WRatio, score_cutoff=78
    )
    if match:
        return _NAME_TO_SYMBOL[match[0]]

    # Fuzzy match against symbols
    match = fuzz_process.extractOne(
        text_clean.upper(), _SYMBOL_LIST, scorer=fuzz.ratio, score_cutoff=75
    )
    if match:
        return match[0]

    return None


def _extract_companies(text: str, db_path: Optional[str] = None) -> list[str]:
    """Extract all company references from a query string."""
    _ensure_cache(db_path)
    assert _NAME_TO_SYMBOL is not None

    found: list[str] = []
    text_lower = text.lower()

    # First pass: try known aliases (longest first to avoid partial matches)
    aliases_sorted = sorted(_NAME_TO_SYMBOL.keys(), key=len, reverse=True)
    remaining = text_lower
    for alias in aliases_sorted:
        if alias in remaining:
            sym = _NAME_TO_SYMBOL[alias]
            if sym not in found:
                found.append(sym)
            remaining = remaining.replace(alias, " ")

    # Second pass: look for uppercase tokens that match symbols
    assert _COMPANY_CACHE is not None
    tokens = re.findall(r'\b[A-Z][A-Z0-9&-]{1,20}\b', text)
    for tok in tokens:
        if tok in _COMPANY_CACHE and tok not in found:
            found.append(tok)

    return found


def _extract_metric(text: str) -> Optional[tuple[str, str, str]]:
    """Extract (readable_name, table, column) from query text."""
    text_lower = text.lower()

    # Check calculated ratios first
    for name, ratio_id in CALCULATED_RATIOS.items():
        if name in text_lower:
            return (name, "__ratio__", ratio_id)

    # Check direct metrics (longest-match first)
    sorted_metrics = sorted(METRIC_MAP.keys(), key=len, reverse=True)
    for name in sorted_metrics:
        if name in text_lower:
            table, column = METRIC_MAP[name]
            return (name, table, column)
    return None


def _extract_fiscal_year(text: str) -> Optional[str]:
    """Extract a fiscal year reference from query text."""
    # "Mar 2024", "March 2024" etc.
    m = re.search(r'(mar(?:ch)?|dec(?:ember)?|sep(?:tember)?)\s*(20\d{2})', text, re.I)
    if m:
        month_map = {"mar": "Mar", "march": "Mar", "dec": "Dec",
                     "december": "Dec", "sep": "Sep", "september": "Sep"}
        month = month_map.get(m.group(1).lower(), "Mar")
        return f"{month} {m.group(2)}"

    # "FY2024", "FY 2024", "fy24"
    m = re.search(r'fy\s*(\d{4}|\d{2})\b', text, re.I)
    if m:
        year_str = m.group(1)
        if len(year_str) == 2:
            year_str = "20" + year_str
        return f"Mar {year_str}"

    # Bare "2024", "2025" etc.
    m = re.search(r'\b(20\d{2})\b', text)
    if m:
        return f"Mar {m.group(1)}"

    return None


def _extract_limit(text: str) -> int:
    """Extract a numeric limit (top N / bottom N)."""
    m = re.search(r'\b(?:top|bottom|best|worst|first|last)\s+(\d+)\b', text, re.I)
    if m:
        return min(int(m.group(1)), 50)
    m = re.search(r'\b(\d+)\s+(?:companies|stocks|firms)\b', text, re.I)
    if m:
        return min(int(m.group(1)), 50)
    return 10


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

@dataclass
class ParsedQuery:
    intent: str  # lookup | compare | rank | trend | overview | list | unknown
    companies: list[str] = field(default_factory=list)
    metric: Optional[tuple[str, str, str]] = None  # (readable, table, column)
    fiscal_year: Optional[str] = None
    limit: int = 10
    order: str = "DESC"
    raw: str = ""


def _classify_intent(text: str, companies: list[str], metric) -> str:
    text_lower = text.lower()

    # Rank intent
    rank_patterns = [
        r'\btop\s+\d+', r'\bbottom\s+\d+', r'\bbest\b', r'\bworst\b',
        r'\bhighest\b', r'\blowest\b', r'\brank', r'\bleading\b',
        r'\blargest\b', r'\bsmallest\b', r'\bmost\b', r'\bleast\b',
    ]
    if any(re.search(p, text_lower) for p in rank_patterns):
        return "rank"

    # Compare intent
    compare_patterns = [
        r'\bcompare\b', r'\bvs\.?\b', r'\bversus\b', r'\bagainst\b',
        r'\bdifference\b', r'\bcomparison\b',
    ]
    if any(re.search(p, text_lower) for p in compare_patterns):
        return "compare"
    if len(companies) >= 2:
        return "compare"

    # Trend intent
    trend_patterns = [
        r'\btrend\b', r'\bgrowth\b', r'\byear.over.year\b', r'\byoy\b',
        r'\bover\s+the\s+years\b', r'\bhistor', r'\btime\s+series\b',
        r'\bchange\b', r'\bincreas', r'\bdecreas',
    ]
    if any(re.search(p, text_lower) for p in trend_patterns) and len(companies) == 1:
        return "trend"

    # Overview intent
    overview_patterns = [
        r'\boverview\b', r'\bsnapshot\b', r'\bfinancials?\b', r'\bbalance\s*sheet\b',
        r'\bprofile\b', r'\bdetails?\b', r'\bsummar', r'\ball\s+data\b',
        r'\bcash\s*flow\b', r'\bp\s*&?\s*l\b', r'\bprofit\s*(and|&)\s*loss\b',
    ]
    # Overview if asking for a broad view and no specific metric, or if asking
    # for a specific statement
    if len(companies) == 1 and not metric:
        if any(re.search(p, text_lower) for p in overview_patterns):
            return "overview"

    # If they mention balance sheet / cash flow / p&l with a company
    if len(companies) == 1 and metric and metric[1] != "__ratio__":
        if any(re.search(p, text_lower) for p in [r'\bbalance\s*sheet\b', r'\bcash\s*flow\b']):
            return "overview"

    # List intent
    list_patterns = [
        r'\blist\b', r'\bshow\s+(?:me\s+)?(?:all\s+)?companies\b',
        r'\bsearch\b', r'\bfind\s+companies\b', r'\bwhich\s+companies\b',
    ]
    if any(re.search(p, text_lower) for p in list_patterns) and not companies:
        return "list"

    # Lookup intent (default when we have a company and metric)
    if len(companies) >= 1 and metric:
        return "lookup"

    # Overview if we have a company but no metric
    if len(companies) == 1 and not metric:
        return "overview"

    return "unknown"


def parse_query(text: str, db_path: Optional[str] = None) -> ParsedQuery:
    """Parse a natural language query into a structured ParsedQuery."""
    companies = _extract_companies(text, db_path)
    metric = _extract_metric(text)
    fiscal_year = _extract_fiscal_year(text)
    limit = _extract_limit(text)
    order = "ASC" if re.search(r'\b(bottom|worst|lowest|smallest|least)\b', text, re.I) else "DESC"
    intent = _classify_intent(text, companies, metric)

    return ParsedQuery(
        intent=intent,
        companies=companies,
        metric=metric,
        fiscal_year=fiscal_year,
        limit=limit,
        order=order,
        raw=text,
    )


# ---------------------------------------------------------------------------
# Query execution
# ---------------------------------------------------------------------------

def _compute_ratio(ratio_id: str, company_id: int, fiscal_year: Optional[str], db_path: Optional[str] = None) -> list[dict]:
    """Compute a derived financial ratio for a company."""
    if ratio_id == "debt_to_equity":
        bs_data = db.get_balance_sheet(company_id, fiscal_year, db_path)
        results = []
        for row in bs_data:
            equity = (row.get("equity_capital") or 0) + (row.get("reserves") or 0)
            borrowings = row.get("borrowings") or 0
            de = round(borrowings / equity, 2) if equity > 0 else None
            results.append({
                "fiscal_year": row["fiscal_year"],
                "borrowings": borrowings,
                "equity": equity,
                "debt_to_equity_ratio": de,
            })
        return results
    elif ratio_id == "roe":
        pnl_data = db.get_profit_loss(company_id, fiscal_year, db_path)
        bs_data = db.get_balance_sheet(company_id, fiscal_year, db_path)
        bs_map = {r["fiscal_year"]: r for r in bs_data}
        results = []
        for row in pnl_data:
            fy = row["fiscal_year"]
            bs_row = bs_map.get(fy, {})
            equity = (bs_row.get("equity_capital") or 0) + (bs_row.get("reserves") or 0)
            net_profit = row.get("net_profit") or 0
            roe = round((net_profit / equity) * 100, 2) if equity > 0 else None
            results.append({
                "fiscal_year": fy,
                "net_profit": net_profit,
                "equity": equity,
                "roe_percent": roe,
            })
        return results
    elif ratio_id == "roa":
        pnl_data = db.get_profit_loss(company_id, fiscal_year, db_path)
        bs_data = db.get_balance_sheet(company_id, fiscal_year, db_path)
        bs_map = {r["fiscal_year"]: r for r in bs_data}
        results = []
        for row in pnl_data:
            fy = row["fiscal_year"]
            bs_row = bs_map.get(fy, {})
            total_assets = bs_row.get("total_assets") or 0
            net_profit = row.get("net_profit") or 0
            roa = round((net_profit / total_assets) * 100, 2) if total_assets > 0 else None
            results.append({
                "fiscal_year": fy,
                "net_profit": net_profit,
                "total_assets": total_assets,
                "roa_percent": roa,
            })
        return results
    elif ratio_id == "net_margin":
        pnl_data = db.get_profit_loss(company_id, fiscal_year, db_path)
        results = []
        for row in pnl_data:
            sales = row.get("sales") or 0
            net_profit = row.get("net_profit") or 0
            margin = round((net_profit / sales) * 100, 2) if sales > 0 else None
            results.append({
                "fiscal_year": row["fiscal_year"],
                "net_profit": net_profit,
                "sales": sales,
                "net_margin_percent": margin,
            })
        return results
    return []


def _format_value(val, metric_name: str = "") -> str:
    """Format a numeric value for display."""
    if val is None:
        return "N/A"
    if "percent" in metric_name or "%" in metric_name or metric_name in ("opm", "tax", "roe", "roa"):
        return f"{val}%"
    if abs(val) >= 100_000:
        return f"₹{val:,.0f} Cr"
    if abs(val) >= 1:
        return f"₹{val:,.2f} Cr"
    return str(val)


def _make_suggestions(pq: ParsedQuery) -> list[str]:
    """Generate follow-up query suggestions."""
    suggestions = []
    if pq.companies:
        sym = pq.companies[0]
        if pq.intent == "lookup":
            suggestions.append(f"Show me the full financials of {sym}")
            suggestions.append(f"What is the trend of net profit for {sym}?")
            suggestions.append(f"Compare {sym} with its peers")
        elif pq.intent == "overview":
            suggestions.append(f"What is the debt to equity ratio of {sym}?")
            suggestions.append(f"Revenue trend for {sym}")
        elif pq.intent == "trend":
            suggestions.append(f"Compare {sym} revenue with peers")
            suggestions.append(f"What is the ROE of {sym}?")
    if pq.intent == "rank":
        suggestions.append("Top 10 companies by revenue")
        suggestions.append("Bottom 5 companies by operating margin")
    if not suggestions:
        suggestions = [
            "Top 10 companies by net profit",
            "What is the revenue of Reliance?",
            "Compare TCS and Infosys",
        ]
    return suggestions[:3]


def execute_query(pq: ParsedQuery, db_path: Optional[str] = None) -> dict:
    """Execute a parsed query and return a result dict suitable for QueryResponse."""
    _ensure_cache(db_path)

    if pq.intent == "unknown":
        return {
            "question": pq.raw,
            "intent": "unknown",
            "answer": (
                "I couldn't understand that query. Try asking about a specific company's "
                "financials, comparing companies, or ranking them by a metric."
            ),
            "data": None,
            "sql_executed": None,
            "suggestions": [
                "What is the net profit of Reliance in FY2024?",
                "Top 10 companies by revenue",
                "Compare TCS and Infosys profit",
            ],
        }

    # ----- LOOKUP -----
    if pq.intent == "lookup":
        sym = pq.companies[0]
        company = db.get_company_by_symbol(sym, db_path)
        if not company:
            return _not_found(pq, sym)
        cid = company["id"]
        metric_name, table, column = pq.metric  # type: ignore[misc]

        if table == "__ratio__":
            data = _compute_ratio(column, cid, pq.fiscal_year, db_path)
            if not data:
                return _no_data(pq, company["name"])
            latest = data[-1] if not pq.fiscal_year else data[0]
            ratio_key = [k for k in latest if k not in ("fiscal_year", "net_profit", "sales", "equity", "total_assets", "borrowings")][0]
            val = latest.get(ratio_key)
            answer = f"The {metric_name} of {company['name']} ({sym}) for {latest['fiscal_year']} is {_format_value(val, metric_name)}."
        elif table == "companies":
            val = company.get(column)
            answer = f"The {metric_name} of {company['name']} ({sym}) is {_format_value(val, metric_name)}."
            data = [{"name": company["name"], "nse_symbol": sym, column: val}]
        else:
            getter = {"profit_loss": db.get_profit_loss, "balance_sheet": db.get_balance_sheet, "cash_flow": db.get_cash_flow}[table]
            rows = getter(cid, pq.fiscal_year, db_path)
            if not rows:
                return _no_data(pq, company["name"])
            data = [{r["fiscal_year"]: r.get(column)} for r in rows]
            if pq.fiscal_year and rows:
                val = rows[0].get(column)
                answer = f"The {metric_name} of {company['name']} ({sym}) for {pq.fiscal_year} is {_format_value(val, metric_name)}."
            else:
                parts = [f"{r['fiscal_year']}: {_format_value(r.get(column), metric_name)}" for r in rows]
                answer = f"{metric_name.title()} of {company['name']} ({sym}):\n" + "\n".join(f"  • {p}" for p in parts)
            data = rows

        return {
            "question": pq.raw,
            "intent": "lookup",
            "answer": answer,
            "data": data,
            "sql_executed": None,
            "suggestions": _make_suggestions(pq),
        }

    # ----- COMPARE -----
    if pq.intent == "compare":
        if len(pq.companies) < 2:
            return {
                "question": pq.raw,
                "intent": "compare",
                "answer": "Please mention at least two companies to compare. Example: 'Compare TCS and Infosys revenue'.",
                "data": None,
                "sql_executed": None,
                "suggestions": ["Compare TCS and Infosys net profit", "Compare Reliance and HDFC Bank revenue"],
            }

        metric_name = "net_profit"
        table = "profit_loss"
        column = "net_profit"
        if pq.metric and pq.metric[1] != "__ratio__":
            metric_name, table, column = pq.metric

        results = db.compare_companies(pq.companies, table, pq.fiscal_year, db_path)
        parts = []
        for entry in results:
            if entry.get("error"):
                parts.append(f"  • {entry.get('symbol', '?')}: not found")
                continue
            name = entry["name"]
            sym = entry["nse_symbol"]
            fins = entry.get("financials", [])
            if fins:
                latest = fins[-1]
                val = latest.get(column)
                fy = latest.get("fiscal_year", "")
                parts.append(f"  • {name} ({sym}) [{fy}]: {_format_value(val, metric_name)}")
            else:
                parts.append(f"  • {name} ({sym}): no data")

        answer = f"Comparison of {metric_name} across companies:\n" + "\n".join(parts)
        return {
            "question": pq.raw,
            "intent": "compare",
            "answer": answer,
            "data": results,
            "sql_executed": None,
            "suggestions": _make_suggestions(pq),
        }

    # ----- RANK -----
    if pq.intent == "rank":
        if not pq.metric:
            # Default to net profit
            metric_name, table, column = "net profit", "profit_loss", "net_profit"
        elif pq.metric[1] == "__ratio__":
            return {
                "question": pq.raw,
                "intent": "rank",
                "answer": "Ranking by computed ratios is not yet supported. Try ranking by a direct metric like revenue or net profit.",
                "data": None,
                "sql_executed": None,
                "suggestions": ["Top 10 by net profit", "Top 10 by revenue", "Top 10 by operating margin"],
            }
        elif pq.metric[1] == "companies":
            metric_name, table, column = pq.metric
            # Market cap ranking
            rows = db.rank_companies_by_metric("profit_loss", "sales", pq.fiscal_year, pq.order, pq.limit, db_path)
            # Override with market cap sort
            companies_list, _ = db.search_companies(limit=pq.limit, db_path=db_path)
            data = [
                {"rank": i + 1, "name": c["name"], "nse_symbol": c["nse_symbol"],
                 "market_cap_crores": c["market_cap_crores"]}
                for i, c in enumerate(companies_list)
            ]
            direction = "largest" if pq.order == "DESC" else "smallest"
            answer = f"{direction.title()} {pq.limit} companies by market cap:\n"
            answer += "\n".join(f"  {e['rank']}. {e['name']} ({e['nse_symbol']}): ₹{e['market_cap_crores']:,.0f} Cr" for e in data)
            return {
                "question": pq.raw,
                "intent": "rank",
                "answer": answer,
                "data": data,
                "sql_executed": None,
                "suggestions": _make_suggestions(pq),
            }
        else:
            metric_name, table, column = pq.metric

        rows = db.rank_companies_by_metric(table, column, pq.fiscal_year, pq.order, pq.limit, db_path)
        data = [
            {"rank": i + 1, **r}
            for i, r in enumerate(rows)
        ]
        direction = "Top" if pq.order == "DESC" else "Bottom"
        answer = f"{direction} {pq.limit} companies by {metric_name}:\n"
        answer += "\n".join(
            f"  {e['rank']}. {e['name']} ({e['nse_symbol']}): {_format_value(e['value'], metric_name)}"
            for e in data
        )
        return {
            "question": pq.raw,
            "intent": "rank",
            "answer": answer,
            "data": data,
            "sql_executed": None,
            "suggestions": _make_suggestions(pq),
        }

    # ----- TREND -----
    if pq.intent == "trend":
        sym = pq.companies[0]
        company = db.get_company_by_symbol(sym, db_path)
        if not company:
            return _not_found(pq, sym)
        cid = company["id"]

        if pq.metric and pq.metric[1] != "__ratio__":
            metric_name, table, column = pq.metric
        elif pq.metric and pq.metric[1] == "__ratio__":
            metric_name, _, ratio_id = pq.metric
            data = _compute_ratio(ratio_id, cid, None, db_path)
            answer = f"{metric_name.title()} trend for {company['name']} ({sym}):\n"
            for row in data:
                fy = row["fiscal_year"]
                ratio_key = [k for k in row if k not in ("fiscal_year", "net_profit", "sales", "equity", "total_assets", "borrowings")][0]
                val = row.get(ratio_key)
                answer += f"  • {fy}: {_format_value(val, metric_name)}\n"
            return {
                "question": pq.raw, "intent": "trend", "answer": answer.strip(),
                "data": data, "sql_executed": None, "suggestions": _make_suggestions(pq),
            }
        else:
            metric_name, table, column = "net profit", "profit_loss", "net_profit"

        getter = {"profit_loss": db.get_profit_loss, "balance_sheet": db.get_balance_sheet, "cash_flow": db.get_cash_flow}[table]
        rows = getter(cid, None, db_path)
        if not rows:
            return _no_data(pq, company["name"])

        answer = f"{metric_name.title()} trend for {company['name']} ({sym}):\n"
        for r in rows:
            answer += f"  • {r['fiscal_year']}: {_format_value(r.get(column), metric_name)}\n"

        # Add growth calculation
        if len(rows) >= 2:
            first_val = rows[0].get(column)
            last_val = rows[-1].get(column)
            if first_val and last_val and first_val != 0:
                growth = ((last_val - first_val) / abs(first_val)) * 100
                answer += f"\nOverall growth: {growth:+.1f}%"

        return {
            "question": pq.raw, "intent": "trend", "answer": answer.strip(),
            "data": rows, "sql_executed": None, "suggestions": _make_suggestions(pq),
        }

    # ----- OVERVIEW -----
    if pq.intent == "overview":
        sym = pq.companies[0] if pq.companies else None
        if not sym:
            return {
                "question": pq.raw, "intent": "overview",
                "answer": "Please specify a company. Example: 'Show me Reliance financials'.",
                "data": None, "sql_executed": None,
                "suggestions": ["Reliance financials", "TCS balance sheet", "HDFC Bank overview"],
            }
        company = db.get_company_by_symbol(sym, db_path)
        if not company:
            return _not_found(pq, sym)
        cid = company["id"]
        financials = db.get_full_financials(cid, db_path)

        answer = f"Financial overview of {company['name']} ({sym})"
        if company.get("market_cap_crores"):
            answer += f" | Market Cap: ₹{company['market_cap_crores']:,.0f} Cr"
        answer += "\n\n"

        pnl = financials["profit_loss"]
        if pnl:
            latest = pnl[-1]
            answer += "Latest P&L ({}):\n".format(latest["fiscal_year"])
            if latest.get("sales"):
                answer += f"  Revenue: {_format_value(latest.get('sales'))}\n"
            if latest.get("operating_profit"):
                answer += f"  Operating Profit: {_format_value(latest.get('operating_profit'))}"
                if latest.get("opm_percent"):
                    answer += f" (OPM: {latest.get('opm_percent')}%)"
                answer += "\n"
            answer += f"  Net Profit: {_format_value(latest.get('net_profit'))}\n"
            if latest.get("eps"):
                answer += f"  EPS: ₹{latest.get('eps')}\n"
            answer += "\n"

        bs = financials["balance_sheet"]
        if bs:
            latest_bs = bs[-1]
            answer += "Latest Balance Sheet ({}):\n".format(latest_bs["fiscal_year"])
            answer += f"  Total Assets: {_format_value(latest_bs.get('total_assets'))}\n"
            answer += f"  Borrowings: {_format_value(latest_bs.get('borrowings'))}\n"
            answer += f"  Reserves: {_format_value(latest_bs.get('reserves'))}\n\n"

        cf = financials["cash_flow"]
        if cf:
            latest_cf = cf[-1]
            answer += "Latest Cash Flow ({}):\n".format(latest_cf["fiscal_year"])
            answer += f"  Operating: {_format_value(latest_cf.get('cash_from_operating'))}\n"
            answer += f"  Investing: {_format_value(latest_cf.get('cash_from_investing'))}\n"
            answer += f"  Financing: {_format_value(latest_cf.get('cash_from_financing'))}\n"

        return {
            "question": pq.raw, "intent": "overview", "answer": answer.strip(),
            "data": {"company": company, **financials},
            "sql_executed": None, "suggestions": _make_suggestions(pq),
        }

    # ----- LIST -----
    if pq.intent == "list":
        companies_list, total = db.search_companies(limit=pq.limit, db_path=db_path)
        answer = f"Showing {len(companies_list)} of {total} companies (by market cap):\n"
        for i, c in enumerate(companies_list, 1):
            mcap = f"₹{c['market_cap_crores']:,.0f} Cr" if c.get("market_cap_crores") else "N/A"
            answer += f"  {i}. {c['name']} ({c['nse_symbol']}) — {mcap}\n"
        return {
            "question": pq.raw, "intent": "list", "answer": answer.strip(),
            "data": companies_list, "sql_executed": None,
            "suggestions": ["Top 10 by revenue", "Reliance overview", "Compare TCS and Infosys"],
        }

    return {
        "question": pq.raw, "intent": pq.intent, "answer": "Query type not yet supported.",
        "data": None, "sql_executed": None, "suggestions": _make_suggestions(pq),
    }


def _not_found(pq: ParsedQuery, sym: str) -> dict:
    return {
        "question": pq.raw, "intent": pq.intent,
        "answer": f"Company '{sym}' was not found in the database.",
        "data": None, "sql_executed": None,
        "suggestions": ["List all companies", "Search for a company"],
    }


def _no_data(pq: ParsedQuery, name: str) -> dict:
    return {
        "question": pq.raw, "intent": pq.intent,
        "answer": f"No financial data available for {name} with the specified criteria.",
        "data": None, "sql_executed": None,
        "suggestions": [f"Show {name} overview"],
    }


# ---------------------------------------------------------------------------
# Public high-level API
# ---------------------------------------------------------------------------

def ask(question: str, db_path: Optional[str] = None) -> dict:
    """Main entry point: take a natural-language question and return an answer."""
    parsed = parse_query(question, db_path)
    return execute_query(parsed, db_path)
