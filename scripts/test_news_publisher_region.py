from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.news_publisher_region import apply_publisher_region_fields, publisher_region_fields  # noqa: E402

OVERSEAS_RSS_SOURCE = "해외 모듈러 RSS"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def item(**overrides):
    base = {
        "id": 1,
        "source": "Naver News",
        "media": "news.sbs.co.kr",
        "title": "Public agency expands modular housing supply",
        "published_at": "2026-07-11",
        "original_url": "https://news.sbs.co.kr/news/endPage.do?news_id=N100",
        "relevance_score": 90,
        "relevance_level": "direct",
    }
    base.update(overrides)
    return base


def test_naver_domestic_url() -> None:
    fields = publisher_region_fields(item())
    require(fields["collection_pipeline"] == "domestic_pipeline", "Naver item must be domestic collection pipeline")
    require(fields["publisher_region"] == "domestic", "SBS URL must be domestic publisher")
    require(fields["publisher_domain"] == "news.sbs.co.kr", "direct SBS domain must be retained")


def test_rss_overseas_url() -> None:
    fields = publisher_region_fields(
        item(
            source=OVERSEAS_RSS_SOURCE,
            media="Assembly Magazine",
            original_url="https://www.assemblymag.com/articles/modular-building-factory",
        )
    )
    require(fields["collection_pipeline"] == "rss_overseas_pipeline", "RSS item must keep RSS collection pipeline")
    require(fields["publisher_region"] == "overseas", "Assembly Magazine must be overseas")


def test_rss_domestic_publisher() -> None:
    fields = publisher_region_fields(
        item(
            source=OVERSEAS_RSS_SOURCE,
            media="news.sbs.co.kr",
            title="Land Minister Pledges Faster Supply - news.sbs.co.kr",
            original_url="https://news.google.com/rss/articles/fixture?oc=5",
        )
    )
    require(fields["collection_pipeline"] == "rss_overseas_pipeline", "RSS pipeline must remain separate")
    require(fields["publisher_region"] == "domestic", "RSS-sourced SBS article must be domestic publisher")
    require(fields["publisher_domain"] == "news.sbs.co.kr", "Google News must not become publisher domain")
    require("news.google.com" not in fields["publisher_domain"], "intermediary domain must not be publisher domain")


def test_google_news_unknown() -> None:
    fields = publisher_region_fields(
        item(
            source=OVERSEAS_RSS_SOURCE,
            media="Unmapped Publisher",
            title="Modular housing project - Unmapped Publisher",
            original_url="https://news.google.com/rss/articles/unknown?oc=5",
        )
    )
    require(fields["publisher_region"] == "unknown", "unmapped Google News item must stay unknown")
    require(fields["publisher_domain"] == "", "Google News intermediary domain must be blank")


def test_apply_preserves_identity_and_score() -> None:
    original = item(id=77, relevance_score=88, relevance_level="direct")
    enriched = apply_publisher_region_fields(original)
    require(enriched["id"] == 77, "ID must be preserved")
    require(enriched["relevance_score"] == 88, "score must be preserved")
    require(enriched["relevance_level"] == "direct", "relevance level must be preserved")


def test_region_config_utf8() -> None:
    text = (ROOT / "config" / "news_publisher_regions.json").read_text(encoding="utf-8")
    payload = json.loads(text)
    replacement = "\ufffd"
    require(replacement not in text, "publisher region config must not contain replacement characters")
    require(payload["publishers"].get("아시아경제") == "domestic", "Asia Economy mapping must use valid UTF-8")
    require(payload["publishers"].get("연합뉴스") == "domestic", "Yonhap mapping must use valid UTF-8")


def main() -> int:
    tests = [
        test_naver_domestic_url,
        test_rss_overseas_url,
        test_rss_domestic_publisher,
        test_google_news_unknown,
        test_apply_preserves_identity_and_score,
        test_region_config_utf8,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("NEWS PUBLISHER REGION TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
