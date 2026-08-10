from __future__ import annotations

from datetime import datetime, timezone

from scripts.build_company_activity_history import build_company_activity_history


NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)


def companies() -> list[dict]:
    return [
        {
            "company_id": "alpha-modular",
            "company_name": "알파모듈러",
            "company_name_en": "Alpha Modular",
            "aliases": ["알파모듈러", "Alpha Modular"],
        },
        {
            "company_id": "beta-modular",
            "company_name": "베타모듈러",
            "company_name_en": "Beta Modular",
            "aliases": ["베타모듈러", "Beta Modular"],
        },
    ]


def news(index: int, published_at: str) -> dict:
    return {
        "id": f"news-{index}",
        "title": f"알파모듈러 모듈러 프로젝트 {index}",
        "summary": "모듈러 사업 신규 활동",
        "published_at": published_at,
        "original_url": f"https://example.com/news/{index}",
        "source": "테스트뉴스",
        "media": "example.com",
    }


def snapshot_activity(activity_id: str, published_at: str) -> dict:
    return {
        "activityId": activity_id,
        "companyId": "alpha-modular",
        "activityType": "project",
        "title": "기존 스냅샷 활동",
        "summary": "기존 공개 활동",
        "publishedAt": published_at,
        "sourceType": "news",
        "sourceName": "기존뉴스",
        "sourceUrl": f"https://example.com/{activity_id}",
        "sourceRecordId": activity_id,
        "matchedAlias": "알파모듈러",
        "matchReason": "title_or_project_name_alias",
        "confidence": "high",
        "projectName": None,
        "organization": "example.com",
        "region": "대한민국",
        "amount": None,
        "status": "direct",
    }


def test_snapshot_is_migrated_into_long_term_history_without_retention_cutoff() -> None:
    old = snapshot_activity("legacy-2022", "2022-01-15")
    snapshot = {
        "companies": [
            {"companyId": "alpha-modular", "activityCount": 1, "activities": [old]},
            {"companyId": "beta-modular", "activityCount": 0, "activities": []},
        ]
    }

    histories, index, audit = build_company_activity_history(
        companies=companies(),
        news_items=[],
        business_items=[],
        snapshot_payload=snapshot,
        existing_histories={},
        now=NOW,
    )

    assert histories["alpha-modular"]["activities"][0]["activityId"] == "legacy-2022"
    assert histories["alpha-modular"]["activityCount"] == 1
    assert index["totalActivityCount"] == 1
    assert audit["snapshotSeedCount"] == 1


def test_history_is_not_capped_at_one_hundred_items() -> None:
    rows = [
        news(index, f"2026-{((index // 28) % 7) + 1:02d}-{(index % 28) + 1:02d}")
        for index in range(125)
    ]

    histories, index, _ = build_company_activity_history(
        companies=companies(),
        news_items=rows,
        business_items=[],
        snapshot_payload=None,
        existing_histories={},
        now=NOW,
    )

    alpha = histories["alpha-modular"]
    assert alpha["activityCount"] == 125
    assert index["companies"][0]["activityCount"] == 125
    dates = [activity["publishedAt"] for activity in alpha["activities"]]
    assert dates == sorted(dates, reverse=True)


def test_existing_history_is_preserved_when_source_inputs_no_longer_contain_it() -> None:
    old = snapshot_activity("preserved-old-activity", "2021-03-01")
    existing_histories = {
        "alpha-modular": {
            "schemaVersion": "company-activity-history-v1",
            "generatedAt": "2026-08-09T00:00:00+00:00",
            "companyId": "alpha-modular",
            "activityCount": 1,
            "activities": [old],
        }
    }

    histories, _, audit = build_company_activity_history(
        companies=companies(),
        news_items=[news(1, "2026-08-09")],
        business_items=[],
        snapshot_payload=None,
        existing_histories=existing_histories,
        now=NOW,
    )

    ids = {activity["activityId"] for activity in histories["alpha-modular"]["activities"]}
    assert "preserved-old-activity" in ids
    assert len(ids) == 2
    assert audit["existingHistoryCount"] == 1


def test_history_dedupes_repeated_source_url() -> None:
    first = news(1, "2026-08-01")
    duplicate = {**first, "id": "news-duplicate", "published_at": "2026-08-02"}

    histories, _, audit = build_company_activity_history(
        companies=companies(),
        news_items=[first, duplicate],
        business_items=[],
        snapshot_payload=None,
        existing_histories={},
        now=NOW,
    )

    assert histories["alpha-modular"]["activityCount"] == 1
    assert histories["alpha-modular"]["activities"][0]["publishedAt"] == "2026-08-02"
    assert audit["duplicateExcludedCount"] == 1
