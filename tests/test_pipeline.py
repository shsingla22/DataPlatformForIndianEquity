"""Tests for the pipeline orchestrator."""

import os
import tempfile
import json
import pytest
from unittest.mock import patch, MagicMock

from src.pipeline import Pipeline
from src.models import init_db, get_db_connection, get_all_companies


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def mock_scraper_data():
    """Mock data returned by the scraper."""
    return {
        "company_info": {
            "name": "Test Corp Ltd",
            "nse_symbol": "TESTCORP",
            "bse_code": "500001",
            "isin": "INE001A01001",
            "industry": "Technology",
            "sector": "IT",
            "market_cap_crores": 50000.0,
            "is_consolidated": True,
        },
        "profit_loss": {
            "Mar 2022": {
                "Sales": 5000.0,
                "Expenses": 4000.0,
                "Operating Profit": 1000.0,
                "OPM %": 20.0,
                "Net Profit": 700.0,
            },
            "Mar 2023": {
                "Sales": 6000.0,
                "Expenses": 4800.0,
                "Operating Profit": 1200.0,
                "OPM %": 20.0,
                "Net Profit": 840.0,
            },
            "Mar 2024": {
                "Sales": 7000.0,
                "Expenses": 5600.0,
                "Operating Profit": 1400.0,
                "OPM %": 20.0,
                "Net Profit": 980.0,
            },
        },
        "balance_sheet": {
            "Mar 2022": {
                "Total Assets": 10000.0,
                "Total Liabilities": 10000.0,
            },
            "Mar 2023": {
                "Total Assets": 12000.0,
                "Total Liabilities": 12000.0,
            },
            "Mar 2024": {
                "Total Assets": 14000.0,
                "Total Liabilities": 14000.0,
            },
        },
        "cash_flow": {
            "Mar 2022": {
                "Cash from Operating Activity": 1500.0,
                "Cash from Investing Activity": -800.0,
                "Cash from Financing Activity": -500.0,
                "Net Cash Flow": 200.0,
            },
            "Mar 2023": {
                "Cash from Operating Activity": 1800.0,
                "Cash from Investing Activity": -900.0,
                "Cash from Financing Activity": -600.0,
                "Net Cash Flow": 300.0,
            },
            "Mar 2024": {
                "Cash from Operating Activity": 2000.0,
                "Cash from Investing Activity": -1000.0,
                "Cash from Financing Activity": -700.0,
                "Net Cash Flow": 300.0,
            },
        },
        "is_consolidated": True,
        "source_url": "https://www.screener.in/company/TESTCORP/consolidated/",
    }


class TestPipelineStorage:
    def test_store_company_data(self, db_path, mock_scraper_data):
        pipeline = Pipeline(db_path=db_path)
        init_db(db_path)

        pipeline._store_company_data(
            "TESTCORP", mock_scraper_data, {"name": "Test Corp", "source": "test"}
        )

        with get_db_connection(db_path) as conn:
            companies = get_all_companies(conn)
            assert len(companies) == 1
            assert companies[0]["nse_symbol"] == "TESTCORP"
            assert companies[0]["is_consolidated"] == 1

            # Check P&L records
            pnl = conn.execute(
                "SELECT COUNT(*) FROM profit_loss WHERE company_id = ?",
                (companies[0]["id"],),
            ).fetchone()[0]
            assert pnl == 3

            # Check Balance Sheet records
            bs = conn.execute(
                "SELECT COUNT(*) FROM balance_sheet WHERE company_id = ?",
                (companies[0]["id"],),
            ).fetchone()[0]
            assert bs == 3

            # Check Cash Flow records
            cf = conn.execute(
                "SELECT COUNT(*) FROM cash_flow WHERE company_id = ?",
                (companies[0]["id"],),
            ).fetchone()[0]
            assert cf == 3

    def test_store_standalone_data(self, db_path, mock_scraper_data):
        pipeline = Pipeline(db_path=db_path)
        init_db(db_path)

        mock_scraper_data["is_consolidated"] = False
        pipeline._store_company_data(
            "TESTCORP", mock_scraper_data, {"name": "Test Corp"}
        )

        with get_db_connection(db_path) as conn:
            companies = get_all_companies(conn)
            assert companies[0]["is_consolidated"] == 0


class TestPipelineRun:
    @patch("src.pipeline.ScreenerScraper")
    @patch("src.pipeline.CompanyListFetcher")
    def test_run_with_specific_symbols(
        self, mock_fetcher_cls, mock_scraper_cls, db_path, mock_scraper_data
    ):
        # Setup mocks
        mock_scraper = MagicMock()
        mock_scraper.scrape_company.return_value = mock_scraper_data
        mock_scraper_cls.return_value = mock_scraper

        pipeline = Pipeline(db_path=db_path)
        stats = pipeline.run(symbols=["TESTCORP"])

        assert stats["companies_processed"] == 1
        assert stats["companies_with_data"] == 1
        assert stats["companies_failed"] == 0

    @patch("src.pipeline.ScreenerScraper")
    @patch("src.pipeline.CompanyListFetcher")
    def test_run_handles_scraper_errors(
        self, mock_fetcher_cls, mock_scraper_cls, db_path
    ):
        from src.screener_scraper import ScraperError

        mock_scraper = MagicMock()
        mock_scraper.scrape_company.side_effect = ScraperError("Page not found")
        mock_scraper_cls.return_value = mock_scraper

        pipeline = Pipeline(db_path=db_path)
        stats = pipeline.run(symbols=["INVALID"])

        assert stats["companies_failed"] == 1
        assert stats["companies_with_data"] == 0

    @patch("src.pipeline.ScreenerScraper")
    @patch("src.pipeline.CompanyListFetcher")
    def test_run_skips_low_market_cap(
        self, mock_fetcher_cls, mock_scraper_cls, db_path, mock_scraper_data
    ):
        # Set market cap below threshold
        mock_scraper_data["company_info"]["market_cap_crores"] = 1000.0
        mock_scraper = MagicMock()
        mock_scraper.scrape_company.return_value = mock_scraper_data
        mock_scraper_cls.return_value = mock_scraper

        pipeline = Pipeline(db_path=db_path)
        stats = pipeline.run(symbols=["SMALLCO"])

        assert stats["companies_skipped_mcap"] == 1
        assert stats["companies_with_data"] == 0


class TestPipelineIntegration:
    """Integration tests using mock HTTP responses."""

    @patch("src.pipeline.ScreenerScraper")
    def test_multiple_companies(self, mock_scraper_cls, db_path, mock_scraper_data):
        mock_scraper = MagicMock()
        mock_scraper.scrape_company.return_value = mock_scraper_data
        mock_scraper_cls.return_value = mock_scraper

        pipeline = Pipeline(db_path=db_path)

        # Process multiple companies
        data2 = mock_scraper_data.copy()
        data2["company_info"] = mock_scraper_data["company_info"].copy()
        data2["company_info"]["name"] = "Another Corp"
        data2["company_info"]["nse_symbol"] = "ANOTHER"
        data2["company_info"]["bse_code"] = "500002"

        def side_effect(symbol):
            if symbol == "TESTCORP":
                return mock_scraper_data
            elif symbol == "ANOTHER":
                return data2
            return None

        mock_scraper.scrape_company.side_effect = side_effect

        stats = pipeline.run(symbols=["TESTCORP", "ANOTHER"])
        assert stats["companies_with_data"] == 2
