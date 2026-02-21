"""Tests for the Screener.in scraper module."""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from src.screener_scraper import ScreenerScraper, ScraperError


# Sample HTML mimicking Screener.in's financial data structure
SAMPLE_COMPANY_HTML = """
<html>
<head><title>Reliance Industries - Financial Statements</title></head>
<body>
<h1>Reliance Industries</h1>

<div id="company-info">
    <ul id="top-ratios">
        <li>
            <span class="name">Market Cap</span>
            <span class="number">17,50,000</span>
        </li>
        <li>
            <span class="name">Current Price</span>
            <span class="number">1,290</span>
        </li>
        <li>
            <span class="name">Industry</span>
            <span class="number">Refineries</span>
        </li>
    </ul>
</div>

<a href="https://www.bseindia.com/stock-share-price/x/y/scripcode=500325">BSE</a>

<section id="profit-loss">
<h2>Profit & Loss</h2>
<table>
<thead>
<tr>
    <th></th>
    <th>Mar 2022</th>
    <th>Mar 2023</th>
    <th>Mar 2024</th>
    <th>TTM</th>
</tr>
</thead>
<tbody>
<tr><td>Sales</td><td>7,21,634</td><td>8,87,112</td><td>9,01,064</td><td>9,50,000</td></tr>
<tr><td>Expenses</td><td>5,94,130</td><td>7,24,293</td><td>7,32,803</td><td>7,60,000</td></tr>
<tr><td>Operating Profit</td><td>1,27,504</td><td>1,62,819</td><td>1,68,261</td><td>1,90,000</td></tr>
<tr><td>OPM %</td><td>17.67</td><td>18.35</td><td>18.67</td><td>20.00</td></tr>
<tr><td>Other Income</td><td>13,642</td><td>15,774</td><td>19,376</td><td>20,000</td></tr>
<tr><td>Interest</td><td>16,568</td><td>19,077</td><td>21,195</td><td>22,000</td></tr>
<tr><td>Depreciation</td><td>24,876</td><td>28,879</td><td>33,153</td><td>35,000</td></tr>
<tr><td>Profit before tax</td><td>99,702</td><td>1,30,637</td><td>1,33,289</td><td>1,53,000</td></tr>
<tr><td>Tax %</td><td>24.5</td><td>25.1</td><td>25.3</td><td>25.0</td></tr>
<tr><td>Net Profit</td><td>67,845</td><td>73,670</td><td>69,621</td><td>79,000</td></tr>
<tr><td>EPS in Rs</td><td>100.2</td><td>108.8</td><td>102.94</td><td>116.0</td></tr>
<tr><td>Dividend Payout %</td><td>8.00</td><td>8.23</td><td>8.74</td><td>9.00</td></tr>
</tbody>
</table>
</section>

<section id="balance-sheet">
<h2>Balance Sheet</h2>
<table>
<thead>
<tr>
    <th></th>
    <th>Mar 2022</th>
    <th>Mar 2023</th>
    <th>Mar 2024</th>
</tr>
</thead>
<tbody>
<tr><td>Equity Capital</td><td>6,765</td><td>6,766</td><td>6,766</td></tr>
<tr><td>Reserves</td><td>4,30,000</td><td>4,65,000</td><td>4,98,000</td></tr>
<tr><td>Borrowings</td><td>2,80,000</td><td>2,95,000</td><td>3,10,000</td></tr>
<tr><td>Other Liabilities</td><td>2,70,000</td><td>2,80,000</td><td>2,90,000</td></tr>
<tr><td>Total Liabilities</td><td>9,86,765</td><td>10,46,766</td><td>11,04,766</td></tr>
<tr><td>Fixed Assets</td><td>4,30,000</td><td>4,55,000</td><td>4,80,000</td></tr>
<tr><td>CWIP</td><td>1,00,000</td><td>1,10,000</td><td>1,20,000</td></tr>
<tr><td>Investments</td><td>2,40,000</td><td>2,60,000</td><td>2,80,000</td></tr>
<tr><td>Other Assets</td><td>2,16,765</td><td>2,21,766</td><td>2,24,766</td></tr>
<tr><td>Total Assets</td><td>9,86,765</td><td>10,46,766</td><td>11,04,766</td></tr>
</tbody>
</table>
</section>

<section id="cash-flow">
<h2>Cash Flow</h2>
<table>
<thead>
<tr>
    <th></th>
    <th>Mar 2022</th>
    <th>Mar 2023</th>
    <th>Mar 2024</th>
</tr>
</thead>
<tbody>
<tr><td>Cash from Operating Activity</td><td>75,000</td><td>80,000</td><td>85,000</td></tr>
<tr><td>Cash from Investing Activity</td><td>-55,000</td><td>-60,000</td><td>-65,000</td></tr>
<tr><td>Cash from Financing Activity</td><td>-15,000</td><td>-17,000</td><td>-18,000</td></tr>
<tr><td>Net Cash Flow</td><td>5,000</td><td>3,000</td><td>2,000</td></tr>
</tbody>
</table>
</section>

</body>
</html>
"""

# HTML for a page with no consolidated data
STANDALONE_HTML = SAMPLE_COMPANY_HTML.replace("consolidated", "standalone")

# HTML with minimal data (some sections missing)
MINIMAL_HTML = """
<html>
<head><title>Small Company</title></head>
<body>
<h1>Small Company Ltd</h1>
<section id="profit-loss">
<table>
<thead><tr><th></th><th>Mar 2024</th></tr></thead>
<tbody>
<tr><td>Sales</td><td>500</td></tr>
<tr><td>Net Profit</td><td>50</td></tr>
</tbody>
</table>
</section>
</body>
</html>
"""


@pytest.fixture
def scraper():
    s = ScreenerScraper(rate_limit_delay=0)
    yield s
    s.close()


class TestNumberParsing:
    def test_parse_integer(self, scraper):
        assert scraper._parse_number("1234") == 1234.0

    def test_parse_with_commas(self, scraper):
        assert scraper._parse_number("7,21,634") == 721634.0

    def test_parse_decimal(self, scraper):
        assert scraper._parse_number("17.67") == 17.67

    def test_parse_negative(self, scraper):
        assert scraper._parse_number("-55,000") == -55000.0

    def test_parse_with_currency(self, scraper):
        assert scraper._parse_number("₹1,290") == 1290.0

    def test_parse_empty(self, scraper):
        assert scraper._parse_number("") is None

    def test_parse_dash(self, scraper):
        assert scraper._parse_number("-") is None

    def test_parse_na(self, scraper):
        assert scraper._parse_number("N/A") is None

    def test_parse_none(self, scraper):
        assert scraper._parse_number(None) is None

    def test_parse_with_percentage(self, scraper):
        assert scraper._parse_number("24.5%") == 24.5


class TestYearSorting:
    def test_sort_key(self, scraper):
        assert scraper._year_sort_key("Mar 2024") == 202403
        assert scraper._year_sort_key("Mar 2023") == 202303
        assert scraper._year_sort_key("Sep 2024") == 202409

    def test_sort_order(self, scraper):
        years = ["Mar 2024", "Mar 2022", "Mar 2023"]
        sorted_years = sorted(years, key=scraper._year_sort_key)
        assert sorted_years == ["Mar 2022", "Mar 2023", "Mar 2024"]


class TestTableExtraction:
    def test_extract_pnl_data(self, scraper):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(SAMPLE_COMPANY_HTML, "lxml")
        data = scraper._extract_table_data(soup, "profit-loss")

        assert "Mar 2022" in data
        assert "Mar 2023" in data
        assert "Mar 2024" in data

        # TTM should be excluded
        assert "TTM" not in data

        # Check specific values
        assert data["Mar 2024"].get("Sales") == 901064.0
        assert data["Mar 2024"].get("Net Profit") == 69621.0
        assert data["Mar 2022"].get("OPM %") == 17.67

    def test_extract_balance_sheet_data(self, scraper):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(SAMPLE_COMPANY_HTML, "lxml")
        data = scraper._extract_table_data(soup, "balance-sheet")

        assert "Mar 2024" in data
        assert data["Mar 2024"].get("Total Assets") == 1104766.0
        assert data["Mar 2024"].get("Total Liabilities") == 1104766.0
        assert data["Mar 2024"].get("Equity Capital") == 6766.0

    def test_extract_cash_flow_data(self, scraper):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(SAMPLE_COMPANY_HTML, "lxml")
        data = scraper._extract_table_data(soup, "cash-flow")

        assert "Mar 2024" in data
        assert data["Mar 2024"].get("Cash from Operating Activity") == 85000.0
        assert data["Mar 2024"].get("Cash from Investing Activity") == -65000.0
        assert data["Mar 2024"].get("Net Cash Flow") == 2000.0

    def test_extract_missing_section(self, scraper):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(MINIMAL_HTML, "lxml")
        data = scraper._extract_table_data(soup, "balance-sheet")
        assert data == {}

    def test_extract_minimal_data(self, scraper):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(MINIMAL_HTML, "lxml")
        data = scraper._extract_table_data(soup, "profit-loss")
        assert "Mar 2024" in data
        assert data["Mar 2024"].get("Sales") == 500.0


class TestCompanyInfoExtraction:
    def test_extract_company_info(self, scraper):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(SAMPLE_COMPANY_HTML, "lxml")
        info = scraper._extract_company_info(soup, "RELIANCE")

        assert info["name"] == "Reliance Industries"
        assert info["nse_symbol"] == "RELIANCE"
        assert info["market_cap_crores"] == 1750000.0
        assert info["bse_code"] == "500325"

    def test_extract_industry(self, scraper):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(SAMPLE_COMPANY_HTML, "lxml")
        info = scraper._extract_company_info(soup, "RELIANCE")
        assert info["industry"] == "Refineries"


class TestFilterRecentYears:
    def test_filter_3_years(self, scraper):
        data = {
            "Mar 2021": {"Sales": 100},
            "Mar 2022": {"Sales": 200},
            "Mar 2023": {"Sales": 300},
            "Mar 2024": {"Sales": 400},
        }
        filtered = scraper._filter_recent_years(data, 3)
        assert len(filtered) == 3
        assert "Mar 2021" not in filtered
        assert "Mar 2024" in filtered

    def test_filter_with_fewer_years(self, scraper):
        data = {
            "Mar 2023": {"Sales": 300},
            "Mar 2024": {"Sales": 400},
        }
        filtered = scraper._filter_recent_years(data, 3)
        assert len(filtered) == 2

    def test_filter_empty(self, scraper):
        filtered = scraper._filter_recent_years({}, 3)
        assert filtered == {}


class TestScrapeCompany:
    @patch.object(ScreenerScraper, "_fetch_page")
    def test_scrape_company_consolidated(self, mock_fetch, scraper):
        mock_fetch.return_value = SAMPLE_COMPANY_HTML

        with patch.object(scraper, "_save_raw_data"):
            result = scraper.scrape_company("RELIANCE")

        assert result["is_consolidated"] is True
        assert result["company_info"]["name"] == "Reliance Industries"
        assert len(result["profit_loss"]) == 3
        assert len(result["balance_sheet"]) == 3
        assert len(result["cash_flow"]) == 3

    @patch.object(ScreenerScraper, "_fetch_page")
    def test_scrape_company_fallback_to_standalone(self, mock_fetch, scraper):
        # First call (consolidated) fails, second call (standalone) succeeds
        import requests

        mock_fetch.side_effect = [
            requests.HTTPError("404"),
            SAMPLE_COMPANY_HTML,
        ]

        with patch.object(scraper, "_save_raw_data"):
            result = scraper.scrape_company("SMALLCO")

        assert result["is_consolidated"] is False

    @patch.object(ScreenerScraper, "_fetch_page")
    def test_scrape_company_both_fail(self, mock_fetch, scraper):
        import requests

        mock_fetch.side_effect = requests.HTTPError("404")

        with pytest.raises(ScraperError):
            scraper.scrape_company("INVALID")
