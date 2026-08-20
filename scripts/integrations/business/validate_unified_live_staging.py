from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

from scripts.integrations.business.d2b import is_d2b_acceptance_failure
from scripts.integrations.business.unified import SOURCE_ROLES, UNIFIED_SCHEMA_VERSION


SENSITIVE_QUERY_KEYS = {
    "access_token",
    "apikey",
    "api_key",
    "authorization",
    "client_secret",
    "servicekey",
    "service_key",
    "token",
}
LH_ACCEPTED_HEALTH = {"healthy", "success_with_fallback"}


class UnifiedLiveAcceptanceError(RuntimeError):
    def __init__(self, category: str, message: str) -> None:
        self.category = category
        super().__init__(message)


def validate_source_acceptance(
    lh_summary: dict[str, Any],
    lh_records: list[dict[str, Any]],
    d2b_summary: dict[str, Any],
    d2b_records: list[dict[str, Any]],
) -> dict[str, Any]:
    lh_health = lh_summary.get("overall_health")
    if lh_summary.get("request_attempted") is not True or lh_health not in LH_ACCEPTED_HEALTH:
        raise UnifiedLiveAcceptanceError("lh_source", f"LH source acceptance failed: overall_health={lh_health}")
    if not isinstance(lh_records, list):
        raise UnifiedLiveAcceptanceError("lh_source", "LH records artifact must be an array")

    d2b_health = d2b_summary.get("overall_health")
    d2b_normalized = _as_nonnegative_int(d2b_summary.get("records_normalized"))
    if (
        d2b_summary.get("request_attempted") is not True
        or is_d2b_acceptance_failure(d2b_summary)
        or d2b_health != "healthy"
        or d2b_normalized <= 0
        or not isinstance(d2b_records, list)
        or not d2b_records
    ):
        raise UnifiedLiveAcceptanceError(
            "d2b_source",
            f"D2B source acceptance failed: overall_health={d2b_health}, records_normalized={d2b_normalized}",
        )

    return {
        "lh_overall_health": lh_health,
        "lh_records": len(lh_records),
        "lh_fallback_used": bool(lh_summary.get("fallback_used")),
        "d2b_overall_health": d2b_health,
        "d2b_records_normalized": d2b_normalized,
        "d2b_records": len(d2b_records),
    }


def validate_unified_acceptance(
    lh_summary: dict[str, Any],
    lh_records: list[dict[str, Any]],
    d2b_summary: dict[str, Any],
    d2b_records: list[dict[str, Any]],
    unified_summary: dict[str, Any],
    unified_records: list[dict[str, Any]],
) -> dict[str, Any]:
    source_result = validate_source_acceptance(lh_summary, lh_records, d2b_summary, d2b_records)

    if unified_summary.get("schema_version") != UNIFIED_SCHEMA_VERSION:
        raise UnifiedLiveAcceptanceError("unified_integration", "Unified schema version is invalid")
    if not isinstance(unified_records, list):
        raise UnifiedLiveAcceptanceError("unified_integration", "Unified records artifact must be an array")

    records_input = _as_nonnegative_int(unified_summary.get("records_input"))
    records_output = _as_nonnegative_int(unified_summary.get("records_output"))
    if records_input != len(lh_records) + len(d2b_records):
        raise UnifiedLiveAcceptanceError("unified_integration", "Unified input count does not match source artifacts")
    if records_input <= 0 or records_output <= 0 or records_output != len(unified_records):
        raise UnifiedLiveAcceptanceError("unified_integration", "Unified output count is invalid")

    actual_source_counts = Counter(str(record.get("source") or "") for record in unified_records)
    expected_source_counts = {str(key): _as_nonnegative_int(value) for key, value in (unified_summary.get("source_counts") or {}).items()}
    if dict(sorted(actual_source_counts.items())) != dict(sorted(expected_source_counts.items())):
        raise UnifiedLiveAcceptanceError("unified_integration", "Unified source counts do not match records")
    unknown_sources = sorted(set(actual_source_counts) - set(SOURCE_ROLES))
    if unknown_sources:
        raise UnifiedLiveAcceptanceError("unified_integration", f"Unified feed contains unsupported sources: {', '.join(unknown_sources)}")
    if actual_source_counts.get("d2b", 0) <= 0:
        raise UnifiedLiveAcceptanceError("d2b_source", "Unified feed contains no D2B records")
    if actual_source_counts.get("lh", 0) + actual_source_counts.get("g2b", 0) <= 0:
        raise UnifiedLiveAcceptanceError("lh_source", "Unified feed contains no LH path records")

    _validate_source_roles(unified_summary, actual_source_counts)
    actual_type_counts = Counter(str(record.get("source_record_type") or "") for record in unified_records)
    expected_type_counts = {
        str(key): _as_nonnegative_int(value) for key, value in (unified_summary.get("record_type_counts") or {}).items()
    }
    if dict(sorted(actual_type_counts.items())) != dict(sorted(expected_type_counts.items())):
        raise UnifiedLiveAcceptanceError("unified_integration", "Unified record type counts do not match records")
    duplicate_identity_count, empty_external_id_count, empty_title_count = _identity_quality(unified_records)
    if duplicate_identity_count:
        raise UnifiedLiveAcceptanceError("unified_integration", "Unified feed contains duplicate source identities")
    if empty_external_id_count or empty_title_count:
        raise UnifiedLiveAcceptanceError("unified_integration", "Unified feed contains empty required identity fields")

    credential_url_count = sum(_has_sensitive_query(record.get("source_url")) for record in unified_records)
    security = unified_summary.get("security") or {}
    if (
        security.get("passed") is not True
        or _as_nonnegative_int(security.get("credential_urls_detected")) != 0
        or _as_nonnegative_int(security.get("raw_payload_fields_detected")) != 0
        or credential_url_count != 0
    ):
        raise UnifiedLiveAcceptanceError("security", "Unified security acceptance failed")

    identity_conflict_count = _as_nonnegative_int(unified_summary.get("identity_conflict_count"))
    if identity_conflict_count:
        raise UnifiedLiveAcceptanceError(
            "identity_conflict",
            f"Unified feed requires identity conflict review: count={identity_conflict_count}",
        )

    return {
        **source_result,
        "schema_version": UNIFIED_SCHEMA_VERSION,
        "records_input": records_input,
        "records_output": records_output,
        "source_counts": dict(sorted(actual_source_counts.items())),
        "record_type_counts": dict(sorted(actual_type_counts.items())),
        "duplicate_identity_count": duplicate_identity_count,
        "empty_external_id_count": empty_external_id_count,
        "empty_title_count": empty_title_count,
        "credential_url_count": credential_url_count,
        "identity_conflict_count": identity_conflict_count,
        "security_passed": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Unified Business Feed live staging artifacts without network access.")
    parser.add_argument("--lh-summary", type=Path, required=True)
    parser.add_argument("--lh-records", type=Path, required=True)
    parser.add_argument("--d2b-summary", type=Path, required=True)
    parser.add_argument("--d2b-records", type=Path, required=True)
    parser.add_argument("--unified-summary", type=Path)
    parser.add_argument("--unified-records", type=Path)
    parser.add_argument("--source-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        lh_summary = _load_object(args.lh_summary)
        lh_records = _load_array(args.lh_records)
        d2b_summary = _load_object(args.d2b_summary)
        d2b_records = _load_array(args.d2b_records)
        if args.source_only:
            result = validate_source_acceptance(lh_summary, lh_records, d2b_summary, d2b_records)
        else:
            if not args.unified_summary or not args.unified_records:
                raise UnifiedLiveAcceptanceError("unified_integration", "Unified artifact paths are required")
            result = validate_unified_acceptance(
                lh_summary,
                lh_records,
                d2b_summary,
                d2b_records,
                _load_object(args.unified_summary),
                _load_array(args.unified_records),
            )
    except (OSError, json.JSONDecodeError, ValueError, UnifiedLiveAcceptanceError) as exc:
        category = exc.category if isinstance(exc, UnifiedLiveAcceptanceError) else "unified_integration"
        print(f"acceptance_status=failed category={category} reason={exc}")
        return 1

    print("acceptance_status=passed")
    for key, value in sorted(result.items()):
        print(f"{key}={json.dumps(value, ensure_ascii=False, sort_keys=True)}")
    return 0


def _validate_source_roles(summary: dict[str, Any], source_counts: Counter[str]) -> None:
    sources = summary.get("sources") or {}
    for source, count in source_counts.items():
        if count <= 0:
            continue
        expected_role = SOURCE_ROLES.get(source)
        if expected_role and (sources.get(source) or {}).get("source_role") != expected_role:
            raise UnifiedLiveAcceptanceError("unified_integration", f"Unexpected source role for {source}")


def _identity_quality(records: list[dict[str, Any]]) -> tuple[int, int, int]:
    identities = []
    empty_external_ids = 0
    empty_titles = 0
    for record in records:
        source = str(record.get("source") or "").strip()
        record_type = str(record.get("source_record_type") or "").strip()
        external_id = str(record.get("external_id") or "").strip()
        title = str(record.get("title") or "").strip()
        if not external_id:
            empty_external_ids += 1
        if not title:
            empty_titles += 1
        identities.append((source, record_type, external_id))
    duplicate_count = len(identities) - len(set(identities))
    return duplicate_count, empty_external_ids, empty_titles


def _has_sensitive_query(value: Any) -> bool:
    if not value:
        return False
    query = urlparse(str(value)).query
    return any(key.lower() in SENSITIVE_QUERY_KEYS for key, _ in parse_qsl(query, keep_blank_values=True))


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def _load_array(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        raise ValueError(f"{path.name} must contain an array of objects")
    return payload


def _as_nonnegative_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


if __name__ == "__main__":
    raise SystemExit(main())
