# DataPlatformForIndianEquity

Creates, stores and refreshes financial profile data for listed companies in India (NSE & BSE) with market capitalization > 5,000 crore INR.

## What This Does

Collects last 3 years of **annual consolidated** financial statements for qualifying companies:
- **Profit & Loss Statement** — Sales, Expenses, Operating Profit, OPM%, Other Income, Interest, Depreciation, PBT, Tax%, Net Profit, EPS, Dividend Payout%
- **Balance Sheet** — Equity Capital, Reserves, Borrowings, Other Liabilities, Total Liabilities, Fixed Assets, CWIP, Investments, Other Assets, Total Assets
- **Cash Flow Statement** — Cash from Operating/Investing/Financing Activities, Net Cash Flow

If consolidated numbers are not available for a company, standalone numbers are used and clearly marked.

## Data Sources

| Source | Purpose |
|--------|---------|
| **Screener.in** | Primary source for financial statements and market cap data |
| **NSE India** | Company discovery (NIFTY 500, NIFTY Total Market indices) |
| **BSE India** | Company discovery (BSE group listings) |

Numbers are sourced from Screener.in which aggregates data from published annual reports filed with BSE/NSE.

## Data Storage

Data is stored in three formats:

1. **SQLite Database** (`data/financial_profiles.db`) — Primary structured storage, queryable
2. **CSV Files** (`data/exports/`) — Flat files for each statement type, easy to open in Excel
3. **JSON Files** (`data/raw/` and `data/exports/company_profiles/`) — Per-company profiles and raw scraped data

### Database Schema

```
companies          — Master list with market cap, exchange codes, consolidated/standalone flag
profit_loss        — Annual P&L data per company per fiscal year
balance_sheet      — Annual balance sheet data per company per fiscal year
cash_flow          — Annual cash flow data per company per fiscal year
scrape_log         — Audit trail of all scraping attempts
```

## Setup

```bash
pip install -r requirements.txt
```

## Usage

### Full Pipeline (discover + scrape all qualifying companies)
```bash
python main.py
```

### Process Specific Companies
```bash
python main.py --symbols RELIANCE TCS INFY HDFCBANK ICICIBANK
```

### Export Only (after data is collected)
```bash
python main.py --export-only
```

### Validate Only
```bash
python main.py --validate-only
```

### Options
```
--symbols         Specific NSE symbols to process
--delay           Seconds between requests (default: 2.0)
--no-skip-existing Re-process companies already in DB
--db-path         Custom database file path
--verbose         Enable debug logging
```

## Project Structure

```
├── main.py                      # Entry point
├── src/
│   ├── config.py                # Configuration constants
│   ├── models.py                # SQLite schema and DB operations
│   ├── company_list.py          # Company discovery from NSE/BSE
│   ├── screener_scraper.py      # Screener.in financial data scraper
│   ├── pipeline.py              # Pipeline orchestrator
│   ├── exporters.py             # CSV/JSON export module
│   └── validators.py            # Data validation checks
├── tests/
│   ├── test_models.py           # DB model tests
│   ├── test_screener.py         # Scraper tests with mock HTML
│   ├── test_pipeline.py         # Pipeline integration tests
│   ├── test_exporters.py        # Export tests
│   └── test_validators.py       # Validation tests
├── data/
│   ├── raw/                     # Raw scraped JSON per company
│   ├── processed/               # Intermediate data
│   └── exports/                 # Final CSV/JSON exports
│       ├── companies.csv
│       ├── profit_loss_all.csv
│       ├── balance_sheet_all.csv
│       ├── cash_flow_all.csv
│       ├── data_summary.json
│       └── company_profiles/    # Per-company JSON profiles
└── requirements.txt
```

## Validation

The pipeline runs automatic validation checks:
- **Completeness** — All 3 years of data present for P&L, BS, CF
- **Balance Sheet Equation** — Total Assets = Total Liabilities (1% tolerance)
- **P&L Consistency** — Operating Profit ≈ Sales - Expenses
- **Cash Flow Consistency** — Net Cash Flow ≈ Sum of components
- **Reasonable Values** — No negative sales or total assets

## Running Tests

```bash
python -m pytest tests/ -v
```

61 unit and integration tests covering models, scraper, pipeline, exporters, and validators.
