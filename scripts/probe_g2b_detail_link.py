from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import requests


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import DATA_GO_KR_SERVICE_KEY, DB_PATH
from src.database import init_db
from src.g2b_detail_url import build_g2b_detail_api_url, get_g2b_detail_operation
from src.link_validator import validate_candidate_url


def mask_url(url: str) -> str:
    if DATA_GO_KR_SERVICE_KEY:
        return url.replace(DATA_GO_KR_SERVICE_KEY, "[MASKED_SERVICE_KEY]")
    return re.sub(r"serviceKey=[^&]+", "serviceKey=[MASKED_SERVICE_KEY]", url)


def main() -> int:
    init_db(DB_PATH)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT *
            FROM items
            WHERE source_name IN ('나라장터', 'G2B')
            ORDER BY id DESC
            LIMIT 5
            """
        ).fetchall()

    if not rows:
        print("No G2B rows found in items. Run collect_g2b.py after matching notices exist.")
        return 0

    for row in rows:
        item = dict(row)
        item.setdefault("category", item.get("summary") or "")
        url = item.get("source_detail_api_url") or build_g2b_detail_api_url(item)
        operation = get_g2b_detail_operation(item)
        print("=" * 72)
        print(f"id={item['id']} title={item['title']}")
        print(f"bidNtceNo={item.get('source_record_id')} bidNtceOrd={item.get('source_record_no')}")
        print(f"operation={operation or '-'}")
        print(f"candidate={mask_url(url) if url else '-'}")
        if not url:
            print("result=failed reason=no_candidate")
            continue
        try:
            response = requests.get(url, timeout=20)
            print(f"http_status={response.status_code}")
            print(f"preview={response.text[:300]}")
        except requests.RequestException as exc:
            print(f"request_failed={exc}")
            continue
        validation = validate_candidate_url(url, item.get("title"), item.get("source_record_id"))
        print(f"valid={validation['is_valid']} reason={validation['reason']} checked_at={validation['checked_at']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
