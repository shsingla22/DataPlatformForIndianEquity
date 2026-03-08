"""Agent 1: P&L Flow Validator.

Validates that Profit & Loss statement follows IndAS income statement flow.
"""

from qa_agents.base_agent import BaseAgent
from qa_agents.models import Severity


class PnlFlowAgent(BaseAgent):
    name = "P&L Flow"

    def validate_company(self, company_data):
        is_bank = self.is_bank(company_data)

        for pl in company_data.get("profit_loss", []):
            fy = pl.get("fiscal_year", "Unknown")
            sales = self.val(pl.get("sales"))
            expenses = self.val(pl.get("expenses"))
            operating_profit = self.val(pl.get("operating_profit"))
            opm_percent = self.val(pl.get("opm_percent"))
            other_income = self.val(pl.get("other_income"))
            interest = self.val(pl.get("interest"))
            depreciation = self.val(pl.get("depreciation"))
            pbt = self.val(pl.get("profit_before_tax"))
            tax_pct = self.val(pl.get("tax_percent"))
            net_profit = self.val(pl.get("net_profit"))
            eps = self.val(pl.get("eps"))

            # Rule 1.1: Operating Profit ≈ Sales - Expenses (±5%)
            if not is_bank and sales is not None and expenses is not None and operating_profit is not None:
                expected_op = sales - expenses
                if sales != 0:
                    diff = self.safe_pct_diff(operating_profit, expected_op)
                    if diff > 5.0:
                        self._finding(company_data, fy, "1.1", Severity.WARNING,
                                      f"Operating Profit ({operating_profit:,.0f}) != Sales - Expenses ({expected_op:,.0f}), diff {diff:.1f}%",
                                      f"{expected_op:,.0f}", f"{operating_profit:,.0f}")
                    else:
                        self._pass()
                else:
                    self._pass()
            elif not is_bank:
                pass  # Can't check, skip without counting
            else:
                self._pass()  # Banks: skip is a pass

            # Rule 1.2: PBT ≈ Operating Profit + Other Income - Interest - Depreciation (±5%)
            if not is_bank and all(v is not None for v in [operating_profit, other_income, interest, depreciation, pbt]):
                expected_pbt = operating_profit + (other_income or 0) - (interest or 0) - (depreciation or 0)
                if abs(expected_pbt) > 0:
                    diff = self.safe_pct_diff(pbt, expected_pbt)
                    if diff > 5.0:
                        self._finding(company_data, fy, "1.2", Severity.WARNING,
                                      f"PBT ({pbt:,.0f}) != OpProfit+OI-Int-Dep ({expected_pbt:,.0f}), diff {diff:.1f}%",
                                      f"{expected_pbt:,.0f}", f"{pbt:,.0f}")
                    else:
                        self._pass()
                else:
                    self._pass()

            # Rule 1.3: Net Profit ≈ PBT × (1 - TaxRate/100) (±10%)
            if pbt is not None and tax_pct is not None and net_profit is not None and pbt != 0:
                expected_np = pbt * (1 - tax_pct / 100.0)
                diff = self.safe_pct_diff(net_profit, expected_np)
                if diff > 10.0:
                    self._finding(company_data, fy, "1.3", Severity.WARNING,
                                  f"Net Profit ({net_profit:,.0f}) != PBT*(1-Tax%) ({expected_np:,.0f}), diff {diff:.1f}%",
                                  f"{expected_np:,.0f}", f"{net_profit:,.0f}")
                else:
                    self._pass()

            # Rule 1.4: Tax Rate between 0% and 45%
            if tax_pct is not None:
                if tax_pct < 0 or tax_pct > 45:
                    self._finding(company_data, fy, "1.4", Severity.WARNING,
                                  f"Tax rate {tax_pct}% outside expected range [0%, 45%]",
                                  "0-45%", f"{tax_pct}%")
                else:
                    self._pass()

            # Rule 1.5: OPM% ≈ (Operating Profit / Sales) × 100 (±2pp)
            if not is_bank and sales is not None and sales > 0 and operating_profit is not None and opm_percent is not None:
                expected_opm = (operating_profit / sales) * 100
                diff = abs(opm_percent - expected_opm)
                if diff > 2.0:
                    self._finding(company_data, fy, "1.5", Severity.WARNING,
                                  f"OPM% ({opm_percent:.1f}%) != computed ({expected_opm:.1f}%), diff {diff:.1f}pp",
                                  f"{expected_opm:.1f}%", f"{opm_percent:.1f}%")
                else:
                    self._pass()

            # Rule 1.6: If Sales > 0, Expenses should be > 0
            if not is_bank and sales is not None and sales > 0:
                if expenses is not None and expenses > 0:
                    self._pass()
                elif expenses is not None:
                    self._finding(company_data, fy, "1.6", Severity.WARNING,
                                  f"Sales ({sales:,.0f}) > 0 but Expenses ({expenses:,.0f}) <= 0",
                                  "> 0", f"{expenses:,.0f}")

            # Rule 1.7: EPS sign should match Net Profit sign
            if eps is not None and net_profit is not None and net_profit != 0 and eps != 0:
                if (eps > 0) != (net_profit > 0):
                    self._finding(company_data, fy, "1.7", Severity.ERROR,
                                  f"EPS sign ({eps:,.2f}) doesn't match Net Profit sign ({net_profit:,.0f})",
                                  "same sign", f"EPS={eps:,.2f}, NP={net_profit:,.0f}")
                else:
                    self._pass()
