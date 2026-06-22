from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.collectors.public_housing_contests.gh import collect_gh_public_housing_contests  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect GH private-participation public housing contests.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Collect and print summary without writing DB.")
    mode.add_argument("--apply", action="store_true", help="Collect and upsert records into DB.")
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--lookback-days", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--known-record-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dry_run = not args.apply
    stats = collect_gh_public_housing_contests(
        dry_run=dry_run,
        max_pages=args.max_pages,
        lookback_days=args.lookback_days,
        limit=args.limit,
        known_record_only=args.known_record_only,
    )
    print(json.dumps(stats.summary(), ensure_ascii=False, indent=2))
    return 0 if stats.records or stats.scanned or args.known_record_only else 1


if __name__ == "__main__":
    raise SystemExit(main())
