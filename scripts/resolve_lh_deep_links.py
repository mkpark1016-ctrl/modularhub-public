from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import DB_PATH
from src.deep_link_resolver import resolve_deep_link_for_item
from src.lh_deep_link import build_lh_deep_link_candidates, build_lh_list_url


def main() -> None:
    parser = argparse.ArgumentParser(description="Store LH OpenAPI details and optionally probe external URLs.")
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
            WHERE source_name = 'LH'
              AND COALESCE(data_quality, 'real') NOT IN ('mock', 'sample', 'test')
            ORDER BY posted_at DESC, id DESC
            LIMIT ?
            """,
            (args.limit,),
        ).fetchall()

        print(f"LH rows={len(rows)}, mode={'apply' if args.apply else 'dry-run'}")
        for row in rows:
            item = dict(row)
            candidates = build_lh_deep_link_candidates(item)
            list_url = item.get("source_search_url") or build_lh_list_url(item)
            payload = build_lh_detail_payload(item, list_url)

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
                f"id={item['id']} bidNum={item.get('source_record_id') or '-'} "
                f"api_detail=stored candidates={len(candidates)} "
                f"external_status={result['link_status']} reason={result['exact_url_validation_reason']}"
            )
            if args.dry_run:
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
                    "LH",
                    item["source_type"],
                    item.get("source_record_id"),
                    item.get("source_record_no"),
                    "LH_OPENAPI_ITEM",
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
                    source_search_url = COALESCE(source_search_url, ?),
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
                    list_url,
                    item["id"],
                ),
            )
        if args.apply:
            conn.commit()


def build_lh_detail_payload(item: dict, list_url: str) -> dict:
    return {
        "source_name": "LH",
        "source_type": item.get("source_type"),
        "bidNum": item.get("source_record_id"),
        "bidnmKor": item.get("title"),
        "organization": item.get("organization"),
        "zoneHqCd": item.get("region"),
        "posted_at": item.get("posted_at"),
        "tndrdocAcptEndDtm": item.get("due_at"),
        "amount": item.get("amount"),
        "summary": item.get("summary"),
        "keywords": item.get("keywords"),
        "relevance_score": item.get("relevance_score"),
        "manual_check": {
            "site_name": "LH 전자조달",
            "site_url": "https://ebid.lh.or.kr",
            "list_url_probe_only": list_url,
            "instruction": "LH 전자조달 사이트에서 공고번호 또는 공고명으로 조회해 확인하세요.",
        },
    }


if __name__ == "__main__":
    main()
