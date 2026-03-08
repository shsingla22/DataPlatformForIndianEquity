"""Agent 6: Completeness & Freshness Checker.

Ensures full data coverage and no missing fields.
"""

from qa_agents.base_agent import BaseAgent
from qa_agents.models import Severity


class CompletenessAgent(BaseAgent):
    name = "Completeness"

    # Key fields that should not be NULL for non-bank companies
    PL_REQUIRED = ["net_profit", "profit_before_tax", "eps"]
    PL_REQUIRED_NON_BANK = ["sales", "operating_profit"]
    BS_REQUIRED = ["total_assets", "total_liabilities", "equity_capital", "reserves"]
    CF_REQUIRED = ["cash_from_operating", "net_cash_flow"]

    def validate_company(self, company_data):
        is_bank = self.is_bank(company_data)
        symbol = company_data.get("nse_symbol", "UNKNOWN")
        name = company_data.get("name", "Unknown")

        pl_years = {pl["fiscal_year"] for pl in company_data.get("profit_loss", [])}
        bs_years = {bs["fiscal_year"] for bs in company_data.get("balance_sheet", [])}
        cf_years = {cf["fiscal_year"] for cf in company_data.get("cash_flow", [])}
        all_years = sorted(pl_years | bs_years | cf_years)

        # Rule 6.1: Each company should have P&L, BS, AND CF for each fiscal year
        for fy in all_years:
            missing = []
            if fy not in pl_years:
                missing.append("P&L")
            if fy not in bs_years:
                missing.append("Balance Sheet")
            if fy not in cf_years:
                missing.append("Cash Flow")
            if missing:
                self._finding(company_data, fy, "6.1", Severity.ERROR,
                              f"Missing statements: {', '.join(missing)}",
                              "all 3 statements", f"missing {', '.join(missing)}")
            else:
                self._pass()

        # Rule 6.2: Key fields should not be NULL
        for pl in company_data.get("profit_loss", []):
            fy = pl.get("fiscal_year", "Unknown")
            required = self.PL_REQUIRED + ([] if is_bank else self.PL_REQUIRED_NON_BANK)
            null_fields = [f for f in required if pl.get(f) is None]
            if null_fields:
                self._finding(company_data, fy, "6.2", Severity.WARNING,
                              f"P&L has NULL key fields: {', '.join(null_fields)}",
                              "all non-null", f"null: {', '.join(null_fields)}")
            else:
                self._pass()

        for bs in company_data.get("balance_sheet", []):
            fy = bs.get("fiscal_year", "Unknown")
            null_fields = [f for f in self.BS_REQUIRED if bs.get(f) is None]
            if null_fields:
                self._finding(company_data, fy, "6.2", Severity.WARNING,
                              f"BS has NULL key fields: {', '.join(null_fields)}",
                              "all non-null", f"null: {', '.join(null_fields)}")
            else:
                self._pass()

        for cf in company_data.get("cash_flow", []):
            fy = cf.get("fiscal_year", "Unknown")
            null_fields = [f for f in self.CF_REQUIRED if cf.get(f) is None]
            if null_fields:
                self._finding(company_data, fy, "6.2", Severity.WARNING,
                              f"CF has NULL key fields: {', '.join(null_fields)}",
                              "all non-null", f"null: {', '.join(null_fields)}")
            else:
                self._pass()

        # Rule 6.3: Should have at least 2 fiscal years of data
        if len(all_years) < 2:
            self._finding(company_data, "N/A", "6.3", Severity.WARNING,
                          f"Only {len(all_years)} fiscal year(s) of data (need ≥2 for trends)",
                          "≥ 2 years", f"{len(all_years)} year(s)")
        else:
            self._pass()

        # Rule 6.4: Latest fiscal year should be Mar 2024 or newer
        if all_years:
            latest = all_years[-1]
            # Simple check: year portion should be >= 2024
            try:
                year_part = int("".join(c for c in latest if c.isdigit())[:4])
                if year_part >= 2024:
                    self._pass()
                else:
                    self._finding(company_data, latest, "6.4", Severity.WARNING,
                                  f"Latest fiscal year ({latest}) is older than Mar 2024",
                                  "≥ Mar 2024", latest)
            except (ValueError, IndexError):
                self._pass()

        # Rule 6.5: No duplicate fiscal years (schema enforces, but verify)
        for statement_name, years_set, records in [
            ("P&L", pl_years, company_data.get("profit_loss", [])),
            ("BS", bs_years, company_data.get("balance_sheet", [])),
            ("CF", cf_years, company_data.get("cash_flow", [])),
        ]:
            year_list = [r.get("fiscal_year") for r in records]
            if len(year_list) != len(set(year_list)):
                dupes = [y for y in set(year_list) if year_list.count(y) > 1]
                self._finding(company_data, ",".join(dupes), "6.5", Severity.ERROR,
                              f"Duplicate fiscal years in {statement_name}: {', '.join(dupes)}",
                              "unique years", f"duplicates: {', '.join(dupes)}")
            else:
                self._pass()

        # Rule 6.6: Company should have nse_symbol and name populated
        if symbol and symbol != "UNKNOWN" and name and name != "Unknown":
            self._pass()
        else:
            missing = []
            if not symbol or symbol == "UNKNOWN":
                missing.append("nse_symbol")
            if not name or name == "Unknown":
                missing.append("name")
            self._finding(company_data, "N/A", "6.6", Severity.ERROR,
                          f"Company missing: {', '.join(missing)}",
                          "populated", f"missing: {', '.join(missing)}")
