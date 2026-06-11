from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collector_runner import run_collector
from src.collectors import MockCollector
from src.config import DB_PATH
from src.database import init_db
from src.dedup import make_unique_hash
from src.normalizer import normalize_item


def main() -> int:
    init_db(DB_PATH)
    collector = MockCollector()
    raw_items = collector.collect()
    print(f"raw item count: {len(raw_items)}")

    normalized = normalize_item(raw_items[0])
    print(f"normalized keys: {sorted(normalized.keys())}")
    unique_hash = make_unique_hash(normalized)
    print(f"unique_hash generated: {bool(unique_hash)}")

    result = run_collector(collector)
    print(
        f"collector run: status={result.status}, inserted={result.inserted_count}, "
        f"updated={result.updated_count}, skipped={result.skipped_count}"
    )

    with sqlite3.connect(DB_PATH) as conn:
        item_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        print(f"final items count: {item_count}")
        logs = conn.execute(
            """
            SELECT collector_name, source_type, started_at, finished_at, status,
                   inserted_count, updated_count, skipped_count, error_message
            FROM collect_logs
            ORDER BY id DESC
            LIMIT 5
            """
        ).fetchall()

    print("recent collect_logs:")
    for log in logs:
        print(log)

    if result.status != "success":
        print("collector flow failed")
        return 1
    print("COLLECTOR FLOW TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
