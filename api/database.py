"""Read-only database access layer for the inference API.

This module provides all data access functions that the API and query engine
use to retrieve financial data from the SQLite database. It opens the database
in read-only mode to guarantee the data pipeline's output is never mutated.
"""

import sqlite3
from contextlib import contextmanager
from typing import Optional

from api.config import DB_PATH


@contextmanager
def get_connection(db_path: Optional[str] = None):
    """Open a read-only connection to the financial database."""
    path = db_path or DB_PATH
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Company queries
# ---------------------------------------------------------------------------

def search_companies(
    keyword: Optional[str] = None,
    sector: Optional[str] = None,
    min_market_cap: Optional[float] = None,
    max_market_cap: Optional[float] = None,
    limit: int = 20,
    offset: int = 0,
    db_path: Optional[str] = None,
) -> tuple[list[dict], int]:
    """Search companies with optional filters. Returns (rows, total_count)."""
    conditions: list[str] = []
    params: list = []

    if keyword:
        conditions.append(
            "(LOWER(name) LIKE ? OR LOWER(nse_symbol) LIKE ?)"
        )
        like = f"%{keyword.lower()}%"
        params.extend([like, like])
    if sector:
        conditions.append("LOWER(sector) LIKE ?")
        params.append(f"%{sector.lower()}%")
    if min_market_cap is not None:
        conditions.append("market_cap_crores >= ?")
        params.append(min_market_cap)
    if max_market_cap is not None:
        conditions.append("market_cap_crores <= ?")
        params.append(max_market_cap)

    where = " AND ".join(conditions) if conditions else "1=1"
    with get_connection(db_path) as conn:
        count_row = conn.execute(
            f"SELECT COUNT(*) FROM companies WHERE {where}", params
        ).fetchone()
        total = count_row[0]

        rows = conn.execute(
            f"SELECT * FROM companies WHERE {where} "
            "ORDER BY market_cap_crores DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return [dict(r) for r in rows], total


def get_company_by_symbol(symbol: str, db_path: Optional[str] = None) -> Optional[dict]:
    """Fetch a single company by NSE symbol (case-insensitive)."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM companies WHERE UPPER(nse_symbol) = ?",
            (symbol.upper(),),
        ).fetchone()
    return dict(row) if row else None


def get_company_by_id(company_id: int, db_path: Optional[str] = None) -> Optional[dict]:
    """Fetch a single company by its database ID."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM companies WHERE id = ?", (company_id,)
        ).fetchone()
    return dict(row) if row else None


def list_all_symbols(db_path: Optional[str] = None) -> list[str]:
    """Return all NSE symbols in the database."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT nse_symbol FROM companies ORDER BY nse_symbol"
        ).fetchall()
    return [r["nse_symbol"] for r in rows]


# ---------------------------------------------------------------------------
# Financial data queries
# ---------------------------------------------------------------------------

def get_profit_loss(
    company_id: int,
    fiscal_year: Optional[str] = None,
    db_path: Optional[str] = None,
) -> list[dict]:
    """Get profit & loss records for a company."""
    with get_connection(db_path) as conn:
        if fiscal_year:
            rows = conn.execute(
                "SELECT * FROM profit_loss WHERE company_id = ? AND fiscal_year = ? "
                "ORDER BY fiscal_year",
                (company_id, fiscal_year),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM profit_loss WHERE company_id = ? ORDER BY fiscal_year",
                (company_id,),
            ).fetchall()
    return [dict(r) for r in rows]


def get_balance_sheet(
    company_id: int,
    fiscal_year: Optional[str] = None,
    db_path: Optional[str] = None,
) -> list[dict]:
    """Get balance sheet records for a company."""
    with get_connection(db_path) as conn:
        if fiscal_year:
            rows = conn.execute(
                "SELECT * FROM balance_sheet WHERE company_id = ? AND fiscal_year = ? "
                "ORDER BY fiscal_year",
                (company_id, fiscal_year),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM balance_sheet WHERE company_id = ? ORDER BY fiscal_year",
                (company_id,),
            ).fetchall()
    return [dict(r) for r in rows]


def get_cash_flow(
    company_id: int,
    fiscal_year: Optional[str] = None,
    db_path: Optional[str] = None,
) -> list[dict]:
    """Get cash flow records for a company."""
    with get_connection(db_path) as conn:
        if fiscal_year:
            rows = conn.execute(
                "SELECT * FROM cash_flow WHERE company_id = ? AND fiscal_year = ? "
                "ORDER BY fiscal_year",
                (company_id, fiscal_year),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM cash_flow WHERE company_id = ? ORDER BY fiscal_year",
                (company_id,),
            ).fetchall()
    return [dict(r) for r in rows]


def get_full_financials(
    company_id: int, db_path: Optional[str] = None
) -> dict:
    """Get all financial data for a company (P&L + BS + CF)."""
    return {
        "profit_loss": get_profit_loss(company_id, db_path=db_path),
        "balance_sheet": get_balance_sheet(company_id, db_path=db_path),
        "cash_flow": get_cash_flow(company_id, db_path=db_path),
    }


# ---------------------------------------------------------------------------
# Aggregation / ranking queries
# ---------------------------------------------------------------------------

def rank_companies_by_metric(
    table: str,
    column: str,
    fiscal_year: Optional[str] = None,
    order: str = "DESC",
    limit: int = 10,
    db_path: Optional[str] = None,
) -> list[dict]:
    """Rank companies by a financial metric.

    Parameters
    ----------
    table : str
        One of 'profit_loss', 'balance_sheet', 'cash_flow'.
    column : str
        The column name to rank by.
    fiscal_year : str, optional
        If provided, filter to that fiscal year. Otherwise use the latest
        available year per company.
    order : str
        'DESC' (default, highest first) or 'ASC' (lowest first).
    limit : int
        Number of results.
    """
    allowed_tables = {"profit_loss", "balance_sheet", "cash_flow"}
    if table not in allowed_tables:
        raise ValueError(f"Invalid table: {table}")

    # Validate column exists
    with get_connection(db_path) as conn:
        cursor = conn.execute(f"PRAGMA table_info({table})")
        valid_columns = {row["name"] for row in cursor.fetchall()}
        if column not in valid_columns:
            raise ValueError(f"Invalid column '{column}' for table '{table}'")

    direction = "DESC" if order.upper() == "DESC" else "ASC"

    if fiscal_year:
        sql = f"""
            SELECT c.name, c.nse_symbol, c.market_cap_crores,
                   t.fiscal_year, t.{column} as value
            FROM {table} t
            JOIN companies c ON c.id = t.company_id
            WHERE t.fiscal_year = ? AND t.{column} IS NOT NULL
            ORDER BY t.{column} {direction}
            LIMIT ?
        """
        params: list = [fiscal_year, limit]
    else:
        # Use the latest fiscal year per company
        sql = f"""
            WITH latest AS (
                SELECT company_id, MAX(fiscal_year) AS fy
                FROM {table}
                GROUP BY company_id
            )
            SELECT c.name, c.nse_symbol, c.market_cap_crores,
                   t.fiscal_year, t.{column} as value
            FROM {table} t
            JOIN latest l ON l.company_id = t.company_id AND l.fy = t.fiscal_year
            JOIN companies c ON c.id = t.company_id
            WHERE t.{column} IS NOT NULL
            ORDER BY t.{column} {direction}
            LIMIT ?
        """
        params = [limit]

    with get_connection(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def compare_companies(
    symbols: list[str],
    table: str = "profit_loss",
    fiscal_year: Optional[str] = None,
    db_path: Optional[str] = None,
) -> list[dict]:
    """Retrieve financial data for multiple companies side-by-side.

    Returns a list of dicts, one per company, each containing the company
    info and its financial row(s) for the requested table.
    """
    allowed_tables = {"profit_loss", "balance_sheet", "cash_flow"}
    if table not in allowed_tables:
        raise ValueError(f"Invalid table: {table}")

    results = []
    with get_connection(db_path) as conn:
        for symbol in symbols:
            company = conn.execute(
                "SELECT * FROM companies WHERE UPPER(nse_symbol) = ?",
                (symbol.upper(),),
            ).fetchone()
            if not company:
                results.append({"symbol": symbol, "error": "Company not found"})
                continue

            company_dict = dict(company)
            cid = company_dict["id"]

            if fiscal_year:
                rows = conn.execute(
                    f"SELECT * FROM {table} WHERE company_id = ? AND fiscal_year = ?",
                    (cid, fiscal_year),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT * FROM {table} WHERE company_id = ? ORDER BY fiscal_year",
                    (cid,),
                ).fetchall()

            company_dict["financials"] = [dict(r) for r in rows]
            results.append(company_dict)
    return results


def execute_raw_query(sql: str, params: Optional[list] = None, db_path: Optional[str] = None) -> list[dict]:
    """Execute a read-only SQL query and return results.

    Safety: the connection is opened in read-only mode, so any writes will
    fail at the SQLite level.
    """
    with get_connection(db_path) as conn:
        cursor = conn.execute(sql, params or [])
        if cursor.description is None:
            return []
        return [dict(row) for row in cursor.fetchall()]


def get_available_fiscal_years(db_path: Optional[str] = None) -> list[str]:
    """Return distinct fiscal years across all tables."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT fiscal_year FROM profit_loss "
            "UNION SELECT DISTINCT fiscal_year FROM balance_sheet "
            "UNION SELECT DISTINCT fiscal_year FROM cash_flow "
            "ORDER BY fiscal_year"
        ).fetchall()
    return [r["fiscal_year"] for r in rows]


def get_database_stats(db_path: Optional[str] = None) -> dict:
    """Return summary statistics about the database."""
    with get_connection(db_path) as conn:
        companies = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        pnl = conn.execute("SELECT COUNT(*) FROM profit_loss").fetchone()[0]
        bs = conn.execute("SELECT COUNT(*) FROM balance_sheet").fetchone()[0]
        cf = conn.execute("SELECT COUNT(*) FROM cash_flow").fetchone()[0]
    return {
        "total_companies": companies,
        "profit_loss_records": pnl,
        "balance_sheet_records": bs,
        "cash_flow_records": cf,
    }
