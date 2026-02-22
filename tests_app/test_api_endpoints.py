"""Tests for the FastAPI API endpoints."""

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


class TestHealthAndStats:
    def test_health(self):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert data["total_companies"] >= 400

    def test_stats(self):
        r = client.get("/api/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["total_companies"] >= 400
        assert len(data["fiscal_years"]) >= 3


class TestCompaniesEndpoints:
    def test_list_companies(self):
        r = client.get("/api/companies")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 400
        assert len(data["companies"]) == data["page_size"]

    def test_search_companies(self):
        r = client.get("/api/companies?q=reliance")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        symbols = [c["nse_symbol"] for c in data["companies"]]
        assert "RELIANCE" in symbols

    def test_pagination(self):
        r = client.get("/api/companies?page=2&page_size=5")
        assert r.status_code == 200
        data = r.json()
        assert data["page"] == 2
        assert data["page_size"] == 5

    def test_get_company(self):
        r = client.get("/api/companies/TCS")
        assert r.status_code == 200
        assert r.json()["nse_symbol"] == "TCS"

    def test_get_company_not_found(self):
        r = client.get("/api/companies/ZZZZNOTEXIST")
        assert r.status_code == 404

    def test_list_symbols(self):
        r = client.get("/api/companies/symbols")
        assert r.status_code == 200
        symbols = r.json()
        assert len(symbols) >= 400
        assert "TCS" in symbols


class TestFinancialsEndpoints:
    def test_full_financials(self):
        r = client.get("/api/financials/TCS")
        assert r.status_code == 200
        data = r.json()
        assert data["company"]["nse_symbol"] == "TCS"
        assert len(data["profit_loss"]) >= 1
        assert len(data["balance_sheet"]) >= 1
        assert len(data["cash_flow"]) >= 1

    def test_financials_with_year(self):
        r = client.get("/api/financials/TCS?year=Mar+2024")
        assert r.status_code == 200
        data = r.json()
        for row in data["profit_loss"]:
            assert row["fiscal_year"] == "Mar 2024"

    def test_profit_loss(self):
        r = client.get("/api/financials/RELIANCE/profit-loss")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_balance_sheet(self):
        r = client.get("/api/financials/RELIANCE/balance-sheet")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_cash_flow(self):
        r = client.get("/api/financials/RELIANCE/cash-flow")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_financials_not_found(self):
        r = client.get("/api/financials/ZZZZNOTEXIST")
        assert r.status_code == 404


class TestCompareEndpoint:
    def test_compare_two(self):
        r = client.get("/api/compare?symbols=TCS,INFY")
        assert r.status_code == 200
        data = r.json()
        assert len(data["companies"]) == 2
        assert all(c.get("financials") for c in data["companies"])

    def test_compare_with_missing(self):
        r = client.get("/api/compare?symbols=TCS,ZZZZNOTEXIST")
        assert r.status_code == 200
        companies = r.json()["companies"]
        errors = [c for c in companies if c.get("error")]
        assert len(errors) == 1


class TestRankEndpoint:
    def test_rank_default(self):
        r = client.get("/api/rank?metric=net_profit")
        assert r.status_code == 200
        data = r.json()
        assert len(data["results"]) == 10
        assert data["results"][0]["rank"] == 1

    def test_rank_custom(self):
        r = client.get("/api/rank?metric=sales&table=profit_loss&order=DESC&limit=5")
        assert r.status_code == 200
        assert len(r.json()["results"]) == 5


class TestQueryEndpoint:
    def test_nl_query(self):
        r = client.post("/api/query", json={"question": "Top 3 companies by revenue"})
        assert r.status_code == 200
        data = r.json()
        assert data["intent"] == "rank"
        assert data["answer"]
        assert data["data"]

    def test_nl_query_lookup(self):
        r = client.post("/api/query", json={"question": "Net profit of TCS in 2024"})
        assert r.status_code == 200
        assert r.json()["intent"] == "lookup"

    def test_nl_query_validation(self):
        r = client.post("/api/query", json={"question": "ab"})
        assert r.status_code == 422  # Validation error (min_length=3)

    def test_nl_query_overview(self):
        r = client.post("/api/query", json={"question": "Tell me about Reliance"})
        assert r.status_code == 200
        assert r.json()["intent"] == "overview"


class TestUIServing:
    def test_index_html(self):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "EquityIQ" in r.text

    def test_css(self):
        r = client.get("/static/css/main.css")
        assert r.status_code == 200

    def test_js(self):
        r = client.get("/static/js/app.js")
        assert r.status_code == 200
