from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import DB_PATH
from src.database import init_db


G2B_SOURCE_NAMES = ("나라장터", "G2B", "조달청", "나라장터/G2B", "?섎씪?ν꽣")


def print_rows(title: str, rows: list[sqlite3.Row]) -> None:
    print(f"\n[{title}]")
    for row in rows:
        print(tuple(row))


def main() -> int:
    init_db(DB_PATH)
    placeholders = ",".join("?" for _ in G2B_SOURCE_NAMES)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        bid_count = conn.execute("SELECT COUNT(*) FROM items WHERE source_type='bid'").fetchone()[0]
        title_candidates = conn.execute(
            """
            SELECT COUNT(*)
            FROM items
            WHERE title LIKE '%나라장터%'
               OR title LIKE '%G2B%'
               OR title LIKE '%조달청%'
               OR organization LIKE '%조달청%'
               OR summary LIKE '%나라장터%'
               OR summary LIKE '%조달청%'
            """
        ).fetchone()[0]
        g2b_candidates = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM items
            WHERE source_name IN ({placeholders})
              AND source_record_id IS NOT NULL
              AND source_record_id != ''
            """,
            G2B_SOURCE_NAMES,
        ).fetchone()[0]
        bid_fields = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM items
            WHERE source_name IN ({placeholders})
              AND source_record_id IS NOT NULL
              AND source_record_id != ''
              AND source_record_no IS NOT NULL
              AND source_record_no != ''
            """,
            G2B_SOURCE_NAMES,
        ).fetchone()[0]

        print(f"total items: {total}")
        print(f"source_type='bid' count: {bid_count}")
        print(f"title/org/summary contains 나라장터/G2B/조달청 count: {title_candidates}")
        print(f"G2B candidate rows with source_record_id: {g2b_candidates}")
        print(f"G2B rows with bidNtceNo and bidNtceOrd: {bid_fields}")
        print_rows(
            "source_name counts",
            conn.execute(
                "SELECT source_name, COUNT(*) FROM items GROUP BY source_name ORDER BY COUNT(*) DESC"
            ).fetchall(),
        )
        print_rows(
            "recent 20 rows",
            conn.execute(
                """
                SELECT source_name, source_type, title, source_record_id
                FROM items
                ORDER BY id DESC
                LIMIT 20
                """
            ).fetchall(),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
