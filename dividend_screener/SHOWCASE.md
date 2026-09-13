# Dividend Value Screener – Indian Equity

*2026-03-08T08:01:12Z by Showboat 0.6.1*
<!-- showboat-id: def4081d-5bbe-46a3-a8a0-71a47c36f04a -->

## Overview

This screener identifies **high dividend-yielding stocks with low payout ratios, cheap valuations, and growing earnings** from a database of 500 Nifty-listed Indian equities built by the Data Platform for Indian Equity.

### Scoring Criteria

| Factor | Weight | Logic |
|---|---|---|
| Dividend Yield | 25% | Higher yield = higher score (0-10% mapped to 0-100) |
| Payout Ratio | 20% | Sweet spot 15-50%; penalises extremes |
| Earnings Growth | 20% | CAGR of net profit across available years |
| Valuation (Earnings Yield) | 20% | Inverse P/E; higher = cheaper stock |
| Balance Sheet Strength | 15% | Lower debt-to-equity is better |

### Data Sources

The screener reads directly from the `financial_profiles.db` SQLite database which contains:
- **Profit & Loss** data (EPS, dividend payout %, net profit, OPM)
- **Balance Sheet** data (equity, reserves, borrowings)
- **Cash Flow** data
- All scraped from Screener.in for Nifty 500 companies

## Step 1: Database Inspection

Let's verify the data platform database is ready with financial data we need.

```python3
import sqlite3
conn = sqlite3.connect('data/financial_profiles.db')
for t in ['companies', 'profit_loss', 'balance_sheet', 'cash_flow']:
    count = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f"{t}: {count} rows")
div_co = conn.execute("SELECT COUNT(DISTINCT company_id) FROM profit_loss WHERE dividend_payout_percent > 0").fetchone()[0]
print(f"\nCompanies with dividend payout data: {div_co}")
# Show a sample
print("\nSample - RELIANCE latest year:")
r = conn.execute("""
    SELECT pl.fiscal_year, pl.eps, pl.dividend_payout_percent, pl.net_profit,
           bs.borrowings, bs.equity_capital + bs.reserves as equity
    FROM profit_loss pl
    JOIN companies c ON pl.company_id = c.id
    JOIN balance_sheet bs ON bs.company_id = c.id AND bs.fiscal_year = pl.fiscal_year
    WHERE c.nse_symbol = 'RELIANCE'
    ORDER BY pl.fiscal_year DESC LIMIT 1
""").fetchone()
print(f"  Year={r[0]}, EPS={r[1]}, DivPayout={r[2]}%, NetProfit={r[3]} Cr, D/E={r[4]/r[5]:.2f}")
conn.close()
```

```output
companies: 500 rows
profit_loss: 1482 rows
balance_sheet: 1482 rows
cash_flow: 1482 rows

Companies with dividend payout data: 415

Sample - RELIANCE latest year:
  Year=Mar 2025, EPS=51.47, DivPayout=11.0%, NetProfit=81309.0 Cr, D/E=0.44
```

## Step 2: Run the Screener

The screener analyses 394 dividend-paying companies, computes 5 factor scores, and ranks them.

## Dividend Value Screener for Indian Equities

Identifies high dividend-yielding stocks with **low payout ratios, cheap valuations, and growing earnings** from 500 Nifty-listed companies. Results split into **PSU (Public Sector)** and **Private Sector** lists.

| Factor | Weight | Logic |
|---|---|---|
| Dividend Yield | 25% | Higher yield = higher score |
| Payout Ratio | 20% | Sweet spot 15-50% |
| Earnings Growth | 20% | CAGR of net profit |
| Valuation | 20% | Earnings yield (inverse P/E) |
| Balance Sheet | 15% | Lower debt-to-equity |

## Run the Screener

```bash
python -m dividend_screener --table-only --store 2>&1
```

```output
TOP 20 PSU COMPANIES
==============================================================================================================
  #  Symbol       Name                           Type        MktCap DivYld% Payout%    EG%     PE   D/E  Score
--------------------------------------------------------------------------------------------------------------
  1  RECLTD       REC Ltd                        PSU         93,269    5.11    30.0   19.3    5.9  0.00   83.5
  2  PFC          Power Finance Corporation Ltd  PSU        135,337    5.19    23.0   20.0    4.4  0.00   82.6
  3  GAIL         GAIL (India) Ltd               PSU        110,771    4.50    40.0   49.2    8.9  0.25   77.3
  4  J&KBANK      Jammu and Kashmir Bank Ltd     PSU         11,405    2.01    11.0   32.8    5.5  0.00   76.2
  5  LICHSGFIN    LIC Housing Finance Ltd        PSU         28,854    1.89    10.0   37.2    5.3  0.00   75.7
  6  UNIONBANK    Union Bank of India            PSU        148,077    2.43    20.0   45.5    8.2  0.00   75.3
  7  BANKINDIA    Bank of India                  PSU         78,169    2.32    19.0   57.7    8.2  0.00   74.9
  8  COALINDIA    Coal India Ltd                 PSU        261,022    6.22    46.0    5.5    7.4  0.09   74.9
  9  PNB          Punjab National Bank           PSU        148,937    2.24    18.0  135.0    8.0  0.00   74.8
 10  CANBK        Canara Bank                    PSU        139,824    2.66    21.0   24.9    7.9  0.00   74.7
 11  MAHABANK     Bank of Maharashtra            PSU         52,910    2.20    21.0   45.9    9.5  0.00   72.7
 12  BANKBARODA   Bank of Baroda                 PSU        159,821    2.74    21.0   17.9    7.7  0.00   72.6
 13  NATIONALUM   National Aluminium Company Ltd PSU         62,666    3.11    37.0   91.6   11.9  0.01   72.5
 14  INDIANB      Indian Bank                    PSU        127,517    1.68    19.0   42.2   11.3  0.00   68.8
 15  IDBI         IDBI Bank Ltd                  PSU        121,319    1.89    30.0   43.3   15.8  0.00   68.1
 16  HUDCO        Housing & Urban Development Co PSU         39,125    2.15    31.0   26.2   14.4  0.00   67.9
 17  MGL          Mahanagar Gas Ltd              PSU         11,196    2.60    28.0   14.7   10.8  0.03   67.1
 18  BPCL         Bharat Petroleum Corporation L PSU        158,919    2.69    32.0  150.2   11.9  0.75   66.9
 19  ONGC         Oil & Natural Gas Corpn Ltd    PSU        350,549    4.70    43.0    8.1    9.1  0.55   65.9
 20  GICRE        General Insurance Corporation  PSU         66,808    2.67    24.0    3.7    9.0  0.00   64.8

TOP 20 PRIVATE SECTOR COMPANIES
==============================================================================================================
  #  Symbol       Name                           Type        MktCap DivYld% Payout%    EG%     PE   D/E  Score
--------------------------------------------------------------------------------------------------------------
  1  ITC          ITC Ltd                        Private    409,706    4.45    52.0   34.2   11.7  0.00   76.5
  2  BBTC         The Bombay Burmah Trading Corp Private     12,397    1.95    11.0   30.2    5.6  0.28   74.0
  3  ZEEL         Zee Entertainment Enterprises  Private      8,712    2.65    34.0  276.4   12.8  0.03   71.0
  4  CHAMBLFERT   Chambal Fertilisers & Chemical Private     18,206    2.17    24.0   26.3   11.0  0.01   69.7
  5  FINPIPE      Finolex Industries Ltd         Private     11,782    1.90    28.0   78.5   14.7  0.04   68.1
  6  REDINGTON    Redington Ltd                  Private     19,658    3.06    33.0   12.5   10.8  0.32   65.0
  7  ZENSARTECH   Zensar Technologies Ltd        Private     12,742    2.30    45.0   40.8   19.6  0.03   64.3
  8  INDIAMART    Indiamart Intermesh Ltd        Private     13,133    2.27    54.0   39.3   23.8  0.02   64.1
  9  CIPLA        Cipla Ltd                      Private    108,331    1.22    25.0   36.4   20.6  0.01   63.4
 10  ZYDUSLIFE    Zydus Lifesciences Ltd         Private     90,637    1.24    24.0   49.5   19.4  0.13   62.8
 11  TMPV         Tata Motors Passenger Vehicles Private    139,192    1.62     8.0  223.5    4.9  0.62   62.4
 12  HDFCBANK     HDFC Bank Ltd                  Private  1,403,163    1.26    24.0   26.1   19.1  0.00   62.4
 13  BSOFT        Birlasoft Ltd                  Private     10,584    1.71    35.0   24.8   20.5  0.04   62.4
 14  NCC          NCC Ltd                        Private      9,359    1.58    17.0   15.9   10.8  0.22   61.4
 15  LTF          L&T Finance Ltd                Private     74,544    0.92    26.0   31.2   28.2  0.00   61.2
 16  KARURVYSYA   Karur Vysya Bank Ltd           Private     31,180    0.69    11.0   32.5   16.1  0.00   61.2
 17  KPITTECH     KPIT Technologies Ltd          Private     22,902    1.03    28.0   47.3   27.3  0.12   61.2
 18  MARUTI       Maruti Suzuki India Ltd        Private    470,881    0.89    29.0   32.9   32.5  0.00   61.1
 19  NEWGEN       Newgen Software Technologies L Private      7,926    0.87    22.0   33.8   25.2  0.03   60.6
 20  APLLTD       Alembic Pharmaceuticals Ltd    Private     14,999    1.44    37.0   30.5   25.8  0.24   60.5

Stored 394 company scores in database
```

## PSU vs Private Comparison

```python3
from dividend_screener.screener import load_company_data, rank_companies
metrics = load_company_data()
psu = sorted([m for m in metrics if m.ownership_type == 'PSU'], key=lambda m: m.composite_score, reverse=True)[:20]
priv = sorted([m for m in metrics if m.ownership_type == 'Private'], key=lambda m: m.composite_score, reverse=True)[:20]

def avg(lst, attr): return sum(getattr(m, attr) for m in lst) / len(lst)

print(f"{'Metric':25s} {'PSU Top 20':>12s} {'Private Top 20':>15s}")
print(f"{'-'*25} {'-'*12} {'-'*15}")
print(f"{'Avg Composite Score':25s} {avg(psu,'composite_score'):12.1f} {avg(priv,'composite_score'):15.1f}")
print(f"{'Avg Dividend Yield':25s} {avg(psu,'dividend_yield_pct'):11.2f}% {avg(priv,'dividend_yield_pct'):14.2f}%")
print(f"{'Avg P/E Ratio':25s} {avg(psu,'pe_ratio'):11.1f}x {avg(priv,'pe_ratio'):14.1f}x")
print(f"{'Avg Earnings Growth':25s} {avg(psu,'earnings_growth_pct'):11.1f}% {avg(priv,'earnings_growth_pct'):14.1f}%")
print(f"{'Avg Payout Ratio':25s} {avg(psu,'dividend_payout_pct'):11.1f}% {avg(priv,'dividend_payout_pct'):14.1f}%")
print()
print("PSUs dominate dividend value: higher yields, lower PEs, lower payouts.")
print("Private sector compensates with higher earnings growth potential.")
```

```output
Metric                      PSU Top 20  Private Top 20
------------------------- ------------ ---------------
Avg Composite Score               72.9            64.7
Avg Dividend Yield               3.05%           1.76%
Avg P/E Ratio                     9.1x           18.0x
Avg Earnings Growth              43.5%           56.1%
Avg Payout Ratio                 26.2%           28.4%

PSUs dominate dividend value: higher yields, lower PEs, lower payouts.
Private sector compensates with higher earnings growth potential.
```

## Database Verification

```python3
import sqlite3
conn = sqlite3.connect('data/financial_profiles.db')
total = conn.execute('SELECT COUNT(*) FROM dividend_screener_results').fetchone()[0]
psu = conn.execute("SELECT COUNT(*) FROM dividend_screener_results WHERE ownership_type='PSU'").fetchone()[0]
priv = conn.execute("SELECT COUNT(*) FROM dividend_screener_results WHERE ownership_type='Private'").fetchone()[0]
print(f"Total scored: {total} (PSU: {psu}, Private: {priv})")
print(f"Top 3 PSU: ", end="")
for r in conn.execute("SELECT nse_symbol, composite_score FROM dividend_screener_results WHERE ownership_type='PSU' ORDER BY composite_score DESC LIMIT 3"):
    print(f"{r[0]}({r[1]})", end=" ")
print(f"\nTop 3 Pvt: ", end="")
for r in conn.execute("SELECT nse_symbol, composite_score FROM dividend_screener_results WHERE ownership_type='Private' ORDER BY composite_score DESC LIMIT 3"):
    print(f"{r[0]}({r[1]})", end=" ")
print()
conn.close()
```

```output
Total scored: 394 (PSU: 55, Private: 339)
Top 3 PSU: RECLTD(83.5) PFC(82.6) GAIL(77.3) 
Top 3 Pvt: ITC(76.5) BBTC(74.0) ZEEL(71.0) 
```
