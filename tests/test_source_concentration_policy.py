from __future__ import annotations

from src.company_source_coverage import evaluate_source_coverage


def test_single_run_source_concentration_is_warning_not_failure() -> None:
    queue = {
        "runId": "run-1",
        "companies": ["a", "b"],
        "candidateCount": 10,
        "candidates": [
            {"candidateId": f"n{i}", "companyId": "a" if i < 5 else "b", "sourceIds": ["naver_api_hub"]}
            for i in range(10)
        ],
    }
    raw_summary = {
        "sourceStatuses": [
            {"sourceId": "public_news", "configured": True, "attempted": True, "state": "success_empty", "normalizedCount": 0, "companyResults": []},
            {
                "sourceId": "naver_api_hub",
                "configured": True,
                "attempted": True,
                "state": "success_with_candidates",
                "normalizedCount": 10,
                "companyResults": [
                    {"companyId": "a", "attempted": True, "state": "success_with_candidates", "candidateCount": 5},
                    {"companyId": "b", "attempted": True, "state": "success_with_candidates", "candidateCount": 5},
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
                    {"companyId": "b", "attempted": True, "state": "success_empty", "candidateCount": 0},
                ],
            },
        ]
    }
    registry = {
        "companies": [
            {"companyId": "a", "mappingStatus": "verified", "corpCode": "001"},
            {"companyId": "b", "mappingStatus": "verified", "corpCode": "002"},
        ]
    }
    report = evaluate_source_coverage(
        queue=queue,
        raw_summary=raw_summary,
        policy={
            "policyVersion": "test",
            "expectedSources": ["public_news", "naver_api_hub", "dart"],
            "requiredAttemptedSources": 3,
            "sourceConcentrationWarningThreshold": 0.8,
            "sourceConcentrationFailureThreshold": 0.95,
            "minimumDartMappingCoverage": 0.8,
        },
        dart_registry=registry,
        expected_company_ids=["a", "b"],
        generated_at="2026-07-27T00:00:00Z",
    )
    assert report["state"] == "WARNING"
    assert report["valid"] is True
    assert "source_candidate_concentration" in report["warningCodes"]
    assert "source_candidate_concentration_sustained" not in report["failureCodes"]
