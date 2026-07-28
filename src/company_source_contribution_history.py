from __future__ import annotations

import io
import json
import os
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "artifacts" / "company-source-coverage"
EXPECTED_SOURCES = ["public_news", "naver_api_hub", "dart"]


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


def repo_relative_posix(path: Path, root: Path = ROOT) -> str:
    return path.relative_to(root).as_posix()


def _candidate_status(candidate: dict[str, Any]) -> str:
    return str(candidate.get("status") or candidate.get("reviewStatus") or candidate.get("review_status") or "pending")


def _candidate_sources(candidate: dict[str, Any]) -> list[str]:
    source_ids = candidate.get("sourceIds") or candidate.get("source_ids")
    if isinstance(source_ids, list):
        return [str(item) for item in source_ids if item]
    source_id = candidate.get("sourceId") or candidate.get("source") or candidate.get("source_id")
    return [str(source_id)] if source_id else []


def _candidate_company(candidate: dict[str, Any]) -> str | None:
    return candidate.get("companyId") or candidate.get("company_id")


def _is_high_priority(candidate: dict[str, Any]) -> bool:
    priority = str(candidate.get("priority") or candidate.get("severity") or "").lower()
    return bool(candidate.get("highPriority")) or priority in {"high", "critical"}


def _source_statuses(raw_summary: dict[str, Any], queue: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = raw_summary.get("sourceStatuses") or queue.get("sourceStatuses") or []
    return {str(row.get("sourceId")): row for row in rows if row.get("sourceId")}


def _status_bucket(status: str) -> str:
    normalized = status.replace("-", "_")
    if normalized == "insufficientEvidence":
        return "insufficient_evidence"
    if normalized in {"pending", "duplicate", "conflict", "rejected", "accepted", "insufficient_evidence"}:
        return normalized
    return "pending"


def current_run_snapshot(
    *,
    queue: dict[str, Any],
    raw_summary: dict[str, Any],
    source_coverage: dict[str, Any],
    audit: dict[str, Any],
    run_metadata: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or utc_now()
    candidates = queue.get("candidates") or []
    source_statuses = _source_statuses(raw_summary, queue)
    candidate_total = int(queue.get("candidateCount", 0) or len(candidates))
    companies = sorted(set(queue.get("companies") or [_candidate_company(candidate) for candidate in candidates if _candidate_company(candidate)]))

    raw_by_source = Counter()
    unique_by_source = Counter()
    status_by_source: dict[str, Counter[str]] = defaultdict(Counter)
    high_by_source = Counter()
    companies_by_source: dict[str, set[str]] = defaultdict(set)
    cross_source_candidates = Counter()

    for source_id, source in source_statuses.items():
        raw_by_source[source_id] = int(source.get("normalizedCount", source.get("candidateCount", 0)) or 0)

    for candidate in candidates:
        candidate_id = candidate.get("candidateId") or candidate.get("candidate_id")
        if not candidate_id:
            continue
        sources = sorted(set(_candidate_sources(candidate)))
        if not sources:
            continue
        status = _status_bucket(_candidate_status(candidate))
        company_id = _candidate_company(candidate)
        for source_id in sources:
            unique_by_source[source_id] += 1
            status_by_source[source_id][status] += 1
            if _is_high_priority(candidate):
                high_by_source[source_id] += 1
            if company_id:
                companies_by_source[source_id].add(company_id)
            if len(sources) > 1:
                cross_source_candidates[source_id] += 1

    if not unique_by_source and source_coverage.get("concentration", {}).get("bySource"):
        unique_by_source.update({source_id: int(count or 0) for source_id, count in source_coverage["concentration"]["bySource"].items()})

    source_ids = sorted(set(EXPECTED_SOURCES) | set(source_statuses) | set(raw_by_source) | set(unique_by_source))
    raw_total = sum(raw_by_source.values()) or int(source_coverage.get("concentration", {}).get("candidateCount", 0) or candidate_total)
    unique_total = sum(unique_by_source.values()) or candidate_total
    high_total = sum(high_by_source.values()) or int(queue.get("highPriority", 0) or 0)
    company_count = len(companies) or int(source_coverage.get("companyActual", 0) or source_coverage.get("companyExpected", 0) or 0)

    source_summaries: list[dict[str, Any]] = []
    for source_id in source_ids:
        status = source_statuses.get(source_id, {})
        raw_count = int(raw_by_source.get(source_id, 0))
        unique_count = int(unique_by_source.get(source_id, 0))
        high_count = int(high_by_source.get(source_id, 0))
        matched_company_count = len(companies_by_source.get(source_id, set()))
        if not matched_company_count:
            matched_company_count = int(status.get("companyCountWithResults", 0) or 0)
        source_summaries.append(
            {
                "sourceId": source_id,
                "configured": bool(status.get("configured", source_id in EXPECTED_SOURCES)),
                "attempted": bool(status.get("attempted")),
                "state": status.get("state") or source_coverage.get("sourceStates", {}).get(source_id, {}).get("state") or "unknown",
                "sourceType": status.get("sourceType") or source_coverage.get("sourceStates", {}).get(source_id, {}).get("sourceType"),
                "rawCount": int(status.get("rawCount", raw_count) or 0),
                "normalizedCount": int(status.get("normalizedCount", raw_count) or raw_count),
                "candidateCount": int(status.get("candidateCount", raw_count) or raw_count),
                "uniqueCandidateCount": unique_count,
                "duplicateCandidateCount": int(status_by_source[source_id].get("duplicate", 0)),
                "conflictCandidateCount": int(status_by_source[source_id].get("conflict", 0)),
                "insufficientEvidenceCount": int(status_by_source[source_id].get("insufficient_evidence", 0)),
                "highPriorityCount": high_count,
                "matchedCompanyCount": matched_company_count,
                "companyCoverageRatio": round(matched_company_count / company_count, 4) if company_count else 0,
                "latestPublishedAt": status.get("latestPublishedAt"),
                "emptyResult": bool(status.get("attempted")) and raw_count == 0 and unique_count == 0,
                "consecutiveEmptyRuns": 0,
                "errorCode": status.get("safeErrorCategory") or status.get("errorCategory"),
                "skipReason": status.get("skipReason"),
                "rawCandidateShare": round(raw_count / raw_total, 4) if raw_total else 0,
                "uniqueCandidateShare": round(unique_count / unique_total, 4) if unique_total else 0,
                "highPriorityShare": round(high_count / high_total, 4) if high_total else 0,
                "companyCoverageShare": round(matched_company_count / company_count, 4) if company_count else 0,
                "independentEvidenceShare": round(cross_source_candidates[source_id] / unique_count, 4) if unique_count else 0,
                "concentrationScore": round(max(raw_count / raw_total if raw_total else 0, unique_count / unique_total if unique_total else 0), 4),
            }
        )

    dominant_source = None
    dominant_share = 0.0
    if source_summaries:
        dominant = max(source_summaries, key=lambda row: row["rawCandidateShare"])
        dominant_source = dominant["sourceId"]
        dominant_share = dominant["rawCandidateShare"]

    return {
        "schemaVersion": "company-source-contribution-run-v1",
        "generatedAt": generated_at,
        "runId": str(run_metadata.get("runId") or queue.get("runId") or ""),
        "runNumber": str(run_metadata.get("runNumber") or ""),
        "headSha": run_metadata.get("headSha") or run_metadata.get("runSha"),
        "event": run_metadata.get("workflowEvent"),
        "mode": run_metadata.get("mode") or run_metadata.get("runKind"),
        "createdAt": run_metadata.get("createdAt"),
        "completedAt": run_metadata.get("completedAt") or generated_at,
        "durationSeconds": run_metadata.get("durationSeconds"),
        "companyCount": company_count,
        "candidateCount": candidate_total,
        "auditValid": bool(audit.get("valid", audit.get("statusConservationPassed", True))),
        "finalGatePassed": bool(run_metadata.get("finalGatePassed", True)),
        "sourceSummaries": source_summaries,
        "dominantSource": dominant_source,
        "dominantSourceShare": dominant_share,
    }


def _dominant_from_run(run: dict[str, Any]) -> tuple[str | None, float]:
    source_summaries = run.get("sourceSummaries") or []
    if not source_summaries:
        return None, 0
    row = max(source_summaries, key=lambda item: float(item.get("rawCandidateShare", 0) or 0))
    return row.get("sourceId"), float(row.get("rawCandidateShare", 0) or 0)


def build_history_payload(
    *,
    current_run: dict[str, Any],
    previous_runs: list[dict[str, Any]] | None = None,
    history_source: str = "local",
    history_error_category: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or utc_now()
    previous_runs = previous_runs or []
    runs = [current_run, *previous_runs]
    source_ids = sorted({source["sourceId"] for run in runs for source in run.get("sourceSummaries", [])})
    history_state = "history_unavailable" if history_error_category else "available"
    if history_state == "available" and len(runs) < 3:
        history_state = "history_insufficient"
    return {
        "schemaVersion": "company-source-contribution-history-v1",
        "generatedAt": generated_at,
        "historyState": history_state,
        "historySource": history_source,
        "historyErrorCategory": history_error_category,
        "comparableRunCount": len(runs),
        "currentRun": {key: current_run.get(key) for key in ["runId", "runNumber", "headSha", "event", "mode", "companyCount", "candidateCount", "auditValid", "finalGatePassed"]},
        "sourceIds": source_ids,
        "runs": runs,
        "secretExposureDetected": False,
        "publicReviewQueueExposureCount": 0,
    }


def concentration_diagnostics(
    history: dict[str, Any],
    *,
    warning_threshold: float = 0.8,
    failure_codes: list[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or utc_now()
    runs = history.get("runs") or []
    current = runs[0] if runs else {}
    dominant_source, raw_share = _dominant_from_run(current)
    unique_share = 0.0
    independent_share = 0.0
    for source in current.get("sourceSummaries", []):
        if source.get("sourceId") == dominant_source:
            unique_share = float(source.get("uniqueCandidateShare", 0) or 0)
            independent_share = float(source.get("independentEvidenceShare", 0) or 0)
            break

    concentrated_runs = []
    for run in runs:
        source_id, share = _dominant_from_run(run)
        concentrated_runs.append({"runId": run.get("runId"), "dominantSource": source_id, "rawDominantSourceShare": round(share, 4), "concentrated": share >= warning_threshold})

    comparable_count = int(history.get("comparableRunCount", len(runs)) or 0)
    last_three_sustained = comparable_count >= 3 and all(row["concentrated"] for row in concentrated_runs[:3])
    last_five = concentrated_runs[:5]
    five_of_four_sustained = len(last_five) >= 5 and sum(1 for row in last_five if row["concentrated"]) >= 4
    sustained = bool(last_three_sustained or five_of_four_sustained)
    concentration_current = raw_share >= warning_threshold
    failure_codes = failure_codes or []

    if failure_codes:
        state = "failed"
    elif history.get("historyState") == "history_unavailable":
        state = "history_unavailable"
    elif comparable_count < 3:
        state = "history_insufficient"
    elif sustained:
        state = "warning"
    elif concentration_current:
        state = "observe"
    else:
        state = "normal"

    empty_streaks = {}
    for source_id in history.get("sourceIds", []):
        streak = 0
        for run in runs:
            source = next((row for row in run.get("sourceSummaries", []) if row.get("sourceId") == source_id), {})
            if source.get("emptyResult") and source.get("attempted"):
                streak += 1
            else:
                break
        empty_streaks[source_id] = streak

    return {
        "schemaVersion": "company-source-concentration-diagnostics-v1",
        "generatedAt": generated_at,
        "state": state,
        "historyState": history.get("historyState"),
        "historySource": history.get("historySource"),
        "historyErrorCategory": history.get("historyErrorCategory"),
        "concentrationCurrent": concentration_current,
        "concentrationSustained": sustained,
        "sustainedRuleMatched": "last_three" if last_three_sustained else "four_of_last_five" if five_of_four_sustained else None,
        "comparableRunCount": comparable_count,
        "dominantSource": dominant_source,
        "rawDominantSourceShare": round(raw_share, 4),
        "uniqueDominantSourceShare": round(unique_share, 4),
        "independentEvidenceShare": round(independent_share, 4),
        "warningThreshold": warning_threshold,
        "concentratedRuns": concentrated_runs,
        "emptySourceStreaks": empty_streaks,
        "failureCodes": failure_codes,
        "secretExposureDetected": False,
        "publicReviewQueueExposureCount": 0,
        "recommendation": recommendation_for_state(state),
    }


def recommendation_for_state(state: str) -> str:
    if state == "warning":
        return "Review source mix and collector health; sustained concentration is an operating warning, not a data mutation."
    if state == "observe":
        return "Single-run source concentration observed. Continue monitoring before opening an operating alert."
    if state == "history_insufficient":
        return "At least three comparable runs are required before sustained concentration can be evaluated."
    if state == "history_unavailable":
        return "Previous run artifacts were unavailable; current-run diagnostics were preserved."
    if state == "failed":
        return "Resolve source coverage failures before treating concentration as an operating trend."
    return "Source contribution is within the current operating baseline."


def diagnostics_markdown(diagnostics: dict[str, Any]) -> str:
    lines = [
        "# Company Source Concentration Diagnostics",
        "",
        f"- State: `{diagnostics.get('state')}`",
        f"- History state: `{diagnostics.get('historyState')}`",
        f"- Comparable runs: `{diagnostics.get('comparableRunCount')}`",
        f"- Dominant source: `{diagnostics.get('dominantSource')}`",
        f"- Raw dominant source share: `{diagnostics.get('rawDominantSourceShare')}`",
        f"- Unique dominant source share: `{diagnostics.get('uniqueDominantSourceShare')}`",
        f"- Independent evidence share: `{diagnostics.get('independentEvidenceShare')}`",
        f"- Sustained: `{diagnostics.get('concentrationSustained')}`",
        f"- Recommendation: {diagnostics.get('recommendation')}",
        "",
        "## Recent Runs",
        "",
    ]
    for row in diagnostics.get("concentratedRuns", []):
        lines.append(f"- `{row.get('runId')}`: dominant=`{row.get('dominantSource')}`, share=`{row.get('rawDominantSourceShare')}`, concentrated=`{row.get('concentrated')}`")
    return "\n".join(lines) + "\n"


def load_previous_runs_from_json(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    if isinstance(payload, dict):
        return payload.get("runs", [])
    if isinstance(payload, list):
        return payload
    return []


def _github_json(url: str, token: str) -> dict[str, Any]:
    req = Request(url, headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}", "User-Agent": "ModularHubSourceHistory"})
    with urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _github_bytes(url: str, token: str) -> bytes:
    req = Request(url, headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}", "User-Agent": "ModularHubSourceHistory"})
    with urlopen(req, timeout=30) as response:
        return response.read()


def load_previous_runs_from_github(
    *,
    token: str | None,
    repository: str | None,
    current_run_id: str | None,
    workflow_file: str = "company-change-monitor.yml",
    branch: str = "main",
    max_runs: int = 14,
) -> tuple[list[dict[str, Any]], str | None]:
    if not token or not repository:
        return [], "history_unavailable"
    api = f"https://api.github.com/repos/{repository}/actions/workflows/{workflow_file}/runs?branch={branch}&status=success&per_page={max_runs}"
    try:
        runs_payload = _github_json(api, token)
        previous_runs: list[dict[str, Any]] = []
        for run in runs_payload.get("workflow_runs", []):
            run_id = str(run.get("id"))
            if current_run_id and run_id == str(current_run_id):
                continue
            if run.get("event") not in {"workflow_dispatch", "schedule"}:
                continue
            if run.get("conclusion") != "success" or run.get("status") != "completed":
                continue
            artifacts = _github_json(run.get("artifacts_url"), token)
            coverage_artifact = next((item for item in artifacts.get("artifacts", []) if item.get("name") == "company-source-coverage"), None)
            if not coverage_artifact:
                continue
            zipped = _github_bytes(coverage_artifact["archive_download_url"], token)
            with zipfile.ZipFile(io.BytesIO(zipped)) as archive:
                coverage_name = next((name for name in archive.namelist() if name.endswith("source-coverage-report.json")), None)
                if not coverage_name:
                    continue
                coverage = json.loads(archive.read(coverage_name).decode("utf-8"))
            source_summaries = []
            for source_id, source in (coverage.get("sourceStates") or {}).items():
                candidate_count = int(source.get("candidateCount", 0) or 0)
                total = int(coverage.get("concentration", {}).get("candidateCount", 0) or 0)
                source_summaries.append(
                    {
                        "sourceId": source_id,
                        "configured": source.get("configured"),
                        "attempted": source.get("attempted"),
                        "state": source.get("state"),
                        "rawCount": candidate_count,
                        "normalizedCount": candidate_count,
                        "candidateCount": candidate_count,
                        "uniqueCandidateCount": candidate_count,
                        "rawCandidateShare": round(candidate_count / total, 4) if total else 0,
                        "uniqueCandidateShare": round(candidate_count / total, 4) if total else 0,
                        "independentEvidenceShare": 0,
                        "emptyResult": bool(source.get("attempted")) and candidate_count == 0,
                    }
                )
            previous_runs.append(
                {
                    "schemaVersion": "company-source-contribution-run-v1",
                    "runId": run_id,
                    "runNumber": str(run.get("run_number") or ""),
                    "headSha": run.get("head_sha"),
                    "event": run.get("event"),
                    "mode": None,
                    "createdAt": run.get("created_at"),
                    "completedAt": run.get("updated_at"),
                    "durationSeconds": None,
                    "companyCount": coverage.get("companyActual") or coverage.get("companyExpected"),
                    "candidateCount": coverage.get("concentration", {}).get("candidateCount", 0),
                    "auditValid": True,
                    "finalGatePassed": True,
                    "sourceSummaries": source_summaries,
                }
            )
        return previous_runs, None
    except (OSError, URLError, KeyError, json.JSONDecodeError, zipfile.BadZipFile):
        return [], "history_unavailable"


def write_outputs(history: dict[str, Any], diagnostics: dict[str, Any], *, root: Path = ROOT) -> dict[str, str]:
    out_dir = root / OUTPUT_DIR.relative_to(ROOT)
    paths = {
        "sourceContributionHistory": out_dir / "source-contribution-history.json",
        "sourceConcentrationDiagnostics": out_dir / "source-concentration-diagnostics.json",
        "sourceConcentrationMarkdown": out_dir / "source-concentration-diagnostics.md",
    }
    write_json(paths["sourceContributionHistory"], history)
    write_json(paths["sourceConcentrationDiagnostics"], diagnostics)
    write_text(paths["sourceConcentrationMarkdown"], diagnostics_markdown(diagnostics))
    return {key: repo_relative_posix(path, root) for key, path in paths.items()}
