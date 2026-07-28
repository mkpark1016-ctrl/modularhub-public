from __future__ import annotations

from datetime import datetime, timezone

from analyze_overseas_news_baseline import build_report


FIXED_NOW = datetime(2026, 7, 28, tzinfo=timezone.utc)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def item(
    *,
    source: str,
    title: str,
    url: str,
    published_at: str,
    country: str = "US",
    pipeline: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "source": source,
        "media": source,
        "title": title,
        "summary": "Modular construction fixture.",
        "original_url": url,
        "published_at": published_at,
        "publisher_country_code": country,
    }
    if pipeline:
        payload["collection_pipeline"] = pipeline
    return payload


def test_build_report_counts_overseas_and_dedupe() -> None:
    rows = [
        item(
            source="해외 모듈러 RSS",
            title="Modular housing opens in California",
            url="https://example.com/a?utm_source=rss",
            published_at="2026-07-27T00:00:00+00:00",
            country="US",
        ),
        item(
            source="GDELT 해외뉴스",
            title="Volumetric modular school opens in London",
            url="https://example.com/b",
            published_at="2026-07-20T00:00:00+00:00",
            country="GB",
        ),
        item(
            source="네이버뉴스",
            title="국내 모듈러 뉴스",
            url="https://example.kr/c",
            published_at="2026-07-26",
            country="KR",
        ),
        item(
            source="해외 모듈러 RSS",
            title="Modular housing opens in California",
            url="https://example.com/a#duplicate",
            published_at="2026-07-27T00:00:00+00:00",
            country="US",
        ),
    ]
    report = build_report(rows, now=FIXED_NOW)
    require(report["totalNewsCount"] == 4, "total count mismatch")
    require(report["overseasNewsCount"] == 3, "overseas count must include RSS and GDELT")
    require(report["domesticNewsCount"] == 1, "domestic count mismatch")
    require(report["recent30DayOverseasNewsCount"] == 3, "recent overseas count mismatch")
    require(report["recent30DayOverseasShare"] == 0.75, "recent overseas share mismatch")
    require(report["overseasByCountryOrRegion"]["US"] == 2, "country distribution mismatch")
    require(report["dedupe"]["beforeCount"] == 4, "dedupe before mismatch")
    require(report["dedupe"]["afterCount"] < report["dedupe"]["beforeCount"], "duplicate URL must be removed by public dedupe")


def main() -> int:
    test_build_report_counts_overseas_and_dedupe()
    print("PASS test_build_report_counts_overseas_and_dedupe")
    print("OVERSEAS NEWS BASELINE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
