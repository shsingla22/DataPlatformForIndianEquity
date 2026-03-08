"""Company comparison and ranking endpoints."""

from typing import Optional

from fastapi import APIRouter, Query

from api import database as db
from api.schemas import (
    ComparisonEntry,
    ComparisonResponse,
    RankingEntry,
    RankingResponse,
)

router = APIRouter(tags=["Compare & Rank"])


@router.get("/compare", response_model=ComparisonResponse)
def compare_companies(
    symbols: str = Query(
        ..., description="Comma-separated NSE symbols, e.g. 'TCS,INFY,WIPRO'"
    ),
    table: str = Query("profit_loss", description="Financial table: profit_loss, balance_sheet, cash_flow"),
    year: Optional[str] = Query(None, description="Fiscal year, e.g. 'Mar 2024'"),
):
    """Compare financial data across multiple companies side-by-side."""
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    results = db.compare_companies(symbol_list, table, year)
    entries = []
    for r in results:
        if r.get("error"):
            entries.append(ComparisonEntry(nse_symbol=r.get("symbol"), error=r["error"]))
        else:
            entries.append(ComparisonEntry(
                name=r["name"],
                nse_symbol=r["nse_symbol"],
                market_cap_crores=r.get("market_cap_crores"),
                financials=r.get("financials", []),
            ))
    return ComparisonResponse(table=table, fiscal_year=year, companies=entries)


@router.get("/rank", response_model=RankingResponse)
def rank_companies(
    metric: str = Query(..., description="Column name, e.g. 'net_profit', 'sales', 'total_assets'"),
    table: str = Query("profit_loss", description="Financial table"),
    year: Optional[str] = Query(None, description="Fiscal year"),
    order: str = Query("DESC", description="DESC (highest first) or ASC"),
    limit: int = Query(10, ge=1, le=50, description="Number of results"),
):
    """Rank companies by a specific financial metric."""
    rows = db.rank_companies_by_metric(table, metric, year, order, limit)
    entries = [
        RankingEntry(rank=i + 1, **r)
        for i, r in enumerate(rows)
    ]
    return RankingResponse(
        metric=metric,
        table=table,
        fiscal_year=year,
        order=order,
        results=entries,
    )
