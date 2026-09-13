"""Pydantic models for API request/response validation."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------

class CompanyOut(BaseModel):
    id: int
    name: str
    nse_symbol: Optional[str] = None
    bse_code: Optional[str] = None
    isin: Optional[str] = None
    industry: Optional[str] = None
    sector: Optional[str] = None
    market_cap_crores: Optional[float] = None
    is_consolidated: bool = True
    screener_url: Optional[str] = None
    last_updated: Optional[str] = None


class CompanyListResponse(BaseModel):
    companies: list[CompanyOut]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Financials
# ---------------------------------------------------------------------------

class ProfitLossRow(BaseModel):
    fiscal_year: str
    sales: Optional[float] = None
    expenses: Optional[float] = None
    operating_profit: Optional[float] = None
    opm_percent: Optional[float] = None
    other_income: Optional[float] = None
    interest: Optional[float] = None
    depreciation: Optional[float] = None
    profit_before_tax: Optional[float] = None
    tax_percent: Optional[float] = None
    net_profit: Optional[float] = None
    eps: Optional[float] = None
    dividend_payout_percent: Optional[float] = None


class BalanceSheetRow(BaseModel):
    fiscal_year: str
    equity_capital: Optional[float] = None
    reserves: Optional[float] = None
    borrowings: Optional[float] = None
    other_liabilities: Optional[float] = None
    total_liabilities: Optional[float] = None
    fixed_assets: Optional[float] = None
    cwip: Optional[float] = None
    investments: Optional[float] = None
    other_assets: Optional[float] = None
    total_assets: Optional[float] = None


class CashFlowRow(BaseModel):
    fiscal_year: str
    cash_from_operating: Optional[float] = None
    cash_from_investing: Optional[float] = None
    cash_from_financing: Optional[float] = None
    net_cash_flow: Optional[float] = None


class FinancialsResponse(BaseModel):
    company: CompanyOut
    profit_loss: list[ProfitLossRow] = []
    balance_sheet: list[BalanceSheetRow] = []
    cash_flow: list[CashFlowRow] = []


# ---------------------------------------------------------------------------
# Rankings
# ---------------------------------------------------------------------------

class RankingEntry(BaseModel):
    rank: int
    name: str
    nse_symbol: Optional[str] = None
    market_cap_crores: Optional[float] = None
    fiscal_year: str
    value: Optional[float] = None


class RankingResponse(BaseModel):
    metric: str
    table: str
    fiscal_year: Optional[str] = None
    order: str
    results: list[RankingEntry]


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

class ComparisonEntry(BaseModel):
    name: Optional[str] = None
    nse_symbol: Optional[str] = None
    market_cap_crores: Optional[float] = None
    financials: list[dict[str, Any]] = []
    error: Optional[str] = None


class ComparisonResponse(BaseModel):
    table: str
    fiscal_year: Optional[str] = None
    companies: list[ComparisonEntry]


# ---------------------------------------------------------------------------
# Natural Language Query
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Natural language question about Indian equity financial data.",
        examples=[
            "What is the revenue of Reliance in 2024?",
            "Compare net profit of TCS and Infosys",
            "Top 5 companies by operating profit margin",
            "Show me HDFC Bank balance sheet",
        ],
    )


class QueryResponse(BaseModel):
    question: str
    intent: str
    answer: str
    data: Optional[Any] = None
    sql_executed: Optional[str] = None
    suggestions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Health / Stats
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    database: str
    total_companies: int
    total_records: int


class StatsResponse(BaseModel):
    total_companies: int
    profit_loss_records: int
    balance_sheet_records: int
    cash_flow_records: int
    fiscal_years: list[str]
