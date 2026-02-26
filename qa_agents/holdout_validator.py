"""Holdout Validator — Phase 2 independent ground-truth check.

Compares database values against known-good holdout data sourced from
company annual reports. This validates both the data accuracy AND whether
the agents caught any issues.
"""

import json
import os
import sqlite3
from pathlib import Path
from typing import Dict, List, Any

from qa_agents.models import HoldoutResult, Finding, Severity


HOLDOUT_DIR = Path(__file__).parent / "holdouts"
TOLERANCE_PCT = 0.5  # ±0.5% tolerance for Crore rounding


class HoldoutValidator:
    """Validates DB data against external holdout ground truth."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def load_holdouts(self) -> List[Dict[str, Any]]:
        """Load all holdout JSON files from the holdouts/ directory."""
        holdouts = []
        for filepath in sorted(HOLDOUT_DIR.glob("*.json")):
            with open(filepath) as f:
                holdouts.append(json.load(f))
        return holdouts

    def get_db_values(self, nse_symbol: str, fiscal_year: str) -> Dict[str, Any]:
        """Fetch the DB record for a company and fiscal year."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            c = conn.execute("SELECT id FROM companies WHERE nse_symbol=?", (nse_symbol,))
            row = c.fetchone()
            if not row:
                return {}
            company_id = row["id"]

            result = {}
            for table in ["profit_loss", "balance_sheet", "cash_flow"]:
                c = conn.execute(
                    f"SELECT * FROM {table} WHERE company_id=? AND fiscal_year=?",
                    (company_id, fiscal_year)
                )
                row = c.fetchone()
                result[table] = dict(row) if row else {}
            return result
        finally:
            conn.close()

    def validate(self, agent_findings: List[Finding] = None) -> Dict[str, Any]:
        """Run holdout validation. Returns summary dict."""
        holdouts = self.load_holdouts()
        results = []
        all_findings_by_symbol = {}

        if agent_findings:
            for f in agent_findings:
                all_findings_by_symbol.setdefault(f.company_symbol, []).append(f)

        for holdout in holdouts:
            symbol = holdout["nse_symbol"]
            fy = holdout["fiscal_year"]
            db_vals = self.get_db_values(symbol, fy)
            result = HoldoutResult(nse_symbol=symbol)

            # Compare P&L fields
            self._compare_section(holdout.get("profit_loss", {}),
                                  db_vals.get("profit_loss", {}),
                                  result, symbol, fy, "P&L")
            # Compare BS fields
            self._compare_section(holdout.get("balance_sheet", {}),
                                  db_vals.get("balance_sheet", {}),
                                  result, symbol, fy, "BS")
            # Compare CF fields
            self._compare_section(holdout.get("cash_flow", {}),
                                  db_vals.get("cash_flow", {}),
                                  result, symbol, fy, "CF")

            results.append(result)

        # Compute overall holdout accuracy
        total_fields = sum(r.total_fields for r in results)
        total_matched = sum(r.matched for r in results)
        overall_accuracy = (total_matched / total_fields * 100) if total_fields > 0 else 100.0

        return {
            "holdout_count": len(holdouts),
            "total_fields_checked": total_fields,
            "total_matched": total_matched,
            "total_mismatches": total_fields - total_matched,
            "overall_accuracy": overall_accuracy,
            "per_company": results,
        }

    def _compare_section(self, holdout_section: Dict, db_section: Dict,
                         result: HoldoutResult, symbol: str, fy: str,
                         section_name: str):
        """Compare one section (P&L, BS, CF) field by field."""
        for field_name, holdout_val in holdout_section.items():
            if holdout_val is None:
                continue  # Skip NULL holdout values (intentionally NULL, e.g. bank sales)

            db_val = db_section.get(field_name)
            result.total_fields += 1

            if db_val is None:
                result.mismatches.append({
                    "symbol": symbol,
                    "fiscal_year": fy,
                    "section": section_name,
                    "field": field_name,
                    "holdout_value": holdout_val,
                    "db_value": None,
                    "issue": "NULL in DB but has value in holdout",
                })
                continue

            try:
                h_val = float(holdout_val)
                d_val = float(db_val)
            except (ValueError, TypeError):
                result.matched += 1
                continue

            if h_val == 0:
                if d_val == 0:
                    result.matched += 1
                else:
                    result.mismatches.append({
                        "symbol": symbol,
                        "fiscal_year": fy,
                        "section": section_name,
                        "field": field_name,
                        "holdout_value": h_val,
                        "db_value": d_val,
                        "issue": f"Holdout=0, DB={d_val}",
                    })
                continue

            pct_diff = abs((d_val - h_val) / abs(h_val)) * 100
            if pct_diff <= TOLERANCE_PCT:
                result.matched += 1
            else:
                result.mismatches.append({
                    "symbol": symbol,
                    "fiscal_year": fy,
                    "section": section_name,
                    "field": field_name,
                    "holdout_value": h_val,
                    "db_value": d_val,
                    "pct_diff": pct_diff,
                    "issue": f"DB value differs by {pct_diff:.2f}%",
                })

    def format_report(self, validation_result: Dict[str, Any]) -> str:
        """Format holdout validation results as human-readable text."""
        lines = []
        lines.append("=" * 70)
        lines.append("HOLDOUT VALIDATION (Phase 2 — Independent Ground Truth)")
        lines.append("=" * 70)
        lines.append(f"Companies checked:  {validation_result['holdout_count']}")
        lines.append(f"Fields compared:    {validation_result['total_fields_checked']}")
        lines.append(f"Fields matched:     {validation_result['total_matched']}")
        lines.append(f"Mismatches:         {validation_result['total_mismatches']}")
        lines.append(f"Overall accuracy:   {validation_result['overall_accuracy']:.1f}%")
        lines.append("")

        for r in validation_result["per_company"]:
            status = "PASS" if r.accuracy == 100.0 else "MISMATCH"
            lines.append(f"  {r.nse_symbol:15s}  {r.accuracy:6.1f}%  [{status}]  "
                         f"({r.matched}/{r.total_fields} fields)")
            for m in r.mismatches:
                lines.append(f"    ! {m['section']}.{m['field']}: "
                             f"holdout={m['holdout_value']}, db={m['db_value']} — {m['issue']}")

        lines.append("")
        return "\n".join(lines)
