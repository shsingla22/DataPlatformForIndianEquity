"""Test suite for Q&A Agent Swarm using in-memory SQLite DTU.

Digital Twin Universe (DTU): We create synthetic companies with known
good/bad data to test each agent independently. This prevents circular
testing — we test agents against known scenarios, not against the real
data they validate.
"""

import pytest

from qa_agents.models import Severity
from qa_agents.pnl_flow_agent import PnlFlowAgent
from qa_agents.balance_sheet_agent import BalanceSheetAgent
from qa_agents.cash_flow_agent import CashFlowAgent
from qa_agents.cross_statement_agent import CrossStatementAgent
from qa_agents.trend_anomaly_agent import TrendAnomalyAgent
from qa_agents.completeness_agent import CompletenessAgent


# ---------------------------------------------------------------------------
# DTU Scenario Companies
# ---------------------------------------------------------------------------

def make_company(symbol, name, pl_list=None, bs_list=None, cf_list=None):
    """Helper to build a company data dict for testing."""
    return {
        "id": 1,
        "nse_symbol": symbol,
        "name": name,
        "profit_loss": pl_list or [],
        "balance_sheet": bs_list or [],
        "cash_flow": cf_list or [],
    }


SCENARIO_CLEAN = make_company(
    "CLEAN", "Clean Corp Ltd",
    pl_list=[
        {
            "fiscal_year": "Mar 2024",
            "sales": 10000, "expenses": 7000, "operating_profit": 3000,
            "opm_percent": 30.0, "other_income": 200, "interest": 300,
            "depreciation": 500, "profit_before_tax": 2400,
            "tax_percent": 25.0, "net_profit": 1800, "eps": 18.0,
            "dividend_payout_percent": 20.0,
        },
        {
            "fiscal_year": "Mar 2025",
            "sales": 12000, "expenses": 8400, "operating_profit": 3600,
            "opm_percent": 30.0, "other_income": 250, "interest": 350,
            "depreciation": 600, "profit_before_tax": 2900,
            "tax_percent": 25.0, "net_profit": 2175, "eps": 21.75,
            "dividend_payout_percent": 22.0,
        },
    ],
    bs_list=[
        {
            "fiscal_year": "Mar 2024",
            "equity_capital": 100, "reserves": 5000, "borrowings": 2000,
            "other_liabilities": 2900, "total_liabilities": 10000,
            "fixed_assets": 4000, "cwip": 500, "investments": 2000,
            "other_assets": 3500, "total_assets": 10000,
        },
        {
            "fiscal_year": "Mar 2025",
            "equity_capital": 100, "reserves": 6800, "borrowings": 2200,
            "other_liabilities": 2900, "total_liabilities": 12000,
            "fixed_assets": 4500, "cwip": 600, "investments": 2400,
            "other_assets": 4500, "total_assets": 12000,
        },
    ],
    cf_list=[
        {
            "fiscal_year": "Mar 2024",
            "cash_from_operating": 2500, "cash_from_investing": -1500,
            "cash_from_financing": -800, "net_cash_flow": 200,
        },
        {
            "fiscal_year": "Mar 2025",
            "cash_from_operating": 3000, "cash_from_investing": -1800,
            "cash_from_financing": -1000, "net_cash_flow": 200,
        },
    ],
)

SCENARIO_BS_BROKEN = make_company(
    "BSBROKEN", "BS Broken Ltd",
    pl_list=[{
        "fiscal_year": "Mar 2025",
        "sales": 5000, "expenses": 3500, "operating_profit": 1500,
        "opm_percent": 30.0, "other_income": 100, "interest": 200,
        "depreciation": 300, "profit_before_tax": 1100,
        "tax_percent": 25.0, "net_profit": 825, "eps": 8.25,
        "dividend_payout_percent": 10.0,
    }],
    bs_list=[{
        "fiscal_year": "Mar 2025",
        "equity_capital": 100, "reserves": 2000, "borrowings": 1000,
        "other_liabilities": 900, "total_liabilities": 4000,
        # Total assets differs by 15% — should trigger Rule 2.1
        "fixed_assets": 2000, "cwip": 100, "investments": 800,
        "other_assets": 1700, "total_assets": 4600,
    }],
    cf_list=[{
        "fiscal_year": "Mar 2025",
        "cash_from_operating": 1200, "cash_from_investing": -500,
        "cash_from_financing": -600, "net_cash_flow": 100,
    }],
)

SCENARIO_PNL_BROKEN = make_company(
    "PNLBROKEN", "PnL Broken Ltd",
    pl_list=[{
        "fiscal_year": "Mar 2025",
        "sales": 8000, "expenses": 5000, "operating_profit": 3000,
        "opm_percent": 37.5, "other_income": 100, "interest": 200,
        "depreciation": 400,
        # PBT should be 3000+100-200-400=2500, but we set it to 1500 (broken)
        "profit_before_tax": 1500,
        "tax_percent": 25.0, "net_profit": 1125, "eps": 11.25,
        "dividend_payout_percent": 10.0,
    }],
    bs_list=[{
        "fiscal_year": "Mar 2025",
        "equity_capital": 100, "reserves": 3000, "borrowings": 500,
        "other_liabilities": 400, "total_liabilities": 4000,
        "fixed_assets": 2000, "cwip": 200, "investments": 800,
        "other_assets": 1000, "total_assets": 4000,
    }],
    cf_list=[{
        "fiscal_year": "Mar 2025",
        "cash_from_operating": 1500, "cash_from_investing": -500,
        "cash_from_financing": -800, "net_cash_flow": 200,
    }],
)

SCENARIO_CF_MISSING = make_company(
    "CFMISSING", "CF Missing Ltd",
    pl_list=[{
        "fiscal_year": "Mar 2025",
        "sales": 6000, "expenses": 4200, "operating_profit": 1800,
        "opm_percent": 30.0, "other_income": 50, "interest": 100,
        "depreciation": 200, "profit_before_tax": 1550,
        "tax_percent": 25.0, "net_profit": 1162, "eps": 11.62,
        "dividend_payout_percent": 15.0,
    }],
    bs_list=[{
        "fiscal_year": "Mar 2025",
        "equity_capital": 100, "reserves": 2500, "borrowings": 800,
        "other_liabilities": 600, "total_liabilities": 4000,
        "fixed_assets": 1500, "cwip": 100, "investments": 1000,
        "other_assets": 1400, "total_assets": 4000,
    }],
    cf_list=[],  # Missing cash flow — Agent 6 must catch
)

SCENARIO_REVENUE_CRASH = make_company(
    "REVCRASH", "Revenue Crash Ltd",
    pl_list=[
        {
            "fiscal_year": "Mar 2024",
            "sales": 20000, "expenses": 14000, "operating_profit": 6000,
            "opm_percent": 30.0, "other_income": 200, "interest": 300,
            "depreciation": 500, "profit_before_tax": 5400,
            "tax_percent": 25.0, "net_profit": 4050, "eps": 40.5,
            "dividend_payout_percent": 20.0,
        },
        {
            "fiscal_year": "Mar 2025",
            # Revenue drops 95% — Agent 5 must catch
            "sales": 1000, "expenses": 900, "operating_profit": 100,
            "opm_percent": 10.0, "other_income": 50, "interest": 100,
            "depreciation": 200, "profit_before_tax": -150,
            "tax_percent": 0.0, "net_profit": -150, "eps": -1.5,
            "dividend_payout_percent": 0.0,
        },
    ],
    bs_list=[
        {
            "fiscal_year": "Mar 2024",
            "equity_capital": 100, "reserves": 8000, "borrowings": 3000,
            "other_liabilities": 1900, "total_liabilities": 13000,
            "fixed_assets": 5000, "cwip": 1000, "investments": 3000,
            "other_assets": 4000, "total_assets": 13000,
        },
        {
            "fiscal_year": "Mar 2025",
            "equity_capital": 100, "reserves": 7850, "borrowings": 3000,
            "other_liabilities": 1900, "total_liabilities": 12850,
            "fixed_assets": 5000, "cwip": 900, "investments": 2950,
            "other_assets": 4000, "total_assets": 12850,
        },
    ],
    cf_list=[
        {
            "fiscal_year": "Mar 2024",
            "cash_from_operating": 5000, "cash_from_investing": -2000,
            "cash_from_financing": -2500, "net_cash_flow": 500,
        },
        {
            "fiscal_year": "Mar 2025",
            "cash_from_operating": 200, "cash_from_investing": -100,
            "cash_from_financing": -50, "net_cash_flow": 50,
        },
    ],
)

SCENARIO_BANK = make_company(
    "BANKTEST", "Test Bank Ltd",
    pl_list=[{
        "fiscal_year": "Mar 2025",
        # Banks have NULL sales, operating_profit, opm_percent
        "sales": None, "expenses": 50000, "operating_profit": None,
        "opm_percent": None, "other_income": 30000, "interest": 40000,
        "depreciation": 1000, "profit_before_tax": 20000,
        "tax_percent": 25.0, "net_profit": 15000, "eps": 15.0,
        "dividend_payout_percent": 20.0,
    }],
    bs_list=[{
        "fiscal_year": "Mar 2025",
        "equity_capital": 500, "reserves": 50000, "borrowings": None,
        "other_liabilities": 149500, "total_liabilities": 200000,
        "fixed_assets": 5000, "cwip": 0, "investments": 80000,
        "other_assets": 115000, "total_assets": 200000,
    }],
    cf_list=[{
        "fiscal_year": "Mar 2025",
        "cash_from_operating": 20000, "cash_from_investing": -5000,
        "cash_from_financing": -10000, "net_cash_flow": 5000,
    }],
)

SCENARIO_CROSS_MISMATCH = make_company(
    "CROSSMIS", "Cross Mismatch Ltd",
    pl_list=[{
        "fiscal_year": "Mar 2025",
        "sales": 7000, "expenses": 5000, "operating_profit": 2000,
        "opm_percent": 28.57, "other_income": 100, "interest": 0,
        "depreciation": 0, "profit_before_tax": 2100,
        "tax_percent": 25.0, "net_profit": 1575, "eps": 15.75,
        "dividend_payout_percent": 10.0,
    }],
    bs_list=[{
        "fiscal_year": "Mar 2025",
        "equity_capital": 100, "reserves": 3000,
        # Has borrowings but interest=0 in P&L — Agent 4 must catch
        "borrowings": 2000,
        "other_liabilities": 900, "total_liabilities": 6000,
        "fixed_assets": 3000, "cwip": 0, "investments": 1000,
        "other_assets": 2000, "total_assets": 6000,
    }],
    cf_list=[{
        "fiscal_year": "Mar 2025",
        "cash_from_operating": 1800, "cash_from_investing": -500,
        "cash_from_financing": -1000, "net_cash_flow": 300,
    }],
)

ALL_SCENARIOS = [
    SCENARIO_CLEAN, SCENARIO_BS_BROKEN, SCENARIO_PNL_BROKEN,
    SCENARIO_CF_MISSING, SCENARIO_REVENUE_CRASH, SCENARIO_BANK,
    SCENARIO_CROSS_MISMATCH,
]


# ---------------------------------------------------------------------------
# Agent 1: P&L Flow Agent Tests
# ---------------------------------------------------------------------------

class TestPnlFlowAgent:
    def test_clean_company_passes(self):
        agent = PnlFlowAgent()
        result = agent.run([SCENARIO_CLEAN])
        errors = [f for f in result.findings if f.severity == Severity.ERROR]
        assert len(errors) == 0, f"Clean company should have no errors: {errors}"

    def test_broken_pbt_detected(self):
        agent = PnlFlowAgent()
        result = agent.run([SCENARIO_PNL_BROKEN])
        rule_ids = [f.rule_id for f in result.findings]
        assert "1.2" in rule_ids, "Should detect broken PBT flow (Rule 1.2)"

    def test_bank_not_flagged_for_null_sales(self):
        agent = PnlFlowAgent()
        result = agent.run([SCENARIO_BANK])
        # Banks should not get flagged for null sales rules (1.1, 1.5, 1.6)
        bank_sales_rules = [f for f in result.findings if f.rule_id in ("1.1", "1.5", "1.6")]
        assert len(bank_sales_rules) == 0, f"Bank should not be flagged for null sales: {bank_sales_rules}"

    def test_satisfaction_computed(self):
        agent = PnlFlowAgent()
        result = agent.run([SCENARIO_CLEAN])
        assert result.satisfaction > 0, "Satisfaction should be computed"
        assert result.total_checks > 0, "Should have run checks"


# ---------------------------------------------------------------------------
# Agent 2: Balance Sheet Agent Tests
# ---------------------------------------------------------------------------

class TestBalanceSheetAgent:
    def test_clean_company_passes(self):
        agent = BalanceSheetAgent()
        result = agent.run([SCENARIO_CLEAN])
        errors = [f for f in result.findings if f.severity == Severity.ERROR]
        assert len(errors) == 0, f"Clean company should have no errors: {errors}"

    def test_broken_bs_detected(self):
        agent = BalanceSheetAgent()
        result = agent.run([SCENARIO_BS_BROKEN])
        rule_ids = [f.rule_id for f in result.findings]
        assert "2.1" in rule_ids, "Should detect Total Assets != Total Liabilities (Rule 2.1)"

    def test_bank_null_borrowings_not_error(self):
        agent = BalanceSheetAgent()
        result = agent.run([SCENARIO_BANK])
        errors = [f for f in result.findings if f.severity == Severity.ERROR]
        assert len(errors) == 0, f"Bank with null borrowings should not error: {errors}"


# ---------------------------------------------------------------------------
# Agent 3: Cash Flow Agent Tests
# ---------------------------------------------------------------------------

class TestCashFlowAgent:
    def test_clean_company_passes(self):
        agent = CashFlowAgent()
        result = agent.run([SCENARIO_CLEAN])
        errors = [f for f in result.findings if f.severity == Severity.ERROR]
        warnings = [f for f in result.findings if f.severity == Severity.WARNING]
        assert len(errors) == 0, f"Clean company should have no errors: {errors}"
        assert len(warnings) == 0, f"Clean company should have no warnings: {warnings}"

    def test_cf_consistency_check(self):
        agent = CashFlowAgent()
        result = agent.run([SCENARIO_CLEAN])
        assert result.total_checks > 0


# ---------------------------------------------------------------------------
# Agent 4: Cross-Statement Agent Tests
# ---------------------------------------------------------------------------

class TestCrossStatementAgent:
    def test_clean_company_passes(self):
        agent = CrossStatementAgent()
        result = agent.run([SCENARIO_CLEAN])
        errors = [f for f in result.findings if f.severity == Severity.ERROR]
        assert len(errors) == 0, f"Clean company should have no errors: {errors}"

    def test_borrowing_interest_mismatch_detected(self):
        agent = CrossStatementAgent()
        result = agent.run([SCENARIO_CROSS_MISMATCH])
        rule_ids = [f.rule_id for f in result.findings]
        assert "4.1" in rule_ids, "Should detect borrowings>0 but interest=0 (Rule 4.1)"

    def test_missing_cf_detected(self):
        agent = CrossStatementAgent()
        result = agent.run([SCENARIO_CF_MISSING])
        rule_ids = [f.rule_id for f in result.findings]
        assert "4.6" in rule_ids, "Should detect missing CF when P&L exists (Rule 4.6)"


# ---------------------------------------------------------------------------
# Agent 5: Trend Anomaly Agent Tests
# ---------------------------------------------------------------------------

class TestTrendAnomalyAgent:
    def test_clean_company_passes(self):
        agent = TrendAnomalyAgent()
        result = agent.run([SCENARIO_CLEAN])
        warnings = [f for f in result.findings if f.severity == Severity.WARNING]
        errors = [f for f in result.findings if f.severity == Severity.ERROR]
        assert len(warnings) == 0, f"Clean company should have no warnings: {warnings}"
        assert len(errors) == 0, f"Clean company should have no errors: {errors}"

    def test_revenue_crash_detected(self):
        agent = TrendAnomalyAgent()
        result = agent.run([SCENARIO_REVENUE_CRASH])
        rule_ids = [f.rule_id for f in result.findings]
        assert "5.1" in rule_ids, "Should detect 95% revenue drop (Rule 5.1)"

    def test_profit_sign_flip_detected(self):
        agent = TrendAnomalyAgent()
        result = agent.run([SCENARIO_REVENUE_CRASH])
        rule_ids = [f.rule_id for f in result.findings]
        assert "5.2" in rule_ids, "Should detect profit sign flip (Rule 5.2)"

    def test_single_year_skipped(self):
        """Company with only 1 year should not produce trend findings."""
        agent = TrendAnomalyAgent()
        result = agent.run([SCENARIO_BS_BROKEN])  # Only 1 year of data
        assert result.total_checks == 0, "Should skip trend analysis for single-year companies"


# ---------------------------------------------------------------------------
# Agent 6: Completeness Agent Tests
# ---------------------------------------------------------------------------

class TestCompletenessAgent:
    def test_clean_company_passes(self):
        agent = CompletenessAgent()
        result = agent.run([SCENARIO_CLEAN])
        errors = [f for f in result.findings if f.severity == Severity.ERROR]
        assert len(errors) == 0, f"Clean company should have no errors: {errors}"

    def test_missing_cf_detected(self):
        agent = CompletenessAgent()
        result = agent.run([SCENARIO_CF_MISSING])
        rule_ids = [f.rule_id for f in result.findings]
        assert "6.1" in rule_ids, "Should detect missing Cash Flow (Rule 6.1)"

    def test_bank_null_sales_not_flagged(self):
        agent = CompletenessAgent()
        result = agent.run([SCENARIO_BANK])
        # Bank should NOT be flagged for null sales (it's sector-appropriate)
        null_findings = [f for f in result.findings
                         if f.rule_id == "6.2" and "sales" in f.message]
        assert len(null_findings) == 0, f"Bank null sales should not be flagged: {null_findings}"

    def test_single_year_warned(self):
        agent = CompletenessAgent()
        result = agent.run([SCENARIO_BS_BROKEN])  # Only 1 year
        rule_ids = [f.rule_id for f in result.findings]
        assert "6.3" in rule_ids, "Should warn about single year of data (Rule 6.3)"


# ---------------------------------------------------------------------------
# Integration: All agents on all scenarios
# ---------------------------------------------------------------------------

class TestAllAgentsIntegration:
    def test_clean_company_no_errors_across_all_agents(self):
        """The CLEAN scenario should produce zero errors from any agent."""
        agents = [
            PnlFlowAgent(), BalanceSheetAgent(), CashFlowAgent(),
            CrossStatementAgent(), TrendAnomalyAgent(), CompletenessAgent(),
        ]
        for agent in agents:
            result = agent.run([SCENARIO_CLEAN])
            errors = [f for f in result.findings if f.severity == Severity.ERROR]
            assert len(errors) == 0, (
                f"{agent.name} produced errors on clean company: "
                f"{[(f.rule_id, f.message) for f in errors]}"
            )

    def test_bank_no_false_positives(self):
        """Bank scenario should not produce false positive errors."""
        agents = [
            PnlFlowAgent(), BalanceSheetAgent(), CashFlowAgent(),
            CrossStatementAgent(), CompletenessAgent(),
        ]
        for agent in agents:
            result = agent.run([SCENARIO_BANK])
            errors = [f for f in result.findings if f.severity == Severity.ERROR]
            assert len(errors) == 0, (
                f"{agent.name} produced errors on bank (false positive): "
                f"{[(f.rule_id, f.message) for f in errors]}"
            )

    def test_each_broken_scenario_caught(self):
        """Each broken scenario should be caught by at least one agent."""
        scenarios_and_expected = [
            (SCENARIO_BS_BROKEN, "2.1", BalanceSheetAgent),
            (SCENARIO_PNL_BROKEN, "1.2", PnlFlowAgent),
            (SCENARIO_CF_MISSING, "6.1", CompletenessAgent),
            (SCENARIO_REVENUE_CRASH, "5.1", TrendAnomalyAgent),
            (SCENARIO_CROSS_MISMATCH, "4.1", CrossStatementAgent),
        ]
        for scenario, expected_rule, agent_cls in scenarios_and_expected:
            agent = agent_cls()
            result = agent.run([scenario])
            rule_ids = [f.rule_id for f in result.findings]
            assert expected_rule in rule_ids, (
                f"{agent.name} should catch Rule {expected_rule} on "
                f"{scenario['nse_symbol']}, but found rules: {rule_ids}"
            )

    def test_satisfaction_all_agents(self):
        """All agents should compute satisfaction on clean data."""
        agents = [
            PnlFlowAgent(), BalanceSheetAgent(), CashFlowAgent(),
            CrossStatementAgent(), TrendAnomalyAgent(), CompletenessAgent(),
        ]
        for agent in agents:
            result = agent.run([SCENARIO_CLEAN])
            assert result.total_checks > 0, f"{agent.name} ran zero checks"
            assert result.satisfaction >= 0, f"{agent.name} has invalid satisfaction"
