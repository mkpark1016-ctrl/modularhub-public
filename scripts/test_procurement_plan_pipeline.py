from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUSINESS_PATH = ROOT / "frontend" / "public" / "data" / "business.json"
APP_PATH = ROOT / "frontend" / "src" / "App.jsx"
FILTER_HELPER_PATH = ROOT / "frontend" / "src" / "businessFilters.js"
DB_PATH = ROOT / "data" / "modular_info.db"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def source_type_matches(item: dict, selected_source_type: str) -> bool:
    if selected_source_type == "all":
        return True
    return item.get("source_type") == selected_source_type


def lifecycle_status(item: dict) -> str:
    return item.get("lifecycle_status") or item.get("opportunity_status") or "unknown"


def agency_value(item: dict) -> str:
    source_code = item.get("source_code")
    if source_code == "LH_CONTEST":
        return "LH"
    if source_code == "GH_CONTEST":
        return "GH"
    if source_code == "IH_NOTICE":
        return "iH"
    if source_code == "SH_CONTEST":
        return "SH"
    combined = f"{item.get('source') or ''} {item.get('source_name') or ''}".lower()
    if "d2b" in combined:
        return "D2B"
    if item.get("source_type") in {"bid", "procurement_plan"}:
        return "G2B"
    return item.get("source_name") or item.get("source") or "unknown"


def business_filter_matches(item: dict, *, source_type: str = "all", agency: str = "all", status: str = "all") -> bool:
    return (
        source_type_matches(item, source_type)
        and (agency == "all" or agency_value(item) == agency)
        and (status == "all" or lifecycle_status(item) == status)
    )


def main() -> int:
    require(BUSINESS_PATH.exists(), "business.json is missing; run export_public_json.py")
    payload = json.loads(BUSINESS_PATH.read_text(encoding="utf-8"))
    items = payload.get("items", []) if isinstance(payload, dict) else payload
    plans = [item for item in items if item.get("source_type") == "procurement_plan"]
    bids = [item for item in items if item.get("source_type") == "bid"]
    db_plan_count = 0
    if DB_PATH.exists():
        with sqlite3.connect(DB_PATH) as conn:
            db_plan_count = int(
                conn.execute("SELECT COUNT(*) FROM items WHERE source_type = 'procurement_plan'").fetchone()[0]
            )

    for item in plans:
        for field in ("id", "source_type", "type", "source", "title", "manual_check"):
            require(item.get(field) not in (None, ""), f"procurement plan field is missing: {field}")
        require(item.get("type") == "발주계획", "procurement plan type label mismatch")

    frontend = APP_PATH.read_text(encoding="utf-8")
    helper = FILTER_HELPER_PATH.read_text(encoding="utf-8")
    require("matchesBusinessFilters" in frontend, "frontend must call the shared business filter helper")
    require("matchesSourceType" in helper, "source type helper is missing")
    require("item?.source_type === selectedSourceType" in helper, "source type helper must compare canonical source_type")
    require("item?.kind" not in helper and "item?.source_name === selectedSourceType" not in helper, "source type helper must not use non-canonical fields")
    require("procurement_plan" in frontend and "발주계획" in frontend, "frontend plan mapping is missing")

    for source_type in ("bid", "procurement_plan", "public_agency_contest"):
        expected = sum(1 for item in items if item.get("source_type") == source_type)
        actual = sum(1 for item in items if business_filter_matches(item, source_type=source_type))
        require(actual == expected, f"source_type filter mismatch: {source_type}")
    require(sum(1 for item in items if business_filter_matches(item, source_type="all")) == len(items), "all source_type filter mismatch")
    require(sum(1 for item in items if business_filter_matches(item, source_type="missing_type")) == 0, "unknown source_type should return 0")
    require(not business_filter_matches({"title": "missing source type"}, source_type="bid"), "missing source_type should be excluded without error")

    g2b_bids = sum(1 for item in items if business_filter_matches(item, source_type="bid", agency="G2B"))
    require(g2b_bids == sum(1 for item in items if item.get("source_type") == "bid" and agency_value(item) == "G2B"), "source_type + agency filter mismatch")
    for status in ("active", "closed", "unknown"):
        expected = sum(1 for item in items if item.get("source_type") == "bid" and lifecycle_status(item) == status)
        actual = sum(1 for item in items if business_filter_matches(item, source_type="bid", status=status))
        require(actual == expected, f"source_type + lifecycle filter mismatch: {status}")
    require(bids, "business export must keep bid items")
    require("serviceKey" not in BUSINESS_PATH.read_text(encoding="utf-8"), "business JSON exposes serviceKey")

    if plans:
        print(f"DB procurement plan items: {db_plan_count}")
        print(f"exported procurement plan items: {len(plans)}")
    else:
        print(
            "WARNING: no modular procurement plans in the current export; "
            f"DB procurement_plan count={db_plan_count}. Pipeline remains valid."
        )
    print("PROCUREMENT PLAN PIPELINE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
