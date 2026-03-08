"""Tests for the data export module."""

import os
import csv
import json
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
from src.exporters import DataExporter


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    os.unlink(path)


@pytest.fixture
def exports_dir():
    d = tempfile.mkdtemp()
    yield d
    # Cleanup
    import shutil
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def populated_db(db_path):
    """Create a database with sample data."""
    with get_db_connection(db_path) as conn:
        company = {
            "name": "Export Test Co",
            "bse_code": "500001",
            "nse_symbol": "EXPORTCO",
            "isin": "INE001A01001",
            "industry": "Technology",
            "sector": "IT",
            "market_cap_crores": 50000.0,
            "is_consolidated": 1,
            "screener_url": "",
        }
        company_id = insert_company(conn, company)

        for year in ["Mar 2022", "Mar 2023", "Mar 2024"]:
            pnl = {
                "Sales": 1000.0, "Expenses": 800.0, "Operating Profit": 200.0,
                "OPM %": 20.0, "Other Income": 50.0, "Interest": 30.0,
                "Depreciation": 40.0, "Profit before tax": 180.0,
                "Tax %": 25.0, "Net Profit": 135.0, "EPS in Rs": 10.0,
                "Dividend Payout %": 30.0,
            }
            insert_profit_loss(conn, company_id, year, pnl)

            bs = {
                "Equity Capital": 100.0, "Reserves": 500.0, "Borrowings": 200.0,
                "Other Liabilities": 200.0, "Total Liabilities": 1000.0,
                "Fixed Assets": 400.0, "CWIP": 100.0, "Investments": 200.0,
                "Other Assets": 300.0, "Total Assets": 1000.0,
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


class TestCSVExports:
    def test_export_company_master(self, populated_db, exports_dir):
        exporter = DataExporter(populated_db, exports_dir)
        exporter.export_company_master()

        filepath = os.path.join(exports_dir, "companies.csv")
        assert os.path.exists(filepath)

        with open(filepath) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["nse_symbol"] == "EXPORTCO"

    def test_export_profit_loss(self, populated_db, exports_dir):
        exporter = DataExporter(populated_db, exports_dir)
        exporter.export_profit_loss()

        filepath = os.path.join(exports_dir, "profit_loss_all.csv")
        assert os.path.exists(filepath)

        with open(filepath) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 3  # 3 years
            assert all(r["nse_symbol"] == "EXPORTCO" for r in rows)
            assert rows[0]["report_type"] == "Consolidated"

    def test_export_balance_sheet(self, populated_db, exports_dir):
        exporter = DataExporter(populated_db, exports_dir)
        exporter.export_balance_sheet()

        filepath = os.path.join(exports_dir, "balance_sheet_all.csv")
        assert os.path.exists(filepath)

        with open(filepath) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 3

    def test_export_cash_flow(self, populated_db, exports_dir):
        exporter = DataExporter(populated_db, exports_dir)
        exporter.export_cash_flow()

        filepath = os.path.join(exports_dir, "cash_flow_all.csv")
        assert os.path.exists(filepath)

        with open(filepath) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 3


class TestCompanyProfiles:
    def test_export_per_company_profiles(self, populated_db, exports_dir):
        exporter = DataExporter(populated_db, exports_dir)
        exporter.export_per_company_profiles()

        profiles_dir = os.path.join(exports_dir, "company_profiles")
        assert os.path.exists(profiles_dir)

        profile_path = os.path.join(profiles_dir, "EXPORTCO.json")
        assert os.path.exists(profile_path)

        with open(profile_path) as f:
            profile = json.load(f)
            assert profile["company"]["nse_symbol"] == "EXPORTCO"
            assert profile["report_type"] == "Consolidated"
            assert len(profile["profit_loss"]) == 3
            assert len(profile["balance_sheet"]) == 3
            assert len(profile["cash_flow"]) == 3


class TestSummaryReport:
    def test_generate_summary(self, populated_db, exports_dir):
        exporter = DataExporter(populated_db, exports_dir)
        summary = exporter.generate_summary_report()

        assert summary["total_companies"] == 1
        assert summary["consolidated_reports"] == 1
        assert summary["standalone_reports"] == 0
        assert summary["profit_loss_records"] == 3
        assert summary["balance_sheet_records"] == 3
        assert summary["cash_flow_records"] == 3
        assert summary["companies_with_complete_3yr_data"] == 1

        # Check the JSON file was created
        filepath = os.path.join(exports_dir, "data_summary.json")
        assert os.path.exists(filepath)
