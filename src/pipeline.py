"""Main data pipeline orchestrating company discovery, scraping, and storage."""

import logging
import json
import os
import time
from tqdm import tqdm

from src.config import (
    DATA_DIR,
    DB_PATH,
    MIN_MARKET_CAP_CRORES,
    PROCESSED_DATA_DIR,
    RATE_LIMIT_DELAY,
    LOG_FORMAT,
    LOG_FILE,
)
from src.models import (
    init_db,
    get_db_connection,
    insert_company,
    insert_profit_loss,
    insert_balance_sheet,
    insert_cash_flow,
    log_scrape,
)
from src.company_list import CompanyListFetcher
from src.screener_scraper import ScreenerScraper, ScraperError
from src.exporters import DataExporter
from src.validators import DataValidator

logger = logging.getLogger(__name__)


class Pipeline:
    """Orchestrates the full data collection pipeline."""

    def __init__(self, db_path=None, rate_limit_delay=RATE_LIMIT_DELAY):
        self.db_path = db_path or DB_PATH
        self.rate_limit_delay = rate_limit_delay
        self.stats = {
            "total_companies": 0,
            "companies_processed": 0,
            "companies_with_data": 0,
            "companies_failed": 0,
            "companies_skipped_mcap": 0,
        }

    def setup_logging(self):
        """Configure logging for the pipeline."""
        logging.basicConfig(
            level=logging.INFO,
            format=LOG_FORMAT,
            handlers=[
                logging.FileHandler(LOG_FILE),
                logging.StreamHandler(),
            ],
        )

    def run(self, symbols=None, skip_existing=True):
        """
        Run the full pipeline.

        Args:
            symbols: Optional list of specific symbols to process.
                    If None, discovers all qualifying companies.
            skip_existing: Skip companies that already have data in the DB.
        """
        self.setup_logging()
        logger.info("=" * 60)
        logger.info("Starting Financial Data Pipeline")
        logger.info("Market cap threshold: %d crores", MIN_MARKET_CAP_CRORES)
        logger.info("=" * 60)

        # Initialize database
        os.makedirs(DATA_DIR, exist_ok=True)
        init_db(self.db_path)

        # Step 1: Get company list
        if symbols:
            company_list = [{"symbol": s, "name": s, "source": "manual"} for s in symbols]
        else:
            company_list = self._discover_companies()

        self.stats["total_companies"] = len(company_list)
        logger.info("Total companies to process: %d", len(company_list))

        # Step 2: Process each company
        self._process_companies(company_list, skip_existing)

        # Step 3: Validate data
        logger.info("Running data validation...")
        validator = DataValidator(self.db_path)
        validation_errors = validator.validate_all()
        validation_summary = validator.get_summary()
        logger.info("Validation summary: %s", json.dumps(validation_summary, indent=2))

        # Step 4: Export data
        logger.info("Exporting data...")
        exporter = DataExporter(self.db_path)
        exporter.export_all()
        summary = exporter.generate_summary_report()

        # Print final stats
        self._print_stats(summary, validation_summary)

        return self.stats

    def _discover_companies(self):
        """Discover companies from all sources.

        Uses the seed company list first (comprehensive NSE/BSE list),
        then tries live APIs for additional companies.
        """
        # First try the curated seed list (most reliable)
        try:
            from src.seed_companies import get_seed_symbols
            seed_symbols = get_seed_symbols()
            if seed_symbols:
                logger.info(
                    "Using seed company list with %d symbols", len(seed_symbols)
                )
                return [
                    {"symbol": s, "name": s, "source": "seed"}
                    for s in seed_symbols
                ]
        except ImportError:
            logger.info("No seed company list found, using live discovery")

        # Fall back to live discovery
        fetcher = CompanyListFetcher(self.rate_limit_delay)
        try:
            cached = fetcher.load_company_list()
            if cached:
                logger.info("Loaded cached company list with %d companies", len(cached))
                return cached

            return fetcher.get_comprehensive_company_list()
        finally:
            fetcher.close()

    def _process_companies(self, company_list, skip_existing):
        """Process each company: scrape and store financial data."""
        scraper = ScreenerScraper(self.rate_limit_delay)

        try:
            with get_db_connection(self.db_path) as conn:
                existing_symbols = set()
                if skip_existing:
                    cursor = conn.execute(
                        "SELECT nse_symbol FROM companies WHERE nse_symbol IS NOT NULL"
                    )
                    existing_symbols = {row["nse_symbol"] for row in cursor.fetchall()}

            progress = tqdm(company_list, desc="Processing companies", unit="company")

            for company_info in progress:
                symbol = company_info.get("symbol")
                if not symbol:
                    continue

                progress.set_postfix(symbol=symbol)

                if skip_existing and symbol in existing_symbols:
                    logger.debug("Skipping %s (already in DB)", symbol)
                    self.stats["companies_processed"] += 1
                    continue

                self._process_single_company(scraper, symbol, company_info)

        finally:
            scraper.close()

    def _process_single_company(self, scraper, symbol, company_info):
        """Process a single company."""
        try:
            # Scrape data from Screener.in
            data = scraper.scrape_company(symbol)

            if not data:
                logger.warning("No data returned for %s", symbol)
                self.stats["companies_failed"] += 1
                return

            # Check market cap threshold
            market_cap = (
                data.get("company_info", {}).get("market_cap_crores")
            )
            if market_cap and market_cap < MIN_MARKET_CAP_CRORES:
                logger.info(
                    "Skipping %s: market cap %.0f < %d crores",
                    symbol, market_cap, MIN_MARKET_CAP_CRORES,
                )
                self.stats["companies_skipped_mcap"] += 1
                return

            # Store in database
            self._store_company_data(symbol, data, company_info)
            self.stats["companies_with_data"] += 1

        except ScraperError as e:
            logger.error("Scraper error for %s: %s", symbol, e)
            self.stats["companies_failed"] += 1
            self._log_error(symbol, str(e))

        except Exception as e:
            logger.error("Unexpected error for %s: %s", symbol, e, exc_info=True)
            self.stats["companies_failed"] += 1
            self._log_error(symbol, str(e))

        finally:
            self.stats["companies_processed"] += 1

    def _store_company_data(self, symbol, data, source_info):
        """Store scraped data in the database."""
        company_info = data.get("company_info", {})
        is_consolidated = data.get("is_consolidated", True)

        with get_db_connection(self.db_path) as conn:
            # Insert/update company
            company_data = {
                "name": company_info.get("name", source_info.get("name", symbol)),
                "bse_code": company_info.get("bse_code", source_info.get("bse_code")),
                "nse_symbol": symbol,
                "isin": company_info.get("isin", source_info.get("isin")),
                "industry": company_info.get("industry", source_info.get("industry")),
                "sector": company_info.get("sector", source_info.get("sector")),
                "market_cap_crores": company_info.get("market_cap_crores"),
                "is_consolidated": 1 if is_consolidated else 0,
                "screener_url": data.get("source_url", ""),
            }
            company_id = insert_company(conn, company_data)

            if not company_id:
                logger.error("Failed to insert company %s", symbol)
                return

            # Insert P&L data
            for fiscal_year, pnl_data in data.get("profit_loss", {}).items():
                if pnl_data:
                    insert_profit_loss(
                        conn, company_id, fiscal_year, pnl_data, is_consolidated
                    )

            # Insert Balance Sheet data
            for fiscal_year, bs_data in data.get("balance_sheet", {}).items():
                if bs_data:
                    insert_balance_sheet(
                        conn, company_id, fiscal_year, bs_data, is_consolidated
                    )

            # Insert Cash Flow data
            for fiscal_year, cf_data in data.get("cash_flow", {}).items():
                if cf_data:
                    insert_cash_flow(
                        conn, company_id, fiscal_year, cf_data, is_consolidated
                    )

            # Log successful scrape
            log_scrape(conn, company_id, symbol, "success", source="screener.in")

        logger.info(
            "Stored data for %s (%s)",
            symbol,
            "Consolidated" if is_consolidated else "Standalone",
        )

    def _log_error(self, symbol, error_message):
        """Log a scraping error to the database."""
        try:
            with get_db_connection(self.db_path) as conn:
                log_scrape(conn, None, symbol, "error", error_message, "screener.in")
        except Exception:
            pass  # Don't let logging errors crash the pipeline

    def _print_stats(self, data_summary, validation_summary):
        """Print final pipeline statistics."""
        logger.info("=" * 60)
        logger.info("Pipeline Complete")
        logger.info("=" * 60)
        logger.info("Companies processed: %d", self.stats["companies_processed"])
        logger.info("Companies with data: %d", self.stats["companies_with_data"])
        logger.info("Companies failed: %d", self.stats["companies_failed"])
        logger.info(
            "Companies below market cap: %d", self.stats["companies_skipped_mcap"]
        )
        logger.info("-" * 40)
        logger.info("Data Summary:")
        logger.info("  Total companies in DB: %d", data_summary.get("total_companies", 0))
        logger.info(
            "  Consolidated: %d", data_summary.get("consolidated_reports", 0)
        )
        logger.info("  Standalone: %d", data_summary.get("standalone_reports", 0))
        logger.info("  P&L records: %d", data_summary.get("profit_loss_records", 0))
        logger.info(
            "  Balance Sheet records: %d", data_summary.get("balance_sheet_records", 0)
        )
        logger.info("  Cash Flow records: %d", data_summary.get("cash_flow_records", 0))
        logger.info(
            "  Complete 3-year profiles: %d",
            data_summary.get("companies_with_complete_3yr_data", 0),
        )
        logger.info("-" * 40)
        logger.info("Validation:")
        logger.info("  Errors: %d", validation_summary.get("errors", 0))
        logger.info("  Warnings: %d", validation_summary.get("warnings", 0))
        logger.info("=" * 60)
