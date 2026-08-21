from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlsplit

from scripts.export_public_json import (
    BUSINESS_SOURCES,
    BUSINESS_TYPES,
    include_business_row,
    manual_check,
    sanitize_url,
)
from scripts.integrations.business.base import NormalizedBusinessRecord
from src.public_data_policy import (
    apply_business_lifecycle,
    business_identity,
    business_items_substantively_equal,
    clean_text,
    parse_public_datetime,
    payload_items,
)


PUBLIC_PROJECTION_SCHEMA_VERSION = "public-business-projection-v1"
PUBLIC_SOURCE_NAMES = {
    "d2b": "D2B",
    "g2b": "G2B",
    "lh": "LH",
}
PUBLIC_SOURCE_TYPES = {
    "procurement_plan": "procurement_plan",
    "pre_spec": "bid",
    "bid_notice": "bid",
}
PUBLIC_TYPE_LABELS = {
    "procurement_plan": "발주계획",
    "pre_spec": "사전규격",
    "bid_notice": "입찰공고",
}
REQUIRED_PUBLIC_FIELDS = (
    "id",
    "source",
    "source_name",
    "source_type",
    "type",
    "title",
    "organization",
    "notice_status",
    "source_record_id",
    "posted_at",
)
SENSITIVE_QUERY_KEYS = {
    "access_token",
    "apikey",
    "api_key",
    "authorization",
    "client_id",
    "client_secret",
    "servicekey",
    "service_key",
    "token",
}
FORBIDDEN_RAW_KEYS = {
    "authorization",
    "headers",
    "raw_api_json",
    "raw_http_response",
    "raw_json",
    "raw_response",
    "raw_xml",
    "request_headers",
    "service_key",
    "servicekey",
}
def public_id(record: NormalizedBusinessRecord) -> str:
    """Follow the existing source-prefixed string ID convention used by public contests."""

    return f"{record.source.lower()}_{record.source_record_type}:{record.external_id}"


def public_relevance_decision(record: NormalizedBusinessRecord) -> tuple[bool, str | None]:
    row = _collector_row(record)
    if row is None:
        return False, "unsupported_existing_public_source_or_type"
    if include_business_row(row):
        return True, None
    if row["source_name"] not in BUSINESS_SOURCES or row["source_type"] not in BUSINESS_TYPES:
        return False, "unsupported_existing_public_source_or_type"
    return False, "existing_public_relevance_policy_no_match"


def project_record(record: NormalizedBusinessRecord) -> dict[str, Any]:
    row = _collector_row(record)
    if row is None:
        raise ValueError(
            f"canonical source/type cannot be represented by the current public contract: "
            f"{record.source}/{record.source_record_type}"
        )

    source_type = row["source_type"]
    record_no = record.external_id
    source_url = sanitize_url(clean_text(record.source_url)) or None
    item_type = PUBLIC_TYPE_LABELS[record.source_record_type]
    return {
        "id": public_id(record),
        "source": row["source_name"],
        "source_name": row["source_name"],
        "source_type": source_type,
        "type": item_type,
        "title": clean_text(record.title),
        "organization": clean_text(record.issuing_organization),
        "demand_org": clean_text(record.issuing_organization),
        "business_type": clean_text(record.category),
        "business_subtype": clean_text(record.contract_method),
        "notice_status": clean_text(record.status),
        "notice_stage": clean_text(record.status),
        "source_record_id": record_no,
        "source_record_no": "",
        "plan_no": record_no if source_type == "procurement_plan" else "",
        "bid_no": record_no,
        "bid_order": "",
        "posted_at": record.published_at,
        "due_at": record.deadline_at,
        "amount": record.estimated_amount,
        "region": clean_text(record.region),
        "summary": "",
        "keywords": "",
        "relevance_score": 0,
        "is_known_important": False,
        "is_operating_scope": True,
        "display_type": item_type,
        "modular_relevance": "",
        "modular_evidence": [],
        "project_name": "",
        "project_sites": [],
        "project_blocks": [],
        "application_schedule_text": "",
        "household_count": None,
        "housing_type": "",
        "attachments": [],
        "related_group_key": "",
        "exact_link_verified": False,
        "external_original_url": source_url,
        "manual_check": manual_check(row),
        "detail": None,
    }


def build_public_projection(
    records: Iterable[NormalizedBusinessRecord],
    public_payload: dict[str, Any] | list[dict[str, Any]],
    *,
    unified_summary: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    canonical_records = list(records)
    existing_items = deepcopy(payload_items(public_payload))
    generated_at = clean_text((unified_summary or {}).get("generated_at")) or _derived_generated_at(canonical_records)
    reference_time = _reference_time(generated_at)

    source_stats = {
        source: {"input": 0, "publishable": 0, "filtered": 0, "existing": 0, "net_new": 0}
        for source in sorted(set(PUBLIC_SOURCE_NAMES) | {record.source for record in canonical_records})
    }
    type_stats = {
        record_type: {"input": 0, "publishable": 0, "filtered": 0, "existing": 0, "net_new": 0}
        for record_type in sorted({record.source_record_type for record in canonical_records})
    }
    filtered_reasons: Counter[str] = Counter()
    publishable_records: list[NormalizedBusinessRecord] = []
    input_credential_urls = 0

    for record in canonical_records:
        source_stats.setdefault(
            record.source, {"input": 0, "publishable": 0, "filtered": 0, "existing": 0, "net_new": 0}
        )["input"] += 1
        type_stats.setdefault(
            record.source_record_type,
            {"input": 0, "publishable": 0, "filtered": 0, "existing": 0, "net_new": 0},
        )["input"] += 1
        input_credential_urls += int(_credential_bearing_url(record.source_url))
        accepted, reason = public_relevance_decision(record)
        if accepted:
            publishable_records.append(record)
            source_stats[record.source]["publishable"] += 1
            type_stats[record.source_record_type]["publishable"] += 1
        else:
            reason = reason or "unknown"
            filtered_reasons[reason] += 1
            source_stats[record.source]["filtered"] += 1
            type_stats[record.source_record_type]["filtered"] += 1

    projected_items = [project_record(record) for record in publishable_records]
    projected_items = apply_business_lifecycle(
        projected_items,
        now=reference_time,
        default_last_seen_at=generated_at or None,
    )
    projected_items = _sort_public_items(projected_items)

    required_field_failures = _required_field_failures(projected_items)
    frontend_contract_issues = _frontend_contract_issues(publishable_records, projected_items)

    existing_by_id = {str(item.get("id")): item for item in existing_items}
    existing_by_lineage: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for item in existing_items:
        existing_by_lineage.setdefault(business_identity(item), []).append(item)

    exact_existing_matches = 0
    lineage_matches = 0
    public_id_collisions: list[dict[str, Any]] = []
    net_new_items: list[dict[str, Any]] = []
    publishable_by_id = {public_id(record): record for record in publishable_records}
    for item in projected_items:
        record = publishable_by_id[str(item["id"])]
        existing_same_id = existing_by_id.get(str(item["id"]))
        if existing_same_id is not None:
            if _same_substantive_public_payload(existing_same_id, item):
                exact_existing_matches += 1
                _increment_existing(source_stats, type_stats, record)
            else:
                public_id_collisions.append(
                    {
                        "public_id": item["id"],
                        "source": record.source,
                        "source_record_type": record.source_record_type,
                        "external_id": record.external_id,
                    }
                )
            continue
        if business_identity(item) in existing_by_lineage:
            lineage_matches += 1
            _increment_existing(source_stats, type_stats, record)
            continue
        net_new_items.append(item)
        source_stats[record.source]["net_new"] += 1
        type_stats[record.source_record_type]["net_new"] += 1

    possible_overlap_candidates = _possible_overlap_candidates(existing_items, net_new_items)
    candidate_items = _sort_public_items([*existing_items, *deepcopy(net_new_items)])
    candidate_payload = _candidate_payload(public_payload, candidate_items)
    existing_records_removed = _existing_records_removed(existing_items, candidate_items)

    candidate_credential_urls = _count_credential_urls(candidate_payload)
    raw_payload_fields = _count_forbidden_raw_keys(candidate_payload)
    security = {
        "credential_urls_detected": input_credential_urls + candidate_credential_urls,
        "raw_payload_fields_detected": raw_payload_fields,
        "passed": input_credential_urls + candidate_credential_urls == 0 and raw_payload_fields == 0,
    }
    candidate_count_conservation_passed = len(candidate_items) == len(existing_items) + len(net_new_items)

    report = {
        "schema_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
        "baseline_public_count": len(existing_items),
        "unified_input_count": len(canonical_records),
        "publishable_count": len(publishable_records),
        "filtered_count": len(canonical_records) - len(publishable_records),
        "filtered_reasons": dict(sorted(filtered_reasons.items())),
        "projected_count": len(projected_items),
        "exact_existing_matches": exact_existing_matches,
        "lineage_matches": lineage_matches,
        "net_new_count": len(net_new_items),
        "public_id_collision_count": len(public_id_collisions),
        "public_id_collisions": public_id_collisions,
        "possible_overlap_candidate_count": len(possible_overlap_candidates),
        "possible_overlap_candidates": possible_overlap_candidates,
        "candidate_public_count": len(candidate_items),
        "candidate_count_conservation_passed": candidate_count_conservation_passed,
        "existing_records_removed": existing_records_removed,
        "required_field_failures": required_field_failures,
        "frontend_contract_issues": frontend_contract_issues,
        "sources": {key: source_stats[key] for key in sorted(source_stats)},
        "record_types": {key: type_stats[key] for key in sorted(type_stats)},
        "security": security,
    }
    return projected_items, candidate_payload, report


def write_public_projection_outputs(
    projected_items: list[dict[str, Any]],
    candidate_payload: dict[str, Any],
    report: dict[str, Any],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "projected_business_records.json": projected_items,
        "candidate_business.json": candidate_payload,
        "public_projection_report.json": report,
    }
    for filename, payload in outputs.items():
        (output_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def projection_blockers(report: dict[str, Any]) -> list[str]:
    blockers = []
    if report["public_id_collision_count"]:
        blockers.append("public_id_collision")
    if report["existing_records_removed"]:
        blockers.append("public_data_preservation")
    if report["required_field_failures"]:
        blockers.append("public_projection_contract")
    if report["frontend_contract_issues"]:
        blockers.append("frontend_business_contract")
    if not report["candidate_count_conservation_passed"]:
        blockers.append("candidate_count_conservation")
    if not report["security"]["passed"]:
        blockers.append("public_projection_security")
    return blockers


def select_net_new_projected_items(
    projected_items: Iterable[dict[str, Any]],
    existing_items: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    existing = list(existing_items)
    existing_ids = {str(item.get("id")) for item in existing}
    existing_lineages = {business_identity(item) for item in existing}
    return _sort_public_items(
        [
            deepcopy(item)
            for item in projected_items
            if str(item.get("id")) not in existing_ids and business_identity(item) not in existing_lineages
        ]
    )


def _same_substantive_public_payload(
    existing_item: dict[str, Any], projected_item: dict[str, Any]
) -> bool:
    return business_items_substantively_equal(existing_item, projected_item)


def _collector_row(record: NormalizedBusinessRecord) -> dict[str, Any] | None:
    source_name = PUBLIC_SOURCE_NAMES.get(record.source.lower())
    source_type = PUBLIC_SOURCE_TYPES.get(record.source_record_type)
    if not source_name or not source_type:
        return None
    return {
        "source_name": source_name,
        "source_type": source_type,
        "source_record_id": record.external_id,
        "source_record_no": "",
        "title": record.title,
        "organization": record.issuing_organization,
        "business_type": record.category,
        "business_subtype": record.contract_method,
        "notice_status": record.status,
        "posted_at": record.published_at,
        "due_at": record.deadline_at,
        "amount": record.estimated_amount,
        "region": record.region,
        "summary": "",
        "keywords": "",
        "is_known_important": False,
        "is_operating_scope": True,
        "original_url": record.source_url,
    }


def _required_field_failures(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures = []
    for item in items:
        missing = [field for field in REQUIRED_PUBLIC_FIELDS if item.get(field) in (None, "")]
        issues = []
        for field in ("posted_at", "due_at"):
            if item.get(field) and parse_public_datetime(item[field]) is None:
                issues.append(f"invalid_{field}")
        amount = item.get("amount")
        if amount is not None and (isinstance(amount, bool) or not isinstance(amount, (int, float))):
            issues.append("invalid_amount_type")
        if item.get("source_type") not in {"bid", "procurement_plan", "public_agency_contest"}:
            issues.append("invalid_source_type")
        link = item.get("external_original_url") or item.get("manual_check", {}).get("site_url")
        if not _safe_http_url(link):
            issues.append("missing_or_invalid_url")
        if missing or issues:
            failures.append({"id": item.get("id"), "missing": missing, "issues": issues})
    return failures


def _frontend_contract_issues(
    records: list[NormalizedBusinessRecord], items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    issues = []
    for record, item in zip(records, items, strict=True):
        if record.source_record_type == "pre_spec":
            issues.append(
                {
                    "id": item["id"],
                    "issue": "pre_spec_not_distinguishable_in_current_frontend_source_type_contract",
                }
            )
        if record.currency != "KRW" and record.estimated_amount is not None:
            issues.append({"id": item["id"], "issue": "non_krw_amount_currency_not_representable"})
        if record.source == "lh" and item["source_type"] in {"bid", "procurement_plan"}:
            issues.append({"id": item["id"], "issue": "lh_direct_source_is_displayed_as_g2b_by_current_frontend"})
    return issues


def _candidate_payload(
    public_payload: dict[str, Any] | list[dict[str, Any]], candidate_items: list[dict[str, Any]]
) -> dict[str, Any]:
    payload = deepcopy(public_payload) if isinstance(public_payload, dict) else {}
    payload["items"] = candidate_items
    payload["business_total"] = len(candidate_items)
    payload["merged_business_count"] = len(candidate_items)
    payload["procurement_plan_count"] = sum(item.get("source_type") == "procurement_plan" for item in candidate_items)
    payload["procurement_plan_total"] = payload["procurement_plan_count"]
    payload["bid_total"] = sum(item.get("source_type") == "bid" for item in candidate_items)
    payload["public_agency_contest_total"] = sum(
        item.get("source_type") == "public_agency_contest" for item in candidate_items
    )
    payload["business_active"] = sum(item.get("opportunity_status") == "active" for item in candidate_items)
    payload["business_closed"] = sum(item.get("opportunity_status") == "closed" for item in candidate_items)
    payload["business_unknown"] = sum(item.get("opportunity_status") == "unknown" for item in candidate_items)
    return payload


def _possible_overlap_candidates(
    existing_items: list[dict[str, Any]], net_new_items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    candidates = []
    seen_pairs: set[tuple[str, str]] = set()
    prior_items = list(existing_items)
    for item in net_new_items:
        for other in prior_items:
            if business_identity(item) == business_identity(other):
                continue
            if _normalize_match_text(item.get("title")) != _normalize_match_text(other.get("title")):
                continue
            if _normalize_match_text(item.get("organization")) != _normalize_match_text(other.get("organization")):
                continue
            matching_dates = [
                field
                for field in ("posted_at", "due_at")
                if item.get(field) and item.get(field) == other.get(field)
            ]
            if not matching_dates:
                continue
            pair = tuple(sorted((str(item.get("id")), str(other.get("id")))))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            seed = json.dumps(pair, ensure_ascii=False, separators=(",", ":"))
            candidates.append(
                {
                    "candidate_id": hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16],
                    "public_ids": list(pair),
                    "match_basis": ["normalized_title", "normalized_organization", *matching_dates],
                }
            )
        prior_items.append(item)
    return sorted(candidates, key=lambda value: value["candidate_id"])


def _existing_records_removed(existing_items: list[dict[str, Any]], candidate_items: list[dict[str, Any]]) -> int:
    existing_payloads = Counter(_stable_json(item) for item in existing_items)
    candidate_payloads = Counter(_stable_json(item) for item in candidate_items)
    return sum(max(0, count - candidate_payloads[payload]) for payload, count in existing_payloads.items())


def _increment_existing(
    source_stats: dict[str, dict[str, int]],
    type_stats: dict[str, dict[str, int]],
    record: NormalizedBusinessRecord,
) -> None:
    source_stats[record.source]["existing"] += 1
    type_stats[record.source_record_type]["existing"] += 1


def _sort_public_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (clean_text(item.get("posted_at")), clean_text(item.get("id"))),
        reverse=True,
    )


def _reference_time(value: str) -> datetime:
    if value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _derived_generated_at(records: list[NormalizedBusinessRecord]) -> str:
    values = [value for record in records for value in (record.collected_at, record.source_updated_at) if value]
    return max(values) if values else ""


def _normalize_match_text(value: Any) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", clean_text(value).casefold())


def _safe_http_url(value: Any) -> bool:
    if not value:
        return False
    try:
        parsed = urlsplit(str(value))
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


def _credential_bearing_url(value: Any) -> bool:
    if not _safe_http_url(value):
        return False
    try:
        return any(key.lower() in SENSITIVE_QUERY_KEYS for key, _ in parse_qsl(urlsplit(str(value)).query))
    except ValueError:
        return False


def _count_credential_urls(value: Any) -> int:
    if isinstance(value, dict):
        return sum(_count_credential_urls(item) for item in value.values())
    if isinstance(value, list):
        return sum(_count_credential_urls(item) for item in value)
    return int(isinstance(value, str) and _credential_bearing_url(value))


def _count_forbidden_raw_keys(value: Any) -> int:
    if isinstance(value, dict):
        count = sum(str(key).lower().replace("-", "_") in FORBIDDEN_RAW_KEYS for key in value)
        return count + sum(_count_forbidden_raw_keys(item) for item in value.values())
    if isinstance(value, list):
        return sum(_count_forbidden_raw_keys(item) for item in value)
    return 0


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
