from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "frontend" / "public" / "data"


def load(name: str) -> dict[str, Any]:
    path = DATA_DIR / f"{name}.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"items": payload}


def latest(items: list[dict[str, Any]], *fields: str) -> str:
    values = [str(item.get(field) or "") for item in items for field in fields if item.get(field)]
    return max(values, default="-")


def main() -> int:
    business_payload = load("business")
    news_payload = load("news")
    meta = load("meta")
    business = business_payload.get("items", [])
    news = news_payload.get("items", [])
    baseline_business = int(os.getenv("PUBLIC_DATA_BASELINE_BUSINESS_COUNT", "107"))
    baseline_news = int(os.getenv("PUBLIC_DATA_BASELINE_NEWS_COUNT", "425"))

    print(f"business_count={len(business)}")
    print(f"news_count={len(news)}")
    print(f"business_by_source={dict(Counter(item.get('source') or item.get('source_name') or 'unknown' for item in business))}")
    print(f"business_by_type={dict(Counter(item.get('source_type') or item.get('type') or 'unknown' for item in business))}")
    print(f"news_by_source={dict(Counter(item.get('source') or item.get('media') or 'unknown' for item in news))}")
    print(f"latest_business={latest(business, 'posted_at', 'due_at')}")
    print(f"latest_news={latest(news, 'published_at')}")
    print(f"meta_last_updated={meta.get('generated_at') or meta.get('last_updated') or '-'}")
    print(f"meta_last_collected_at={meta.get('last_collected_at') or '-'}")
    print(
        "merge_counts="
        f"previous_business={meta.get('previous_business_count', '-')}, "
        f"fresh_business={meta.get('current_business_count', '-')}, "
        f"merged_business={meta.get('merged_business_count', '-')}, "
        f"previous_news={meta.get('previous_news_count', '-')}, "
        f"fresh_news={meta.get('current_news_count', '-')}, "
        f"merged_news={meta.get('merged_news_count', '-')}"
    )
    print(f"baseline_business={baseline_business} decreased={len(business) < baseline_business}")
    print(f"baseline_news={baseline_news} decreased={len(news) < baseline_news}")
    print(f"public_data_guard_status={meta.get('public_data_guard_status', 'unknown')}")
    print(f"public_data_guard_message={meta.get('public_data_guard_message', '-')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
