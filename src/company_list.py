"""
Fetch list of companies listed on NSE and BSE with market cap > 5000 crore.

Uses multiple data sources:
1. NSE India equity list (for all NSE-listed symbols)
2. BSE India API (for BSE-listed companies)
3. Screener.in (for market cap filtering and as primary source)

The combined approach ensures comprehensive coverage of both exchanges.
"""

import csv
import io
import re
import time
import logging
import json
import os
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config import (
    HEADERS,
    REQUEST_TIMEOUT,
    NSE_BASE_URL,
    BSE_API_BASE,
    SCREENER_BASE_URL,
    MIN_MARKET_CAP_CRORES,
    RATE_LIMIT_DELAY,
    PROCESSED_DATA_DIR,
)

logger = logging.getLogger(__name__)


class CompanyListFetcher:
    """Fetches and maintains a list of companies meeting market cap criteria."""

    def __init__(self, rate_limit_delay=RATE_LIMIT_DELAY):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time = 0

    def _rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    )
    def _fetch(self, url, **kwargs):
        self._rate_limit()
        response = self.session.get(url, timeout=REQUEST_TIMEOUT, **kwargs)
        response.raise_for_status()
        return response

    def fetch_nse_equity_list(self):
        """
        Fetch complete list of equities listed on NSE.

        Returns list of dicts with keys: symbol, name, isin, series
        """
        companies = []
        try:
            # NSE requires cookies/session, so visit main page first
            self.session.get(NSE_BASE_URL, timeout=REQUEST_TIMEOUT)
            time.sleep(1)

            # Try the NSE API for equity stock indices
            url = f"{NSE_BASE_URL}/api/equity-stockIndices?index=SECURITIES%20IN%20F%26O"
            response = self._fetch(url)
            data = response.json()

            if "data" in data:
                for item in data["data"]:
                    companies.append({
                        "symbol": item.get("symbol"),
                        "name": item.get("companyName", item.get("symbol")),
                        "isin": item.get("isin"),
                        "series": "EQ",
                        "source": "nse",
                    })
            logger.info("Fetched %d companies from NSE F&O list", len(companies))
        except Exception as e:
            logger.warning("Failed to fetch NSE equity list via API: %s", e)

        # Also try NIFTY 500
        try:
            time.sleep(2)
            url = f"{NSE_BASE_URL}/api/equity-stockIndices?index=NIFTY%20500"
            response = self._fetch(url)
            data = response.json()
            existing_symbols = {c["symbol"] for c in companies}

            if "data" in data:
                for item in data["data"]:
                    sym = item.get("symbol")
                    if sym and sym not in existing_symbols:
                        companies.append({
                            "symbol": sym,
                            "name": item.get("companyName", sym),
                            "isin": item.get("isin"),
                            "series": "EQ",
                            "source": "nse",
                        })
            logger.info("Total companies after NIFTY 500: %d", len(companies))
        except Exception as e:
            logger.warning("Failed to fetch NIFTY 500 list: %s", e)

        # Try NIFTY TOTAL MARKET
        try:
            time.sleep(2)
            url = f"{NSE_BASE_URL}/api/equity-stockIndices?index=NIFTY%20TOTAL%20MARKET"
            response = self._fetch(url)
            data = response.json()
            existing_symbols = {c["symbol"] for c in companies}

            if "data" in data:
                for item in data["data"]:
                    sym = item.get("symbol")
                    if sym and sym not in existing_symbols:
                        companies.append({
                            "symbol": sym,
                            "name": item.get("companyName", sym),
                            "isin": item.get("isin"),
                            "series": "EQ",
                            "source": "nse",
                        })
            logger.info("Total companies after NIFTY TOTAL MARKET: %d", len(companies))
        except Exception as e:
            logger.warning("Failed to fetch NIFTY TOTAL MARKET list: %s", e)

        return companies

    def fetch_bse_company_list(self):
        """
        Fetch list of companies from BSE India.

        Returns list of dicts with keys: symbol, name, bse_code, source
        """
        companies = []

        # Try BSE API for active companies
        for group in ["A", "B", "T", "S", "M", "XC", "XD", "XT"]:
            try:
                url = (
                    f"{BSE_API_BASE}/ListofScripData/w"
                    f"?Group={group}&Scripcode=&industry=&Flag=&Search="
                )
                response = self._fetch(url)
                data = response.json()

                if isinstance(data, list):
                    for item in data:
                        companies.append({
                            "symbol": item.get("scrip_id", ""),
                            "name": item.get("SCRIP_NAME", item.get("Scrip_Name", "")),
                            "bse_code": str(item.get("SCRIP_CD", item.get("Scrip_Code", ""))),
                            "group": group,
                            "source": "bse",
                        })
                logger.info("Fetched %d companies from BSE group %s", len(data) if isinstance(data, list) else 0, group)
                time.sleep(1)
            except Exception as e:
                logger.warning("Failed to fetch BSE group %s: %s", group, e)

        return companies

    def fetch_companies_from_screener(self, min_market_cap=MIN_MARKET_CAP_CRORES):
        """
        Fetch companies from Screener.in with market cap > threshold.

        This is used as a fallback/supplement. Screener.in query pages
        may require authentication for full results, but individual
        company pages are publicly accessible.

        Returns list of dicts with symbol and name.
        """
        companies = []
        page = 1
        max_pages = 50  # Safety limit

        while page <= max_pages:
            try:
                url = (
                    f"{SCREENER_BASE_URL}/screen/raw/"
                    f"?sort=market+capitalization&order=desc"
                    f"&query=Market+Capitalization+>+{min_market_cap}"
                    f"&page={page}"
                )
                self._rate_limit()
                response = self.session.get(url, timeout=REQUEST_TIMEOUT)

                if response.status_code in (401, 403):
                    logger.info("Screener.in requires authentication for query pages")
                    break

                response.raise_for_status()
                soup = BeautifulSoup(response.text, "lxml")

                # Parse results table
                table = soup.find("table")
                if not table:
                    break

                rows_found = 0
                for row in table.find_all("tr"):
                    link = row.find("a", href=re.compile(r"/company/"))
                    if link:
                        href = link.get("href", "")
                        match = re.search(r"/company/([^/]+)/", href)
                        if match:
                            companies.append({
                                "symbol": match.group(1),
                                "name": link.get_text(strip=True),
                                "source": "screener",
                            })
                            rows_found += 1

                if rows_found == 0:
                    break

                # Check for next page
                next_link = soup.find("a", string=re.compile(r"Next|›"))
                if not next_link:
                    break

                page += 1
                logger.info("Fetched page %d from Screener.in (%d companies so far)", page, len(companies))

            except Exception as e:
                logger.warning("Failed to fetch Screener.in page %d: %s", page, e)
                break

        return companies

    def get_comprehensive_company_list(self):
        """
        Get a comprehensive list of companies from all sources.

        Merges data from NSE, BSE, and Screener.in, deduplicates by symbol.

        Returns list of dicts with keys: symbol, name, bse_code, isin, source
        """
        all_companies = {}

        # 1. Try NSE first
        logger.info("Fetching company list from NSE...")
        nse_companies = self.fetch_nse_equity_list()
        for company in nse_companies:
            sym = company.get("symbol")
            if sym:
                all_companies[sym] = company

        # 2. Try BSE
        logger.info("Fetching company list from BSE...")
        bse_companies = self.fetch_bse_company_list()
        for company in bse_companies:
            sym = company.get("symbol")
            if sym and sym not in all_companies:
                all_companies[sym] = company
            elif sym and sym in all_companies:
                # Merge BSE code into existing record
                all_companies[sym]["bse_code"] = company.get("bse_code")

        # 3. Try Screener.in as supplement
        logger.info("Fetching company list from Screener.in...")
        screener_companies = self.fetch_companies_from_screener()
        for company in screener_companies:
            sym = company.get("symbol")
            if sym and sym not in all_companies:
                all_companies[sym] = company

        result = list(all_companies.values())
        logger.info("Total unique companies from all sources: %d", len(result))

        # Save the combined list
        self._save_company_list(result)

        return result

    def _save_company_list(self, companies):
        """Save the company list to a JSON file."""
        os.makedirs(PROCESSED_DATA_DIR, exist_ok=True)
        filepath = os.path.join(PROCESSED_DATA_DIR, "company_list.json")
        with open(filepath, "w") as f:
            json.dump(companies, f, indent=2)
        logger.info("Company list saved to %s", filepath)

    def load_company_list(self):
        """Load previously saved company list."""
        filepath = os.path.join(PROCESSED_DATA_DIR, "company_list.json")
        if os.path.exists(filepath):
            with open(filepath) as f:
                return json.load(f)
        return None

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
