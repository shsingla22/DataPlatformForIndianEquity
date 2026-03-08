"""Agent 2: Balance Sheet Validator.

Validates that Balance Sheet follows the fundamental accounting equation
and IndAS norms. Performs detailed validation of all stored fields and
their sub-component relationships per Indian Accounting Standards.

Database fields validated (per IndAS 1 / Schedule III of Companies Act 2013):

EQUITY & LIABILITIES SIDE:
  equity_capital   — Paid-up share capital (IndAS 1 para 54(r))
                     Contains: face value × number of shares outstanding
                     Sub-items: equity shares, preference shares
  reserves         — Retained earnings + other reserves (IndAS 1 para 54(r))
                     Contains: securities premium, general reserve,
                     retained earnings, revaluation surplus, OCI reserves
  borrowings       — Total debt obligations (IndAS 23, IndAS 109)
                     Contains: long-term borrowings (debentures, term loans,
                     bonds, ECBs) + short-term borrowings (working capital
                     loans, commercial paper, current maturities of LT debt)
                     NULL for banks (deposits are in other_liabilities)
  other_liabilities — All non-debt liabilities (IndAS 37, IndAS 19)
                     Contains: trade payables (accounts payable), provisions
                     (employee benefits, warranties, tax provisions),
                     deferred tax liabilities, current tax liabilities,
                     advances from customers, other current liabilities
                     For banks: includes customer deposits, inter-bank
                     borrowings, RBI borrowings
  total_liabilities — Sum of equity + all liabilities (= total_assets)

ASSETS SIDE:
  fixed_assets     — Property, Plant & Equipment net of depreciation (IndAS 16)
                     Contains: land, buildings, plant & machinery, furniture,
                     vehicles, office equipment, intangible assets (IndAS 38:
                     software, patents, goodwill), right-of-use assets (IndAS 116)
  cwip             — Capital Work in Progress (IndAS 16 para 17)
                     Contains: assets under construction/installation not yet
                     ready for use; should eventually move to fixed_assets
  investments      — Financial investments (IndAS 109, IndAS 27, IndAS 28)
                     Contains: investments in subsidiaries/associates/JVs,
                     quoted & unquoted equity/debt instruments, mutual funds,
                     government securities, fixed deposits > 12 months
                     For banks: large portion of total assets (SLR/treasury)
  other_assets     — Current & other non-current assets (IndAS 1)
                     Contains: inventory (IndAS 2: raw materials, WIP,
                     finished goods), trade receivables (accounts receivable),
                     cash & bank balances (IndAS 7), loans & advances,
                     prepaid expenses, tax assets (MAT credit, advance tax),
                     other current assets
  total_assets     — Sum of all assets (= total_liabilities)
"""

from typing import Dict, Any, Optional
from qa_agents.base_agent import BaseAgent
from qa_agents.models import Severity


class BalanceSheetAgent(BaseAgent):
    name = "Balance Sheet"

    def validate_company(self, company_data):
        is_bank = self.is_bank(company_data)
        pl_by_year = {pl["fiscal_year"]: pl for pl in company_data.get("profit_loss", [])}
        cf_by_year = {cf["fiscal_year"]: cf for cf in company_data.get("cash_flow", [])}
        bs_list = sorted(company_data.get("balance_sheet", []),
                         key=lambda x: x.get("fiscal_year", ""))
        bs_by_year = {bs["fiscal_year"]: bs for bs in bs_list}

        for bs in bs_list:
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

            pl = pl_by_year.get(fy, {})
            cf = cf_by_year.get(fy, {})

            # ====================================================================
            # FUNDAMENTAL ACCOUNTING EQUATION (IndAS 1)
            # ====================================================================

            # Rule 2.1: Total Assets ≈ Total Liabilities (±1%)
            # IndAS 1 para 54: Assets = Equity + Liabilities
            if total_assets is not None and total_liab is not None and total_assets != 0:
                diff = self.safe_pct_diff(total_assets, total_liab)
                if diff > 1.0:
                    self._finding(company_data, fy, "2.1", Severity.ERROR,
                                  f"Total Assets ({total_assets:,.0f}) != Total Liabilities ({total_liab:,.0f}), "
                                  f"diff {diff:.2f}%. Fundamental accounting equation violated.",
                                  f"{total_liab:,.0f}", f"{total_assets:,.0f}")
                else:
                    self._pass()

            # ====================================================================
            # LIABILITIES SIDE — COMPONENT VALIDATION
            # ====================================================================

            # Rule 2.2: Total Liabilities ≈ Equity Capital + Reserves + Borrowings + Other Liabilities (±1%)
            # Schedule III: Total = Shareholders' Funds + Non-Current Liabilities + Current Liabilities
            if total_liab is not None and total_liab != 0:
                eq = equity or 0
                res = reserves or 0
                bor = borrowings or 0  # NULL for banks (deposits in other_liab)
                ol = other_liab or 0
                computed = eq + res + bor + ol
                diff = self.safe_pct_diff(computed, total_liab)
                if diff > 1.0:
                    self._finding(company_data, fy, "2.2", Severity.WARNING,
                                  f"Equity({eq:,.0f}) + Reserves({res:,.0f}) + Borrowings({bor:,.0f}) + "
                                  f"OtherLiab({ol:,.0f}) = {computed:,.0f} != Total Liabilities({total_liab:,.0f}), "
                                  f"diff {diff:.2f}%. Check for deposits/sub-debt not classified.",
                                  f"{total_liab:,.0f}", f"{computed:,.0f}")
                else:
                    self._pass()

            # Rule 2.3: Equity Capital (paid-up share capital) should be positive and stable
            # IndAS 1 para 54(r): share capital must exist
            if equity is not None:
                if equity > 0:
                    self._pass()
                else:
                    self._finding(company_data, fy, "2.3", Severity.WARNING,
                                  f"Equity Capital ({equity:,.0f}) is not positive. "
                                  f"All listed companies must have paid-up share capital.",
                                  "> 0", f"{equity:,.0f}")

            # Rule 2.4: Equity Capital should be stable YoY (changes only via rights issue/buyback/split)
            # Large changes indicate data error or major corporate action
            prev_years = [y for y in sorted(bs_by_year.keys()) if y < fy]
            if prev_years and equity is not None:
                prev_fy = prev_years[-1]
                prev_equity = self.val(bs_by_year[prev_fy].get("equity_capital"))
                if prev_equity is not None and prev_equity > 0:
                    change_pct = self.safe_pct_diff(equity, prev_equity)
                    if change_pct > 50:
                        self._finding(company_data, fy, "2.4", Severity.WARNING,
                                      f"Equity Capital changed {change_pct:.0f}% YoY "
                                      f"({prev_equity:,.0f} → {equity:,.0f}). "
                                      f"Possible stock split, rights issue, or data error.",
                                      f"~{prev_equity:,.0f}", f"{equity:,.0f}")
                    else:
                        self._pass()

            # Rule 2.5: Reserves should grow approximately by Net Profit minus Dividends
            # IndAS 1, Schedule III Part I: Reserves include retained earnings
            if prev_years and reserves is not None:
                prev_fy = prev_years[-1]
                prev_reserves = self.val(bs_by_year[prev_fy].get("reserves"))
                net_profit = self.val(pl.get("net_profit"))
                div_pct = self.val(pl.get("dividend_payout_percent"))
                if prev_reserves is not None and net_profit is not None:
                    dividends_est = abs(net_profit) * (div_pct / 100.0) if div_pct and div_pct > 0 else 0
                    expected_reserves = prev_reserves + net_profit - dividends_est
                    actual_change = reserves - prev_reserves
                    expected_change = net_profit - dividends_est
                    if abs(expected_change) > 100:  # Only check if material
                        diff = self.safe_pct_diff(actual_change, expected_change)
                        if diff > 50 and abs(actual_change - expected_change) > 1000:
                            self._finding(company_data, fy, "2.5", Severity.INFO,
                                          f"Reserves change ({actual_change:,.0f}) vs expected NP-Div "
                                          f"({expected_change:,.0f}), diff {diff:.0f}%. "
                                          f"Difference may include OCI, share premium, "
                                          f"revaluation surplus, or buybacks.",
                                          f"{expected_change:,.0f}", f"{actual_change:,.0f}")
                        else:
                            self._pass()

            # Rule 2.6: Borrowings should relate to Interest expense in P&L
            # IndAS 23: Borrowing costs must be recognized as expense
            if not is_bank and borrowings is not None and borrowings > 0:
                interest = self.val(pl.get("interest"))
                if interest is not None and interest > 0:
                    # Implied interest rate = interest / borrowings
                    implied_rate = (interest / borrowings) * 100
                    if implied_rate > 25:
                        self._finding(company_data, fy, "2.6a", Severity.WARNING,
                                      f"Implied interest rate ({implied_rate:.1f}%) on borrowings "
                                      f"({borrowings:,.0f}) seems high. Interest={interest:,.0f}. "
                                      f"Expected 5-15% for Indian corporates.",
                                      "5-15%", f"{implied_rate:.1f}%")
                    else:
                        self._pass()
                elif interest is not None:
                    self._finding(company_data, fy, "2.6b", Severity.WARNING,
                                  f"Borrowings ({borrowings:,.0f}) > 0 but Interest ({interest:,.0f}) "
                                  f"not positive. Check if interest is capitalized (IndAS 23) "
                                  f"or if borrowings are interest-free.",
                                  "> 0", f"{interest:,.0f}")

            # ====================================================================
            # ASSETS SIDE — COMPONENT VALIDATION
            # ====================================================================

            # Rule 2.7: Total Assets ≈ Fixed Assets + CWIP + Investments + Other Assets (±1%)
            # Schedule III Part I: total of non-current + current assets
            if total_assets is not None and total_assets != 0:
                fa = fixed_assets or 0
                cw = cwip or 0
                inv = investments or 0
                oa = other_assets or 0
                computed = fa + cw + inv + oa
                diff = self.safe_pct_diff(computed, total_assets)
                if diff > 1.0:
                    self._finding(company_data, fy, "2.7", Severity.WARNING,
                                  f"FixedAssets({fa:,.0f}) + CWIP({cw:,.0f}) + "
                                  f"Investments({inv:,.0f}) + OtherAssets({oa:,.0f}) = "
                                  f"{computed:,.0f} != Total Assets({total_assets:,.0f}), "
                                  f"diff {diff:.2f}%.",
                                  f"{total_assets:,.0f}", f"{computed:,.0f}")
                else:
                    self._pass()

            # Rule 2.8: Fixed Assets (PP&E + Intangibles) should decrease by depreciation if no capex
            # IndAS 16: Carrying amount = cost - accumulated depreciation - impairment
            if prev_years and fixed_assets is not None:
                prev_fy = prev_years[-1]
                prev_fa = self.val(bs_by_year[prev_fy].get("fixed_assets"))
                depreciation = self.val(pl.get("depreciation"))
                if prev_fa is not None and depreciation is not None and prev_fa > 0:
                    fa_change = fixed_assets - prev_fa
                    # If FA increased, capex > depreciation (healthy growing company)
                    # If FA decreased by more than depreciation, possible impairment or disposal
                    if fa_change < -depreciation * 1.5 and abs(fa_change + depreciation) > 500:
                        self._finding(company_data, fy, "2.8", Severity.WARNING,
                                      f"Fixed Assets dropped by {abs(fa_change):,.0f} but Depreciation "
                                      f"was only {depreciation:,.0f}. Possible asset disposal, "
                                      f"impairment (IndAS 36), or data error.",
                                      f"decrease ≤ {depreciation:,.0f}", f"decrease = {abs(fa_change):,.0f}")
                    else:
                        self._pass()

            # Rule 2.9: CWIP should eventually convert to Fixed Assets
            # IndAS 16 para 17: asset recognized when ready for intended use
            if cwip is not None and total_assets is not None and total_assets > 0:
                cwip_ratio = (cwip / total_assets) * 100
                if cwip_ratio > 30:
                    self._finding(company_data, fy, "2.9", Severity.WARNING,
                                  f"CWIP ({cwip:,.0f}) is {cwip_ratio:.1f}% of Total Assets. "
                                  f"Unusually high — may indicate stalled projects or "
                                  f"delayed capitalization.",
                                  "< 30% of total assets", f"{cwip_ratio:.1f}%")
                else:
                    self._pass()

            # Rule 2.10: Investments proportion check
            # IndAS 109/27/28: financial instruments + subsidiaries/associates
            # Banks typically have 30-50% of assets as investments (SLR requirement)
            if investments is not None and total_assets is not None and total_assets > 0:
                inv_ratio = (investments / total_assets) * 100
                if is_bank:
                    if inv_ratio < 15:
                        self._finding(company_data, fy, "2.10", Severity.WARNING,
                                      f"Bank investment ratio ({inv_ratio:.1f}%) seems low. "
                                      f"Banks typically hold 25-50% as investments "
                                      f"(SLR/treasury). Investments={investments:,.0f}.",
                                      "25-50%", f"{inv_ratio:.1f}%")
                    else:
                        self._pass()
                else:
                    if inv_ratio > 80:
                        self._finding(company_data, fy, "2.10", Severity.INFO,
                                      f"Investment ratio ({inv_ratio:.1f}%) is very high for "
                                      f"a non-bank. Likely a holding/investment company. "
                                      f"Investments={investments:,.0f}.",
                                      "< 80%", f"{inv_ratio:.1f}%")
                    else:
                        self._pass()

            # Rule 2.11: Other Assets (current assets) should include working capital
            # IndAS 2 (Inventory), IndAS 109 (Trade Receivables), IndAS 7 (Cash)
            # Other Assets = Inventory + Trade Receivables + Cash + Loans + Prepaid + Tax assets
            if not is_bank and other_assets is not None and total_assets is not None and total_assets > 0:
                oa_ratio = (other_assets / total_assets) * 100
                sales = self.val(pl.get("sales"))
                if sales is not None and sales > 0:
                    # Other assets / sales = rough working capital cycle indicator
                    oa_to_sales = (other_assets / sales) * 365  # days
                    if oa_to_sales > 365:
                        self._finding(company_data, fy, "2.11", Severity.INFO,
                                      f"Other Assets ({other_assets:,.0f}) represent "
                                      f"{oa_to_sales:.0f} days of sales. High ratio may indicate "
                                      f"slow inventory turnover, high receivables (trade receivables), "
                                      f"or large cash balances in other_assets.",
                                      "< 365 days", f"{oa_to_sales:.0f} days")
                    else:
                        self._pass()

            # Rule 2.12: Other Liabilities (trade payables + provisions) reasonableness
            # IndAS 37 (Provisions), IndAS 19 (Employee Benefits)
            if not is_bank and other_liab is not None and total_liab is not None and total_liab > 0:
                ol_ratio = (other_liab / total_liab) * 100
                expenses = self.val(pl.get("expenses"))
                if expenses is not None and expenses > 0:
                    # Other liab / expenses = rough payable days
                    payable_days = (other_liab / expenses) * 365
                    if payable_days > 365:
                        self._finding(company_data, fy, "2.12", Severity.INFO,
                                      f"Other Liabilities ({other_liab:,.0f}) represent "
                                      f"{payable_days:.0f} days of expenses. High ratio may "
                                      f"indicate large trade payables, provisions, deferred "
                                      f"tax liabilities, or advance from customers.",
                                      "< 365 days", f"{payable_days:.0f} days")
                    else:
                        self._pass()

            # Rule 2.13: Total Assets must be positive
            if total_assets is not None:
                if total_assets > 0:
                    self._pass()
                else:
                    self._finding(company_data, fy, "2.13", Severity.ERROR,
                                  f"Total Assets ({total_assets:,.0f}) is not positive. "
                                  f"Every listed company must have positive total assets.",
                                  "> 0", f"{total_assets:,.0f}")

            # ====================================================================
            # DERIVED RATIOS & FINANCIAL HEALTH (Indian corporate norms)
            # ====================================================================

            # Rule 2.14: Debt-to-Equity Ratio
            # Borrowings / (Equity Capital + Reserves) — key solvency metric
            if not is_bank and borrowings is not None and equity is not None and reserves is not None:
                shareholders_funds = equity + reserves
                if shareholders_funds > 0 and borrowings >= 0:
                    de_ratio = borrowings / shareholders_funds
                    if de_ratio > 5.0:
                        self._finding(company_data, fy, "2.14", Severity.WARNING,
                                      f"D/E ratio ({de_ratio:.2f}) is very high. "
                                      f"Borrowings={borrowings:,.0f}, Equity+Reserves="
                                      f"{shareholders_funds:,.0f}. Indian corporates typically "
                                      f"maintain D/E < 2.0 (manufacturing) or < 3.0 (infra).",
                                      "< 5.0", f"{de_ratio:.2f}")
                    else:
                        self._pass()
                elif shareholders_funds <= 0:
                    self._finding(company_data, fy, "2.14", Severity.ERROR,
                                  f"Negative shareholders' funds ({shareholders_funds:,.0f}). "
                                  f"Equity({equity:,.0f}) + Reserves({reserves:,.0f}) ≤ 0. "
                                  f"Company may be technically insolvent per Companies Act 2013.",
                                  "> 0", f"{shareholders_funds:,.0f}")

            # Rule 2.15: Net Worth to Total Assets ratio
            # Shareholders' Funds / Total Assets — leverage indicator
            if equity is not None and reserves is not None and total_assets is not None and total_assets > 0:
                net_worth = equity + reserves
                nw_ratio = (net_worth / total_assets) * 100
                if not is_bank and nw_ratio < 10:
                    self._finding(company_data, fy, "2.15", Severity.WARNING,
                                  f"Net Worth ({net_worth:,.0f}) is only {nw_ratio:.1f}% of "
                                  f"Total Assets ({total_assets:,.0f}). Company is highly "
                                  f"leveraged with thin equity cushion.",
                                  "> 10%", f"{nw_ratio:.1f}%")
                else:
                    self._pass()

            # Rule 2.16: Investments change should relate to Investing Cash Flow
            # IndAS 7: purchase/sale of investments appears in investing activities
            if prev_years:
                prev_fy = prev_years[-1]
                prev_inv = self.val(bs_by_year[prev_fy].get("investments"))
                icf = self.val(cf.get("cash_from_investing"))
                if prev_inv is not None and investments is not None and icf is not None:
                    inv_change = investments - prev_inv
                    # If investments increased significantly but ICF is positive,
                    # there's an inconsistency
                    if inv_change > 0 and icf > 0 and inv_change > 1000:
                        self._finding(company_data, fy, "2.16", Severity.INFO,
                                      f"Investments increased by {inv_change:,.0f} but Investing "
                                      f"CF is positive ({icf:,.0f}). Investment purchases should "
                                      f"appear as negative investing CF (includes fixed asset "
                                      f"purchases and investment purchases).",
                                      "ICF < 0 when investments increase",
                                      f"inv change=+{inv_change:,.0f}, ICF=+{icf:,.0f}")
                    else:
                        self._pass()

            # Rule 2.17: Borrowings change should relate to Financing Cash Flow
            # IndAS 7: proceeds/repayment of borrowings in financing activities
            if not is_bank and prev_years and borrowings is not None:
                prev_fy = prev_years[-1]
                prev_bor = self.val(bs_by_year[prev_fy].get("borrowings"))
                fcf = self.val(cf.get("cash_from_financing"))
                if prev_bor is not None and fcf is not None:
                    bor_change = borrowings - prev_bor
                    # If borrowings increased substantially but financing CF is very negative,
                    # something doesn't add up (financing CF includes dividends + equity too)
                    if bor_change > 5000 and fcf < -5000:
                        self._finding(company_data, fy, "2.17", Severity.INFO,
                                      f"Borrowings increased by {bor_change:,.0f} but Financing "
                                      f"CF is negative ({fcf:,.0f}). Financing CF includes "
                                      f"proceeds/repayment of long-term & short-term borrowings, "
                                      f"dividends paid, and equity raised.",
                                      "FCF direction consistent with borrowing change",
                                      f"bor change=+{bor_change:,.0f}, FCF={fcf:,.0f}")
                    else:
                        self._pass()
