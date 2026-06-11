from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api_contract import get_item_detail, safe_text
from src.config import DB_PATH
from src.database import get_connection, init_db


def main() -> int:
    init_db(DB_PATH)
    with get_connection(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT id
            FROM items
            WHERE source_type = 'bid'
              AND COALESCE(data_quality, 'real') = 'real'
            ORDER BY id DESC
            LIMIT 3
            """
        ).fetchall()
    if not rows:
        print("SKIP: no bid items available")
        return 0

    for row in rows:
        item_id = int(row["id"])
        detail = get_item_detail(item_id)
        item = detail["item"]
        assert item["id"] == item_id
        assert "manual_check" in detail
        assert detail["manual_check"]["search_keys"] is not None
        assert isinstance(detail["available_actions"], list)
        for key in ("source_record_id", "source_record_no", "notice_status"):
            value = safe_text(item.get(key), "-")
            assert value.lower() not in {"nan", "none"}
        print(
            f"checked item_id={item_id} record={safe_text(item.get('source_record_id'), '-')} "
            f"detail={bool(detail['source_detail'])} site={detail['manual_check'].get('site_name')}"
        )

    print("DETAIL PANEL DATA TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
