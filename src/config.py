"""Configuration constants for the financial data platform."""

import os

# Project paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_DATA_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DATA_DIR = os.path.join(DATA_DIR, "processed")
EXPORTS_DIR = os.path.join(DATA_DIR, "exports")
DB_PATH = os.path.join(DATA_DIR, "financial_profiles.db")

# Market cap filter (in crores INR)
MIN_MARKET_CAP_CRORES = 1000

# Number of years of financial data to fetch
NUM_YEARS = 3

# Screener.in configuration
SCREENER_BASE_URL = "https://www.screener.in"
SCREENER_COMPANY_URL = SCREENER_BASE_URL + "/company/{symbol}/consolidated/"
SCREENER_STANDALONE_URL = SCREENER_BASE_URL + "/company/{symbol}/"

# BSE API configuration
BSE_API_BASE = "https://api.bseindia.com/BseIndiaAPI/api"
BSE_STOCK_REACH = BSE_API_BASE + "/GetStockReachGraph/w"

# NSE configuration
NSE_BASE_URL = "https://www.nseindia.com"
NSE_EQUITY_LIST_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
NSE_MARKET_STATUS_URL = NSE_BASE_URL + "/api/marketStatus"

# HTTP settings
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds
RATE_LIMIT_DELAY = 2.0  # seconds between requests

# User agent for requests
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# Profit & Loss statement line items (as they appear on Screener.in)
PNL_LINE_ITEMS = [
    "Sales",
    "Expenses",
    "Operating Profit",
    "OPM %",
    "Other Income",
    "Interest",
    "Depreciation",
    "Profit before tax",
    "Tax %",
    "Net Profit",
    "EPS in Rs",
    "Dividend Payout %",
]

# Balance Sheet line items
BS_LINE_ITEMS = [
    "Equity Capital",
    "Reserves",
    "Borrowings",
    "Other Liabilities",
    "Total Liabilities",
    "Fixed Assets",
    "CWIP",
    "Investments",
    "Other Assets",
    "Total Assets",
]

# Cash Flow line items
CF_LINE_ITEMS = [
    "Cash from Operating Activity",
    "Cash from Investing Activity",
    "Cash from Financing Activity",
    "Net Cash Flow",
]

# Logging
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = os.path.join(BASE_DIR, "pipeline.log")
