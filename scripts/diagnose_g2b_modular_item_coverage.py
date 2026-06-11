from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import DB_PATH
from src.database import init_db


def main() -> int:
    init_db(DB_PATH)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        total_g2b = scalar(conn, "SELECT COUNT(*) FROM items WHERE source_name='나라장터'")
        goods = scalar(conn, "SELECT COUNT(*) FROM items WHERE source_name='나라장터' AND business_type='물품'")
        modular_goods = scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM items
            WHERE source_name='나라장터'
              AND business_type='물품'
              AND REPLACE(LOWER(title), ' ', '') LIKE '%모듈러%'
            """,
        )
        missing_record_id = scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM items
            WHERE source_name='나라장터'
              AND business_type='물품'
              AND REPLACE(LOWER(title), ' ', '') LIKE '%모듈러%'
              AND (source_record_id IS NULL OR source_record_id='')
            """,
        )
        missing_order = scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM items
            WHERE source_name='나라장터'
              AND business_type='물품'
              AND REPLACE(LOWER(title), ' ', '') LIKE '%모듈러%'
              AND (source_record_no IS NULL OR source_record_no='')
            """,
        )
        cancelled = scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM items
            WHERE source_name='나라장터'
              AND business_type='물품'
              AND REPLACE(LOWER(title), ' ', '') LIKE '%모듈러%'
              AND COALESCE(notice_status, '') LIKE '%취소%'
            """,
        )
        correction = scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM items
            WHERE source_name='나라장터'
              AND business_type='물품'
              AND REPLACE(LOWER(title), ' ', '') LIKE '%모듈러%'
              AND (COALESCE(notice_status, '') LIKE '%정정%' OR COALESCE(notice_status, '') LIKE '%변경%')
            """,
        )

        print(f"전체 나라장터 공고 수: {total_g2b}")
        print(f"나라장터 물품 공고 수: {goods}")
        print(f"나라장터 물품 + 공고명 모듈러 포함 수: {modular_goods}")
        print(f"source_record_id 누락 건수: {missing_record_id}")
        print(f"공고차수 누락 건수: {missing_order}")
        print(f"취소공고 건수: {cancelled}")
        print(f"정정/변경공고 건수: {correction}")
        print("\n최근 20개 나라장터 모듈러 물품 공고:")

        rows = conn.execute(
            """
            SELECT id, title, source_record_id, source_record_no, notice_status,
                   business_type, organization, posted_at, due_at, amount
            FROM items
            WHERE source_name='나라장터'
              AND business_type='물품'
              AND REPLACE(LOWER(title), ' ', '') LIKE '%모듈러%'
            ORDER BY COALESCE(posted_at, created_at) DESC, id DESC
            LIMIT 20
            """
        ).fetchall()
        for row in rows:
            print(dict(row))

    return 0


def scalar(conn: sqlite3.Connection, query: str) -> int:
    return int(conn.execute(query).fetchone()[0])


if __name__ == "__main__":
    raise SystemExit(main())
