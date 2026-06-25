from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.public_data_policy import (  # noqa: E402
    apply_business_lifecycle,
    business_lifecycle_fields,
    merge_public_items,
)


DATA_DIR = ROOT / "frontend" / "public" / "data"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def synthetic_business(item_id: str, *, due_at: str | None, source_type: str = "bid") -> dict:
    return {
        "id": item_id,
        "source": "G2B",
        "source_name": "G2B",
        "source_type": source_type,
        "type": "입찰공고",
        "title": f"synthetic modular business {item_id}",
        "organization": "Test Org",
        "bid_no": f"BID-{item_id}",
        "bid_order": "000",
        "posted_at": "2025-12-01",
        "due_at": due_at,
    }


def test_cumulative_business_retention() -> None:
    old_items = [
        synthetic_business(str(index), due_at="2025-12-18" if index > 144 else "2026-07-01")
        for index in range(1, 156)
    ]
    fresh_items = [synthetic_business(str(index), due_at="2026-07-01") for index in range(1, 145)]
    fresh_items.extend(
        [
            synthetic_business("new-1", due_at="2026-08-01"),
            synthetic_business("new-2", due_at="2026-08-02"),
        ]
    )
    merged = merge_public_items(
        old_items,
        fresh_items,
        kind="business",
        now=datetime(2026, 6, 24, tzinfo=timezone.utc),
    )
    require(len(merged) == 157, f"expected 157 merged business items, got {len(merged)}")
    merged_ids = {str(item["id"]) for item in merged}
    for item_id in [str(index) for index in range(145, 156)]:
        require(item_id in merged_ids, f"expired business item was pruned: {item_id}")


def test_lifecycle_states() -> None:
    now = datetime(2026, 6, 24, tzinfo=timezone.utc)
    closed = business_lifecycle_fields({"due_at": "2026-06-23"}, now=now)
    today = business_lifecycle_fields({"due_at": "2026-06-24"}, now=now)
    future = business_lifecycle_fields({"due_at": "2026-06-25"}, now=now)
    unknown = business_lifecycle_fields({"due_at": ""}, now=now)
    require(closed["opportunity_status"] == "closed", "past due date must be closed")
    require(closed["is_closed"] is True, "closed item must set is_closed")
    require(today["opportunity_status"] == "active", "today due date must remain active")
    require(future["opportunity_status"] == "active", "future due date must be active")
    require(unknown["opportunity_status"] == "unknown", "missing due date must be unknown")


def test_duplicate_and_approved_removal_policy() -> None:
    old_items = [
        synthetic_business("same-id", due_at="2026-07-01"),
        {**synthetic_business("bid-order-1", due_at="2026-07-01"), "bid_no": "SAME-BID", "bid_order": "001"},
        {**synthetic_business("bid-order-2", due_at="2026-07-01"), "bid_no": "SAME-BID", "bid_order": "002"},
        synthetic_business("approved-delete", due_at="2026-07-01"),
    ]
    fresh_items = [
        {**synthetic_business("same-id", due_at="2026-07-02"), "title": "updated title"},
    ]
    merged = merge_public_items(
        old_items,
        fresh_items,
        kind="business",
        now=datetime(2026, 6, 24, tzinfo=timezone.utc),
        removal_allowlist={"approved-delete": {"reason": "manually_approved"}},
    )
    merged_by_id = {str(item["id"]): item for item in merged}
    require(len([item for item in merged if str(item["id"]) == "same-id"]) == 1, "same id must update without duplication")
    require(merged_by_id["same-id"]["title"] == "updated title", "fresh same-id record must update existing item")
    require("bid-order-1" in merged_by_id and "bid-order-2" in merged_by_id, "different bid orders must remain distinct")
    require("approved-delete" not in merged_by_id, "approved removal was not applied")


def test_actual_public_data_contract() -> None:
    business = json.loads((DATA_DIR / "business.json").read_text(encoding="utf-8"))["items"]
    business = apply_business_lifecycle(business, now=datetime(2026, 6, 24, tzinfo=timezone.utc))
    ids = [str(item.get("id")) for item in business]
    require(len(ids) == len(set(ids)), "duplicate business id detected")
    source_types = {}
    sources = {}
    for item in business:
        source_types[item.get("source_type")] = source_types.get(item.get("source_type"), 0) + 1
        sources[item.get("source")] = sources.get(item.get("source"), 0) + 1
        require(item.get("opportunity_status") in {"active", "closed", "unknown"}, "invalid lifecycle status")
    require(source_types.get("public_agency_contest", 0) >= 28, "public agency contests decreased")
    require(source_types.get("procurement_plan", 0) >= 16, "procurement plans decreased")
    require(sources.get("LH", 0) >= 10, "LH public contests decreased")
    require(sources.get("GH", 0) >= 14, "GH public contests decreased")
    require(sources.get("iH", 0) >= 4, "iH public contests decreased")
    require(sources.get("SH", 0) == 0, "SH shadow data must not be public yet")


def main() -> int:
    test_cumulative_business_retention()
    test_lifecycle_states()
    test_duplicate_and_approved_removal_policy()
    test_actual_public_data_contract()
    print("PUBLIC DATA RETENTION POLICY TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
