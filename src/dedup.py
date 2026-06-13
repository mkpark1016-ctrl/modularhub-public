from __future__ import annotations

from hashlib import sha256
from typing import Any


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def make_unique_hash(item: dict) -> str:
    if _clean(item.get("source_type")) == "procurement_plan":
        parts = [
            item.get("source_name"),
            item.get("source_type"),
            item.get("source_record_id") or item.get("plan_no") or item.get("bid_no"),
            item.get("title"),
            item.get("organization"),
            item.get("due_at"),
        ]
        return sha256("|".join(_clean(part) for part in parts).encode("utf-8")).hexdigest()

    if _clean(item.get("source_name")) in {"나라장터", "g2b", "조달청"} and _clean(
        item.get("source_record_id") or item.get("bid_no")
    ):
        parts = [
            item.get("source_type"),
            "나라장터",
            item.get("source_record_id") or item.get("bid_no"),
            item.get("source_record_no") or item.get("bid_order"),
            item.get("business_type") or item.get("category"),
        ]
        return sha256("|".join(_clean(part) for part in parts).encode("utf-8")).hexdigest()

    if _clean(item.get("source_type")) == "news":
        url = _clean(item.get("url"))
        if url:
            parts = [
                item.get("source_type"),
                item.get("source_name"),
                item.get("url"),
            ]
        else:
            parts = [
                item.get("source_type"),
                item.get("source_name"),
                item.get("title"),
                item.get("posted_at"),
                item.get("keyword_query"),
            ]
        return sha256("|".join(_clean(part) for part in parts).encode("utf-8")).hexdigest()

    parts = [
        item.get("source_type"),
        item.get("source_name"),
        item.get("title"),
        item.get("organization"),
        item.get("posted_at"),
        item.get("url"),
    ]
    return sha256("|".join(_clean(part) for part in parts).encode("utf-8")).hexdigest()
