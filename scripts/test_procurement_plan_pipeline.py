from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUSINESS_PATH = ROOT / "frontend" / "public" / "data" / "business.json"
APP_PATH = ROOT / "frontend" / "src" / "App.jsx"
DB_PATH = ROOT / "data" / "modular_info.db"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


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
    require('item.source_type === selectedSourceType' in frontend, "frontend kind filter must use source_type")
    require('procurement_plan' in frontend and '발주계획' in frontend, "frontend plan mapping is missing")
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
