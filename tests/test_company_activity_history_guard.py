from __future__ import annotations

from scripts.validate_company_activity_history import validate_activity_history


def company_payload() -> dict:
    return {"companies": [{"company_id": "alpha"}, {"company_id": "beta"}]}


def activity(activity_id: str, company_id: str, published_at: str) -> dict:
    return {
        "activityId": activity_id,
        "companyId": company_id,
        "activityType": "project",
        "title": f"{company_id} activity {activity_id}",
        "publishedAt": published_at,
        "sourceType": "news",
        "sourceName": "테스트뉴스",
        "sourceUrl": f"https://example.com/{activity_id}",
        "confidence": "high",
    }


def history(company_id: str, activities: list[dict]) -> dict:
    return {
        "schemaVersion": "company-activity-history-v1",
        "generatedAt": "2026-08-10T00:00:00+00:00",
        "companyId": company_id,
        "activityCount": len(activities),
        "activities": activities,
    }


def valid_histories() -> dict[str, dict]:
    return {
        "alpha": history("alpha", [activity("a-2", "alpha", "2026-08-09"), activity("a-1", "alpha", "2025-01-01")]),
        "beta": history("beta", [activity("b-1", "beta", "2026-07-01")]),
    }


def valid_index() -> dict:
    return {
        "schemaVersion": "company-activity-history-index-v1",
        "generatedAt": "2026-08-10T00:00:00+00:00",
        "companyCount": 2,
        "totalActivityCount": 3,
        "companies": [
            {
                "companyId": "alpha",
                "activityCount": 2,
                "latestPublishedAt": "2026-08-09",
                "earliestPublishedAt": "2025-01-01",
                "path": "company-activity-history/alpha.json",
            },
            {
                "companyId": "beta",
                "activityCount": 1,
                "latestPublishedAt": "2026-07-01",
                "earliestPublishedAt": "2026-07-01",
                "path": "company-activity-history/beta.json",
            },
        ],
    }


def snapshot() -> dict:
    return {
        "companies": [
            {"companyId": "alpha", "activityCount": 1, "activities": [activity("a-2", "alpha", "2026-08-09")]},
            {"companyId": "beta", "activityCount": 1, "activities": [activity("b-1", "beta", "2026-07-01")]},
        ]
    }


def test_valid_history_passes_and_contains_snapshot() -> None:
    assert validate_activity_history(valid_index(), valid_histories(), company_payload(), snapshot=snapshot()) == []


def test_history_cannot_drop_snapshot_activity() -> None:
    histories = valid_histories()
    histories["alpha"]["activities"] = [activity("a-1", "alpha", "2025-01-01")]
    histories["alpha"]["activityCount"] = 1
    index = valid_index()
    index["companies"][0]["activityCount"] = 1
    index["companies"][0]["latestPublishedAt"] = "2025-01-01"
    index["totalActivityCount"] = 2

    errors = validate_activity_history(index, histories, company_payload(), snapshot=snapshot())

    assert any("history missing snapshot activities for alpha" in error for error in errors)


def test_history_cannot_drop_previously_retained_activity() -> None:
    baseline = valid_histories()
    candidate = valid_histories()
    candidate["alpha"]["activities"] = [activity("a-2", "alpha", "2026-08-09")]
    candidate["alpha"]["activityCount"] = 1
    index = valid_index()
    index["companies"][0]["activityCount"] = 1
    index["companies"][0]["earliestPublishedAt"] = "2026-08-09"
    index["totalActivityCount"] = 2

    errors = validate_activity_history(
        index,
        candidate,
        company_payload(),
        snapshot=snapshot(),
        baseline_histories=baseline,
    )

    assert any("refusing destructive history shrink for alpha" in error for error in errors)


def test_history_must_be_newest_first() -> None:
    histories = valid_histories()
    histories["alpha"]["activities"].reverse()

    errors = validate_activity_history(valid_index(), histories, company_payload(), snapshot=snapshot())

    assert any("history activities are not newest-first for alpha" in error for error in errors)


def test_history_index_path_and_totals_are_checked() -> None:
    index = valid_index()
    index["companies"][0]["path"] = "wrong/alpha.json"
    index["totalActivityCount"] = 999

    errors = validate_activity_history(index, valid_histories(), company_payload(), snapshot=snapshot())

    assert any("unexpected history path for alpha" in error for error in errors)
    assert any("history totalActivityCount mismatch" in error for error in errors)
