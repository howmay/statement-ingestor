#!/usr/bin/env python3

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.integrations.gmail.auth import get_gmail_service
from src.integrations.gmail.search_analysis import (
    analysis_to_json,
    fetch_attachment_email_records,
    recommend_search_filters,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Gmail statement-search candidates and recommend filters.")
    parser.add_argument("--date-from", default="2026-02-01", help="Inclusive start date, default: 2026-02-01")
    parser.add_argument("--date-to", default=datetime.now(UTC).strftime("%Y-%m-%d"), help="Inclusive end date")
    parser.add_argument("--max-results", type=int, default=None, help="Optional fetch cap for faster exploration")
    args = parser.parse_args()

    service = get_gmail_service()
    records = fetch_attachment_email_records(
        service,
        date_from=args.date_from,
        date_to=args.date_to,
        max_results=args.max_results,
    )
    result = recommend_search_filters(records)
    print(analysis_to_json({
        "date_from": args.date_from,
        "date_to": args.date_to,
        "records": records,
        "recommendation": result,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
