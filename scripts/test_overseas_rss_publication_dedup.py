from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import src.collectors.overseas_rss_news as rss_module  # noqa: E402
from audit_overseas_rss_publication import audit_news_items  # noqa: E402
from src.collectors.overseas_rss_news import OverseasRssNewsCollector  # noqa: E402
from src.overseas_news_rules import overseas_news_content_key  # noqa: E402
from src.public_data_policy import dedupe_overseas_rss_public_items  # noqa: E402


rss_module.feedparser = None

OVERSEAS_SOURCE = "해외 모듈러 RSS"
FIXED_NOW = datetime(2026, 7, 3, tzinfo=timezone.utc)
FAILURE_TITLE = "The proposal for a modular housing complex for internally displaced persons was not supported in Mykolaiv - Інтент"


class FakeResponse:
    def __init__(self, content: str):
        self.status_code = 200
        self.content = content.encode("utf-8")
        self.headers = {"Content-Type": "application/rss+xml"}


class FakeGet:
    def __init__(self, responses: dict[str, FakeResponse]):
        self.responses = responses
        self.calls: list[str] = []

    def __call__(self, url: str, **_: Any) -> FakeResponse:
        self.calls.append(url)
        return self.responses[url]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def rss_feed(*items: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Fixture Feed</title>{''.join(items)}</channel></rss>"""


def rss_item(
    *,
    title: str = FAILURE_TITLE,
    link: str = "https://news.google.com/rss/articles/fixture?oc=5",
    pub_date: str = "Wed, 01 Jul 2026 08:00:00 GMT",
    source: str = "Інтент",
) -> str:
    return f"""
<item>
  <title>{title}</title>
  <link>{link}</link>
  <pubDate>{pub_date}</pubDate>
  <description>Modular housing complex project coverage.</description>
  <source>{source}</source>
</item>"""


def public_item(**overrides: Any) -> dict[str, Any]:
    item = {
        "id": overrides.pop("id", 1),
        "source": OVERSEAS_SOURCE,
        "media": overrides.pop("media", "Інтент"),
        "title": overrides.pop("title", FAILURE_TITLE),
        "summary": overrides.pop("summary", "Modular housing complex project coverage."),
        "published_at": overrides.pop("published_at", "2026-07-01"),
        "original_url": overrides.pop("original_url", "https://news.google.com/rss/articles/fixture?oc=5"),
        "keywords": overrides.pop("keywords", "modular housing"),
        "relevance_score": overrides.pop("relevance_score", 90),
    }
    item.update(overrides)
    return item


def filler_items(start_id: int = 100) -> list[dict[str, Any]]:
    return [
        public_item(
            id=start_id + index,
            title=f"Modular housing filler project {index}",
            original_url=f"https://publisher.example/filler-{index}",
            published_at="2026-07-02",
        )
        for index in range(4)
    ]


def audit_with_fillers(items: list[dict[str, Any]]) -> dict[str, Any]:
    return audit_news_items(items + filler_items(), now=FIXED_NOW)


def test_shared_content_key() -> None:
    key_a = overseas_news_content_key("Modular housing complex - Mykolaiv", "2026-07-01T23:30:00+03:00")
    key_b = overseas_news_content_key("Modular housing complex Mykolaiv", "Wed, 01 Jul 2026 20:30:00 GMT")
    require(key_a == key_b, "punctuation variants on the same UTC day must share a content key")
    key_c = overseas_news_content_key("Modular housing complex Mykolaiv", "2026-07-02")
    require(key_c != key_a, "same title on a different publication day must remain distinct")


def test_collector_cross_feed_content_dedup() -> None:
    feeds = [
        {"name": "Google News RSS", "url": "https://feed.example/google"},
        {"name": "Publisher RSS", "url": "https://feed.example/publisher"},
    ]
    fake_get = FakeGet(
        {
            "https://feed.example/google": FakeResponse(rss_feed(rss_item(link="https://news.google.com/rss/articles/a?oc=5", source="Google News"))),
            "https://feed.example/publisher": FakeResponse(rss_feed(rss_item(link="https://intent.press/mykolaiv", source="Інтент"))),
        }
    )
    collector = OverseasRssNewsCollector(feeds=feeds, requests_get=fake_get, today=date(2026, 7, 3))
    items = collector.collect()
    require(len(items) == 1, "collector must dedupe same title/day across feeds and organizations")
    require(collector.stats["duplicate_excluded_count"] == 1, "collector duplicate statistic mismatch")
    require(len(fake_get.calls) == 2, "collector must still request each feed at most once")


def test_public_dedup_and_audit_recovery() -> None:
    duplicates = [
        public_item(id=367, original_url="https://news.google.com/rss/articles/CBMiFixture?oc=5", summary="short", relevance_score=80),
        public_item(
            id=991,
            original_url="https://intent.press/news/modular-housing-mykolaiv",
            summary="Longer publisher summary with modular housing context.",
            keywords="modular housing, prefabricated building",
            relevance_score=95,
        ),
    ]
    before = audit_with_fillers(duplicates)
    require(before["audit_status"] == "failed", "duplicate fixture should fail before publication dedup")
    require(before["duplicate_title_date_count"] == 1, "pre-dedup duplicate count mismatch")

    deduped = dedupe_overseas_rss_public_items(duplicates)
    require(len(deduped) == 1, "public dedup must keep one overseas RSS content item")
    require(deduped[0]["id"] == 367, "stable existing ID must be preserved")
    require(deduped[0]["original_url"] == "https://intent.press/news/modular-housing-mykolaiv", "direct publisher URL must beat Google News URL")
    require(deduped[0]["relevance_score"] == 95, "highest relevance score must be retained")
    require("prefabricated building" in deduped[0]["keywords"], "keywords must be merged")

    after = audit_with_fillers(deduped)
    require(after["audit_status"] == "passed", "publication audit should pass after dedup")
    require(after["duplicate_title_date_count"] == 0, "post-dedup duplicate title/date count must be zero")


def test_title_variant_dedup() -> None:
    items = [
        public_item(id=1, title="Modular housing complex - Mykolaiv", original_url="https://publisher.example/a"),
        public_item(id=2, title="Modular housing complex Mykolaiv", original_url="https://publisher.example/b"),
    ]
    require(len(dedupe_overseas_rss_public_items(items)) == 1, "punctuation-only title variants must dedupe")


def test_distinct_title_or_date_survives() -> None:
    same_title_different_dates = [
        public_item(id=10, title="Modular housing complex Mykolaiv", published_at="2026-07-01", original_url="https://publisher.example/a"),
        public_item(id=11, title="Modular housing complex Mykolaiv", published_at="2026-07-02", original_url="https://publisher.example/b"),
    ]
    same_date_different_titles = [
        public_item(id=12, title="Modular housing complex Mykolaiv", published_at="2026-07-01", original_url="https://publisher.example/c"),
        public_item(id=13, title="Modular school project Mykolaiv", published_at="2026-07-01", original_url="https://publisher.example/d"),
    ]
    require(len(dedupe_overseas_rss_public_items(same_title_different_dates)) == 2, "same title on different dates must remain distinct")
    require(len(dedupe_overseas_rss_public_items(same_date_different_titles)) == 2, "different titles on the same date must remain distinct")


def test_existing_public_and_domestic_scope() -> None:
    overseas_existing = public_item(id=21, title="Modular apartment development opens", original_url="https://news.google.com/rss/articles/old?oc=5", summary="short")
    overseas_fresh = public_item(
        id=99,
        title="Modular apartment development opens!",
        original_url="https://publisher.example/modular-apartment",
        summary="Better modular apartment development summary.",
        keywords="modular apartment, modular construction",
    )
    domestic_same_content = {
        "id": 22,
        "source": "네이버뉴스",
        "media": "국내 언론",
        "title": "Modular apartment development opens",
        "published_at": "2026-07-01",
        "original_url": "https://domestic.example/news",
    }
    result = dedupe_overseas_rss_public_items([overseas_existing, overseas_fresh, domestic_same_content])
    require(len(result) == 2, "domestic news must not be affected by overseas RSS dedup")
    survivor = next(item for item in result if item.get("source") == OVERSEAS_SOURCE)
    require(survivor["id"] == 21, "existing overseas public ID must be retained")
    require(survivor["original_url"] == "https://publisher.example/modular-apartment", "publisher URL must be retained after merge")
    require(any(item.get("source") == "네이버뉴스" for item in result), "domestic item must remain present")


def test_failure_title_fixture_passes_after_dedup() -> None:
    inputs = [
        public_item(id=31, title=FAILURE_TITLE, original_url="https://news.google.com/rss/articles/failure-a?oc=5"),
        public_item(id=32, title=FAILURE_TITLE, original_url="https://news.google.com/rss/articles/failure-b?oc=5"),
    ]
    deduped = dedupe_overseas_rss_public_items(inputs)
    require(len(deduped) == 1, "failure title fixture must dedupe to one item")
    report = audit_with_fillers(deduped)
    require(report["audit_status"] == "passed", "failure title fixture should pass audit after dedup")
    require(report["duplicate_title_date_count"] == 0, "failure title fixture duplicate count must be zero after dedup")


def main() -> int:
    tests = [
        test_shared_content_key,
        test_collector_cross_feed_content_dedup,
        test_public_dedup_and_audit_recovery,
        test_title_variant_dedup,
        test_distinct_title_or_date_survives,
        test_existing_public_and_domestic_scope,
        test_failure_title_fixture_passes_after_dedup,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("OVERSEAS RSS PUBLICATION DEDUP TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
