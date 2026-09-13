"""Management data collection pipeline.

Orchestrates the full management data collection process:
  1. Create/verify database tables
  2. Scrape board of directors from BlinkX for each company
  3. Parse Key Highlights for year-over-year tracking
  4. Enrich key management personnel with background data
  5. Detect management changes and flag companies
  6. Generate human-readable report

Usage:
    python -m management_scraper                    # Full pipeline
    python -m management_scraper --symbols RELIANCE TCS
    python -m management_scraper --skip-existing    # Skip already-scraped
    python -m management_scraper --enrich-only      # Just enrich existing data
    python -m management_scraper --detect-changes   # Just detect changes
    python -m management_scraper --report           # Just generate report
"""

import argparse
import json
import sqlite3
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from management_scraper.schema import create_management_tables, DEFAULT_DB
from management_scraper.blinkx_scraper import scrape_company_bod, RATE_LIMIT
from management_scraper.enricher import enrich_from_screener, enrich_director
from management_scraper.change_detector import (
    detect_changes_for_company, store_changes, flag_companies_with_changes
)

logger = logging.getLogger(__name__)

REPORT_DIR = Path(__file__).parent.parent / "qa_reports"


def get_companies(conn: sqlite3.Connection,
                  symbols: List[str] = None) -> List[Dict]:
    """Get companies from database."""
    conn.row_factory = sqlite3.Row
    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        rows = conn.execute(
            f"SELECT * FROM companies WHERE nse_symbol IN ({placeholders}) "
            f"ORDER BY nse_symbol",
            symbols
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM companies ORDER BY nse_symbol"
        ).fetchall()
    return [dict(r) for r in rows]


def _already_scraped(conn: sqlite3.Connection, company_id: int) -> bool:
    """Check if company already has management data."""
    row = conn.execute(
        "SELECT COUNT(*) FROM management_personnel WHERE company_id = ?",
        (company_id,)
    ).fetchone()
    return row[0] > 0


def store_directors(conn: sqlite3.Connection, company_id: int,
                    directors: List[Dict], year_options: List[int]):
    """Store director data in management_personnel and management_yearly tables."""
    latest_year = str(max(year_options)) if year_options else "2025"

    for d in directors:
        name = d.get("person_name", "").strip()
        if not name:
            continue

        designation = d.get("designation")
        category = d.get("director_category", "Other")
        is_kmp = 1 if d.get("is_kmp") else 0
        source = d.get("source", "blinkx")
        change_status = d.get("change_status", "unknown")

        # Upsert into management_personnel
        try:
            conn.execute(
                "INSERT INTO management_personnel "
                "(company_id, person_name, designation, director_category, "
                "is_current, is_kmp, source, updated_at) "
                "VALUES (?, ?, ?, ?, 1, ?, ?, datetime('now')) "
                "ON CONFLICT(company_id, person_name) DO UPDATE SET "
                "designation=excluded.designation, "
                "director_category=excluded.director_category, "
                "is_kmp=excluded.is_kmp, "
                "is_current=CASE WHEN excluded.designation IS NOT NULL THEN 1 "
                "  ELSE management_personnel.is_current END, "
                "updated_at=datetime('now')",
                (company_id, name, designation, category, is_kmp, source)
            )
        except sqlite3.IntegrityError:
            pass

        # Insert into management_yearly for the latest year
        try:
            conn.execute(
                "INSERT OR IGNORE INTO management_yearly "
                "(company_id, fiscal_year, person_name, designation, "
                "director_category, change_status) VALUES (?, ?, ?, ?, ?, ?)",
                (company_id, latest_year, name, designation, category,
                 change_status)
            )
        except sqlite3.IntegrityError:
            pass

        # If change_status is 'continues', also insert for the prior year
        if change_status == "continues" and year_options and len(year_options) > 1:
            prev_year = str(sorted(year_options)[-2])
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO management_yearly "
                    "(company_id, fiscal_year, person_name, designation, "
                    "director_category, change_status) "
                    "VALUES (?, ?, ?, ?, ?, 'continues')",
                    (company_id, prev_year, name, designation, category)
                )
            except sqlite3.IntegrityError:
                pass

    # Mark departed directors as not current
    for d in directors:
        if d.get("change_status") == "departed":
            conn.execute(
                "UPDATE management_personnel SET is_current = 0, "
                "cessation_date = ?, updated_at = datetime('now') "
                "WHERE company_id = ? AND person_name = ?",
                (latest_year, company_id, d.get("person_name", ""))
            )

    conn.commit()


def enrich_company_directors(conn: sqlite3.Connection, company_id: int,
                             nse_symbol: str, company_name: str):
    """Enrich directors of a company with background data from Screener.in."""
    # Get about text from Screener
    about_text = enrich_from_screener(nse_symbol)

    # Get KMP directors to enrich
    cursor = conn.execute(
        "SELECT id, person_name, designation FROM management_personnel "
        "WHERE company_id = ? AND is_kmp = 1 AND qualification IS NULL",
        (company_id,)
    )
    directors = cursor.fetchall()

    for did, name, designation in directors:
        enriched = enrich_director(name, company_name, about_text)

        updates = []
        params = []
        for field in ["qualification", "experience_summary",
                      "previous_companies", "din"]:
            if enriched.get(field):
                updates.append(f"{field} = ?")
                params.append(enriched[field])

        if updates:
            params.append(did)
            conn.execute(
                f"UPDATE management_personnel SET {', '.join(updates)}, "
                f"updated_at = datetime('now') WHERE id = ?",
                params
            )

    conn.commit()


def generate_report(conn: sqlite3.Connection) -> str:
    """Generate a human-readable management data report."""
    lines = []
    lines.append("=" * 70)
    lines.append("MANAGEMENT DATA REPORT")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 70)
    lines.append("")

    # Summary stats
    total_personnel = conn.execute(
        "SELECT COUNT(*) FROM management_personnel"
    ).fetchone()[0]
    total_companies_with_data = conn.execute(
        "SELECT COUNT(DISTINCT company_id) FROM management_personnel"
    ).fetchone()[0]
    total_kmp = conn.execute(
        "SELECT COUNT(*) FROM management_personnel WHERE is_kmp = 1"
    ).fetchone()[0]
    total_changes = conn.execute(
        "SELECT COUNT(*) FROM management_changes"
    ).fetchone()[0]
    flagged_companies = conn.execute(
        "SELECT COUNT(*) FROM companies WHERE management_change_flag = 1"
    ).fetchone()[0]
    enriched = conn.execute(
        "SELECT COUNT(*) FROM management_personnel WHERE qualification IS NOT NULL"
    ).fetchone()[0]

    lines.append("SUMMARY")
    lines.append("-" * 40)
    lines.append(f"  Companies with management data: {total_companies_with_data}")
    lines.append(f"  Total directors/KMP tracked: {total_personnel}")
    lines.append(f"  Key Management Personnel (KMP): {total_kmp}")
    lines.append(f"  Directors with qualifications: {enriched}")
    lines.append(f"  Management changes detected: {total_changes}")
    lines.append(f"  Companies flagged for changes: {flagged_companies}")
    lines.append("")

    # Top management changes
    lines.append("MANAGEMENT CHANGES (by company)")
    lines.append("-" * 40)
    cursor = conn.execute(
        "SELECT c.nse_symbol, c.name, mc.fiscal_year, mc.change_type, "
        "mc.person_name, mc.old_designation, mc.new_designation "
        "FROM management_changes mc "
        "JOIN companies c ON c.id = mc.company_id "
        "ORDER BY c.nse_symbol, mc.fiscal_year DESC "
        "LIMIT 100"
    )
    current_company = None
    for row in cursor.fetchall():
        symbol, name, fy, change_type, person, old_desig, new_desig = row
        if symbol != current_company:
            current_company = symbol
            lines.append(f"\n  {symbol} ({name}):")

        if change_type == "appointment":
            lines.append(f"    [{fy}] NEW: {person} → {new_desig or 'Director'}")
        elif change_type == "departure":
            lines.append(f"    [{fy}] LEFT: {person} (was {old_desig or 'Director'})")
        elif change_type == "redesignation":
            lines.append(
                f"    [{fy}] CHANGED: {person}: {old_desig} → {new_desig}"
            )

    lines.append("")

    # Companies flagged for management change
    lines.append("\nFLAGGED COMPANIES (management changes)")
    lines.append("-" * 40)
    cursor = conn.execute(
        "SELECT nse_symbol, name FROM companies "
        "WHERE management_change_flag = 1 ORDER BY nse_symbol"
    )
    for row in cursor.fetchall():
        lines.append(f"  {row[0]:15s} {row[1]}")

    lines.append("")

    # Sample directors with qualifications
    lines.append("\nSAMPLE ENRICHED DIRECTORS")
    lines.append("-" * 40)
    cursor = conn.execute(
        "SELECT mp.person_name, mp.designation, mp.qualification, "
        "mp.experience_summary, c.nse_symbol "
        "FROM management_personnel mp "
        "JOIN companies c ON c.id = mp.company_id "
        "WHERE mp.qualification IS NOT NULL "
        "ORDER BY c.nse_symbol LIMIT 30"
    )
    for row in cursor.fetchall():
        name, desig, qual, exp, symbol = row
        lines.append(f"  {symbol} | {name} | {desig or 'N/A'}")
        if qual:
            lines.append(f"    Qualification: {qual[:120]}")
        if exp:
            lines.append(f"    Experience: {exp[:120]}")

    return "\n".join(lines)


def run_pipeline(db_path: str = DEFAULT_DB, symbols: List[str] = None,
                 skip_existing: bool = False, enrich_only: bool = False,
                 detect_only: bool = False, report_only: bool = False,
                 rate_limit: float = RATE_LIMIT):
    """Run the full management data collection pipeline."""
    # Step 1: Create tables
    create_management_tables(db_path)

    conn = sqlite3.connect(db_path)
    try:
        companies = get_companies(conn, symbols)
        total = len(companies)
        print(f"Found {total} companies to process", file=sys.stderr)

        if report_only:
            report = generate_report(conn)
            report_path = REPORT_DIR / "management_report.txt"
            REPORT_DIR.mkdir(parents=True, exist_ok=True)
            with open(report_path, "w") as f:
                f.write(report)
            print(report)
            print(f"\nReport saved: {report_path}", file=sys.stderr)
            return

        if detect_only:
            print("Detecting management changes...", file=sys.stderr)
            for company in companies:
                changes = detect_changes_for_company(
                    conn, company["id"], company["nse_symbol"]
                )
                if changes:
                    store_changes(conn, changes)
            n_flagged = flag_companies_with_changes(conn)
            print(f"Flagged {n_flagged} companies with management changes",
                  file=sys.stderr)
            return

        if not enrich_only:
            # Step 2: Scrape board of directors from BlinkX
            print("Phase 1: Scraping board of directors from BlinkX...",
                  file=sys.stderr)
            scraped = 0
            skipped = 0
            failed = 0

            for i, company in enumerate(companies):
                cid = company["id"]
                symbol = company["nse_symbol"]
                name = company["name"]

                if skip_existing and _already_scraped(conn, cid):
                    skipped += 1
                    continue

                if i > 0:
                    time.sleep(rate_limit)

                print(
                    f"  [{i+1}/{total}] {symbol} ({name[:40]})",
                    file=sys.stderr, end="", flush=True
                )

                bod_data = scrape_company_bod(name, symbol)

                if bod_data and bod_data.get("directors"):
                    n_dirs = len(bod_data["directors"])
                    store_directors(
                        conn, cid, bod_data["directors"],
                        bod_data.get("year_options", [])
                    )

                    # Update company last_mgmt_update
                    conn.execute(
                        "UPDATE companies SET last_mgmt_update = datetime('now') "
                        "WHERE id = ?", (cid,)
                    )
                    conn.commit()

                    scraped += 1
                    print(f" → {n_dirs} directors", file=sys.stderr)
                else:
                    failed += 1
                    print(f" → no data", file=sys.stderr)

            print(
                f"\nPhase 1 complete: {scraped} scraped, {skipped} skipped, "
                f"{failed} failed",
                file=sys.stderr
            )

        # Step 3: Enrich key management personnel
        print("\nPhase 2: Enriching director profiles from Screener.in...",
              file=sys.stderr)
        enriched_count = 0
        for i, company in enumerate(companies):
            cid = company["id"]
            symbol = company["nse_symbol"]
            name = company["name"]

            # Only enrich companies that have KMP without qualifications
            has_unenriched = conn.execute(
                "SELECT COUNT(*) FROM management_personnel "
                "WHERE company_id = ? AND is_kmp = 1 AND qualification IS NULL",
                (cid,)
            ).fetchone()[0]

            if has_unenriched > 0:
                if enriched_count > 0 and enriched_count % 10 == 0:
                    time.sleep(2)  # Rate limit for Screener.in
                enrich_company_directors(conn, cid, symbol, name)
                enriched_count += 1

        print(f"Phase 2 complete: enriched {enriched_count} companies",
              file=sys.stderr)

        # Step 4: Detect management changes
        print("\nPhase 3: Detecting management changes...", file=sys.stderr)
        total_changes = 0
        for company in companies:
            changes = detect_changes_for_company(
                conn, company["id"], company["nse_symbol"]
            )
            if changes:
                store_changes(conn, changes)
                total_changes += len(changes)

        print(f"Phase 3 complete: {total_changes} changes detected",
              file=sys.stderr)

        # Step 5: Flag companies
        n_flagged = flag_companies_with_changes(conn)
        print(f"Flagged {n_flagged} companies with significant management changes",
              file=sys.stderr)

        # Step 6: Generate report
        report = generate_report(conn)
        report_path = REPORT_DIR / "management_report.txt"
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            f.write(report)
        print(f"\nReport saved: {report_path}", file=sys.stderr)
        print(report)

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Management Data Collection Pipeline"
    )
    parser.add_argument("--db", default=DEFAULT_DB, help="Database path")
    parser.add_argument("--symbols", nargs="+",
                        help="Process specific company symbols only")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip companies already in the database")
    parser.add_argument("--enrich-only", action="store_true",
                        help="Only enrich existing director data")
    parser.add_argument("--detect-changes", action="store_true",
                        help="Only detect management changes")
    parser.add_argument("--report", action="store_true",
                        help="Only generate report")
    parser.add_argument("--rate-limit", type=float, default=RATE_LIMIT,
                        help=f"Seconds between requests (default: {RATE_LIMIT})")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable debug logging")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    run_pipeline(
        db_path=args.db,
        symbols=args.symbols,
        skip_existing=args.skip_existing,
        enrich_only=args.enrich_only,
        detect_only=args.detect_changes,
        report_only=args.report,
        rate_limit=args.rate_limit,
    )


if __name__ == "__main__":
    main()
