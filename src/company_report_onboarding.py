"""Guarded onboarding pipeline for curated company audit-report datasets."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from scripts.build_company_report_insights import build_view_model, stable_json
from scripts.validate_company_audit_financials import money_paths, validate

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SCHEMA_PATH = ROOT / "schemas" / "company_reports" / "company_report_onboarding_manifest_v1.schema.json"
PUBLIC_VIEW_MODEL_RELATIVE_PATH = Path("frontend/public/data/companies/company_report_insights.json")
DEFAULT_ARTIFACT_ROOT = Path("artifacts/company-report-onboarding")
MANIFEST_SCHEMA_VERSION = "company_report_onboarding_manifest_v1"
PROMOTION_MANIFEST_SCHEMA_VERSION = "company_report_onboarding_promotion_manifest_v1"
REPORT_SCHEMA_VERSION = "company_report_onboarding_validation_report_v1"

PASS = "PASS"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
BLOCKED = "BLOCKED"
EXIT_CODES = {PASS: 0, REVIEW_REQUIRED: 2, BLOCKED: 3, "CLI_ERROR": 4}

PROTECTED_PUBLIC_FILES = [
    "frontend/public/data/companies/companies.json",
    "frontend/public/data/companies/company_intelligence_v2.json",
    "frontend/public/data/news.json",
    "frontend/public/data/business.json",
    "frontend/public/data/meta.json",
]
PIPELINE_CONTRACT_VERSION = "company_report_onboarding_gate_v1"
DECISION_DERIVED_FIELDS = {"latest_snapshot", "trends", "financial_health", "evidence_health", "peer_benchmarks"}
SECRET_PATTERNS = [
    re.compile(r"(?i)(DART_API_KEY|NAVER_API_HUB_CLIENT_ID|NAVER_API_HUB_CLIENT_SECRET)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{12,}"),
    re.compile(r"(?i)Authorization\s*[:=]\s*['\"]?(Bearer|Basic)\s+[A-Za-z0-9_./+=-]{12,}"),
    re.compile(r"X-NCP-APIGW-API-KEY(?:-ID)?\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{12,}"),
]


@dataclass
class PipelineContext:
    repo_root: Path = ROOT
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT
    base_ref: str | None = "origin/main"

    def resolve_artifact_root(self, company_id: str) -> Path:
        root = self.artifact_root
        if not root.is_absolute():
            root = self.repo_root / root
        return root / company_id


def stable_json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(payload: dict[str, Any]) -> str:
    return sha256_bytes(stable_json_text(payload).encode("utf-8"))


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def maybe_file_sha256(path: Path) -> str | None:
    return file_sha256(path) if path.exists() else None


def git_show_bytes(repo_root: Path, ref: str, relative_path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{relative_path}"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def git_file_sha256(repo_root: Path, ref: str | None, relative_path: str) -> str | None:
    if not ref:
        return maybe_file_sha256(repo_root / relative_path)
    data = git_show_bytes(repo_root, ref, relative_path)
    return sha256_bytes(data) if data is not None else None


def protected_file_sha_map(context: PipelineContext, *, base: bool = False) -> dict[str, str | None]:
    ref = context.base_ref if base else None
    return {path: git_file_sha256(context.repo_root, ref, path) for path in PROTECTED_PUBLIC_FILES}


def protected_file_changes(context: PipelineContext) -> list[dict[str, Any]]:
    current = protected_file_sha_map(context)
    base = protected_file_sha_map(context, base=True)
    changes = []
    for path in PROTECTED_PUBLIC_FILES:
        if current.get(path) != base.get(path):
            changes.append({"path": path, "base_sha256": base.get(path), "current_sha256": current.get(path)})
    return changes


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stable_json_text(payload), encoding="utf-8")


def safe_relative_path(value: str) -> Path:
    if "\\" in value:
        raise ValueError(f"unsafe path uses backslash: {value}")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe path: {value}")
    return path


def resolve_safe(repo_root: Path, value: str) -> Path:
    relative = safe_relative_path(value)
    resolved = (repo_root / relative).resolve()
    if repo_root.resolve() not in (resolved, *resolved.parents):
        raise ValueError(f"path escapes repository root: {value}")
    return resolved


def expected_paths(company_id: str, years: list[int]) -> dict[str, str]:
    first, last = years[0], years[-1]
    return {
        "candidate_input_path": f"data/company_reports/{company_id}/onboarding/candidate_audit_financials.json",
        "staging_output_path": f"data/company_reports/{company_id}/staging/audit_financials_{first}_{last}.json",
        "public_output_path": f"data/company_reports/{company_id}/audit_financials_{first}_{last}.json",
    }


def validate_manifest_shape(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    schema = read_json(MANIFEST_SCHEMA_PATH)
    errors = []
    for error in Draft202012Validator(schema).iter_errors(manifest):
        path = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append({
            "code": "manifest_schema_error",
            "path": path,
            "message": error.message,
        })
    years = manifest.get("target_years")
    if isinstance(years, list) and years != sorted(years):
        errors.append({
            "code": "target_years_not_ascending",
            "path": "target_years",
            "message": "target_years must be ascending",
        })
    return errors


def load_manifest(path: Path, context: PipelineContext) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    blockers: list[dict[str, Any]] = []
    try:
        manifest = read_json(path)
    except Exception as error:  # noqa: BLE001
        return None, [{"code": "manifest_load_error", "path": str(path), "message": str(error)}]
    blockers.extend(validate_manifest_shape(manifest))
    if blockers:
        return manifest, blockers
    company_id = manifest["company_id"]
    years = manifest["target_years"]
    expected = expected_paths(company_id, years)
    for field, expected_value in expected.items():
        if manifest[field] != expected_value:
            blockers.append({
                "code": f"{field}_mismatch",
                "path": field,
                "message": f"{field} must be {expected_value}",
                "expected": expected_value,
                "actual": manifest[field],
            })
    try:
        for field in ("candidate_input_path", "staging_output_path", "public_output_path"):
            resolve_safe(context.repo_root, manifest[field])
    except ValueError as error:
        blockers.append({"code": "unsafe_path", "path": "paths", "message": str(error)})
    return manifest, blockers


def candidate_financial_scope(candidate: dict[str, Any]) -> str | None:
    return (candidate.get("entity_attribution") or {}).get("financial_scope") or candidate.get("financial_scope")


def candidate_sources(candidate: dict[str, Any]) -> set[str]:
    return set((candidate.get("source_documents") or {}).keys())


def candidate_years(candidate: dict[str, Any]) -> list[int]:
    return [int(year) for year in sorted((candidate.get("financial_years") or {}).keys())]


def source_locations_for_year(candidate: dict[str, Any], year: str) -> list[dict[str, Any]]:
    locations = []
    for _, record in money_paths((candidate.get("financial_years") or {}).get(str(year), {})):
        locations.extend(record.get("source_locations") or [])
    return locations


def source_priority_summary(candidate: dict[str, Any], target_years: list[int]) -> list[dict[str, Any]]:
    priority = candidate.get("source_priority") or {}
    documents = candidate.get("source_documents") or {}
    rows = []
    for year in target_years:
        item = priority.get(str(year)) or {}
        primary = item.get("primary_source_ref")
        cross_checks = item.get("cross_check_source_refs") or []
        rows.append({
            "year": year,
            "primary_source_ref": primary,
            "cross_check_source_refs": cross_checks,
            "covered_years": documents.get(primary, {}).get("covered_years") if primary else None,
            "report_date": documents.get(primary, {}).get("report_date") if primary else None,
            "source_location_count": len(source_locations_for_year(candidate, str(year))),
            "verification_statuses": sorted({
                location.get("verification_status")
                for location in source_locations_for_year(candidate, str(year))
                if location.get("verification_status")
            }),
        })
    return rows


def normalized_source_priority_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "primary_source_ref": item.get("primary_source_ref"),
        "cross_check_source_refs": sorted(set(item.get("cross_check_source_refs") or [])),
    }


def find_metric_record(candidate: dict[str, Any], year: str, metric: str) -> dict[str, Any] | None:
    if "." in metric:
        section, key = metric.split(".", 1)
        value = (candidate.get("financial_years") or {}).get(year, {}).get(section, {}).get(key)
        return value if isinstance(value, dict) and "reported" in value else None
    matches = [record for path, record in money_paths((candidate.get("financial_years") or {}).get(year, {})) if path.endswith(f".{metric}")]
    return matches[0] if matches else None


def coverage_for_metrics(candidate: dict[str, Any], metrics: list[str], target_years: list[int]) -> dict[str, Any]:
    coverage = {}
    for metric in metrics:
        year_rows = {}
        for year in target_years:
            record = find_metric_record(candidate, str(year), metric)
            if record is None:
                year_rows[str(year)] = {"present": False, "disclosure_status": "missing", "reported": None}
            else:
                year_rows[str(year)] = {
                    "present": True,
                    "disclosure_status": record.get("disclosure_status", "reported"),
                    "reported": record.get("reported"),
                }
        coverage[metric] = year_rows
    return coverage


def disclosure_status_counts(candidate: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for _, record in money_paths(candidate):
        status = record.get("disclosure_status", "reported")
        if record.get("reported") is None and status == "reported":
            status = "missing_status"
        counts[status] = counts.get(status, 0) + 1
    return counts


def pending_manual_page_check_details(candidate: dict[str, Any]) -> dict[str, Any]:
    seen = set()
    source_ids = set()
    years = set()
    for year, year_record in (candidate.get("financial_years") or {}).items():
        for _, record in money_paths(year_record):
            for location in record.get("source_locations") or []:
                if location.get("verification_status") != "pending_manual_page_check":
                    continue
                key = (
                    location.get("source_ref"),
                    location.get("section"),
                    location.get("page_range") or location.get("page"),
                    location.get("note"),
                )
                if key in seen:
                    continue
                seen.add(key)
                source_ids.add(location.get("source_ref"))
                years.add(int(year))
    return {
        "count": len(seen),
        "source_ids": sorted(item for item in source_ids if item),
        "years": sorted(years),
    }


def issue_row(code: str, path: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "path": path, "message": message, **extra}


def reconcile_manifest_candidate(manifest: dict[str, Any], candidate: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    company_id = manifest["company_id"]
    target_years = manifest["target_years"]
    if candidate.get("company_id") != company_id:
        blockers.append(issue_row("company_id_mismatch", "company_id", "candidate company_id does not match manifest", expected=company_id, actual=candidate.get("company_id")))
    if candidate.get("reporting_entity") != manifest["reporting_entity"]:
        blockers.append(issue_row("reporting_entity_mismatch", "reporting_entity", "candidate reporting entity does not match manifest", expected=manifest["reporting_entity"], actual=candidate.get("reporting_entity")))
    if candidate_financial_scope(candidate) != manifest["financial_scope"]:
        blockers.append(issue_row("financial_scope_mismatch", "financial_scope", "candidate financial scope does not match manifest", expected=manifest["financial_scope"], actual=candidate_financial_scope(candidate)))
    if candidate.get("currency") != manifest["currency"]:
        blockers.append(issue_row("currency_mismatch", "currency", "candidate currency does not match manifest", expected=manifest["currency"], actual=candidate.get("currency")))
    if candidate.get("unit") != manifest["unit"]:
        blockers.append(issue_row("unit_mismatch", "unit", "candidate unit does not match manifest", expected=manifest["unit"], actual=candidate.get("unit")))
    if candidate_years(candidate) != target_years:
        blockers.append(issue_row("target_years_mismatch", "financial_years", "candidate years do not match manifest", expected=target_years, actual=candidate_years(candidate)))

    sources = candidate_sources(candidate)
    candidate_priority = candidate.get("source_priority") or {}
    manifest_priority = manifest.get("source_priority") or {}
    if set(manifest_priority.keys()) != {str(year) for year in target_years}:
        blockers.append(issue_row("source_priority_years_mismatch", "source_priority", "source priority must cover every target year"))
    for year in target_years:
        manifest_item = manifest_priority.get(str(year)) or {}
        candidate_item = candidate_priority.get(str(year)) or {}
        primary = manifest_item.get("primary_source_ref")
        if primary not in sources:
            blockers.append(issue_row("primary_source_missing", f"source_priority.{year}.primary_source_ref", "primary source ref is not declared in candidate source_documents", actual=primary))
        elif year not in set(documents_years := (candidate.get("source_documents") or {}).get(primary, {}).get("covered_years") or []):
            blockers.append(issue_row("primary_source_year_not_covered", f"source_priority.{year}.primary_source_ref", "primary source document does not cover target year", expected=year, actual=documents_years))
        if normalized_source_priority_item(manifest_item) != normalized_source_priority_item(candidate_item):
            blockers.append(issue_row("source_priority_mismatch", f"source_priority.{year}", "manifest source priority does not match candidate", expected=manifest_item, actual=candidate_item))
        for source_ref in manifest_item.get("cross_check_source_refs") or []:
            if source_ref not in sources:
                blockers.append(issue_row("cross_check_source_missing", f"source_priority.{year}.cross_check_source_refs", "cross-check source ref is not declared in candidate source_documents", actual=source_ref))
            elif year not in set(documents_years := (candidate.get("source_documents") or {}).get(source_ref, {}).get("covered_years") or []):
                blockers.append(issue_row("cross_check_source_year_not_covered", f"source_priority.{year}.cross_check_source_refs", "cross-check source document does not cover target year", expected=year, actual={source_ref: documents_years}))

    policy = manifest.get("promotion_policy") or {}
    required = coverage_for_metrics(candidate, manifest.get("required_metrics") or [], target_years)
    for metric, rows in required.items():
        for year, row in rows.items():
            status = row["disclosure_status"]
            if not row["present"]:
                blockers.append(issue_row("required_metric_missing", f"financial_years.{year}.{metric}", "required metric is missing"))
            elif status == "verification_pending" and not policy.get("allow_verification_pending_required_metrics", False):
                blockers.append(issue_row("required_metric_verification_pending", f"financial_years.{year}.{metric}", "required metric is verification_pending and policy does not allow it"))
            elif status in {"not_disclosed", "not_applicable", "missing_status"}:
                blockers.append(issue_row("required_metric_unavailable", f"financial_years.{year}.{metric}", "required metric is unavailable", actual=status))

    optional = coverage_for_metrics(candidate, manifest.get("optional_metrics") or [], target_years)
    for metric, rows in optional.items():
        for year, row in rows.items():
            status = row["disclosure_status"]
            if status in {"not_disclosed", "verification_pending", "missing"}:
                warnings.append(issue_row(f"optional_metric_{status}", f"financial_years.{year}.{metric}", "optional metric requires review", actual=status))

    pending_details = pending_manual_page_check_details(candidate)
    if pending_details["count"]:
        warnings.append(issue_row("pending_manual_page_check", "source_locations", "manual page check remains", actual=pending_details["count"], source_ids=pending_details["source_ids"], years=pending_details["years"]))
    for event in (candidate.get("entity_attribution") or {}).get("special_events") or []:
        warnings.append(issue_row("special_event_present", "entity_attribution.special_events", "special event requires reviewer awareness", actual=event.get("event_type")))
    return blockers, warnings


def secret_or_pdf_findings(paths: list[Path]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in paths:
        if path.suffix.lower() == ".pdf":
            findings.append(issue_row("pdf_file_detected", str(path), "PDF files must not be committed by onboarding"))
            continue
        if not path.exists() or not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(issue_row("secret_like_text_detected", str(path), "secret-like key or header name detected", actual=pattern.pattern))
                break
    return findings


def verdict_for(blockers: list[dict[str, Any]], warnings: list[dict[str, Any]], manifest: dict[str, Any]) -> str:
    if blockers:
        return BLOCKED
    allowed = set(manifest.get("allowed_warning_codes") or [])
    unallowed = [warning for warning in warnings if warning["code"] not in allowed]
    if unallowed:
        return REVIEW_REQUIRED
    policy = manifest.get("promotion_policy") or {}
    if policy.get("require_zero_blockers", True):
        return PASS
    return REVIEW_REQUIRED


def validation_report(
    manifest: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
    manifest_path: Path,
    candidate_path: Path | None,
    blockers: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    accounting_validation: dict[str, Any] | None,
) -> dict[str, Any]:
    manifest = manifest or {}
    candidate = candidate or {}
    target_years = manifest.get("target_years") or []
    verdict = verdict_for(blockers, warnings, manifest) if manifest else BLOCKED
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "verdict": verdict,
        "company_id": manifest.get("company_id") or candidate.get("company_id"),
        "target_years": target_years,
        "financial_scope": manifest.get("financial_scope"),
        "currency": manifest.get("currency"),
        "unit": manifest.get("unit"),
        "manifest_sha256": file_sha256(manifest_path) if manifest_path.exists() else None,
        "candidate_sha256": file_sha256(candidate_path) if candidate_path and candidate_path.exists() else None,
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
        "blockers": blockers,
        "warnings": warnings,
        "required_metric_coverage": coverage_for_metrics(candidate, manifest.get("required_metrics") or [], target_years) if candidate else {},
        "optional_metric_coverage": coverage_for_metrics(candidate, manifest.get("optional_metrics") or [], target_years) if candidate else {},
        "disclosure_status_counts": disclosure_status_counts(candidate) if candidate else {},
        "source_document_count": len(candidate.get("source_documents") or {}),
        "source_priority_summary": source_priority_summary(candidate, target_years) if candidate else [],
        "accounting_validation_summary": accounting_validation or {},
        "restatement_event_count": sum(1 for event in (candidate.get("entity_attribution") or {}).get("special_events") or [] if "restatement" in str(event.get("event_type", ""))),
        "pending_manual_page_check_count": pending_manual_page_check_details(candidate)["count"] if candidate else 0,
        "pending_manual_page_check_source_ids": pending_manual_page_check_details(candidate)["source_ids"] if candidate else [],
        "pending_manual_page_check_years": pending_manual_page_check_details(candidate)["years"] if candidate else [],
        "promotion_eligible": verdict == PASS,
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Company Report Onboarding Validation - {report.get('company_id') or 'unknown'}",
        "",
        f"- Verdict: {report['verdict']}",
        f"- Target years: {', '.join(str(year) for year in report.get('target_years') or [])}",
        f"- Financial scope: {report.get('financial_scope')}",
        f"- Currency/unit: {report.get('currency')} / {report.get('unit')}",
        f"- Blockers: {report['blocker_count']}",
        f"- Warnings: {report['warning_count']}",
        f"- Promotion eligible: {report['promotion_eligible']}",
        "",
        "## Blockers",
    ]
    if report["blockers"]:
        lines.extend(f"- `{item['code']}` {item['path']}: {item['message']}" for item in report["blockers"])
    else:
        lines.append("- None")
    lines.append("")
    lines.append("## Warnings")
    if report["warnings"]:
        lines.extend(f"- `{item['code']}` {item['path']}: {item['message']}" for item in report["warnings"])
    else:
        lines.append("- None")
    lines.append("")
    lines.append("This report does not extract PDF values or create new financial interpretations.")
    return "\n".join(lines) + "\n"


def write_validation_artifacts(context: PipelineContext, company_id: str, report: dict[str, Any], source_reconciliation: dict[str, Any] | None = None) -> Path:
    root = context.resolve_artifact_root(company_id)
    write_json(root / "validation-report.json", report)
    (root / "validation-report.md").write_text(markdown_report(report), encoding="utf-8")
    if source_reconciliation is not None:
        write_json(root / "source-reconciliation.json", source_reconciliation)
    return root


def validate_onboarding(manifest_path: Path, context: PipelineContext) -> dict[str, Any]:
    manifest, blockers = load_manifest(manifest_path, context)
    candidate = None
    accounting = None
    candidate_path = None
    warnings: list[dict[str, Any]] = []
    if manifest and not blockers:
        try:
            candidate_path = resolve_safe(context.repo_root, manifest["candidate_input_path"])
        except ValueError as error:
            blockers.append(issue_row("unsafe_candidate_path", "candidate_input_path", str(error)))
            candidate_path = None
    if manifest and not blockers and candidate_path is not None:
        if not candidate_path.exists():
            blockers.append(issue_row("candidate_missing", manifest["candidate_input_path"], "candidate input file does not exist"))
        else:
            candidate = read_json(candidate_path)
            accounting = validate(candidate, expected_year_override=manifest["target_years"], base_ref=context.base_ref)
            for item in accounting.get("issues") or []:
                row = issue_row(item["code"], item["path"], item["message"], expected=item.get("expected"), actual=item.get("actual"))
                if item.get("severity") == "warning":
                    warnings.append(row)
                else:
                    blockers.append(row)
            extra_blockers, extra_warnings = reconcile_manifest_candidate(manifest, candidate)
            blockers.extend(extra_blockers)
            warnings.extend(extra_warnings)
            blockers.extend(secret_or_pdf_findings([manifest_path, candidate_path]))
            public_path = resolve_safe(context.repo_root, manifest["public_output_path"])
            if public_path.exists() and not manifest.get("replace_existing", False):
                blockers.append(issue_row("public_file_exists_replace_false", manifest["public_output_path"], "public output exists but replace_existing is false"))
    report = validation_report(manifest, candidate, manifest_path, candidate_path, blockers, warnings, accounting)
    reconciliation = {
        "company_id": report.get("company_id"),
        "years": source_priority_summary(candidate, manifest.get("target_years") if manifest else []) if candidate and manifest else [],
    }
    write_validation_artifacts(context, report.get("company_id") or "unknown", report, reconciliation)
    return report


def copy_candidate_to_staging(manifest: dict[str, Any], context: PipelineContext) -> Path:
    source = resolve_safe(context.repo_root, manifest["candidate_input_path"])
    target = resolve_safe(context.repo_root, manifest["staging_output_path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return target


def stage_onboarding(manifest_path: Path, context: PipelineContext) -> dict[str, Any]:
    report = validate_onboarding(manifest_path, context)
    if report["verdict"] == BLOCKED:
        return report
    manifest = read_json(manifest_path)
    target = copy_candidate_to_staging(manifest, context)
    staged = read_json(target)
    staged_validation = validate(staged, expected_year_override=manifest["target_years"], base_ref=context.base_ref)
    if not staged_validation["valid"]:
        report["verdict"] = BLOCKED
        report["promotion_eligible"] = False
        report["blockers"].append(issue_row("staged_validation_failed", manifest["staging_output_path"], "staged output failed audit validator", actual=staged_validation["issues"]))
    report["staging_output_path"] = manifest["staging_output_path"]
    report["staging_sha256"] = file_sha256(target)
    write_validation_artifacts(context, report.get("company_id") or manifest["company_id"], report)
    shutil.copyfile(target, context.resolve_artifact_root(manifest["company_id"]) / "staged-candidate.json")
    return report


def source_payload_without_decision(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in DECISION_DERIVED_FIELDS}


def changed_top_level_paths(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    keys = sorted(set(before) | set(after))
    return [key for key in keys if before.get(key) != after.get(key)]


def raw_source_changes(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    return changed_top_level_paths(source_payload_without_decision(before), source_payload_without_decision(after))


def build_temp_input_root(manifest: dict[str, Any], context: PipelineContext) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temp = tempfile.TemporaryDirectory()
    temp_root = Path(temp.name)
    source_root = context.repo_root / "data" / "company_reports"
    input_root = temp_root / "data" / "company_reports"
    input_root.mkdir(parents=True, exist_ok=True)
    for path in sorted(source_root.glob("*/*.json")):
        try:
            if read_json(path).get("schema_version") != "company_audit_financials_v1":
                continue
        except Exception:  # noqa: BLE001
            continue
        target = input_root / path.relative_to(source_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    candidate = resolve_safe(context.repo_root, manifest["candidate_input_path"])
    public_rel = Path(manifest["public_output_path"]).relative_to("data/company_reports")
    target = input_root / public_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(candidate, target)
    return temp, input_root


def load_current_public_view_model(context: PipelineContext) -> dict[str, Any]:
    path = context.repo_root / PUBLIC_VIEW_MODEL_RELATIVE_PATH
    return read_json(path) if path.exists() else {"schema_version": "company_report_insights_v1", "companies": []}


def company_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {company["company_id"]: company for company in payload.get("companies") or []}


def preview_diff(manifest: dict[str, Any], generated: dict[str, Any], context: PipelineContext) -> dict[str, Any]:
    current = load_current_public_view_model(context)
    old_map = company_map(current)
    new_map = company_map(generated)
    company_id = manifest["company_id"]
    operation = "update" if company_id in old_map else "add"
    manifest_sha = file_sha256(resolve_safe(context.repo_root, f"data/company_reports/{company_id}/onboarding/manifest.json"))
    candidate_sha = file_sha256(resolve_safe(context.repo_root, manifest["candidate_input_path"]))
    current_public_sha = maybe_file_sha256(context.repo_root / PUBLIC_VIEW_MODEL_RELATIVE_PATH)
    protected_current = protected_file_sha_map(context)
    protected_base = protected_file_sha_map(context, base=True)
    protected_changes = protected_file_changes(context)
    affected_peer_company_ids = []
    affected_peer_metric_ids = set()
    non_target_raw_source_changes = []
    for cid, new_company in new_map.items():
        if cid == company_id or cid not in old_map:
            continue
        if (old_map[cid].get("peer_benchmarks") or []) != (new_company.get("peer_benchmarks") or []):
            affected_peer_company_ids.append(cid)
            for item in new_company.get("peer_benchmarks") or []:
                affected_peer_metric_ids.add(item.get("metric_id"))
        changes = raw_source_changes(old_map[cid], new_company)
        if changes:
            non_target_raw_source_changes.append({
                "company_id": cid,
                "changed_paths": changes,
                "before_sha256": sha256_json(source_payload_without_decision(old_map[cid])),
                "after_sha256": sha256_json(source_payload_without_decision(new_company)),
            })
    old_target = old_map.get(company_id)
    new_target = new_map.get(company_id)
    target_raw_changes = []
    target_source_changes = []
    if old_target and new_target:
        target_raw_changes = raw_source_changes(old_target, new_target)
        if old_target.get("source_summary") != new_target.get("source_summary"):
            target_source_changes.append(company_id)
    elif new_target:
        target_raw_changes.append(company_id)
        target_source_changes.append(company_id)

    expected_text = stable_json(generated)
    added_company_ids = sorted(set(new_map) - set(old_map))
    removed_company_ids = sorted(set(old_map) - set(new_map))
    unexpected_added = [cid for cid in added_company_ids if not (operation == "add" and cid == company_id)]
    unexpected_removed = removed_company_ids
    result = {
        "pipeline_contract_version": PIPELINE_CONTRACT_VERSION,
        "target_company_id": company_id,
        "operation": operation,
        "manifest_sha256": manifest_sha,
        "candidate_sha256": candidate_sha,
        "current_public_view_model_sha256": current_public_sha,
        "protected_file_sha256": protected_current,
        "base_protected_file_sha256": protected_base,
        "target_raw_changes": target_raw_changes,
        "target_source_changes": target_source_changes,
        "non_target_raw_source_changes": sorted(non_target_raw_source_changes, key=lambda row: row["company_id"]),
        "non_target_raw_source_change_count": len(non_target_raw_source_changes),
        "affected_peer_benchmark_company_ids": sorted(affected_peer_company_ids),
        "affected_peer_benchmark_metric_ids": sorted(item for item in affected_peer_metric_ids if item),
        "added_company_ids": added_company_ids,
        "removed_company_ids": removed_company_ids,
        "unexpected_added_company_ids": unexpected_added,
        "unexpected_removed_company_ids": unexpected_removed,
        "protected_file_changes": protected_changes,
        "expected_public_output_sha256": sha256_bytes(expected_text.encode("utf-8")),
    }
    result["preview_sha256"] = sha256_json(result)
    return result


def preview_gate_blockers(diff: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if diff.get("non_target_raw_source_change_count", 0) != 0:
        blockers.append(issue_row("non_target_raw_source_change", "public_diff_preview.non_target_raw_source_changes", "non-target raw/source changes are blocked", actual=diff.get("non_target_raw_source_changes")))
    if diff.get("unexpected_added_company_ids"):
        blockers.append(issue_row("unexpected_added_company", "public_diff_preview.added_company_ids", "unexpected non-target company additions are blocked", actual=diff.get("unexpected_added_company_ids")))
    if diff.get("unexpected_removed_company_ids"):
        blockers.append(issue_row("unexpected_removed_company", "public_diff_preview.removed_company_ids", "company removals are blocked", actual=diff.get("unexpected_removed_company_ids")))
    if diff.get("protected_file_changes"):
        blockers.append(issue_row("protected_file_change", "public_diff_preview.protected_file_changes", "protected file changes are blocked", actual=diff.get("protected_file_changes")))
    return blockers


def preview_onboarding(manifest_path: Path, context: PipelineContext) -> dict[str, Any]:
    report = validate_onboarding(manifest_path, context)
    manifest = read_json(manifest_path)
    if report["verdict"] == BLOCKED:
        diff = {
            "target_company_id": manifest.get("company_id"),
            "operation": "blocked",
            "preview_sha256": None,
        }
    else:
        temp, input_root = build_temp_input_root(manifest, context)
        try:
            generated = build_view_model(input_root=input_root, base_ref=context.base_ref)
            diff = preview_diff(manifest, generated, context)
            diff_blockers = preview_gate_blockers(diff)
            if diff_blockers:
                report["verdict"] = BLOCKED
                report["promotion_eligible"] = False
                report["blockers"] = list(report.get("blockers") or []) + diff_blockers
                report["blocker_count"] = len(report["blockers"])
            diff["preview_output"] = generated
        finally:
            temp.cleanup()
    root = context.resolve_artifact_root(manifest.get("company_id", "unknown"))
    write_json(root / "public-diff-preview.json", {k: v for k, v in diff.items() if k != "preview_output"})
    promotion = promotion_manifest(manifest, report, diff, write_requested=False)
    write_json(root / "promotion-manifest.json", promotion)
    return {**report, "public_diff_preview": {k: v for k, v in diff.items() if k != "preview_output"}, "promotion_manifest": promotion}


def promotion_manifest(
    manifest: dict[str, Any],
    report: dict[str, Any],
    diff: dict[str, Any],
    *,
    write_requested: bool,
    expected_preview_sha: str | None = None,
    source_ack: bool = False,
    public_ack: bool = False,
    preview_artifact_verified: bool = False,
    write_applied: bool = False,
    rollback_applied: bool = False,
    final_public_source_sha256: str | None = None,
    final_public_view_model_sha256: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": PROMOTION_MANIFEST_SCHEMA_VERSION,
        "company_id": manifest["company_id"],
        "verdict": report["verdict"],
        "promotion_eligible": report.get("promotion_eligible", False),
        "preview_artifact_verified": preview_artifact_verified,
        "manifest_unchanged_since_preview": preview_artifact_verified,
        "candidate_unchanged_since_preview": preview_artifact_verified,
        "public_view_model_unchanged_since_preview": preview_artifact_verified,
        "protected_files_unchanged_since_preview": preview_artifact_verified,
        "source_review_acknowledged": source_ack,
        "public_change_acknowledged": public_ack,
        "write_requested": write_requested,
        "write_applied": write_applied,
        "rollback_applied": rollback_applied,
        "expected_preview_sha": expected_preview_sha,
        "actual_preview_sha": diff.get("preview_sha256"),
        "manifest_sha256": report.get("manifest_sha256"),
        "candidate_sha256": report.get("candidate_sha256"),
        "target_public_path": manifest["public_output_path"],
        "target_public_view_model_path": PUBLIC_VIEW_MODEL_RELATIVE_PATH.as_posix(),
        "non_target_raw_source_change_count": diff.get("non_target_raw_source_change_count", 0),
        "protected_file_change_count": len(diff.get("protected_file_changes") or []),
        "unexpected_added_company_count": len(diff.get("unexpected_added_company_ids") or []),
        "unexpected_removed_company_count": len(diff.get("unexpected_removed_company_ids") or []),
        "changed_company_ids": sorted(set(diff.get("added_company_ids") or []) | {manifest["company_id"]}),
        "derived_peer_change_company_ids": diff.get("affected_peer_benchmark_company_ids") or [],
        "final_public_source_sha256": final_public_source_sha256,
        "final_public_view_model_sha256": final_public_view_model_sha256,
    }


def read_preview_artifact(context: PipelineContext, company_id: str) -> dict[str, Any] | None:
    path = context.resolve_artifact_root(company_id) / "public-diff-preview.json"
    if not path.exists():
        return None
    try:
        return read_json(path)
    except Exception:  # noqa: BLE001
        return {"preview_artifact_invalid": True}


def verify_preview_artifact(artifact: dict[str, Any] | None, latest: dict[str, Any], expected_preview_sha: str | None) -> tuple[bool, list[dict[str, Any]]]:
    blockers: list[dict[str, Any]] = []
    if artifact is None:
        blockers.append(issue_row("preview_artifact_missing", "public-diff-preview.json", "preview artifact must exist before promotion"))
        return False, blockers
    if artifact.get("preview_artifact_invalid"):
        blockers.append(issue_row("preview_artifact_invalid", "public-diff-preview.json", "preview artifact is not valid JSON"))
        return False, blockers
    if artifact.get("preview_sha256") != expected_preview_sha:
        blockers.append(issue_row("preview_sha_mismatch", "expected_preview_sha", "expected preview SHA does not match preview artifact", expected=expected_preview_sha, actual=artifact.get("preview_sha256")))
    comparable_fields = [
        ("manifest_sha256", "manifest_changed_after_preview"),
        ("candidate_sha256", "candidate_changed_after_preview"),
        ("current_public_view_model_sha256", "public_view_model_changed_after_preview"),
        ("protected_file_sha256", "protected_file_changed_after_preview"),
        ("base_protected_file_sha256", "protected_file_changed_after_preview"),
        ("preview_sha256", "preview_artifact_invalid"),
    ]
    for field, code in comparable_fields:
        if artifact.get(field) != latest.get(field):
            blockers.append(issue_row(code, f"public-diff-preview.{field}", "latest preview state does not match stored preview artifact", expected=artifact.get(field), actual=latest.get(field)))
    return not blockers, blockers


def replace_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(temp_name, path)
    finally:
        temp_path = Path(temp_name)
        if temp_path.exists():
            temp_path.unlink()


def promote_onboarding(
    manifest_path: Path,
    context: PipelineContext,
    *,
    expected_preview_sha: str | None,
    source_ack: bool,
    public_ack: bool,
    write: bool,
    simulate_failure: bool = False,
) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    artifact = read_preview_artifact(context, manifest["company_id"])
    preview = preview_onboarding(manifest_path, context)
    diff = preview.get("public_diff_preview") or {}
    blockers = list(preview.get("blockers") or [])
    preview_artifact_verified, artifact_blockers = verify_preview_artifact(artifact, diff, expected_preview_sha)
    blockers.extend(artifact_blockers)
    if not source_ack and (manifest.get("promotion_policy") or {}).get("require_source_review_acknowledgement", True):
        blockers.append(issue_row("source_review_acknowledgement_missing", "promote", "source review acknowledgement is required"))
    if not public_ack and (manifest.get("promotion_policy") or {}).get("require_public_change_acknowledgement", True):
        blockers.append(issue_row("public_change_acknowledgement_missing", "promote", "public change acknowledgement is required"))
    if expected_preview_sha != diff.get("preview_sha256"):
        blockers.append(issue_row("preview_sha_mismatch", "expected_preview_sha", "expected preview SHA does not match latest preview", expected=expected_preview_sha, actual=diff.get("preview_sha256")))
    if preview["verdict"] != PASS:
        blockers.append(issue_row("verdict_not_pass", "verdict", "only PASS previews can be promoted", actual=preview["verdict"]))
    if diff.get("non_target_raw_source_change_count", 0) != 0:
        blockers.append(issue_row("non_target_raw_source_change", "public_diff_preview", "non-target raw/source changes are blocked"))
    if diff.get("protected_file_changes"):
        blockers.append(issue_row("protected_file_change", "public_diff_preview", "protected file changes are blocked", actual=diff.get("protected_file_changes")))

    if blockers:
        preview["verdict"] = BLOCKED
        preview["promotion_eligible"] = False
        preview["blockers"] = blockers
        preview["blocker_count"] = len(blockers)
    promotion = promotion_manifest(
        manifest,
        preview,
        diff,
        write_requested=write,
        expected_preview_sha=expected_preview_sha,
        source_ack=source_ack,
        public_ack=public_ack,
        preview_artifact_verified=preview_artifact_verified,
    )
    root = context.resolve_artifact_root(manifest["company_id"])
    write_json(root / "promotion-manifest.json", promotion)
    if preview["verdict"] == BLOCKED or not write:
        return {**preview, "promotion_manifest": promotion, "write_applied": False}

    candidate_bytes = resolve_safe(context.repo_root, manifest["candidate_input_path"]).read_bytes()
    temp, input_root = build_temp_input_root(manifest, context)
    backups: dict[Path, bytes | None] = {}
    try:
        generated = build_view_model(input_root=input_root, base_ref=context.base_ref)
        view_model_bytes = stable_json(generated).encode("utf-8")
        public_source = resolve_safe(context.repo_root, manifest["public_output_path"])
        public_view_model = context.repo_root / PUBLIC_VIEW_MODEL_RELATIVE_PATH
        for path in (public_source, public_view_model):
            backups[path] = path.read_bytes() if path.exists() else None
        replace_atomic(public_source, candidate_bytes)
        if simulate_failure:
            raise RuntimeError("simulated promotion failure")
        replace_atomic(public_view_model, view_model_bytes)
        check = build_view_model(input_root=context.repo_root / "data" / "company_reports", base_ref=context.base_ref)
        if stable_json(check).encode("utf-8") != view_model_bytes:
            raise RuntimeError("post-promotion builder check failed")
        promotion = promotion_manifest(
            manifest,
            preview,
            diff,
            write_requested=write,
            expected_preview_sha=expected_preview_sha,
            source_ack=source_ack,
            public_ack=public_ack,
            preview_artifact_verified=preview_artifact_verified,
            write_applied=True,
            rollback_applied=False,
            final_public_source_sha256=file_sha256(public_source),
            final_public_view_model_sha256=file_sha256(public_view_model),
        )
        write_json(root / "promotion-manifest.json", promotion)
        return {**preview, "promotion_manifest": promotion, "write_applied": True, "rollback_applied": False}
    except Exception as error:  # noqa: BLE001
        rollback_applied = bool(backups)
        for path, backup in backups.items():
            if backup is None:
                if path.exists():
                    path.unlink()
            else:
                replace_atomic(path, backup)
        preview["verdict"] = BLOCKED
        preview["promotion_eligible"] = False
        preview["blockers"] = list(preview.get("blockers") or []) + [issue_row("atomic_promotion_failed", "promote", str(error))]
        preview["blocker_count"] = len(preview["blockers"])
        promotion = promotion_manifest(
            manifest,
            preview,
            diff,
            write_requested=write,
            expected_preview_sha=expected_preview_sha,
            source_ack=source_ack,
            public_ack=public_ack,
            preview_artifact_verified=preview_artifact_verified,
            write_applied=False,
            rollback_applied=rollback_applied,
            final_public_source_sha256=maybe_file_sha256(resolve_safe(context.repo_root, manifest["public_output_path"])),
            final_public_view_model_sha256=maybe_file_sha256(context.repo_root / PUBLIC_VIEW_MODEL_RELATIVE_PATH),
        )
        write_json(root / "promotion-manifest.json", promotion)
        return {**preview, "promotion_manifest": promotion, "write_applied": False, "rollback_applied": rollback_applied}
    finally:
        temp.cleanup()
