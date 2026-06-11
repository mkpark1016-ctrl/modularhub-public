from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import DB_PATH
from src.database import init_db
from src.deep_link_resolver import normalize_source, resolve_deep_link_for_item


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve and validate exact deep links.")
    parser.add_argument("--source", required=True, help="G2B, LH, D2B, or 네이버뉴스")
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

    source_name = normalize_source(args.source)
    init_db(DB_PATH)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT *
            FROM items
            WHERE source_name = ?
              AND COALESCE(is_mock, 0) != 1
              AND COALESCE(data_quality, 'real') NOT IN ('mock', 'sample', 'test')
            ORDER BY id DESC
            LIMIT ?
            """,
            (source_name, args.limit),
        ).fetchall()
        print(f"source={source_name}, rows={len(rows)}, mode={'apply' if args.apply else 'dry-run'}")
        for row in rows:
            item = dict(row)
            result = resolve_deep_link_for_item(item, validate=args.apply)
            print(
                f"id={item['id']} record={item.get('source_record_id') or '-'} "
                f"candidate={result.get('exact_url_candidate') or '-'} "
                f"verified={result.get('exact_url_verified')} reason={result.get('exact_url_validation_reason')}"
            )
            if args.apply:
                conn.execute(
                    """
                    UPDATE items
                    SET exact_url_candidate = ?,
                        exact_url_verified = ?,
                        exact_url_verified_at = ?,
                        exact_url_validation_reason = ?,
                        original_url = ?,
                        link_type = ?,
                        link_status = ?,
                        source_detail_api_url = COALESCE(?, source_detail_api_url),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        result.get("exact_url_candidate"),
                        result.get("exact_url_verified"),
                        result.get("exact_url_verified_at"),
                        result.get("exact_url_validation_reason"),
                        result.get("original_url"),
                        result.get("link_type"),
                        result.get("link_status"),
                        result.get("source_detail_api_url"),
                        item["id"],
                    ),
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
