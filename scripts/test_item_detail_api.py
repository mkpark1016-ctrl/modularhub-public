from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api_contract import get_bids, get_item_detail


def main() -> int:
    bids = get_bids(limit=1)
    if not bids:
        print("SKIP: no bid items available")
        return 0
    item_id = int(bids[0]["id"])
    detail = get_item_detail(item_id)
    assert detail["item"]["id"] == item_id
    assert detail["manual_check"]
    assert isinstance(detail["available_actions"], list)
    assert "favorite" in detail["available_actions"]
    assert "site_name" in detail["manual_check"]
    print("ITEM DETAIL API TEST PASSED")
    print(f"item_id={item_id}")
    print(f"actions={detail['available_actions']}")
    print(f"manual_check={detail['manual_check']}")
    print(f"source_detail_exists={bool(detail['source_detail'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
