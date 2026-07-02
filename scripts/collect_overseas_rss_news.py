from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.collector_runner import run_collector  # noqa: E402
from src.collectors.overseas_rss_news import OverseasRssNewsCollector  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect overseas modular construction RSS news.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Fetch RSS feeds without writing to DB.")
    mode.add_argument("--apply", action="store_true", help="Write filtered RSS candidates through run_collector.")
    parser.add_argument("--show-limit", type=int, default=10, help="Number of candidates to print.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    dry_run = not args.apply
    collector = OverseasRssNewsCollector()

    if dry_run:
        try:
            items = collector.collect()
        except Exception as exc:
            print(f"Overseas RSS dry-run failed: {exc}")
            print_stats(collector)
            return 1
        print("Overseas RSS dry-run completed")
        print_stats(collector)
        for index, item in enumerate(items[: max(0, args.show_limit)], start=1):
            print(
                console_text(
                    f"{index}. score={item.get('relevance_score')} "
                    f"source={item.get('organization') or '-'} posted_at={item.get('posted_at') or '-'} "
                    f"title={item.get('title')} url={item.get('url')}"
                )
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


def print_stats(collector: OverseasRssNewsCollector) -> None:
    print(f"request_count={collector.request_count}")
    for key in (
        "feed_count",
        "successful_feed_count",
        "failed_feed_count",
        "fetched_item_count",
        "relevance_excluded_count",
        "date_excluded_count",
        "duplicate_excluded_count",
        "returned_count",
    ):
        print(f"{key}={collector.stats.get(key)}")
    if collector.stats.get("feed_errors"):
        print(console_text(f"feed_errors={collector.stats.get('feed_errors')}"))


def console_text(value: str) -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return value.encode(encoding, errors="replace").decode(encoding, errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())
