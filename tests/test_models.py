"""Tests for database models and operations."""

import os
import tempfile
import pytest
from src.models import (
    init_db,
    get_db_connection,
    insert_company,
    insert_profit_loss,
    insert_balance_sheet,
    insert_cash_flow,
    log_scrape,
    get_all_companies,
    get_company_financial_data,
)


@pytest.fixture
def db_path():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    os.unlink(path)


@pytest.fixture
def sample_company():
    return {
        "name": "Reliance Industries Ltd",
        "bse_code": "500325",
        "nse_symbol": "RELIANCE",
        "isin": "INE002A01018",
        "industry": "Oil & Gas",
        "sector": "Energy",
        "market_cap_crores": 1700000.0,
        "is_consolidated": 1,
        "screener_url": "https://www.screener.in/company/RELIANCE/consolidated/",
    }


@pytest.fixture
def sample_pnl_data():
    return {
        "Sales": 615840.0,
        "Expenses": 532450.0,
        "Operating Profit": 83390.0,
        "OPM %": 13.54,
        "Other Income": 15420.0,
        "Interest": 17560.0,
        "Depreciation": 28310.0,
        "Profit before tax": 52940.0,
        "Tax %": 23.5,
        "Net Profit": 69621.0,
        "EPS in Rs": 102.94,
        "Dividend Payout %": 8.74,
    }


@pytest.fixture
def sample_bs_data():
    return {
        "Equity Capital": 6766.0,
        "Reserves": 498000.0,
        "Borrowings": 310000.0,
        "Other Liabilities": 290000.0,
        "Total Liabilities": 1104766.0,
        "Fixed Assets": 480000.0,
        "CWIP": 120000.0,
        "Investments": 280000.0,
        "Other Assets": 224766.0,
        "Total Assets": 1104766.0,
    }


@pytest.fixture
def sample_cf_data():
    return {
        "Cash from Operating Activity": 85000.0,
        "Cash from Investing Activity": -65000.0,
        "Cash from Financing Activity": -18000.0,
        "Net Cash Flow": 2000.0,
    }


class TestDatabaseInit:
    def test_init_db_creates_tables(self, db_path):
        with get_db_connection(db_path) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {row["name"] for row in tables}
            assert "companies" in table_names
            assert "profit_loss" in table_names
            assert "balance_sheet" in table_names
            assert "cash_flow" in table_names
            assert "scrape_log" in table_names

    def test_init_db_idempotent(self, db_path):
        # Should not fail when called multiple times
        init_db(db_path)
        init_db(db_path)


class TestCompanyOperations:
    def test_insert_company(self, db_path, sample_company):
        with get_db_connection(db_path) as conn:
            company_id = insert_company(conn, sample_company)
            assert company_id is not None
            assert company_id > 0

    def test_insert_company_upsert(self, db_path, sample_company):
        with get_db_connection(db_path) as conn:
            id1 = insert_company(conn, sample_company)
            # Update market cap
            sample_company["market_cap_crores"] = 1800000.0
            id2 = insert_company(conn, sample_company)
            assert id1 == id2

            # Verify updated value
            row = conn.execute(
                "SELECT market_cap_crores FROM companies WHERE id = ?", (id1,)
            ).fetchone()
            assert row["market_cap_crores"] == 1800000.0

    def test_get_all_companies(self, db_path, sample_company):
        with get_db_connection(db_path) as conn:
            insert_company(conn, sample_company)

        with get_db_connection(db_path) as conn:
            companies = get_all_companies(conn)
            assert len(companies) == 1
            assert companies[0]["nse_symbol"] == "RELIANCE"

    def test_get_all_companies_with_market_cap_filter(self, db_path, sample_company):
        with get_db_connection(db_path) as conn:
            insert_company(conn, sample_company)
            # Insert a small company
            small_company = sample_company.copy()
            small_company["nse_symbol"] = "SMALLCO"
            small_company["market_cap_crores"] = 500.0
            insert_company(conn, small_company)

        with get_db_connection(db_path) as conn:
            companies = get_all_companies(conn, min_market_cap=1000)
            assert len(companies) == 1
            assert companies[0]["nse_symbol"] == "RELIANCE"


class TestFinancialDataOperations:
    def test_insert_profit_loss(self, db_path, sample_company, sample_pnl_data):
        with get_db_connection(db_path) as conn:
            company_id = insert_company(conn, sample_company)
            insert_profit_loss(conn, company_id, "Mar 2024", sample_pnl_data)

            row = conn.execute(
                "SELECT * FROM profit_loss WHERE company_id = ?", (company_id,)
            ).fetchone()
            assert row is not None
            assert row["fiscal_year"] == "Mar 2024"
            assert row["sales"] == 615840.0
            assert row["net_profit"] == 69621.0
            assert row["is_consolidated"] == 1

    def test_insert_balance_sheet(self, db_path, sample_company, sample_bs_data):
        with get_db_connection(db_path) as conn:
            company_id = insert_company(conn, sample_company)
            insert_balance_sheet(conn, company_id, "Mar 2024", sample_bs_data)

            row = conn.execute(
                "SELECT * FROM balance_sheet WHERE company_id = ?", (company_id,)
            ).fetchone()
            assert row is not None
            assert row["total_assets"] == 1104766.0
            assert row["total_liabilities"] == 1104766.0

    def test_insert_cash_flow(self, db_path, sample_company, sample_cf_data):
        with get_db_connection(db_path) as conn:
            company_id = insert_company(conn, sample_company)
            insert_cash_flow(conn, company_id, "Mar 2024", sample_cf_data)

            row = conn.execute(
                "SELECT * FROM cash_flow WHERE company_id = ?", (company_id,)
            ).fetchone()
            assert row is not None
            assert row["cash_from_operating"] == 85000.0
            assert row["net_cash_flow"] == 2000.0

    def test_insert_standalone_data(self, db_path, sample_company, sample_pnl_data):
        with get_db_connection(db_path) as conn:
            company_id = insert_company(conn, sample_company)
            insert_profit_loss(
                conn, company_id, "Mar 2024", sample_pnl_data, is_consolidated=False
            )

            row = conn.execute(
                "SELECT * FROM profit_loss WHERE company_id = ?", (company_id,)
            ).fetchone()
            assert row["is_consolidated"] == 0

    def test_upsert_financial_data(self, db_path, sample_company, sample_pnl_data):
        with get_db_connection(db_path) as conn:
            company_id = insert_company(conn, sample_company)
            insert_profit_loss(conn, company_id, "Mar 2024", sample_pnl_data)

            # Update with new data
            updated = sample_pnl_data.copy()
            updated["Sales"] = 700000.0
            insert_profit_loss(conn, company_id, "Mar 2024", updated)

            row = conn.execute(
                "SELECT sales FROM profit_loss WHERE company_id = ? AND fiscal_year = ?",
                (company_id, "Mar 2024"),
            ).fetchone()
            assert row["sales"] == 700000.0

    def test_get_company_financial_data(
        self, db_path, sample_company, sample_pnl_data, sample_bs_data, sample_cf_data
    ):
        with get_db_connection(db_path) as conn:
            company_id = insert_company(conn, sample_company)

            for year in ["Mar 2022", "Mar 2023", "Mar 2024"]:
                insert_profit_loss(conn, company_id, year, sample_pnl_data)
                insert_balance_sheet(conn, company_id, year, sample_bs_data)
                insert_cash_flow(conn, company_id, year, sample_cf_data)

        with get_db_connection(db_path) as conn:
            data = get_company_financial_data(conn, company_id)
            assert len(data["profit_loss"]) == 3
            assert len(data["balance_sheet"]) == 3
            assert len(data["cash_flow"]) == 3


class TestScrapeLog:
    def test_log_success(self, db_path, sample_company):
        with get_db_connection(db_path) as conn:
            company_id = insert_company(conn, sample_company)
            log_scrape(conn, company_id, "RELIANCE", "success", source="screener.in")

            row = conn.execute(
                "SELECT * FROM scrape_log WHERE company_id = ?", (company_id,)
            ).fetchone()
            assert row["status"] == "success"

    def test_log_error(self, db_path):
        with get_db_connection(db_path) as conn:
            log_scrape(conn, None, "UNKNOWN", "error", "Page not found")

            row = conn.execute(
                "SELECT * FROM scrape_log WHERE nse_symbol = 'UNKNOWN'"
            ).fetchone()
            assert row["status"] == "error"
            assert row["error_message"] == "Page not found"
