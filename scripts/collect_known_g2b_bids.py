from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.probe_g2b_known_bid import (
    LIST_OPERATIONS,
    OPERATIONS,
    print_probe_result,
    request_detail,
    request_list_fallback,
    upsert_probe_result,
)


KNOWN_BIDS_PATH = ROOT_DIR / "config" / "known_important_bids.json"


def main() -> int:
    known_bids = json.loads(KNOWN_BIDS_PATH.read_text(encoding="utf-8"))
    failures = 0
    stored = 0

    for bid in known_bids:
        if not bid.get("must_collect", True):
            continue
        bid_no = bid["bid_no"]
        orders = bid.get("bid_orders") or ["000", "001"]
        title_contains = bid.get("title_contains") or []
        print(f"\n[known bid] {bid_no} orders={orders} title_contains={title_contains}")

        successes: list[dict] = []
        for category, operation in OPERATIONS.items():
            for order in orders:
                result = request_detail(category, operation, bid_no, order, title_contains)
                if result["matched"]:
                    print_probe_result(category, operation, order, result, _Args(title_contains))
                    successes.append(result)

        if not successes:
            print("  detail candidates did not match. trying list fallback...")
            for category, operation in LIST_OPERATIONS.items():
                result = request_list_fallback(category, operation, bid_no, title_contains)
                if result["matched"]:
                    print_probe_result(category, operation, "list", result, _Args(title_contains))
                    successes.append(result)

        if not successes:
            print(f"  FAIL: {bid_no} API에서 확인 실패")
            failures += 1
            continue

        for result in successes:
            item_id = upsert_probe_result(result)
            print(
                f"  stored item_id={item_id} category={result['category']} "
                f"order={result['bid_order'] or '-'}"
            )
            stored += 1

    if failures:
        print(f"KNOWN G2B BID COLLECTION FAILED failures={failures} stored={stored}")
        return 1
    print(f"KNOWN G2B BID COLLECTION PASSED stored={stored}")
    return 0


class _Args:
    def __init__(self, title_contains: list[str]) -> None:
        self.title_keyword = title_contains[0] if title_contains else ""
        self.title_contains = title_contains


if __name__ == "__main__":
    raise SystemExit(main())
