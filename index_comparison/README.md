# Nifty Total Market vs Nifty Microcap 250 — Index Comparison

## Key Finding

**There are ZERO companies in Nifty Microcap 250 that are not in Nifty Total Market.**

This is because, by NSE's official methodology:

> **Nifty Total Market = Nifty 500 + Nifty Microcap 250**

The Nifty Total Market index is explicitly defined as the union of these two indices. Every stock in Microcap 250 is, by construction, a constituent of Nifty Total Market.

## Index Structure

```
┌───────────────────────────────────────────────────────────┐
│            NIFTY TOTAL MARKET (~750 stocks)               │
│                                                           │
│  ┌──────────────────┐   ┌───────────────────────────┐    │
│  │   NIFTY 500      │   │  NIFTY MICROCAP 250       │    │
│  │  (Ranks 1–500)   │   │  (Ranks 501–750)          │    │
│  │                   │   │                           │    │
│  │  • Nifty 50       │   │  Top 250 stocks ranked    │    │
│  │  • Nifty Next 50  │   │  501–750 by full market   │    │
│  │  • Nifty Midcap   │   │  capitalisation           │    │
│  │    150            │   │                           │    │
│  │  • Nifty Smallcap │   │                           │    │
│  │    250            │   │                           │    │
│  └──────────────────┘   └───────────────────────────┘    │
└───────────────────────────────────────────────────────────┘
```

## Methodology

| Index | # Stocks | Selection Criteria |
|-------|----------|-------------------|
| Nifty 50 | 50 | Top 50 by free-float market cap |
| Nifty Next 50 | 50 | Ranks 51–100 |
| Nifty Midcap 150 | 150 | Ranks 101–250 |
| Nifty Smallcap 250 | 250 | Ranks 251–500 |
| **Nifty 500** | **500** | **Union of above (Ranks 1–500)** |
| **Nifty Microcap 250** | **250** | **Ranks 501–750 by full market cap** |
| **Nifty Total Market** | **~750** | **Nifty 500 + Nifty Microcap 250** |

## Reconstitution

Both Nifty 500 and Nifty Microcap 250 are rebalanced **semi-annually** (March and September). The Nifty Total Market reconstitution is aligned to these rebalancing dates.

## Running the Comparison

```bash
python index_comparison/compare_indices.py
```

This generates:
- A formatted console report with the full constituent list
- `comparison_results.json` with machine-readable results

## Sources

- [NSE Indices — Nifty Total Market](https://www.nseindia.com/products-services/indices-nifty-total-market-index)
- [NSE Indices Methodology Document](https://nsearchives.nseindia.com/content/indices/Method_NIFTY_Equity_Indices.pdf)
- [Nifty Total Market Factsheet](https://www.niftyindices.com/Factsheet/Factsheet_NiftyTotalMarket.pdf)
- [Nifty Microcap 250 Factsheet](https://nsearchives.nseindia.com/content/indices/Factsheet_Nifty_Microcap_250_Index.pdf)
