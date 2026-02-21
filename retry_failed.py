"""Retry companies that had no financial data in the first pass.

Some companies on Screener.in have their consolidated page redirect to
standalone, or their financial data tables render differently. This script
tries both consolidated and standalone URLs and also tries alternate
parsing strategies.
"""

import logging
import json
import time
import re
import requests
from bs4 import BeautifulSoup

from src.config import (
    SCREENER_BASE_URL,
    HEADERS,
    DB_PATH,
    RAW_DATA_DIR,
    NUM_YEARS,
    REQUEST_TIMEOUT,
)
from src.models import (
    get_db_connection,
    insert_company,
    insert_profit_loss,
    insert_balance_sheet,
    insert_cash_flow,
    log_scrape,
)
from src.screener_scraper import ScreenerScraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Companies that had 0 financial data in the first pass
RETRY_SYMBOLS = [
    "ABBOTINDIA", "ASTRAZEN", "ATHERENERG", "BAJAJHFL", "BANDHANBNK",
    "BDL", "BHARTIHEXA", "CANFINHOME", "CASTROLIND", "CUB",
    "DATAPATTNS", "ENRIN", "GILLETTE", "GODIGIT", "GRSE",
    "HOMEFIRST", "HONAUT", "ICICIGI", "IRFC", "KARURVYSYA",
    "KWIL", "MAHSCOOTER", "MSUMI", "NETWEB", "NIVABUPA",
    "NSLNISP", "PAGEIND", "PFIZER", "PGHH", "POWERINDIA",
    "SBICARD", "SBILIFE", "SCHNEIDER", "STARHEALTH",
]


def try_standalone(scraper, symbol):
    """Try fetching from standalone URL."""
    url = f"{SCREENER_BASE_URL}/company/{symbol}/"
    try:
        html = scraper._fetch_page(url)
        soup = BeautifulSoup(html, "lxml")

        company_info = scraper._extract_company_info(soup, symbol)
        company_info["is_consolidated"] = False

        profit_loss = scraper._extract_table_data(soup, "profit-loss")
        balance_sheet = scraper._extract_table_data(soup, "balance-sheet")
        cash_flow = scraper._extract_table_data(soup, "cash-flow")

        # Filter to annual March data and recent N years
        profit_loss = scraper._filter_recent_years(profit_loss, NUM_YEARS)
        balance_sheet = scraper._filter_recent_years(balance_sheet, NUM_YEARS)
        cash_flow = scraper._filter_recent_years(cash_flow, NUM_YEARS)

        if profit_loss or balance_sheet or cash_flow:
            return {
                "company_info": company_info,
                "profit_loss": profit_loss,
                "balance_sheet": balance_sheet,
                "cash_flow": cash_flow,
                "is_consolidated": False,
                "source_url": url,
            }
    except Exception as e:
        logger.warning("Standalone failed for %s: %s", symbol, e)

    return None


def try_consolidated_retry(scraper, symbol):
    """Retry consolidated URL with fresh session."""
    url = f"{SCREENER_BASE_URL}/company/{symbol}/consolidated/"
    try:
        html = scraper._fetch_page(url)
        soup = BeautifulSoup(html, "lxml")

        company_info = scraper._extract_company_info(soup, symbol)
        company_info["is_consolidated"] = True

        profit_loss = scraper._extract_table_data(soup, "profit-loss")
        balance_sheet = scraper._extract_table_data(soup, "balance-sheet")
        cash_flow = scraper._extract_table_data(soup, "cash-flow")

        profit_loss = scraper._filter_recent_years(profit_loss, NUM_YEARS)
        balance_sheet = scraper._filter_recent_years(balance_sheet, NUM_YEARS)
        cash_flow = scraper._filter_recent_years(cash_flow, NUM_YEARS)

        if profit_loss or balance_sheet or cash_flow:
            return {
                "company_info": company_info,
                "profit_loss": profit_loss,
                "balance_sheet": balance_sheet,
                "cash_flow": cash_flow,
                "is_consolidated": True,
                "source_url": url,
            }
    except Exception as e:
        logger.warning("Consolidated retry failed for %s: %s", symbol, e)

    return None


def store_data(symbol, data):
    """Store scraped data in the database."""
    company_info = data.get("company_info", {})
    is_consolidated = data.get("is_consolidated", True)

    with get_db_connection(DB_PATH) as conn:
        company_data = {
            "name": company_info.get("name", symbol),
            "bse_code": company_info.get("bse_code"),
            "nse_symbol": symbol,
            "isin": company_info.get("isin"),
            "industry": company_info.get("industry"),
            "sector": company_info.get("sector"),
            "market_cap_crores": company_info.get("market_cap_crores"),
            "is_consolidated": 1 if is_consolidated else 0,
            "screener_url": data.get("source_url", ""),
        }
        company_id = insert_company(conn, company_data)

        for fiscal_year, pnl_data in data.get("profit_loss", {}).items():
            if pnl_data:
                insert_profit_loss(conn, company_id, fiscal_year, pnl_data, is_consolidated)

        for fiscal_year, bs_data in data.get("balance_sheet", {}).items():
            if bs_data:
                insert_balance_sheet(conn, company_id, fiscal_year, bs_data, is_consolidated)

        for fiscal_year, cf_data in data.get("cash_flow", {}).items():
            if cf_data:
                insert_cash_flow(conn, company_id, fiscal_year, cf_data, is_consolidated)

        log_scrape(conn, company_id, symbol, "success", source="screener.in-retry")


def main():
    logger.info("Retrying %d companies with missing financial data", len(RETRY_SYMBOLS))

    # Use a fresh session
    scraper = ScreenerScraper(rate_limit_delay=3.0)
    scraper.session = requests.Session()
    scraper.session.headers.update(HEADERS)

    success_count = 0
    still_failed = []

    for symbol in RETRY_SYMBOLS:
        logger.info("Retrying %s...", symbol)

        # Try consolidated with fresh session
        data = try_consolidated_retry(scraper, symbol)

        # If consolidated still fails, try standalone
        if not data:
            logger.info("  Trying standalone for %s...", symbol)
            data = try_standalone(scraper, symbol)

        if data:
            pnl_years = len(data.get("profit_loss", {}))
            bs_years = len(data.get("balance_sheet", {}))
            cf_years = len(data.get("cash_flow", {}))
            report_type = "Consolidated" if data["is_consolidated"] else "Standalone"

            if pnl_years > 0 or bs_years > 0 or cf_years > 0:
                store_data(symbol, data)
                logger.info(
                    "  SUCCESS: %s (%s) - P&L: %d years, BS: %d years, CF: %d years",
                    symbol, report_type, pnl_years, bs_years, cf_years,
                )
                success_count += 1

                # Save raw data
                import os
                os.makedirs(RAW_DATA_DIR, exist_ok=True)
                with open(os.path.join(RAW_DATA_DIR, f"{symbol}.json"), "w") as f:
                    json.dump(data, f, indent=2, default=str)
            else:
                still_failed.append(symbol)
                logger.warning("  STILL NO DATA: %s", symbol)
        else:
            still_failed.append(symbol)
            logger.warning("  FAILED: %s - no data from either source", symbol)

        time.sleep(3)

    scraper.close()

    logger.info("=" * 50)
    logger.info("Retry complete: %d recovered, %d still failed", success_count, len(still_failed))
    if still_failed:
        logger.info("Still failed: %s", ", ".join(still_failed))


if __name__ == "__main__":
    main()
