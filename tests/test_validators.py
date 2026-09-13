"""Tests for the data validation module."""

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
)
from src.validators import DataValidator


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    os.unlink(path)


@pytest.fixture
def populated_db(db_path):
    """Create a database with sample data for validation testing."""
    with get_db_connection(db_path) as conn:
        # Insert a company with complete valid data
        company_data = {
            "name": "Test Company",
            "bse_code": "100001",
            "nse_symbol": "TESTCO",
            "isin": "INE001A01001",
            "industry": "Technology",
            "sector": "IT",
            "market_cap_crores": 10000.0,
            "is_consolidated": 1,
            "screener_url": "",
        }
        company_id = insert_company(conn, company_data)

        for year in ["Mar 2022", "Mar 2023", "Mar 2024"]:
            pnl = {
                "Sales": 1000.0,
                "Expenses": 800.0,
                "Operating Profit": 200.0,
                "OPM %": 20.0,
                "Other Income": 50.0,
                "Interest": 30.0,
                "Depreciation": 40.0,
                "Profit before tax": 180.0,
                "Tax %": 25.0,
                "Net Profit": 135.0,
                "EPS in Rs": 10.0,
                "Dividend Payout %": 30.0,
            }
            insert_profit_loss(conn, company_id, year, pnl)

            bs = {
                "Equity Capital": 100.0,
                "Reserves": 500.0,
                "Borrowings": 200.0,
                "Other Liabilities": 200.0,
                "Total Liabilities": 1000.0,
                "Fixed Assets": 400.0,
                "CWIP": 100.0,
                "Investments": 200.0,
                "Other Assets": 300.0,
                "Total Assets": 1000.0,
            }
            insert_balance_sheet(conn, company_id, year, bs)

            cf = {
                "Cash from Operating Activity": 200.0,
                "Cash from Investing Activity": -100.0,
                "Cash from Financing Activity": -50.0,
                "Net Cash Flow": 50.0,
            }
            insert_cash_flow(conn, company_id, year, cf)

    return db_path


class TestDataCompleteness:
    def test_complete_data_no_errors(self, populated_db):
        validator = DataValidator(populated_db)
        errors = validator.validate_all()
        completeness_errors = [e for e in errors if e.check_name == "completeness"]
        assert len(completeness_errors) == 0

    def test_missing_pnl_data(self, db_path):
        with get_db_connection(db_path) as conn:
            company_data = {
                "name": "Incomplete Co",
                "bse_code": None,
                "nse_symbol": "INCOMP",
                "isin": None,
                "industry": None,
                "sector": None,
                "market_cap_crores": 10000.0,
                "is_consolidated": 1,
                "screener_url": "",
            }
            company_id = insert_company(conn, company_data)
            # Only insert 1 year of P&L
            pnl = {"Sales": 100.0, "Net Profit": 10.0}
            insert_profit_loss(conn, company_id, "Mar 2024", pnl)

        validator = DataValidator(db_path)
        errors = validator.validate_all()
        completeness_errors = [e for e in errors if e.check_name == "completeness"]
        assert len(completeness_errors) >= 2  # Missing BS and CF, and incomplete PNL


class TestBalanceSheetEquation:
    def test_balanced_sheet(self, populated_db):
        validator = DataValidator(populated_db)
        errors = validator.validate_all()
        bs_errors = [e for e in errors if e.check_name == "balance_sheet_equation"]
        assert len(bs_errors) == 0

    def test_unbalanced_sheet(self, db_path):
        with get_db_connection(db_path) as conn:
            company_data = {
                "name": "Unbalanced Co",
                "bse_code": None,
                "nse_symbol": "UNBAL",
                "isin": None,
                "industry": None,
                "sector": None,
                "market_cap_crores": 10000.0,
                "is_consolidated": 1,
                "screener_url": "",
            }
            company_id = insert_company(conn, company_data)
            bs = {
                "Total Liabilities": 1000.0,
                "Total Assets": 1200.0,  # 20% mismatch
            }
            insert_balance_sheet(conn, company_id, "Mar 2024", bs)

        validator = DataValidator(db_path)
        errors = validator.validate_all()
        bs_errors = [e for e in errors if e.check_name == "balance_sheet_equation"]
        assert len(bs_errors) >= 1


class TestPnLConsistency:
    def test_consistent_pnl(self, populated_db):
        validator = DataValidator(populated_db)
        errors = validator.validate_all()
        pnl_errors = [e for e in errors if e.check_name == "pnl_consistency"]
        assert len(pnl_errors) == 0

    def test_inconsistent_operating_profit(self, db_path):
        with get_db_connection(db_path) as conn:
            company_data = {
                "name": "Inconsistent Co",
                "bse_code": None,
                "nse_symbol": "INCONS",
                "isin": None,
                "industry": None,
                "sector": None,
                "market_cap_crores": 10000.0,
                "is_consolidated": 1,
                "screener_url": "",
            }
            company_id = insert_company(conn, company_data)
            pnl = {
                "Sales": 1000.0,
                "Expenses": 800.0,
                "Operating Profit": 300.0,  # Should be 200 (1000-800)
            }
            insert_profit_loss(conn, company_id, "Mar 2024", pnl)

        validator = DataValidator(db_path)
        errors = validator.validate_all()
        pnl_errors = [e for e in errors if e.check_name == "pnl_consistency"]
        assert len(pnl_errors) >= 1


class TestCashFlowConsistency:
    def test_consistent_cash_flow(self, populated_db):
        validator = DataValidator(populated_db)
        errors = validator.validate_all()
        cf_errors = [e for e in errors if e.check_name == "cash_flow_consistency"]
        assert len(cf_errors) == 0

    def test_inconsistent_net_cash_flow(self, db_path):
        with get_db_connection(db_path) as conn:
            company_data = {
                "name": "Bad CF Co",
                "bse_code": None,
                "nse_symbol": "BADCF",
                "isin": None,
                "industry": None,
                "sector": None,
                "market_cap_crores": 10000.0,
                "is_consolidated": 1,
                "screener_url": "",
            }
            company_id = insert_company(conn, company_data)
            cf = {
                "Cash from Operating Activity": 200.0,
                "Cash from Investing Activity": -100.0,
                "Cash from Financing Activity": -50.0,
                "Net Cash Flow": 100.0,  # Should be 50 (200-100-50)
            }
            insert_cash_flow(conn, company_id, "Mar 2024", cf)

        validator = DataValidator(db_path)
        errors = validator.validate_all()
        cf_errors = [e for e in errors if e.check_name == "cash_flow_consistency"]
        assert len(cf_errors) >= 1


class TestValidationSummary:
    def test_summary_with_no_errors(self, populated_db):
        validator = DataValidator(populated_db)
        validator.validate_all()
        summary = validator.get_summary()
        assert summary["errors"] == 0

    def test_summary_grouping(self, db_path):
        with get_db_connection(db_path) as conn:
            company_data = {
                "name": "Problem Co",
                "bse_code": None,
                "nse_symbol": "PROB",
                "isin": None,
                "industry": None,
                "sector": None,
                "market_cap_crores": 10000.0,
                "is_consolidated": 1,
                "screener_url": "",
            }
            insert_company(conn, company_data)

        validator = DataValidator(db_path)
        errors = validator.validate_all()
        summary = validator.get_summary()
        assert "completeness" in summary["issues_by_check"]
