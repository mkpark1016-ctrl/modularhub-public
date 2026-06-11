from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import DB_PATH
from src.database import init_db


CONFIG_PATH = ROOT_DIR / "config" / "known_important_bids.json"


def main() -> int:
    init_db(DB_PATH)
    bids = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    failures = 0
    warnings = 0
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        for bid in bids:
            bid_no = bid["bid_no"]
            rows = conn.execute(
                """
                SELECT id, source_name, source_type, title, source_record_id, source_record_no,
                       notice_status, business_type, operating_scope, is_operating_scope, data_quality
                FROM items
                WHERE source_record_id = ? OR bid_no = ?
                ORDER BY source_record_no, id
                """,
                (bid_no, bid_no),
            ).fetchall()
            detail_rows = conn.execute(
                """
                SELECT id, item_id, source_name, source_record_id, source_record_no, status
                FROM source_details
                WHERE source_record_id = ?
                ORDER BY id
                """,
                (bid_no,),
            ).fetchall()

            if not rows and not detail_rows:
                print(f"FAIL {bid_no}: items/source_details에 없음")
                failures += 1
                continue

            if rows:
                print(f"PASS {bid_no}: items {len(rows)}건")
                for row in rows:
                    print(f"  {dict(row)}")
                    if row["data_quality"] != "real":
                        print(f"  FAIL data_quality={row['data_quality']}")
                        failures += 1
                    if not row["source_record_id"]:
                        print("  FAIL source_record_id 없음")
                        failures += 1
                    if not row["source_record_no"]:
                        print("  WARN 공고차수/source_record_no 없음")
                        warnings += 1
                    if not row["notice_status"]:
                        print("  WARN 공고상태/notice_status 없음")
                        warnings += 1
                    if row["operating_scope"] == "modular_goods_service" or row["is_operating_scope"]:
                        print("  INFO 운영 범위 포함 중요공고")
                    else:
                        print(
                            "  INFO 운영 필터 외 중요공고: "
                            f"business_type={row['business_type']} expected={bid.get('expected_business_type') or '-'}"
                        )
            else:
                print(f"WARN {bid_no}: source_details에는 있으나 items에는 없음")
                warnings += 1

            if detail_rows:
                print(f"  source_details {len(detail_rows)}건")
            else:
                print("  WARN source_details 상세 응답 없음")
                warnings += 1

    if failures:
        print(f"KNOWN IMPORTANT BIDS TEST FAILED failures={failures} warnings={warnings}")
        return 1
    print(f"KNOWN IMPORTANT BIDS TEST PASSED warnings={warnings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
