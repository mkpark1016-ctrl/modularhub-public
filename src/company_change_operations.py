from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "company_change_monitoring" / "operations_policy.json"
IDENTITIES_PATH = ROOT / "config" / "company_change_monitoring" / "company_identities.json"

REQUIRED_ARTIFACTS = {
    "rawSummary": "artifacts/company-change-monitor/raw-summary.json",
    "normalized": "artifacts/company-change-monitor/normalized-signals.json",
    "reviewQueue": "data/company_change_monitoring/review_queue.json",
    "digest": "reports/company_change_monitoring/latest_digest.json",
    "audit": "artifacts/company-change-monitor/audit-summary.json",
    "diagnostics": "artifacts/company-change-monitor/classification-diagnostics.json",
}

SOURCE_COVERAGE_ARTIFACTS = {
    "sourceCoverage": "artifacts/company-source-coverage/source-coverage-report.json",
    "dartMapping": "artifacts/company-source-coverage/dart-mapping-report.json",
    "publicNewsDiagnostics": "artifacts/company-source-coverage/public-news-empty-diagnostics.json",
}
FAILED = "FAILED"
WARNING = "WARNING"
HEALTHY = "HEALTHY"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_operations_policy(root: Path = ROOT) -> dict[str, Any]:
    return read_json(root / POLICY_PATH.relative_to(ROOT))


def load_expected_company_ids(root: Path = ROOT) -> list[str]:
    payload = read_json(root / IDENTITIES_PATH.relative_to(ROOT))
    companies = payload.get("companies", payload) if isinstance(payload, dict) else payload
    return sorted(row.get("companyId") or row.get("company_id") for row in companies)


def run_kind_from_event(event_name: str, schedule: str | None, policy: dict[str, Any]) -> str:
    if event_name == "schedule":
        if schedule == policy["daily"]["cronUtc"]:
            return "daily"
        if schedule == policy["weekly"]["cronUtc"]:
            return "weekly"
        return "scheduled_unknown"
    return "manual"


def retention_days_for_run_kind(run_kind: str, policy: dict[str, Any]) -> int:
    retention = policy.get("artifactRetentionDays", {})
    if run_kind in retention:
        return int(retention[run_kind])
    return int(retention.get("manual", 30))


def _artifact_statuses(root: Path, artifact_paths: dict[str, str] | None = None) -> dict[str, dict[str, Any]]:
    artifact_paths = artifact_paths or REQUIRED_ARTIFACTS
    statuses: dict[str, dict[str, Any]] = {}
    for name, rel in artifact_paths.items():
        path = root / rel
        exists = path.exists()
        parseable = False
        file_type = "missing"
        if exists and path.is_file():
            file_type = path.suffix.lstrip(".") or "file"
            if path.suffix == ".json":
                try:
                    read_json(path)
                    parseable = True
                except json.JSONDecodeError:
                    parseable = False
            else:
                parseable = path.stat().st_size > 0
        statuses[name] = {
            "path": rel,
            "exists": exists,
            "sizeBytes": path.stat().st_size if exists and path.is_file() else 0,
            "parseable": parseable,
            "fileType": file_type,
        }
    return statuses


def _empty_streak(source_id: str, current: dict[str, Any], history: list[dict[str, Any]]) -> int:
    if current.get("state") != "success_empty" or not current.get("attempted"):
        return 0
    streak = 1
    for previous in history:
        previous_sources = {row.get("sourceId"): row for row in previous.get("sources", [])}
        row = previous_sources.get(source_id)
        if row and row.get("state") == "success_empty" and row.get("attempted"):
            streak += 1
        else:
            break
    return streak


def _naver_only_streak(queue: dict[str, Any], history: list[dict[str, Any]]) -> int:
    current_by_source = queue.get("classificationDiagnostics", {}).get("bySource", {})
    if not current_by_source or set(current_by_source) != {"naver_api_hub"}:
        return 0
    streak = 1
    for previous in history:
        by_source = previous.get("classificationDiagnostics", {}).get("bySource", {})
        if by_source and set(by_source) == {"naver_api_hub"}:
            streak += 1
        else:
            break
    return streak


def _candidate_growth_warning(queue: dict[str, Any], history: list[dict[str, Any]], threshold_percent: float) -> dict[str, Any] | None:
    if not history:
        return None
    previous_count = int(history[0].get("candidateCount", 0) or 0)
    current_count = int(queue.get("candidateCount", 0) or 0)
    if previous_count <= 0:
        return None
    increase = ((current_count - previous_count) / previous_count) * 100
    if increase > threshold_percent:
        return {
            "code": "candidate_count_spike",
            "severity": WARNING,
            "message": f"Candidate count increased by {increase:.1f}% versus previous successful run.",
            "sustained": False,
        }
    return None


def _dart_mapping_coverage(source_status: dict[str, Any]) -> float | None:
    results = source_status.get("companyResults") or []
    if not results:
        return None
    covered = sum(1 for row in results if row.get("safeErrorCategory") != "identity_mapping_missing")
    return (covered / len(results)) * 100


def evaluate_operations(
    *,
    root: Path = ROOT,
    policy: dict[str, Any] | None = None,
    queue: dict[str, Any] | None = None,
    audit: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
    raw_summary: dict[str, Any] | None = None,
    normalized: dict[str, Any] | None = None,
    digest: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
    run_metadata: dict[str, Any] | None = None,
    artifact_paths: dict[str, str] | None = None,
    source_coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = policy or load_operations_policy(root)
    thresholds = policy.get("thresholds", {})
    history = history or []
    run_metadata = run_metadata or {}
    artifacts = _artifact_statuses(root, artifact_paths)
    source_coverage_artifacts = _artifact_statuses(root, SOURCE_COVERAGE_ARTIFACTS)

    def load_optional(name: str) -> dict[str, Any]:
        status = artifacts[name]
        if status["exists"] and status["parseable"] and status["fileType"] == "json":
            return read_json(root / status["path"])
        return {}

    queue = queue if queue is not None else load_optional("reviewQueue")
    audit = audit if audit is not None else load_optional("audit")
    diagnostics = diagnostics if diagnostics is not None else load_optional("diagnostics")
    raw_summary = raw_summary if raw_summary is not None else load_optional("rawSummary")
    normalized = normalized if normalized is not None else load_optional("normalized")
    digest = digest if digest is not None else load_optional("digest")
    if source_coverage is None:
        coverage_status = source_coverage_artifacts["sourceCoverage"]
        if coverage_status["exists"] and coverage_status["parseable"] and coverage_status["fileType"] == "json":
            source_coverage = read_json(root / coverage_status["path"])
        else:
            source_coverage = {}

    expected_ids = load_expected_company_ids(root)
    actual_ids = sorted(queue.get("companies") or [])
    missing = sorted(set(expected_ids) - set(actual_ids))
    unexpected = sorted(set(actual_ids) - set(expected_ids))
    duplicates = sorted([item for item, count in Counter(actual_ids).items() if count > 1])

    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []

    for name, status in artifacts.items():
        if not status["exists"] or status["sizeBytes"] <= 0 or not status["parseable"]:
            failures.append({"code": "artifact_invalid", "artifact": name, "severity": FAILED})

    expected_company_count = int(thresholds.get("expectedCompanyCount", 11))
    if len(actual_ids) != expected_company_count or missing or unexpected or duplicates:
        failures.append(
            {
                "code": "company_scope_mismatch",
                "severity": FAILED,
                "expected": expected_company_count,
                "actual": len(actual_ids),
                "missing": missing,
                "unexpected": unexpected,
                "duplicates": duplicates,
            }
        )

    source_statuses = queue.get("sourceStatuses") or raw_summary.get("sourceStatuses") or []
    for source in source_statuses:
        if source.get("configured") is True and not source.get("attempted"):
            failures.append({"code": "configured_source_not_attempted", "sourceId": source.get("sourceId"), "severity": FAILED})
        if source.get("state") in {"ZERO_PIPELINE_NOT_EXECUTED", "configured_deferred_to_source_adapter"}:
            failures.append({"code": str(source.get("state")), "sourceId": source.get("sourceId"), "severity": FAILED})

    status_sum = sum(int(queue.get(key, 0) or 0) for key in ["pending", "duplicate", "conflict", "insufficientEvidence", "rejected"])
    if status_sum != int(queue.get("candidateCount", 0) or 0):
        failures.append({"code": "status_conservation_failed", "severity": FAILED})

    audit_failure_keys = {
        "candidateIdUnique": False,
        "statusConservationPassed": False,
    }
    for key, bad_value in audit_failure_keys.items():
        if audit and audit.get(key) is bad_value:
            failures.append({"code": key, "severity": FAILED})

    count_failure_keys = [
        "multiStatusCandidateCount",
        "orphanDuplicateReferenceCount",
        "orphanConflictReferenceCount",
        "missingDuplicateOfCount",
        "duplicateOfSelfCount",
        "conflictSelfReferenceCount",
        "duplicateReferenceCycleCount",
        "crossCompanyContaminationCount",
        "duplicateFingerprintErrors",
        "invalidCandidateCount",
        "deferredSourceStatusCount",
        "unattemptedConfiguredSourceCount",
        "publicReviewQueueExposureCount",
        "daeseungContaminationCount",
    ]
    for key in count_failure_keys:
        if int(audit.get(key, 0) or 0) > 0:
            failures.append({"code": key, "severity": FAILED, "count": audit.get(key)})

    if audit.get("publicDataChanged") or digest.get("publicDataChanged"):
        failures.append({"code": "public_data_changed", "severity": FAILED})
    if audit.get("secretExposureDetected") or digest.get("secretExposureDetected"):
        failures.append({"code": "secret_exposure_detected", "severity": FAILED})
    if queue.get("proposal", {}).get("created") or run_metadata.get("proposalGenerated"):
        failures.append({"code": "proposal_generated", "severity": FAILED})
    if run_metadata.get("autoMerge"):
        failures.append({"code": "auto_merge_detected", "severity": FAILED})

    if int(queue.get("pending", 0) or 0) >= int(thresholds.get("pendingWarningCount", 3000)):
        warnings.append({"code": "pending_count_high", "severity": WARNING, "count": queue.get("pending"), "sustained": False})

    growth = _candidate_growth_warning(queue, history, float(thresholds.get("candidateCountWarningIncreasePercent", 50)))
    if growth:
        warnings.append(growth)

    if not history:
        notes.append({"code": "history_unavailable", "message": "Previous run artifacts were unavailable; consecutive-run warnings were not evaluated."})
    else:
        empty_threshold = int(thresholds.get("sourceEmptyConsecutiveWarningRuns", 3))
        for source in source_statuses:
            streak = _empty_streak(source.get("sourceId"), source, history)
            if streak >= empty_threshold:
                warnings.append({"code": "source_empty_streak", "severity": WARNING, "sourceId": source.get("sourceId"), "streak": streak, "sustained": True})
        naver_threshold = int(thresholds.get("naverOnlyConsecutiveWarningRuns", 3))
        naver_streak = _naver_only_streak(queue, history)
        if naver_streak >= naver_threshold:
            warnings.append({"code": "naver_only_streak", "severity": WARNING, "streak": naver_streak, "sustained": True})

    by_company = diagnostics.get("byCompany") or queue.get("classificationDiagnostics", {}).get("byCompany", {})
    candidate_count = int(queue.get("candidateCount", 0) or 0)
    if candidate_count:
        for company_id, count in by_company.items():
            share = (int(count) / candidate_count) * 100
            if share >= 60:
                warnings.append({"code": "company_candidate_concentration", "severity": WARNING, "companyId": company_id, "sharePercent": round(share, 1), "sustained": False})
    by_source = diagnostics.get("bySource") or queue.get("classificationDiagnostics", {}).get("bySource", {})
    for source_id, count in by_source.items():
        if candidate_count and (int(count) / candidate_count) * 100 >= 95:
            warnings.append({"code": "source_candidate_concentration", "severity": WARNING, "sourceId": source_id, "sharePercent": round((int(count) / candidate_count) * 100, 1), "sustained": False})

    dart_status = next((source for source in source_statuses if source.get("sourceId") == "dart"), None)
    if dart_status:
        coverage = _dart_mapping_coverage(dart_status)
        threshold = float(thresholds.get("dartIdentityMappingCoverageWarningPercent", 80))
        if coverage is not None and coverage < threshold:
            warnings.append({"code": "dart_identity_mapping_coverage_low", "severity": WARNING, "coveragePercent": round(coverage, 1), "thresholdPercent": threshold, "sustained": False})

    if source_coverage:
        for code in source_coverage.get("failureCodes", []):
            failures.append({"code": code, "severity": FAILED, "source": "source_coverage"})
        for warning in source_coverage.get("warnings", []):
            warnings.append(
                {
                    "code": warning.get("code", "source_coverage_warning"),
                    "severity": WARNING,
                    "sourceId": warning.get("sourceId"),
                    "companyId": warning.get("companyId"),
                    "sustained": bool(warning.get("sustained")),
                    "source": "source_coverage",
                }
            )
        if source_coverage.get("state") == FAILED or source_coverage.get("valid") is False:
            failures.append({"code": "source_coverage_failed", "severity": FAILED})
    else:
        notes.append({"code": "source_coverage_artifact_unavailable", "message": "Source coverage artifact was not available for operations evaluation."})
    state = FAILED if failures else WARNING if warnings else HEALTHY
    return {
        "schemaVersion": "company-change-operations-evaluation-v1",
        "generatedAt": utc_now(),
        "state": state,
        "runMetadata": run_metadata,
        "companyScope": {
            "expectedCount": expected_company_count,
            "actualCount": len(actual_ids),
            "expectedCompanyIds": expected_ids,
            "actualCompanyIds": actual_ids,
            "missing": missing,
            "unexpected": unexpected,
            "duplicates": duplicates,
        },
        "sources": source_statuses,
        "candidates": {
            "candidateCount": queue.get("candidateCount", 0),
            "pending": queue.get("pending", 0),
            "duplicate": queue.get("duplicate", 0),
            "conflict": queue.get("conflict", 0),
            "insufficientEvidence": queue.get("insufficientEvidence", 0),
            "rejected": queue.get("rejected", 0),
            "highPriority": queue.get("highPriority", 0),
            "statusConservationPassed": status_sum == int(queue.get("candidateCount", 0) or 0),
        },
        "integrity": {
            "candidateIdUnique": audit.get("candidateIdUnique"),
            "statusConservationPassed": audit.get("statusConservationPassed"),
            "multiStatusCandidateCount": audit.get("multiStatusCandidateCount", 0),
            "orphanDuplicateReferenceCount": audit.get("orphanDuplicateReferenceCount", 0),
            "orphanConflictReferenceCount": audit.get("orphanConflictReferenceCount", 0),
            "duplicateOfSelfCount": audit.get("duplicateOfSelfCount", 0),
            "conflictSelfReferenceCount": audit.get("conflictSelfReferenceCount", 0),
            "duplicateReferenceCycleCount": audit.get("duplicateReferenceCycleCount", 0),
            "crossCompanyContaminationCount": audit.get("crossCompanyContaminationCount", 0),
            "invalidCandidateCount": audit.get("invalidCandidateCount", 0),
        },
        "artifacts": artifacts,
        "sourceCoverageArtifacts": source_coverage_artifacts,
        "sourceCoverage": {
            "available": bool(source_coverage),
            "state": source_coverage.get("state"),
            "valid": source_coverage.get("valid"),
            "warningCodes": source_coverage.get("warningCodes", []),
            "failureCodes": source_coverage.get("failureCodes", []),
            "dartMappingCoverage": source_coverage.get("dartMappingCoverage", {}),
            "publicNewsDiagnostics": source_coverage.get("publicNewsDiagnostics", {}),
        },
        "protection": {
            "publicDataChanged": bool(audit.get("publicDataChanged") or digest.get("publicDataChanged")),
            "proposalGenerated": bool(queue.get("proposal", {}).get("created") or run_metadata.get("proposalGenerated")),
            "autoMerge": bool(run_metadata.get("autoMerge")),
            "publicReviewQueueExposure": int(audit.get("publicReviewQueueExposureCount", 0) or 0),
            "secretExposureDetected": bool(audit.get("secretExposureDetected") or digest.get("secretExposureDetected")),
        },
        "classificationDiagnostics": diagnostics or queue.get("classificationDiagnostics", {}),
        "warnings": warnings,
        "failures": failures,
        "notes": notes,
        "historyStatus": "available" if history else "history_unavailable",
        "alertRequired": bool(failures) or any(warning.get("sustained") for warning in warnings),
        "alertCode": alert_code({"state": state, "failures": failures, "warnings": warnings}),
    }


def alert_code(evaluation: dict[str, Any]) -> str:
    state = evaluation.get("state")
    if state == FAILED:
        first = (evaluation.get("failures") or [{"code": "unknown"}])[0].get("code", "unknown")
        return f"failed:{first}"
    sustained = [warning for warning in evaluation.get("warnings", []) if warning.get("sustained")]
    if sustained:
        return f"warning:{sustained[0].get('code')}"
    return "none"


def markdown_evaluation(evaluation: dict[str, Any]) -> str:
    lines = [
        "# Company Change Monitor Operations Evaluation",
        "",
        f"- State: `{evaluation['state']}`",
        f"- Generated at: `{evaluation['generatedAt']}`",
        f"- Alert required: `{evaluation['alertRequired']}`",
        f"- Alert code: `{evaluation['alertCode']}`",
        f"- Company count: `{evaluation['companyScope']['actualCount']}`",
        f"- Candidates: `{evaluation['candidates']['candidateCount']}`",
        f"- Pending: `{evaluation['candidates']['pending']}`",
        f"- Duplicate: `{evaluation['candidates']['duplicate']}`",
        f"- Conflict: `{evaluation['candidates']['conflict']}`",
        f"- Insufficient evidence: `{evaluation['candidates']['insufficientEvidence']}`",
        f"- High priority: `{evaluation['candidates']['highPriority']}`",
        f"- Public data changed: `{evaluation['protection']['publicDataChanged']}`",
        f"- Proposal generated: `{evaluation['protection']['proposalGenerated']}`",
        f"- Secret exposure: `{evaluation['protection']['secretExposureDetected']}`",
        "",
        "## Sources",
        "",
    ]
    for source in evaluation.get("sources", []):
        lines.append(
            f"- `{source.get('sourceId')}`: configured={source.get('configured')}, attempted={source.get('attempted')}, state={source.get('state')}, raw={source.get('rawCount')}, normalized={source.get('normalizedCount')}"
        )
    coverage = evaluation.get("sourceCoverage") or {}
    if coverage.get("available"):
        lines.extend(["", "## Source Coverage", ""])
        lines.append(f"- State: `{coverage.get('state')}`")
        lines.append(f"- Valid: `{coverage.get('valid')}`")
        lines.append(f"- Warning codes: `{', '.join(coverage.get('warningCodes') or []) or 'none'}`")
        lines.append(f"- Failure codes: `{', '.join(coverage.get('failureCodes') or []) or 'none'}`")
        lines.append(f"- DART mapping coverage: `{(coverage.get('dartMappingCoverage') or {}).get('percent')}`")
    if evaluation.get("failures"):
        lines.extend(["", "## Failures", ""])
        for failure in evaluation["failures"]:
            lines.append(f"- `{failure.get('code')}`")
    if evaluation.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        for warning in evaluation["warnings"]:
            lines.append(f"- `{warning.get('code')}`")
    if evaluation.get("notes"):
        lines.extend(["", "## Notes", ""])
        for note in evaluation["notes"]:
            lines.append(f"- `{note.get('code')}`: {note.get('message')}")
    return "\n".join(lines) + "\n"
