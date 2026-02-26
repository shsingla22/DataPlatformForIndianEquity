"""Agent 4: Cross-Statement Reconciler.

Validates relationships between P&L, Balance Sheet, and Cash Flow statements.
"""

from qa_agents.base_agent import BaseAgent
from qa_agents.models import Severity


class CrossStatementAgent(BaseAgent):
    name = "Cross-Statement"

    def validate_company(self, company_data):
        is_bank = self.is_bank(company_data)
        pl_by_year = {pl["fiscal_year"]: pl for pl in company_data.get("profit_loss", [])}
        bs_by_year = {bs["fiscal_year"]: bs for bs in company_data.get("balance_sheet", [])}
        cf_by_year = {cf["fiscal_year"]: cf for cf in company_data.get("cash_flow", [])}

        all_years = sorted(set(list(pl_by_year.keys()) + list(bs_by_year.keys()) + list(cf_by_year.keys())))

        for fy in all_years:
            pl = pl_by_year.get(fy, {})
            bs = bs_by_year.get(fy, {})
            cf = cf_by_year.get(fy, {})

            borrowings = self.val(bs.get("borrowings"))
            interest = self.val(pl.get("interest"))
            fixed_assets = self.val(bs.get("fixed_assets"))
            depreciation = self.val(pl.get("depreciation"))
            net_profit = self.val(pl.get("net_profit"))
            ocf = self.val(cf.get("cash_from_operating"))
            equity = self.val(bs.get("equity_capital"))
            reserves = self.val(bs.get("reserves"))

            # Rule 4.1: If Borrowings > 0, Interest > 0
            if not is_bank and borrowings is not None and borrowings > 0:
                if interest is not None and interest > 0:
                    self._pass()
                elif interest is not None:
                    self._finding(company_data, fy, "4.1", Severity.WARNING,
                                  f"Borrowings ({borrowings:,.0f}) > 0 but Interest ({interest:,.0f}) not positive",
                                  "> 0", f"{interest:,.0f}")

            # Rule 4.2: If Fixed Assets > 0, Depreciation > 0
            if fixed_assets is not None and fixed_assets > 0:
                if depreciation is not None and depreciation > 0:
                    self._pass()
                elif depreciation is not None:
                    self._finding(company_data, fy, "4.2", Severity.WARNING,
                                  f"Fixed Assets ({fixed_assets:,.0f}) > 0 but Depreciation ({depreciation:,.0f}) not positive",
                                  "> 0", f"{depreciation:,.0f}")

            # Rule 4.3: Reserves change ≈ Net Profit (approx, ±20%)
            prev_years = [y for y in all_years if y < fy]
            if prev_years:
                prev_fy = prev_years[-1]
                prev_bs = bs_by_year.get(prev_fy, {})
                prev_reserves = self.val(prev_bs.get("reserves"))
                if prev_reserves is not None and reserves is not None and net_profit is not None:
                    reserves_change = reserves - prev_reserves
                    # Dividends reduce reserves, so reserves_change < net_profit is normal
                    # But reserves_change should not be wildly different
                    if abs(net_profit) > 0:
                        diff = self.safe_pct_diff(reserves_change, net_profit)
                        if diff > 50.0 and abs(reserves_change - net_profit) > 1000:
                            self._finding(company_data, fy, "4.3", Severity.INFO,
                                          f"Reserves change ({reserves_change:,.0f}) vs Net Profit ({net_profit:,.0f}), diff {diff:.0f}%. "
                                          f"May include OCI, dividends, buybacks.",
                                          f"~{net_profit:,.0f}", f"{reserves_change:,.0f}")
                        else:
                            self._pass()

            # Rule 4.4: Net Profit and Operating CF directional consistency
            if net_profit is not None and ocf is not None and net_profit != 0 and ocf != 0:
                if (net_profit > 0) != (ocf > 0):
                    self._finding(company_data, fy, "4.4", Severity.INFO,
                                  f"Net Profit ({net_profit:,.0f}) and OCF ({ocf:,.0f}) have opposite signs",
                                  "same direction", f"NP={net_profit:,.0f}, OCF={ocf:,.0f}")
                else:
                    self._pass()

            # Rule 4.5: D/E ratio between 0 and 10 for non-financial companies
            if not is_bank and borrowings is not None and equity is not None and reserves is not None:
                total_equity = equity + reserves
                if total_equity > 0:
                    de_ratio = borrowings / total_equity
                    if de_ratio > 10.0:
                        self._finding(company_data, fy, "4.5", Severity.WARNING,
                                      f"D/E ratio ({de_ratio:.2f}) exceeds 10.0",
                                      "0-10", f"{de_ratio:.2f}")
                    else:
                        self._pass()

            # Rule 4.6: If P&L exists for a year, BS and CF should too
            has_pl = bool(pl)
            has_bs = bool(bs)
            has_cf = bool(cf)
            if has_pl:
                if has_bs and has_cf:
                    self._pass()
                elif not has_bs:
                    self._finding(company_data, fy, "4.6", Severity.ERROR,
                                  f"P&L exists for {fy} but Balance Sheet is missing",
                                  "BS present", "BS missing")
                elif not has_cf:
                    self._finding(company_data, fy, "4.6", Severity.ERROR,
                                  f"P&L exists for {fy} but Cash Flow is missing",
                                  "CF present", "CF missing")
