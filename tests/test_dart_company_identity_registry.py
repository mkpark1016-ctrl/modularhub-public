from __future__ import annotations

from src.company_source_coverage import dart_mapping_report


def test_dart_identity_registry_reports_verified_coverage_without_guessing() -> None:
    registry = {
        "companies": [
            {"companyId": "verified-company", "corpCode": "00123456", "mappingStatus": "verified", "identityConfidence": "high"},
            {"companyId": "research-company", "corpCode": None, "mappingStatus": "not_verified", "identityConfidence": "unknown"},
        ]
    }
    report = dart_mapping_report(
        registry,
        expected_company_ids=["verified-company", "research-company", "missing-row"],
        generated_at="2026-07-27T00:00:00Z",
    )
    assert report["companyCount"] == 3
    assert report["verifiedCount"] == 1
    assert report["mappingCoverageRatio"] == 0.3333
    assert report["statusCounts"]["missing_registry_row"] == 1
    assert report["statusCounts"]["not_verified"] == 1


def test_dart_identity_registry_keeps_same_name_exclusions_visible() -> None:
    registry = {
        "companies": [
            {
                "companyId": "daeseung-engineering",
                "corpCode": None,
                "mappingStatus": "not_verified",
                "identityConfidence": "unknown",
                "exclusionNotes": ["Exclude same-name water treatment company."],
            }
        ]
    }
    report = dart_mapping_report(registry, expected_company_ids=["daeseung-engineering"], generated_at="2026-07-27T00:00:00Z")
    row = report["companies"][0]
    assert row["mappingStatus"] == "not_verified"
    assert row["corpCodeConfigured"] is False
    assert "water treatment" in row["exclusionNotes"][0]
