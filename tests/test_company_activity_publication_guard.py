from __future__ import annotations

from scripts.validate_company_activity_publication import validate_activity_payload


def company_payload() -> dict:
    return {
        "companies": [
            {"company_id": "alpha"},
            {"company_id": "beta"},
        ]
    }


def activity(activity_id: str, company_id: str) -> dict:
    return {
        "activityId": activity_id,
        "companyId": company_id,
        "activityType": "project",
        "title": f"{company_id} activity",
        "publishedAt": "2026-08-10",
        "sourceType": "news",
        "sourceName": "test",
        "sourceUrl": "https://example.com/article",
        "confidence": "high",
    }


def valid_candidate() -> dict:
    return {
        "schemaVersion": "company-activities-v1",
        "generatedAt": "2026-08-10T00:00:00+00:00",
        "companyCount": 2,
        "companies": [
            {"companyId": "alpha", "activityCount": 1, "activities": [activity("a-1", "alpha")]},
            {"companyId": "beta", "activityCount": 1, "activities": [activity("b-1", "beta")]},
        ],
    }


def test_valid_candidate_passes() -> None:
    assert validate_activity_payload(valid_candidate(), company_payload()) == []


def test_missing_company_row_is_blocked() -> None:
    candidate = valid_candidate()
    candidate["companies"] = candidate["companies"][:1]
    candidate["companyCount"] = 1

    errors = validate_activity_payload(candidate, company_payload())

    assert any("company universe mismatch" in error for error in errors)
    assert any("companyCount mismatch" in error for error in errors)


def test_duplicate_company_row_is_blocked() -> None:
    candidate = valid_candidate()
    candidate["companies"][1] = {
        "companyId": "alpha",
        "activityCount": 1,
        "activities": [activity("a-2", "alpha")],
    }

    errors = validate_activity_payload(candidate, company_payload())

    assert "duplicate companyId rows detected" in errors


def test_zero_activity_candidate_cannot_replace_nonempty_baseline() -> None:
    candidate = valid_candidate()
    for row in candidate["companies"]:
        row["activityCount"] = 0
        row["activities"] = []

    errors = validate_activity_payload(candidate, company_payload(), valid_candidate())

    assert any("refusing destructive activity shrink" in error for error in errors)


def test_activity_company_id_and_duplicate_id_are_checked() -> None:
    candidate = valid_candidate()
    candidate["companies"][1]["activities"][0]["activityId"] = "a-1"
    candidate["companies"][1]["activities"][0]["companyId"] = "alpha"

    errors = validate_activity_payload(candidate, company_payload())

    assert any("duplicate activityId" in error for error in errors)
    assert any("activity companyId mismatch" in error for error in errors)
