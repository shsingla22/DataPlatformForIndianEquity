"""Tests for the database access layer."""

import pytest

from api import database as db


class TestSearchCompanies:
    def test_returns_results(self):
        rows, total = db.search_companies(limit=5)
        assert total >= 400
        assert len(rows) == 5

    def test_keyword_filter(self):
        rows, total = db.search_companies(keyword="reliance")
        assert total >= 1
        symbols = [r["nse_symbol"] for r in rows]
        assert "RELIANCE" in symbols

    def test_market_cap_filter(self):
        rows, _ = db.search_companies(min_market_cap=500000, limit=100)
        for r in rows:
            assert r["market_cap_crores"] >= 500000

    def test_pagination(self):
        page1, _ = db.search_companies(limit=5, offset=0)
        page2, _ = db.search_companies(limit=5, offset=5)
        syms1 = {r["nse_symbol"] for r in page1}
        syms2 = {r["nse_symbol"] for r in page2}
        assert syms1.isdisjoint(syms2)


class TestGetCompanyBySymbol:
    def test_existing(self):
        c = db.get_company_by_symbol("TCS")
        assert c is not None
        assert c["nse_symbol"] == "TCS"

    def test_case_insensitive(self):
        c = db.get_company_by_symbol("tcs")
        assert c is not None
        assert c["nse_symbol"] == "TCS"

    def test_missing(self):
        assert db.get_company_by_symbol("ZZZZNOTEXIST") is None


class TestFinancialData:
    def test_profit_loss(self):
        c = db.get_company_by_symbol("RELIANCE")
        rows = db.get_profit_loss(c["id"])
        assert len(rows) >= 1
        assert "sales" in rows[0]
        assert "net_profit" in rows[0]

    def test_balance_sheet(self):
        c = db.get_company_by_symbol("TCS")
        rows = db.get_balance_sheet(c["id"])
        assert len(rows) >= 1
        assert "total_assets" in rows[0]

    def test_cash_flow(self):
        c = db.get_company_by_symbol("INFY")
        rows = db.get_cash_flow(c["id"])
        assert len(rows) >= 1
        assert "net_cash_flow" in rows[0]

    def test_full_financials(self):
        c = db.get_company_by_symbol("HDFCBANK")
        data = db.get_full_financials(c["id"])
        assert "profit_loss" in data
        assert "balance_sheet" in data
        assert "cash_flow" in data

    def test_fiscal_year_filter(self):
        c = db.get_company_by_symbol("TCS")
        rows = db.get_profit_loss(c["id"], "Mar 2024")
        assert all(r["fiscal_year"] == "Mar 2024" for r in rows)


class TestRankAndCompare:
    def test_rank_by_net_profit(self):
        rows = db.rank_companies_by_metric("profit_loss", "net_profit", limit=5)
        assert len(rows) == 5
        # Should be descending
        values = [r["value"] for r in rows]
        assert values == sorted(values, reverse=True)

    def test_rank_ascending(self):
        rows = db.rank_companies_by_metric("profit_loss", "sales", order="ASC", limit=5)
        values = [r["value"] for r in rows]
        assert values == sorted(values)

    def test_compare(self):
        results = db.compare_companies(["TCS", "INFY"], "profit_loss")
        assert len(results) == 2
        for r in results:
            assert "financials" in r
            assert len(r["financials"]) >= 1

    def test_compare_missing_company(self):
        results = db.compare_companies(["TCS", "ZZZZNOTEXIST"], "profit_loss")
        assert len(results) == 2
        assert results[1].get("error") == "Company not found"

    def test_invalid_table(self):
        with pytest.raises(ValueError, match="Invalid table"):
            db.rank_companies_by_metric("invalid_table", "sales")

    def test_invalid_column(self):
        with pytest.raises(ValueError, match="Invalid column"):
            db.rank_companies_by_metric("profit_loss", "nonexistent_col")


class TestUtilities:
    def test_list_all_symbols(self):
        symbols = db.list_all_symbols()
        assert len(symbols) >= 400
        assert "TCS" in symbols

    def test_available_fiscal_years(self):
        years = db.get_available_fiscal_years()
        assert len(years) >= 3
        assert any("2024" in y for y in years)

    def test_database_stats(self):
        stats = db.get_database_stats()
        assert stats["total_companies"] >= 400
        assert stats["profit_loss_records"] > 0
