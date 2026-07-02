from __future__ import annotations

import sys
import tempfile
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import export_public_json  # noqa: E402
import src.collector_runner as collector_runner  # noqa: E402
from src.collectors.base import BaseCollector  # noqa: E402
from src.collectors import GdeltDocNewsCollector, __all__  # noqa: E402
from src.collectors.gdelt_doc_news import GDELT_DOC_NEWS_STRONG_PHRASES  # noqa: E402
from src.database import init_db, upsert_item  # noqa: E402
from src.models import Item  # noqa: E402
from src.normalizer import normalize_item  # noqa: E402

from scripts.test_gdelt_doc_news_collector import FakeResponse, FakeGet, article  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_collector_exported_in_all() -> None:
    assert_true("GdeltDocNewsCollector" in __all__, "collector must be exported from src.collectors")


def test_collect_all_registration_contract() -> None:
    text = (ROOT / "scripts" / "collect_all.py").read_text(encoding="utf-8")
    assert_true("GdeltDocNewsCollector" in text, "collect_all must reference GdeltDocNewsCollector")
    assert_true("GDELT_DOC_NEWS_ENABLED" in text, "collect_all must gate registration with GDELT_DOC_NEWS_ENABLED")
    assert_true("GDELT_DOC_NEWS_ENABLED=false" in text, "collect_all must support disabled state")


def test_api_key_independent_instantiation() -> None:
    collector = GdeltDocNewsCollector(requests_get=FakeGet(FakeResponse(payload={"articles": []})))
    assert_true(collector.get_source_type() == "news", "source_type mismatch")
    assert_true(collector.get_source_name() == "GDELT 해외뉴스", "source_name mismatch")


def test_normalize_item_and_model() -> None:
    fake_get = FakeGet(FakeResponse(payload={"articles": [article()]}))
    collector = GdeltDocNewsCollector(requests_get=fake_get)
    raw = collector.collect()[0]
    normalized = normalize_item(raw)
    item = Item(**normalized)
    assert_true(item.source_type == "news", "normalized item must be news")
    assert_true(item.source_name == "GDELT 해외뉴스", "normalized source_name mismatch")
    assert_true(bool(item.unique_hash), "unique_hash must be generated")
    assert_true(item.original_url == raw["original_url"], "original_url must be preserved")
    assert_true(item.source_portal_name == "GDELT DOC", "source_portal_name must be preserved")


def test_temp_db_upsert_deduplicates() -> None:
    fake_get = FakeGet(FakeResponse(payload={"articles": [article()]}))
    collector = GdeltDocNewsCollector(requests_get=fake_get)
    item = Item(**normalize_item(collector.collect()[0]))
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "gdelt-doc-test.db"
        init_db(db_path)
        first = upsert_item(item, db_path)
        second = upsert_item(item, db_path)
    assert_true(first == "inserted", "first upsert must insert")
    assert_true(second == "skipped", "same article must not insert twice")


def test_export_filter_can_include_english_modular_news() -> None:
    assert_true(
        export_public_json.contains_modular("Modular construction project", "GDELT DOC", "modular construction"),
        "public export modular filter must recognize English GDELT terms",
    )


def test_query_phrases_are_available() -> None:
    assert_true("modular construction" in GDELT_DOC_NEWS_STRONG_PHRASES, "strong phrase config missing")
    assert_true("small modular reactor" not in GDELT_DOC_NEWS_STRONG_PHRASES, "exclude terms must not be query phrases")


class NextCollector(BaseCollector):
    def collect(self) -> list[dict]:
        return [
            {
                "source_type": "news",
                "source_name": "next_collector",
                "title": "Modular construction follow-on fixture",
                "organization": "fixture.example",
                "posted_at": "2026-07-03",
                "url": "https://fixture.example/modular-construction-follow-on",
                "summary": "Follow-on collector fixture",
                "keywords": ["modular construction"],
                "relevance_score": 90,
                "data_quality": "real",
                "original_url": "https://fixture.example/modular-construction-follow-on",
            }
        ]

    def get_source_type(self) -> str:
        return "news"

    def get_source_name(self) -> str:
        return "next_collector"


def test_429_failure_is_non_destructive_and_next_collector_can_run() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "gdelt-doc-failure-test.db"
        init_db(db_path)
        existing = Item(
            **normalize_item(
                {
                    "source_type": "news",
                    "source_name": "existing_fixture",
                    "title": "Existing modular construction fixture",
                    "organization": "existing.example",
                    "posted_at": "2026-07-02",
                    "url": "https://existing.example/modular",
                    "original_url": "https://existing.example/modular",
                    "summary": "Existing fixture must remain",
                    "keywords": ["modular construction"],
                    "relevance_score": 90,
                    "data_quality": "real",
                }
            )
        )
        upsert_item(existing, db_path)

        old_db_path = collector_runner.DB_PATH
        collector_runner.DB_PATH = db_path
        try:
            gdelt = GdeltDocNewsCollector(
                requests_get=FakeGet(
                    FakeResponse(status_code=429, payload={"articles": []}, headers={"Retry-After": "120"})
                )
            )
            failed = collector_runner.run_collector(gdelt)
            continued = collector_runner.run_collector(NextCollector())
        finally:
            collector_runner.DB_PATH = old_db_path

        assert_true(failed.status == "failed", "429 collector result must be failed")
        assert_true("gdelt_doc_rate_limited" in (failed.error_message or ""), "429 failure must keep error code")
        assert_true("Retry-After=120" in (failed.error_message or ""), "429 failure must keep Retry-After")
        assert_true(gdelt.request_count == 1, "429 failure must make one request")
        assert_true(continued.status == "success", "following collector must still run")

        with sqlite3.connect(db_path) as conn:
            item_count = conn.execute("select count(1) from items").fetchone()[0]
            gdelt_rows = conn.execute("select count(1) from items where source_name = ?", ("GDELT 해외뉴스",)).fetchone()[0]
            logs = conn.execute("select collector_name, status, error_message from collect_logs order by id").fetchall()
        assert_true(item_count == 2, "existing item plus next collector item must remain")
        assert_true(gdelt_rows == 0, "429 must not insert GDELT candidates")
        assert_true(logs[0][1] == "failed" and "gdelt_doc_rate_limited" in logs[0][2], "failed log must be recorded")
        assert_true(logs[1][0] == "next_collector" and logs[1][1] == "success", "next collector success log missing")


def main() -> int:
    tests = [
        test_collector_exported_in_all,
        test_collect_all_registration_contract,
        test_api_key_independent_instantiation,
        test_normalize_item_and_model,
        test_temp_db_upsert_deduplicates,
        test_export_filter_can_include_english_modular_news,
        test_query_phrases_are_available,
        test_429_failure_is_non_destructive_and_next_collector_can_run,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("GDELT DOC NEWS INTEGRATION TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
