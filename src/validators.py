"""Data validation module for financial data integrity checks."""

import logging
from src.models import get_db_connection, get_all_companies
from src.config import MIN_MARKET_CAP_CRORES

logger = logging.getLogger(__name__)


class ValidationError:
    """Represents a single validation error."""

    def __init__(self, company_id, symbol, check_name, message, severity="warning"):
        self.company_id = company_id
        self.symbol = symbol
        self.check_name = check_name
        self.message = message
        self.severity = severity

    def __repr__(self):
        return f"[{self.severity.upper()}] {self.symbol}: {self.check_name} - {self.message}"


class DataValidator:
    """Validates financial data for completeness and consistency."""

    def __init__(self, db_path=None):
        self.db_path = db_path
        self.errors = []

    def validate_all(self):
        """Run all validation checks."""
        self.errors = []

        with get_db_connection(self.db_path) as conn:
            companies = get_all_companies(conn, MIN_MARKET_CAP_CRORES)

            for company in companies:
                company_id = company["id"]
                symbol = company.get("nse_symbol", "UNKNOWN")

                self._check_data_completeness(conn, company_id, symbol)
                self._check_balance_sheet_equation(conn, company_id, symbol)
                self._check_pnl_consistency(conn, company_id, symbol)
                self._check_cash_flow_consistency(conn, company_id, symbol)
                self._check_reasonable_values(conn, company_id, symbol)

        return self.errors

    def _check_data_completeness(self, conn, company_id, symbol):
        """Check that all 3 years of data exist for all 3 statements."""
        pnl_count = conn.execute(
            "SELECT COUNT(*) FROM profit_loss WHERE company_id = ?", (company_id,)
        ).fetchone()[0]

        bs_count = conn.execute(
            "SELECT COUNT(*) FROM balance_sheet WHERE company_id = ?", (company_id,)
        ).fetchone()[0]

        cf_count = conn.execute(
            "SELECT COUNT(*) FROM cash_flow WHERE company_id = ?", (company_id,)
        ).fetchone()[0]

        if pnl_count < 3:
            self.errors.append(ValidationError(
                company_id, symbol, "completeness",
                f"Only {pnl_count}/3 years of P&L data",
                "warning" if pnl_count > 0 else "error",
            ))

        if bs_count < 3:
            self.errors.append(ValidationError(
                company_id, symbol, "completeness",
                f"Only {bs_count}/3 years of Balance Sheet data",
                "warning" if bs_count > 0 else "error",
            ))

        if cf_count < 3:
            self.errors.append(ValidationError(
                company_id, symbol, "completeness",
                f"Only {cf_count}/3 years of Cash Flow data",
                "warning" if cf_count > 0 else "error",
            ))

    def _check_balance_sheet_equation(self, conn, company_id, symbol):
        """Check that Total Assets = Total Liabilities (accounting equation)."""
        rows = conn.execute(
            """SELECT fiscal_year, total_assets, total_liabilities
               FROM balance_sheet WHERE company_id = ?""",
            (company_id,),
        ).fetchall()

        for row in rows:
            total_assets = row["total_assets"]
            total_liabilities = row["total_liabilities"]

            if total_assets is None or total_liabilities is None:
                self.errors.append(ValidationError(
                    company_id, symbol, "balance_sheet_equation",
                    f"FY {row['fiscal_year']}: Missing total assets or liabilities",
                    "warning",
                ))
                continue

            # Allow 1% tolerance for rounding differences
            if total_assets > 0:
                diff_pct = abs(total_assets - total_liabilities) / total_assets * 100
                if diff_pct > 1.0:
                    self.errors.append(ValidationError(
                        company_id, symbol, "balance_sheet_equation",
                        f"FY {row['fiscal_year']}: Total Assets ({total_assets:.1f}) != "
                        f"Total Liabilities ({total_liabilities:.1f}), diff: {diff_pct:.1f}%",
                        "error",
                    ))

    def _check_pnl_consistency(self, conn, company_id, symbol):
        """Check P&L internal consistency."""
        rows = conn.execute(
            """SELECT fiscal_year, sales, expenses, operating_profit,
                      profit_before_tax, net_profit
               FROM profit_loss WHERE company_id = ?""",
            (company_id,),
        ).fetchall()

        for row in rows:
            fy = row["fiscal_year"]
            sales = row["sales"]
            expenses = row["expenses"]
            op_profit = row["operating_profit"]

            # Check: Operating Profit ≈ Sales - Expenses
            if sales is not None and expenses is not None and op_profit is not None:
                expected_op = sales - expenses
                if abs(expected_op) > 0:
                    diff_pct = abs(op_profit - expected_op) / abs(max(sales, 1)) * 100
                    if diff_pct > 5.0:
                        self.errors.append(ValidationError(
                            company_id, symbol, "pnl_consistency",
                            f"FY {fy}: Operating Profit ({op_profit:.1f}) != "
                            f"Sales ({sales:.1f}) - Expenses ({expenses:.1f}) = {expected_op:.1f}",
                            "warning",
                        ))

    def _check_cash_flow_consistency(self, conn, company_id, symbol):
        """Check cash flow components sum to net cash flow."""
        rows = conn.execute(
            """SELECT fiscal_year, cash_from_operating, cash_from_investing,
                      cash_from_financing, net_cash_flow
               FROM cash_flow WHERE company_id = ?""",
            (company_id,),
        ).fetchall()

        for row in rows:
            fy = row["fiscal_year"]
            operating = row["cash_from_operating"]
            investing = row["cash_from_investing"]
            financing = row["cash_from_financing"]
            net = row["net_cash_flow"]

            if all(v is not None for v in [operating, investing, financing, net]):
                expected_net = operating + investing + financing
                if abs(net) > 0:
                    diff_pct = abs(net - expected_net) / max(abs(net), 1) * 100
                    if diff_pct > 5.0:
                        self.errors.append(ValidationError(
                            company_id, symbol, "cash_flow_consistency",
                            f"FY {fy}: Net Cash Flow ({net:.1f}) != "
                            f"Sum of components ({expected_net:.1f})",
                            "warning",
                        ))

    def _check_reasonable_values(self, conn, company_id, symbol):
        """Check for unreasonable values that might indicate scraping errors."""
        # Check for negative sales (unusual except for financial companies)
        rows = conn.execute(
            "SELECT fiscal_year, sales FROM profit_loss WHERE company_id = ? AND sales < 0",
            (company_id,),
        ).fetchall()
        for row in rows:
            self.errors.append(ValidationError(
                company_id, symbol, "reasonable_values",
                f"FY {row['fiscal_year']}: Negative sales ({row['sales']:.1f})",
                "warning",
            ))

        # Check for negative total assets
        rows = conn.execute(
            "SELECT fiscal_year, total_assets FROM balance_sheet WHERE company_id = ? AND total_assets < 0",
            (company_id,),
        ).fetchall()
        for row in rows:
            self.errors.append(ValidationError(
                company_id, symbol, "reasonable_values",
                f"FY {row['fiscal_year']}: Negative total assets ({row['total_assets']:.1f})",
                "error",
            ))

    def get_summary(self):
        """Get validation summary."""
        error_count = sum(1 for e in self.errors if e.severity == "error")
        warning_count = sum(1 for e in self.errors if e.severity == "warning")

        return {
            "total_issues": len(self.errors),
            "errors": error_count,
            "warnings": warning_count,
            "issues_by_check": self._group_by_check(),
        }

    def _group_by_check(self):
        """Group errors by check name."""
        groups = {}
        for error in self.errors:
            if error.check_name not in groups:
                groups[error.check_name] = 0
            groups[error.check_name] += 1
        return groups
