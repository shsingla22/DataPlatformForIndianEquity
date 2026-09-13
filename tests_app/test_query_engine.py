"""Tests for the natural language query engine."""

import pytest

from api.query_engine import (
    ParsedQuery,
    ask,
    execute_query,
    parse_query,
    resolve_company,
)


class TestResolveCompany:
    def test_exact_symbol(self):
        assert resolve_company("TCS") == "TCS"

    def test_case_insensitive_symbol(self):
        assert resolve_company("reliance") == "RELIANCE"

    def test_alias(self):
        assert resolve_company("infosys") == "INFY"

    def test_hdfc_bank_alias(self):
        assert resolve_company("hdfc bank") == "HDFCBANK"

    def test_fuzzy_match(self):
        result = resolve_company("Tata Consultancy")
        assert result == "TCS"

    def test_not_found(self):
        assert resolve_company("QuantumFluxDynamics") is None


class TestParseQuery:
    def test_lookup_intent(self):
        pq = parse_query("What is the revenue of Reliance in 2024?")
        assert pq.intent == "lookup"
        assert "RELIANCE" in pq.companies
        assert pq.metric is not None
        assert pq.metric[1] == "profit_loss"
        assert pq.metric[2] == "sales"
        assert pq.fiscal_year == "Mar 2024"

    def test_rank_intent(self):
        pq = parse_query("Top 5 companies by net profit")
        assert pq.intent == "rank"
        assert pq.limit == 5

    def test_compare_intent(self):
        pq = parse_query("Compare TCS and Infosys")
        assert pq.intent == "compare"
        assert len(pq.companies) >= 2

    def test_overview_intent(self):
        pq = parse_query("Show me Reliance financials")
        assert pq.intent == "overview"
        assert "RELIANCE" in pq.companies

    def test_trend_intent(self):
        pq = parse_query("Revenue trend for TCS")
        assert pq.intent == "trend"

    def test_list_intent(self):
        pq = parse_query("List all companies")
        assert pq.intent == "list"

    def test_fiscal_year_fy_format(self):
        pq = parse_query("Revenue of TCS in FY2024")
        assert pq.fiscal_year == "Mar 2024"

    def test_fiscal_year_fy_short(self):
        pq = parse_query("Revenue of TCS in FY24")
        assert pq.fiscal_year == "Mar 2024"

    def test_bottom_order(self):
        pq = parse_query("Bottom 10 companies by operating margin")
        assert pq.order == "ASC"
        assert pq.limit == 10

    def test_metric_extraction_eps(self):
        pq = parse_query("What is the EPS of Reliance?")
        assert pq.metric is not None
        assert pq.metric[2] == "eps"

    def test_metric_extraction_debt(self):
        pq = parse_query("What is the debt of TCS?")
        assert pq.metric is not None
        assert pq.metric[2] == "borrowings"

    def test_calculated_ratio_de(self):
        pq = parse_query("What is the debt to equity ratio of TCS?")
        assert pq.metric is not None
        assert pq.metric[1] == "__ratio__"
        assert pq.metric[2] == "debt_to_equity"

    def test_calculated_ratio_roe(self):
        pq = parse_query("ROE of Reliance")
        assert pq.metric is not None
        assert pq.metric[2] == "roe"


class TestExecuteQuery:
    def test_lookup_revenue(self):
        result = ask("What is the revenue of Reliance in 2024?")
        assert result["intent"] == "lookup"
        assert "Reliance" in result["answer"]
        assert result["data"] is not None

    def test_rank_top5(self):
        result = ask("Top 5 companies by net profit")
        assert result["intent"] == "rank"
        assert result["data"] is not None
        assert len(result["data"]) == 5

    def test_compare_two(self):
        result = ask("Compare TCS and Infosys profit")
        assert result["intent"] == "compare"
        assert "TCS" in result["answer"] or "Tata" in result["answer"]

    def test_overview(self):
        result = ask("Show me TCS financials")
        assert result["intent"] == "overview"
        assert result["data"] is not None

    def test_trend(self):
        result = ask("Revenue growth for Reliance")
        assert result["intent"] in ("trend", "lookup")
        assert result["data"] is not None

    def test_de_ratio(self):
        result = ask("Debt to equity ratio of TCS")
        assert result["intent"] == "lookup"
        assert "debt" in result["answer"].lower() or "TCS" in result["answer"]

    def test_unknown_query(self):
        result = ask("xyz")
        assert result["intent"] == "unknown"

    def test_company_not_found(self):
        result = ask("Revenue of XYZNONEXISTENTCORP in 2024")
        assert "not found" in result["answer"].lower() or result["intent"] == "unknown"

    def test_suggestions_present(self):
        result = ask("Top 10 by revenue")
        assert "suggestions" in result
        assert len(result["suggestions"]) > 0

    def test_list_companies(self):
        result = ask("List all companies")
        assert result["intent"] == "list"
        assert result["data"] is not None


class TestEdgeCases:
    def test_empty_metric_with_company(self):
        result = ask("Tell me about SBIN")
        assert result["intent"] == "overview"

    def test_market_cap_rank(self):
        result = ask("Top 10 companies by market cap")
        assert result["intent"] == "rank"
        assert result["data"] is not None

    def test_multiple_companies_triggers_compare(self):
        pq = parse_query("TCS INFY WIPRO revenue")
        assert pq.intent == "compare"
        assert len(pq.companies) >= 2
