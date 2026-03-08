"""Store screener results back into the database.

Creates a dividend_screener_results table and populates it with
the ranked output, plus adds a dividend_score column to companies.
"""

import sqlite3
from datetime import datetime
from typing import List

from dividend_screener.screener import CompanyMetrics, DB_PATH


def create_results_table(db_path: str = DB_PATH):
    """Create the dividend_screener_results table if it doesn't exist."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dividend_screener_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            nse_symbol TEXT,
            rank INTEGER,
            fiscal_year TEXT,
            dividend_yield_pct REAL,
            dividend_payout_pct REAL,
            eps REAL,
            dps REAL,
            pe_ratio REAL,
            earnings_yield_pct REAL,
            earnings_growth_pct REAL,
            debt_to_equity REAL,
            roe_pct REAL,
            score_div_yield REAL,
            score_payout REAL,
            score_earnings_growth REAL,
            score_valuation REAL,
            score_balance_sheet REAL,
            composite_score REAL,
            screened_at TEXT,
            UNIQUE(company_id, screened_at)
        )
    """)

    # Add dividend_score column to companies if it doesn't exist
    try:
        conn.execute(
            "ALTER TABLE companies ADD COLUMN dividend_score REAL DEFAULT NULL"
        )
    except sqlite3.OperationalError:
        pass  # column already exists

    conn.commit()
    conn.close()


def store_results(all_metrics: List[CompanyMetrics],
                  ranked: List[CompanyMetrics],
                  db_path: str = DB_PATH):
    """Store all scored companies and update company dividend_score."""
    create_results_table(db_path)
    conn = sqlite3.connect(db_path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Clear previous results to avoid duplicates
    conn.execute("DELETE FROM dividend_screener_results")

    # Build rank lookup
    rank_map = {m.company_id: i + 1 for i, m in enumerate(ranked)}

    # Store all scored companies
    for m in all_metrics:
        rank = rank_map.get(m.company_id)
        conn.execute(
            "INSERT OR REPLACE INTO dividend_screener_results "
            "(company_id, nse_symbol, rank, fiscal_year, "
            "dividend_yield_pct, dividend_payout_pct, eps, dps, "
            "pe_ratio, earnings_yield_pct, earnings_growth_pct, "
            "debt_to_equity, roe_pct, "
            "score_div_yield, score_payout, score_earnings_growth, "
            "score_valuation, score_balance_sheet, composite_score, "
            "screened_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                m.company_id, m.nse_symbol, rank, m.latest_year,
                round(m.dividend_yield_pct, 2),
                round(m.dividend_payout_pct, 1),
                round(m.eps, 2), round(m.dps, 2),
                round(m.pe_ratio, 1),
                round(m.earnings_yield_pct, 2),
                round(m.earnings_growth_pct, 1),
                round(m.debt_to_equity, 2),
                round(m.roe_pct, 1),
                round(m.score_div_yield, 1),
                round(m.score_payout, 1),
                round(m.score_earnings_growth, 1),
                round(m.score_valuation, 1),
                round(m.score_balance_sheet, 1),
                round(m.composite_score, 1),
                now,
            )
        )

        # Update company dividend_score
        conn.execute(
            "UPDATE companies SET dividend_score = ? WHERE id = ?",
            (round(m.composite_score, 1), m.company_id)
        )

    conn.commit()
    conn.close()
    return len(all_metrics)
