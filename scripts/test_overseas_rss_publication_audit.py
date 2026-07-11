from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from audit_overseas_rss_publication import (
    OVERSEAS_RSS_SOURCE,
    audit_file,
    audit_news_items,
)


FIXED_NOW = datetime(2026, 7, 3, tzinfo=timezone.utc)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def rss_item(**overrides):
    item = {
        "id": overrides.pop("id", 1),
        "source": OVERSEAS_RSS_SOURCE,
        "media": overrides.pop("media", "Construction Dive"),
        "title": overrides.pop("title", "Modular construction project opens in Denver"),
        "summary": overrides.pop("summary", "A modular construction project uses factory-built housing methods."),
        "published_at": overrides.pop("published_at", "2026-07-02T09:00:00+00:00"),
        "original_url": overrides.pop("original_url", "https://example-news.test/modular-project?utm_source=rss"),
        "keywords": overrides.pop("keywords", "modular construction"),
        "relevance_score": overrides.pop("relevance_score", 90),
    }
    item.update(overrides)
    return item


def audit(items):
    return audit_news_items(items, now=FIXED_NOW)


def has_code(report, code):
    return any(issue.get("code") == code for issue in report["validation_errors"] + report["warnings"])


def test_normal_and_domestic_scope():
    report = audit([
        rss_item(id=idx, title=f"Modular construction project {idx}", original_url=f"https://example-news.test/modular-project-{idx}")
        for idx in range(1, 6)
    ] + [
        {
            "id": 100,
            "source": "네이버뉴스",
            "media": "domestic.example",
            "title": "software module is not audited here",
            "original_url": "",
            "relevance_score": 0,
        },
    ])
    require(report["audit_status"] == "passed", "valid overseas RSS item should pass")
    require(report["overseas_rss_count"] == 5, "domestic news must be excluded from overseas audit")
    require(report["valid_count"] == 5, "valid overseas count mismatch")


def test_hard_failures():
    cases = [
        ("title_missing", rss_item(id=2, title="")),
        ("invalid_url", rss_item(id=3, original_url="")),
        ("invalid_url", rss_item(id=4, original_url="ftp://example.test/item")),
        ("low_relevance_score", rss_item(id=5, relevance_score=69)),
        ("excluded_context_public", rss_item(id=6, title="Software module architecture update")),
        ("excluded_context_public", rss_item(id=7, title="Modular open systems for aircraft")),
        ("excluded_context_public", rss_item(id=8, title="Army modular bridge procurement")),
        ("excluded_context_public", rss_item(id=9, title="Small modular reactor construction update")),
    ]
    for expected_code, item in cases:
        report = audit([item])
        require(report["audit_status"] == "failed", f"{expected_code} should fail")
        require(has_code(report, expected_code), f"{expected_code} missing from validation errors")


def test_duplicate_failures():
    report = audit([
        rss_item(id=10, original_url="https://publisher.test/a?utm_campaign=x"),
        rss_item(id=11, original_url="https://publisher.test/a#section", title="Modular construction project opens in Austin"),
    ])
    require(report["audit_status"] == "failed", "duplicate URL should fail")
    require(report["duplicate_url_count"] == 1, "duplicate URL count mismatch")

    report = audit([
        rss_item(id=12, title="Modular hotel project opens", published_at="2026-07-02"),
        rss_item(id=13, title="Modular hotel project opens!", published_at="2026-07-02", original_url="https://publisher.test/other"),
    ])
    require(report["audit_status"] == "failed", "duplicate title/date should fail")
    require(report["duplicate_title_date_count"] == 1, "duplicate title/date count mismatch")


def test_warnings():
    report = audit([rss_item(id=20, media="")])
    require(report["audit_status"] == "passed_with_warnings", "missing media should warn")
    require(has_code(report, "media_missing"), "media warning missing")

    report = audit([rss_item(id=21, published_at="")])
    require(report["audit_status"] == "passed_with_warnings", "missing date should warn")
    require(has_code(report, "published_at_missing"), "date missing warning absent")

    report = audit([rss_item(id=22, published_at="not-a-date")])
    require(report["audit_status"] == "passed_with_warnings", "invalid date should warn")
    require(has_code(report, "published_at_invalid"), "date invalid warning absent")

    report = audit([{"id": 23, "source": "네이버뉴스", "title": "국내뉴스"}])
    require(report["audit_status"] == "passed_with_warnings", "zero overseas RSS items should warn")
    require(has_code(report, "overseas_rss_empty"), "zero overseas warning absent")


def test_google_news_url_allowed_as_information():
    report = audit([
        rss_item(
            id=30 + idx,
            original_url=f"https://news.google.com/rss/articles/CBMi{idx}?hl=en-US&gl=US&ceid=US:en",
            title=f"Modular housing development approved {idx}",
        )
        for idx in range(6)
    ])
    require(report["audit_status"] == "passed", "Google News RSS URL alone should not warn")
    require(not has_code(report, "google_news_rss_url"), "Google News URL must not be a warning")
    require(report["warning_count"] == 0, "Google News URL must not increase warning count")
    require(report["google_news_rss_url_count"] == 6, "Google News URL count mismatch")
    require(report["google_news_rss_url_policy"] == "allowed_intermediary_url", "Google News policy mismatch")
    require(len(report["google_news_rss_url_sample"]) == 5, "Google News sample must be capped at 5")
    require(report["invalid_url_count"] == 0, "Google News URL must not be invalid")


def test_unified_v2_score_contract():
    report = audit([
        rss_item(id=40, relevance_score=55, relevance_score_version="unified-v2", relevance_level="adjacent")
    ])
    require(report["audit_status"] == "passed_with_warnings", "unified-v2 score below legacy 70 should not be a hard failure")
    require(report["low_relevance_count"] == 0, "unified-v2 scores must not use the legacy low relevance threshold")
    require(report["score_range_violation_count"] == 0, "valid unified-v2 score must be in range")

    report = audit([
        rss_item(id=41, relevance_score=101, relevance_score_version="unified-v2", relevance_level="direct")
    ])
    require(report["audit_status"] == "failed", "score above 100 must fail")
    require(has_code(report, "score_range_violation"), "score range violation missing")

    report = audit([
        rss_item(id=42, relevance_score=55, relevance_score_version="unified-v2", relevance_level="")
    ])
    require(report["audit_status"] == "failed", "unified-v2 missing relevance_level must fail")
    require(has_code(report, "relevance_level_missing"), "relevance level error missing")


def test_output_files_are_written():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        input_path = root / "news.json"
        output_dir = root / "audit"
        input_path.write_text(
            json.dumps(
                {
                    "items": [
                        rss_item(id=idx, title=f"Modular construction project {idx}", original_url=f"https://example-news.test/modular-project-{idx}")
                        for idx in range(1, 6)
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        report = audit_file(input_path, output_dir)
        require(report["audit_status"] == "passed", "fixture audit should pass")
        require((output_dir / "overseas_rss_audit.json").exists(), "audit JSON not written")
        require((output_dir / "overseas_rss_audit.md").exists(), "audit markdown not written")
        parsed = json.loads((output_dir / "overseas_rss_audit.json").read_text(encoding="utf-8"))
        require(parsed["overseas_rss_count"] == 5, "audit JSON content mismatch")
        markdown = (output_dir / "overseas_rss_audit.md").read_text(encoding="utf-8")
        require("## Information" in markdown, "information section missing")
        require("Google News RSS intermediary URL count" in markdown, "Google News info metric missing")
        require("## Warnings" in markdown and "- None" in markdown, "empty warnings section should say None")


def main():
    tests = [
        test_normal_and_domestic_scope,
        test_hard_failures,
        test_duplicate_failures,
        test_warnings,
        test_google_news_url_allowed_as_information,
        test_unified_v2_score_contract,
        test_output_files_are_written,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("OVERSEAS RSS PUBLICATION AUDIT TESTS PASSED")


if __name__ == "__main__":
    main()
