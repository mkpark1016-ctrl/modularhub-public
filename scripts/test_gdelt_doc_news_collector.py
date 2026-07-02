from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import requests


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collectors.gdelt_doc_news import (  # noqa: E402
    GdeltDocNewsCollector,
    calculate_gdelt_doc_relevance,
    canonicalize_url,
    parse_gdelt_date,
)


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        payload: Any = None,
        text: str = "",
        json_error: Exception | None = None,
        headers: dict[str, str] | None = None,
    ):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"articles": []}
        self.text = text
        self._json_error = json_error
        self.headers = headers or {}

    def json(self) -> Any:
        if self._json_error:
            raise self._json_error
        return self._payload


class FakeGet:
    def __init__(self, response: FakeResponse | None = None, exc: Exception | None = None):
        self.response = response or FakeResponse()
        self.exc = exc
        self.calls: list[dict[str, Any]] = []

    def __call__(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if self.exc:
            raise self.exc
        return self.response


def article(**overrides: Any) -> dict[str, Any]:
    data = {
        "url": "https://news.example.org/path/modular?utm_source=x#frag",
        "url_mobile": "https://m.news.example.org/path/modular",
        "title": "Modular construction project opens for new housing",
        "seendate": "20211215083000",
        "domain": "news.example.org",
        "language": "English",
        "sourcecountry": "US",
        "socialimage": "https://img.example.org/1.jpg",
        "snippet": "A modular construction housing project opened.",
        "body": "this must not be stored",
    }
    data.update(overrides)
    return data


def collect_with(payload: Any, **kwargs: Any) -> tuple[list[dict], GdeltDocNewsCollector, FakeGet]:
    fake_get = FakeGet(FakeResponse(payload=payload))
    collector = GdeltDocNewsCollector(requests_get=fake_get, **kwargs)
    return collector.collect(), collector, fake_get


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_normal_article_list_parsing() -> None:
    items, collector, fake_get = collect_with({"articles": [article()]})
    assert_true(len(items) == 1, "expected one collected article")
    assert_true(collector.request_count == 1, "collector must make exactly one request")
    call = fake_get.calls[0]
    assert_true(call["params"]["mode"] == "artlist", "mode must be artlist")
    assert_true(call["params"]["format"] == "json", "format must be json")
    assert_true(call["params"]["maxrecords"] == 250, "default maxrecords must be 250")
    item = items[0]
    for key in ("source_type", "source_name", "category", "title", "organization", "posted_at", "url", "summary"):
        assert_true(key in item, f"missing raw item field: {key}")
    assert_true(item["source_type"] == "news", "source_type must be news")
    assert_true(item["source_name"] == "GDELT 해외뉴스", "source_name mismatch")
    assert_true(item["posted_at"] == "2021-12-15", "seendate must parse to date")
    assert_true("utm_source" not in item["url"] and "#" not in item["url"], "tracking and fragment must be removed")
    assert_true("body" not in item["raw"], "article body must not be stored in raw metadata")


def test_empty_articles_success() -> None:
    items, collector, _ = collect_with({"articles": []})
    assert_true(items == [], "empty articles must be a successful empty result")
    assert_true(collector.stats["article_count"] == 0, "article_count must be 0")


def test_root_shape_errors() -> None:
    for payload in ({}, {"articles": "bad"}, []):
        fake_get = FakeGet(FakeResponse(payload=payload))
        collector = GdeltDocNewsCollector(requests_get=fake_get)
        try:
            collector.collect()
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"expected root shape error for {payload!r}")


def test_http_and_request_errors() -> None:
    for status in (403, 429, 500):
        fake_get = FakeGet(FakeResponse(status_code=status, payload={"articles": []}))
        collector = GdeltDocNewsCollector(requests_get=fake_get)
        try:
            collector.collect()
        except RuntimeError as exc:
            assert_true(str(status) in str(exc), f"HTTP {status} must be reported")
        else:
            raise AssertionError(f"HTTP {status} must fail")
        assert_true(collector.request_count == 1, "failed HTTP request must still count as one request")

    fake_get = FakeGet(exc=requests.Timeout("slow"))
    collector = GdeltDocNewsCollector(requests_get=fake_get)
    try:
        collector.collect()
    except RuntimeError as exc:
        assert_true("timeout" in str(exc).lower(), "timeout must be reported")
    else:
        raise AssertionError("timeout must fail")
    assert_true(collector.request_count == 1, "timeout attempt must count as one request")


def test_429_rate_limit_contract() -> None:
    fake_get = FakeGet(FakeResponse(status_code=429, payload={"articles": []}, headers={"Retry-After": "3600"}))
    collector = GdeltDocNewsCollector(requests_get=fake_get)
    try:
        collector.collect()
    except RuntimeError as exc:
        text = str(exc)
        assert_true("gdelt_doc_rate_limited" in text, "429 must include explicit rate limit error code")
        assert_true("HTTP 429" in text, "429 must include HTTP status")
        assert_true("Retry-After=3600" in text, "429 must include Retry-After when present")
        assert_true("Authorization" not in text and "Cookie" not in text and "Secret" not in text, "error must not expose secrets")
    else:
        raise AssertionError("HTTP 429 must fail")
    assert_true(collector.request_count == 1, "429 must not be retried")
    assert_true(len(fake_get.calls) == 1, "429 must not fallback to another request")

    fake_get = FakeGet(FakeResponse(status_code=429, payload={"articles": []}))
    collector = GdeltDocNewsCollector(requests_get=fake_get)
    try:
        collector.collect()
    except RuntimeError as exc:
        assert_true("Retry-After=unknown" in str(exc), "missing Retry-After must be reported as unknown")
    else:
        raise AssertionError("HTTP 429 without Retry-After must fail")
    assert_true(collector.request_count == 1, "429 without Retry-After must not be retried")


def test_json_parse_error() -> None:
    fake_get = FakeGet(FakeResponse(json_error=ValueError("bad json"), text="<html>not json</html>"))
    collector = GdeltDocNewsCollector(requests_get=fake_get)
    try:
        collector.collect()
    except RuntimeError as exc:
        assert_true("JSON parse failed" in str(exc), "JSON parse failure must be explicit")
    else:
        raise AssertionError("bad JSON must fail")


def test_maxrecords_clamped() -> None:
    _, _, fake_get = collect_with({"articles": []}, max_records=999)
    assert_true(fake_get.calls[0]["params"]["maxrecords"] == 250, "maxrecords must be clamped to 250")


def test_relevance_rules() -> None:
    strong, _ = calculate_gdelt_doc_relevance("Volumetric modular hotel opens downtown")
    weak, _ = calculate_gdelt_doc_relevance("Prefab residential project advances")
    software, _ = calculate_gdelt_doc_relevance("New modular software component released")
    open_systems, _ = calculate_gdelt_doc_relevance("Army modular open systems architecture update")
    bridge, _ = calculate_gdelt_doc_relevance("Military modular bridge deployed")
    reactor, _ = calculate_gdelt_doc_relevance("Small modular reactor licensing update")
    assert_true(strong >= 90, "strong phrase must pass")
    assert_true(weak >= 80, "weak modular term with construction context must pass")
    assert_true(software == 0, "software module context must be excluded")
    assert_true(open_systems == 0, "modular open systems must be excluded")
    assert_true(bridge == 0, "modular bridge must be excluded")
    assert_true(reactor == 0, "small modular reactor must be excluded")


def test_language_filter_and_missing_language() -> None:
    items, collector, _ = collect_with(
        {
            "articles": [
                article(url="https://news.example.org/en", title="Modular construction housing opens", language="English"),
                article(url="https://news.example.org/fr", title="Modular construction hotel opens", language="French"),
                article(url="https://news.example.org/missing", title="Modular construction school opens", language=""),
            ]
        }
    )
    assert_true(len(items) == 2, "English and missing-language articles may pass")
    assert_true(collector.stats["language_excluded_count"] == 1, "one non-English article must be excluded")


def test_url_normalization_and_duplicates() -> None:
    assert_true(
        canonicalize_url("HTTPS://News.Example.Org:443/a/%7Eitem/?utm_medium=x&b=2&a=1#frag")
        == "https://news.example.org/a/~item?a=1&b=2",
        "canonical URL normalization failed",
    )
    items, collector, _ = collect_with(
        {
            "articles": [
                article(url="https://news.example.org/a?utm_source=x#one"),
                article(url="https://news.example.org/a#two"),
                article(url="https://news.example.org/b", title="Modular housing project opens", seendate="20211215"),
                article(url="https://news.example.org/c", title="Modular housing project opens", seendate="20211215000000"),
            ]
        }
    )
    assert_true(len(items) == 2, "same URL and same title/date/domain duplicates must be removed")
    assert_true(collector.stats["duplicate_excluded_count"] == 2, "duplicate count mismatch")


def test_date_parse_failure_does_not_drop_article() -> None:
    items, _, _ = collect_with({"articles": [article(seendate="not-a-date")]})
    assert_true(len(items) == 1, "date parse failure must not drop relevant article")
    assert_true(items[0]["posted_at"] is None, "invalid date should become None")
    assert_true(parse_gdelt_date("2021-12-14T13:18:01Z").isoformat() == "2021-12-14", "ISO date must parse")


def test_min_relevance_score() -> None:
    items, _, _ = collect_with(
        {"articles": [article(title="Prefab residential project advances")]},
        min_relevance_score=85,
    )
    assert_true(items == [], "candidate below configured relevance threshold must be excluded")


def main() -> int:
    tests = [
        test_normal_article_list_parsing,
        test_empty_articles_success,
        test_root_shape_errors,
        test_http_and_request_errors,
        test_429_rate_limit_contract,
        test_json_parse_error,
        test_maxrecords_clamped,
        test_relevance_rules,
        test_language_filter_and_missing_language,
        test_url_normalization_and_duplicates,
        test_date_parse_failure_does_not_drop_article,
        test_min_relevance_score,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("GDELT DOC NEWS COLLECTOR TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
