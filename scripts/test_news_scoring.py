from __future__ import annotations

import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.news_scoring import (  # noqa: E402
    SCORE_VERSION,
    apply_unified_news_score,
    apply_unified_news_scores,
    news_score_audit_stats,
    score_news_item,
)
from src.collectors.naver_news import NaverNewsCollector  # noqa: E402


TODAY = date(2026, 7, 11)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def item(title: str, *, summary: str = "요약 있음", published_at: str = "2026-07-10", organization: str = "Fixture") -> dict:
    return {
        "id": 1,
        "source": "네이버뉴스",
        "media": organization,
        "title": title,
        "summary": summary,
        "published_at": published_at,
        "original_url": "https://example.test/news",
    }


def test_korean_and_english_direct_equivalence() -> None:
    korean = score_news_item(item("LH, 모듈러 주택 공급 확대"), today=TODAY)
    english = score_news_item(item("Public agency expands modular housing supply"), today=TODAY)
    require(korean.relevance_level == "direct", "Korean direct fixture must be direct")
    require(english.relevance_level == "direct", "English direct fixture must be direct")
    require(abs(korean.relevance_score - english.relevance_score) <= 5, "Korean/English direct scores must be comparable")


def test_weak_context_equivalence() -> None:
    korean = score_news_item(item("모듈러 기숙사 제작 프로젝트"), today=TODAY)
    english = score_news_item(item("Prefab dormitory manufacturing project"), today=TODAY)
    require(korean.relevance_level == english.relevance_level, "weak/context level must match across languages")
    require(abs(korean.relevance_score - english.relevance_score) <= 5, "weak/context scores must be comparable")


def test_reference_and_excluded() -> None:
    reference = score_news_item(item("스마트건설 정책 및 건설기술 지원"), today=TODAY)
    require(reference.relevance_level == "reference", "smart construction policy fixture must be reference")
    for title in ("Python software module update", "small modular reactor project", "자동차 전자부품 모듈 생산"):
        scored = score_news_item(item(title), today=TODAY)
        require(scored.relevance_level == "excluded", f"{title} must be excluded")
        require(scored.relevance_score == 0, f"{title} must score zero")


def test_freshness_order() -> None:
    scores = [
        score_news_item(item("Modular housing project", published_at="2026-07-11"), today=TODAY).relevance_score,
        score_news_item(item("Modular housing project", published_at="2026-07-05"), today=TODAY).relevance_score,
        score_news_item(item("Modular housing project", published_at="2026-07-01"), today=TODAY).relevance_score,
        score_news_item(item("Modular housing project", published_at="2026-06-10"), today=TODAY).relevance_score,
    ]
    require(scores[0] > scores[1] > scores[2] > scores[3], "freshness buckets must be ordered")


def test_migration_preserves_identity_and_count() -> None:
    legacy = [
        item("LH, 모듈러 주택 공급 확대", published_at="2026-07-10") | {"id": 101, "relevance_score": 17},
        item("스마트건설 정책 및 건설기술 지원", published_at="2026-07-09") | {"id": 102, "relevance_score": 3},
    ]
    migrated = apply_unified_news_scores(legacy, today=TODAY)
    require(len(migrated) == len(legacy), "migration must not remove news")
    require([entry["id"] for entry in migrated] == [entry["id"] for entry in legacy], "migration must preserve IDs")
    for before, after in zip(legacy, migrated, strict=True):
        require(before["title"] == after["title"], "migration must preserve title")
        require(before["published_at"] == after["published_at"], "migration must preserve published_at")
        require(after["relevance_score_version"] == SCORE_VERSION, "migration must apply unified-v2")
        require(isinstance(after["relevance_score"], int), "score must be integer")
        require(0 <= after["relevance_score"] <= 100, "score must be 0..100")
    stats = news_score_audit_stats(legacy, migrated)
    require(stats["news_score_existing_id_missing_count"] == 0, "ID audit must not miss existing IDs")
    require(stats["news_score_missing_version_count"] == 0, "version audit must pass")
    require(stats["news_score_range_violation_count"] == 0, "score range audit must pass")


def test_apply_is_pure_copy() -> None:
    original = item("LH, 모듈러 주택 공급 확대")
    migrated = apply_unified_news_score(original, today=TODAY)
    require("relevance_score_version" not in original, "apply_unified_news_score must not mutate input")
    require(migrated["relevance_score_version"] == SCORE_VERSION, "copy must include version")


def test_naver_raw_item_uses_unified_score_without_network() -> None:
    collector = NaverNewsCollector()
    raw = collector._to_raw_item(
        "핵심 모듈러",
        "모듈러 주택",
        {
            "title": "LH, 모듈러 주택 공급 확대",
            "description": "공공기관이 모듈러 주택 프로젝트를 확대한다.",
            "originallink": "https://news.example.test/modular",
            "link": "https://search.naver.test/modular",
            "pubDate": "Fri, 10 Jul 2026 00:00:00 +0900",
        },
    )
    require(raw["relevance_score_version"] == SCORE_VERSION, "Naver raw item must use unified-v2")
    require(raw["relevance_level"] == "direct", "Naver direct raw item must be direct")
    require(isinstance(raw["relevance_score"], int) and 0 <= raw["relevance_score"] <= 100, "Naver score must be a 0..100 integer")
    require(raw["legacy_relevance_score"] < raw["relevance_score"], "legacy score should remain diagnostic only")


def main() -> int:
    tests = [
        test_korean_and_english_direct_equivalence,
        test_weak_context_equivalence,
        test_reference_and_excluded,
        test_freshness_order,
        test_migration_preserves_identity_and_count,
        test_apply_is_pure_copy,
        test_naver_raw_item_uses_unified_score_without_network,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("NEWS SCORING TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
