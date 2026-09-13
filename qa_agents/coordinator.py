"""QA Coordinator — orchestrates all agents, holdout validation, and reporting.

Usage:
    python -m qa_agents.coordinator                    # Run all agents + holdout + summary
    python -m qa_agents.coordinator --agent pnl_flow   # Run a single agent
    python -m qa_agents.coordinator --holdout           # Run holdout validation only
    python -m qa_agents.coordinator --summary           # Print summary only (from last run)
    python -m qa_agents.coordinator --showboat          # Generate Showboat demo document
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Any

from qa_agents.models import AgentResult, Finding, Severity
from qa_agents.pnl_flow_agent import PnlFlowAgent
from qa_agents.balance_sheet_agent import BalanceSheetAgent
from qa_agents.cash_flow_agent import CashFlowAgent
from qa_agents.cross_statement_agent import CrossStatementAgent
from qa_agents.trend_anomaly_agent import TrendAnomalyAgent
from qa_agents.completeness_agent import CompletenessAgent
from qa_agents.holdout_validator import HoldoutValidator


DEFAULT_DB = str(Path(__file__).parent.parent / "data" / "financial_profiles.db")
REPORT_DIR = Path(__file__).parent.parent / "qa_reports"

AGENT_MAP = {
    "pnl_flow": PnlFlowAgent,
    "balance_sheet": BalanceSheetAgent,
    "cash_flow": CashFlowAgent,
    "cross_statement": CrossStatementAgent,
    "trend_anomaly": TrendAnomalyAgent,
    "completeness": CompletenessAgent,
}


def load_all_companies(db_path: str) -> List[Dict[str, Any]]:
    """Load all company data from the database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        companies = []
        for row in conn.execute("SELECT * FROM companies ORDER BY nse_symbol"):
            company = dict(row)
            cid = company["id"]
            company["profit_loss"] = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM profit_loss WHERE company_id=? ORDER BY fiscal_year", (cid,))
            ]
            company["balance_sheet"] = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM balance_sheet WHERE company_id=? ORDER BY fiscal_year", (cid,))
            ]
            company["cash_flow"] = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM cash_flow WHERE company_id=? ORDER BY fiscal_year", (cid,))
            ]
            companies.append(company)
        return companies
    finally:
        conn.close()


def run_agent(agent_name: str, companies: List[Dict[str, Any]]) -> AgentResult:
    """Run a single agent and return its result."""
    agent_cls = AGENT_MAP.get(agent_name)
    if not agent_cls:
        print(f"Unknown agent: {agent_name}", file=sys.stderr)
        sys.exit(1)
    agent = agent_cls()
    return agent.run(companies)


def run_all_agents(companies: List[Dict[str, Any]]) -> List[AgentResult]:
    """Run all 6 agents sequentially."""
    results = []
    for name, cls in AGENT_MAP.items():
        agent = cls()
        result = agent.run(companies)
        results.append(result)
    return results


def format_agent_report(result: AgentResult) -> str:
    """Format a single agent's results as human-readable text."""
    lines = []
    lines.append("=" * 70)
    lines.append(f"AGENT: {result.agent_name}")
    lines.append("=" * 70)
    lines.append(result.summary_line())
    lines.append("")

    if not result.findings:
        lines.append("  No issues found.")
        lines.append("")
        return "\n".join(lines)

    # Group findings by severity
    errors = [f for f in result.findings if f.severity == Severity.ERROR]
    warnings = [f for f in result.findings if f.severity == Severity.WARNING]
    infos = [f for f in result.findings if f.severity == Severity.INFO]

    lines.append(f"  Errors: {len(errors)}  |  Warnings: {len(warnings)}  |  Info: {len(infos)}")
    lines.append("")

    # Show errors first (up to 20), then warnings (up to 20), then infos (up to 10)
    for label, items, limit in [("ERRORS", errors, 20), ("WARNINGS", warnings, 20), ("INFO", infos, 10)]:
        if not items:
            continue
        lines.append(f"  --- {label} ({len(items)} total, showing up to {limit}) ---")
        for f in items[:limit]:
            lines.append(f"  [{f.severity.value.upper()}] {f.company_symbol} | {f.fiscal_year} | "
                         f"Rule {f.rule_id}")
            lines.append(f"    {f.message}")
            if f.expected and f.actual:
                lines.append(f"    Expected: {f.expected}  |  Actual: {f.actual}")
        if len(items) > limit:
            lines.append(f"  ... and {len(items) - limit} more {label.lower()}")
        lines.append("")

    return "\n".join(lines)


def format_pyramid_summary(agent_results: List[AgentResult],
                           holdout_result: Dict[str, Any] = None) -> str:
    """Format 3-level Pyramid Summary."""
    lines = []

    # Level 1: Executive one-liner
    total_checks = sum(r.total_checks for r in agent_results)
    total_passed = sum(r.passed for r in agent_results)
    total_failed = sum(r.failed for r in agent_results)
    overall_satisfaction = (total_passed / total_checks * 100) if total_checks > 0 else 100.0

    all_findings = []
    for r in agent_results:
        all_findings.extend(r.findings)
    error_count = sum(1 for f in all_findings if f.severity == Severity.ERROR)
    warning_count = sum(1 for f in all_findings if f.severity == Severity.WARNING)
    info_count = sum(1 for f in all_findings if f.severity == Severity.INFO)

    holdout_str = ""
    if holdout_result:
        h_acc = holdout_result["overall_accuracy"]
        h_count = holdout_result["holdout_count"]
        holdout_str = f" | Holdout: {h_acc:.0f}% ({h_count} companies)"

    lines.append("=" * 70)
    lines.append("PYRAMID SUMMARY")
    lines.append("=" * 70)
    lines.append("")
    lines.append("LEVEL 1 — Executive Summary")
    lines.append("-" * 40)
    lines.append(f"Data Health: {overall_satisfaction:.1f}% satisfaction | "
                 f"{error_count} errors, {warning_count} warnings, {info_count} info | "
                 f"{total_checks} checks{holdout_str}")
    lines.append("")

    # Level 2: Per-agent table
    lines.append("LEVEL 2 — Agent Performance")
    lines.append("-" * 40)
    lines.append(f"  {'Agent':<20s} {'Checks':>7s} {'Passed':>7s} {'Failed':>7s} {'Satisfaction':>13s}")
    lines.append(f"  {'-'*20} {'-'*7} {'-'*7} {'-'*7} {'-'*13}")
    for r in agent_results:
        lines.append(f"  {r.agent_name:<20s} {r.total_checks:>7d} {r.passed:>7d} "
                     f"{r.failed:>7d} {r.satisfaction:>12.1f}%")
    if holdout_result:
        h = holdout_result
        lines.append(f"  {'HOLDOUT':<20s} {h['total_fields_checked']:>7d} {h['total_matched']:>7d} "
                     f"{h['total_mismatches']:>7d} {h['overall_accuracy']:>12.1f}%")
    lines.append("")

    # Level 3: Top findings per agent
    lines.append("LEVEL 3 — Top Findings by Agent")
    lines.append("-" * 40)
    for r in agent_results:
        if not r.findings:
            continue
        errors = [f for f in r.findings if f.severity == Severity.ERROR]
        warnings = [f for f in r.findings if f.severity == Severity.WARNING]
        top = (errors + warnings)[:5]
        if not top:
            continue
        lines.append(f"  {r.agent_name}:")
        for f in top:
            lines.append(f"    [{f.severity.value.upper()}] {f.company_symbol} | {f.fiscal_year} | "
                         f"Rule {f.rule_id}: {f.message[:80]}")
        remaining = len(errors) + len(warnings) - len(top)
        if remaining > 0:
            lines.append(f"    ... and {remaining} more errors/warnings")
        lines.append("")

    return "\n".join(lines)


def save_json_report(agent_results: List[AgentResult],
                     holdout_result: Dict[str, Any] = None) -> str:
    """Save full results as JSON for machine consumption."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    # Serialize holdout result (convert HoldoutResult objects)
    serialized_holdout = None
    if holdout_result:
        serialized_holdout = {
            "holdout_count": holdout_result["holdout_count"],
            "total_fields_checked": holdout_result["total_fields_checked"],
            "total_matched": holdout_result["total_matched"],
            "total_mismatches": holdout_result["total_mismatches"],
            "overall_accuracy": holdout_result["overall_accuracy"],
            "per_company": [
                {
                    "nse_symbol": r.nse_symbol,
                    "accuracy": r.accuracy,
                    "total_fields": r.total_fields,
                    "matched": r.matched,
                    "mismatches": r.mismatches,
                }
                for r in holdout_result["per_company"]
            ],
        }
    report = {
        "agents": [],
        "holdout": serialized_holdout,
    }
    for r in agent_results:
        agent_data = {
            "name": r.agent_name,
            "total_checks": r.total_checks,
            "passed": r.passed,
            "failed": r.failed,
            "satisfaction": round(r.satisfaction, 2),
            "findings": [
                {
                    "company_symbol": f.company_symbol,
                    "company_name": f.company_name,
                    "fiscal_year": f.fiscal_year,
                    "rule_id": f.rule_id,
                    "severity": f.severity.value,
                    "message": f.message,
                    "expected": f.expected,
                    "actual": f.actual,
                }
                for f in r.findings
            ],
        }
        report["agents"].append(agent_data)

    filepath = REPORT_DIR / "qa_validation_results.json"
    with open(filepath, "w") as fh:
        json.dump(report, fh, indent=2)
    return str(filepath)


def save_text_report(agent_results: List[AgentResult],
                     holdout_result: Dict[str, Any] = None) -> str:
    """Save human-readable text report."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("FINANCIAL DATA Q&A VALIDATION REPORT")
    lines.append(f"Database: {DEFAULT_DB}")
    lines.append(f"Companies: {len(set(f.company_symbol for r in agent_results for f in r.findings)) or 'all checked'}")
    lines.append("")

    # Pyramid summary
    lines.append(format_pyramid_summary(agent_results, holdout_result))
    lines.append("")

    # Individual agent reports
    for r in agent_results:
        lines.append(format_agent_report(r))

    # Holdout report
    if holdout_result:
        hv = HoldoutValidator(DEFAULT_DB)
        lines.append(hv.format_report(holdout_result))

    filepath = REPORT_DIR / "qa_validation_report.txt"
    with open(filepath, "w") as fh:
        fh.write("\n".join(lines))
    return str(filepath)


def generate_showboat_report(db_path: str) -> str:
    """Generate a Showboat executable demo document."""
    report_path = str(REPORT_DIR / "qa_report.md")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    project_root = str(Path(__file__).parent.parent)
    showboat_cmd = "showboat"

    def run_showboat(args: List[str]):
        subprocess.run([showboat_cmd] + args, cwd=project_root,
                       capture_output=True, text=True)

    def run_showboat_exec(report: str, code: str):
        result = subprocess.run(
            [showboat_cmd, "exec", report, "bash", code],
            cwd=project_root, capture_output=True, text=True
        )
        return result.stdout

    # Initialize
    run_showboat(["init", report_path, "Financial Data Q&A Validation Report"])

    # Overview note
    run_showboat(["note", report_path,
                  "Validation of 500+ Indian equity companies against IndAS accounting "
                  "principles using a 6-agent swarm with holdout ground-truth verification.\n\n"
                  "**Agents:** P&L Flow | Balance Sheet | Cash Flow | Cross-Statement | "
                  "Trend Anomaly | Completeness\n\n"
                  "**Holdout:** 10 benchmark companies verified against annual reports"])

    # Run each agent
    for agent_name in AGENT_MAP.keys():
        label = AGENT_MAP[agent_name].name
        run_showboat(["note", report_path, f"## Agent: {label}"])
        output = run_showboat_exec(
            report_path,
            f"cd {project_root} && python -m qa_agents.coordinator --agent {agent_name}"
        )

    # Holdout validation
    run_showboat(["note", report_path, "## Holdout Validation (Phase 2 — Independent Ground Truth)"])
    run_showboat_exec(report_path,
                      f"cd {project_root} && python -m qa_agents.coordinator --holdout")

    # Full summary
    run_showboat(["note", report_path, "## Overall Data Health — Pyramid Summary"])
    run_showboat_exec(report_path,
                      f"cd {project_root} && python -m qa_agents.coordinator --summary")

    return report_path


def main():
    parser = argparse.ArgumentParser(description="Q&A Agent Swarm Coordinator")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to SQLite database")
    parser.add_argument("--agent", choices=list(AGENT_MAP.keys()),
                        help="Run a single agent")
    parser.add_argument("--holdout", action="store_true",
                        help="Run holdout validation only")
    parser.add_argument("--summary", action="store_true",
                        help="Run all agents + holdout and print summary")
    parser.add_argument("--showboat", action="store_true",
                        help="Generate Showboat demo document")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON instead of text")
    args = parser.parse_args()

    db_path = args.db

    if args.showboat:
        report_path = generate_showboat_report(db_path)
        print(f"Showboat report generated: {report_path}")
        return

    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    if args.holdout:
        hv = HoldoutValidator(db_path)
        result = hv.validate()
        if args.json:
            # Convert HoldoutResult objects for JSON serialization
            serializable = {
                "holdout_count": result["holdout_count"],
                "total_fields_checked": result["total_fields_checked"],
                "total_matched": result["total_matched"],
                "total_mismatches": result["total_mismatches"],
                "overall_accuracy": result["overall_accuracy"],
                "per_company": [
                    {
                        "nse_symbol": r.nse_symbol,
                        "accuracy": r.accuracy,
                        "total_fields": r.total_fields,
                        "matched": r.matched,
                        "mismatches": r.mismatches,
                    }
                    for r in result["per_company"]
                ]
            }
            print(json.dumps(serializable, indent=2))
        else:
            print(hv.format_report(result))
        return

    # Load data
    print(f"Loading companies from {db_path}...", file=sys.stderr)
    companies = load_all_companies(db_path)
    print(f"Loaded {len(companies)} companies.", file=sys.stderr)

    if args.agent:
        # Single agent mode
        result = run_agent(args.agent, companies)
        if args.json:
            print(json.dumps({
                "name": result.agent_name,
                "satisfaction": round(result.satisfaction, 2),
                "total_checks": result.total_checks,
                "passed": result.passed,
                "failed": result.failed,
            }, indent=2))
        else:
            print(format_agent_report(result))
        return

    # Full run: all agents + holdout + summary
    print("Running all agents...", file=sys.stderr)
    agent_results = run_all_agents(companies)

    print("Running holdout validation...", file=sys.stderr)
    hv = HoldoutValidator(db_path)
    holdout_result = hv.validate(
        [f for r in agent_results for f in r.findings]
    )

    # Print summary
    if args.json:
        json_path = save_json_report(agent_results, holdout_result)
        print(f"JSON report saved: {json_path}", file=sys.stderr)
        with open(json_path) as fh:
            print(fh.read())
    else:
        text_path = save_text_report(agent_results, holdout_result)
        print(f"Text report saved: {text_path}", file=sys.stderr)
        print(format_pyramid_summary(agent_results, holdout_result))

    # Always save both reports
    save_json_report(agent_results, holdout_result)
    save_text_report(agent_results, holdout_result)


if __name__ == "__main__":
    main()
