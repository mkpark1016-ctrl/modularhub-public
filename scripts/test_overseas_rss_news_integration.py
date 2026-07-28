from __future__ import annotations

import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import export_public_json  # noqa: E402
from scripts import collect_all  # noqa: E402
from scripts.test_overseas_rss_news_collector import FakeGet, FakeResponse, rss_feed, rss_item  # noqa: E402
from src.collectors import OverseasRssNewsCollector, __all__  # noqa: E402
from src.config import DEFAULT_OVERSEAS_RSS_NEWS_FEEDS  # noqa: E402
from src.database import init_db, upsert_item  # noqa: E402
from src.models import Item  # noqa: E402
from src.normalizer import normalize_item  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_collector_exported_in_all() -> None:
    assert_true("OverseasRssNewsCollector" in __all__, "RSS collector must be exported")


def test_collect_all_registration_contract() -> None:
    text = (ROOT / "scripts" / "collect_all.py").read_text(encoding="utf-8")
    assert_true("OverseasRssNewsCollector" in text, "collect_all must reference RSS collector")
    assert_true("OVERSEAS_RSS_NEWS_ENABLED" in text, "collect_all must gate RSS collector")
    assert_true("GDELT_DOC_NEWS_ENABLED" in text, "GDELT collector gate must remain")
    config_text = (ROOT / "src" / "config.py").read_text(encoding="utf-8")
    assert_true('GDELT_DOC_NEWS_ENABLED = _env_bool("GDELT_DOC_NEWS_ENABLED", False)' in config_text, "GDELT DOC default must be false")
    assert_true('OVERSEAS_RSS_NEWS_ENABLED = _env_bool("OVERSEAS_RSS_NEWS_ENABLED", True)' in config_text, "RSS default must be true")


def test_default_feeds_are_configured_once() -> None:
    urls = [feed["url"] for feed in DEFAULT_OVERSEAS_RSS_NEWS_FEEDS]
    assert_true(len(DEFAULT_OVERSEAS_RSS_NEWS_FEEDS) >= 11, "expanded overseas RSS feed set must be configured")
    assert_true(len(urls) == len(set(urls)), "default overseas RSS feed URLs must be unique")
    assert_true(
        any("Google News" in feed["name"] for feed in DEFAULT_OVERSEAS_RSS_NEWS_FEEDS),
        "Google News RSS feed must be present",
    )
    assert_true(
        any(feed["name"] == "Google News modular housing US" for feed in DEFAULT_OVERSEAS_RSS_NEWS_FEEDS),
        "modular housing regional Google News feed must be present",
    )
    assert_true(
        any(feed["name"] == "Google News offsite construction UK" for feed in DEFAULT_OVERSEAS_RSS_NEWS_FEEDS),
        "offsite construction regional Google News feed must be present",
    )


def test_update_public_data_workflow_overseas_news_settings() -> None:
    workflow = (ROOT / ".github" / "workflows" / "update-public-data.yml").read_text(encoding="utf-8")
    assert_true("GDELT_DOC_NEWS_ENABLED=true" in workflow, "public data workflow must enable GDELT DOC collection")
    assert_true("GDELT_DOC_NEWS_TIMESPAN=14d" in workflow, "GDELT DOC lookback must be configured")
    assert_true("GDELT_DOC_NEWS_MIN_RELEVANCE_SCORE=65" in workflow, "GDELT DOC relevance threshold must be configured")
    assert_true("OVERSEAS_RSS_NEWS_LOOKBACK_DAYS=30" in workflow, "overseas RSS lookback must be expanded to 30 days")
    assert_true("OVERSEAS_RSS_NEWS_MIN_RELEVANCE_SCORE=65" in workflow, "overseas RSS relevance threshold must be configured")
    assert_true("news-collection-diagnostics" in workflow, "news diagnostics artifact upload must be configured")


def test_normalize_item_and_model() -> None:
    collector = OverseasRssNewsCollector(
        feeds=[{"name": "Fixture", "url": "https://feed.example.org/rss"}],
        requests_get=FakeGet({"https://feed.example.org/rss": FakeResponse(content=rss_feed(rss_item()))}),
        today=date(2026, 7, 3),
    )
    raw = collector.collect()[0]
    normalized = normalize_item(raw)
    item = Item(**normalized)
    assert_true(item.source_type == "news", "normalized RSS item must be news")
    assert_true(item.source_name == "해외 모듈러 RSS", "source name mismatch")
    assert_true(item.original_url == raw["original_url"], "original URL must be preserved")
    assert_true(item.source_portal_name == "Fixture", "feed source portal must be preserved")
    assert_true(bool(item.unique_hash), "unique hash must be generated")


def test_temp_db_upsert_deduplicates() -> None:
    collector = OverseasRssNewsCollector(
        feeds=[{"name": "Fixture", "url": "https://feed.example.org/rss"}],
        requests_get=FakeGet({"https://feed.example.org/rss": FakeResponse(content=rss_feed(rss_item()))}),
        today=date(2026, 7, 3),
    )
    item = Item(**normalize_item(collector.collect()[0]))
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "rss-test.db"
        init_db(db_path)
        first = upsert_item(item, db_path)
        second = upsert_item(item, db_path)
        with sqlite3.connect(db_path) as conn:
            count = conn.execute("select count(1) from items").fetchone()[0]
    assert_true(first == "inserted", "first upsert must insert")
    assert_true(second == "skipped", "second upsert must skip duplicate")
    assert_true(count == 1, "duplicate insert must not create a second row")


def test_export_filter_includes_rss_news() -> None:
    assert_true(
        export_public_json.contains_modular("Offsite construction factory opens", "RSS", "offsite construction"),
        "public export filter must recognize RSS overseas terms",
    )


def test_news_collection_diagnostics_are_safe() -> None:
    class CollectorWithStats:
        stats = {
            "returned_count": 2,
            "request_headers": {"Authorization": "must-not-appear"},
            "raw_response": {"secret": "must-not-appear"},
        }

    safe_stats = collect_all.safe_collector_stats(CollectorWithStats())
    assert_true("request_headers" not in safe_stats, "request headers must be removed from diagnostics")
    assert_true("raw_response" not in safe_stats, "raw response must be removed from diagnostics")

    results = [
        {
            "collectorName": "해외 모듈러 RSS",
            "sourceType": "news",
            "status": "success",
            "insertedCount": 1,
            "updatedCount": 0,
            "skippedCount": 1,
            "safeErrorCategory": "none",
            "stats": {
                "feed_count": 2,
                "successful_feed_count": 2,
                "failed_feed_count": 0,
                "fetched_item_count": 4,
                "returned_count": 2,
            },
        }
    ]
    previous_dir = collect_all.DIAGNOSTICS_DIR
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        collect_all.DIAGNOSTICS_DIR = Path(tmp)
        try:
            collect_all.write_news_collection_diagnostics(results)
        finally:
            collect_all.DIAGNOSTICS_DIR = previous_dir
        payload = (Path(tmp) / "news-collection-diagnostics.json").read_text(encoding="utf-8")
        assert_true("must-not-appear" not in payload, "diagnostics JSON must not include sensitive internals")
        assert_true('"overseasRss"' in payload, "diagnostics JSON must include overseas RSS section")


def main() -> int:
    tests = [
        test_collector_exported_in_all,
        test_collect_all_registration_contract,
        test_default_feeds_are_configured_once,
        test_update_public_data_workflow_overseas_news_settings,
        test_normalize_item_and_model,
        test_temp_db_upsert_deduplicates,
        test_export_filter_includes_rss_news,
        test_news_collection_diagnostics_are_safe,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("OVERSEAS RSS NEWS INTEGRATION TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
