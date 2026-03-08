"""Export financial data from SQLite database to CSV files."""

import csv
import json
import os
import logging
import pandas as pd

from src.config import EXPORTS_DIR, MIN_MARKET_CAP_CRORES
from src.models import get_db_connection, get_all_companies, get_company_financial_data

logger = logging.getLogger(__name__)


class DataExporter:
    """Exports financial data to various formats."""

    def __init__(self, db_path=None, exports_dir=None):
        self.db_path = db_path
        self.exports_dir = exports_dir or EXPORTS_DIR

    def export_all(self):
        """Export all data to CSV files."""
        os.makedirs(self.exports_dir, exist_ok=True)

        self.export_company_master()
        self.export_profit_loss()
        self.export_balance_sheet()
        self.export_cash_flow()
        self.export_per_company_profiles()

        logger.info("All exports completed to %s", self.exports_dir)

    def export_company_master(self):
        """Export company master list to CSV."""
        filepath = os.path.join(self.exports_dir, "companies.csv")
        with get_db_connection(self.db_path) as conn:
            companies = get_all_companies(conn, MIN_MARKET_CAP_CRORES)

        if not companies:
            logger.warning("No companies to export")
            return

        df = pd.DataFrame(companies)
        # Reorder columns
        cols = ["id", "name", "nse_symbol", "bse_code", "isin", "industry",
                "sector", "market_cap_crores", "is_consolidated", "last_updated"]
        cols = [c for c in cols if c in df.columns]
        df = df[cols]
        df.to_csv(filepath, index=False)
        logger.info("Exported %d companies to %s", len(df), filepath)

    def export_profit_loss(self):
        """Export all profit & loss data to a single CSV."""
        filepath = os.path.join(self.exports_dir, "profit_loss_all.csv")
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT c.name, c.nse_symbol, c.bse_code,
                       p.fiscal_year, p.sales, p.expenses, p.operating_profit,
                       p.opm_percent, p.other_income, p.interest, p.depreciation,
                       p.profit_before_tax, p.tax_percent, p.net_profit,
                       p.eps, p.dividend_payout_percent,
                       CASE WHEN p.is_consolidated = 1 THEN 'Consolidated' ELSE 'Standalone' END as report_type
                FROM profit_loss p
                JOIN companies c ON p.company_id = c.id
                WHERE c.market_cap_crores >= ?
                ORDER BY c.name, p.fiscal_year
            """, (MIN_MARKET_CAP_CRORES,))
            rows = cursor.fetchall()

        if not rows:
            logger.warning("No P&L data to export")
            return

        df = pd.DataFrame([dict(r) for r in rows])
        df.to_csv(filepath, index=False)
        logger.info("Exported %d P&L records to %s", len(df), filepath)

    def export_balance_sheet(self):
        """Export all balance sheet data to a single CSV."""
        filepath = os.path.join(self.exports_dir, "balance_sheet_all.csv")
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT c.name, c.nse_symbol, c.bse_code,
                       b.fiscal_year, b.equity_capital, b.reserves, b.borrowings,
                       b.other_liabilities, b.total_liabilities, b.fixed_assets,
                       b.cwip, b.investments, b.other_assets, b.total_assets,
                       CASE WHEN b.is_consolidated = 1 THEN 'Consolidated' ELSE 'Standalone' END as report_type
                FROM balance_sheet b
                JOIN companies c ON b.company_id = c.id
                WHERE c.market_cap_crores >= ?
                ORDER BY c.name, b.fiscal_year
            """, (MIN_MARKET_CAP_CRORES,))
            rows = cursor.fetchall()

        if not rows:
            logger.warning("No balance sheet data to export")
            return

        df = pd.DataFrame([dict(r) for r in rows])
        df.to_csv(filepath, index=False)
        logger.info("Exported %d balance sheet records to %s", len(df), filepath)

    def export_cash_flow(self):
        """Export all cash flow data to a single CSV."""
        filepath = os.path.join(self.exports_dir, "cash_flow_all.csv")
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT c.name, c.nse_symbol, c.bse_code,
                       cf.fiscal_year, cf.cash_from_operating, cf.cash_from_investing,
                       cf.cash_from_financing, cf.net_cash_flow,
                       CASE WHEN cf.is_consolidated = 1 THEN 'Consolidated' ELSE 'Standalone' END as report_type
                FROM cash_flow cf
                JOIN companies c ON cf.company_id = c.id
                WHERE c.market_cap_crores >= ?
                ORDER BY c.name, cf.fiscal_year
            """, (MIN_MARKET_CAP_CRORES,))
            rows = cursor.fetchall()

        if not rows:
            logger.warning("No cash flow data to export")
            return

        df = pd.DataFrame([dict(r) for r in rows])
        df.to_csv(filepath, index=False)
        logger.info("Exported %d cash flow records to %s", len(df), filepath)

    def export_per_company_profiles(self):
        """Export individual company financial profiles as JSON files."""
        profiles_dir = os.path.join(self.exports_dir, "company_profiles")
        os.makedirs(profiles_dir, exist_ok=True)

        with get_db_connection(self.db_path) as conn:
            companies = get_all_companies(conn, MIN_MARKET_CAP_CRORES)

            for company in companies:
                company_id = company["id"]
                symbol = company.get("nse_symbol", company.get("bse_code", str(company_id)))
                financial_data = get_company_financial_data(conn, company_id)

                profile = {
                    "company": company,
                    "report_type": "Consolidated" if company.get("is_consolidated") else "Standalone",
                    "profit_loss": financial_data["profit_loss"],
                    "balance_sheet": financial_data["balance_sheet"],
                    "cash_flow": financial_data["cash_flow"],
                }

                filepath = os.path.join(profiles_dir, f"{symbol}.json")
                with open(filepath, "w") as f:
                    json.dump(profile, f, indent=2, default=str)

        logger.info("Exported %d company profiles to %s", len(companies), profiles_dir)

    def generate_summary_report(self):
        """Generate a summary report of the collected data."""
        with get_db_connection(self.db_path) as conn:
            total_companies = conn.execute(
                "SELECT COUNT(*) FROM companies WHERE market_cap_crores >= ?",
                (MIN_MARKET_CAP_CRORES,),
            ).fetchone()[0]

            consolidated_count = conn.execute(
                "SELECT COUNT(*) FROM companies WHERE market_cap_crores >= ? AND is_consolidated = 1",
                (MIN_MARKET_CAP_CRORES,),
            ).fetchone()[0]

            standalone_count = total_companies - consolidated_count

            pnl_records = conn.execute(
                """SELECT COUNT(*) FROM profit_loss p
                   JOIN companies c ON p.company_id = c.id
                   WHERE c.market_cap_crores >= ?""",
                (MIN_MARKET_CAP_CRORES,),
            ).fetchone()[0]

            bs_records = conn.execute(
                """SELECT COUNT(*) FROM balance_sheet b
                   JOIN companies c ON b.company_id = c.id
                   WHERE c.market_cap_crores >= ?""",
                (MIN_MARKET_CAP_CRORES,),
            ).fetchone()[0]

            cf_records = conn.execute(
                """SELECT COUNT(*) FROM cash_flow cf
                   JOIN companies c ON cf.company_id = c.id
                   WHERE c.market_cap_crores >= ?""",
                (MIN_MARKET_CAP_CRORES,),
            ).fetchone()[0]

            # Companies with complete data (all 3 years for all 3 statements)
            complete_companies = conn.execute(
                """SELECT COUNT(DISTINCT c.id) FROM companies c
                   WHERE c.market_cap_crores >= ?
                   AND (SELECT COUNT(*) FROM profit_loss WHERE company_id = c.id) >= 3
                   AND (SELECT COUNT(*) FROM balance_sheet WHERE company_id = c.id) >= 3
                   AND (SELECT COUNT(*) FROM cash_flow WHERE company_id = c.id) >= 3""",
                (MIN_MARKET_CAP_CRORES,),
            ).fetchone()[0]

        summary = {
            "total_companies": total_companies,
            "consolidated_reports": consolidated_count,
            "standalone_reports": standalone_count,
            "profit_loss_records": pnl_records,
            "balance_sheet_records": bs_records,
            "cash_flow_records": cf_records,
            "companies_with_complete_3yr_data": complete_companies,
            "market_cap_threshold_crores": MIN_MARKET_CAP_CRORES,
        }

        filepath = os.path.join(self.exports_dir, "data_summary.json")
        with open(filepath, "w") as f:
            json.dump(summary, f, indent=2)

        logger.info("Summary report: %s", json.dumps(summary, indent=2))
        return summary
