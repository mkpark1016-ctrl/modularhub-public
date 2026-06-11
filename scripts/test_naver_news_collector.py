from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collector_runner import run_collector
from src.collectors import NaverNewsCollector
from src.config import DB_PATH, NAVER_CLIENT_ID, NAVER_CLIENT_SECRET
from src.database import init_db


def main() -> int:
    init_db(DB_PATH)
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print("NAVER_CLIENT_ID or NAVER_CLIENT_SECRET is missing. Add them to .env before running this test.")
        result = run_collector(NaverNewsCollector())
        print(f"collector run status={result.status}, error={result.error_message}")
        return 1

    collector = NaverNewsCollector()
    print(f"collector created: {collector.get_source_name()}")
    try:
        items = collector.collect()
        print(f"collect result type: {type(items).__name__}")
        print(f"collected items: {len(items)}")
        if not isinstance(items, list):
            print("collect() did not return a list")
            return 1
        for item in items[:5]:
            for key in ("title", "source_name", "source_type", "url"):
                if key not in item:
                    print(f"missing key in collected item: {key}")
                    return 1
    except Exception as exc:
        print(f"collect() failed: {exc}")
        result = run_collector(collector)
        print(f"collector run status={result.status}, error={result.error_message}")
        return 1

    first = run_collector(collector)
    second = run_collector(collector)
    print(
        f"first run: status={first.status}, inserted={first.inserted_count}, "
        f"updated={first.updated_count}, skipped={first.skipped_count}"
    )
    print(
        f"second run: status={second.status}, inserted={second.inserted_count}, "
        f"updated={second.updated_count}, skipped={second.skipped_count}"
    )

    with sqlite3.connect(DB_PATH) as conn:
        log = conn.execute(
            "SELECT collector_name, status, inserted_count, updated_count, skipped_count, error_message "
            "FROM collect_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    print(f"latest collect_log: {log}")

    if first.status != "success" or second.status != "success":
        return 1
    print("NAVER NEWS COLLECTOR TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
