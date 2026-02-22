"""Financial data endpoints — P&L, Balance Sheet, Cash Flow."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api import database as db
from api.schemas import (
    BalanceSheetRow,
    CashFlowRow,
    CompanyOut,
    FinancialsResponse,
    ProfitLossRow,
)

router = APIRouter(prefix="/financials", tags=["Financials"])


def _resolve_company(symbol: str) -> dict:
    company = db.get_company_by_symbol(symbol)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company '{symbol}' not found")
    return company


@router.get("/{symbol}", response_model=FinancialsResponse)
def get_financials(
    symbol: str,
    year: Optional[str] = Query(None, description="Fiscal year, e.g. 'Mar 2024'"),
):
    """Get all financial data for a company (P&L + BS + CF)."""
    company = _resolve_company(symbol)
    cid = company["id"]
    pnl = db.get_profit_loss(cid, year)
    bs = db.get_balance_sheet(cid, year)
    cf = db.get_cash_flow(cid, year)
    return FinancialsResponse(
        company=CompanyOut(**company),
        profit_loss=[ProfitLossRow(**{k: v for k, v in r.items() if k in ProfitLossRow.model_fields}) for r in pnl],
        balance_sheet=[BalanceSheetRow(**{k: v for k, v in r.items() if k in BalanceSheetRow.model_fields}) for r in bs],
        cash_flow=[CashFlowRow(**{k: v for k, v in r.items() if k in CashFlowRow.model_fields}) for r in cf],
    )


@router.get("/{symbol}/profit-loss", response_model=list[ProfitLossRow])
def get_profit_loss(
    symbol: str,
    year: Optional[str] = Query(None, description="Fiscal year"),
):
    """Get profit & loss data for a company."""
    company = _resolve_company(symbol)
    rows = db.get_profit_loss(company["id"], year)
    return [ProfitLossRow(**{k: v for k, v in r.items() if k in ProfitLossRow.model_fields}) for r in rows]


@router.get("/{symbol}/balance-sheet", response_model=list[BalanceSheetRow])
def get_balance_sheet(
    symbol: str,
    year: Optional[str] = Query(None, description="Fiscal year"),
):
    """Get balance sheet data for a company."""
    company = _resolve_company(symbol)
    rows = db.get_balance_sheet(company["id"], year)
    return [BalanceSheetRow(**{k: v for k, v in r.items() if k in BalanceSheetRow.model_fields}) for r in rows]


@router.get("/{symbol}/cash-flow", response_model=list[CashFlowRow])
def get_cash_flow(
    symbol: str,
    year: Optional[str] = Query(None, description="Fiscal year"),
):
    """Get cash flow data for a company."""
    company = _resolve_company(symbol)
    rows = db.get_cash_flow(company["id"], year)
    return [CashFlowRow(**{k: v for k, v in r.items() if k in CashFlowRow.model_fields}) for r in rows]
