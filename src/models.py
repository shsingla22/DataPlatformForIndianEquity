"""Database models and schema for financial data storage."""

import sqlite3
import logging
from contextlib import contextmanager
from src.config import DB_PATH

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    bse_code TEXT,
    nse_symbol TEXT,
    isin TEXT,
    industry TEXT,
    sector TEXT,
    market_cap_crores REAL,
    is_consolidated INTEGER NOT NULL DEFAULT 1,
    screener_url TEXT,
    last_updated TEXT,
    UNIQUE(nse_symbol)
);

CREATE TABLE IF NOT EXISTS profit_loss (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    fiscal_year TEXT NOT NULL,
    sales REAL,
    expenses REAL,
    operating_profit REAL,
    opm_percent REAL,
    other_income REAL,
    interest REAL,
    depreciation REAL,
    profit_before_tax REAL,
    tax_percent REAL,
    net_profit REAL,
    eps REAL,
    dividend_payout_percent REAL,
    is_consolidated INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (company_id) REFERENCES companies(id),
    UNIQUE(company_id, fiscal_year)
);

CREATE TABLE IF NOT EXISTS balance_sheet (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    fiscal_year TEXT NOT NULL,
    equity_capital REAL,
    reserves REAL,
    borrowings REAL,
    other_liabilities REAL,
    total_liabilities REAL,
    fixed_assets REAL,
    cwip REAL,
    investments REAL,
    other_assets REAL,
    total_assets REAL,
    is_consolidated INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (company_id) REFERENCES companies(id),
    UNIQUE(company_id, fiscal_year)
);

CREATE TABLE IF NOT EXISTS cash_flow (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    fiscal_year TEXT NOT NULL,
    cash_from_operating REAL,
    cash_from_investing REAL,
    cash_from_financing REAL,
    net_cash_flow REAL,
    is_consolidated INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (company_id) REFERENCES companies(id),
    UNIQUE(company_id, fiscal_year)
);

CREATE TABLE IF NOT EXISTS scrape_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER,
    nse_symbol TEXT,
    status TEXT NOT NULL,
    error_message TEXT,
    source TEXT,
    timestamp TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

CREATE INDEX IF NOT EXISTS idx_pnl_company ON profit_loss(company_id);
CREATE INDEX IF NOT EXISTS idx_pnl_year ON profit_loss(fiscal_year);
CREATE INDEX IF NOT EXISTS idx_bs_company ON balance_sheet(company_id);
CREATE INDEX IF NOT EXISTS idx_bs_year ON balance_sheet(fiscal_year);
CREATE INDEX IF NOT EXISTS idx_cf_company ON cash_flow(company_id);
CREATE INDEX IF NOT EXISTS idx_cf_year ON cash_flow(fiscal_year);
CREATE INDEX IF NOT EXISTS idx_companies_mcap ON companies(market_cap_crores);
CREATE INDEX IF NOT EXISTS idx_companies_symbol ON companies(nse_symbol);
"""


@contextmanager
def get_db_connection(db_path=None):
    """Context manager for database connections."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path=None):
    """Initialize the database with the schema."""
    path = db_path or DB_PATH
    with get_db_connection(path) as conn:
        conn.executescript(SCHEMA_SQL)
    logger.info("Database initialized at %s", path)


def insert_company(conn, company_data):
    """Insert or update a company record. Returns the company ID."""
    conn.execute(
        """
        INSERT INTO companies (name, bse_code, nse_symbol, isin, industry, sector,
                               market_cap_crores, is_consolidated, screener_url, last_updated)
        VALUES (:name, :bse_code, :nse_symbol, :isin, :industry, :sector,
                :market_cap_crores, :is_consolidated, :screener_url, datetime('now'))
        ON CONFLICT(nse_symbol) DO UPDATE SET
            name = excluded.name,
            bse_code = COALESCE(excluded.bse_code, companies.bse_code),
            isin = COALESCE(excluded.isin, companies.isin),
            industry = COALESCE(excluded.industry, companies.industry),
            sector = COALESCE(excluded.sector, companies.sector),
            market_cap_crores = excluded.market_cap_crores,
            is_consolidated = excluded.is_consolidated,
            screener_url = excluded.screener_url,
            last_updated = datetime('now')
        """,
        company_data,
    )
    cursor = conn.execute(
        "SELECT id FROM companies WHERE nse_symbol = :nse_symbol", company_data
    )
    row = cursor.fetchone()
    return row["id"] if row else None


def _get_value(data, key):
    """Get a value from scraped data dict, trying key with and without '+' suffix.

    Screener.in has expandable row buttons that may leave a '+' in line
    item names even after cleanup.
    """
    val = data.get(key)
    if val is None:
        val = data.get(key + "+")
    return val


def insert_profit_loss(conn, company_id, fiscal_year, data, is_consolidated=True):
    """Insert or update profit & loss data."""
    conn.execute(
        """
        INSERT INTO profit_loss (company_id, fiscal_year, sales, expenses,
            operating_profit, opm_percent, other_income, interest, depreciation,
            profit_before_tax, tax_percent, net_profit, eps,
            dividend_payout_percent, is_consolidated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(company_id, fiscal_year) DO UPDATE SET
            sales = excluded.sales,
            expenses = excluded.expenses,
            operating_profit = excluded.operating_profit,
            opm_percent = excluded.opm_percent,
            other_income = excluded.other_income,
            interest = excluded.interest,
            depreciation = excluded.depreciation,
            profit_before_tax = excluded.profit_before_tax,
            tax_percent = excluded.tax_percent,
            net_profit = excluded.net_profit,
            eps = excluded.eps,
            dividend_payout_percent = excluded.dividend_payout_percent,
            is_consolidated = excluded.is_consolidated
        """,
        (
            company_id,
            fiscal_year,
            _get_value(data, "Sales"),
            _get_value(data, "Expenses"),
            _get_value(data, "Operating Profit"),
            _get_value(data, "OPM %"),
            _get_value(data, "Other Income"),
            _get_value(data, "Interest"),
            _get_value(data, "Depreciation"),
            _get_value(data, "Profit before tax"),
            _get_value(data, "Tax %"),
            _get_value(data, "Net Profit"),
            _get_value(data, "EPS in Rs"),
            _get_value(data, "Dividend Payout %"),
            1 if is_consolidated else 0,
        ),
    )


def insert_balance_sheet(conn, company_id, fiscal_year, data, is_consolidated=True):
    """Insert or update balance sheet data."""
    conn.execute(
        """
        INSERT INTO balance_sheet (company_id, fiscal_year, equity_capital, reserves,
            borrowings, other_liabilities, total_liabilities, fixed_assets, cwip,
            investments, other_assets, total_assets, is_consolidated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(company_id, fiscal_year) DO UPDATE SET
            equity_capital = excluded.equity_capital,
            reserves = excluded.reserves,
            borrowings = excluded.borrowings,
            other_liabilities = excluded.other_liabilities,
            total_liabilities = excluded.total_liabilities,
            fixed_assets = excluded.fixed_assets,
            cwip = excluded.cwip,
            investments = excluded.investments,
            other_assets = excluded.other_assets,
            total_assets = excluded.total_assets,
            is_consolidated = excluded.is_consolidated
        """,
        (
            company_id,
            fiscal_year,
            _get_value(data, "Equity Capital"),
            _get_value(data, "Reserves"),
            _get_value(data, "Borrowings"),
            _get_value(data, "Other Liabilities"),
            _get_value(data, "Total Liabilities"),
            _get_value(data, "Fixed Assets"),
            _get_value(data, "CWIP"),
            _get_value(data, "Investments"),
            _get_value(data, "Other Assets"),
            _get_value(data, "Total Assets"),
            1 if is_consolidated else 0,
        ),
    )


def insert_cash_flow(conn, company_id, fiscal_year, data, is_consolidated=True):
    """Insert or update cash flow data."""
    conn.execute(
        """
        INSERT INTO cash_flow (company_id, fiscal_year, cash_from_operating,
            cash_from_investing, cash_from_financing, net_cash_flow, is_consolidated)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(company_id, fiscal_year) DO UPDATE SET
            cash_from_operating = excluded.cash_from_operating,
            cash_from_investing = excluded.cash_from_investing,
            cash_from_financing = excluded.cash_from_financing,
            net_cash_flow = excluded.net_cash_flow,
            is_consolidated = excluded.is_consolidated
        """,
        (
            company_id,
            fiscal_year,
            _get_value(data, "Cash from Operating Activity"),
            _get_value(data, "Cash from Investing Activity"),
            _get_value(data, "Cash from Financing Activity"),
            _get_value(data, "Net Cash Flow"),
            1 if is_consolidated else 0,
        ),
    )


def log_scrape(conn, company_id, nse_symbol, status, error_message=None, source=None):
    """Log a scraping attempt."""
    conn.execute(
        """
        INSERT INTO scrape_log (company_id, nse_symbol, status, error_message, source)
        VALUES (?, ?, ?, ?, ?)
        """,
        (company_id, nse_symbol, status, error_message, source),
    )


def get_all_companies(conn, min_market_cap=None):
    """Get all companies, optionally filtered by market cap."""
    if min_market_cap:
        cursor = conn.execute(
            "SELECT * FROM companies WHERE market_cap_crores >= ? ORDER BY market_cap_crores DESC",
            (min_market_cap,),
        )
    else:
        cursor = conn.execute(
            "SELECT * FROM companies ORDER BY market_cap_crores DESC"
        )
    return [dict(row) for row in cursor.fetchall()]


def get_company_financial_data(conn, company_id):
    """Get all financial data for a company."""
    pnl = conn.execute(
        "SELECT * FROM profit_loss WHERE company_id = ? ORDER BY fiscal_year",
        (company_id,),
    ).fetchall()
    bs = conn.execute(
        "SELECT * FROM balance_sheet WHERE company_id = ? ORDER BY fiscal_year",
        (company_id,),
    ).fetchall()
    cf = conn.execute(
        "SELECT * FROM cash_flow WHERE company_id = ? ORDER BY fiscal_year",
        (company_id,),
    ).fetchall()
    return {
        "profit_loss": [dict(row) for row in pnl],
        "balance_sheet": [dict(row) for row in bs],
        "cash_flow": [dict(row) for row in cf],
    }
