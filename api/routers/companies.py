"""Company search and detail endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api import database as db
from api.config import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from api.schemas import CompanyListResponse, CompanyOut

router = APIRouter(prefix="/companies", tags=["Companies"])


@router.get("", response_model=CompanyListResponse)
def list_companies(
    q: Optional[str] = Query(None, description="Search by name or symbol"),
    sector: Optional[str] = Query(None, description="Filter by sector"),
    min_market_cap: Optional[float] = Query(None, description="Min market cap in crores"),
    max_market_cap: Optional[float] = Query(None, description="Max market cap in crores"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    """Search and list companies with optional filters and pagination."""
    offset = (page - 1) * page_size
    rows, total = db.search_companies(
        keyword=q,
        sector=sector,
        min_market_cap=min_market_cap,
        max_market_cap=max_market_cap,
        limit=page_size,
        offset=offset,
    )
    return CompanyListResponse(
        companies=[CompanyOut(**r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/symbols", response_model=list[str])
def list_symbols():
    """Return all NSE symbols (useful for autocomplete)."""
    return db.list_all_symbols()


@router.get("/{symbol}", response_model=CompanyOut)
def get_company(symbol: str):
    """Get a single company by NSE symbol."""
    company = db.get_company_by_symbol(symbol)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company '{symbol}' not found")
    return CompanyOut(**company)
