from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import DATA_GO_KR_SERVICE_KEY, DB_PATH
from src.database import init_db
from src.deep_link_resolver import resolve_deep_link_for_item
from src.g2b_detail_url import build_g2b_detail_api_url, fetch_g2b_detail


G2B_SOURCE_NAMES = ("나라장터", "G2B", "조달청", "나라장터/G2B", "?섎씪?ν꽣")


def mask_url(url: str | None) -> str:
    if not url:
        return "-"
    if DATA_GO_KR_SERVICE_KEY:
        return url.replace(DATA_GO_KR_SERVICE_KEY, "[MASKED_SERVICE_KEY]")
    return re.sub(r"serviceKey=[^&]+", "serviceKey=[MASKED_SERVICE_KEY]", url)


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve G2B detail API payloads.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if args.dry_run and args.apply:
        print("Use only one of --dry-run or --apply.")
        return 1
    if not args.dry_run and not args.apply:
        print("Choose --dry-run or --apply.")
        return 1

    init_db(DB_PATH)
    placeholders = ",".join("?" for _ in G2B_SOURCE_NAMES)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT *
            FROM items
            WHERE source_name IN ({placeholders})
              AND COALESCE(is_mock, 0) != 1
              AND COALESCE(data_quality, 'real') NOT IN ('mock', 'sample', 'test')
            ORDER BY id DESC
            LIMIT ?
            """,
            (*G2B_SOURCE_NAMES, args.limit),
        ).fetchall()
        print(f"G2B rows={len(rows)}, mode={'apply' if args.apply else 'dry-run'}")
        for row in rows:
            item = dict(row)
            if not item.get("source_detail_api_url"):
                item["category"] = item.get("summary") or ""
                item["source_detail_api_url"] = build_g2b_detail_api_url(item)

            if args.apply:
                detail_result = fetch_g2b_detail(item)
                api_verified = 1 if detail_result["ok"] else 0
                result = {
                    "source_detail_api_url": detail_result.get("detail_api_url") or item.get("source_detail_api_url"),
                    "exact_url_candidate": detail_result.get("detail_api_url") or item.get("source_detail_api_url"),
                    "exact_url_verified": 0,
                    "exact_url_verified_at": None,
                    "exact_url_validation_reason": "api_detail_verified"
                    if api_verified
                    else detail_result.get("error_message"),
                    "original_url": None,
                    "link_type": "exact_api" if api_verified else "unknown",
                    "link_status": "ok" if api_verified else "broken",
                    "api_detail_verified": api_verified,
                }
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
                        item["source_name"],
                        item["source_type"],
                        item.get("source_record_id"),
                        item.get("source_record_no"),
                        result["source_detail_api_url"],
                        detail_result.get("payload_json"),
                        detail_result.get("status") or "failed",
                        detail_result.get("error_message"),
                    ),
                )
            else:
                result = resolve_deep_link_for_item(item, validate=False)
                result["api_detail_verified"] = 0

            print(
                f"id={item['id']} record={item.get('source_record_id') or '-'} "
                f"candidate={mask_url(result.get('exact_url_candidate'))} "
                f"api_verified={result.get('api_detail_verified', 0)} "
                f"reason={result.get('exact_url_validation_reason')}"
            )

            if args.apply:
                conn.execute(
                    """
                    UPDATE items
                    SET source_detail_api_url = ?,
                        exact_url_candidate = ?,
                        exact_url_verified = ?,
                        exact_url_verified_at = ?,
                        exact_url_validation_reason = ?,
                        original_url = ?,
                        link_type = ?,
                        link_status = ?,
                        api_detail_verified = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        result.get("source_detail_api_url"),
                        result.get("exact_url_candidate"),
                        result.get("exact_url_verified"),
                        result.get("exact_url_verified_at"),
                        result.get("exact_url_validation_reason"),
                        result.get("original_url"),
                        result.get("link_type"),
                        result.get("link_status"),
                        result.get("api_detail_verified", 0),
                        item["id"],
                    ),
                )
        if args.apply:
            conn.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
