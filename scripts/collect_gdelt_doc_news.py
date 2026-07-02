from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.collector_runner import run_collector  # noqa: E402
from src.collectors.gdelt_doc_news import GdeltDocNewsCollector  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect GDELT DOC overseas modular news.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Fetch and filter candidates without writing to DB.")
    mode.add_argument("--apply", action="store_true", help="Write filtered candidates through the normal collector runner.")
    parser.add_argument("--timespan", help="GDELT DOC timespan, for example 7d.")
    parser.add_argument("--max-records", type=int, help="GDELT DOC maxrecords, clamped to 1..250.")
    parser.add_argument("--show-limit", type=int, default=10, help="Number of candidates to print in dry-run output.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    dry_run = not args.apply
    collector = GdeltDocNewsCollector(timespan=args.timespan, max_records=args.max_records)

    if dry_run:
        try:
            items = collector.collect()
        except Exception as exc:
            print(f"GDELT DOC dry-run failed: {exc}")
            print(f"request_count={collector.request_count}")
            return 1
        print("GDELT DOC dry-run completed")
        print(f"request_count={collector.request_count}")
        for key in sorted(collector.stats):
            print(f"{key}={collector.stats[key]}")
        for index, item in enumerate(items[: max(0, args.show_limit)], start=1):
            print(
                f"{index}. score={item.get('relevance_score')} "
                f"country={item.get('region') or '-'} domain={item.get('organization') or '-'} "
                f"title={item.get('title')} url={item.get('url')}"
            )
        return 0

    result = run_collector(collector)
    print(
        f"{result.collector_name}: status={result.status}, inserted={result.inserted_count}, "
        f"updated={result.updated_count}, skipped={result.skipped_count}, request_count={collector.request_count}"
    )
    if result.error_message:
        print(f"error: {result.error_message}")
    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
