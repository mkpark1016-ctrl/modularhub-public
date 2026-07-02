from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import src.collectors.overseas_rss_news as rss_module  # noqa: E402
from src.collectors.overseas_rss_news import OverseasRssNewsCollector  # noqa: E402


rss_module.feedparser = None


class FakeResponse:
    def __init__(self, status_code: int = 200, content: bytes | str = b"", headers: dict[str, str] | None = None):
        self.status_code = status_code
        self.content = content.encode("utf-8") if isinstance(content, str) else content
        self.headers = headers or {"Content-Type": "application/rss+xml"}


class FakeGet:
    def __init__(self, responses: dict[str, FakeResponse | Exception]):
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def __call__(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        response = self.responses.get(url, FakeResponse(404, b""))
        if isinstance(response, Exception):
            raise response
        return response


def rss_feed(*items: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Fixture Feed</title>{''.join(items)}</channel></rss>"""


def rss_item(
    *,
    title: str = "Modular construction housing project opens",
    link: str = "https://news.example.org/article?utm_source=x#frag",
    pub_date: str = "Fri, 03 Jul 2026 00:00:00 GMT",
    description: str = "A modular construction article.",
    source: str = "Fixture Publisher",
) -> str:
    return f"""
<item>
  <title>{title}</title>
  <link>{link}</link>
  <pubDate>{pub_date}</pubDate>
  <description>{description}</description>
  <source>{source}</source>
  <content>full body must not be stored</content>
</item>"""


def atom_feed(*entries: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom Fixture</title>{''.join(entries)}</feed>"""


def atom_entry(
    *,
    title: str = "Volumetric modular hotel opens",
    link: str = "https://atom.example.org/a",
    updated: str = "2026-07-03T00:00:00Z",
    summary: str = "Hotel delivered with volumetric modular construction.",
) -> str:
    return f"""
<entry>
  <title>{title}</title>
  <link href="{link}" />
  <updated>{updated}</updated>
  <summary>{summary}</summary>
  <author><name>Atom Author</name></author>
</entry>"""


def collector_for(responses: dict[str, FakeResponse | Exception], feeds: list[dict[str, str]] | None = None) -> tuple[OverseasRssNewsCollector, FakeGet]:
    fake_get = FakeGet(responses)
    collector = OverseasRssNewsCollector(
        feeds=feeds or [{"name": "Fixture", "url": "https://feed.example.org/rss"}],
        requests_get=fake_get,
        today=date(2026, 7, 3),
    )
    return collector, fake_get


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_rss_2_parsing() -> None:
    collector, fake_get = collector_for({"https://feed.example.org/rss": FakeResponse(content=rss_feed(rss_item()))})
    items = collector.collect()
    assert_true(len(items) == 1, "RSS item must be collected")
    assert_true(items[0]["url"] == "https://news.example.org/article", "RSS URL must be normalized")
    assert_true("full body" not in str(items[0].get("raw")), "full article body must not be stored")
    assert_true(len(fake_get.calls) == 1 and collector.request_count == 1, "one feed request expected")


def test_atom_parsing() -> None:
    collector, _ = collector_for({"https://feed.example.org/rss": FakeResponse(content=atom_feed(atom_entry()))})
    items = collector.collect()
    assert_true(len(items) == 1, "Atom entry must be collected")
    assert_true(items[0]["organization"] == "Fixture", "Atom item should fall back to feed source")


def test_empty_feed_success() -> None:
    collector, _ = collector_for({"https://feed.example.org/rss": FakeResponse(content=rss_feed())})
    assert_true(collector.collect() == [], "empty feed should be successful empty result")
    assert_true(collector.stats["successful_feed_count"] == 1, "empty feed counts as successful feed")


def test_feed_http_errors_and_timeout() -> None:
    for status in (404, 429, 500):
        collector, _ = collector_for({"https://feed.example.org/rss": FakeResponse(status_code=status, content=b"")})
        try:
            collector.collect()
        except RuntimeError as exc:
            assert_true(f"feed_http_{status}" in str(exc), f"HTTP {status} must be recorded")
        else:
            raise AssertionError(f"HTTP {status} must fail when all feeds fail")
        assert_true(collector.request_count == 1, "HTTP failure must not retry")

    collector, _ = collector_for({"https://feed.example.org/rss": requests.Timeout("slow")})
    try:
        collector.collect()
    except RuntimeError as exc:
        assert_true("feed_timeout" in str(exc), "timeout must be recorded")
    else:
        raise AssertionError("timeout must fail when all feeds fail")
    assert_true(collector.request_count == 1, "timeout must not retry")


def test_xml_parse_error() -> None:
    collector, _ = collector_for({"https://feed.example.org/rss": FakeResponse(content="<rss><broken>")})
    try:
        collector.collect()
    except RuntimeError as exc:
        assert_true("feed_parse_error" in str(exc), "parse error must be recorded")
    else:
        raise AssertionError("bad XML must fail when all feeds fail")


def test_partial_feed_failure_continues() -> None:
    feeds = [
        {"name": "Bad", "url": "https://bad.example.org/rss"},
        {"name": "Good", "url": "https://good.example.org/rss"},
    ]
    collector, fake_get = collector_for(
        {
            "https://bad.example.org/rss": FakeResponse(status_code=500, content=b""),
            "https://good.example.org/rss": FakeResponse(content=rss_feed(rss_item(link="https://good.example.org/a"))),
        },
        feeds,
    )
    items = collector.collect()
    assert_true(len(items) == 1, "successful feed must still return items")
    assert_true(collector.stats["successful_feed_count"] == 1, "one successful feed expected")
    assert_true(collector.stats["failed_feed_count"] == 1, "one failed feed expected")
    assert_true(len(fake_get.calls) == 2, "one request per feed expected")


def test_relevance_and_exclusions() -> None:
    cases = [
        ("Modular construction homes open", "x", 1),
        ("Prefab residential project advances", "x", 1),
        ("Industry update", "A modular construction project opens", 1),
        ("Software module update", "x", 0),
        ("Army modular open systems update", "x", 0),
        ("Military modular bridge deployed", "x", 0),
        ("Small modular reactor advances", "x", 0),
    ]
    for index, (title, summary, expected) in enumerate(cases):
        item = rss_item(title=title, description=summary, link=f"https://news.example.org/{index}")
        collector, _ = collector_for({"https://feed.example.org/rss": FakeResponse(content=rss_feed(item))})
        assert_true(len(collector.collect()) == expected, f"unexpected relevance result for {title}")


def test_date_handling() -> None:
    old = rss_item(title="Modular construction housing opens", pub_date="Fri, 01 May 2026 00:00:00 GMT")
    invalid_strong = rss_item(title="Modular construction hotel opens", pub_date="not a date", link="https://news.example.org/strong")
    invalid_weak = rss_item(title="Prefab residential project advances", pub_date="not a date", link="https://news.example.org/weak")
    collector, _ = collector_for({"https://feed.example.org/rss": FakeResponse(content=rss_feed(old, invalid_strong, invalid_weak))})
    items = collector.collect()
    assert_true(len(items) == 1, "old and weak undated items should be excluded")
    assert_true(items[0]["url"] == "https://news.example.org/strong", "strong undated item may pass")
    assert_true(collector.stats["date_excluded_count"] == 2, "date exclusion count mismatch")


def test_duplicates() -> None:
    items_xml = [
        rss_item(link="https://news.example.org/a?utm_medium=x#one"),
        rss_item(link="https://news.example.org/a#two"),
        rss_item(title="Modular housing project opens", link="https://news.example.org/b", source="Same Source"),
        rss_item(title="Modular housing project opens", link="https://news.example.org/c", source="Same Source"),
    ]
    collector, _ = collector_for({"https://feed.example.org/rss": FakeResponse(content=rss_feed(*items_xml))})
    items = collector.collect()
    assert_true(len(items) == 2, "URL and title/date/source duplicates must be removed")
    assert_true(collector.stats["duplicate_excluded_count"] == 2, "duplicate count mismatch")


def test_html_response_rejected() -> None:
    collector, _ = collector_for(
        {"https://feed.example.org/rss": FakeResponse(content="<html>not feed</html>", headers={"Content-Type": "text/html"})}
    )
    try:
        collector.collect()
    except RuntimeError as exc:
        assert_true("feed_html_response" in str(exc), "HTML response must be rejected")
    else:
        raise AssertionError("HTML response must fail when all feeds fail")


def main() -> int:
    tests = [
        test_rss_2_parsing,
        test_atom_parsing,
        test_empty_feed_success,
        test_feed_http_errors_and_timeout,
        test_xml_parse_error,
        test_partial_feed_failure_continues,
        test_relevance_and_exclusions,
        test_date_handling,
        test_duplicates,
        test_html_response_rejected,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("OVERSEAS RSS NEWS COLLECTOR TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
