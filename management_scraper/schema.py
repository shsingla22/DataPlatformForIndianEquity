"""Database schema for management data tables.

Creates three new tables:
  - management_personnel: Current and historical directors/KMP
  - management_yearly: Year-over-year board composition snapshots
  - management_changes: Log of all management transitions

Also adds management_change_flag and last_mgmt_update columns to companies.
"""

import sqlite3
from pathlib import Path

DEFAULT_DB = str(Path(__file__).parent.parent / "data" / "financial_profiles.db")


def create_management_tables(db_path: str = DEFAULT_DB):
    """Create management-related tables if they don't exist."""
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            -- Main management personnel table
            CREATE TABLE IF NOT EXISTS management_personnel (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                person_name TEXT NOT NULL,
                designation TEXT,
                director_category TEXT,
                din TEXT,
                appointment_date TEXT,
                cessation_date TEXT,
                qualification TEXT,
                experience_summary TEXT,
                previous_companies TEXT,
                age INTEGER,
                is_current INTEGER DEFAULT 1,
                is_kmp INTEGER DEFAULT 0,
                source TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (company_id) REFERENCES companies(id),
                UNIQUE(company_id, person_name)
            );

            -- Year-over-year board composition snapshots
            CREATE TABLE IF NOT EXISTS management_yearly (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                fiscal_year TEXT NOT NULL,
                person_name TEXT NOT NULL,
                designation TEXT,
                director_category TEXT,
                change_status TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (company_id) REFERENCES companies(id),
                UNIQUE(company_id, fiscal_year, person_name)
            );

            -- Management changes log
            CREATE TABLE IF NOT EXISTS management_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                fiscal_year TEXT NOT NULL,
                change_type TEXT NOT NULL,
                person_name TEXT NOT NULL,
                old_designation TEXT,
                new_designation TEXT,
                change_date TEXT,
                reason TEXT,
                news_source TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (company_id) REFERENCES companies(id)
            );
        """)

        # Add columns to companies table (ignore if already exists)
        for col, default in [
            ("management_change_flag", "0"),
            ("last_mgmt_update", "NULL"),
        ]:
            try:
                conn.execute(
                    f"ALTER TABLE companies ADD COLUMN {col} "
                    f"{'INTEGER DEFAULT ' + default if default.isdigit() else 'TEXT'}"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists

        conn.commit()
        print(f"Management tables created in {db_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    create_management_tables()
