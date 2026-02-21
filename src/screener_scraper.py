"""Scraper for Screener.in to extract financial data for Indian listed companies."""

import re
import time
import logging
import json
import os
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config import (
    SCREENER_BASE_URL,
    SCREENER_COMPANY_URL,
    SCREENER_STANDALONE_URL,
    HEADERS,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    RATE_LIMIT_DELAY,
    RAW_DATA_DIR,
    NUM_YEARS,
)

logger = logging.getLogger(__name__)


class ScraperError(Exception):
    """Custom exception for scraper errors."""
    pass


class ScreenerScraper:
    """Scrapes financial data from Screener.in company pages."""

    def __init__(self, rate_limit_delay=RATE_LIMIT_DELAY):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time = 0

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    )
    def _fetch_page(self, url):
        """Fetch a page with retry logic."""
        self._rate_limit()
        logger.debug("Fetching: %s", url)
        response = self.session.get(url, timeout=REQUEST_TIMEOUT)
        if response.status_code == 429:
            logger.warning("Rate limited, waiting 30 seconds...")
            time.sleep(30)
            raise requests.ConnectionError("Rate limited")
        response.raise_for_status()
        return response.text

    def scrape_company(self, symbol):
        """
        Scrape all financial data for a company.

        Args:
            symbol: NSE trading symbol (e.g., 'RELIANCE')

        Returns:
            dict with keys: company_info, profit_loss, balance_sheet, cash_flow,
                            is_consolidated
        """
        # Try consolidated first
        url = SCREENER_COMPANY_URL.format(symbol=symbol)
        is_consolidated = True
        try:
            html = self._fetch_page(url)
            soup = BeautifulSoup(html, "lxml")

            # Check if page has consolidated data - look for the consolidated tab
            # being active or if it redirects to standalone
            has_consolidated = self._check_consolidated(soup, html)
            if not has_consolidated:
                raise ScraperError("No consolidated data")
        except (requests.HTTPError, ScraperError) as e:
            logger.info(
                "No consolidated data for %s (%s), trying standalone", symbol, e
            )
            url = SCREENER_STANDALONE_URL.format(symbol=symbol)
            is_consolidated = False
            try:
                html = self._fetch_page(url)
                soup = BeautifulSoup(html, "lxml")
            except requests.HTTPError as e2:
                raise ScraperError(
                    f"Failed to fetch data for {symbol}: {e2}"
                ) from e2

        # Extract data
        company_info = self._extract_company_info(soup, symbol)
        company_info["is_consolidated"] = is_consolidated

        profit_loss = self._extract_table_data(soup, "profit-loss")
        balance_sheet = self._extract_table_data(soup, "balance-sheet")
        cash_flow = self._extract_table_data(soup, "cash-flow")

        # Filter to last N years
        profit_loss = self._filter_recent_years(profit_loss, NUM_YEARS)
        balance_sheet = self._filter_recent_years(balance_sheet, NUM_YEARS)
        cash_flow = self._filter_recent_years(cash_flow, NUM_YEARS)

        result = {
            "company_info": company_info,
            "profit_loss": profit_loss,
            "balance_sheet": balance_sheet,
            "cash_flow": cash_flow,
            "is_consolidated": is_consolidated,
            "source_url": url,
        }

        # Save raw data
        self._save_raw_data(symbol, result)

        return result

    def _check_consolidated(self, soup, html):
        """Check if the page contains consolidated financial data."""
        # Screener.in shows "Consolidated" or "Standalone" in the page
        # If consolidated page returns a redirect or shows standalone, it's not available
        # Look for consolidated indicator in the page
        page_text = soup.get_text()
        # If we're on the consolidated URL but the page shows "Standalone" prominently
        # or doesn't have the consolidated toggle, consolidated isn't available
        consolidated_links = soup.find_all("a", href=re.compile(r"/consolidated/"))
        standalone_links = soup.find_all("a", href=re.compile(r"(?<!/consolidated/)$"))

        # Check if we were redirected to standalone
        if "consolidated" not in html.lower() and consolidated_links:
            return True

        # If the page has financial sections, data is present
        pnl_section = soup.find("section", {"id": "profit-loss"})
        if pnl_section:
            return True

        return False

    def _extract_company_info(self, soup, symbol):
        """Extract basic company information from the page."""
        info = {
            "name": None,
            "nse_symbol": symbol,
            "bse_code": None,
            "isin": None,
            "industry": None,
            "sector": None,
            "market_cap_crores": None,
        }

        # Company name - typically in h1 or the page title
        name_tag = soup.find("h1")
        if name_tag:
            info["name"] = name_tag.get_text(strip=True)

        # Market cap and other info from the company ratios section
        # Screener.in has a top section with key ratios
        ratios_list = soup.find("ul", {"id": "top-ratios"})
        if not ratios_list:
            # Try alternative: look for the company-ratios section
            ratios_list = soup.find("div", {"id": "company-ratios"})

        if ratios_list:
            for li in ratios_list.find_all("li"):
                name_span = li.find("span", {"class": "name"})
                value_span = li.find("span", {"class": "number"})
                if name_span and value_span:
                    name = name_span.get_text(strip=True)
                    value = value_span.get_text(strip=True)
                    if "Market Cap" in name:
                        info["market_cap_crores"] = self._parse_number(value)
                    elif "Sector" in name or "Industry" in name:
                        info["industry"] = value

        # Also try to get market cap from other locations on the page
        if info["market_cap_crores"] is None:
            info["market_cap_crores"] = self._extract_market_cap_alt(soup)

        # Extract BSE code and ISIN from company links if available
        company_links = soup.find_all("a")
        for link in company_links:
            href = link.get("href", "")
            if "bseindia.com" in href:
                # Try to extract BSE code from URL
                match = re.search(r"scripcode=(\d+)", href)
                if match:
                    info["bse_code"] = match.group(1)

        return info

    def _extract_market_cap_alt(self, soup):
        """Alternative method to extract market cap from the page."""
        # Look for market cap in various page elements
        text = soup.get_text()
        # Pattern: "Market Cap ₹ XX,XXX Cr" or "Market Cap\nXX,XXX"
        match = re.search(
            r"Market\s+Cap[:\s]*[₹Rs.\s]*([\d,]+(?:\.\d+)?)\s*(?:Cr|Crores?)?",
            text,
            re.IGNORECASE,
        )
        if match:
            return self._parse_number(match.group(1))

        # Try finding it in structured elements
        for el in soup.find_all(["span", "div", "td", "li"]):
            el_text = el.get_text(strip=True)
            if "Market Cap" in el_text:
                match = re.search(r"([\d,]+(?:\.\d+)?)", el_text)
                if match:
                    val = self._parse_number(match.group(1))
                    if val and val > 100:  # Reasonable market cap minimum
                        return val
        return None

    def _extract_table_data(self, soup, section_id):
        """
        Extract financial table data from a section.

        Args:
            soup: BeautifulSoup parsed page
            section_id: HTML section ID ('profit-loss', 'balance-sheet', 'cash-flow')

        Returns:
            dict mapping fiscal year (e.g., 'Mar 2024') to dict of line items
        """
        section = soup.find("section", {"id": section_id})
        if not section:
            # Try alternative selectors
            section = soup.find("div", {"id": section_id})
        if not section:
            logger.warning("Section '%s' not found", section_id)
            return {}

        table = section.find("table")
        if not table:
            logger.warning("No table found in section '%s'", section_id)
            return {}

        # Extract headers (years)
        headers = []
        thead = table.find("thead")
        if thead:
            header_row = thead.find("tr")
            if header_row:
                for th in header_row.find_all(["th", "td"]):
                    text = th.get_text(strip=True)
                    if text and text != "":
                        headers.append(text)
        else:
            # Try first row as header
            first_row = table.find("tr")
            if first_row:
                for th in first_row.find_all(["th", "td"]):
                    text = th.get_text(strip=True)
                    if text:
                        headers.append(text)

        if not headers:
            logger.warning("No headers found in section '%s'", section_id)
            return {}

        # The first header is usually empty (row label column) or contains section title
        # Year headers look like "Mar 2022", "Mar 2023", etc.
        year_headers = []
        for h in headers:
            if re.match(r"(Mar|Jun|Sep|Dec)\s+\d{4}", h):
                year_headers.append(h)
            elif h == "TTM":
                # Skip trailing twelve months
                continue

        if not year_headers:
            logger.warning("No year headers found in section '%s'", section_id)
            return {}

        # Initialize result dict
        result = {year: {} for year in year_headers}

        # Extract rows
        tbody = table.find("tbody")
        rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]

        for row in rows:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue

            # First cell is the line item name
            line_item = cells[0].get_text(strip=True)
            if not line_item or line_item in ("", "+"):
                continue

            # Clean up the line item name:
            # - Remove trailing "+" from expandable row buttons
            # - Normalize whitespace
            line_item = re.sub(r"\s+", " ", line_item).strip()
            line_item = line_item.rstrip("+")

            # Map cell values to years
            # Need to align cells with year headers, accounting for possible
            # extra columns (like the label column and TTM column)
            value_cells = cells[1:]  # Skip the label cell

            year_idx = 0
            for cell in value_cells:
                cell_text = cell.get_text(strip=True)
                # Skip TTM column
                if year_idx >= len(year_headers):
                    break

                # Try to figure out if this cell corresponds to a year column
                # by checking the table structure
                value = self._parse_number(cell_text)
                if year_idx < len(year_headers):
                    result[year_headers[year_idx]][line_item] = value
                year_idx += 1

        return result

    def _filter_recent_years(self, data, num_years):
        """Filter data to keep only the most recent N annual (March) years.

        Screener.in may include half-year data (e.g., Sep 2025) in
        balance sheets. We only keep March fiscal year-end entries for
        annual reports.
        """
        if not data:
            return {}

        # Only keep March year-end data (annual reports)
        annual_data = {
            year: values
            for year, values in data.items()
            if year.startswith("Mar ")
        }

        if not annual_data:
            # Fall back to all data if no March entries found
            annual_data = data

        # Sort years and take the last N
        sorted_years = sorted(
            annual_data.keys(),
            key=lambda y: self._year_sort_key(y),
        )

        recent_years = sorted_years[-num_years:] if len(sorted_years) > num_years else sorted_years
        return {year: annual_data[year] for year in recent_years}

    def _year_sort_key(self, year_str):
        """Convert year string like 'Mar 2024' to a sortable value."""
        month_map = {"Mar": 3, "Jun": 6, "Sep": 9, "Dec": 12}
        parts = year_str.split()
        if len(parts) == 2:
            month = month_map.get(parts[0], 0)
            try:
                year = int(parts[1])
                return year * 100 + month
            except ValueError:
                pass
        return 0

    def _parse_number(self, text):
        """Parse a number string from Screener.in format.

        Handles Indian number formatting (e.g., '7,21,634') and
        preserves decimal points.
        """
        if not text or text.strip() in ("", "-", "—", "N/A", "NA"):
            return None

        cleaned = text.strip()
        # Remove currency symbols, percentage signs, and spaces
        cleaned = re.sub(r"[₹%]", "", cleaned)
        cleaned = re.sub(r"Rs\.?\s*", "", cleaned)
        # Remove commas (Indian number format: 7,21,634)
        cleaned = cleaned.replace(",", "")
        cleaned = cleaned.strip()

        if not cleaned or cleaned == "-":
            return None

        try:
            return float(cleaned)
        except ValueError:
            return None

    def _save_raw_data(self, symbol, data):
        """Save raw scraped data as JSON for audit trail."""
        os.makedirs(RAW_DATA_DIR, exist_ok=True)
        filepath = os.path.join(RAW_DATA_DIR, f"{symbol}.json")
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)
        logger.debug("Raw data saved to %s", filepath)

    def get_company_list_page(self, query="Market Capitalization > 5000", page=1):
        """
        Fetch a page of company results from Screener.in query.

        Note: This may require authentication for full results.
        Falls back to scraping individual pages if query access is limited.
        """
        url = f"{SCREENER_BASE_URL}/screen/raw/"
        params = {
            "sort": "market capitalization",
            "order": "desc",
            "query": query,
            "page": page,
        }
        try:
            html = self._fetch_page(f"{url}?{'&'.join(f'{k}={v}' for k, v in params.items())}")
            soup = BeautifulSoup(html, "lxml")
            return self._parse_company_list(soup)
        except Exception as e:
            logger.error("Failed to fetch company list page %d: %s", page, e)
            return [], False

    def _parse_company_list(self, soup):
        """Parse company list from Screener.in screen results page."""
        companies = []

        # Find the results table
        table = soup.find("table", {"class": "data-table"})
        if not table:
            table = soup.find("table")

        if not table:
            return companies, False

        tbody = table.find("tbody")
        if not tbody:
            return companies, False

        for row in tbody.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) >= 2:
                link = cells[0].find("a")
                if link:
                    name = link.get_text(strip=True)
                    href = link.get("href", "")
                    symbol_match = re.search(r"/company/([^/]+)/", href)
                    symbol = symbol_match.group(1) if symbol_match else None
                    if symbol:
                        companies.append({"name": name, "symbol": symbol})

        # Check if there's a next page
        has_next = bool(soup.find("a", {"class": "ink-900"}, string=re.compile(r"Next|»")))
        if not has_next:
            # Also check for pagination links
            pagination = soup.find("div", {"class": "pagination"})
            if pagination:
                next_link = pagination.find("a", string=re.compile(r"Next|›|»"))
                has_next = bool(next_link)

        return companies, has_next

    def close(self):
        """Close the session."""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
