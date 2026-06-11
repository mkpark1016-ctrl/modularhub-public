from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import DB_PATH
from src.database import init_db


G2B_SOURCES = ("나라장터", "G2B", "조달청")


def scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    return int(conn.execute(sql, params).fetchone()[0] or 0)


def main() -> int:
    init_db(DB_PATH)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        source_placeholders = ",".join("?" for _ in G2B_SOURCES)
        source_params = G2B_SOURCES
        print(f"DB: {DB_PATH}")
        print(
            "나라장터 전체 수집 건수:",
            scalar(conn, f"SELECT COUNT(*) FROM items WHERE source_name IN ({source_placeholders})", source_params),
        )
        print(
            "물품 모듈러 건수:",
            scalar(
                conn,
                f"""
                SELECT COUNT(*) FROM items
                WHERE source_name IN ({source_placeholders})
                  AND business_type = '물품'
                  AND REPLACE(COALESCE(title, ''), ' ', '') LIKE '%모듈러%'
                """,
                source_params,
            ),
        )
        print(
            "용역 모듈러 건수:",
            scalar(
                conn,
                f"""
                SELECT COUNT(*) FROM items
                WHERE source_name IN ({source_placeholders})
                  AND business_type = '용역'
                  AND REPLACE(COALESCE(title, ''), ' ', '') LIKE '%모듈러%'
                """,
                source_params,
            ),
        )
        print(
            "일반용역 후보 건수:",
            scalar(
                conn,
                f"""
                SELECT COUNT(*) FROM items
                WHERE source_name IN ({source_placeholders})
                  AND business_type = '용역'
                  AND COALESCE(business_subtype, '') <> ''
                """,
                source_params,
            ),
        )
        print(
            "operating_scope='modular_goods_service' 건수:",
            scalar(conn, "SELECT COUNT(*) FROM items WHERE operating_scope = 'modular_goods_service'"),
        )
        print(
            "source_record_id 누락 건수:",
            scalar(
                conn,
                f"""
                SELECT COUNT(*) FROM items
                WHERE source_name IN ({source_placeholders})
                  AND operating_scope = 'modular_goods_service'
                  AND COALESCE(source_record_id, '') = ''
                """,
                source_params,
            ),
        )
        print(
            "공고차수 누락 건수:",
            scalar(
                conn,
                f"""
                SELECT COUNT(*) FROM items
                WHERE source_name IN ({source_placeholders})
                  AND operating_scope = 'modular_goods_service'
                  AND COALESCE(source_record_no, '') = ''
                """,
                source_params,
            ),
        )
        print(
            "취소/정정공고 건수:",
            scalar(
                conn,
                f"""
                SELECT COUNT(*) FROM items
                WHERE source_name IN ({source_placeholders})
                  AND operating_scope = 'modular_goods_service'
                  AND (
                    COALESCE(notice_status, '') LIKE '%취소%'
                    OR COALESCE(notice_status, '') LIKE '%정정%'
                    OR COALESCE(notice_status, '') LIKE '%변경%'
                  )
                """,
                source_params,
            ),
        )
        rows = conn.execute(
            f"""
            SELECT id, business_type, business_subtype, source_record_id, source_record_no,
                   notice_status, posted_at, due_at, title
            FROM items
            WHERE source_name IN ({source_placeholders})
              AND (
                operating_scope = 'modular_goods_service'
                OR REPLACE(COALESCE(title, ''), ' ', '') LIKE '%모듈러%'
              )
            ORDER BY COALESCE(posted_at, created_at) DESC, id DESC
            LIMIT 30
            """,
            source_params,
        ).fetchall()
        print("\n최근 30건")
        for row in rows:
            print(
                f"- id={row['id']} {row['business_type']}/{row['business_subtype']} "
                f"{row['source_record_id']}-{row['source_record_no']} "
                f"[{row['notice_status']}] {row['posted_at']} {row['title']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
