from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import DB_PATH
from src.database import init_db
from src.link_resolver import validate_exact_url


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate exact original links only.")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--clear-invalid", action="store_true", help="Clear original_url and mark invalid exact links unknown.")
    args = parser.parse_args()

    init_db(DB_PATH)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, title, original_url, link_type, source_record_id
            FROM items
            WHERE original_url IS NOT NULL
              AND original_url != ''
              AND link_type IN ('exact', 'exact_api')
              AND COALESCE(is_mock, 0) != 1
              AND COALESCE(data_quality, 'real') NOT IN ('mock', 'sample', 'test')
            ORDER BY COALESCE(link_checked_at, '') ASC, id DESC
            LIMIT ?
            """,
            (args.limit,),
        ).fetchall()

        print(f"exact links to check: {len(rows)}")
        for row in rows:
            result = validate_exact_url(row["original_url"], row["title"], row["source_record_id"] or "")
            status = "ok" if result["is_valid"] else "broken"
            if args.clear_invalid and status == "broken":
                conn.execute(
                    """
                    UPDATE items
                    SET original_url = NULL,
                        link_type = 'unknown',
                        link_status = 'unknown',
                        exact_url_verified = 0,
                        exact_url_verified_at = ?,
                        exact_url_validation_reason = ?,
                        link_checked_at = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (result["checked_at"], result["reason"], result["checked_at"], row["id"]),
                )
            else:
                conn.execute(
                    """
                    UPDATE items
                    SET link_status = ?,
                        link_checked_at = ?,
                        exact_url_verified = ?,
                        exact_url_verified_at = ?,
                        exact_url_validation_reason = ?,
                        exact_url_candidate = COALESCE(exact_url_candidate, original_url),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        status,
                        result["checked_at"],
                        1 if status == "ok" else 0,
                        result["checked_at"],
                        result["reason"],
                        row["id"],
                    ),
                )
            print(f"{status}: {result['reason']} ({result['status_code']}) {row['title'][:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
