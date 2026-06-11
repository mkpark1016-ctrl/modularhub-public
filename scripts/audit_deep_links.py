from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import DATA_GO_KR_SERVICE_KEY, DB_PATH
from src.database import init_db


def print_rows(title: str, rows: list[sqlite3.Row]) -> None:
    print(f"\n[{title}]")
    for row in rows:
        print(tuple(_mask(value) for value in tuple(row)))


def _mask(value):
    if isinstance(value, str) and DATA_GO_KR_SERVICE_KEY:
        return value.replace(DATA_GO_KR_SERVICE_KEY, "[MASKED_SERVICE_KEY]")
    return value


def main() -> int:
    init_db(DB_PATH)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        print_rows(
            "source coverage",
            conn.execute(
                """
                SELECT source_name,
                       COUNT(*) AS total,
                       SUM(CASE WHEN original_url IS NOT NULL AND original_url != '' THEN 1 ELSE 0 END) AS original_url_count,
                       SUM(CASE WHEN COALESCE(exact_url_verified, 0) = 1 THEN 1 ELSE 0 END) AS verified_count,
                       SUM(CASE WHEN source_detail_api_url IS NOT NULL AND source_detail_api_url != '' THEN 1 ELSE 0 END) AS detail_api_count,
                       SUM(CASE WHEN link_type = 'exact_api' THEN 1 ELSE 0 END) AS exact_api_count,
                       SUM(CASE WHEN COALESCE(api_detail_verified, 0) = 1 THEN 1 ELSE 0 END) AS api_detail_verified_count
                FROM items
                WHERE COALESCE(is_mock, 0) != 1
                  AND COALESCE(data_quality, 'real') NOT IN ('mock', 'sample', 'test')
                GROUP BY source_name
                ORDER BY total DESC
                """
            ).fetchall(),
        )
        print_rows(
            "D2B coverage by source_type",
            conn.execute(
                """
                SELECT source_type,
                       COUNT(*) AS total,
                       SUM(CASE WHEN original_url IS NOT NULL AND original_url != '' THEN 1 ELSE 0 END) AS original_url_count,
                       SUM(CASE WHEN COALESCE(exact_url_verified, 0) = 1 THEN 1 ELSE 0 END) AS verified_count,
                       SUM(CASE WHEN COALESCE(exact_url_verified, 0) = 0
                                  AND exact_url_validation_reason IS NOT NULL
                                  AND exact_url_validation_reason != ''
                                THEN 1 ELSE 0 END) AS failed_count
                FROM items
                WHERE source_name = 'D2B'
                  AND COALESCE(is_mock, 0) != 1
                  AND COALESCE(data_quality, 'real') NOT IN ('mock', 'sample', 'test')
                GROUP BY source_type
                ORDER BY source_type
                """
            ).fetchall(),
        )
        print_rows(
            "link_type counts",
            conn.execute("SELECT COALESCE(link_type, 'unknown'), COUNT(*) FROM items GROUP BY link_type").fetchall(),
        )
        print_rows(
            "validation failures",
            conn.execute(
                """
                SELECT source_name, COUNT(*)
                FROM items
                WHERE COALESCE(exact_url_verified, 0) = 0
                  AND COALESCE(api_detail_verified, 0) = 0
                  AND exact_url_validation_reason IS NOT NULL
                  AND exact_url_validation_reason != ''
                GROUP BY source_name
                """
            ).fetchall(),
        )
        print_rows(
            "recent 20 failure reasons",
            conn.execute(
                """
                SELECT source_name, title, exact_url_candidate, exact_url_validation_reason
                FROM items
                WHERE COALESCE(exact_url_verified, 0) = 0
                  AND COALESCE(api_detail_verified, 0) = 0
                  AND exact_url_validation_reason IS NOT NULL
                  AND exact_url_validation_reason != ''
                ORDER BY updated_at DESC
                LIMIT 20
                """
            ).fetchall(),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
