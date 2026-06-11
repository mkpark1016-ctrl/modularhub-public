from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import DB_PATH
from src.database import init_db


def main() -> int:
    init_db(DB_PATH)
    with sqlite3.connect(DB_PATH) as conn:
        target_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM items
            WHERE COALESCE(link_type, 'unknown') IN ('search', 'portal', 'unknown', 'sample', 'mock')
               OR (original_url IS NOT NULL AND original_url != '' AND COALESCE(link_type, 'unknown') NOT IN ('exact', 'exact_api'))
            """
        ).fetchone()[0]
        conn.execute(
            """
            UPDATE items
            SET original_url = NULL,
                link_status = CASE
                    WHEN COALESCE(link_type, 'unknown') IN ('search', 'portal') THEN 'unknown'
                    ELSE COALESCE(link_status, 'unknown')
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE COALESCE(link_type, 'unknown') IN ('search', 'portal', 'unknown', 'sample', 'mock')
               OR (original_url IS NOT NULL AND original_url != '' AND COALESCE(link_type, 'unknown') NOT IN ('exact', 'exact_api'))
            """
        )
        remaining_bad = conn.execute(
            """
            SELECT COUNT(*)
            FROM items
            WHERE original_url IS NOT NULL
              AND original_url != ''
              AND COALESCE(link_type, 'unknown') NOT IN ('exact', 'exact_api')
            """
        ).fetchone()[0]
        print(f"rows cleaned: {target_count}")
        print(f"non-exact rows still holding original_url: {remaining_bad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
