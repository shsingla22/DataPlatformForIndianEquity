"""
Financial Data Platform for Indian Equity Markets

Main entry point for the data collection pipeline.

Usage:
    # Run full pipeline (discover companies and scrape all)
    python main.py

    # Process specific companies
    python main.py --symbols RELIANCE TCS INFY HDFCBANK

    # Export data only (assumes data is already collected)
    python main.py --export-only

    # Validate data only
    python main.py --validate-only

    # Set custom rate limit delay (seconds between requests)
    python main.py --delay 3.0
"""

import argparse
import logging
import json
import sys

from src.pipeline import Pipeline
from src.exporters import DataExporter
from src.validators import DataValidator
from src.models import init_db, get_db_connection
from src.config import DB_PATH, MIN_MARKET_CAP_CRORES


def main():
    parser = argparse.ArgumentParser(
        description="Financial Data Platform for Indian Equity Markets"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Specific NSE symbols to process (e.g., RELIANCE TCS INFY)",
    )
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Only export data (skip scraping)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate data (skip scraping)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay between requests in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Re-process companies already in the database",
    )
    parser.add_argument(
        "--db-path",
        default=DB_PATH,
        help="Path to SQLite database file",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    if args.export_only:
        print("Exporting data...")
        exporter = DataExporter(args.db_path)
        exporter.export_all()
        summary = exporter.generate_summary_report()
        print(f"\nSummary: {json.dumps(summary, indent=2)}")
        return

    if args.validate_only:
        print("Validating data...")
        validator = DataValidator(args.db_path)
        errors = validator.validate_all()
        summary = validator.get_summary()
        print(f"\nValidation Summary: {json.dumps(summary, indent=2)}")
        if errors:
            print(f"\nFirst 20 issues:")
            for error in errors[:20]:
                print(f"  {error}")
        return

    # Run full pipeline
    pipeline = Pipeline(
        db_path=args.db_path,
        rate_limit_delay=args.delay,
    )

    stats = pipeline.run(
        symbols=args.symbols,
        skip_existing=not args.no_skip_existing,
    )

    # Return non-zero exit code if there were failures
    if stats["companies_failed"] > stats["companies_with_data"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
