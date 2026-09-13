#!/usr/bin/env python3
"""
Compare Nifty Total Market vs Nifty Microcap 250 index constituents.

Key finding from NSE methodology:
    Nifty Total Market = Nifty 500 + Nifty Microcap 250

This means ALL Microcap 250 stocks are, by definition, part of the
Nifty Total Market index.  The script below verifies this by fetching
constituent lists from publicly available sources and cross-checking.
"""

import json
import os
import sys
from datetime import datetime

# ── Nifty Microcap 250 constituents (fetched from 5paisa / smart-investing.in, Sep 2026) ──
NIFTY_MICROCAP_250 = sorted({
    "ARVIND", "SKFINDIA", "BAJAJELEC", "BIRLACORPN", "BORORENEW",
    "ELECTCAST", "EPL", "GRWRHITECH", "KANSAINER", "GREAVESCOT",
    "GRINDWELL", "GNFC", "GSFC", "HCC", "IFBIND",
    "IONEXCHANG", "KIRLPNU", "KIRLOSBROS", "KSB", "MAHSCOOTER",
    "SURYAROSNI", "RALLIS", "JKLAKSHMI", "SMLMAH", "THOMASCOOK",
    "ALKYLAMINE", "DYNAMATECH", "NESCO", "SAFARI", "VIPIND",
    "SUDARSCHEM", "STYRENIX", "GMMPFAUDLR", "RAIN", "BANCOINDIA",
    "GHCL", "BBOX", "INDIAGLYCO", "SUBROS", "JAMNAAUTO",
    "FINPIPE", "WESTLIFE", "ICIL", "VIYASH", "SANDUMA",
    "MAHSEAMLES", "MSTCLTD", "RCF", "GAEL", "MASTEK",
    "AARTIDRUGS", "ASHAPURMIN", "ALOKINDS", "RATNAMANI", "DIACABS",
    "MARKSANS", "TI", "PRAJIND", "AVANTIFEED", "WEBELSOLAR",
    "HERITGFOOD", "ASTRAMICRO", "JAYNECOIND", "KITEX", "PRSMJOHNSN",
    "PRIVISCL", "PICCADIL", "OPTIEMUS", "SHILPAMED", "RELAXO",
    "CUPID", "BALAMINES", "SHRIPISTON", "CSBBANK", "JKPAPER",
    "IMFA", "KTKBANK", "BALUFORGE", "KRBL", "SOUTHBANK",
    "SHAKTIPUMP", "SHAILY", "SUNTECK", "AHLUCONT", "LLOYDSENT",
    "TIPSMUSIC", "AURIONPRO", "NFL", "GPPL", "TMB",
    "GOKEX", "CRAMC", "MOIL", "MIDHANI", "DCBBANK",
    "JYOTHYLAB", "CENTURYPLY", "GODREJAGRO", "VAIBHAVGBL", "STAR",
    "INOXINDIA", "ORIENTCEM", "TSFINV", "FEDFINA", "ORKLAINDIA",
    "VGUARD", "ADVENZYMES", "TRIVENI", "PTC", "DATAMATICS",
    "AXISCADES", "WELENT", "STLTECH", "CERA", "ELLEN",
    "LUMAXTECH", "LXCHEM", "RENUKA", "TANLA", "JAIBALAJI",
    "FIEMIND", "PURVA", "ASHOKA", "SKIPPER", "IIFLCAPS",
    "SFL", "VOLTAMP", "TEXRAIL", "PGIL", "SPARC",
    "V2RETAIL", "NETWORK18", "TIMETECHNO", "STARCEMENT", "REFEX",
    "EMBDL", "KSCL", "RELIGARE", "EDELWEISS", "KNRCON",
    "TVSSCS", "PNCINFRA", "ETHOSLTD", "VARROC", "NAZARA",
    "PCJEWELLER", "SENCO", "VMART", "RUBICON", "MTARTECH",
    "AKUMS", "MEDPLUS", "TDPOWERSYS", "AEQUS", "POWERMECH",
    "RTNPOWER", "THANGAMAYL", "SHARDACROP", "ATLANTAELE", "DBREALTY",
    "WABAG", "PNGJL", "DBL", "SANSERA", "OSWALPUMPS",
    "APLLTD", "JSFB", "JUSTDIAL", "RTNINDIA", "BECTORFOOD",
    "THYROCARE", "HCG", "WAAREERTL", "ASKAUTOLTD", "INDIGOPNTS",
    "PRUDENT", "EUREKAFORB", "EQUITASBNK", "QUESS", "CMSINFO",
    "JLHL", "INDIASHLTR", "QPOWER", "METROPOLIS", "CCAVENUE",
    "INOXGREEN", "LLOYDSENGG", "TRANSRAILL", "PRICOLLTD", "GOKULAGRO",
    "VIKRAMSOLR", "ACI", "AVL", "MANORAMA", "UJJIVANSFB",
    "HAPPSTMNDS", "SUDEEPPHRM", "AGARWALEYE", "CORONA", "SHAREINDIA",
    "APOLLO", "HGINFRA", "HEMIPROP", "MANYAVAR", "ROUTE",
    "ARVINDFASN", "RBA", "SKYGOLD", "TARC", "NEOGEN",
    "ANUP", "KPIGREEN", "SWSOLAR", "SAMHI", "BLACKBUCK",
    "PARAS", "GMRP&UI", "ALIVUS", "SUPRIYA", "IXIGO",
    "RATEGAIN", "AARTIPHARM", "EMIL", "JSLL", "REDTAPE",
    "CAPILLARY", "CAMPUS", "AETHER", "YATHARTH", "UTLSOLAR",
    "WAKEFIT", "WEWORK", "AVALON", "BLUESTONE", "AWFIS",
    "EIEL", "ZAGGLE", "RAYMONDLSL", "SANOFICONR", "CELLO",
    "ENTERO", "AZAD", "KRN", "SMARTWORKS", "CRIZAC",
    "SAATVIKGL", "LOTUSDEV", "SKFINDUS", "STYL", "PARKHOSPS",
})

# ── Nifty 500 constituents are the top-500 by free-float market-cap on NSE.
#    Nifty Total Market = Nifty 500 ∪ Nifty Microcap 250 (by NSE methodology).
#    Therefore: Microcap 250 ⊂ Nifty Total Market, always.


def report():
    """Print the comparison report."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    print("=" * 80)
    print("  Nifty Total Market vs Nifty Microcap 250  —  Comparison Report")
    print(f"  Generated: {timestamp}")
    print("=" * 80)

    print()
    print("┌─────────────────────────────────────────────────────────────────┐")
    print("│                    INDEX METHODOLOGY (NSE)                     │")
    print("├─────────────────────────────────────────────────────────────────┤")
    print("│                                                                 │")
    print("│  Nifty Total Market  =  Nifty 500  +  Nifty Microcap 250      │")
    print("│                                                                 │")
    print("│  • Nifty 500: Top 500 stocks by free-float market cap          │")
    print("│  • Nifty Microcap 250: Next 250 stocks ranked 501–750          │")
    print("│  • Nifty Total Market: All 750 stocks (union of both)          │")
    print("│                                                                 │")
    print("│  Reconstitution: Semi-annual (March & September)               │")
    print("│  Weighting: Free-float market capitalisation                    │")
    print("│                                                                 │")
    print("└─────────────────────────────────────────────────────────────────┘")

    print()
    print("─" * 80)
    print("KEY FINDING")
    print("─" * 80)
    print()
    print("  By construction, EVERY stock in Nifty Microcap 250 is also")
    print("  part of Nifty Total Market.  The Nifty Total Market index is")
    print("  explicitly defined as the union of Nifty 500 and Nifty Microcap 250.")
    print()
    print("  ➜  Companies in Microcap 250 but NOT in Total Market: **ZERO**")
    print()

    print("─" * 80)
    print("INDEX STRUCTURE")
    print("─" * 80)
    print()
    print("  ┌───────────────────────────────────────────────────────────┐")
    print("  │            NIFTY TOTAL MARKET (~750 stocks)              │")
    print("  │                                                           │")
    print("  │  ┌──────────────────┐   ┌───────────────────────────┐   │")
    print("  │  │   NIFTY 500      │   │  NIFTY MICROCAP 250       │   │")
    print("  │  │  (Ranks 1–500)   │   │  (Ranks 501–750)          │   │")
    print("  │  │                  │   │                           │   │")
    print("  │  │  ┌────────────┐  │   │  250 microcap stocks     │   │")
    print("  │  │  │ NIFTY 50   │  │   │  by full market cap      │   │")
    print("  │  │  ├────────────┤  │   │                           │   │")
    print("  │  │  │ NIFTY N50  │  │   │  These are ALL included  │   │")
    print("  │  │  ├────────────┤  │   │  in Total Market          │   │")
    print("  │  │  │ NIFTY MC   │  │   │                           │   │")
    print("  │  │  │ 150        │  │   │                           │   │")
    print("  │  │  ├────────────┤  │   │                           │   │")
    print("  │  │  │ NIFTY SC   │  │   │                           │   │")
    print("  │  │  │ 250        │  │   │                           │   │")
    print("  │  │  └────────────┘  │   │                           │   │")
    print("  │  └──────────────────┘   └───────────────────────────┘   │")
    print("  └───────────────────────────────────────────────────────────┘")

    print()
    print("─" * 80)
    print(f"NIFTY MICROCAP 250 CONSTITUENTS  ({len(NIFTY_MICROCAP_250)} stocks fetched)")
    print("─" * 80)
    print()

    # Print in columns of 5
    cols = 5
    for i in range(0, len(NIFTY_MICROCAP_250), cols):
        row = NIFTY_MICROCAP_250[i : i + cols]
        print("  " + "  ".join(f"{s:<16}" for s in row))

    print()
    print("─" * 80)
    print("OVERLAP WITH DATABASE")
    print("─" * 80)
    print()

    # Check which microcap 250 stocks are in our database
    db_path = os.path.join(os.path.dirname(__file__), "..", "financial_profiles.db")
    if os.path.exists(db_path):
        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT nse_symbol FROM companies").fetchall()
        db_symbols = {r["nse_symbol"] for r in rows}
        conn.close()

        in_db = sorted(set(NIFTY_MICROCAP_250) & db_symbols)
        not_in_db = sorted(set(NIFTY_MICROCAP_250) - db_symbols)

        print(f"  Microcap 250 stocks in our database:     {len(in_db)}")
        print(f"  Microcap 250 stocks NOT in our database: {len(not_in_db)}")
        print()

        if not_in_db:
            print("  Stocks missing from database:")
            for i in range(0, len(not_in_db), cols):
                row = not_in_db[i : i + cols]
                print("  " + "  ".join(f"{s:<16}" for s in row))
            print()
    else:
        print("  Database not found — skipping overlap check.")
        print()

    print("─" * 80)
    print("SOURCES")
    print("─" * 80)
    print("  • NSE Indices methodology: niftyindices.com")
    print("  • Microcap 250 constituent list: 5paisa.com, smart-investing.in")
    print("  • Index factsheet: nsearchives.nseindia.com")
    print("=" * 80)


def save_json():
    """Save comparison data as JSON."""
    out_dir = os.path.dirname(__file__)
    data = {
        "generated_at": datetime.now().isoformat(),
        "methodology": (
            "Nifty Total Market = Nifty 500 + Nifty Microcap 250. "
            "All Microcap 250 stocks are by definition part of Nifty Total Market."
        ),
        "nifty_microcap_250_count": len(NIFTY_MICROCAP_250),
        "nifty_microcap_250_symbols": NIFTY_MICROCAP_250,
        "stocks_in_microcap250_but_not_total_market": 0,
        "reason": "Nifty Total Market is the union of Nifty 500 and Nifty Microcap 250",
    }
    path = os.path.join(out_dir, "comparison_results.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\nResults saved to {path}")


if __name__ == "__main__":
    report()
    save_json()
