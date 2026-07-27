from __future__ import annotations

from src.company_source_coverage import public_news_empty_diagnostics


def test_public_news_empty_diagnostics_reports_snapshot_zero_as_valid_empty() -> None:
    diagnostics = public_news_empty_diagnostics(
        {
            "sourceId": "public_news",
            "configured": True,
            "attempted": True,
            "state": "success_empty",
            "rawCount": 0,
            "normalizedCount": 0,
            "latestPublishedAt": "2026-07-27",
        },
        expected_company_ids=["a", "b"],
        generated_at="2026-07-27T00:00:00Z",
    )
    assert diagnostics["sourceType"] == "snapshot"
    assert diagnostics["normalizedState"] == "success_empty_valid"
    assert diagnostics["finalZeroReason"] == "NO_MATCHED_PUBLIC_NEWS_IN_LOOKBACK"
    assert diagnostics["queryCount"] == 0


def test_public_news_empty_diagnostics_distinguishes_not_attempted() -> None:
    diagnostics = public_news_empty_diagnostics(
        {"sourceId": "public_news", "attempted": False, "state": "not_attempted"},
        expected_company_ids=["a"],
        generated_at="2026-07-27T00:00:00Z",
    )
    assert diagnostics["finalZeroReason"] == "PUBLIC_NEWS_SOURCE_NOT_ATTEMPTED"
    assert diagnostics["attempted"] is False
