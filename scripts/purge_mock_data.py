from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import DB_PATH
from src.config import SAMPLE_CSV_PATH
from src.database import init_db


PURGE_WHERE = """
    COALESCE(is_mock, 0) = 1
    OR COALESCE(data_quality, '') IN ('mock', 'sample', 'test')
    OR LOWER(COALESCE(source_name, '')) LIKE '%mock%'
    OR LOWER(COALESCE(source_type, '')) LIKE '%mock%'
    OR LOWER(COALESCE(title, '')) LIKE '%mock%'
    OR LOWER(COALESCE(summary, '')) LIKE '%mock%'
    OR title LIKE '%샘플%'
    OR title LIKE '%테스트%'
"""


def main() -> int:
    init_db(DB_PATH)
    with sqlite3.connect(DB_PATH) as conn:
        before_total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        purge_count = conn.execute(f"SELECT COUNT(*) FROM items WHERE {PURGE_WHERE}").fetchone()[0]
        sample_titles = _sample_titles()
        if sample_titles:
            placeholders = ",".join("?" for _ in sample_titles)
            purge_count += conn.execute(
                f"SELECT COUNT(*) FROM items WHERE title IN ({placeholders}) AND NOT ({PURGE_WHERE})",
                sample_titles,
            ).fetchone()[0]
        print(f"total before: {before_total}")
        print(f"mock/sample/test rows to delete: {purge_count}")
        conn.execute(f"DELETE FROM items WHERE {PURGE_WHERE}")
        if sample_titles:
            placeholders = ",".join("?" for _ in sample_titles)
            conn.execute(f"DELETE FROM items WHERE title IN ({placeholders})", sample_titles)
        after_total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        print(f"total after: {after_total}")
        print(f"deleted: {before_total - after_total}")
    return 0


def _sample_titles() -> list[str]:
    if not SAMPLE_CSV_PATH.exists():
        return []
    lines = SAMPLE_CSV_PATH.read_text(encoding="utf-8-sig").splitlines()
    if len(lines) <= 1:
        return []
    import csv

    rows = csv.DictReader(lines)
    return [row["title"] for row in rows if row.get("title")]


if __name__ == "__main__":
    raise SystemExit(main())
