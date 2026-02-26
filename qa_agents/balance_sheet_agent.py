"""Agent 2: Balance Sheet Validator.

Validates that Balance Sheet follows the fundamental accounting equation
and IndAS norms.
"""

from qa_agents.base_agent import BaseAgent
from qa_agents.models import Severity


class BalanceSheetAgent(BaseAgent):
    name = "Balance Sheet"

    def validate_company(self, company_data):
        is_bank = self.is_bank(company_data)
        pl_by_year = {pl["fiscal_year"]: pl for pl in company_data.get("profit_loss", [])}

        for bs in company_data.get("balance_sheet", []):
            fy = bs.get("fiscal_year", "Unknown")
            equity = self.val(bs.get("equity_capital"))
            reserves = self.val(bs.get("reserves"))
            borrowings = self.val(bs.get("borrowings"))
            other_liab = self.val(bs.get("other_liabilities"))
            total_liab = self.val(bs.get("total_liabilities"))
            fixed_assets = self.val(bs.get("fixed_assets"))
            cwip = self.val(bs.get("cwip"))
            investments = self.val(bs.get("investments"))
            other_assets = self.val(bs.get("other_assets"))
            total_assets = self.val(bs.get("total_assets"))

            # Rule 2.1: Total Assets ≈ Total Liabilities (±1%)
            if total_assets is not None and total_liab is not None and total_assets != 0:
                diff = self.safe_pct_diff(total_assets, total_liab)
                if diff > 1.0:
                    self._finding(company_data, fy, "2.1", Severity.ERROR,
                                  f"Total Assets ({total_assets:,.0f}) != Total Liabilities ({total_liab:,.0f}), diff {diff:.2f}%",
                                  f"{total_liab:,.0f}", f"{total_assets:,.0f}")
                else:
                    self._pass()

            # Rule 2.2: Total Liabilities ≈ Equity + Reserves + Borrowings + Other Liabilities (±1%)
            if total_liab is not None and total_liab != 0:
                eq = equity or 0
                res = reserves or 0
                bor = borrowings or 0  # NULL for banks
                ol = other_liab or 0
                computed = eq + res + bor + ol
                diff = self.safe_pct_diff(computed, total_liab)
                if diff > 1.0:
                    self._finding(company_data, fy, "2.2", Severity.WARNING,
                                  f"Sum of components ({computed:,.0f}) != Total Liabilities ({total_liab:,.0f}), diff {diff:.2f}%",
                                  f"{total_liab:,.0f}", f"{computed:,.0f}")
                else:
                    self._pass()

            # Rule 2.3: Total Assets ≈ Fixed Assets + CWIP + Investments + Other Assets (±1%)
            if total_assets is not None and total_assets != 0:
                fa = fixed_assets or 0
                cw = cwip or 0
                inv = investments or 0
                oa = other_assets or 0
                computed = fa + cw + inv + oa
                diff = self.safe_pct_diff(computed, total_assets)
                if diff > 1.0:
                    self._finding(company_data, fy, "2.3", Severity.WARNING,
                                  f"Sum of asset components ({computed:,.0f}) != Total Assets ({total_assets:,.0f}), diff {diff:.2f}%",
                                  f"{total_assets:,.0f}", f"{computed:,.0f}")
                else:
                    self._pass()

            # Rule 2.4: Equity Capital > 0
            if equity is not None:
                if equity > 0:
                    self._pass()
                else:
                    self._finding(company_data, fy, "2.4", Severity.WARNING,
                                  f"Equity Capital ({equity:,.0f}) is not positive",
                                  "> 0", f"{equity:,.0f}")

            # Rule 2.5: Total Assets > 0
            if total_assets is not None:
                if total_assets > 0:
                    self._pass()
                else:
                    self._finding(company_data, fy, "2.5", Severity.ERROR,
                                  f"Total Assets ({total_assets:,.0f}) is not positive",
                                  "> 0", f"{total_assets:,.0f}")

            # Rule 2.6: If Borrowings > 0, Interest in P&L should be > 0
            if not is_bank and borrowings is not None and borrowings > 0:
                pl = pl_by_year.get(fy, {})
                interest = self.val(pl.get("interest"))
                if interest is not None and interest > 0:
                    self._pass()
                elif interest is not None:
                    self._finding(company_data, fy, "2.6", Severity.WARNING,
                                  f"Borrowings ({borrowings:,.0f}) > 0 but Interest ({interest:,.0f}) is not positive",
                                  "> 0", f"{interest:,.0f}")
