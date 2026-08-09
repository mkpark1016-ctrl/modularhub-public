from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_POLICY_PATH = Path("config/operations/data_freshness_policy.json")
STATE_ORDER = {"healthy": 0, "no_new_items": 0, "warning": 1, "unknown": 1, "empty": 2, "critical": 3}
SAFE_MESSAGE_MAX = 180


class OperationsAuditError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OperationsAuditError(f"{path} is not valid JSON: {exc}") from exc
    except OSError as exc:
        raise OperationsAuditError(f"{path} could not be read: {exc}") from exc


def load_policy(path: Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict) or "datasets" not in payload:
        raise OperationsAuditError("freshness policy must be an object with datasets")
    return payload


def parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso_or_empty(value: datetime | None) -> str:
    return value.astimezone(timezone.utc).isoformat() if value else ""


def item_list(payload: Any, key: str = "items") -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get(key), list):
        return [item for item in payload[key] if isinstance(item, dict)]
    return []


def latest_item_at(items: list[dict[str, Any]], fields: tuple[str, ...]) -> datetime | None:
    latest: datetime | None = None
    for item in items:
        for field in fields:
            parsed = parse_datetime(item.get(field))
            if parsed and (latest is None or parsed > latest):
                latest = parsed
                break
    return latest


def freshness_state(age_hours: float | None, warning_hours: float, critical_hours: float, *, record_count: int, timestamp_missing: bool) -> tuple[str, str]:
    if record_count == 0:
        return "empty", "dataset has no records"
    if timestamp_missing or age_hours is None:
        return "unknown", "latest timestamp is missing or invalid"
    if age_hours >= critical_hours:
        return "critical", f"age {age_hours:.1f}h exceeds critical threshold {critical_hours:g}h"
    if age_hours >= warning_hours:
        return "warning", f"age {age_hours:.1f}h exceeds warning threshold {warning_hours:g}h"
    return "healthy", "within freshness SLA"


def dataset_threshold_hours(policy: dict[str, Any], dataset: str) -> tuple[float, float]:
    config = policy.get("datasets", {}).get(dataset, {})
    if "warningHours" in config and "criticalHours" in config:
        return float(config["warningHours"]), float(config["criticalHours"])
    return float(config.get("warningDays", 0)) * 24, float(config.get("criticalDays", 0)) * 24


def public_company_count(companies_payload: dict[str, Any]) -> int:
    companies = item_list(companies_payload, "companies")
    ids = {str(company.get("company_id") or "").strip() for company in companies}
    ids.discard("")
    return len(ids)


def audit_datasets(
    *,
    news_payload: dict[str, Any],
    business_payload: dict[str, Any],
    companies_payload: dict[str, Any],
    company_v2_payload: dict[str, Any] | None,
    meta_payload: dict[str, Any],
    policy: dict[str, Any],
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    datasets: list[dict[str, Any]] = []

    inputs = [
        ("news", news_payload, item_list(news_payload), ("published_at", "posted_at"), news_payload.get("generated_at") or meta_payload.get("generated_at")),
        ("business", business_payload, item_list(business_payload), ("posted_at", "notice_date", "deadline"), business_payload.get("generated_at") or meta_payload.get("generated_at")),
    ]
    for name, payload, items, date_fields, generated_at in inputs:
        latest = parse_datetime(payload.get(f"latest_public_{name}_published_at")) or latest_item_at(items, date_fields)
        if name == "business":
            collection_times = [
                parse_datetime(payload.get("generated_at")),
                parse_datetime(meta_payload.get("generated_at")),
                parse_datetime(meta_payload.get("last_collected_at")),
                parse_datetime(payload.get("procurement_plan_last_collected_at")),
            ]
            latest_collection = max([item for item in collection_times if item], default=None)
            if latest_collection and (latest is None or latest_collection > latest):
                latest = latest_collection
        warning, critical = dataset_threshold_hours(policy, name)
        age_hours = (now - latest).total_seconds() / 3600 if latest else None
        state, reason = freshness_state(age_hours, warning, critical, record_count=len(items), timestamp_missing=latest is None)
        datasets.append(
            {
                "dataset": name,
                "recordCount": len(items),
                "generatedAt": str(generated_at or ""),
                "latestItemAt": iso_or_empty(latest),
                "ageHours": round(age_hours, 2) if age_hours is not None else None,
                "warningThreshold": warning,
                "criticalThreshold": critical,
                "state": state,
                "reason": reason,
            }
        )

    company_count = public_company_count(companies_payload)
    company_generated = parse_datetime(companies_payload.get("generated_at"))
    company_v2_generated = parse_datetime((company_v2_payload or {}).get("generated_at"))
    latest_company_at = max([dt for dt in [company_generated, company_v2_generated] if dt], default=None)
    warning, critical = dataset_threshold_hours(policy, "companies")
    age_hours = (now - latest_company_at).total_seconds() / 3600 if latest_company_at else None
    state, reason = freshness_state(age_hours, warning, critical, record_count=company_count, timestamp_missing=latest_company_at is None)
    minimum = int(policy.get("datasets", {}).get("companies", {}).get("minimumPublicCount", 0))
    if minimum and company_count < minimum:
        state = "critical"
        reason = f"public company count {company_count} is below minimum {minimum}"
    datasets.append(
        {
            "dataset": "companies",
            "recordCount": company_count,
            "generatedAt": companies_payload.get("generated_at", ""),
            "latestItemAt": iso_or_empty(latest_company_at),
            "ageDays": round(age_hours / 24, 2) if age_hours is not None else None,
            "warningThreshold": warning / 24,
            "criticalThreshold": critical / 24,
            "state": state,
            "reason": reason,
        }
    )
    return datasets


def safe_message(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    for token in ("Authorization", "X-NCP-APIGW-API-KEY", "NAVER_API_HUB_CLIENT_SECRET", "NAVER_API_HUB_CLIENT_ID", "DART_API_KEY"):
        text = text.replace(token, "[redacted-key-name]")
    return text[:SAFE_MESSAGE_MAX]


def normalize_source_health(raw: dict[str, Any], policy: dict[str, Any], category: str = "unknown") -> dict[str, Any]:
    aliases = policy.get("sourceStateAliases", {})
    source_id = str(raw.get("id") or raw.get("source_id") or raw.get("source") or raw.get("source_name") or "unknown").strip()
    source_name = str(raw.get("name") or raw.get("source_name") or source_id)
    raw_state = str(raw.get("state") or raw.get("status") or "unknown").strip()
    normalized_state = aliases.get(raw_state, raw_state if raw_state else "unknown")
    error_category = str(raw.get("safe_error_category") or raw.get("errorCategory") or raw.get("error_category") or "none")
    if error_category in {"auth_error", "permission_error", "rate_limited", "timeout", "parse_error"}:
        normalized_state = error_category
    return {
        "sourceId": source_id,
        "sourceName": source_name,
        "category": raw.get("source_type") or category,
        "enabled": bool(raw.get("enabled", True)),
        "configured": bool(raw.get("configured", raw.get("state") != "missing_secret")),
        "lastAttemptedAt": str(raw.get("last_attempted_at") or raw.get("lastAttemptedAt") or ""),
        "lastSuccessfulAt": str(raw.get("last_successful_at") or raw.get("lastSuccessfulAt") or ""),
        "latestSourceItemAt": str(raw.get("latest_item_published_at") or raw.get("latestSourceItemAt") or ""),
        "fetchedCount": int(raw.get("fetched_count") or raw.get("fetchedCount") or 0),
        "acceptedCount": int(raw.get("accepted_count") or raw.get("acceptedCount") or 0),
        "duplicateCount": int(raw.get("duplicate_count") or raw.get("duplicateCount") or 0),
        "rejectedCount": int(raw.get("rejected_count") or raw.get("rejectedCount") or 0),
        "httpStatus": str(raw.get("http_status") or raw.get("httpStatus") or ""),
        "state": normalized_state,
        "errorCategory": error_category,
        "safeMessage": safe_message(raw.get("message") or raw.get("safe_message") or raw.get("safeMessage") or ""),
    }


def source_health_from_payloads(news_payload: dict[str, Any], business_payload: dict[str, Any], meta_payload: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for raw in news_payload.get("news_source_statuses") or meta_payload.get("news_source_statuses") or []:
        if isinstance(raw, dict):
            sources.append(normalize_source_health(raw, policy, "news"))
    business_sources = [
        {"id": "g2b", "name": "나라장터", "source_type": "business", "state": business_payload.get("g2b_order_plan_status"), "last_attempted_at": business_payload.get("procurement_plan_last_collected_at"), "safe_message": business_payload.get("g2b_order_plan_message")},
        {"id": "d2b", "name": "D2B", "source_type": "business", "state": business_payload.get("d2b_status"), "safe_message": business_payload.get("d2b_message")},
        {"id": "lh", "name": "LH", "source_type": "business", "state": business_payload.get("lh_contest_status"), "last_attempted_at": business_payload.get("lh_contest_last_attempt"), "last_successful_at": business_payload.get("lh_contest_last_success"), "fetched_count": business_payload.get("lh_contest_scanned_count"), "accepted_count": business_payload.get("lh_contest_public_count"), "safe_message": business_payload.get("lh_contest_message")},
        {"id": "gh", "name": "GH", "source_type": "business", "state": business_payload.get("gh_contest_status"), "last_attempted_at": business_payload.get("gh_contest_last_attempt"), "last_successful_at": business_payload.get("gh_contest_last_success"), "fetched_count": business_payload.get("gh_contest_scanned_count"), "accepted_count": business_payload.get("gh_contest_public_count"), "safe_message": business_payload.get("gh_contest_message")},
        {"id": "ih", "name": "iH", "source_type": "business", "state": business_payload.get("ih_contest_status"), "last_attempted_at": business_payload.get("ih_contest_last_attempt"), "last_successful_at": business_payload.get("ih_contest_last_success"), "fetched_count": business_payload.get("ih_contest_scanned_count"), "accepted_count": business_payload.get("ih_contest_public_count"), "safe_message": business_payload.get("ih_contest_message")},
    ]
    for raw in business_sources:
        sources.append(normalize_source_health(raw, policy, "business"))
    return sources


def count_delta_guard(current: int, previous: int, config: dict[str, Any], dataset: str) -> dict[str, Any]:
    delta = current - previous
    percent = ((previous - current) / previous * 100) if previous > 0 and current < previous else 0.0
    state = "healthy"
    reason = "count did not decrease"
    if dataset == "companies":
        drop_limit = int(config.get("countDropCritical", 1))
        minimum = int(config.get("minimumPublicCount", 0))
        if current < minimum:
            state, reason = "critical", f"company count {current} is below minimum {minimum}"
        elif previous - current >= drop_limit:
            state, reason = "critical", f"company count decreased by {previous - current}"
    elif percent > float(config.get("countDropCriticalPercent", 100)):
        state, reason = "critical", f"count decreased by {percent:.1f}%"
    return {"dataset": dataset, "previousCount": previous, "currentCount": current, "delta": delta, "dropPercent": round(percent, 2), "state": state, "reason": reason}


def issue_fingerprint(dataset: str, source_id: str, error_category: str) -> str:
    basis = f"{dataset}:{source_id}:{error_category}".lower()
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
    return f"modularhub-ops-{digest}"


def contains_secret_indicator(text: str, policy: dict[str, Any]) -> bool:
    indicators = [str(item) for item in policy.get("secretIndicators", [])]
    return any(indicator and indicator in text for indicator in indicators)


def worst_state(records: list[dict[str, Any]]) -> str:
    state = "healthy"
    for record in records:
        candidate = str(record.get("state") or "unknown")
        if STATE_ORDER.get(candidate, 1) > STATE_ORDER.get(state, 0):
            state = candidate
    return state
