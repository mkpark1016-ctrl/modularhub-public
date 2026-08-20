from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.integrations.business.public_projection import (
    build_public_projection,
    projection_blockers,
    select_net_new_projected_items,
)
from scripts.integrations.business.unified import load_canonical_records
from src.public_data_policy import merge_public_items


PUBLIC_PIPELINE_INTEGRATION_SCHEMA_VERSION = "public-business-pipeline-integration-v1"


class UnifiedPublicInputError(RuntimeError):
    pass


def integrate_optional_unified_business(
    existing_items: list[dict[str, Any]],
    *,
    unified_records_path: Path | None = None,
    unified_summary_path: Path | None = None,
    merge_time: datetime | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if unified_records_path is None and unified_summary_path is None:
        return deepcopy(existing_items), _disabled_report(len(existing_items))

    records_path, summary_path = validate_unified_input_paths(
        unified_records_path,
        unified_summary_path,
    )
    records = load_canonical_records(records_path)
    summary = _load_json_object(summary_path)
    if summary.get("records_output") != len(records):
        raise UnifiedPublicInputError(
            "UNIFIED_PUBLIC_INPUT_COUNT_MISMATCH: "
            f"summary={summary.get('records_output')!r} records={len(records)}"
        )

    projected, _, projection_report = build_public_projection(
        records,
        {"items": existing_items},
        unified_summary=summary,
    )
    blockers = projection_blockers(projection_report)
    if blockers:
        raise UnifiedPublicInputError(
            f"UNIFIED_PUBLIC_PROJECTION_BLOCKED: {','.join(sorted(blockers))}"
        )

    net_new_items = select_net_new_projected_items(projected, existing_items)
    merged_items = merge_public_items(
        existing_items,
        net_new_items,
        kind="business",
        now=merge_time or _summary_time(summary),
        removal_allowlist={},
    )
    removed = _removed_payload_count(existing_items, merged_items)
    if removed:
        raise UnifiedPublicInputError(f"UNIFIED_PUBLIC_DATA_PRESERVATION_FAILED: removed={removed}")
    if len(merged_items) != len(existing_items) + len(net_new_items):
        raise UnifiedPublicInputError(
            "UNIFIED_PUBLIC_COUNT_CONSERVATION_FAILED: "
            f"baseline={len(existing_items)} net_new={len(net_new_items)} candidate={len(merged_items)}"
        )

    report = {
        "schema_version": PUBLIC_PIPELINE_INTEGRATION_SCHEMA_VERSION,
        "integration_enabled": True,
        "input_path": records_path.as_posix(),
        "summary_path": summary_path.as_posix(),
        "unified_input_count": projection_report["unified_input_count"],
        "publishable_count": projection_report["publishable_count"],
        "filtered_count": projection_report["filtered_count"],
        "filtered_reasons": projection_report["filtered_reasons"],
        "baseline_public_count": len(existing_items),
        "existing_matches": (
            projection_report["exact_existing_matches"] + projection_report["lineage_matches"]
        ),
        "exact_existing_matches": projection_report["exact_existing_matches"],
        "lineage_matches": projection_report["lineage_matches"],
        "net_new_count": len(net_new_items),
        "candidate_public_count": len(merged_items),
        "identity_collision_count": projection_report["public_id_collision_count"],
        "existing_removed_count": removed,
        "default_pipeline_unchanged": True,
        "frontend_contract_passed": not projection_report["frontend_contract_issues"],
        "security_passed": projection_report["security"]["passed"],
        "security": projection_report["security"],
        "sources": projection_report["sources"],
        "record_types": projection_report["record_types"],
        "merge_contract": "src.public_data_policy.merge_public_items",
    }
    return merged_items, report


def validate_unified_input_paths(
    records_path: Path | None,
    summary_path: Path | None,
) -> tuple[Path, Path]:
    if records_path is None or summary_path is None:
        raise UnifiedPublicInputError(
            "UNIFIED_PUBLIC_INPUT_INCOMPLETE: records and summary paths are both required"
        )
    for path in (records_path, summary_path):
        if not path.is_file():
            raise UnifiedPublicInputError(f"UNIFIED_PUBLIC_INPUT_NOT_FOUND: {path.as_posix()}")
    return records_path, summary_path


def write_public_pipeline_integration_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _disabled_report(existing_count: int) -> dict[str, Any]:
    return {
        "schema_version": PUBLIC_PIPELINE_INTEGRATION_SCHEMA_VERSION,
        "integration_enabled": False,
        "baseline_public_count": existing_count,
        "candidate_public_count": existing_count,
        "net_new_count": 0,
        "existing_removed_count": 0,
        "default_pipeline_unchanged": True,
    }


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UnifiedPublicInputError(f"UNIFIED_PUBLIC_INPUT_INVALID: {path.as_posix()}") from exc
    if not isinstance(payload, dict):
        raise UnifiedPublicInputError(f"UNIFIED_PUBLIC_INPUT_INVALID: {path.as_posix()}")
    return payload


def _summary_time(summary: dict[str, Any]) -> datetime:
    value = str(summary.get("generated_at") or "").replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _removed_payload_count(
    existing_items: list[dict[str, Any]], merged_items: list[dict[str, Any]]
) -> int:
    stable = lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    existing_payloads = Counter(stable(item) for item in existing_items)
    merged_payloads = Counter(stable(item) for item in merged_items)
    return sum(max(0, count - merged_payloads[payload]) for payload, count in existing_payloads.items())
