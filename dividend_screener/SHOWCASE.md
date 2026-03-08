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

```bash
python -m dividend_screener --table-only --store 2>/dev/null
```

```output
  #  Symbol       Name                           Sector                 MktCap DivYld% Payout%    EG%     PE   D/E  Score
-------------------------------------------------------------------------------------------------------------------------
  1  RECLTD       REC Ltd                                               93,269    5.11    30.0   19.3    5.9  0.00   83.5
  2  PFC          Power Finance Corporation Ltd                        135,337    5.19    23.0   20.0    4.4  0.00   82.6
  3  GAIL         GAIL (India) Ltd                                     110,771    4.50    40.0   49.2    8.9  0.25   77.3
  4  ITC          ITC Ltd                                              409,706    4.45    52.0   34.2   11.7  0.00   76.5
  5  J&KBANK      Jammu and Kashmir Bank Ltd                            11,405    2.01    11.0   32.8    5.5  0.00   76.2
  6  LICHSGFIN    LIC Housing Finance Ltd                               28,854    1.89    10.0   37.2    5.3  0.00   75.7
  7  UNIONBANK    Union Bank of India                                  148,077    2.43    20.0   45.5    8.2  0.00   75.3
  8  BANKINDIA    Bank of India                                         78,169    2.32    19.0   57.7    8.2  0.00   74.9
  9  COALINDIA    Coal India Ltd                                       261,022    6.22    46.0    5.5    7.4  0.09   74.9
 10  PNB          Punjab National Bank                                 148,937    2.24    18.0  135.0    8.0  0.00   74.8
 11  CANBK        Canara Bank                                          139,824    2.66    21.0   24.9    7.9  0.00   74.7
 12  BBTC         The Bombay Burmah Trading Corp                        12,397    1.95    11.0   30.2    5.6  0.28   74.0
 13  MAHABANK     Bank of Maharashtra                                   52,910    2.20    21.0   45.9    9.5  0.00   72.7
 14  BANKBARODA   Bank of Baroda                                       159,821    2.74    21.0   17.9    7.7  0.00   72.6
 15  NATIONALUM   National Aluminium Company Ltd                        62,666    3.11    37.0   91.6   11.9  0.01   72.5
 16  ZEEL         Zee Entertainment Enterprises                          8,712    2.65    34.0  276.4   12.8  0.03   71.0
 17  CHAMBLFERT   Chambal Fertilisers & Chemical                        18,206    2.17    24.0   26.3   11.0  0.01   69.7
 18  INDIANB      Indian Bank                                          127,517    1.68    19.0   42.2   11.3  0.00   68.8
 19  IDBI         IDBI Bank Ltd                                        121,319    1.89    30.0   43.3   15.8  0.00   68.1
 20  FINPIPE      Finolex Industries Ltd                                11,782    1.90    28.0   78.5   14.7  0.04   68.1
 21  HUDCO        Housing & Urban Development Co                        39,125    2.15    31.0   26.2   14.4  0.00   67.9
 22  MGL          Mahanagar Gas Ltd                                     11,196    2.60    28.0   14.7   10.8  0.03   67.1
 23  BPCL         Bharat Petroleum Corporation L                       158,919    2.69    32.0  150.2   11.9  0.75   66.9
 24  ONGC         Oil & Natural Gas Corpn Ltd                          350,549    4.70    43.0    8.1    9.1  0.55   65.9
 25  REDINGTON    Redington Ltd                                         19,658    3.06    33.0   12.5   10.8  0.32   65.0
 26  GICRE        General Insurance Corporation                         66,808    2.67    24.0    3.7    9.0  0.00   64.8
 27  NMDC         NMDC Ltd                                              70,449    4.07    44.0    7.9   10.8  0.14   64.8
 28  ZENSARTECH   Zensar Technologies Ltd                               12,742    2.30    45.0   40.8   19.6  0.03   64.3
 29  INDIAMART    Indiamart Intermesh Ltd                               13,133    2.27    54.0   39.3   23.8  0.02   64.1
 30  ENGINERSIN   Engineers India Ltd                                   12,078    1.87    39.0   29.5   20.8  0.01   64.0
```

## Step 2: Run the Screener and Store Results

The screener analyses all dividend-paying companies, computes 5 factor scores, ranks them, and stores results in the database.

```bash
python -m dividend_screener --table-only --store 2>&1
```

```output
  #  Symbol       Name                           Sector                 MktCap DivYld% Payout%    EG%     PE   D/E  Score
-------------------------------------------------------------------------------------------------------------------------
  1  RECLTD       REC Ltd                                               93,269    5.11    30.0   19.3    5.9  0.00   83.5
  2  PFC          Power Finance Corporation Ltd                        135,337    5.19    23.0   20.0    4.4  0.00   82.6
  3  GAIL         GAIL (India) Ltd                                     110,771    4.50    40.0   49.2    8.9  0.25   77.3
  4  ITC          ITC Ltd                                              409,706    4.45    52.0   34.2   11.7  0.00   76.5
  5  J&KBANK      Jammu and Kashmir Bank Ltd                            11,405    2.01    11.0   32.8    5.5  0.00   76.2
  6  LICHSGFIN    LIC Housing Finance Ltd                               28,854    1.89    10.0   37.2    5.3  0.00   75.7
  7  UNIONBANK    Union Bank of India                                  148,077    2.43    20.0   45.5    8.2  0.00   75.3
  8  BANKINDIA    Bank of India                                         78,169    2.32    19.0   57.7    8.2  0.00   74.9
  9  COALINDIA    Coal India Ltd                                       261,022    6.22    46.0    5.5    7.4  0.09   74.9
 10  PNB          Punjab National Bank                                 148,937    2.24    18.0  135.0    8.0  0.00   74.8
 11  CANBK        Canara Bank                                          139,824    2.66    21.0   24.9    7.9  0.00   74.7
 12  BBTC         The Bombay Burmah Trading Corp                        12,397    1.95    11.0   30.2    5.6  0.28   74.0
 13  MAHABANK     Bank of Maharashtra                                   52,910    2.20    21.0   45.9    9.5  0.00   72.7
 14  BANKBARODA   Bank of Baroda                                       159,821    2.74    21.0   17.9    7.7  0.00   72.6
 15  NATIONALUM   National Aluminium Company Ltd                        62,666    3.11    37.0   91.6   11.9  0.01   72.5
 16  ZEEL         Zee Entertainment Enterprises                          8,712    2.65    34.0  276.4   12.8  0.03   71.0
 17  CHAMBLFERT   Chambal Fertilisers & Chemical                        18,206    2.17    24.0   26.3   11.0  0.01   69.7
 18  INDIANB      Indian Bank                                          127,517    1.68    19.0   42.2   11.3  0.00   68.8
 19  IDBI         IDBI Bank Ltd                                        121,319    1.89    30.0   43.3   15.8  0.00   68.1
 20  FINPIPE      Finolex Industries Ltd                                11,782    1.90    28.0   78.5   14.7  0.04   68.1
 21  HUDCO        Housing & Urban Development Co                        39,125    2.15    31.0   26.2   14.4  0.00   67.9
 22  MGL          Mahanagar Gas Ltd                                     11,196    2.60    28.0   14.7   10.8  0.03   67.1
 23  BPCL         Bharat Petroleum Corporation L                       158,919    2.69    32.0  150.2   11.9  0.75   66.9
 24  ONGC         Oil & Natural Gas Corpn Ltd                          350,549    4.70    43.0    8.1    9.1  0.55   65.9
 25  REDINGTON    Redington Ltd                                         19,658    3.06    33.0   12.5   10.8  0.32   65.0
 26  GICRE        General Insurance Corporation                         66,808    2.67    24.0    3.7    9.0  0.00   64.8
 27  NMDC         NMDC Ltd                                              70,449    4.07    44.0    7.9   10.8  0.14   64.8
 28  ZENSARTECH   Zensar Technologies Ltd                               12,742    2.30    45.0   40.8   19.6  0.03   64.3
 29  INDIAMART    Indiamart Intermesh Ltd                               13,133    2.27    54.0   39.3   23.8  0.02   64.1
 30  ENGINERSIN   Engineers India Ltd                                   12,078    1.87    39.0   29.5   20.8  0.01   64.0

Stored 394 company scores in database
```

## Step 2: Run the Screener

The screener analyses all dividend-paying companies, scores them across 5 factors, ranks them, and stores results in the database.

```bash
python -m dividend_screener --table-only --store 2>&1
```

```output
  #  Symbol       Name                           Sector                 MktCap DivYld% Payout%    EG%     PE   D/E  Score
-------------------------------------------------------------------------------------------------------------------------
  1  RECLTD       REC Ltd                                               93,269    5.11    30.0   19.3    5.9  0.00   83.5
  2  PFC          Power Finance Corporation Ltd                        135,337    5.19    23.0   20.0    4.4  0.00   82.6
  3  GAIL         GAIL (India) Ltd                                     110,771    4.50    40.0   49.2    8.9  0.25   77.3
  4  ITC          ITC Ltd                                              409,706    4.45    52.0   34.2   11.7  0.00   76.5
  5  J&KBANK      Jammu and Kashmir Bank Ltd                            11,405    2.01    11.0   32.8    5.5  0.00   76.2
  6  LICHSGFIN    LIC Housing Finance Ltd                               28,854    1.89    10.0   37.2    5.3  0.00   75.7
  7  UNIONBANK    Union Bank of India                                  148,077    2.43    20.0   45.5    8.2  0.00   75.3
  8  BANKINDIA    Bank of India                                         78,169    2.32    19.0   57.7    8.2  0.00   74.9
  9  COALINDIA    Coal India Ltd                                       261,022    6.22    46.0    5.5    7.4  0.09   74.9
 10  PNB          Punjab National Bank                                 148,937    2.24    18.0  135.0    8.0  0.00   74.8
 11  CANBK        Canara Bank                                          139,824    2.66    21.0   24.9    7.9  0.00   74.7
 12  BBTC         The Bombay Burmah Trading Corp                        12,397    1.95    11.0   30.2    5.6  0.28   74.0
 13  MAHABANK     Bank of Maharashtra                                   52,910    2.20    21.0   45.9    9.5  0.00   72.7
 14  BANKBARODA   Bank of Baroda                                       159,821    2.74    21.0   17.9    7.7  0.00   72.6
 15  NATIONALUM   National Aluminium Company Ltd                        62,666    3.11    37.0   91.6   11.9  0.01   72.5
 16  ZEEL         Zee Entertainment Enterprises                          8,712    2.65    34.0  276.4   12.8  0.03   71.0
 17  CHAMBLFERT   Chambal Fertilisers & Chemical                        18,206    2.17    24.0   26.3   11.0  0.01   69.7
 18  INDIANB      Indian Bank                                          127,517    1.68    19.0   42.2   11.3  0.00   68.8
 19  IDBI         IDBI Bank Ltd                                        121,319    1.89    30.0   43.3   15.8  0.00   68.1
 20  FINPIPE      Finolex Industries Ltd                                11,782    1.90    28.0   78.5   14.7  0.04   68.1
 21  HUDCO        Housing & Urban Development Co                        39,125    2.15    31.0   26.2   14.4  0.00   67.9
 22  MGL          Mahanagar Gas Ltd                                     11,196    2.60    28.0   14.7   10.8  0.03   67.1
 23  BPCL         Bharat Petroleum Corporation L                       158,919    2.69    32.0  150.2   11.9  0.75   66.9
 24  ONGC         Oil & Natural Gas Corpn Ltd                          350,549    4.70    43.0    8.1    9.1  0.55   65.9
 25  REDINGTON    Redington Ltd                                         19,658    3.06    33.0   12.5   10.8  0.32   65.0
 26  GICRE        General Insurance Corporation                         66,808    2.67    24.0    3.7    9.0  0.00   64.8
 27  NMDC         NMDC Ltd                                              70,449    4.07    44.0    7.9   10.8  0.14   64.8
 28  ZENSARTECH   Zensar Technologies Ltd                               12,742    2.30    45.0   40.8   19.6  0.03   64.3
 29  INDIAMART    Indiamart Intermesh Ltd                               13,133    2.27    54.0   39.3   23.8  0.02   64.1
 30  ENGINERSIN   Engineers India Ltd                                   12,078    1.87    39.0   29.5   20.8  0.01   64.0

Stored 394 company scores in database
```

## Step 3: Score Breakdown – Top 5

Each company is scored 0-100 on five factors, then weighted into a composite.

```python3
from dividend_screener.screener import load_company_data, rank_companies
metrics = load_company_data()
ranked = rank_companies(metrics, 5)
print(f"{'Symbol':12s} {'DivYld':>7s} {'Payout':>7s} {'Growth':>7s} {'Value':>7s} {'BalSht':>7s} {'TOTAL':>7s}")
print("-" * 60)
for m in ranked:
    print(f"{m.nse_symbol:12s} {m.score_div_yield:7.1f} {m.score_payout:7.1f} {m.score_earnings_growth:7.1f} {m.score_valuation:7.1f} {m.score_balance_sheet:7.1f} {m.composite_score:7.1f}")
print()
print("Key insights:")
print("  #1 REC Ltd: 5.1% yield, 30% payout, 19% earnings CAGR, 5.9x PE")
print("  #2 PFC: Infrastructure NBFC peer to REC with similar profile")
print("  #3 GAIL: Gas utility with 49% earnings growth, 4.5% yield")
print("  #4 ITC: Classic FMCG dividend compounder at 4.5% yield")
print("  #5 J&K Bank: Deep value at 5.5x PE with 33% earnings CAGR")
```

```output
Symbol        DivYld  Payout  Growth   Value  BalSht   TOTAL
------------------------------------------------------------
RECLTD          51.1   100.0    78.5   100.0   100.0    83.5
PFC             51.9    93.0    80.1   100.0   100.0    82.6
GAIL            45.0    90.0   100.0    75.0    87.3    77.3
ITC             44.5    95.0   100.0    57.0    99.8    76.5
J&KBANK         20.1    81.0   100.0   100.0   100.0    76.2

Key insights:
  #1 REC Ltd: 5.1% yield, 30% payout, 19% earnings CAGR, 5.9x PE
  #2 PFC: Infrastructure NBFC peer to REC with similar profile
  #3 GAIL: Gas utility with 49% earnings growth, 4.5% yield
  #4 ITC: Classic FMCG dividend compounder at 4.5% yield
  #5 J&K Bank: Deep value at 5.5x PE with 33% earnings CAGR
```

## Step 4: Database Storage Verification

Results are persisted in `dividend_screener_results` and each company's `dividend_score` is updated.

```python3
import sqlite3
conn = sqlite3.connect('data/financial_profiles.db')
total = conn.execute('SELECT COUNT(*) FROM dividend_screener_results').fetchone()[0]
ranked = conn.execute('SELECT COUNT(*) FROM dividend_screener_results WHERE rank IS NOT NULL').fetchone()[0]
scored = conn.execute('SELECT COUNT(*) FROM companies WHERE dividend_score IS NOT NULL').fetchone()[0]
print(f"dividend_screener_results: {total} companies scored")
print(f"Top 30 ranked: {ranked}")
print(f"companies.dividend_score updated: {scored}")
print()
print("Top 3 from database:")
for r in conn.execute("""
    SELECT rank, nse_symbol, dividend_yield_pct, dividend_payout_pct,
           pe_ratio, earnings_growth_pct, composite_score
    FROM dividend_screener_results WHERE rank IS NOT NULL ORDER BY rank LIMIT 3
""").fetchall():
    print(f"  #{r[0]} {r[1]:12s} DY={r[2]:.1f}% Payout={r[3]:.0f}% PE={r[4]:.1f}x Growth={r[5]:.0f}% Score={r[6]:.1f}")
conn.close()
```

```output
dividend_screener_results: 394 companies scored
Top 30 ranked: 30
companies.dividend_score updated: 394

Top 3 from database:
  #1 RECLTD       DY=5.1% Payout=30% PE=5.9x Growth=19% Score=83.5
  #2 PFC          DY=5.2% Payout=23% PE=4.4x Growth=20% Score=82.6
  #3 GAIL         DY=4.5% Payout=40% PE=8.9x Growth=49% Score=77.3
```
