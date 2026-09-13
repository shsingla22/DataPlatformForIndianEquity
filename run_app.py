#!/usr/bin/env python3
"""Launch the Indian Equity Financial Data Platform.

Usage
-----
    python run_app.py                   # default: 0.0.0.0:8000
    python run_app.py --port 3000       # custom port
    API_HOST=127.0.0.1 python run_app.py
"""

import argparse
import os
import sys

import uvicorn

from api.config import API_HOST, API_PORT, DB_PATH


def main():
    parser = argparse.ArgumentParser(description="Indian Equity Financial Data Platform")
    parser.add_argument("--host", default=API_HOST, help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=API_PORT, help="Bind port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    args = parser.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        print("Run the data pipeline first:  python main.py")
        sys.exit(1)

    print(f"Starting Indian Equity Financial Data Platform")
    print(f"  Database : {DB_PATH}")
    print(f"  API      : http://{args.host}:{args.port}/docs")
    print(f"  UI       : http://{args.host}:{args.port}/")
    print()

    uvicorn.run(
        "api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
