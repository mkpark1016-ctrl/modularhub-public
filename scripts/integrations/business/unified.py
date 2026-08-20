from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlparse

from scripts.integrations.business.base import NormalizedBusinessRecord


UNIFIED_SCHEMA_VERSION = "unified-business-feed-v1"
SOURCE_ROLES = {
    "lh": "primary",
    "g2b": "lh_fallback",
    "d2b": "independent",
}
CORE_CONFLICT_FIELDS = (
    "title",
    "issuing_organization",
    "estimated_amount",
    "deadline_at",
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
CANONICAL_FIELDS = {field.name for field in fields(NormalizedBusinessRecord)}


def source_identity(record: NormalizedBusinessRecord) -> tuple[str, str, str]:
    return (record.source, record.source_record_type, record.external_id)


def load_canonical_records(path: Path) -> list[NormalizedBusinessRecord]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"canonical record artifact must contain a JSON array: {path.name}")

    records = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"canonical record at index {index} must be an object")
        lowered_keys = {str(key).lower() for key in item}
        forbidden = sorted(lowered_keys & FORBIDDEN_RAW_KEYS)
        unknown = sorted(set(item) - CANONICAL_FIELDS)
        if forbidden:
            raise ValueError(f"raw or sensitive fields are not accepted at index {index}: {', '.join(forbidden)}")
        if unknown:
            raise ValueError(f"non-canonical fields are not accepted at index {index}: {', '.join(unknown)}")
        record = NormalizedBusinessRecord(**item)
        _assert_safe_source_url(record.source_url)
        records.append(record)
    return records


def build_unified_business_feed(
    records: Iterable[NormalizedBusinessRecord],
    *,
    generated_at: str | None = None,
) -> tuple[list[NormalizedBusinessRecord], dict[str, Any]]:
    input_records = list(records)
    for record in input_records:
        if not isinstance(record, NormalizedBusinessRecord):
            raise TypeError("unified feed accepts NormalizedBusinessRecord values only")
        _assert_safe_source_url(record.source_url)

    grouped: dict[tuple[str, str, str], list[NormalizedBusinessRecord]] = defaultdict(list)
    for record in input_records:
        grouped[source_identity(record)].append(record)

    unified_records: list[NormalizedBusinessRecord] = []
    exact_duplicates_removed = 0
    identity_conflict_records_removed = 0
    identity_conflicts = []

    for identity in sorted(grouped):
        candidates = grouped[identity]
        distinct_payloads = {_canonical_record_json(candidate) for candidate in candidates}
        winner = _select_identity_winner(candidates)
        unified_records.append(winner)

        if len(distinct_payloads) == 1:
            exact_duplicates_removed += len(candidates) - 1
            continue

        identity_conflict_records_removed += len(candidates) - 1
        differing_fields = _core_conflict_fields(candidates)
        identity_conflicts.append(
            {
                "identity": {
                    "source": identity[0],
                    "source_record_type": identity[1],
                    "external_id": identity[2],
                },
                "candidate_count": len(candidates),
                "distinct_payload_count": len(distinct_payloads),
                "differing_core_fields": differing_fields,
                "winner_rule": "source_updated_at,collected_at,completeness,canonical_payload",
            }
        )

    unified_records.sort(key=_record_sort_key)
    reconciliation_candidates = build_cross_source_candidates(unified_records)
    summary_generated_at = generated_at if generated_at is not None else _derived_generated_at(input_records)

    input_source_counts = Counter(record.source for record in input_records)
    output_source_counts = Counter(record.source for record in unified_records)
    output_type_counts = Counter(record.source_record_type for record in unified_records)
    sources = {}
    for source in sorted(input_source_counts | output_source_counts):
        source_output_records = [record for record in unified_records if record.source == source]
        sources[source] = {
            "source_role": SOURCE_ROLES.get(source, "unclassified"),
            "records_input": input_source_counts[source],
            "records_output": output_source_counts[source],
            "record_type_counts": dict(sorted(Counter(record.source_record_type for record in source_output_records).items())),
        }

    summary = {
        "schema_version": UNIFIED_SCHEMA_VERSION,
        "generated_at": summary_generated_at,
        "records_input": len(input_records),
        "records_output": len(unified_records),
        "source_counts": dict(sorted(output_source_counts.items())),
        "record_type_counts": dict(sorted(output_type_counts.items())),
        "exact_duplicates_removed": exact_duplicates_removed,
        "identity_conflict_records_removed": identity_conflict_records_removed,
        "identity_conflict_count": len(identity_conflicts),
        "identity_conflicts": identity_conflicts,
        "cross_source_candidate_count": len(reconciliation_candidates),
        "cross_source_candidates": reconciliation_candidates,
        "sources": sources,
        "security": {
            "normalized_records_only": True,
            "credential_urls_detected": 0,
            "raw_payload_fields_detected": 0,
            "passed": True,
        },
    }
    return unified_records, summary


def build_cross_source_candidates(records: Iterable[NormalizedBusinessRecord]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[NormalizedBusinessRecord]] = defaultdict(list)
    for record in records:
        normalized_title = _normalize_match_text(record.title)
        normalized_organization = _normalize_match_text(record.issuing_organization)
        if normalized_title and normalized_organization:
            grouped[(record.source_record_type, normalized_title, normalized_organization)].append(record)

    candidates = []
    for group in grouped.values():
        ordered = sorted(group, key=source_identity)
        for left_index, left in enumerate(ordered):
            for right in ordered[left_index + 1 :]:
                if left.source == right.source:
                    continue
                matching_dates = []
                if left.published_at and left.published_at == right.published_at:
                    matching_dates.append("published_at")
                if left.deadline_at and left.deadline_at == right.deadline_at:
                    matching_dates.append("deadline_at")
                if not matching_dates:
                    continue
                identities = sorted((source_identity(left), source_identity(right)))
                candidate_seed = json.dumps(identities, ensure_ascii=False, separators=(",", ":"))
                candidates.append(
                    {
                        "candidate_id": hashlib.sha256(candidate_seed.encode("utf-8")).hexdigest()[:16],
                        "source_record_type": left.source_record_type,
                        "match_basis": ["normalized_title", "normalized_organization", *matching_dates],
                        "records": [
                            {
                                "source": identity[0],
                                "source_record_type": identity[1],
                                "external_id": identity[2],
                            }
                            for identity in identities
                        ],
                    }
                )
    return sorted(candidates, key=lambda candidate: candidate["candidate_id"])


def write_unified_staging_outputs(
    records: list[NormalizedBusinessRecord],
    summary: dict[str, Any],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "unified_business_records.json").write_text(
        json.dumps([record.as_dict() for record in records], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "unified_business_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _assert_safe_source_url(source_url: str | None) -> None:
    if not source_url:
        return
    parsed = urlparse(source_url)
    sensitive_keys = sorted(
        key for key, _ in parse_qsl(parsed.query, keep_blank_values=True) if key.lower() in SENSITIVE_QUERY_KEYS
    )
    if sensitive_keys:
        raise ValueError(f"credential-bearing source_url is not allowed; sensitive query keys: {', '.join(sensitive_keys)}")


def _select_identity_winner(records: list[NormalizedBusinessRecord]) -> NormalizedBusinessRecord:
    return max(
        records,
        key=lambda record: (
            _timestamp_rank(record.source_updated_at),
            _timestamp_rank(record.collected_at),
            _completeness(record),
            _canonical_record_json(record),
        ),
    )


def _core_conflict_fields(records: list[NormalizedBusinessRecord]) -> list[str]:
    conflicting = []
    for field_name in CORE_CONFLICT_FIELDS:
        values = {_stable_value(getattr(record, field_name)) for record in records if getattr(record, field_name) is not None}
        if len(values) > 1:
            conflicting.append(field_name)
    return conflicting


def _timestamp_rank(value: str | None) -> tuple[int, float, str]:
    if not value:
        return (0, 0.0, "")
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (1, parsed.timestamp(), value)
    except ValueError:
        return (0, 0.0, value)


def _completeness(record: NormalizedBusinessRecord) -> int:
    return sum(value not in (None, "") for value in record.as_dict().values())


def _record_sort_key(record: NormalizedBusinessRecord) -> tuple[str, str, str, str, str]:
    primary_date = record.published_at or record.deadline_at or "9999-12-31"
    secondary_date = record.deadline_at or record.published_at or "9999-12-31"
    return (primary_date, secondary_date, record.source, record.source_record_type, record.external_id)


def _derived_generated_at(records: list[NormalizedBusinessRecord]) -> str | None:
    timestamps = [value for record in records for value in (record.collected_at, record.source_updated_at) if value]
    if not timestamps:
        return None
    return max(timestamps, key=_timestamp_rank)


def _normalize_match_text(value: str | None) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", (value or "").casefold())


def _canonical_record_json(record: NormalizedBusinessRecord) -> str:
    return json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _stable_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
