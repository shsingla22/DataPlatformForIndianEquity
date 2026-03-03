"""BlinkX Board of Directors scraper.

BlinkX (blinkx.in) provides structured board of directors data via
Next.js server-side rendering. Data is embedded in __NEXT_DATA__ JSON
within the HTML, giving us:
  - Board table: name, designation, name_id
  - Year options: [2025, 2024, 2023, 2022] for historical data
  - Key Highlights: Text describing each director's status
    (continues/joins/redesignated) with year-over-year tracking

URL pattern: https://blinkx.in/insights/bod/{slug}-board-of-directors
where slug = company_name.lower().replace(' ', '-')
"""

import json
import re
import time
import logging
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BLINKX_BASE = "https://blinkx.in/insights/bod"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
RATE_LIMIT = 3.0  # seconds between requests
REQUEST_TIMEOUT = 20


def _slugify(company_name: str) -> str:
    """Convert company name to BlinkX URL slug.

    Examples:
        'Reliance Industries Ltd' -> 'reliance-industries-ltd'
        'HDFC Bank Ltd' -> 'hdfc-bank-ltd'
        '360 ONE WAM Ltd' -> '360-one-wam-ltd'
    """
    slug = company_name.lower().strip()
    # Remove special characters except spaces and hyphens
    slug = re.sub(r"[^\w\s-]", "", slug)
    # Replace whitespace with hyphens
    slug = re.sub(r"\s+", "-", slug)
    # Remove consecutive hyphens
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def _categorize_designation(designation: str) -> str:
    """Categorize a designation into standard director categories."""
    d = designation.lower() if designation else ""
    if "independent" in d:
        return "Independent"
    if "chairman" in d and "managing" in d:
        return "Executive"
    if "managing director" in d or "whole time" in d or "executive director" in d:
        return "Executive"
    if "non-exec" in d or "non exec" in d:
        return "Non-Executive"
    if any(kw in d for kw in ["ceo", "cfo", "coo", "company sec", "chief"]):
        return "Executive"
    if "nominee" in d:
        return "Nominee"
    return "Other"


def _is_kmp(designation: str) -> bool:
    """Check if designation indicates Key Management Personnel per Companies Act 2013."""
    d = designation.lower() if designation else ""
    return any(kw in d for kw in [
        "chairman", "managing director", "ceo", "cfo", "coo",
        "whole time", "company sec", "chief financial",
        "chief executive",
    ])


def _parse_key_highlights(text: str) -> List[Dict]:
    """Parse Key Highlights text to extract all directors with status.

    The text uses 'a1#' as separator between director entries.
    Each entry is like:
        'Mukesh D Ambani continues to serve as the Chairman & Managing
         Director in 2025, maintaining the same position as in the
         previous year.'
    or:
        'Hital R Meswani joins the board as Whole Time Director, in a
         new position in 2025.'
    """
    if not text:
        return []

    entries = text.split("a1#")
    directors = []

    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue

        # Extract person name (text before "continues" or "joins" or "was")
        name = None
        designation = None
        status = "unknown"

        # Pattern: "{Name} continues to serve as the {Designation}"
        m = re.match(
            r"^(.+?)\s+continues\s+to\s+serve\s+as\s+(?:the\s+)?(.+?)\s+in\s+(\d{4})",
            entry, re.IGNORECASE
        )
        if m:
            name = m.group(1).strip()
            designation = m.group(2).strip().rstrip(",. ")
            status = "continues"

        # Pattern: "{Name} joins the board as {Designation}"
        if not name:
            m = re.match(
                r"^(.+?)\s+joins\s+the\s+board\s+as\s+(.+?)(?:,|\s+in\s+)",
                entry, re.IGNORECASE
            )
            if m:
                name = m.group(1).strip()
                designation = m.group(2).strip().rstrip(",. ")
                status = "new_appointment"

        # Pattern: "{Name} was previously ... and has been redesignated"
        if not name:
            m = re.match(
                r"^(.+?)\s+(?:was|has been)\s+(?:previously|redesignated|appointed)",
                entry, re.IGNORECASE
            )
            if m:
                name = m.group(1).strip()
                status = "redesignated"
                # Try to extract new designation
                dm = re.search(r"(?:redesignated|appointed)\s+as\s+(.+?)(?:\.|,|$)",
                               entry, re.IGNORECASE)
                if dm:
                    designation = dm.group(1).strip()

        # Pattern: "{Name} is no longer on the board" / "departed"
        if not name:
            m = re.match(
                r"^(.+?)\s+(?:is no longer|departed|resigned|retired|left)",
                entry, re.IGNORECASE
            )
            if m:
                name = m.group(1).strip()
                status = "departed"

        if name:
            # Clean up name
            name = re.sub(r"\s+", " ", name).strip()
            directors.append({
                "person_name": name,
                "designation": designation,
                "change_status": status,
            })

    return directors


def scrape_company_bod(company_name: str, nse_symbol: str = None) -> Optional[Dict]:
    """Scrape board of directors data for a company from BlinkX.

    Returns dict with:
        - directors: list of dicts with name, designation, category
        - key_highlights: parsed director change info
        - year_options: available years [2025, 2024, ...]
        - source_url: the URL scraped
    or None if scraping fails.
    """
    slug = _slugify(company_name)
    url = f"{BLINKX_BASE}/{slug}-board-of-directors"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            logger.warning(
                f"BlinkX returned {resp.status_code} for {nse_symbol or company_name} "
                f"(URL: {url})"
            )
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        next_data = soup.find("script", {"id": "__NEXT_DATA__"})
        if not next_data:
            logger.warning(f"No __NEXT_DATA__ found for {nse_symbol or company_name}")
            return None

        data = json.loads(next_data.get_text())
        api_data = data.get("props", {}).get("pageProps", {}).get("apiData", {})
        response = api_data.get("response", {})
        results = response.get("result", [])

        directors_table = []
        key_highlights_text = ""
        year_options = []

        for r in results:
            if not isinstance(r, dict):
                continue

            # Board table (tableBOD rendering)
            if r.get("suggested_rendering") == "tableBOD":
                rows = r.get("metric_data", {}).get("rows", [])
                year_options = r.get("options", [])
                for row in rows:
                    name = row.get("name", "").strip()
                    desig = row.get("designation", "").strip()
                    if name:
                        directors_table.append({
                            "person_name": name,
                            "designation": desig,
                            "director_category": _categorize_designation(desig),
                            "is_kmp": _is_kmp(desig),
                            "source": "blinkx_table",
                        })

            # Key Highlights text
            if r.get("title") == "Key Highlights":
                key_highlights_text = r.get("text", "")

        # Parse key highlights for full director roster
        highlights_directors = _parse_key_highlights(key_highlights_text)

        # Merge: key highlights have ALL directors, table may only show new/changed
        all_directors = {}

        # First add from key highlights (more complete)
        for d in highlights_directors:
            name = d["person_name"]
            all_directors[name.upper()] = {
                "person_name": name,
                "designation": d.get("designation"),
                "director_category": _categorize_designation(d.get("designation", "")),
                "is_kmp": _is_kmp(d.get("designation", "")),
                "change_status": d.get("change_status", "unknown"),
                "source": "blinkx_highlights",
            }

        # Then overlay/add from table (more accurate designations)
        for d in directors_table:
            key = d["person_name"].upper()
            if key in all_directors:
                # Update designation from table (more precise)
                if d["designation"]:
                    all_directors[key]["designation"] = d["designation"]
                    all_directors[key]["director_category"] = d["director_category"]
                    all_directors[key]["is_kmp"] = d["is_kmp"]
                all_directors[key]["source"] = "blinkx_table"
            else:
                d["change_status"] = "unknown"
                all_directors[key] = d

        return {
            "directors": list(all_directors.values()),
            "year_options": year_options,
            "source_url": url,
            "key_highlights_raw": key_highlights_text,
        }

    except requests.RequestException as e:
        logger.error(f"Request failed for {nse_symbol or company_name}: {e}")
        return None
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Parse error for {nse_symbol or company_name}: {e}")
        return None


def scrape_batch(companies: List[Dict], rate_limit: float = RATE_LIMIT) -> List[Tuple[Dict, Optional[Dict]]]:
    """Scrape BOD data for a batch of companies.

    Args:
        companies: list of dicts with 'name' and 'nse_symbol'
        rate_limit: seconds between requests

    Returns:
        list of (company, bod_data) tuples
    """
    results = []
    total = len(companies)

    for i, company in enumerate(companies):
        name = company.get("name", "")
        symbol = company.get("nse_symbol", "")

        if i > 0:
            time.sleep(rate_limit)

        logger.info(f"[{i+1}/{total}] Scraping {symbol} ({name})")
        bod_data = scrape_company_bod(name, symbol)

        if bod_data:
            n_directors = len(bod_data["directors"])
            logger.info(f"  Found {n_directors} directors")
        else:
            logger.info(f"  No data found")

        results.append((company, bod_data))

    return results
