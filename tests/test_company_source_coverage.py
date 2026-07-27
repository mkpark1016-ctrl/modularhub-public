from __future__ import annotations

from src.company_source_coverage import evaluate_source_coverage


def _policy() -> dict:
    return {
        "policyVersion": "test",
        "expectedSources": ["public_news", "naver_api_hub", "dart"],
        "requiredAttemptedSources": 3,
        "sourceConcentrationWarningThreshold": 0.8,
        "sourceConcentrationFailureThreshold": 0.95,
        "minimumDartMappingCoverage": 0.8,
    }


def _registry() -> dict:
    return {
        "companies": [
            {"companyId": "a", "corpCode": "001", "mappingStatus": "verified", "identityConfidence": "high"},
            {"companyId": "b", "corpCode": None, "mappingStatus": "not_verified", "identityConfidence": "unknown"},
        ]
    }


def test_source_coverage_distinguishes_attempted_empty_from_failure() -> None:
    queue = {
        "runId": "run-1",
        "companies": ["a", "b"],
        "candidateCount": 1,
        "candidates": [{"candidateId": "c1", "companyId": "a", "sourceIds": ["naver_api_hub"]}],
    }
    raw_summary = {
        "sourceStatuses": [
            {"sourceId": "public_news", "configured": True, "attempted": True, "state": "success_empty", "normalizedCount": 0, "companyResults": []},
            {
                "sourceId": "naver_api_hub",
                "configured": True,
                "attempted": True,
                "state": "success_with_candidates",
                "normalizedCount": 1,
                "companyResults": [
                    {"companyId": "a", "attempted": True, "state": "success_with_candidates", "candidateCount": 1},
                    {"companyId": "b", "attempted": True, "state": "success_empty", "candidateCount": 0},
                ],
            },
            {
                "sourceId": "dart",
                "configured": True,
                "attempted": True,
                "state": "success_empty",
                "normalizedCount": 0,
                "companyResults": [
                    {"companyId": "a", "attempted": True, "state": "success_empty", "candidateCount": 0},
                    {"companyId": "b", "attempted": False, "state": "identity_mapping_missing", "candidateCount": 0},
                ],
            },
        ]
    }
    report = evaluate_source_coverage(
        queue=queue,
        raw_summary=raw_summary,
        policy=_policy(),
        dart_registry=_registry(),
        expected_company_ids=["a", "b"],
        generated_at="2026-07-27T00:00:00Z",
    )
    assert report["valid"] is True
    assert "configured_source_not_attempted" not in report["failureCodes"]
    assert report["sourceStates"]["public_news"]["normalizedState"] == "success_empty_valid"
    assert report["publicNewsDiagnostics"]["finalZeroReason"] == "NO_MATCHED_PUBLIC_NEWS_IN_LOOKBACK"


def test_company_source_coverage_zero_is_failure() -> None:
    queue = {"runId": "run-1", "companies": ["a"], "candidateCount": 0, "candidates": []}
    raw_summary = {
        "sourceStatuses": [
            {"sourceId": "public_news", "configured": True, "attempted": False, "state": "not_attempted", "normalizedCount": 0, "companyResults": []},
            {"sourceId": "naver_api_hub", "configured": True, "attempted": False, "state": "not_attempted", "normalizedCount": 0, "companyResults": []},
            {"sourceId": "dart", "configured": True, "attempted": False, "state": "not_attempted", "normalizedCount": 0, "companyResults": []},
        ]
    }
    report = evaluate_source_coverage(
        queue=queue,
        raw_summary=raw_summary,
        policy=_policy(),
        dart_registry={"companies": [{"companyId": "a", "mappingStatus": "not_verified"}]},
        expected_company_ids=["a"],
        generated_at="2026-07-27T00:00:00Z",
    )
    assert report["state"] == "FAILED"
    assert "company_source_coverage_zero" in report["failureCodes"]
