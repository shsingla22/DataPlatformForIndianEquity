"""Agent 5: Trend Anomaly Detector.

Detects suspicious year-over-year changes that likely indicate data errors.
"""

from qa_agents.base_agent import BaseAgent
from qa_agents.models import Severity


class TrendAnomalyAgent(BaseAgent):
    name = "Trend Anomaly"

    def validate_company(self, company_data):
        is_bank = self.is_bank(company_data)

        pl_list = sorted(company_data.get("profit_loss", []),
                         key=lambda x: x.get("fiscal_year", ""))
        bs_list = sorted(company_data.get("balance_sheet", []),
                         key=lambda x: x.get("fiscal_year", ""))

        # Need at least 2 years for trend analysis
        if len(pl_list) < 2 and len(bs_list) < 2:
            return

        # P&L trend checks
        for i in range(1, len(pl_list)):
            prev = pl_list[i - 1]
            curr = pl_list[i]
            fy = curr.get("fiscal_year", "Unknown")
            prev_fy = prev.get("fiscal_year", "Unknown")

            # Rule 5.1: Revenue YoY change > 200% or < -50%
            if not is_bank:
                prev_sales = self.val(prev.get("sales"))
                curr_sales = self.val(curr.get("sales"))
                if prev_sales is not None and curr_sales is not None and prev_sales > 0:
                    yoy = ((curr_sales - prev_sales) / prev_sales) * 100
                    if yoy > 200:
                        self._finding(company_data, fy, "5.1", Severity.WARNING,
                                      f"Revenue surged {yoy:.0f}% YoY ({prev_sales:,.0f} → {curr_sales:,.0f})",
                                      "< 200% growth", f"{yoy:.0f}% growth")
                    elif yoy < -50:
                        self._finding(company_data, fy, "5.1", Severity.WARNING,
                                      f"Revenue dropped {yoy:.0f}% YoY ({prev_sales:,.0f} → {curr_sales:,.0f})",
                                      "> -50% decline", f"{yoy:.0f}% decline")
                    else:
                        self._pass()

            # Rule 5.2: Net Profit sign flip
            prev_np = self.val(prev.get("net_profit"))
            curr_np = self.val(curr.get("net_profit"))
            if prev_np is not None and curr_np is not None and prev_np != 0 and curr_np != 0:
                if (prev_np > 0) != (curr_np > 0):
                    direction = "profit → loss" if prev_np > 0 else "loss → profit"
                    self._finding(company_data, fy, "5.2", Severity.INFO,
                                  f"Net Profit sign flip ({direction}): {prev_np:,.0f} → {curr_np:,.0f}",
                                  "consistent sign", direction)
                else:
                    self._pass()

            # Rule 5.4: OPM swing > 20pp YoY
            if not is_bank:
                prev_opm = self.val(prev.get("opm_percent"))
                curr_opm = self.val(curr.get("opm_percent"))
                if prev_opm is not None and curr_opm is not None:
                    swing = abs(curr_opm - prev_opm)
                    if swing > 20:
                        self._finding(company_data, fy, "5.4", Severity.WARNING,
                                      f"OPM swung {swing:.1f}pp YoY ({prev_opm:.1f}% → {curr_opm:.1f}%)",
                                      "< 20pp swing", f"{swing:.1f}pp")
                    else:
                        self._pass()

            # Rule 5.5: EPS and Net Profit should move in same direction
            prev_eps = self.val(prev.get("eps"))
            curr_eps = self.val(curr.get("eps"))
            if all(v is not None for v in [prev_np, curr_np, prev_eps, curr_eps]):
                np_up = curr_np > prev_np
                eps_up = curr_eps > prev_eps
                # Only flag if they move in opposite directions and the change is material
                if np_up != eps_up and abs(curr_np - prev_np) > 100:
                    np_dir = "up" if np_up else "down"
                    eps_dir = "up" if eps_up else "down"
                    self._finding(company_data, fy, "5.5", Severity.ERROR,
                                  f"Net Profit went {np_dir} ({prev_np:,.0f}→{curr_np:,.0f}) but EPS went {eps_dir} ({prev_eps:.2f}→{curr_eps:.2f})",
                                  "same direction", f"NP {np_dir}, EPS {eps_dir}")
                else:
                    self._pass()

        # Balance Sheet trend checks
        for i in range(1, len(bs_list)):
            prev = bs_list[i - 1]
            curr = bs_list[i]
            fy = curr.get("fiscal_year", "Unknown")

            # Rule 5.3: Total Assets YoY change > 100% or < -30%
            prev_ta = self.val(prev.get("total_assets"))
            curr_ta = self.val(curr.get("total_assets"))
            if prev_ta is not None and curr_ta is not None and prev_ta > 0:
                yoy = ((curr_ta - prev_ta) / prev_ta) * 100
                if yoy > 100:
                    self._finding(company_data, fy, "5.3", Severity.WARNING,
                                  f"Total Assets surged {yoy:.0f}% YoY ({prev_ta:,.0f} → {curr_ta:,.0f})",
                                  "< 100% growth", f"{yoy:.0f}% growth")
                elif yoy < -30:
                    self._finding(company_data, fy, "5.3", Severity.WARNING,
                                  f"Total Assets dropped {yoy:.0f}% YoY ({prev_ta:,.0f} → {curr_ta:,.0f})",
                                  "> -30% decline", f"{yoy:.0f}% decline")
                else:
                    self._pass()
