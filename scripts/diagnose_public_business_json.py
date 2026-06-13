from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUSINESS_PATH = ROOT / "frontend" / "public" / "data" / "business.json"


def main() -> int:
    if not BUSINESS_PATH.exists():
        print(f"business.json not found: {BUSINESS_PATH}")
        print("Run scripts/export_public_json.py first.")
        return 1

    payload = json.loads(BUSINESS_PATH.read_text(encoding="utf-8"))
    items = payload if isinstance(payload, list) else payload.get("items", [])
    source_types = Counter(str(item.get("source_type") or "(missing)") for item in items)
    sources = Counter(str(item.get("source") or "(missing)") for item in items)
    type_values = Counter(str(item.get("type") or item.get("category") or "(missing)") for item in items)
    plans = [item for item in items if item.get("source_type") == "procurement_plan"]
    modular = [
        item for item in items
        if "모듈러" in " ".join(str(item.get(key) or "") for key in ("title", "summary", "keywords"))
    ]

    print(f"total business items: {len(items)}")
    print(f"source_type counts: {dict(source_types)}")
    print(f"source counts: {dict(sources)}")
    print(f"type/category counts: {dict(type_values)}")
    print(f"bid count: {source_types.get('bid', 0)}")
    print(f"procurement_plan count: {len(plans)}")
    print(f"items containing 모듈러: {len(modular)}")
    print("\nprocurement plan samples:")
    for item in plans[:10]:
        print(
            f"- [{item.get('source')}] {item.get('title')} | "
            f"plan_no={item.get('plan_no') or item.get('bid_no')} | due_at={item.get('due_at')}"
        )

    if not plans:
        status = payload.get("procurement_plan_collection_status") if isinstance(payload, dict) else None
        print("\nNo procurement plan items are exported.")
        if status in {"failed", "partial_warning", "not_collected"}:
            source_status = payload.get("procurement_plan_source_status", {})
            print(
                f"Likely cause: collector status is {status} ({source_status}); "
                "run or inspect both procurement plan collectors."
            )
        else:
            print("Likely causes: no modular match in the query range, source_type mismatch, or export filtering.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
