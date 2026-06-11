from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import DB_PATH
from src.database import init_db


def print_rows(title: str, rows: list[sqlite3.Row]) -> None:
    print(f"\n[{title}]")
    for row in rows:
        print(tuple(row))


def main() -> int:
    init_db(DB_PATH)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        original_url_count = conn.execute(
            "SELECT COUNT(*) FROM items WHERE original_url IS NOT NULL AND original_url != ''"
        ).fetchone()[0]
        missing_record_id = conn.execute(
            """
            SELECT COUNT(*) FROM items
            WHERE COALESCE(is_mock, 0) != 1
              AND COALESCE(data_quality, 'real') NOT IN ('mock', 'sample', 'test')
              AND (source_record_id IS NULL OR source_record_id = '')
            """
        ).fetchone()[0]
        print(f"total items: {total}")
        print(f"items with original_url: {original_url_count}")
        print(f"real rows missing source_record_id: {missing_record_id}")
        exact_count = conn.execute("SELECT COUNT(*) FROM items WHERE link_type = 'exact'").fetchone()[0]
        exact_api_count = conn.execute("SELECT COUNT(*) FROM items WHERE link_type = 'exact_api'").fetchone()[0]
        search_portal_count = conn.execute("SELECT COUNT(*) FROM items WHERE link_type IN ('search', 'portal')").fetchone()[0]
        non_exact_original_count = conn.execute(
            """
            SELECT COUNT(*) FROM items
            WHERE original_url IS NOT NULL
              AND original_url != ''
              AND COALESCE(link_type, 'unknown') NOT IN ('exact', 'exact_api')
            """
        ).fetchone()[0]
        broken_count = conn.execute("SELECT COUNT(*) FROM items WHERE link_status = 'broken'").fetchone()[0]
        print(f"exact links: {exact_count}")
        print(f"exact_api links: {exact_api_count}")
        print(f"search/portal links: {search_portal_count}")
        print(f"original_url with non-exact link_type: {non_exact_original_count}")
        print(f"broken links: {broken_count}")

        print_rows(
            "data_quality counts",
            conn.execute(
                "SELECT COALESCE(data_quality, 'unknown') AS data_quality, COUNT(*) FROM items GROUP BY data_quality"
            ).fetchall(),
        )
        print_rows(
            "link_type counts",
            conn.execute("SELECT COALESCE(link_type, 'unknown') AS link_type, COUNT(*) FROM items GROUP BY link_type").fetchall(),
        )
        print_rows(
            "link_status counts",
            conn.execute(
                "SELECT COALESCE(link_status, 'unknown') AS link_status, COUNT(*) FROM items GROUP BY link_status"
            ).fetchall(),
        )
        print_rows(
            "source_name counts",
            conn.execute("SELECT source_name, COUNT(*) FROM items GROUP BY source_name ORDER BY COUNT(*) DESC").fetchall(),
        )
        print_rows(
            "source exact link coverage",
            conn.execute(
                """
                SELECT source_name,
                       COUNT(*) AS total,
                       SUM(CASE WHEN link_type IN ('exact', 'exact_api') AND original_url IS NOT NULL AND original_url != '' THEN 1 ELSE 0 END) AS exact_links,
                       ROUND(100.0 * SUM(CASE WHEN link_type IN ('exact', 'exact_api') AND original_url IS NOT NULL AND original_url != '' THEN 1 ELSE 0 END) / COUNT(*), 1) AS exact_pct
                FROM items
                GROUP BY source_name
                ORDER BY total DESC
                """
            ).fetchall(),
        )
        print_rows(
            "source_type counts",
            conn.execute("SELECT source_type, COUNT(*) FROM items GROUP BY source_type ORDER BY COUNT(*) DESC").fetchall(),
        )
        print_rows(
            "recent 20 rows",
            conn.execute(
                """
                SELECT title, source_name, COALESCE(data_quality, 'unknown'), COALESCE(link_type, 'unknown')
                FROM items
                ORDER BY id DESC
                LIMIT 20
                """
            ).fetchall(),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
