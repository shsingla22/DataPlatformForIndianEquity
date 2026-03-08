"""CLI entry point for the dividend value screener.

Usage:
    python -m dividend_screener                   # Full screening (PSU + Private top 20 each)
    python -m dividend_screener --top 20          # Top N per category
    python -m dividend_screener --json            # JSON output
    python -m dividend_screener --out results.txt # Save to file
    python -m dividend_screener --store           # Store results in database
"""

import argparse
import sys
from pathlib import Path

from dividend_screener.screener import DB_PATH, load_company_data, rank_companies
from dividend_screener.report import format_summary, format_table, to_json
from dividend_screener.storage import store_results


def main():
    parser = argparse.ArgumentParser(
        description="Dividend Value Screener for Indian Equities"
    )
    parser.add_argument(
        "--db", default=DB_PATH,
        help="Path to the SQLite database"
    )
    parser.add_argument(
        "--top", type=int, default=20,
        help="Number of top companies per category (default: 20)"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "--out", type=str, default=None,
        help="Write output to a file"
    )
    parser.add_argument(
        "--table-only", action="store_true",
        help="Print only the ranked tables (no summary)"
    )
    parser.add_argument(
        "--store", action="store_true",
        help="Store results into the database"
    )
    args = parser.parse_args()

    all_metrics = load_company_data(args.db)
    if not all_metrics:
        print("No companies found with valid dividend data.", file=sys.stderr)
        sys.exit(1)

    ranked = rank_companies(all_metrics, len(all_metrics))  # rank all

    if args.json:
        output = to_json(all_metrics, args.top)
    elif args.table_only:
        psu = sorted(
            [m for m in all_metrics if m.ownership_type == "PSU"],
            key=lambda m: m.composite_score, reverse=True
        )[:args.top]
        private = sorted(
            [m for m in all_metrics if m.ownership_type == "Private"],
            key=lambda m: m.composite_score, reverse=True
        )[:args.top]
        output = (
            format_table(psu, f"TOP {len(psu)} PSU COMPANIES")
            + "\n\n"
            + format_table(private, f"TOP {len(private)} PRIVATE SECTOR COMPANIES")
        )
    else:
        output = format_summary(all_metrics, ranked, args.top)

    print(output)

    # Store results in the database
    if args.store:
        n = store_results(all_metrics, ranked, args.db)
        print(f"\nStored {n} company scores in database", file=sys.stderr)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w") as f:
            f.write(output)
        print(f"\nResults saved to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
