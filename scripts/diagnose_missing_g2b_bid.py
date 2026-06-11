from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import DB_PATH
from src.database import init_db


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose why a G2B bid is missing from the dashboard.")
    parser.add_argument("--bid-no", required=True)
    parser.add_argument("--title-keyword", default="")
    parser.add_argument("--lookback-days", type=int, default=30)
    args = parser.parse_args()

    init_db(DB_PATH)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        bid_like = f"%{args.bid_no}%"
        keyword_like = f"%{args.title_keyword}%" if args.title_keyword else "%"

        print(f"[diagnose] bid_no={args.bid_no} title_keyword={args.title_keyword or '-'}")
        rows = conn.execute(
            """
            SELECT id, source_name, source_type, title, source_record_id, source_record_no,
                   bid_no, bid_order, notice_status, business_type, data_quality, unique_hash
            FROM items
            WHERE source_record_id = ?
               OR bid_no = ?
               OR title LIKE ?
               OR summary LIKE ?
            ORDER BY id DESC
            """,
            (args.bid_no, args.bid_no, keyword_like, keyword_like),
        ).fetchall()
        print(f"items candidates: {len(rows)}")
        for row in rows[:20]:
            print(dict(row))

        source_name_candidates = conn.execute(
            """
            SELECT source_name, COUNT(*) AS cnt
            FROM items
            WHERE source_type = 'bid'
              AND (source_name IN ('나라장터', 'G2B', '조달청') OR source_name LIKE '%나라%')
            GROUP BY source_name
            """
        ).fetchall()
        print("\nG2B-like source_name counts:")
        for row in source_name_candidates:
            print(dict(row))

        details = conn.execute(
            """
            SELECT sd.id, sd.item_id, sd.source_name, sd.source_record_id, sd.source_record_no,
                   sd.status, sd.fetched_at
            FROM source_details sd
            WHERE sd.source_record_id = ?
            ORDER BY sd.id DESC
            """,
            (args.bid_no,),
        ).fetchall()
        print(f"\nsource_details exact record candidates: {len(details)}")
        for row in details[:20]:
            print(dict(row))

        payload_refs = conn.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM source_details
            WHERE detail_payload_json LIKE ?
            """,
            (bid_like,),
        ).fetchone()["cnt"]
        print(f"source_details payload references: {payload_refs}")

        logs = conn.execute(
            """
            SELECT collector_name, started_at, finished_at, status,
                   inserted_count, updated_count, skipped_count, error_message
            FROM collect_logs
            WHERE collector_name IN ('나라장터', 'G2B', '조달청')
               OR collector_name LIKE '%나라%'
            ORDER BY id DESC
            LIMIT 5
            """
        ).fetchall()
        print("\nrecent G2B collect_logs:")
        for row in logs:
            print(dict(row))

        exact_bid = [row for row in rows if row["source_record_id"] == args.bid_no or row["bid_no"] == args.bid_no]
        if exact_bid:
            print("\n판정: DB에 공고번호 기준으로 존재합니다. 대시보드 검색/필터 조건을 확인하세요.")
            return 0
        if details:
            print("\n판정: source_details에는 있으나 items에 없습니다. 상세 probe 후 items upsert 흐름을 확인하세요.")
            return 1
        if rows:
            print("\n판정: 제목/키워드 후보는 있으나 공고번호가 다릅니다. 공고차수 또는 source_record_id 저장 문제 가능성이 있습니다.")
            return 1
        print("\n판정: DB에 없습니다. API endpoint 범위, 키워드 필터, 날짜 범위, 공고차수/취소공고 처리 문제를 점검하세요.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
