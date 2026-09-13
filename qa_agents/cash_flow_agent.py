"""Agent 3: Cash Flow Integrity Validator.

Validates Cash Flow statement internal consistency per IndAS 7 (Statement
of Cash Flows) and cross-references with Balance Sheet and P&L changes.

Database fields validated and their sub-components per IndAS 7:

OPERATING ACTIVITIES (cash_from_operating) — IndAS 7 para 14-20:
  The indirect method starts with Net Profit and adjusts for:
  Sub-items (not stored individually but implied):
    + Depreciation & amortization (add-back, non-cash)
    + Finance costs / interest expense (reclassified to financing)
    - Interest income (reclassified to investing)
    + Loss on sale of assets / - gain on sale of assets
    + Impairment losses (IndAS 36)
    ± Changes in working capital:
        - Increase in trade receivables (part of other_assets)
        - Increase in inventories (part of other_assets)
        + Increase in trade payables (part of other_liabilities)
        ± Other working capital changes
    - Income tax paid
  Approximation: OCF ≈ Net Profit + Depreciation ± Working Capital changes

INVESTING ACTIVITIES (cash_from_investing) — IndAS 7 para 21-25:
  Sub-items (not stored individually but implied):
    - Purchase of fixed assets / PP&E (capital expenditure / capex)
    + Sale proceeds from fixed assets
    - Purchase of investments (subsidiaries, associates, financial instruments)
    + Sale proceeds from investments
    - Acquisition of businesses
    + Proceeds from disposal of businesses
    - Loans and advances given
    + Loans and advances recovered
    - Purchase of intangible assets
    + Interest received (if classified as investing)
    + Dividends received (if classified as investing)
  Approximation: ICF ≈ -(change in fixed_assets + change in cwip +
                          change in investments + depreciation)

FINANCING ACTIVITIES (cash_from_financing) — IndAS 7 para 26-29:
  Sub-items (not stored individually but implied):
    + Proceeds from long-term borrowings (term loans, debentures, bonds, ECBs)
    - Repayment of long-term borrowings
    + Proceeds from short-term borrowings (working capital loans, CP)
    - Repayment of short-term borrowings
    + Proceeds from issue of equity shares / share premium
    - Buyback of shares
    - Dividends paid to shareholders
    - Dividend distribution tax (abolished from April 2020)
    - Interest paid (if classified as financing per IndAS 7 para 33)
    + Proceeds from issue of preference shares
    - Lease liability payments (IndAS 116)
  Approximation: FCF ≈ change in borrowings + change in equity_capital
                        - dividends paid - interest paid

NET CASH FLOW (net_cash_flow) — IndAS 7 para 45:
  = cash_from_operating + cash_from_investing + cash_from_financing
  Should approximately equal change in cash & cash equivalents
  (part of other_assets on Balance Sheet)
"""

from qa_agents.base_agent import BaseAgent
from qa_agents.models import Severity


class CashFlowAgent(BaseAgent):
    name = "Cash Flow"

    def validate_company(self, company_data):
        is_bank = self.is_bank(company_data)
        pl_by_year = {pl["fiscal_year"]: pl for pl in company_data.get("profit_loss", [])}
        bs_by_year = {bs["fiscal_year"]: bs for bs in company_data.get("balance_sheet", [])}
        bs_list = sorted(company_data.get("balance_sheet", []),
                         key=lambda x: x.get("fiscal_year", ""))
        cf_list = sorted(company_data.get("cash_flow", []),
                         key=lambda x: x.get("fiscal_year", ""))

        consecutive_negative_ocf = 0

        for cf in cf_list:
            fy = cf.get("fiscal_year", "Unknown")
            ocf = self.val(cf.get("cash_from_operating"))
            icf = self.val(cf.get("cash_from_investing"))
            fcf_val = self.val(cf.get("cash_from_financing"))
            ncf = self.val(cf.get("net_cash_flow"))

            pl = pl_by_year.get(fy, {})
            bs = bs_by_year.get(fy, {})

            # Find previous year BS for delta calculations
            prev_bs = None
            sorted_years = sorted(bs_by_year.keys())
            curr_idx = sorted_years.index(fy) if fy in sorted_years else -1
            if curr_idx > 0:
                prev_bs = bs_by_year[sorted_years[curr_idx - 1]]

            # ====================================================================
            # INTERNAL CONSISTENCY (IndAS 7 para 45)
            # ====================================================================

            # Rule 3.1: Net CF ≈ Operating + Investing + Financing (±5%)
            if all(v is not None for v in [ocf, icf, fcf_val, ncf]):
                expected = ocf + icf + fcf_val
                if abs(expected) > 0:
                    diff = self.safe_pct_diff(ncf, expected)
                    if diff > 5.0:
                        self._finding(company_data, fy, "3.1", Severity.WARNING,
                                      f"Net CF ({ncf:,.0f}) != OCF({ocf:,.0f}) + ICF({icf:,.0f}) + "
                                      f"FCF({fcf_val:,.0f}) = {expected:,.0f}, diff {diff:.1f}%.",
                                      f"{expected:,.0f}", f"{ncf:,.0f}")
                    else:
                        self._pass()
                else:
                    self._pass()

            # ====================================================================
            # OPERATING CASH FLOW VALIDATION (IndAS 7 para 14-20)
            # ====================================================================

            # Rule 3.2: OCF should approximate Net Profit + Depreciation (rough indirect method)
            # IndAS 7 para 18-20: indirect method adjustments
            net_profit = self.val(pl.get("net_profit"))
            depreciation = self.val(pl.get("depreciation"))
            if not is_bank and ocf is not None and net_profit is not None and depreciation is not None:
                # OCF ≈ NP + Dep ± working capital changes ± other adjustments
                np_plus_dep = net_profit + depreciation
                if abs(np_plus_dep) > 0:
                    ratio = ocf / np_plus_dep if np_plus_dep != 0 else 0
                    # OCF should be in same ballpark as NP+Dep (0.3x to 3.0x is reasonable)
                    if abs(np_plus_dep) > 500 and (ratio < 0.1 or ratio > 5.0):
                        self._finding(company_data, fy, "3.2", Severity.WARNING,
                                      f"OCF ({ocf:,.0f}) is {ratio:.2f}x of NP+Dep "
                                      f"({np_plus_dep:,.0f}). Large deviation suggests significant "
                                      f"working capital changes (inventory buildup/drawdown in "
                                      f"other_assets, receivables changes, payable changes in "
                                      f"other_liabilities) or non-cash items.",
                                      f"0.3-3.0x of {np_plus_dep:,.0f}", f"{ratio:.2f}x")
                    else:
                        self._pass()

            # Rule 3.3: Profitable company should have positive OCF (IndAS 7 para 19)
            if net_profit is not None and net_profit > 0 and ocf is not None:
                if ocf < 0:
                    consecutive_negative_ocf += 1
                    if consecutive_negative_ocf >= 2:
                        self._finding(company_data, fy, "3.3", Severity.WARNING,
                                      f"Profitable (NP={net_profit:,.0f}) but negative OCF "
                                      f"({ocf:,.0f}) for 2+ consecutive years. Persistent negative "
                                      f"OCF despite profits may indicate: aggressive revenue "
                                      f"recognition, growing receivables (trade receivables in "
                                      f"other_assets), inventory buildup, or poor cash conversion.",
                                      "> 0", f"{ocf:,.0f}")
                    else:
                        self._pass()
                else:
                    consecutive_negative_ocf = 0
                    self._pass()

            # ====================================================================
            # INVESTING CASH FLOW VALIDATION (IndAS 7 para 21-25)
            # ====================================================================

            # Rule 3.4: ICF should relate to changes in Fixed Assets + CWIP + Investments
            # ICF includes: purchase/sale of PP&E (capex), purchase/sale of investments,
            # acquisition/disposal of subsidiaries, loans given/recovered
            if prev_bs and icf is not None:
                curr_fa = self.val(bs.get("fixed_assets")) or 0
                prev_fa = self.val(prev_bs.get("fixed_assets")) or 0
                curr_cwip = self.val(bs.get("cwip")) or 0
                prev_cwip = self.val(prev_bs.get("cwip")) or 0
                curr_inv = self.val(bs.get("investments")) or 0
                prev_inv = self.val(prev_bs.get("investments")) or 0
                dep = self.val(pl.get("depreciation")) or 0

                # Estimated capex = change in (FA + CWIP) + depreciation
                # (depreciation reduces FA, so actual capex = FA increase + depreciation)
                estimated_capex = (curr_fa - prev_fa) + (curr_cwip - prev_cwip) + dep
                estimated_inv_change = curr_inv - prev_inv
                estimated_icf = -(estimated_capex + estimated_inv_change)

                if abs(estimated_icf) > 500 and abs(icf) > 500:
                    diff = self.safe_pct_diff(icf, estimated_icf)
                    # Allow large tolerance since cash flow statement has many sub-items
                    # not captured in BS summary (loans, interest received, etc.)
                    if diff > 100 and abs(icf - estimated_icf) > 5000:
                        self._finding(company_data, fy, "3.4", Severity.INFO,
                                      f"ICF ({icf:,.0f}) vs estimated from BS changes "
                                      f"({estimated_icf:,.0f}). Estimated capex (PP&E + CWIP "
                                      f"change + depreciation): {estimated_capex:,.0f}. Investment "
                                      f"change: {estimated_inv_change:,.0f}. Difference may include "
                                      f"asset disposals, loans given/recovered, acquisition of "
                                      f"subsidiaries, interest/dividends received.",
                                      f"{estimated_icf:,.0f}", f"{icf:,.0f}")
                    else:
                        self._pass()

            # Rule 3.5: ICF typically negative for growing companies
            # IndAS 7 para 21: capex appears as outflow
            if icf is not None:
                if icf > 0:
                    self._finding(company_data, fy, "3.5", Severity.INFO,
                                  f"Investing CF is positive ({icf:,.0f}). Company is net "
                                  f"disinvesting — selling fixed assets, liquidating investments "
                                  f"(subsidiaries/associates/financial instruments), or recovering "
                                  f"loans. Unusual for a growing company.",
                                  "< 0 (capex outflow)", f"{icf:,.0f}")
                else:
                    self._pass()

            # Rule 3.6: Capex ratio — estimated capex vs depreciation
            # Capex > depreciation means company is investing for growth
            if prev_bs and not is_bank:
                curr_fa = self.val(bs.get("fixed_assets")) or 0
                prev_fa = self.val(prev_bs.get("fixed_assets")) or 0
                curr_cwip = self.val(bs.get("cwip")) or 0
                prev_cwip = self.val(prev_bs.get("cwip")) or 0
                dep = self.val(pl.get("depreciation"))

                if dep is not None and dep > 0:
                    estimated_capex = (curr_fa - prev_fa) + (curr_cwip - prev_cwip) + dep
                    capex_to_dep = estimated_capex / dep if dep > 0 else 0
                    if capex_to_dep < 0.3 and dep > 100:
                        self._finding(company_data, fy, "3.6", Severity.INFO,
                                      f"Estimated capex ({estimated_capex:,.0f}) is only "
                                      f"{capex_to_dep:.1f}x of depreciation ({dep:,.0f}). "
                                      f"Company may be under-investing in PP&E (fixed assets) "
                                      f"and CWIP. Capex < depreciation means asset base is "
                                      f"shrinking.",
                                      "> 0.5x depreciation", f"{capex_to_dep:.1f}x")
                    else:
                        self._pass()

            # ====================================================================
            # FINANCING CASH FLOW VALIDATION (IndAS 7 para 26-29)
            # ====================================================================

            # Rule 3.7: FCF should relate to changes in Borrowings + Equity + Dividends
            # Financing CF includes: proceeds/repayment of long-term & short-term borrowings,
            # issue/buyback of equity, dividends paid, lease payments (IndAS 116)
            if prev_bs and fcf_val is not None and not is_bank:
                curr_bor = self.val(bs.get("borrowings")) or 0
                prev_bor = self.val(prev_bs.get("borrowings")) or 0
                curr_eq = self.val(bs.get("equity_capital")) or 0
                prev_eq = self.val(prev_bs.get("equity_capital")) or 0

                bor_change = curr_bor - prev_bor  # + means new debt raised, - means repaid
                eq_change = curr_eq - prev_eq  # + means new shares issued

                interest = self.val(pl.get("interest")) or 0
                div_pct = self.val(pl.get("dividend_payout_percent")) or 0
                np = self.val(pl.get("net_profit")) or 0
                dividends_est = abs(np) * (div_pct / 100.0) if div_pct > 0 and np > 0 else 0

                # Estimated FCF ≈ borrowing change + equity change - interest paid - dividends paid
                estimated_fcf = bor_change + eq_change - interest - dividends_est

                if abs(estimated_fcf) > 500 and abs(fcf_val) > 500:
                    diff = self.safe_pct_diff(fcf_val, estimated_fcf)
                    if diff > 100 and abs(fcf_val - estimated_fcf) > 5000:
                        self._finding(company_data, fy, "3.7", Severity.INFO,
                                      f"Financing CF ({fcf_val:,.0f}) vs estimated ({estimated_fcf:,.0f}). "
                                      f"Borrowing change (long-term + short-term): {bor_change:,.0f}, "
                                      f"equity change: {eq_change:,.0f}, interest paid: {interest:,.0f}, "
                                      f"estimated dividends paid: {dividends_est:,.0f}. Difference "
                                      f"may include lease payments (IndAS 116), share premium, "
                                      f"buybacks, or preference share transactions.",
                                      f"{estimated_fcf:,.0f}", f"{fcf_val:,.0f}")
                    else:
                        self._pass()

            # Rule 3.8: Large positive financing CF may indicate heavy borrowing
            total_assets_bs = self.val(bs.get("total_assets"))
            if fcf_val is not None and total_assets_bs is not None and total_assets_bs > 0:
                fcf_ratio = (fcf_val / total_assets_bs) * 100
                if fcf_ratio > 20:
                    self._finding(company_data, fy, "3.8", Severity.INFO,
                                  f"Financing CF ({fcf_val:,.0f}) is {fcf_ratio:.1f}% of Total "
                                  f"Assets. Large inflow suggests significant new borrowings "
                                  f"(long-term or short-term) or equity issuance.",
                                  "< 20% of total assets", f"{fcf_ratio:.1f}%")
                else:
                    self._pass()

            # ====================================================================
            # NET CASH FLOW & FREE CASH FLOW (IndAS 7 para 45-47)
            # ====================================================================

            # Rule 3.9: |Net CF| should not exceed Total Assets (sanity check)
            total_assets_val = self.val(bs.get("total_assets"))
            if ncf is not None and total_assets_val is not None and total_assets_val > 0:
                if abs(ncf) > total_assets_val:
                    self._finding(company_data, fy, "3.9", Severity.WARNING,
                                  f"|Net CF| ({abs(ncf):,.0f}) exceeds Total Assets "
                                  f"({total_assets_val:,.0f}). Cash movement larger than entire "
                                  f"balance sheet is highly unusual.",
                                  f"< {total_assets_val:,.0f}", f"{abs(ncf):,.0f}")
                else:
                    self._pass()

            # Rule 3.10: Free Cash Flow = OCF - estimated capex
            # FCF is the cash available for debt repayment, dividends, buybacks
            if not is_bank and ocf is not None and prev_bs:
                curr_fa = self.val(bs.get("fixed_assets")) or 0
                prev_fa = self.val(prev_bs.get("fixed_assets")) or 0
                curr_cwip = self.val(bs.get("cwip")) or 0
                prev_cwip = self.val(prev_bs.get("cwip")) or 0
                dep = self.val(pl.get("depreciation")) or 0

                estimated_capex = (curr_fa - prev_fa) + (curr_cwip - prev_cwip) + dep
                if estimated_capex > 0:
                    free_cash_flow = ocf - estimated_capex
                    sales = self.val(pl.get("sales"))
                    if sales and sales > 0:
                        fcf_margin = (free_cash_flow / sales) * 100
                        if fcf_margin < -20 and abs(free_cash_flow) > 1000:
                            self._finding(company_data, fy, "3.10", Severity.WARNING,
                                          f"Free Cash Flow ({free_cash_flow:,.0f}) is deeply "
                                          f"negative at {fcf_margin:.1f}% of sales. OCF={ocf:,.0f}, "
                                          f"estimated capex (PP&E + CWIP change + depreciation)="
                                          f"{estimated_capex:,.0f}. Company is spending far more "
                                          f"on fixed assets than generating from operations.",
                                          "> -20% of sales", f"{fcf_margin:.1f}%")
                        else:
                            self._pass()

            # Rule 3.11: Cash flow from operations quality — OCF vs Net Profit
            # High-quality earnings should convert to cash
            if not is_bank and ocf is not None and net_profit is not None and net_profit > 0:
                cash_conversion = (ocf / net_profit) * 100
                if cash_conversion < 50 and net_profit > 500:
                    self._finding(company_data, fy, "3.11", Severity.INFO,
                                  f"Cash conversion ratio ({cash_conversion:.0f}%) is below 50%. "
                                  f"OCF={ocf:,.0f} vs Net Profit={net_profit:,.0f}. Low conversion "
                                  f"may indicate: rising trade receivables, inventory buildup, "
                                  f"revenue recognition timing, or large non-cash income items.",
                                  "> 50%", f"{cash_conversion:.0f}%")
                else:
                    self._pass()
