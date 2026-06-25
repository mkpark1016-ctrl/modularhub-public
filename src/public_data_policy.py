from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
REMOVAL_ALLOWLIST_PATH = ROOT / "config" / "public_data_removal_allowlist.json"
BUSINESS_SHRINK_THRESHOLD = 0.20
NEWS_SHRINK_THRESHOLD = 0.30
KST = timezone(timedelta(hours=9), "KST")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "none", "nan", "nat"} else text


def payload_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        items = payload.get("items", [])
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def parse_public_datetime(value: Any) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        pass
    for fmt in ("%Y%m%d%H%M", "%Y%m%d", "%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(text[: len(datetime.now().strftime(fmt))], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def business_identity(item: dict[str, Any]) -> tuple[str, ...]:
    source = clean_text(item.get("source_name") or item.get("source")).lower()
    source_type = clean_text(item.get("source_type")).lower()
    bid_no = clean_text(item.get("bid_no"))
    plan_no = clean_text(item.get("plan_no"))
    bid_order = clean_text(item.get("bid_order"))
    source_record_id = clean_text(item.get("source_record_id") or item.get("bid_no") or item.get("plan_no"))
    if source_type == "public_agency_contest" and source_record_id:
        return ("contest", source, source_record_id.lower())
    if source_type == "procurement_plan" and plan_no:
        return ("plan", source, plan_no.lower())
    if bid_no:
        return ("bid", source, bid_no.lower(), bid_order.lower())
    title = clean_text(item.get("title")).lower()
    organization = clean_text(item.get("organization")).lower()
    posted_at = clean_text(item.get("posted_at"))[:10]
    if posted_at:
        return ("fallback-posted", source, title, organization, posted_at)
    due_at = clean_text(item.get("due_at"))[:10]
    item_id = clean_text(item.get("id"))
    if item_id:
        return ("id", item_id.lower())
    return ("fallback-due", source, title, due_at)


def news_identity(item: dict[str, Any]) -> tuple[str, ...]:
    original_url = clean_text(item.get("original_url"))
    if original_url:
        return ("original-url", original_url.lower())
    link = clean_text(item.get("naver_url") or item.get("link"))
    if link:
        return ("link", link.lower())
    return (
        "fallback",
        clean_text(item.get("title")).lower(),
        clean_text(item.get("media") or item.get("source")).lower(),
        clean_text(item.get("published_at"))[:10],
    )


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(clean_text(value))
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return True


def merge_record(existing: dict[str, Any], fresh: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    original_id = existing.get("id")
    for key, value in fresh.items():
        if _nonempty(value):
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
    if (
        clean_text(fresh.get("source_type")) == "public_agency_contest"
        and clean_text(fresh.get("source")) in {"GH", "iH"}
        and _nonempty(fresh.get("id"))
    ):
        merged["id"] = fresh["id"]
    elif _nonempty(original_id):
        merged["id"] = original_id
    return merged


def load_removal_allowlist(path: Path | None = None) -> dict[str, dict[str, Any]]:
    allowlist_path = path or REMOVAL_ALLOWLIST_PATH
    if not allowlist_path.exists():
        return {}
    try:
        payload = json.loads(allowlist_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    raw_items = payload.get("items", []) if isinstance(payload, dict) else payload
    if not isinstance(raw_items, list):
        return {}
    allowed: dict[str, dict[str, Any]] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        item_id = clean_text(item.get("item_id") or item.get("id"))
        reason = clean_text(item.get("reason"))
        if item_id and reason:
            allowed[item_id] = item
    return allowed


def is_removal_allowed(item: dict[str, Any], allowlist: dict[str, dict[str, Any]] | None = None) -> bool:
    item_id = clean_text(item.get("id") or item.get("item_id"))
    if not item_id:
        return False
    allowed = allowlist if allowlist is not None else load_removal_allowlist()
    return item_id in allowed


def should_retain_existing(item: dict[str, Any], kind: str, *, now: datetime, retention_days: int) -> bool:
    if kind == "business" and clean_text(item.get("source_type")).lower() == "public_agency_contest":
        stage = clean_text(item.get("notice_status") or item.get("notice_stage"))
        if stage not in {"pre_notice", "main_notice", "re_notice", "correction"}:
            return False
    return True


def ensure_unique_ids(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    used: set[str] = set()
    numeric_ids = []
    for item in items:
        try:
            numeric_ids.append(int(item.get("id")))
        except (TypeError, ValueError):
            pass
    next_id = max(numeric_ids, default=0) + 1
    result: list[dict[str, Any]] = []
    for item in items:
        copied = dict(item)
        item_id = clean_text(copied.get("id"))
        if not item_id or item_id in used:
            while str(next_id) in used:
                next_id += 1
            copied["id"] = next_id
            item_id = str(next_id)
            next_id += 1
        used.add(item_id)
        result.append(copied)
    return result


def merge_public_items(
    existing: list[dict[str, Any]],
    fresh: list[dict[str, Any]],
    *,
    kind: str,
    now: datetime | None = None,
    retention_days: int | None = None,
    removal_allowlist: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if kind not in {"business", "news"}:
        raise ValueError(f"unsupported public data kind: {kind}")
    current_time = now or datetime.now(timezone.utc)
    identity: Callable[[dict[str, Any]], tuple[str, ...]] = business_identity if kind == "business" else news_identity
    merged_by_key: dict[tuple[str, ...], dict[str, Any]] = {}
    allowed_removals = removal_allowlist if removal_allowlist is not None else load_removal_allowlist()

    for item in existing:
        if is_removal_allowed(item, allowed_removals):
            continue
        if should_retain_existing(item, kind, now=current_time, retention_days=retention_days or 0):
            merged_by_key[identity(item)] = dict(item)
    for item in fresh:
        if is_removal_allowed(item, allowed_removals):
            continue
        key = identity(item)
        if key in merged_by_key:
            merged_by_key[key] = merge_record(merged_by_key[key], item)
        else:
            merged_by_key[key] = dict(item)

    merged = ensure_unique_ids(list(merged_by_key.values()))
    date_field = "posted_at" if kind == "business" else "published_at"
    merged.sort(key=lambda item: (clean_text(item.get(date_field)), clean_text(item.get("id"))), reverse=True)
    return merged


def business_lifecycle_fields(
    item: dict[str, Any],
    *,
    now: datetime | None = None,
    default_last_seen_at: str | None = None,
) -> dict[str, Any]:
    current_time = (now or datetime.now(KST)).astimezone(KST)
    today = current_time.date()
    due_at = parse_public_datetime(item.get("due_at"))
    last_seen_at = (
        clean_text(item.get("last_seen_at"))
        or clean_text(item.get("collected_at"))
        or clean_text(item.get("posted_at"))
        or clean_text(default_last_seen_at)
    )
    if due_at is None:
        return {
            "opportunity_status": "unknown",
            "is_closed": False,
            "days_until_deadline": None,
            "closed_at": None,
            "last_seen_at": last_seen_at,
            "lifecycle_reason": "no_deadline",
        }
    due_date = due_at.astimezone(KST).date()
    days_until_deadline = (due_date - today).days
    if days_until_deadline < 0:
        return {
            "opportunity_status": "closed",
            "is_closed": True,
            "days_until_deadline": days_until_deadline,
            "closed_at": due_date.isoformat(),
            "last_seen_at": last_seen_at,
            "lifecycle_reason": "deadline_passed",
        }
    return {
        "opportunity_status": "active",
        "is_closed": False,
        "days_until_deadline": days_until_deadline,
        "closed_at": None,
        "last_seen_at": last_seen_at,
        "lifecycle_reason": "deadline_today_or_future",
    }


def apply_business_lifecycle(
    items: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    default_last_seen_at: str | None = None,
) -> list[dict[str, Any]]:
    return [
        {
            **item,
            **business_lifecycle_fields(item, now=now, default_last_seen_at=default_last_seen_at),
        }
        for item in items
    ]


def guard_result(
    *,
    previous_business: int,
    merged_business: int,
    previous_news: int,
    merged_news: int,
    allow_shrink: bool = False,
) -> tuple[str, str]:
    business_limit = int(previous_business * (1 - BUSINESS_SHRINK_THRESHOLD))
    news_limit = int(previous_news * (1 - NEWS_SHRINK_THRESHOLD))
    problems = []
    if previous_business and merged_business < business_limit:
        problems.append(f"business {previous_business} -> {merged_business}")
    if previous_news and merged_news < news_limit:
        problems.append(f"news {previous_news} -> {merged_news}")
    if problems and not allow_shrink:
        return "blocked", "Public data shrink detected. " + ", ".join(problems) + ". Refusing commit."
    if problems:
        return "override", "Public data shrink allowed by ALLOW_PUBLIC_DATA_SHRINK=true: " + ", ".join(problems)
    if merged_business < previous_business or merged_news < previous_news:
        return "warning", (
            f"Cumulative normalization reduced data within guard limits: business {previous_business} -> {merged_business}, "
            f"news {previous_news} -> {merged_news}."
        )
    return "passed", (
        f"Cumulative merge protected public data: business {previous_business} -> {merged_business}, "
        f"news {previous_news} -> {merged_news}."
    )
