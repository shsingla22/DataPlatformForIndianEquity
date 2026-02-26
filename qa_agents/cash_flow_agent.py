"""Agent 3: Cash Flow Integrity Validator.

Validates Cash Flow statement internal consistency per IndAS 7.
"""

from qa_agents.base_agent import BaseAgent
from qa_agents.models import Severity


class CashFlowAgent(BaseAgent):
    name = "Cash Flow"

    def validate_company(self, company_data):
        pl_by_year = {pl["fiscal_year"]: pl for pl in company_data.get("profit_loss", [])}
        bs_by_year = {bs["fiscal_year"]: bs for bs in company_data.get("balance_sheet", [])}
        cf_list = sorted(company_data.get("cash_flow", []), key=lambda x: x.get("fiscal_year", ""))

        consecutive_negative_ocf = 0

        for cf in cf_list:
            fy = cf.get("fiscal_year", "Unknown")
            ocf = self.val(cf.get("cash_from_operating"))
            icf = self.val(cf.get("cash_from_investing"))
            fcf = self.val(cf.get("cash_from_financing"))
            ncf = self.val(cf.get("net_cash_flow"))

            # Rule 3.1: Net CF ≈ Operating + Investing + Financing (±5%)
            if all(v is not None for v in [ocf, icf, fcf, ncf]):
                expected = ocf + icf + fcf
                if abs(expected) > 0:
                    diff = self.safe_pct_diff(ncf, expected)
                    if diff > 5.0:
                        self._finding(company_data, fy, "3.1", Severity.WARNING,
                                      f"Net CF ({ncf:,.0f}) != OCF+ICF+FCF ({expected:,.0f}), diff {diff:.1f}%",
                                      f"{expected:,.0f}", f"{ncf:,.0f}")
                    else:
                        self._pass()
                else:
                    self._pass()

            # Rule 3.2: Profitable company should have positive OCF
            pl = pl_by_year.get(fy, {})
            net_profit = self.val(pl.get("net_profit"))
            if net_profit is not None and net_profit > 0 and ocf is not None:
                if ocf < 0:
                    consecutive_negative_ocf += 1
                    if consecutive_negative_ocf >= 2:
                        self._finding(company_data, fy, "3.2", Severity.WARNING,
                                      f"Profitable (NP={net_profit:,.0f}) but negative OCF ({ocf:,.0f}) for 2+ consecutive years",
                                      "> 0", f"{ocf:,.0f}")
                    else:
                        self._pass()
                else:
                    consecutive_negative_ocf = 0
                    self._pass()

            # Rule 3.3: Investing CF typically negative (info only)
            if icf is not None and icf > 0:
                self._finding(company_data, fy, "3.3", Severity.INFO,
                              f"Investing CF is positive ({icf:,.0f}), unusual for growing companies",
                              "< 0", f"{icf:,.0f}")
            elif icf is not None:
                self._pass()

            # Rule 3.4: |Net CF| should not exceed Total Assets
            bs = bs_by_year.get(fy, {})
            total_assets = self.val(bs.get("total_assets"))
            if ncf is not None and total_assets is not None and total_assets > 0:
                if abs(ncf) > total_assets:
                    self._finding(company_data, fy, "3.4", Severity.WARNING,
                                  f"|Net CF| ({abs(ncf):,.0f}) exceeds Total Assets ({total_assets:,.0f})",
                                  f"< {total_assets:,.0f}", f"{abs(ncf):,.0f}")
                else:
                    self._pass()
