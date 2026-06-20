from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.collectors.public_housing_contests.lh import collect_lh_public_housing_contests  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect LH private participation public housing contests.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Fetch and parse LH contests without writing DB.")
    mode.add_argument("--apply", action="store_true", help="Write parsed LH contests to DB and source_details.")
    parser.add_argument("--max-pages", type=int, default=None, help="Maximum LH list pages to scan.")
    parser.add_argument("--lookback-days", type=int, default=None, help="Skip list items older than this many days.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum matched records to collect.")
    parser.add_argument("--known-record-only", action="store_true", help="Fetch configured known LH records only.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dry_run = not args.apply
    stats = collect_lh_public_housing_contests(
        dry_run=dry_run,
        max_pages=args.max_pages,
        lookback_days=args.lookback_days,
        limit=args.limit,
        known_record_only=args.known_record_only,
    )
    print(json.dumps(stats.summary(), ensure_ascii=False, indent=2))
    for record in stats.records[:10]:
        print(
            f"- {record.source_record_id} | {record.notice_stage} | "
            f"{record.modular_relevance} | attachments={len(record.attachments)} | {record.title}"
        )
    if dry_run:
        print("dry-run only: DB was not modified.")
    return 0 if not stats.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
