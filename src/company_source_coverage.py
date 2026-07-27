from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "company_change_monitoring" / "source_coverage_policy.json"
DART_REGISTRY_PATH = ROOT / "config" / "company_change_monitoring" / "dart_company_identity_registry.json"
IDENTITIES_PATH = ROOT / "config" / "company_change_monitoring" / "company_identities.json"
RAW_SUMMARY_PATH = ROOT / "artifacts" / "company-change-monitor" / "raw-summary.json"
REVIEW_QUEUE_PATH = ROOT / "data" / "company_change_monitoring" / "review_queue.json"
OUTPUT_DIR = ROOT / "artifacts" / "company-source-coverage"

SUCCESS_EMPTY_STATES = {
    "success_empty",
    "success_empty_valid",
    "success_empty_query_miss",
    "success_empty_date_window",
    "success_empty_identity_unavailable",
}
SOURCE_FAILURE_STATES = {
    "auth_error",
    "forbidden_or_subscription_error",
    "rate_limited",
    "transport_error",
    "response_parse_error",
    "source_not_configured",
    "unsupported_source",
    "live_opt_in_required",
}
LIVE_SOURCES = {"naver_api_hub", "dart"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_source_coverage_policy(root: Path = ROOT) -> dict[str, Any]:
    return read_json(root / POLICY_PATH.relative_to(ROOT))


def load_dart_identity_registry(root: Path = ROOT) -> dict[str, Any]:
    return read_json(root / DART_REGISTRY_PATH.relative_to(ROOT))


def load_expected_company_ids(root: Path = ROOT) -> list[str]:
    payload = read_json(root / IDENTITIES_PATH.relative_to(ROOT))
    rows = payload.get("companies", payload) if isinstance(payload, dict) else payload
    return [row.get("companyId") or row.get("company_id") for row in rows]


def source_type(source_id: str) -> str:
    if source_id == "public_news":
        return "snapshot"
    if source_id == "dart":
        return "registry"
    if source_id == "naver_api_hub":
        return "live"
    return "derived"


def normalize_empty_state(source_id: str, status: dict[str, Any]) -> str:
    state = status.get("state")
    if state != "success_empty":
        return str(state or "unknown")
    if source_id == "public_news":
        return "success_empty_valid"
    if source_id == "dart":
        return "success_empty_valid"
    return "success_empty_valid"


def dart_mapping_report(
    registry: dict[str, Any],
    *,
    expected_company_ids: list[str],
    generated_at: str,
) -> dict[str, Any]:
    rows = registry.get("companies", [])
    by_id = {row.get("companyId"): row for row in rows}
    coverage_rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    for company_id in expected_company_ids:
        row = by_id.get(company_id, {})
        status = row.get("mappingStatus") or "missing_registry_row"
        status_counts[status] += 1
        coverage_rows.append(
            {
                "companyId": company_id,
                "corpCodeConfigured": bool(row.get("corpCode")),
                "mappingStatus": status,
                "identityConfidence": row.get("identityConfidence") or "unknown",
                "lastVerifiedAt": row.get("lastVerifiedAt"),
                "evidenceSourceIds": row.get("evidenceSourceIds") or [],
                "exclusionNotes": row.get("exclusionNotes") or [],
            }
        )
    verified = status_counts.get("verified", 0)
    total = len(expected_company_ids)
    coverage_ratio = verified / total if total else 0
    return {
        "schemaVersion": "company-dart-identity-coverage-v1",
        "generatedAt": generated_at,
        "companyCount": total,
        "verifiedCount": verified,
        "notVerifiedCount": total - verified,
        "mappingCoverageRatio": round(coverage_ratio, 4),
        "mappingCoveragePercent": round(coverage_ratio * 100, 1),
        "statusCounts": dict(sorted(status_counts.items())),
        "companies": coverage_rows,
    }


def public_news_empty_diagnostics(
    source_status: dict[str, Any] | None,
    *,
    expected_company_ids: list[str],
    generated_at: str,
) -> dict[str, Any]:
    source_status = source_status or {}
    state = source_status.get("state") or "not_attempted"
    normalized_state = normalize_empty_state("public_news", source_status)
    normalized_count = int(source_status.get("normalizedCount", 0) or 0)
    raw_count = int(source_status.get("rawCount", 0) or 0)
    if normalized_count > 0:
        final_zero_reason = "HAS_MATCHED_PUBLIC_NEWS"
    elif source_status.get("attempted"):
        final_zero_reason = "NO_MATCHED_PUBLIC_NEWS_IN_LOOKBACK"
    else:
        final_zero_reason = "PUBLIC_NEWS_SOURCE_NOT_ATTEMPTED"
    return {
        "schemaVersion": "company-public-news-empty-diagnostics-v1",
        "generatedAt": generated_at,
        "sourceId": "public_news",
        "sourceType": "snapshot",
        "attempted": bool(source_status.get("attempted")),
        "state": state,
        "normalizedState": normalized_state,
        "rawCount": raw_count,
        "normalizedCount": normalized_count,
        "identityRejected": int(source_status.get("identityRejected", 0) or 0),
        "latestPublishedAt": source_status.get("latestPublishedAt"),
        "companyCount": len(expected_company_ids),
        "queryCount": int(source_status.get("queryCount", 0) or 0),
        "responseCount": int(source_status.get("responseCount", raw_count) or 0),
        "matchedCompanyCount": int(source_status.get("companyCountWithResults", 0) or 0),
        "finalZeroReason": final_zero_reason,
        "diagnostics": source_status.get("diagnostics") or {},
    }


def _source_status_map(raw_summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row.get("sourceId"): row for row in raw_summary.get("sourceStatuses", [])}


def _candidate_source_counts(queue: dict[str, Any]) -> tuple[dict[str, Counter[str]], Counter[str]]:
    by_company: dict[str, Counter[str]] = defaultdict(Counter)
    by_source: Counter[str] = Counter()
    for candidate in queue.get("candidates", []):
        company_id = candidate.get("companyId")
        for source_id in candidate.get("sourceIds") or []:
            by_company[company_id][source_id] += 1
            by_source[source_id] += 1
    return by_company, by_source


def _company_results_by_source(statuses: dict[str, dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    mapped: dict[str, dict[str, dict[str, Any]]] = {}
    for source_id, source in statuses.items():
        mapped[source_id] = {row.get("companyId"): row for row in source.get("companyResults") or []}
    return mapped


def build_company_coverage_matrix(
    *,
    queue: dict[str, Any],
    raw_summary: dict[str, Any],
    expected_company_ids: list[str],
    expected_sources: list[str],
    dart_report: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    statuses = _source_status_map(raw_summary)
    company_results = _company_results_by_source(statuses)
    candidate_counts, _ = _candidate_source_counts(queue)
    dart_by_company = {row["companyId"]: row for row in dart_report.get("companies", [])}
    rows: list[dict[str, Any]] = []
    concentration_threshold = float(policy.get("sourceConcentrationWarningThreshold", 0.8))
    for company_id in expected_company_ids:
        source_rows: dict[str, dict[str, Any]] = {}
        attempted_count = 0
        result_count = 0
        total_candidates = sum(candidate_counts.get(company_id, Counter()).values())
        dominant_source = None
        dominant_share = 0.0
        if total_candidates:
            dominant_source, dominant_count = candidate_counts[company_id].most_common(1)[0]
            dominant_share = dominant_count / total_candidates
        warnings: list[str] = []
        failures: list[str] = []

        for source_id in expected_sources:
            source = statuses.get(source_id, {})
            row = company_results.get(source_id, {}).get(company_id)
            if row is None and source_id == "public_news":
                attempted = bool(source.get("attempted"))
                candidate_count = candidate_counts.get(company_id, Counter()).get(source_id, 0)
                state = normalize_empty_state(source_id, source)
            elif row is None:
                attempted = False
                candidate_count = 0
                state = "missing_company_result"
            else:
                attempted = bool(row.get("attempted"))
                candidate_count = int(row.get("candidateCount", 0) or 0)
                state = normalize_empty_state(source_id, row)
            if attempted:
                attempted_count += 1
            if candidate_count > 0:
                result_count += 1
            source_rows[source_id] = {
                "attempted": attempted,
                "state": state,
                "candidateCount": candidate_count,
                "sourceType": source_type(source_id),
            }

        dart_mapping = dart_by_company.get(company_id, {})
        if attempted_count == 0:
            failures.append("company_source_coverage_zero")
        if attempted_count == 1:
            warnings.append("company_single_source_coverage")
        if total_candidates and dominant_share >= concentration_threshold:
            warnings.append("source_candidate_concentration")
        if dart_mapping.get("mappingStatus") != "verified":
            warnings.append("dart_identity_mapping_coverage_low")

        if failures:
            coverage_state = "failed"
        elif warnings:
            coverage_state = "warning"
        elif result_count == 0:
            coverage_state = "empty_valid"
        else:
            coverage_state = "healthy"
        rows.append(
            {
                "companyId": company_id,
                "coverageState": coverage_state,
                "attemptedSourceCount": attempted_count,
                "resultSourceCount": result_count,
                "candidateCount": total_candidates,
                "dominantSource": dominant_source,
                "dominantSourceShare": round(dominant_share, 4),
                "sourceResults": source_rows,
                "dartMappingStatus": dart_mapping.get("mappingStatus", "missing_registry_row"),
                "warningCodes": sorted(set(warnings)),
                "failureCodes": sorted(set(failures)),
            }
        )
    return rows


def evaluate_source_coverage(
    *,
    queue: dict[str, Any],
    raw_summary: dict[str, Any],
    policy: dict[str, Any] | None = None,
    dart_registry: dict[str, Any] | None = None,
    expected_company_ids: list[str] | None = None,
    run_id: str | None = None,
    head_sha: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or utc_now()
    policy = policy or load_source_coverage_policy()
    dart_registry = dart_registry or load_dart_identity_registry()
    expected_company_ids = expected_company_ids or list(queue.get("companies") or load_expected_company_ids())
    expected_sources = list(policy.get("expectedSources") or [])
    statuses = _source_status_map(raw_summary)
    dart_report = dart_mapping_report(dart_registry, expected_company_ids=expected_company_ids, generated_at=generated_at)
    public_news_diagnostics = public_news_empty_diagnostics(statuses.get("public_news"), expected_company_ids=expected_company_ids, generated_at=generated_at)
    company_matrix = build_company_coverage_matrix(
        queue=queue,
        raw_summary=raw_summary,
        expected_company_ids=expected_company_ids,
        expected_sources=expected_sources,
        dart_report=dart_report,
        policy=policy,
    )

    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    attempted_sources = [source_id for source_id in expected_sources if statuses.get(source_id, {}).get("attempted")]
    missing_sources = [source_id for source_id in expected_sources if source_id not in statuses]
    not_attempted = [source_id for source_id in expected_sources if not statuses.get(source_id, {}).get("attempted")]
    if missing_sources:
        failures.append({"code": "configured_source_not_attempted", "sources": missing_sources})
    if len(attempted_sources) < int(policy.get("requiredAttemptedSources", len(expected_sources))):
        failures.append({"code": "configured_source_not_attempted", "attemptedSources": attempted_sources})
    for source_id in not_attempted:
        state = statuses.get(source_id, {}).get("state")
        if state not in {"identity_mapping_missing"}:
            failures.append({"code": "configured_source_not_attempted", "sourceId": source_id, "state": state})

    for source_id, source in statuses.items():
        state = source.get("state")
        if source_id in expected_sources and state in SOURCE_FAILURE_STATES and state not in SUCCESS_EMPTY_STATES:
            failures.append({"code": "live_source_adapter_failed", "sourceId": source_id, "state": state})
        if source_id in LIVE_SOURCES and state in {"configured_deferred_to_source_adapter", "unsupported_source"}:
            failures.append({"code": "source_contract_failure", "sourceId": source_id, "state": state})

    by_company, by_source = _candidate_source_counts(queue)
    candidate_total = int(queue.get("candidateCount", 0) or len(queue.get("candidates", [])))
    concentration: dict[str, Any] = {
        "candidateCount": candidate_total,
        "bySource": dict(sorted(by_source.items())),
        "dominantSource": None,
        "dominantShare": 0,
    }
    if candidate_total and by_source:
        dominant_source, dominant_count = by_source.most_common(1)[0]
        share = dominant_count / candidate_total
        concentration.update({"dominantSource": dominant_source, "dominantShare": round(share, 4)})
        warning_threshold = float(policy.get("sourceConcentrationWarningThreshold", 0.8))
        failure_threshold = float(policy.get("sourceConcentrationFailureThreshold", 0.95))
        if share >= failure_threshold:
            warnings.append({"code": "source_candidate_concentration", "sourceId": dominant_source, "share": round(share, 4), "sustained": False})
        elif share >= warning_threshold:
            warnings.append({"code": "source_candidate_concentration", "sourceId": dominant_source, "share": round(share, 4), "sustained": False})

    dart_threshold = float(policy.get("minimumDartMappingCoverage", 0.8))
    if dart_report["mappingCoverageRatio"] < dart_threshold:
        warnings.append(
            {
                "code": "dart_identity_mapping_coverage_low",
                "coverageRatio": dart_report["mappingCoverageRatio"],
                "threshold": dart_threshold,
                "sustained": False,
            }
        )

    for row in company_matrix:
        for code in row.get("failureCodes", []):
            failures.append({"code": code, "companyId": row["companyId"]})
        if "company_single_source_coverage" in row.get("warningCodes", []):
            warnings.append({"code": "company_single_source_coverage", "companyId": row["companyId"], "sustained": False})

    if candidate_total == 0 and all(statuses.get(source, {}).get("attempted") for source in expected_sources):
        states = [normalize_empty_state(source, statuses.get(source, {})) for source in expected_sources]
        if not all(state in SUCCESS_EMPTY_STATES for state in states):
            failures.append({"code": "all_sources_empty_unexpected", "states": states})

    warning_codes = sorted({warning["code"] for warning in warnings})
    failure_codes = sorted({failure["code"] for failure in failures})
    state = "FAILED" if failures else "WARNING" if warnings else "HEALTHY"
    source_states = {
        source_id: {
            "configured": bool(statuses.get(source_id, {}).get("configured")),
            "attempted": bool(statuses.get(source_id, {}).get("attempted")),
            "state": statuses.get(source_id, {}).get("state", "missing_source_status"),
            "normalizedState": normalize_empty_state(source_id, statuses.get(source_id, {})),
            "sourceType": source_type(source_id),
            "candidateCount": int(statuses.get(source_id, {}).get("normalizedCount", 0) or 0),
            "latestPublishedAt": statuses.get(source_id, {}).get("latestPublishedAt"),
        }
        for source_id in expected_sources
    }
    return {
        "schemaVersion": "company-source-coverage-report-v1",
        "policyVersion": policy.get("policyVersion", "company-source-coverage-v1"),
        "generatedAt": generated_at,
        "runId": run_id or queue.get("runId"),
        "headSha": head_sha,
        "valid": not failures,
        "state": state,
        "companyExpected": len(expected_company_ids),
        "companyActual": len(queue.get("companies") or []),
        "sourceExpected": expected_sources,
        "sourceAttempted": attempted_sources,
        "sourceStates": source_states,
        "concentration": concentration,
        "dartMappingCoverage": {
            "verified": dart_report["verifiedCount"],
            "total": dart_report["companyCount"],
            "ratio": dart_report["mappingCoverageRatio"],
            "percent": dart_report["mappingCoveragePercent"],
        },
        "companyCoverage": company_matrix,
        "warningCodes": warning_codes,
        "failureCodes": failure_codes,
        "warnings": warnings,
        "failures": failures,
        "publicNewsDiagnostics": public_news_diagnostics,
        "dartMappingReport": dart_report,
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Company Source Coverage Report",
        "",
        f"- State: `{report['state']}`",
        f"- Valid: `{report['valid']}`",
        f"- Generated at: `{report['generatedAt']}`",
        f"- Companies: `{report['companyActual']}` / `{report['companyExpected']}`",
        f"- Attempted sources: `{len(report['sourceAttempted'])}` / `{len(report['sourceExpected'])}`",
        f"- DART identity coverage: `{report['dartMappingCoverage']['percent']}%`",
        f"- Dominant source: `{report['concentration'].get('dominantSource')}` share `{report['concentration'].get('dominantShare')}`",
        "",
        "## Sources",
        "",
    ]
    for source_id, source in report.get("sourceStates", {}).items():
        lines.append(
            f"- `{source_id}` ({source.get('sourceType')}): attempted={source.get('attempted')}, state={source.get('state')}, normalizedState={source.get('normalizedState')}, candidates={source.get('candidateCount')}"
        )
    if report.get("failureCodes"):
        lines.extend(["", "## Failures", ""])
        for failure in report.get("failures", []):
            lines.append(f"- `{failure.get('code')}` {failure.get('sourceId') or failure.get('companyId') or ''}".rstrip())
    if report.get("warningCodes"):
        lines.extend(["", "## Warnings", ""])
        for warning in report.get("warnings", []):
            lines.append(f"- `{warning.get('code')}` {warning.get('sourceId') or warning.get('companyId') or ''}".rstrip())
    lines.extend(["", "## Public News Diagnostics", ""])
    diagnostics = report.get("publicNewsDiagnostics", {})
    lines.append(f"- Final zero reason: `{diagnostics.get('finalZeroReason')}`")
    lines.append(f"- Matched company count: `{diagnostics.get('matchedCompanyCount')}`")
    return "\n".join(lines) + "\n"


def write_source_coverage_outputs(report: dict[str, Any], *, root: Path = ROOT) -> dict[str, str]:
    out_dir = root / OUTPUT_DIR.relative_to(ROOT)
    paths = {
        "sourceCoverageReport": out_dir / "source-coverage-report.json",
        "sourceCoverageMarkdown": out_dir / "source-coverage-report.md",
        "dartMappingReport": out_dir / "dart-mapping-report.json",
        "publicNewsEmptyDiagnostics": out_dir / "public-news-empty-diagnostics.json",
    }
    write_json(paths["sourceCoverageReport"], {k: v for k, v in report.items() if k not in {"dartMappingReport"}})
    write_text(paths["sourceCoverageMarkdown"], markdown_report(report))
    write_json(paths["dartMappingReport"], report["dartMappingReport"])
    write_json(paths["publicNewsEmptyDiagnostics"], report["publicNewsDiagnostics"])
    return {key: str(path.relative_to(root)) for key, path in paths.items()}


def audit_source_coverage_from_files(
    *,
    root: Path = ROOT,
    raw_summary_path: Path | None = None,
    review_queue_path: Path | None = None,
    run_id: str | None = None,
    head_sha: str | None = None,
    write_outputs: bool = True,
) -> dict[str, Any]:
    raw_summary = read_json(raw_summary_path or root / RAW_SUMMARY_PATH.relative_to(ROOT))
    queue = read_json(review_queue_path or root / REVIEW_QUEUE_PATH.relative_to(ROOT))
    report = evaluate_source_coverage(queue=queue, raw_summary=raw_summary, run_id=run_id, head_sha=head_sha)
    if write_outputs:
        report["artifactPaths"] = write_source_coverage_outputs(report, root=root)
    return report
