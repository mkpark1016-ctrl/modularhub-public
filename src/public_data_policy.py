from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlsplit

from src.overseas_news_rules import overseas_news_content_key

ROOT = Path(__file__).resolve().parents[1]
REMOVAL_ALLOWLIST_PATH = ROOT / "config" / "public_data_removal_allowlist.json"
BUSINESS_SHRINK_THRESHOLD = 0.20
NEWS_SHRINK_THRESHOLD = 0.30
KST = timezone(timedelta(hours=9), "KST")
PUBLIC_NEWS_POLICY_VERSION = "unified-v2-publication-v1"
PUBLISHABLE_RELEVANCE_LEVELS = {"direct", "adjacent", "reference"}
OVERSEAS_RSS_SOURCE = "해외 모듈러 RSS"
CONTROLLED_PUBLIC_BUSINESS_PATH = "frontend/public/data/business.json"
CONTROLLED_PUBLIC_META_PATH = "frontend/public/data/meta.json"
CONTROLLED_PUBLIC_COMPANIES_PATH = "frontend/public/data/companies/companies.json"
CONTROLLED_PUBLICATION_PATHS = {
    CONTROLLED_PUBLIC_BUSINESS_PATH,
    CONTROLLED_PUBLIC_META_PATH,
}
CONTROLLED_PUBLICATION_SCHEMA_VERSION = "controlled-publication-protection-v1"
SENSITIVE_PUBLIC_QUERY_KEYS = {
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
FORBIDDEN_PUBLIC_PAYLOAD_KEYS = {
    "access_token",
    "apikey",
    "api_key",
    "authorization",
    "client_id",
    "client_secret",
    "headers",
    "raw_api_json",
    "raw_http_response",
    "raw_json",
    "raw_response",
    "raw_xml",
    "request_headers",
    "service_key",
    "servicekey",
    "token",
}
PUBLIC_LOCAL_PATH_PATTERNS = (
    ("windows_drive", re.compile(r"^[A-Za-z]:[\\\\/]")),
    ("file_url", re.compile(r"^file://", re.IGNORECASE)),
    ("unc", re.compile(r"^\\\\[^\\/]+[\\/][^\\/]+")),
    (
        "unix_absolute",
        re.compile(
            r"^/(?:Users|Volumes|home|mnt|opt|private|root|srv|tmp|var)(?:/|$)"
        ),
    ),
)
BUSINESS_METADATA_COUNT_FIELDS = (
    "business_total",
    "business_active",
    "business_closed",
    "business_unknown",
    "bid_total",
    "procurement_plan_count",
    "procurement_plan_total",
    "public_agency_contest_total",
)
BUSINESS_METADATA_MIRROR_FIELDS = (
    *BUSINESS_METADATA_COUNT_FIELDS,
    "previous_business_count",
    "merged_business_count",
    "public_data_guard_status",
    "public_data_guard_message",
    "d2b_status",
    "d2b_legacy_status",
    "d2b_gw_migration_required",
    "d2b_unified_status",
    "d2b_unified_public_count",
    "d2b_unified_last_collected_at",
    "procurement_plan_source_status",
)
BUSINESS_LIFECYCLE_DERIVED_FIELDS = frozenset(
    {
        "closed_at",
        "days_until_deadline",
        "is_closed",
        "last_seen_at",
        "lifecycle_reason",
        "opportunity_status",
    }
)
BUSINESS_AUTHORITATIVE_REFRESH_FIELDS = frozenset(
    {
        "due_at",
        "notice_stage",
        "notice_status",
    }
)
BUSINESS_VERIFIED_EVIDENCE_REFRESH_FIELDS = frozenset(
    {
        "attachments",
        "external_original_url",
        "original_url",
    }
)
BUSINESS_EVIDENCE_VERIFICATION_FIELDS = frozenset(
    {
        "exact_link_verified",
        "link_verified",
    }
)
BUSINESS_SAFE_EMPTY_FIELD_ENRICHMENT_FIELDS = frozenset()
SAMSUNG_TECHNOLOGY_COMPANY_ID = "samsung-ct-construction"
SAMSUNG_TECHNOLOGY_BASELINE_IDS = frozenset(
    f"tech-samsung-{index:03d}" for index in range(1, 8)
)
SAMSUNG_TECHNOLOGY_NEW_IDS = frozenset(
    {
        "tech-samsung-kipris-1020230005994",
        "tech-samsung-kipris-1020230005995",
        "tech-samsung-kipris-1020230050560",
        "tech-samsung-kipris-1020230050561",
        "tech-samsung-kipris-1020230091868",
        "tech-samsung-kipris-1020230105666",
    }
)
SAMSUNG_TECHNOLOGY_ENRICHMENT_FIELDS = frozenset(
    {"application_number", "patent_number", "application_date", "registration_date"}
)
SAMSUNG_TECHNOLOGY_STATUS_TRANSITIONS = {
    "tech-samsung-006": ("registered", "expired"),
    "tech-samsung-007": ("registered", "expired"),
}
SAMSUNG_TECHNOLOGY_SOURCE_ID = "samsung-kipris-direct-patents-20260824"
SAMSUNG_NEW_TECHNOLOGY_REQUIRED_FIELDS = frozenset(
    {
        "technology_id",
        "name",
        "record_type",
        "registration_number",
        "application_number",
        "patent_number",
        "status",
        "technology_area",
        "application_date",
        "registration_date",
        "summary",
        "source_ids",
    }
)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "none", "nan", "nat"} else text


def classify_public_local_path(value: Any) -> str | None:
    """Classify absolute local filesystem values without retaining the value."""

    if not isinstance(value, str):
        return None
    candidate = value.strip()
    for path_kind, pattern in PUBLIC_LOCAL_PATH_PATTERNS:
        if pattern.match(candidate):
            return path_kind
    return None


def find_public_local_paths(
    value: Any,
    *,
    json_path: str = "$",
    field: str | None = None,
) -> list[dict[str, str | None]]:
    """Return redacted structural diagnostics for local paths in a JSON payload."""

    findings: list[dict[str, str | None]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key_text):
                child_path = f"{json_path}.{key_text}"
            else:
                child_path = f"{json_path}[{json.dumps(key_text, ensure_ascii=False)}]"
            findings.extend(
                find_public_local_paths(
                    child,
                    json_path=child_path,
                    field=key_text,
                )
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(
                find_public_local_paths(
                    child,
                    json_path=f"{json_path}[{index}]",
                    field=field,
                )
            )
    else:
        path_kind = classify_public_local_path(value)
        if path_kind:
            findings.append(
                {
                    "json_path": json_path,
                    "field": field,
                    "path_kind": path_kind,
                }
            )
    return findings


def scan_public_payload_security(value: Any) -> dict[str, Any]:
    """Inspect a public payload while keeping sensitive values out of diagnostics."""

    local_path_findings = find_public_local_paths(value)
    credential_url_count = _count_credential_bearing_urls(value)
    forbidden_field_count = _count_forbidden_public_keys(value)
    return {
        "passed": not (
            local_path_findings or credential_url_count or forbidden_field_count
        ),
        "local_path_count": len(local_path_findings),
        "local_path_findings": local_path_findings,
        "credential_url_count": credential_url_count,
        "forbidden_field_count": forbidden_field_count,
    }


def validate_public_local_path_cleanup(before: Any, after: Any) -> dict[str, Any]:
    """Allow only deletion of existing local-path values from a public payload."""

    before_findings = find_public_local_paths(before)
    after_findings = find_public_local_paths(after)
    sanitized_before = _without_public_local_paths(before)
    passed = bool(before_findings) and not after_findings and sanitized_before == after
    return {
        "passed": passed,
        "removed_local_path_count": len(before_findings) if passed else 0,
        "remaining_local_path_count": len(after_findings),
        "other_changes": 0 if passed else int(sanitized_before != after),
    }


def _without_public_local_paths(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_public_local_paths(child)
            for key, child in value.items()
            if classify_public_local_path(child) is None
        }
    if isinstance(value, list):
        return [_without_public_local_paths(child) for child in value]
    return value


def payload_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        items = payload.get("items", [])
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def business_items_substantively_equal(
    before: dict[str, Any], after: dict[str, Any]
) -> bool:
    """Compare public business records without derived lifecycle state."""

    return not changed_business_fields(before, after)


def safe_business_refresh_fields(
    before: dict[str, Any], after: dict[str, Any]
) -> list[str]:
    """Return changed fields allowed by the narrow existing-record contract.

    Official deadline/status values may refresh when non-empty. Evidence fields
    may refresh only when the candidate carries a verified exact-source link;
    verification itself is monotonic and cannot be downgraded. Identity or any
    other substantive mutation makes the transition unsafe.
    """

    changed = changed_business_fields(before, after)
    if business_identity(before) != business_identity(after):
        return []

    verified = bool(
        after.get("exact_link_verified") or after.get("link_verified")
    )
    safe: list[str] = []
    for field in changed:
        value = after.get(field)
        if field in BUSINESS_AUTHORITATIVE_REFRESH_FIELDS and _nonempty(value):
            safe.append(field)
        elif (
            field in BUSINESS_VERIFIED_EVIDENCE_REFRESH_FIELDS
            and verified
            and _nonempty(value)
        ):
            safe.append(field)
        elif (
            field in BUSINESS_EVIDENCE_VERIFICATION_FIELDS
            and not bool(before.get(field))
            and bool(value)
        ):
            safe.append(field)
    return safe


def unsafe_business_refresh_fields(
    before: dict[str, Any], after: dict[str, Any]
) -> list[str]:
    """Return substantive changes that are outside the refresh contract."""

    changed = changed_business_fields(before, after)
    safe = set(safe_business_refresh_fields(before, after))
    return [field for field in changed if field not in safe]


def business_items_safely_refreshable(
    before: dict[str, Any], after: dict[str, Any]
) -> bool:
    """Whether an existing public record transition is publication-safe."""

    return not unsafe_business_refresh_fields(before, after)


def changed_business_fields(
    before: dict[str, Any], after: dict[str, Any]
) -> list[str]:
    """Return deterministic substantive top-level field names without values."""

    missing = object()
    return sorted(
        key
        for key in set(before) | set(after)
        if key not in BUSINESS_LIFECYCLE_DERIVED_FIELDS
        and before.get(key, missing) != after.get(key, missing)
    )


def validate_controlled_business_publication(
    before_business: dict[str, Any],
    after_business: dict[str, Any],
    before_meta: dict[str, Any],
    after_meta: dict[str, Any],
    changed_paths: list[str] | set[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Validate an additive business publication from payload semantics alone."""
    normalized_paths = sorted({_normalized_repo_path(path) for path in changed_paths if path})
    public_paths_changed = sorted(CONTROLLED_PUBLICATION_PATHS.intersection(normalized_paths))
    before_items, before_shape_valid = _strict_payload_items(before_business)
    after_items, after_shape_valid = _strict_payload_items(after_business)
    failures: set[str] = set()

    if not public_paths_changed:
        return _controlled_publication_result(
            failures,
            normalized_paths,
            before_items,
            after_items,
            status="NO_CONTROLLED_PUBLIC_DATA_CHANGE",
        )

    if set(normalized_paths) != CONTROLLED_PUBLICATION_PATHS:
        failures.add("changed_file_scope_invalid")
    if not before_shape_valid or not after_shape_valid:
        failures.add("business_items_invalid")

    before_ids = _item_id_counts(before_items)
    after_ids = _item_id_counts(after_items)
    before_id_set = set(before_ids)
    after_id_set = set(after_ids)
    missing_id_count = before_ids.get("", 0) + after_ids.get("", 0)
    duplicate_id_count = sum(max(0, count - 1) for count in after_ids.values())
    if missing_id_count:
        failures.add("public_id_missing")
    if duplicate_id_count:
        failures.add("public_id_collision")

    after_identity_counts = _identity_counts(after_items)
    duplicate_identity_count = sum(max(0, count - 1) for count in after_identity_counts.values())
    if duplicate_identity_count:
        failures.add("duplicate_business_identity")

    removed_ids = before_id_set - after_id_set
    if removed_ids:
        failures.add("existing_business_removed")
    before_by_id = {clean_text(item.get("id")): item for item in before_items if clean_text(item.get("id"))}
    after_by_id = {clean_text(item.get("id")): item for item in after_items if clean_text(item.get("id"))}
    modified_ids = {
        item_id
        for item_id in before_id_set.intersection(after_id_set)
        if not business_items_safely_refreshable(
            before_by_id[item_id], after_by_id[item_id]
        )
    }
    if modified_ids:
        failures.add("existing_business_modified")

    net_new_ids = after_id_set - before_id_set
    count_delta = len(after_items) - len(before_items)
    if count_delta < 0:
        failures.add("business_count_decreased")
    if len(after_items) != len(before_items) + len(net_new_ids):
        failures.add("business_count_conservation_failed")

    expected_counts = _business_counts(after_items)
    if before_business.get("business_total") != len(before_items):
        failures.add("baseline_business_total_mismatch")
    if before_meta.get("business_count") != len(before_items):
        failures.add("baseline_meta_business_count_mismatch")
    for field, expected in expected_counts.items():
        if after_business.get(field) != expected:
            failures.add(f"business_{field}_mismatch")
        if after_meta.get(field) != expected:
            failures.add(f"meta_{field}_mismatch")
    if after_meta.get("business_count") != len(after_items):
        failures.add("meta_business_count_mismatch")

    for field in BUSINESS_METADATA_MIRROR_FIELDS:
        if field in after_business or field in after_meta:
            if after_business.get(field) != after_meta.get(field):
                failures.add(f"business_meta_{field}_mismatch")

    if after_business.get("public_data_guard_status") != "passed":
        failures.add("public_data_guard_not_passed")
    guard_counts = _guard_business_counts(after_business.get("public_data_guard_message"))
    if guard_counts != (len(before_items), len(after_items)):
        failures.add("public_data_guard_count_mismatch")
    if after_business.get("previous_business_count") != len(before_items):
        failures.add("previous_business_count_mismatch")
    if after_business.get("merged_business_count") != len(after_items):
        failures.add("merged_business_count_mismatch")

    credential_urls = _count_credential_bearing_urls([after_business, after_meta])
    forbidden_fields = _count_forbidden_public_keys([after_business, after_meta])
    if credential_urls:
        failures.add("credential_bearing_url_detected")
    if forbidden_fields:
        failures.add("raw_or_secret_field_detected")

    new_d2b_items = [
        after_by_id[item_id]
        for item_id in net_new_ids
        if clean_text(after_by_id[item_id].get("source")).casefold() == "d2b"
    ]
    if new_d2b_items:
        if after_business.get("d2b_status") != "success":
            failures.add("d2b_current_status_inconsistent")
        if after_business.get("d2b_unified_status") != "success":
            failures.add("d2b_unified_status_inconsistent")
        if after_business.get("d2b_gw_migration_required") is not False:
            failures.add("d2b_migration_status_inconsistent")
        d2b_count = sum(
            clean_text(item.get("source")).casefold() == "d2b" for item in after_items
        )
        if after_business.get("d2b_unified_public_count") != d2b_count:
            failures.add("d2b_unified_count_inconsistent")
        if any(clean_text(item.get("source_type")) == "procurement_plan" for item in new_d2b_items):
            source_status = after_business.get("procurement_plan_source_status") or {}
            if not isinstance(source_status, dict) or source_status.get("D2B") != "success":
                failures.add("d2b_procurement_source_status_inconsistent")

    return _controlled_publication_result(
        failures,
        normalized_paths,
        before_items,
        after_items,
        removed_count=len(removed_ids),
        modified_count=len(modified_ids),
        net_new_count=len(net_new_ids),
        public_id_collision_count=duplicate_id_count,
        duplicate_identity_count=duplicate_identity_count,
        credential_url_count=credential_urls,
        forbidden_field_count=forbidden_fields,
        status="CONTROLLED_PUBLICATION_SAFE" if not failures else "CONTROLLED_PUBLICATION_BLOCKED",
    )


def validate_controlled_samsung_technology_publication(
    before_payload: dict[str, Any],
    after_payload: dict[str, Any],
    changed_paths: list[str] | set[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Validate the accepted Samsung technology delta from payload semantics."""

    paths = sorted({_normalized_repo_path(path) for path in changed_paths if path})
    failures: set[str] = set()
    counts = {
        "baseline": 0,
        "candidate": 0,
        "existing_preserved": 0,
        "enriched_existing": 0,
        "status_updated_existing": 0,
        "existing_modified": 0,
        "net_new": 0,
        "adjacent_published": 0,
        "removed": 0,
        "other_company_modified": 0,
        "identity_collisions": 0,
        "duplicate_identities": 0,
        "before_incomplete": 0,
        "after_incomplete": 0,
        "resolved_incomplete": 0,
    }
    security = {"credential_urls": 0, "forbidden_fields": 0, "passed": True}

    if CONTROLLED_PUBLIC_COMPANIES_PATH not in paths:
        return {
            "schema_version": "controlled-company-technology-publication-v1",
            "passed": True,
            "status": "NO_CONTROLLED_COMPANY_TECHNOLOGY_CHANGE",
            "reason_codes": [],
            "changed_paths": paths,
            "company_id": SAMSUNG_TECHNOLOGY_COMPANY_ID,
            "counts": counts,
            "security": security,
        }
    if set(paths) != {CONTROLLED_PUBLIC_COMPANIES_PATH}:
        failures.add("changed_file_scope_invalid")
    if not isinstance(before_payload, dict) or not isinstance(after_payload, dict):
        failures.add("company_payload_invalid")
        return _samsung_technology_publication_result(failures, paths, counts, security)

    before_companies = before_payload.get("companies")
    after_companies = after_payload.get("companies")
    if not isinstance(before_companies, list) or not isinstance(after_companies, list):
        failures.add("company_list_invalid")
        return _samsung_technology_publication_result(failures, paths, counts, security)
    if {key: value for key, value in before_payload.items() if key != "companies"} != {
        key: value for key, value in after_payload.items() if key != "companies"
    }:
        failures.add("company_root_metadata_modified")

    before_ids = [clean_text(company.get("company_id")) for company in before_companies if isinstance(company, dict)]
    after_ids = [clean_text(company.get("company_id")) for company in after_companies if isinstance(company, dict)]
    if before_ids != after_ids or len(before_ids) != len(before_companies) or len(after_ids) != len(after_companies):
        failures.add("company_universe_modified")
    before_by_id = {clean_text(company.get("company_id")): company for company in before_companies if isinstance(company, dict)}
    after_by_id = {clean_text(company.get("company_id")): company for company in after_companies if isinstance(company, dict)}
    before_company = before_by_id.get(SAMSUNG_TECHNOLOGY_COMPANY_ID)
    after_company = after_by_id.get(SAMSUNG_TECHNOLOGY_COMPANY_ID)
    if not isinstance(before_company, dict) or not isinstance(after_company, dict):
        failures.add("samsung_company_missing")
        return _samsung_technology_publication_result(failures, paths, counts, security)

    other_modified = sum(
        before_by_id.get(company_id) != after_by_id.get(company_id)
        for company_id in set(before_by_id) | set(after_by_id)
        if company_id != SAMSUNG_TECHNOLOGY_COMPANY_ID
    )
    counts["other_company_modified"] = other_modified
    if other_modified:
        failures.add("other_company_modified")
    before_nontechnology = {
        key: value for key, value in before_company.items() if key not in {"technology", "sources"}
    }
    after_nontechnology = {
        key: value for key, value in after_company.items() if key not in {"technology", "sources"}
    }
    if before_nontechnology != after_nontechnology:
        failures.add("samsung_nontechnology_payload_modified")

    before_items = _company_technology_items(before_company)
    after_items = _company_technology_items(after_company)
    counts["baseline"] = len(before_items)
    counts["candidate"] = len(after_items)
    before_item_counts = _technology_id_counts(before_items)
    after_item_counts = _technology_id_counts(after_items)
    if "" in before_item_counts or "" in after_item_counts:
        failures.add("technology_id_missing")
    if any(count > 1 for count in after_item_counts.values()):
        failures.add("technology_id_collision")
        counts["identity_collisions"] = sum(max(0, count - 1) for count in after_item_counts.values())
    before_item_by_id = {clean_text(item.get("technology_id")): item for item in before_items}
    after_item_by_id = {clean_text(item.get("technology_id")): item for item in after_items}
    before_id_set = set(before_item_by_id)
    after_id_set = set(after_item_by_id)
    removed_ids = before_id_set - after_id_set
    new_ids = after_id_set - before_id_set
    counts["existing_preserved"] = len(before_id_set & after_id_set)
    counts["removed"] = len(removed_ids)
    counts["net_new"] = len(new_ids)
    if removed_ids:
        failures.add("existing_technology_removed")
    if before_id_set != SAMSUNG_TECHNOLOGY_BASELINE_IDS:
        failures.add("baseline_identity_drift")
    if new_ids != SAMSUNG_TECHNOLOGY_NEW_IDS:
        failures.add("new_technology_identity_mismatch")

    enriched_ids: set[str] = set()
    status_updated_ids: set[str] = set()
    for technology_id in sorted(before_id_set & after_id_set):
        before_item = before_item_by_id[technology_id]
        after_item = after_item_by_id[technology_id]
        changed_fields = {
            key
            for key in set(before_item) | set(after_item)
            if before_item.get(key) != after_item.get(key)
        }
        for field in changed_fields:
            if field in SAMSUNG_TECHNOLOGY_ENRICHMENT_FIELDS:
                if before_item.get(field) not in {None, ""} or after_item.get(field) in {None, ""}:
                    failures.add("existing_nonempty_field_overwritten")
                else:
                    enriched_ids.add(technology_id)
            elif field == "status":
                expected = SAMSUNG_TECHNOLOGY_STATUS_TRANSITIONS.get(technology_id)
                if expected != (before_item.get(field), after_item.get(field)):
                    failures.add("unapproved_status_transition")
                else:
                    status_updated_ids.add(technology_id)
            else:
                failures.add("unexpected_existing_technology_change")
    counts["enriched_existing"] = len(enriched_ids)
    counts["status_updated_existing"] = len(status_updated_ids)
    counts["existing_modified"] = len(enriched_ids | status_updated_ids)
    if len(enriched_ids) != 4:
        failures.add("enrichment_count_mismatch")
    if status_updated_ids != set(SAMSUNG_TECHNOLOGY_STATUS_TRANSITIONS):
        failures.add("status_update_mismatch")

    new_items = [after_item_by_id[item_id] for item_id in sorted(new_ids)]
    for item in new_items:
        if not SAMSUNG_NEW_TECHNOLOGY_REQUIRED_FIELDS.issubset(item):
            failures.add("new_technology_schema_incomplete")
        if item.get("record_type") != "patent" or item.get("status") != "registered":
            failures.add("new_technology_contract_invalid")
        if item.get("source_ids") != [SAMSUNG_TECHNOLOGY_SOURCE_ID]:
            failures.add("new_technology_source_mismatch")

    identity_counts: dict[tuple[str, str], int] = {}
    for item in after_items:
        identity = _technology_identity(item)
        identity_counts[identity] = identity_counts.get(identity, 0) + 1
    duplicate_identities = sum(max(0, count - 1) for count in identity_counts.values())
    counts["duplicate_identities"] = duplicate_identities
    if duplicate_identities:
        failures.add("duplicate_technology_identity")

    before_sources = before_company.get("sources")
    after_sources = after_company.get("sources")
    if not isinstance(before_sources, list) or not isinstance(after_sources, list):
        failures.add("source_registry_invalid")
        before_sources = before_sources if isinstance(before_sources, list) else []
        after_sources = after_sources if isinstance(after_sources, list) else []
    if after_sources[: len(before_sources)] != before_sources:
        failures.add("existing_source_registry_modified")
    added_sources = after_sources[len(before_sources) :]
    if len(added_sources) != 1 or clean_text(added_sources[0].get("source_id")) != SAMSUNG_TECHNOLOGY_SOURCE_ID:
        failures.add("source_registry_addition_mismatch")
    source_ids = [clean_text(source.get("source_id")) for source in after_sources if isinstance(source, dict)]
    if "" in source_ids or len(source_ids) != len(set(source_ids)):
        failures.add("source_registry_identity_invalid")
    known_sources = set(source_ids)
    if any(
        not isinstance(item.get("source_ids"), list)
        or not item.get("source_ids")
        or any(clean_text(source_id) not in known_sources for source_id in item.get("source_ids", []))
        for item in after_items
    ):
        failures.add("technology_source_reference_invalid")

    counts["before_incomplete"] = sum(_technology_information_incomplete(item) for item in before_items)
    counts["after_incomplete"] = sum(_technology_information_incomplete(item) for item in after_items)
    counts["resolved_incomplete"] = counts["before_incomplete"] - counts["after_incomplete"]
    if (counts["baseline"], counts["candidate"], counts["before_incomplete"], counts["after_incomplete"]) != (7, 13, 7, 3):
        failures.add("publication_metric_mismatch")

    security["credential_urls"] = _count_credential_bearing_urls({"technology": after_company.get("technology"), "sources": added_sources})
    security["forbidden_fields"] = _count_forbidden_public_keys({"technology": after_company.get("technology"), "sources": added_sources})
    security["passed"] = security["credential_urls"] == 0 and security["forbidden_fields"] == 0
    if not security["passed"]:
        failures.add("sensitive_public_payload_detected")

    return _samsung_technology_publication_result(failures, paths, counts, security)


def _company_technology_items(company: dict[str, Any]) -> list[dict[str, Any]]:
    technology = company.get("technology")
    if not isinstance(technology, dict):
        return []
    return [
        item
        for rows in technology.values()
        if isinstance(rows, list)
        for item in rows
        if isinstance(item, dict)
    ]


def _technology_id_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        technology_id = clean_text(item.get("technology_id"))
        counts[technology_id] = counts.get(technology_id, 0) + 1
    return counts


def _technology_identity(item: dict[str, Any]) -> tuple[str, str]:
    for field in ("application_number", "registration_number", "patent_number"):
        value = re.sub(r"[^0-9A-Za-z]", "", clean_text(item.get(field))).casefold()
        if value:
            return field, value
    return "technology_id", clean_text(item.get("technology_id"))


def _technology_information_incomplete(item: dict[str, Any]) -> int:
    return int(not item.get("application_date") or not item.get("registration_date"))


def _samsung_technology_publication_result(
    failures: set[str],
    paths: list[str],
    counts: dict[str, int],
    security: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "controlled-company-technology-publication-v1",
        "passed": not failures,
        "status": "SAMSUNG_TECH_CONTROLLED_PUBLICATION_SAFE" if not failures else "SAMSUNG_TECH_CONTROLLED_PUBLICATION_BLOCKED",
        "reason_codes": sorted(failures),
        "changed_paths": paths,
        "company_id": SAMSUNG_TECHNOLOGY_COMPANY_ID,
        "counts": counts,
        "security": security,
    }

def _normalized_repo_path(path: Any) -> str:
    return str(path).strip().replace("\\", "/").lstrip("./")


def _strict_payload_items(payload: Any) -> tuple[list[dict[str, Any]], bool]:
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return [], False
    raw_items = payload["items"]
    return [item for item in raw_items if isinstance(item, dict)], all(
        isinstance(item, dict) for item in raw_items
    )


def _item_id_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        item_id = clean_text(item.get("id"))
        counts[item_id] = counts.get(item_id, 0) + 1
    return counts


def _identity_counts(items: list[dict[str, Any]]) -> dict[tuple[str, ...], int]:
    counts: dict[tuple[str, ...], int] = {}
    for item in items:
        identity = business_identity(item)
        counts[identity] = counts.get(identity, 0) + 1
    return counts


def _business_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "business_total": len(items),
        "business_active": sum(item.get("opportunity_status") == "active" for item in items),
        "business_closed": sum(item.get("opportunity_status") == "closed" for item in items),
        "business_unknown": sum(item.get("opportunity_status") == "unknown" for item in items),
        "bid_total": sum(item.get("source_type") == "bid" for item in items),
        "procurement_plan_count": sum(
            item.get("source_type") == "procurement_plan" for item in items
        ),
        "procurement_plan_total": sum(
            item.get("source_type") == "procurement_plan" for item in items
        ),
        "public_agency_contest_total": sum(
            item.get("source_type") == "public_agency_contest" for item in items
        ),
    }


def _guard_business_counts(value: Any) -> tuple[int, int] | None:
    match = re.search(r"\bbusiness\s+(\d+)\s*->\s*(\d+)\b", clean_text(value))
    return (int(match.group(1)), int(match.group(2))) if match else None


def _credential_bearing_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    return any(key.casefold() in SENSITIVE_PUBLIC_QUERY_KEYS for key, _ in parse_qsl(parsed.query))


def _count_credential_bearing_urls(value: Any) -> int:
    if isinstance(value, dict):
        return sum(_count_credential_bearing_urls(child) for child in value.values())
    if isinstance(value, list):
        return sum(_count_credential_bearing_urls(child) for child in value)
    return int(_credential_bearing_url(value))


def _count_forbidden_public_keys(value: Any) -> int:
    if isinstance(value, dict):
        own = sum(
            str(key).casefold().replace("-", "_") in FORBIDDEN_PUBLIC_PAYLOAD_KEYS
            for key in value
        )
        return own + sum(_count_forbidden_public_keys(child) for child in value.values())
    if isinstance(value, list):
        return sum(_count_forbidden_public_keys(child) for child in value)
    return 0


def _controlled_publication_result(
    failures: set[str],
    changed_paths: list[str],
    before_items: list[dict[str, Any]],
    after_items: list[dict[str, Any]],
    *,
    removed_count: int = 0,
    modified_count: int = 0,
    net_new_count: int = 0,
    public_id_collision_count: int = 0,
    duplicate_identity_count: int = 0,
    credential_url_count: int = 0,
    forbidden_field_count: int = 0,
    status: str,
) -> dict[str, Any]:
    return {
        "schema_version": CONTROLLED_PUBLICATION_SCHEMA_VERSION,
        "passed": not failures,
        "status": status,
        "reason_codes": sorted(failures),
        "changed_paths": changed_paths,
        "counts": {
            "baseline": len(before_items),
            "candidate": len(after_items),
            "net_new": net_new_count,
            "removed": removed_count,
            "modified": modified_count,
            "public_id_collisions": public_id_collision_count,
            "duplicate_identities": duplicate_identity_count,
        },
        "security": {
            "credential_urls": credential_url_count,
            "forbidden_fields": forbidden_field_count,
            "passed": credential_url_count == 0 and forbidden_field_count == 0,
        },
    }


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


def is_overseas_rss_public_item(item: dict[str, Any]) -> bool:
    return clean_text(item.get("source")) == OVERSEAS_RSS_SOURCE


def _numeric_id(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_google_news_url(value: Any) -> bool:
    text = clean_text(value)
    if not text:
        return False
    try:
        return (urlsplit(text).hostname or "").lower() == "news.google.com"
    except ValueError:
        return False


def _url_quality(value: Any) -> int:
    text = clean_text(value)
    if not text:
        return 0
    return 1 if _is_google_news_url(text) else 2


def _text_quality(value: Any) -> int:
    text = clean_text(value)
    if not text or text.lower() in {"rss", "google news", "unknown", "출처 미확인"}:
        return 0
    return len(text)


def _keyword_parts(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_parts = value
    else:
        raw_parts = re.split(r"[,;|]", clean_text(value))
    parts: list[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        text = clean_text(part)
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            parts.append(text)
    return parts


def _choose_stable_public_item(items: list[dict[str, Any]]) -> dict[str, Any]:
    def sort_key(pair: tuple[int, dict[str, Any]]) -> tuple[int, int, str]:
        index, item = pair
        numeric = _numeric_id(item.get("id"))
        return (0 if numeric is not None else 1, numeric if numeric is not None else index, clean_text(item.get("id")))

    return dict(sorted(enumerate(items), key=sort_key)[0][1])


def _merge_overseas_rss_group(items: list[dict[str, Any]], content_key: tuple[str, str]) -> dict[str, Any]:
    survivor = _choose_stable_public_item(items)
    for item in items:
        if _url_quality(item.get("original_url")) > _url_quality(survivor.get("original_url")):
            survivor["original_url"] = item.get("original_url")
        if _text_quality(item.get("media") or item.get("source_name")) > _text_quality(survivor.get("media") or survivor.get("source_name")):
            if _nonempty(item.get("media")):
                survivor["media"] = item.get("media")
            elif _nonempty(item.get("source_name")):
                survivor["source_name"] = item.get("source_name")
        if len(clean_text(item.get("summary"))) > len(clean_text(survivor.get("summary"))):
            survivor["summary"] = item.get("summary")
        try:
            item_score = float(item.get("relevance_score"))
        except (TypeError, ValueError):
            item_score = 0.0
        try:
            survivor_score = float(survivor.get("relevance_score"))
        except (TypeError, ValueError):
            survivor_score = 0.0
        if item_score > survivor_score:
            survivor["relevance_score"] = item.get("relevance_score")

    merged_keywords: list[str] = []
    seen_keywords: set[str] = set()
    for item in items:
        for keyword in _keyword_parts(item.get("keywords")):
            key = keyword.lower()
            if key not in seen_keywords:
                seen_keywords.add(key)
                merged_keywords.append(keyword)
    if merged_keywords:
        survivor["keywords"] = ", ".join(merged_keywords)
    if content_key[1]:
        survivor["published_at"] = content_key[1]
    survivor["source"] = OVERSEAS_RSS_SOURCE
    return survivor


def _merge_public_news_group(items: list[dict[str, Any]], content_key: tuple[str, str]) -> dict[str, Any]:
    survivor = _choose_stable_public_item(items)
    for item in items:
        if _url_quality(item.get("original_url")) > _url_quality(survivor.get("original_url")):
            survivor["original_url"] = item.get("original_url")
        if _url_quality(item.get("url")) > _url_quality(survivor.get("url")):
            survivor["url"] = item.get("url")
        if _text_quality(item.get("media") or item.get("source_name") or item.get("organization")) > _text_quality(
            survivor.get("media") or survivor.get("source_name") or survivor.get("organization")
        ):
            if _nonempty(item.get("media")):
                survivor["media"] = item.get("media")
            elif _nonempty(item.get("source_name")):
                survivor["source_name"] = item.get("source_name")
            elif _nonempty(item.get("organization")):
                survivor["organization"] = item.get("organization")
        if len(clean_text(item.get("summary"))) > len(clean_text(survivor.get("summary"))):
            survivor["summary"] = item.get("summary")

    merged_keywords: list[str] = []
    seen_keywords: set[str] = set()
    for item in items:
        for keyword in _keyword_parts(item.get("keywords")):
            key = keyword.lower()
            if key not in seen_keywords:
                seen_keywords.add(key)
                merged_keywords.append(keyword)
    if merged_keywords:
        survivor["keywords"] = ", ".join(merged_keywords)

    merged_reasons: list[str] = []
    seen_reasons: set[str] = set()
    for item in items:
        raw_reasons = item.get("relevance_reasons")
        reason_parts = raw_reasons if isinstance(raw_reasons, list) else re.split(r"[,;|]", clean_text(raw_reasons))
        for reason in reason_parts:
            text = clean_text(reason)
            key = text.lower()
            if text and key not in seen_reasons:
                seen_reasons.add(key)
                merged_reasons.append(text)
    if merged_reasons:
        survivor["relevance_reasons"] = merged_reasons

    if content_key[1]:
        survivor["published_at"] = content_key[1]
    return survivor


def dedupe_overseas_rss_public_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    ordered: list[tuple[str, dict[str, Any] | tuple[str, str]]] = []

    for item in items:
        copied = dict(item)
        if not is_overseas_rss_public_item(copied):
            ordered.append(("item", copied))
            continue
        content_key = overseas_news_content_key(copied.get("title"), copied.get("published_at"))
        if not all(content_key):
            ordered.append(("item", copied))
            continue
        if content_key not in groups:
            groups[content_key] = [copied]
            ordered.append(("group", content_key))
        else:
            groups[content_key].append(copied)

    result: list[dict[str, Any]] = []
    for kind, value in ordered:
        if kind == "group":
            result.append(_merge_overseas_rss_group(groups[value], value))  # type: ignore[index,arg-type]
        else:
            result.append(value)  # type: ignore[arg-type]
    return result


def dedupe_all_public_news_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    ordered: list[tuple[str, dict[str, Any] | tuple[str, str]]] = []

    for item in items:
        copied = dict(item)
        content_key = overseas_news_content_key(copied.get("title"), copied.get("published_at"))
        if not all(content_key):
            ordered.append(("item", copied))
            continue
        if content_key not in groups:
            groups[content_key] = [copied]
            ordered.append(("group", content_key))
        else:
            groups[content_key].append(copied)

    result: list[dict[str, Any]] = []
    for kind, value in ordered:
        if kind == "group":
            result.append(_merge_public_news_group(groups[value], value))  # type: ignore[index,arg-type]
        else:
            result.append(value)  # type: ignore[arg-type]
    return result


def is_publishable_news_item(item: dict[str, Any]) -> bool:
    return (
        clean_text(item.get("relevance_score_version")) == "unified-v2"
        and clean_text(item.get("relevance_level")) in PUBLISHABLE_RELEVANCE_LEVELS
    )


def filter_publishable_news_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in items if is_publishable_news_item(item)]


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


def merge_existing_business_record(
    existing: dict[str, Any], fresh: dict[str, Any]
) -> dict[str, Any]:
    """Preserve canonical facts while applying narrow, source-backed refreshes.

    Empty-field enrichment is intentionally not enabled here. It requires a
    separate, explicit field allowlist and verification contract.
    """

    merged = dict(existing)
    for field in BUSINESS_LIFECYCLE_DERIVED_FIELDS:
        if field in fresh:
            merged[field] = fresh[field]
    for field in BUSINESS_AUTHORITATIVE_REFRESH_FIELDS:
        if field in fresh and _nonempty(fresh[field]):
            merged[field] = fresh[field]

    verified = bool(
        fresh.get("exact_link_verified") or fresh.get("link_verified")
    )
    if verified:
        for field in BUSINESS_VERIFIED_EVIDENCE_REFRESH_FIELDS:
            if field in fresh and _nonempty(fresh[field]):
                merged[field] = fresh[field]
        for field in BUSINESS_EVIDENCE_VERIFICATION_FIELDS:
            if fresh.get(field):
                merged[field] = True
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
            if kind == "business":
                merged_by_key[key] = merge_existing_business_record(
                    merged_by_key[key], item
                )
            else:
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
    approved_news_policy_removals: int = 0,
) -> tuple[str, str]:
    business_limit = int(previous_business * (1 - BUSINESS_SHRINK_THRESHOLD))
    news_limit = int(previous_news * (1 - NEWS_SHRINK_THRESHOLD))
    effective_merged_news = merged_news + max(0, approved_news_policy_removals)
    problems = []
    if previous_business and merged_business < business_limit:
        problems.append(f"business {previous_business} -> {merged_business}")
    if previous_news and effective_merged_news < news_limit:
        problems.append(f"news {previous_news} -> {merged_news}, policy_removed={approved_news_policy_removals}")
    if problems and not allow_shrink:
        return "blocked", "Public data shrink detected. " + ", ".join(problems) + ". Refusing commit."
    if problems:
        return "override", "Public data shrink allowed by ALLOW_PUBLIC_DATA_SHRINK=true: " + ", ".join(problems)
    if merged_business < previous_business or merged_news < previous_news:
        if approved_news_policy_removals and effective_merged_news >= previous_news and merged_business >= previous_business:
            return "passed", (
                f"Cumulative merge protected public data with approved news policy removals: "
                f"business {previous_business} -> {merged_business}, news {previous_news} -> {merged_news}, "
                f"policy_removed={approved_news_policy_removals}."
            )
        return "warning", (
            f"Cumulative normalization reduced data within guard limits: business {previous_business} -> {merged_business}, "
            f"news {previous_news} -> {merged_news}, policy_removed={approved_news_policy_removals}."
        )
    return "passed", (
        f"Cumulative merge protected public data: business {previous_business} -> {merged_business}, "
        f"news {previous_news} -> {merged_news}."
    )
