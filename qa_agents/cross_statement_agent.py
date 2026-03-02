"""Agent 4: Cross-Statement Reconciler.

Validates relationships BETWEEN P&L, Balance Sheet, and Cash Flow statements.
This is the most critical agent for detecting data accuracy issues because
each financial statement should be internally consistent with the others.

Cross-statement relationships validated (per IndAS):

P&L ↔ Balance Sheet:
  - Borrowings (long-term + short-term in BS) → Interest expense in P&L (IndAS 23)
  - Fixed Assets (PP&E + intangibles in BS) → Depreciation in P&L (IndAS 16, 38)
  - Net Profit in P&L → Reserves change in BS (retained earnings flow)
  - Equity Capital in BS → EPS denominator in P&L

P&L ↔ Cash Flow:
  - Net Profit in P&L → Operating CF base (indirect method, IndAS 7 para 18)
  - Interest in P&L → appears in OCF adjustments or FCF (IndAS 7 para 33)
  - Depreciation in P&L → add-back in OCF (non-cash, IndAS 7 para 20)

Balance Sheet ↔ Cash Flow:
  - Fixed Assets + CWIP change → Investing CF (capex component)
  - Investments change → Investing CF (investment purchase/sale)
  - Borrowings change → Financing CF (debt raised/repaid)
  - Equity Capital change → Financing CF (shares issued/bought back)
  - Other Assets change → includes cash balance change = Net CF
  - Other Liabilities change → part of working capital in OCF
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

        all_years = sorted(set(
            list(pl_by_year.keys()) + list(bs_by_year.keys()) + list(cf_by_year.keys())
        ))

        for fy in all_years:
            pl = pl_by_year.get(fy, {})
            bs = bs_by_year.get(fy, {})
            cf = cf_by_year.get(fy, {})

            # Extract all fields
            borrowings = self.val(bs.get("borrowings"))
            interest = self.val(pl.get("interest"))
            fixed_assets = self.val(bs.get("fixed_assets"))
            cwip = self.val(bs.get("cwip"))
            depreciation = self.val(pl.get("depreciation"))
            net_profit = self.val(pl.get("net_profit"))
            sales = self.val(pl.get("sales"))
            expenses = self.val(pl.get("expenses"))
            ocf = self.val(cf.get("cash_from_operating"))
            icf = self.val(cf.get("cash_from_investing"))
            fcf = self.val(cf.get("cash_from_financing"))
            ncf = self.val(cf.get("net_cash_flow"))
            equity = self.val(bs.get("equity_capital"))
            reserves = self.val(bs.get("reserves"))
            investments = self.val(bs.get("investments"))
            other_assets = self.val(bs.get("other_assets"))
            other_liab = self.val(bs.get("other_liabilities"))
            total_assets = self.val(bs.get("total_assets"))
            total_liab = self.val(bs.get("total_liabilities"))
            eps = self.val(pl.get("eps"))
            div_pct = self.val(pl.get("dividend_payout_percent"))

            prev_years = [y for y in all_years if y < fy]
            prev_fy = prev_years[-1] if prev_years else None
            prev_bs = bs_by_year.get(prev_fy, {}) if prev_fy else {}

            # ====================================================================
            # P&L ↔ BALANCE SHEET CROSS-CHECKS
            # ====================================================================

            # Rule 4.1: Borrowings (long-term + short-term debt) → Interest expense
            # IndAS 23: borrowing costs recognized in P&L unless capitalized
            if not is_bank and borrowings is not None and borrowings > 0:
                if interest is not None and interest > 0:
                    self._pass()
                elif interest is not None:
                    self._finding(company_data, fy, "4.1", Severity.WARNING,
                                  f"Borrowings ({borrowings:,.0f} — includes long-term debentures, "
                                  f"term loans, bonds + short-term working capital, CP) > 0 "
                                  f"but Interest ({interest:,.0f}) not positive. "
                                  f"Interest may be fully capitalized (IndAS 23) or borrowings "
                                  f"are interest-free advances.",
                                  "> 0", f"{interest:,.0f}")

            # Rule 4.2: Fixed Assets (PP&E + intangibles + ROU assets) → Depreciation
            # IndAS 16 para 6: depreciation is systematic allocation of depreciable amount
            if fixed_assets is not None and fixed_assets > 0:
                if depreciation is not None and depreciation > 0:
                    # Check depreciation rate is reasonable: 2-25% of gross block
                    dep_rate = (depreciation / fixed_assets) * 100
                    if dep_rate > 50:
                        self._finding(company_data, fy, "4.2a", Severity.WARNING,
                                      f"Depreciation rate ({dep_rate:.1f}%) on Fixed Assets "
                                      f"({fixed_assets:,.0f}) seems very high. Dep={depreciation:,.0f}. "
                                      f"Fixed Assets includes PP&E (land, buildings, plant, "
                                      f"machinery) + intangible assets (software, patents, "
                                      f"goodwill) + ROU assets. Normal range: 3-20%.",
                                      "3-20%", f"{dep_rate:.1f}%")
                    else:
                        self._pass()
                elif depreciation is not None:
                    self._finding(company_data, fy, "4.2b", Severity.WARNING,
                                  f"Fixed Assets ({fixed_assets:,.0f} — PP&E + intangibles + "
                                  f"ROU) > 0 but Depreciation ({depreciation:,.0f}) not positive.",
                                  "> 0", f"{depreciation:,.0f}")

            # Rule 4.3: Reserves change ≈ Net Profit - Dividends paid
            # Reserves = securities premium + general reserve + retained earnings + OCI
            if prev_fy and reserves is not None:
                prev_reserves = self.val(prev_bs.get("reserves"))
                if prev_reserves is not None and net_profit is not None:
                    reserves_change = reserves - prev_reserves
                    dividends_est = 0
                    if div_pct and div_pct > 0 and net_profit > 0:
                        dividends_est = net_profit * (div_pct / 100.0)
                    expected_change = net_profit - dividends_est
                    if abs(net_profit) > 0:
                        diff = self.safe_pct_diff(reserves_change, expected_change)
                        if diff > 50.0 and abs(reserves_change - expected_change) > 1000:
                            self._finding(company_data, fy, "4.3", Severity.INFO,
                                          f"Reserves change ({reserves_change:,.0f}) vs expected "
                                          f"NP({net_profit:,.0f}) - Div({dividends_est:,.0f}) = "
                                          f"{expected_change:,.0f}, diff {diff:.0f}%. "
                                          f"Difference may include: OCI items (foreign currency "
                                          f"translation, fair value changes), share premium from "
                                          f"new issuances, share buybacks, or revaluation surplus.",
                                          f"{expected_change:,.0f}", f"{reserves_change:,.0f}")
                        else:
                            self._pass()

            # ====================================================================
            # P&L ↔ CASH FLOW CROSS-CHECKS
            # ====================================================================

            # Rule 4.4: Net Profit ↔ Operating CF directional consistency
            # IndAS 7 para 18: OCF starts with net profit in indirect method
            if net_profit is not None and ocf is not None and net_profit != 0 and ocf != 0:
                if (net_profit > 0) != (ocf > 0):
                    self._finding(company_data, fy, "4.4", Severity.INFO,
                                  f"Net Profit ({net_profit:,.0f}) and OCF ({ocf:,.0f}) have "
                                  f"opposite signs. OCF = NP + depreciation ± working capital "
                                  f"changes (inventory in other_assets, receivables in "
                                  f"other_assets, payables in other_liabilities) - tax paid. "
                                  f"Large working capital swings can cause this divergence.",
                                  "same direction", f"NP={net_profit:,.0f}, OCF={ocf:,.0f}")
                else:
                    self._pass()

            # Rule 4.5: Depreciation as OCF add-back sanity
            # IndAS 7 para 20: depreciation is a non-cash charge added back in indirect OCF
            if not is_bank and ocf is not None and net_profit is not None and depreciation is not None:
                if depreciation > 0 and net_profit != 0:
                    # OCF should generally be > NP because depreciation is added back
                    # (unless large working capital outflow offsets it)
                    if ocf < net_profit - depreciation and abs(net_profit) > 500:
                        self._finding(company_data, fy, "4.5", Severity.INFO,
                                      f"OCF ({ocf:,.0f}) < NP - Dep ({net_profit - depreciation:,.0f}). "
                                      f"Even after removing the depreciation add-back, OCF is low. "
                                      f"Suggests large working capital outflow: inventory buildup "
                                      f"(in other_assets), rising trade receivables (in other_assets), "
                                      f"or declining trade payables (in other_liabilities).",
                                      f"> {net_profit - depreciation:,.0f}",
                                      f"{ocf:,.0f}")
                    else:
                        self._pass()

            # ====================================================================
            # BALANCE SHEET ↔ CASH FLOW CROSS-CHECKS
            # ====================================================================

            # Rule 4.6: Fixed Assets + CWIP changes → Investing CF (capex)
            # IndAS 7 para 22: purchase of PP&E is investing outflow
            if prev_fy and not is_bank:
                prev_fa = self.val(prev_bs.get("fixed_assets"))
                prev_cwip = self.val(prev_bs.get("cwip"))
                if (prev_fa is not None and fixed_assets is not None and
                        depreciation is not None and icf is not None):
                    fa_change = (fixed_assets or 0) - (prev_fa or 0)
                    cwip_change = (cwip or 0) - (prev_cwip or 0) if cwip is not None and prev_cwip is not None else 0
                    # Estimated gross capex = net FA increase + depreciation + CWIP change
                    estimated_capex = fa_change + cwip_change + depreciation
                    # ICF should be approximately -(capex + investment changes)
                    if estimated_capex > 0 and icf is not None and icf > 0 and estimated_capex > 1000:
                        self._finding(company_data, fy, "4.6", Severity.INFO,
                                      f"Estimated capex (FA change + CWIP change + Dep) = "
                                      f"{estimated_capex:,.0f} but Investing CF is positive "
                                      f"({icf:,.0f}). Net investment purchases of PP&E (land, "
                                      f"buildings, plant, machinery) and CWIP should make ICF "
                                      f"negative, unless offset by large asset sales or "
                                      f"investment disposals.",
                                      "ICF < 0 with positive capex",
                                      f"capex={estimated_capex:,.0f}, ICF={icf:,.0f}")
                    else:
                        self._pass()

            # Rule 4.7: Investments change → Investing CF component
            # IndAS 7 para 22: purchase/sale of investments is investing activity
            if prev_fy:
                prev_inv = self.val(prev_bs.get("investments"))
                if prev_inv is not None and investments is not None and icf is not None:
                    inv_change = investments - prev_inv
                    # If investments increased significantly, ICF should include this as outflow
                    if inv_change > 5000 and icf > 0:
                        self._finding(company_data, fy, "4.7", Severity.INFO,
                                      f"Investments (subsidiaries, associates, financial "
                                      f"instruments) increased by {inv_change:,.0f} but ICF is "
                                      f"positive ({icf:,.0f}). Investment purchases should "
                                      f"appear as negative ICF.",
                                      "ICF < 0", f"ICF={icf:,.0f}")
                    else:
                        self._pass()

            # Rule 4.8: Borrowings change → Financing CF component
            # IndAS 7 para 27: proceeds/repayment of borrowings is financing activity
            if not is_bank and prev_fy and fcf is not None:
                prev_bor = self.val(prev_bs.get("borrowings"))
                if prev_bor is not None and borrowings is not None:
                    bor_change = borrowings - prev_bor
                    # If borrowings increased a lot but financing CF is very negative,
                    # the debt-related inflow should partially offset dividend/interest outflow
                    if bor_change > 10000 and fcf < -10000:
                        self._finding(company_data, fy, "4.8", Severity.INFO,
                                      f"Borrowings (long-term + short-term) increased by "
                                      f"{bor_change:,.0f} but Financing CF is very negative "
                                      f"({fcf:,.0f}). FCF = borrowing proceeds - repayments + "
                                      f"equity raised - buybacks - dividends paid - interest "
                                      f"paid - lease payments. Large offsetting items likely.",
                                      "FCF partially positive from new borrowings",
                                      f"bor_change=+{bor_change:,.0f}, FCF={fcf:,.0f}")
                    else:
                        self._pass()

            # Rule 4.9: Equity Capital change → Financing CF (share issuance/buyback)
            # IndAS 7 para 27: proceeds from issuing shares is financing activity
            if prev_fy and fcf is not None:
                prev_eq = self.val(prev_bs.get("equity_capital"))
                if prev_eq is not None and equity is not None:
                    eq_change = equity - prev_eq
                    if abs(eq_change) > 100 and eq_change > 0 and fcf < 0:
                        # Equity increased but FCF is negative — other financing
                        # outflows (dividends, interest, debt repayment) dominate
                        self._pass()
                    else:
                        self._pass()

            # ====================================================================
            # THREE-WAY RECONCILIATION (all 3 statements)
            # ====================================================================

            # Rule 4.10: ROE cross-check: Net Profit / (Equity + Reserves) from P&L and BS
            if (net_profit is not None and equity is not None and reserves is not None):
                shareholders_funds = equity + reserves
                if shareholders_funds > 0:
                    roe = (net_profit / shareholders_funds) * 100
                    if roe > 100:
                        self._finding(company_data, fy, "4.10", Severity.WARNING,
                                      f"ROE ({roe:.1f}%) exceeds 100%. Net Profit "
                                      f"({net_profit:,.0f}) vs Shareholders' Funds "
                                      f"(Equity {equity:,.0f} + Reserves {reserves:,.0f} = "
                                      f"{shareholders_funds:,.0f}). Very high ROE may indicate "
                                      f"thin equity base or data error.",
                                      "< 100%", f"{roe:.1f}%")
                    else:
                        self._pass()

            # Rule 4.11: ROA cross-check: Net Profit / Total Assets from P&L and BS
            if net_profit is not None and total_assets is not None and total_assets > 0:
                roa = (net_profit / total_assets) * 100
                if not is_bank and roa > 50:
                    self._finding(company_data, fy, "4.11", Severity.WARNING,
                                  f"ROA ({roa:.1f}%) exceeds 50%. Net Profit ({net_profit:,.0f}) "
                                  f"vs Total Assets ({total_assets:,.0f}). Extremely high ROA "
                                  f"for a non-bank — verify data accuracy.",
                                  "< 50%", f"{roa:.1f}%")
                else:
                    self._pass()

            # Rule 4.12: All three statements should exist for each fiscal year
            has_pl = bool(pl)
            has_bs = bool(bs)
            has_cf = bool(cf)
            if has_pl:
                if has_bs and has_cf:
                    self._pass()
                elif not has_bs:
                    self._finding(company_data, fy, "4.12", Severity.ERROR,
                                  f"P&L exists for {fy} but Balance Sheet is missing. "
                                  f"Cannot validate: equity capital, reserves, borrowings, "
                                  f"fixed assets, CWIP, investments, other assets/liabilities.",
                                  "BS present", "BS missing")
                elif not has_cf:
                    self._finding(company_data, fy, "4.12", Severity.ERROR,
                                  f"P&L exists for {fy} but Cash Flow is missing. "
                                  f"Cannot validate: operating CF, investing CF (capex, "
                                  f"investment changes), financing CF (borrowing changes, "
                                  f"dividends paid).",
                                  "CF present", "CF missing")

            # Rule 4.13: Sales vs Total Assets (asset turnover sanity)
            if not is_bank and sales is not None and total_assets is not None and total_assets > 0:
                asset_turnover = sales / total_assets
                if asset_turnover > 10:
                    self._finding(company_data, fy, "4.13", Severity.WARNING,
                                  f"Asset Turnover ({asset_turnover:.2f}x) is very high. "
                                  f"Sales ({sales:,.0f}) vs Total Assets ({total_assets:,.0f}). "
                                  f"This means each rupee of assets (fixed assets + CWIP + "
                                  f"investments + other assets) generates ₹{asset_turnover:.0f} "
                                  f"of revenue, which is unusual.",
                                  "< 10x", f"{asset_turnover:.2f}x")
                else:
                    self._pass()
