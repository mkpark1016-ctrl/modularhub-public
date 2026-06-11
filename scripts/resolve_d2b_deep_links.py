from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import DB_PATH
from src.d2b_deep_link import build_d2b_deep_link_candidates
from src.deep_link_resolver import resolve_deep_link_for_item


def main() -> None:
    parser = argparse.ArgumentParser(description="Store D2B OpenAPI details and optionally probe external URLs.")
    parser.add_argument("--source-type", choices=["bid", "procurement_plan"], required=True)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--probe-external-url", action="store_true")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT *
            FROM items
            WHERE source_name = 'D2B'
              AND source_type = ?
              AND COALESCE(data_quality, 'real') NOT IN ('mock', 'sample', 'test')
            ORDER BY posted_at DESC, id DESC
            LIMIT ?
            """,
            (args.source_type, args.limit),
        ).fetchall()

        print(f"D2B {args.source_type} rows={len(rows)}, mode={'apply' if args.apply else 'dry-run'}")
        for row in rows:
            item = dict(row)
            candidates = build_d2b_deep_link_candidates(item)
            payload = build_d2b_detail_payload(item)

            if args.probe_external_url:
                result = resolve_deep_link_for_item(item, validate=args.apply)
            else:
                result = {
                    "exact_url_candidate": candidates[0] if candidates else None,
                    "exact_url_verified": 0,
                    "exact_url_verified_at": None,
                    "exact_url_validation_reason": "external_url_unavailable",
                    "original_url": None,
                    "link_type": "unknown",
                    "link_status": "unknown",
                }

            print(
                f"id={item['id']} record={item.get('source_record_id') or '-'} "
                f"api_detail=stored candidates={len(candidates)} "
                f"external_status={result['link_status']} reason={result['exact_url_validation_reason']}"
            )
            if args.dry_run:
                for candidate in candidates[:5]:
                    print(f"  candidate={candidate}")
                if len(candidates) > 5:
                    print(f"  ... {len(candidates) - 5} more")
                continue

            conn.execute(
                """
                INSERT INTO source_details (
                    item_id, source_name, source_type, source_record_id, source_record_no,
                    detail_api_url, detail_payload_json, fetched_at, status, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                ON CONFLICT(item_id, detail_api_url) DO UPDATE SET
                    source_name=excluded.source_name,
                    source_type=excluded.source_type,
                    source_record_id=excluded.source_record_id,
                    source_record_no=excluded.source_record_no,
                    detail_payload_json=excluded.detail_payload_json,
                    fetched_at=CURRENT_TIMESTAMP,
                    status=excluded.status,
                    error_message=excluded.error_message
                """,
                (
                    item["id"],
                    "D2B",
                    item["source_type"],
                    item.get("source_record_id"),
                    item.get("source_record_no"),
                    f"D2B_OPENAPI_ITEM_{item['source_type']}",
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    "openapi_item_stored",
                    None,
                ),
            )
            conn.execute(
                """
                UPDATE items
                SET exact_url_candidate = ?,
                    exact_url_verified = ?,
                    exact_url_verified_at = ?,
                    exact_url_validation_reason = ?,
                    original_url = NULL,
                    link_type = ?,
                    link_status = ?,
                    api_detail_verified = 1,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    result.get("exact_url_candidate"),
                    result.get("exact_url_verified"),
                    result.get("exact_url_verified_at"),
                    result.get("exact_url_validation_reason"),
                    result.get("link_type"),
                    result.get("link_status"),
                    item["id"],
                ),
            )
        if args.apply:
            conn.commit()


def build_d2b_detail_payload(item: dict) -> dict:
    source_type = item.get("source_type")
    summary_fields = _parse_summary(item.get("summary") or "")
    payload = {
        "source_name": "D2B",
        "source_type": source_type,
        "record_label": "판단번호" if source_type == "procurement_plan" else "공고번호",
        "source_record_id": item.get("source_record_id"),
        "source_record_no": item.get("source_record_no"),
        "title": item.get("title"),
        "organization": item.get("organization"),
        "posted_at": item.get("posted_at"),
        "due_at": item.get("due_at"),
        "amount": item.get("amount"),
        "region": item.get("region"),
        "keywords": item.get("keywords"),
        "relevance_score": item.get("relevance_score"),
        "summary": item.get("summary"),
        "summary_fields": summary_fields,
        "manual_check": {
            "site_name": "D2B 국방전자조달",
            "site_url": "https://www.d2b.go.kr",
            "instruction": "D2B 국방전자조달 사이트에서 판단번호, 공고번호 또는 제목으로 조회해 확인하세요.",
        },
    }
    if source_type == "procurement_plan":
        payload.update(
            {
                "dcs_no": item.get("source_record_id"),
                "order_month": summary_fields.get("발주예정월") or item.get("posted_at"),
                "representative_item_name": item.get("title"),
                "ordering_organization": item.get("organization"),
                "budget_amount": item.get("amount"),
                "contract_method": summary_fields.get("계약방법"),
                "bid_method": summary_fields.get("입찰방법"),
                "progress_status": summary_fields.get("진행상태"),
            }
        )
    else:
        payload.update(
            {
                "notice_no": item.get("source_record_id"),
                "bid_name": item.get("title"),
                "ordering_organization": item.get("organization"),
                "contract_method": summary_fields.get("계약방법"),
                "bid_method": summary_fields.get("입찰방법"),
                "business_type": summary_fields.get("업무구분"),
                "registration_deadline": summary_fields.get("등록마감"),
                "bid_submission_deadline": summary_fields.get("입찰서제출마감"),
                "opening_datetime": summary_fields.get("개찰일시"),
            }
        )
    return payload


def _parse_summary(summary: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in re.split(r";\s*", summary):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            fields[key] = value
    return fields


if __name__ == "__main__":
    main()
