from __future__ import annotations

from datetime import datetime, timezone

from build_company_activity_timeline import build_alias_registry, build_timeline


NOW = datetime(2026, 7, 28, tzinfo=timezone.utc)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def companies() -> list[dict[str, object]]:
    return [
        {
            "company_id": "yuchang-enc",
            "company_name": "유창이앤씨",
            "company_name_en": "YooChang E&C",
            "aliases": ["유창이앤씨", "YooChang E&C"],
        },
        {
            "company_id": "kumkang-kind",
            "company_name": "금강공업",
            "company_name_en": "Kumkang Kind",
            "aliases": ["금강공업", "금강"],
        },
        {
            "company_id": "daeseung-engineering",
            "company_name": "대승엔지니어링",
            "aliases": ["대승엔지니어링", "대승"],
        },
    ]


def news(title: str, summary: str = "", **extra: object) -> dict[str, object]:
    payload = {
        "id": extra.pop("id", title),
        "title": title,
        "summary": summary,
        "published_at": extra.pop("published_at", "2026-07-20"),
        "original_url": extra.pop("original_url", f"https://news.example.test/{abs(hash(title))}"),
        "source": "네이버뉴스",
        "media": "fixture",
    }
    payload.update(extra)
    return payload


def business(title: str, **extra: object) -> dict[str, object]:
    payload = {
        "id": extra.pop("id", title),
        "title": title,
        "summary": extra.pop("summary", title),
        "posted_at": extra.pop("posted_at", "2026-07-20"),
        "source_type": extra.pop("source_type", "bid"),
        "source_record_id": extra.pop("source_record_id", title),
        "source_name": "나라장터",
        "organization": extra.pop("organization", "교육청"),
        "demand_org": extra.pop("demand_org", "교육청"),
    }
    payload.update(extra)
    return payload


def build(news_items: list[dict[str, object]], business_items: list[dict[str, object]] | None = None):
    return build_timeline(
        companies=companies(),
        news_items=news_items,
        business_items=business_items or [],
        existing_payload=None,
        now=NOW,
    )


def activities_for(output: dict, company_id: str) -> list[dict]:
    row = next(item for item in output["companies"] if item["companyId"] == company_id)
    return row["activities"]


def test_exact_and_english_alias_matching() -> None:
    output, audit = build([
        news("유창이앤씨 모듈러 학교 프로젝트 수주"),
        news("YooChang E&C expands modular construction exports"),
    ])
    rows = activities_for(output, "yuchang-enc")
    require(len(rows) == 2, "Korean and English aliases must match")
    require(all(row["confidence"] in {"high", "medium"} for row in rows), "only public confidence rows allowed")
    require(audit["companyCount"] == 3, "company count mismatch")


def test_ambiguous_alias_and_identity_guard() -> None:
    aliases, collisions = build_alias_registry(companies())
    require(not collisions, "fixture aliases should not collide")
    ambiguous = [row for row in aliases if row["alias"] in {"금강", "대승"}]
    require(ambiguous and all(row["ambiguous"] for row in ambiguous), "short ambiguous aliases must be excluded")

    output, audit = build([
        news("대승 수처리 제진기 업체 김해 공장 소식", "최병천 대표의 기계설비 기사"),
        news("금강 일대 모듈러 축제 일반 기사"),
    ])
    require(len(activities_for(output, "daeseung-engineering")) == 0, "same-name Daeseung article must be blocked")
    require(len(activities_for(output, "kumkang-kind")) == 0, "ambiguous Kumkang alias must not match")
    require(audit["ambiguousExcludedCount"] >= 1, "ambiguous exclusion must be counted")


def test_multi_company_news_and_business_org_only_guard() -> None:
    output, audit = build(
        [news("유창이앤씨와 금강공업 모듈러 공동개발 협약")],
        [
            business(
                "모듈러 교실 임차 입찰공고",
                organization="유창이앤씨",
                demand_org="유창이앤씨",
                source_record_id="org-only",
            ),
            business(
                "금강공업 모듈러 제작 입찰 참여 공고",
                organization="교육청",
                demand_org="교육청",
                source_record_id="bid-company-title",
            ),
        ],
    )
    require(len(activities_for(output, "yuchang-enc")) == 1, "multi-company news should create Yuchang activity")
    require(len(activities_for(output, "kumkang-kind")) == 2, "news plus title business activity expected for Kumkang")
    require(audit["orderingOrgOnlyExcludedCount"] == 1, "business ordering-org-only match must be excluded")
    require(audit["businessActivityCount"] == 1, "only title-level business match should be published")


def test_dedupe_retention_and_limit() -> None:
    rows = [
        news("유창이앤씨 모듈러 프로젝트 중복", original_url="https://news.example.test/dup", id="a"),
        news("유창이앤씨 모듈러 프로젝트 중복", original_url="https://news.example.test/dup", id="b"),
        news("유창이앤씨 오래된 모듈러 기사", published_at="2023-01-01", original_url="https://news.example.test/old"),
    ]
    rows.extend(
        news(
            f"유창이앤씨 모듈러 프로젝트 {idx}",
            id=f"many-{idx}",
            published_at=f"2026-07-{(idx % 20) + 1:02d}",
            original_url=f"https://news.example.test/many-{idx}",
        )
        for idx in range(120)
    )
    output, audit = build(rows)
    yuchang = activities_for(output, "yuchang-enc")
    require(len(yuchang) == 100, "company activities must be capped at 100")
    require(all(row["publishedAt"] >= "2024-07-01" for row in yuchang), "activities must respect retention window")
    require(audit["duplicateExcludedCount"] >= 1, "duplicate URL exclusion must be counted")


def main() -> int:
    tests = [
        test_exact_and_english_alias_matching,
        test_ambiguous_alias_and_identity_guard,
        test_multi_company_news_and_business_org_only_guard,
        test_dedupe_retention_and_limit,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("COMPANY ACTIVITY TIMELINE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
