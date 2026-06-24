from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.collectors.public_housing_contests.sh import collect_sh_public_housing_contests  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect SH private-participation public housing contest candidates.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Collect and print summary without writing DB.")
    mode.add_argument("--apply", action="store_true", help="Collect and upsert records into DB.")
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--lookback-days", type=int, default=None)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--list-url", default=None)
    parser.add_argument("--request-delay", type=float, default=None)
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stats = collect_sh_public_housing_contests(
        dry_run=not args.apply,
        max_pages=args.max_pages,
        lookback_days=args.lookback_days,
        start_date=args.start_date,
        end_date=args.end_date,
        list_url=args.list_url,
        request_interval_seconds=args.request_delay,
        timeout_seconds=args.timeout,
        verbose=args.verbose,
    )
    print(json.dumps(stats.summary(), ensure_ascii=False, indent=2))
    return 0 if stats.scanned or stats.status in {"success", "success_no_matches"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
