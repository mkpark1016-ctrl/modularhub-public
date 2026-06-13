from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "frontend" / "public" / "data"


def load(name: str) -> dict[str, Any]:
    payload = json.loads((DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{name}.json must be an object with items")
    return payload


def integer(meta: dict[str, Any], name: str, fallback: int) -> int:
    try:
        return int(meta.get(name, fallback))
    except (TypeError, ValueError):
        return fallback


def main() -> int:
    business = load("business").get("items", [])
    news = load("news").get("items", [])
    meta = load("meta")
    if not business or not news:
        print(f"Public data shrink detected. business={len(business)}, news={len(news)}. Refusing commit.")
        return 1

    previous_business = max(
        integer(meta, "previous_business_count", len(business)),
        int(os.getenv("PUBLIC_DATA_BASELINE_BUSINESS_COUNT", "107")),
    )
    previous_news = max(
        integer(meta, "previous_news_count", len(news)),
        int(os.getenv("PUBLIC_DATA_BASELINE_NEWS_COUNT", "425")),
    )
    merged_business = integer(meta, "merged_business_count", len(business))
    merged_news = integer(meta, "merged_news_count", len(news))
    allow = os.getenv("ALLOW_PUBLIC_DATA_SHRINK", "false").lower() in {"1", "true", "yes", "y"}

    if merged_business != len(business) or merged_news != len(news):
        print(
            "Public data metadata mismatch. "
            f"business meta/file={merged_business}/{len(business)}, news meta/file={merged_news}/{len(news)}."
        )
        return 1

    business_limit = int(previous_business * 0.80)
    news_limit = int(previous_news * 0.70)
    suspicious = merged_business < business_limit or merged_news < news_limit
    if suspicious and not allow:
        print(
            "Public data shrink detected. "
            f"business {previous_business} -> {merged_business}, news {previous_news} -> {merged_news}. Refusing commit."
        )
        return 1
    print(
        f"PUBLIC DATA GUARD PASSED: business {previous_business} -> {merged_business}, "
        f"news {previous_news} -> {merged_news}, status={meta.get('public_data_guard_status', 'unknown')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
