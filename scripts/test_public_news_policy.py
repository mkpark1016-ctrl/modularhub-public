from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.news_scoring import apply_unified_news_scores  # noqa: E402
from src.public_data_policy import (  # noqa: E402
    OVERSEAS_RSS_SOURCE,
    dedupe_all_public_news_items,
    filter_publishable_news_items,
    guard_result,
)


TODAY = date(2026, 7, 11)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def news_item(**overrides: Any) -> dict[str, Any]:
    item = {
        "id": overrides.pop("id", 1),
        "source": overrides.pop("source", "Naver News"),
        "media": overrides.pop("media", "Fixture Daily"),
        "title": overrides.pop("title", "Public agency expands modular housing supply"),
        "summary": overrides.pop("summary", "A modular housing supply project is planned."),
        "published_at": overrides.pop("published_at", "2026-07-10"),
        "original_url": overrides.pop("original_url", "https://publisher.example/news"),
        "keywords": overrides.pop("keywords", "modular housing"),
    }
    item.update(overrides)
    return item


def apply_policy(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = dedupe_all_public_news_items(items)
    scored = apply_unified_news_scores(deduped, today=TODAY)
    return filter_publishable_news_items(scored)


def test_existing_excluded_removed() -> None:
    items = [
        news_item(id=1, title="Python software module update", summary="Software module release."),
        news_item(id=2, title="Public agency expands modular housing supply"),
    ]
    result = apply_policy(items)
    require([item["id"] for item in result] == [2], "existing excluded news must be removed")


def test_new_excluded_removed() -> None:
    result = apply_policy([news_item(id=3, title="small modular reactor project", summary="Nuclear reactor project.")])
    require(result == [], "new excluded news must not be published")


def test_domestic_duplicate_dedup() -> None:
    items = [
        news_item(id=10, original_url="https://a.example/news"),
        news_item(id=11, original_url="https://b.example/news"),
    ]
    result = dedupe_all_public_news_items(items)
    require(len(result) == 1, "same title/date domestic duplicates must dedupe")
    require(result[0]["id"] == 10, "smallest stable ID must survive")


def test_cross_pipeline_duplicate_dedup() -> None:
    items = [
        news_item(id=20, source="Naver News", original_url="https://domestic.example/news"),
        news_item(id=21, source=OVERSEAS_RSS_SOURCE, original_url="https://news.google.com/rss/articles/x?oc=5"),
    ]
    result = dedupe_all_public_news_items(items)
    require(len(result) == 1, "domestic/RSS same title/date duplicate must dedupe")
    require(result[0]["id"] == 20, "domestic existing ID should survive when it is smaller")


def test_overseas_duplicate_dedup() -> None:
    items = [
        news_item(id=30, source=OVERSEAS_RSS_SOURCE, original_url="https://news.google.com/rss/articles/a?oc=5"),
        news_item(id=31, source=OVERSEAS_RSS_SOURCE, original_url="https://publisher.example/direct"),
    ]
    result = dedupe_all_public_news_items(items)
    require(len(result) == 1, "RSS same title/date duplicate must dedupe")
    require(result[0]["original_url"] == "https://publisher.example/direct", "direct publisher URL must beat Google News")


def test_distinct_title_or_date_survives() -> None:
    same_title_different_dates = [
        news_item(id=40, published_at="2026-07-10"),
        news_item(id=41, published_at="2026-07-09"),
    ]
    same_date_different_titles = [
        news_item(id=42, title="Public agency expands modular housing supply"),
        news_item(id=43, title="Factory opens for modular school project"),
    ]
    require(len(dedupe_all_public_news_items(same_title_different_dates)) == 2, "same title on different dates must survive")
    require(len(dedupe_all_public_news_items(same_date_different_titles)) == 2, "different titles on same date must survive")


def test_survivor_merge_policy() -> None:
    items = [
        news_item(
            id=50,
            original_url="https://news.google.com/rss/articles/a?oc=5",
            summary="Short.",
            keywords="modular housing",
        ),
        news_item(
            id=99,
            original_url="https://publisher.example/direct",
            media="Specific Publisher",
            summary="Longer modular housing summary with supply project details.",
            keywords="modular housing, public agency",
            relevance_reasons=["publisher detail"],
        ),
    ]
    result = dedupe_all_public_news_items(items)
    require(len(result) == 1, "survivor merge must keep one item")
    survivor = result[0]
    require(survivor["id"] == 50, "smallest existing ID must survive")
    require(survivor["original_url"] == "https://publisher.example/direct", "direct URL must be merged into survivor")
    require(survivor["summary"].startswith("Longer modular"), "longer summary must be merged")
    require("public agency" in survivor["keywords"], "keywords must be merged")


def test_guard_approved_policy_removals() -> None:
    status, _ = guard_result(previous_business=100, merged_business=100, previous_news=100, merged_news=60)
    require(status == "blocked", "unexplained large news shrink must stay blocked")
    status, _ = guard_result(
        previous_business=100,
        merged_business=100,
        previous_news=100,
        merged_news=60,
        approved_news_policy_removals=40,
    )
    require(status == "passed", "approved policy removals must be accounted for by guard")


def test_idempotent_policy() -> None:
    items = [
        news_item(id=60, original_url="https://news.google.com/rss/articles/a?oc=5"),
        news_item(id=61, original_url="https://publisher.example/direct"),
        news_item(id=62, title="Python software module update", summary="Software module release."),
    ]
    once = apply_policy(items)
    twice = apply_policy(once)
    require(once == twice, "policy must be idempotent")


def main() -> int:
    tests = [
        test_existing_excluded_removed,
        test_new_excluded_removed,
        test_domestic_duplicate_dedup,
        test_cross_pipeline_duplicate_dedup,
        test_overseas_duplicate_dedup,
        test_distinct_title_or_date_survives,
        test_survivor_merge_policy,
        test_guard_approved_policy_removals,
        test_idempotent_policy,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("PUBLIC NEWS POLICY TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
