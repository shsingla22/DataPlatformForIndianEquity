"""Refresh market cap data from Screener.in for all companies in the database.

Uses the same scraping pattern as the main pipeline but only fetches market cap,
making it much faster. This ensures dividend yield calculations use current prices.

Usage:
    python -m dividend_screener.refresh_market_cap          # refresh all
    python -m dividend_screener.refresh_market_cap --limit 5 # test with 5
"""

import logging
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

DB_PATH = str(Path(__file__).parent.parent / "data" / "financial_profiles.db")

SCREENER_URL = "https://www.screener.in/company/{symbol}/consolidated/"
SCREENER_STANDALONE_URL = "https://www.screener.in/company/{symbol}/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

RATE_LIMIT_DELAY = 2.0  # seconds between requests


def _parse_number(text: str) -> Optional[float]:
    """Parse Indian-format number string (e.g. '7,21,634.50')."""
    if not text or text.strip() in ("", "-", "—", "N/A", "NA"):
        return None
    cleaned = re.sub(r"[₹%]", "", text.strip())
    cleaned = re.sub(r"Rs\.?\s*", "", cleaned)
    cleaned = cleaned.replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


class MarketCapRefresher:
    """Fetches current market cap from Screener.in for database companies."""

    def __init__(self, db_path: str = DB_PATH, rate_limit: float = RATE_LIMIT_DELAY):
        self.db_path = db_path
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.rate_limit = rate_limit
        self._last_req = 0.0

    def _wait(self):
        elapsed = time.time() - self._last_req
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_req = time.time()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    )
    def _fetch(self, url: str) -> requests.Response:
        self._wait()
        resp = self.session.get(url, timeout=30)
        if resp.status_code == 429:
            logger.warning("Rate limited, waiting 30s...")
            time.sleep(30)
            resp = self.session.get(url, timeout=30)
        return resp

    def _extract_market_cap(self, html: str) -> Optional[float]:
        """Extract market cap from Screener.in HTML page."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        # Method 1: structured ratios list
        ratios = soup.find("ul", {"id": "top-ratios"})
        if not ratios:
            ratios = soup.find("div", {"id": "company-ratios"})

        if ratios:
            for li in ratios.find_all("li"):
                name_span = li.find("span", {"class": "name"})
                value_span = li.find("span", {"class": "number"})
                if name_span and value_span:
                    if "Market Cap" in name_span.get_text(strip=True):
                        val = _parse_number(value_span.get_text(strip=True))
                        if val and val > 100:
                            return val

        # Method 2: regex fallback on full page text
        text = soup.get_text()
        match = re.search(
            r"Market\s+Cap[:\s]*[₹Rs.\s]*([\d,]+(?:\.\d+)?)\s*(?:Cr|Crores?)?",
            text,
            re.IGNORECASE,
        )
        if match:
            val = _parse_number(match.group(1))
            if val and val > 100:
                return val

        # Method 3: scan structured elements
        for el in soup.find_all(["span", "div", "td", "li"]):
            el_text = el.get_text(strip=True)
            if "Market Cap" in el_text:
                m = re.search(r"([\d,]+(?:\.\d+)?)", el_text)
                if m:
                    val = _parse_number(m.group(1))
                    if val and val > 100:
                        return val

        return None

    def fetch_market_cap(self, symbol: str) -> Optional[float]:
        """Fetch current market cap for a single NSE symbol."""
        # Try consolidated first, then standalone
        for url_tmpl in [SCREENER_URL, SCREENER_STANDALONE_URL]:
            url = url_tmpl.format(symbol=symbol)
            try:
                resp = self._fetch(url)
                if resp.status_code == 200:
                    mcap = self._extract_market_cap(resp.text)
                    if mcap:
                        return mcap
                elif resp.status_code == 404:
                    continue
                else:
                    logger.warning("%s: HTTP %d", symbol, resp.status_code)
            except Exception as e:
                logger.warning("%s: %s", symbol, e)

        return None

    def refresh_all(self, limit: int = 0) -> dict:
        """Refresh market cap for all companies in the database.

        Returns dict with counts: updated, failed, skipped, total.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        query = "SELECT id, nse_symbol, market_cap_crores FROM companies WHERE nse_symbol IS NOT NULL"
        if limit > 0:
            query += f" LIMIT {limit}"
        companies = conn.execute(query).fetchall()

        stats = {"total": len(companies), "updated": 0, "unchanged": 0, "failed": 0}

        for i, company in enumerate(companies, 1):
            symbol = company["nse_symbol"]
            old_mcap = company["market_cap_crores"] or 0

            new_mcap = self.fetch_market_cap(symbol)

            if new_mcap is None:
                stats["failed"] += 1
                logger.warning("[%d/%d] %s: FAILED to fetch market cap",
                               i, stats["total"], symbol)
                continue

            pct_change = ((new_mcap - old_mcap) / old_mcap * 100) if old_mcap > 0 else 0

            conn.execute(
                "UPDATE companies SET market_cap_crores = ? WHERE id = ?",
                (new_mcap, company["id"]),
            )
            conn.commit()

            if abs(pct_change) > 0.1:
                stats["updated"] += 1
                logger.info(
                    "[%d/%d] %s: %.0f -> %.0f Cr (%+.1f%%)",
                    i, stats["total"], symbol, old_mcap, new_mcap, pct_change,
                )
            else:
                stats["unchanged"] += 1

        conn.close()
        return stats


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Refresh market cap from Screener.in")
    parser.add_argument("--db", default=DB_PATH, help="Database path")
    parser.add_argument("--limit", type=int, default=0, help="Limit companies (0=all)")
    parser.add_argument("--symbol", type=str, default=None, help="Refresh single symbol")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    refresher = MarketCapRefresher(db_path=args.db)

    if args.symbol:
        mcap = refresher.fetch_market_cap(args.symbol)
        if mcap:
            print(f"{args.symbol}: {mcap:,.0f} Cr")
            conn = sqlite3.connect(args.db)
            conn.execute(
                "UPDATE companies SET market_cap_crores = ? WHERE nse_symbol = ?",
                (mcap, args.symbol),
            )
            conn.commit()
            conn.close()
            print("Updated in database.")
        else:
            print(f"{args.symbol}: Failed to fetch", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"Refreshing market caps from Screener.in...")
        stats = refresher.refresh_all(limit=args.limit)
        print(f"\nDone: {stats['updated']} updated, {stats['unchanged']} unchanged, "
              f"{stats['failed']} failed out of {stats['total']} companies")


if __name__ == "__main__":
    main()
