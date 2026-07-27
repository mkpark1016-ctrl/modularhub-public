from __future__ import annotations

from src.company_change_operations import evaluate_operations, load_expected_company_ids
from src.company_source_contribution_history import build_history_payload, concentration_diagnostics, current_run_snapshot


def candidate(candidate_id: str, source_id: str, *, status: str = "pending", company_id: str = "a", high: bool = False) -> dict:
    return {"candidateId": candidate_id, "companyId": company_id, "sourceIds": [source_id], "status": status, "highPriority": high}


def run_snapshot(run_id: str, *, naver: int = 10, dart: int = 0, public_news: int = 0) -> dict:
    total = naver + dart + public_news
    return {
        "runId": run_id,
        "runNumber": run_id,
        "headSha": "abc",
        "event": "workflow_dispatch",
        "mode": "full_audit",
        "companyCount": 11,
        "candidateCount": total,
        "auditValid": True,
        "finalGatePassed": True,
        "sourceSummaries": [
            {"sourceId": "naver_api_hub", "attempted": True, "rawCandidateShare": naver / total if total else 0, "uniqueCandidateShare": naver / total if total else 0, "independentEvidenceShare": 0, "emptyResult": naver == 0},
            {"sourceId": "dart", "attempted": True, "rawCandidateShare": dart / total if total else 0, "uniqueCandidateShare": dart / total if total else 0, "independentEvidenceShare": 0, "emptyResult": dart == 0},
            {"sourceId": "public_news", "attempted": True, "rawCandidateShare": public_news / total if total else 0, "uniqueCandidateShare": public_news / total if total else 0, "independentEvidenceShare": 0, "emptyResult": public_news == 0},
        ],
    }


def test_current_run_snapshot_separates_raw_unique_and_status_counts() -> None:
    queue = {
        "runId": "1",
        "companies": ["a", "b"],
        "candidateCount": 4,
        "highPriority": 1,
        "candidates": [
            candidate("n1", "naver_api_hub", high=True),
            candidate("n2", "naver_api_hub", status="duplicate"),
            candidate("n3", "naver_api_hub", status="conflict", company_id="b"),
            candidate("d1", "dart", status="insufficient_evidence", company_id="b"),
        ],
    }
    raw_summary = {
        "sourceStatuses": [
            {"sourceId": "naver_api_hub", "configured": True, "attempted": True, "state": "success_with_candidates", "normalizedCount": 4, "rawCount": 4},
            {"sourceId": "dart", "configured": True, "attempted": True, "state": "success_with_candidates", "normalizedCount": 1, "rawCount": 1},
            {"sourceId": "public_news", "configured": True, "attempted": True, "state": "success_empty", "normalizedCount": 0, "rawCount": 0},
        ]
    }
    snapshot = current_run_snapshot(queue=queue, raw_summary=raw_summary, source_coverage={"concentration": {"candidateCount": 4}}, audit={"valid": True}, run_metadata={"runId": "1"})
    naver = next(row for row in snapshot["sourceSummaries"] if row["sourceId"] == "naver_api_hub")
    assert naver["rawCandidateShare"] == 0.8
    assert naver["uniqueCandidateShare"] == 0.75
    assert naver["duplicateCandidateCount"] == 1
    assert naver["conflictCandidateCount"] == 1
    assert naver["highPriorityCount"] == 1


def test_single_concentrated_run_is_observe_when_history_is_available_but_not_sustained() -> None:
    history = build_history_payload(current_run=run_snapshot("3"), previous_runs=[run_snapshot("2", naver=4, dart=6), run_snapshot("1", naver=4, dart=6)])
    diagnostics = concentration_diagnostics(history, warning_threshold=0.8)
    assert diagnostics["state"] == "observe"
    assert diagnostics["concentrationCurrent"] is True
    assert diagnostics["concentrationSustained"] is False


def test_two_comparable_runs_are_history_insufficient() -> None:
    history = build_history_payload(current_run=run_snapshot("2"), previous_runs=[run_snapshot("1")])
    diagnostics = concentration_diagnostics(history, warning_threshold=0.8)
    assert diagnostics["state"] == "history_insufficient"
    assert diagnostics["comparableRunCount"] == 2
    assert diagnostics["concentrationSustained"] is False


def test_three_consecutive_concentrated_runs_are_sustained_warning() -> None:
    history = build_history_payload(current_run=run_snapshot("3"), previous_runs=[run_snapshot("2"), run_snapshot("1")])
    diagnostics = concentration_diagnostics(history, warning_threshold=0.8)
    assert diagnostics["state"] == "warning"
    assert diagnostics["concentrationSustained"] is True
    assert diagnostics["sustainedRuleMatched"] == "last_three"


def test_four_of_last_five_concentrated_runs_are_warning() -> None:
    history = build_history_payload(
        current_run=run_snapshot("5"),
        previous_runs=[run_snapshot("4"), run_snapshot("3", naver=4, dart=6), run_snapshot("2"), run_snapshot("1")],
    )
    diagnostics = concentration_diagnostics(history, warning_threshold=0.8)
    assert diagnostics["state"] == "warning"
    assert diagnostics["sustainedRuleMatched"] == "four_of_last_five"


def test_history_unavailable_gracefully_degrades() -> None:
    history = build_history_payload(current_run=run_snapshot("1"), previous_runs=[], history_error_category="history_unavailable")
    diagnostics = concentration_diagnostics(history, warning_threshold=0.8)
    assert diagnostics["state"] == "history_unavailable"
    assert diagnostics["concentrationSustained"] is False


def test_operations_alerts_only_on_sustained_concentration() -> None:
    queue = {
        "companies": load_expected_company_ids(),
        "candidateCount": 1,
        "pending": 1,
        "duplicate": 0,
        "conflict": 0,
        "insufficientEvidence": 0,
        "rejected": 0,
        "sourceStatuses": [],
    }
    audit = {"candidateIdUnique": True, "statusConservationPassed": True}
    diagnostics = {
        "state": "history_insufficient",
        "historyState": "history_insufficient",
        "concentrationCurrent": True,
        "concentrationSustained": False,
        "comparableRunCount": 2,
        "dominantSource": "naver_api_hub",
        "rawDominantSourceShare": 0.99,
        "uniqueDominantSourceShare": 0.99,
        "independentEvidenceShare": 0,
        "emptySourceStreaks": {},
        "secretExposureDetected": False,
        "publicReviewQueueExposureCount": 0,
    }
    evaluation = evaluate_operations(
        queue=queue,
        audit=audit,
        diagnostics={"bySource": {"naver_api_hub": 1}},
        raw_summary={},
        normalized={},
        digest={},
        source_coverage={},
        source_concentration_diagnostics=diagnostics,
        source_contribution_history={"comparableRunCount": 2},
        policy={"thresholds": {"expectedCompanyCount": 11}},
        artifact_paths={},
    )
    assert evaluation["state"] == "WARNING"
    assert evaluation["alertRequired"] is False

    diagnostics["state"] = "warning"
    diagnostics["concentrationSustained"] = True
    evaluation = evaluate_operations(
        queue=queue,
        audit=audit,
        diagnostics={"bySource": {"naver_api_hub": 1}},
        raw_summary={},
        normalized={},
        digest={},
        source_coverage={},
        source_concentration_diagnostics=diagnostics,
        source_contribution_history={"comparableRunCount": 3},
        policy={"thresholds": {"expectedCompanyCount": 11}},
        artifact_paths={},
    )
    assert evaluation["alertRequired"] is True
