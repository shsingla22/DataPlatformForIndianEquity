"""Year-over-year management change detection.

Compares board composition across fiscal years to identify:
  - New appointments (person appears in year N but not N-1)
  - Departures (person in year N-1 but not in year N)
  - Redesignations (same person, different title)
  - Key management changes (CMD, MD, CEO, CFO transitions)

Flags companies in the companies table when significant management
changes are detected.
"""

import sqlite3
import logging
from datetime import datetime
from typing import Dict, List, Set, Tuple

logger = logging.getLogger(__name__)


def _is_significant_change(designation: str) -> bool:
    """Check if a change involves a key leadership position."""
    d = (designation or "").lower()
    return any(kw in d for kw in [
        "chairman", "managing director", "ceo", "chief executive",
        "cfo", "chief financial", "whole time",
    ])


def detect_changes_for_company(conn: sqlite3.Connection, company_id: int,
                               company_symbol: str) -> List[Dict]:
    """Compare year-over-year management and log changes.

    Returns list of detected changes.
    """
    cursor = conn.execute(
        "SELECT DISTINCT fiscal_year FROM management_yearly "
        "WHERE company_id = ? ORDER BY fiscal_year",
        (company_id,)
    )
    years = [row[0] for row in cursor.fetchall()]

    if len(years) < 2:
        return []

    changes = []

    for i in range(1, len(years)):
        prev_year = years[i - 1]
        curr_year = years[i]

        # Get directors for each year
        prev_directors = {}
        for row in conn.execute(
            "SELECT person_name, designation FROM management_yearly "
            "WHERE company_id = ? AND fiscal_year = ?",
            (company_id, prev_year)
        ):
            prev_directors[row[0].upper()] = row[1]

        curr_directors = {}
        for row in conn.execute(
            "SELECT person_name, designation FROM management_yearly "
            "WHERE company_id = ? AND fiscal_year = ?",
            (company_id, curr_year)
        ):
            curr_directors[row[0].upper()] = row[1]

        prev_names = set(prev_directors.keys())
        curr_names = set(curr_directors.keys())

        # New appointments
        for name in curr_names - prev_names:
            desig = curr_directors[name]
            changes.append({
                "company_id": company_id,
                "fiscal_year": curr_year,
                "change_type": "appointment",
                "person_name": name.title(),
                "old_designation": None,
                "new_designation": desig,
            })

        # Departures
        for name in prev_names - curr_names:
            desig = prev_directors[name]
            changes.append({
                "company_id": company_id,
                "fiscal_year": curr_year,
                "change_type": "departure",
                "person_name": name.title(),
                "old_designation": desig,
                "new_designation": None,
            })

        # Redesignations (same person, different title)
        for name in prev_names & curr_names:
            prev_desig = prev_directors[name]
            curr_desig = curr_directors[name]
            if prev_desig and curr_desig and prev_desig != curr_desig:
                changes.append({
                    "company_id": company_id,
                    "fiscal_year": curr_year,
                    "change_type": "redesignation",
                    "person_name": name.title(),
                    "old_designation": prev_desig,
                    "new_designation": curr_desig,
                })

    return changes


def store_changes(conn: sqlite3.Connection, changes: List[Dict]):
    """Insert detected changes into management_changes table."""
    for change in changes:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO management_changes "
                "(company_id, fiscal_year, change_type, person_name, "
                "old_designation, new_designation) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    change["company_id"],
                    change["fiscal_year"],
                    change["change_type"],
                    change["person_name"],
                    change.get("old_designation"),
                    change.get("new_designation"),
                )
            )
        except sqlite3.IntegrityError:
            pass
    conn.commit()


def flag_companies_with_changes(conn: sqlite3.Connection):
    """Set management_change_flag=1 for companies with key management changes.

    A company is flagged if it has any of:
      - CMD/MD/CEO appointment or departure in recent 2 years
      - More than 3 board changes in a single year
    """
    cursor = conn.execute(
        "SELECT DISTINCT c.company_id, c.fiscal_year, c.change_type, "
        "c.new_designation, c.old_designation "
        "FROM management_changes c "
        "ORDER BY c.company_id, c.fiscal_year"
    )
    changes_by_company = {}
    for row in cursor.fetchall():
        cid = row[0]
        if cid not in changes_by_company:
            changes_by_company[cid] = []
        changes_by_company[cid].append({
            "fiscal_year": row[1],
            "change_type": row[2],
            "new_designation": row[3],
            "old_designation": row[4],
        })

    flagged = 0
    for company_id, company_changes in changes_by_company.items():
        should_flag = False

        # Check for key management changes
        for change in company_changes:
            desig = change.get("new_designation") or change.get("old_designation") or ""
            if _is_significant_change(desig):
                should_flag = True
                break

        # Check for high change volume in a single year
        from collections import Counter
        year_counts = Counter(c["fiscal_year"] for c in company_changes)
        if any(count > 3 for count in year_counts.values()):
            should_flag = True

        if should_flag:
            conn.execute(
                "UPDATE companies SET management_change_flag = 1 "
                "WHERE id = ?", (company_id,)
            )
            flagged += 1

    conn.commit()
    logger.info(f"Flagged {flagged} companies with significant management changes")
    return flagged
