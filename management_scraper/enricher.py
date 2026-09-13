"""Director background enrichment via web search and page scraping.

For each Key Management Personnel (CMD, MD, CEO, CFO, etc.), searches the
web and company annual reports to gather:
  - Educational qualifications (university, degree)
  - Previous companies / roles
  - Career summary
  - DIN (Director Identification Number)

Sources checked:
  1. Company annual report pages (ril.com, tcs.com, etc.)
  2. Screener.in company about sections
  3. BlinkX director profile pages
"""

import re
import time
import logging
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}
REQUEST_TIMEOUT = 15


def _extract_din(text: str) -> Optional[str]:
    """Extract DIN (8-digit number) from text."""
    m = re.search(r"DIN[:\s]*(\d{8})", text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _extract_qualifications(text: str) -> Optional[str]:
    """Extract educational qualifications from text."""
    quals = []
    patterns = [
        r"(?:B\.?Tech|B\.?E\.?|Bachelor(?:'s)?\s+(?:of\s+)?(?:Engineering|Technology|Science|Arts|Commerce))[^.]*",
        r"(?:M\.?Tech|M\.?E\.?|M\.?B\.?A\.?|Master(?:'s)?)[^.]*",
        r"(?:Ph\.?D\.?|Doctorate|Doctor of)[^.]*",
        r"(?:C\.?A\.?|Chartered Accountant|Company Secretary|C\.?S\.?|ICWA|CMA)[^.]*",
        r"(?:from|at|of)\s+(?:IIT|IIM|Stanford|Harvard|MIT|Wharton|INSEAD|London Business|Oxford|Cambridge|ISB|XLRI|IIMA|IIMB|IIMC)[^.]*",
        r"(?:mechanical|chemical|electrical|civil|computer)\s+engineer[^.]*",
        r"(?:Post[- ]?Gradu(?:ate|ation)|PG\s+Diploma)[^.]*",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            cleaned = match.strip().rstrip(",;. ")
            if cleaned and len(cleaned) > 5 and cleaned not in quals:
                quals.append(cleaned)

    return "; ".join(quals[:5]) if quals else None


def _extract_experience(text: str, person_name: str) -> Optional[str]:
    """Extract career experience summary from text."""
    # Look for sentences mentioning the person's career
    parts = person_name.split()
    surname = parts[-1] if parts else person_name

    sentences = re.split(r"[.!?]\s+", text)
    relevant = []
    keywords = [
        "experience", "career", "worked", "served", "joined",
        "appointed", "founded", "managing", "director", "chairman",
        "president", "ceo", "headed", "led", "responsible",
        "previously", "former", "prior", surname.lower(),
    ]

    for sent in sentences:
        if any(kw in sent.lower() for kw in keywords) and len(sent) > 30:
            cleaned = sent.strip()
            if len(cleaned) < 500:
                relevant.append(cleaned)

    return ". ".join(relevant[:5]) + "." if relevant else None


def _extract_previous_companies(text: str) -> Optional[str]:
    """Extract previous companies/organizations from text."""
    companies = set()
    patterns = [
        r"(?:former(?:ly)?|previously|ex-?|worked at|served at|joined)\s+(?:at\s+)?([A-Z][A-Za-z &]+(?:Ltd|Limited|Inc|Corp|Bank|Group|Company))",
        r"(?:Chairman|MD|CEO|Director|Head|President)\s+(?:of\s+)?([A-Z][A-Za-z &]+(?:Ltd|Limited|Inc|Corp|Bank|Group))",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            cleaned = match.strip().rstrip(",;. ")
            if cleaned and len(cleaned) > 3:
                companies.add(cleaned)

    return "; ".join(sorted(companies)[:10]) if companies else None


def enrich_from_screener(nse_symbol: str) -> Optional[str]:
    """Fetch company about/description from Screener.in.

    Returns the about text which may contain management info.
    """
    url = f"https://www.screener.in/company/{nse_symbol}/consolidated/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # Look for the about section
        about_section = soup.find("div", class_="about")
        if not about_section:
            about_section = soup.find("div", {"id": "company-profile"})
        if not about_section:
            # Try to find any section with company description
            for div in soup.find_all("div", class_="sub"):
                text = div.get_text(strip=True)
                if "incorporated" in text.lower() or "founded" in text.lower():
                    return text[:2000]

        if about_section:
            return about_section.get_text(strip=True)[:2000]

        return None
    except requests.RequestException:
        return None


def enrich_director(person_name: str, company_name: str,
                    company_about: str = None) -> Dict:
    """Enrich a director's profile with available information.

    Args:
        person_name: Director's name
        company_name: Company they serve on
        company_about: Pre-fetched company about text

    Returns:
        dict with qualification, experience_summary, previous_companies, din
    """
    result = {
        "qualification": None,
        "experience_summary": None,
        "previous_companies": None,
        "din": None,
    }

    # Source 1: Extract from company about text
    if company_about:
        result["qualification"] = _extract_qualifications(company_about)
        result["experience_summary"] = _extract_experience(company_about, person_name)
        result["previous_companies"] = _extract_previous_companies(company_about)
        result["din"] = _extract_din(company_about)

    return result


def enrich_from_blinkx_profile(name_id: str) -> Optional[Dict]:
    """Fetch individual director profile from BlinkX if available.

    BlinkX has director profile pages at:
    https://blinkx.in/insights/bod/{name_id}
    """
    if not name_id:
        return None

    url = f"https://blinkx.in/insights/bod/{name_id}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        return {
            "qualification": _extract_qualifications(text),
            "experience_summary": _extract_experience(text, name_id.replace("-", " ")),
            "din": _extract_din(text),
        }
    except requests.RequestException:
        return None
