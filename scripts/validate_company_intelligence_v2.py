#!/usr/bin/env python3
"""Validate Company Intelligence V2 truth, visibility, and regression contracts."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from migrate_company_intelligence_v2 import (
    ALLOWED_PROJECT_CREDIT_STATUSES,
    DEFAULT_COMPANIES,
    DEFAULT_OUTPUT,
    PROTECTED_PUBLIC_FILES,
    ROOT,
    UNKNOWN_PROJECT_ROLES,
    protected_hash,
    read_json,
    sha256_file,
)
from src.env_config import load_project_dotenv

DEFAULT_PUBLIC_V2 = ROOT / "frontend" / "public" / "data" / "companies" / "company_intelligence_v2.json"
DEFAULT_SCHEMA = ROOT / "schemas" / "companies" / "company_intelligence_v2.schema.json"
FRONTEND_APP = ROOT / "frontend" / "src" / "App.jsx"
PUBLIC_ROOT = ROOT / "frontend" / "public"

RAW_UI_PATTERNS = {
    "event_status_direct": r"\{\s*(?:item|event)\.event_status\s*\}",
    "verification_status_direct": r"\{\s*(?:item|event)\.verification_status\s*\}",
    "signal_type_direct": r"\{\s*item\.signal_type\s*\}",
    "technology_status_direct": r"\{\s*item\.status\s*\}",
    "record_type_direct": r"\{\s*item\.record_type\s*\}",
    "ownership_type_direct": r"\{\s*item\.ownership_type\s*\}",
    "operation_status_direct": r"\{\s*item\.operation_status\s*\}",
}


def duplicate_values(records: list[dict[str, Any]], key: str) -> list[str]:
    counts = Counter(record.get(key) for record in records if record.get(key))
    return sorted(value for value, count in counts.items() if count > 1)


def add_error(errors: list[dict[str, Any]], code: str, message: str, path: str = "", severity: str = "error") -> None:
    errors.append({"code": code, "path": path, "message": message, "severity": severity})


def validate_schema(payload: dict[str, Any], schema_path: Path, errors: list[dict[str, Any]]) -> None:
    try:
        import jsonschema
    except ImportError:
        required = {"schema_version", "generated_at", "companies", "facts", "events", "evidence", "corrections", "materialized_summaries", "audit_metadata"}
        for field in sorted(required - set(payload)):
            add_error(errors, "schema_required_field_missing", field, "root")
        if payload.get("schema_version") != "2.0.0":
            add_error(errors, "schema_version_invalid", str(payload.get("schema_version")), "schema_version")
        return
    schema = read_json(schema_path)
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    for issue in sorted(validator.iter_errors(payload), key=lambda item: list(item.path)):
        add_error(errors, "schema_error", issue.message, "/".join(map(str, issue.path)))


def scan_secret_exposure(paths: list[Path]) -> int:
    secret_values = [
        value for name in ["OPENDART_API_KEY", "NAVER_CLIENT_SECRET", "DATA_GO_KR_SERVICE_KEY"]
        if len(value := os.getenv(name, "")) >= 16
    ]
    literal_pattern = re.compile(r"(?:OPENDART_API_KEY|NAVER_CLIENT_SECRET|DATA_GO_KR_SERVICE_KEY)\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{16,}")
    hits = 0
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if literal_pattern.search(text):
            hits += 1
        hits += sum(1 for value in secret_values if value and value in text)
    return hits


def raw_ui_exposures() -> list[dict[str, Any]]:
    text = FRONTEND_APP.read_text(encoding="utf-8")
    rows = []
    for code, pattern in RAW_UI_PATTERNS.items():
        for match in re.finditer(pattern, text):
            rows.append({"code": code, "offset": match.start(), "match": match.group(0)})
    return rows


def validate_v2(
    payload_path: Path = DEFAULT_OUTPUT,
    public_path: Path = DEFAULT_PUBLIC_V2,
    companies_path: Path = DEFAULT_COMPANIES,
    schema_path: Path = DEFAULT_SCHEMA,
) -> dict[str, Any]:
    load_project_dotenv()
    payload = read_json(payload_path)
    public = read_json(public_path)
    legacy = read_json(companies_path)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    validate_schema(payload, schema_path, errors)

    for collection, key in [("companies", "company_id"), ("facts", "fact_id"), ("events", "event_id"), ("evidence", "source_id"), ("corrections", "correction_id")]:
        for duplicate in duplicate_values(payload.get(collection, []), key):
            add_error(errors, f"duplicate_{key}", duplicate, collection)

    companies = {company["company_id"]: company for company in payload.get("companies", [])}
    evidence = {item["source_id"]: item for item in payload.get("evidence", [])}
    events = payload.get("events", [])
    summaries = {item["company_id"]: item for item in payload.get("materialized_summaries", [])}

    for fact in payload.get("facts", []):
        if fact.get("company_id") not in companies:
            add_error(errors, "orphan_fact_company", fact.get("fact_id", ""), "facts")
        if isinstance(fact.get("value"), (int, float)) and not isinstance(fact.get("value"), bool) and not fact.get("source_ids"):
            add_error(errors, "numeric_fact_without_source", fact["fact_id"], "facts")
        if fact.get("verification_status") == "unavailable" and fact.get("value") == 0:
            add_error(errors, "unknown_value_rendered_as_zero", fact["fact_id"], "facts")
        for source_id in fact.get("source_ids", []):
            if source_id not in evidence:
                add_error(errors, "missing_fact_evidence", source_id, fact["fact_id"])

    event_keys = Counter()
    for event in events:
        if event.get("company_id") not in companies:
            add_error(errors, "orphan_event_company", event.get("event_id", ""), "events")
        if event.get("event_type") in {"mou", "partnership"} and event.get("project_credit"):
            add_error(errors, "non_project_event_has_credit", event["event_id"], "events")
        if event.get("event_status") in {"mou_signed", "partnership_discussion", "r_and_d", "exhibition", "not_signed", "unconfirmed"} and event.get("project_credit"):
            add_error(errors, "ineligible_status_has_credit", event["event_id"], "events")
        if event.get("project_credit"):
            if event.get("event_type") != "project":
                add_error(errors, "project_credit_wrong_type", event["event_id"], "events")
            if event.get("event_status") not in ALLOWED_PROJECT_CREDIT_STATUSES:
                add_error(errors, "project_credit_wrong_status", event["event_id"], "events")
            if event.get("project_role") in UNKNOWN_PROJECT_ROLES:
                add_error(errors, "project_credit_missing_role", event["event_id"], "events")
            tiers = {evidence.get(source_id, {}).get("source_tier") for source_id in event.get("source_ids", [])}
            if not tiers.intersection({"A", "B"}):
                add_error(errors, "project_credit_missing_official_evidence", event["event_id"], "events")
        for source_id in event.get("source_ids", []):
            if source_id not in evidence:
                add_error(errors, "missing_event_evidence", source_id, event["event_id"])
        key = (event.get("company_id"), re.sub(r"\W+", "", str(event.get("title", "")).lower()), event.get("client"), event.get("location"))
        event_keys[key] += 1
    for key, count in event_keys.items():
        if count > 1:
            add_error(errors, "duplicate_event_candidate", f"{key} x{count}", "events")

    for company_id, summary in summaries.items():
        own_events = [event for event in events if event.get("company_id") == company_id]
        expected_verified = sum(1 for event in own_events if event.get("event_type") == "project" and event.get("project_credit"))
        expected_candidates = sum(1 for event in own_events if event.get("event_type") == "project" and not event.get("project_credit"))
        if summary.get("event_counts", {}).get("verified_projects") != expected_verified:
            add_error(errors, "verified_project_count_mismatch", company_id, "materialized_summaries")
        if summary.get("event_counts", {}).get("project_candidates") != expected_candidates:
            add_error(errors, "project_candidate_count_mismatch", company_id, "materialized_summaries")
        article_count = sum(
            1 for item in evidence.values()
            if item.get("source_type") == "media_article" and any(event["event_id"] in item.get("supports", []) for event in own_events)
        )
        if summary.get("article_evidence_count") != article_count:
            add_error(errors, "article_evidence_count_mismatch", company_id, "materialized_summaries")
        if summary.get("overall_data_status") == "core_verified":
            statuses = summary.get("domain_statuses", {})
            if statuses.get("identity_status") not in {"official_verified", "cross_verified"} or statuses.get("financial_status") not in {"official_verified", "cross_verified"}:
                add_error(errors, "overall_domain_status_conflict", company_id, "materialized_summaries")

    public_records = sum((public.get(key, []) for key in ["companies", "facts", "events", "evidence", "corrections"]), [])
    internal_public_count = sum(1 for record in public_records if record.get("visibility") != "public")
    if internal_public_count:
        add_error(errors, "internal_data_in_public_export", str(internal_public_count), str(public_path))
    if public.get("audit_metadata", {}).get("visibility_filter") != "visibility=public":
        add_error(errors, "public_visibility_contract_missing", "visibility filter missing", str(public_path))

    protected_expected = payload.get("audit_metadata", {}).get("protected_company_hashes", {})
    for company in legacy.get("companies", []):
        expected = protected_expected.get(company["company_id"])
        if expected and protected_hash(company) != expected:
            add_error(errors, "legacy_protected_field_regression", company["company_id"], "companies.json")

    source_hashes = payload.get("audit_metadata", {}).get("source_hashes", {})
    for name, path in PROTECTED_PUBLIC_FILES.items():
        if source_hashes.get(name) != sha256_file(path):
            add_error(errors, "protected_public_json_changed", name, str(path))

    ui_exposures = raw_ui_exposures()
    for exposure in ui_exposures:
        add_error(errors, "raw_ui_code_exposure", exposure["code"], str(FRONTEND_APP))

    scan_roots = [
        ROOT / "config",
        ROOT / "docs",
        ROOT / "scripts",
        ROOT / "data" / "companies",
        ROOT / "frontend" / "src",
        ROOT / "frontend" / "scripts",
        ROOT / "frontend" / "public" / "data" / "companies",
        ROOT / "frontend" / "dist",
        ROOT / "artifacts" / "company-intelligence-v2-truth-layer",
    ]
    scan_paths = [path for scan_root in scan_roots if scan_root.exists() for path in scan_root.rglob("*") if path.is_file()]
    secret_hits = scan_secret_exposure(scan_paths)
    if secret_hits:
        add_error(errors, "secret_exposure", str(secret_hits), str(ROOT))

    result = {
        "status": "PASS" if not errors else "HOLD_FOR_FIX",
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "company_count": len(companies),
            "fact_count": len(payload.get("facts", [])),
            "event_count": len(events),
            "evidence_count": len(evidence),
            "verified_project_count": sum(1 for event in events if event.get("project_credit")),
            "project_candidate_count": sum(1 for event in events if event.get("event_type") == "project" and not event.get("project_credit")),
            "partnership_mou_count": sum(1 for event in events if event.get("event_type") in {"partnership", "mou"}),
            "r_and_d_exhibition_count": sum(1 for event in events if event.get("event_type") in {"r_and_d", "exhibition"}),
            "raw_ui_code_exposure_count": len(ui_exposures),
            "internal_public_export_count": internal_public_count,
            "secret_exposure_count": secret_hits,
        },
        "raw_ui_exposures": ui_exposures,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--public", type=Path, default=DEFAULT_PUBLIC_V2)
    parser.add_argument("--companies", type=Path, default=DEFAULT_COMPANIES)
    args = parser.parse_args()
    result = validate_v2(args.input, args.public, args.companies)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
