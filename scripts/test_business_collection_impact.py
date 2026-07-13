#!/usr/bin/env python3
"""Regression tests for business collection impact audit helpers."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_business_collection_impact import (  # noqa: E402
    build_source_matrix,
    classify_source_impact,
    evaluate_fixtures,
    impact_decision,
    known_important_impact,
    procurement_plan_impact,
    source_specs,
    staleness_bucket,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def payload(items: list[dict]) -> dict:
    return {
        "generated_at": "2026-07-13T07:40:40+09:00",
        "previous_business_count": len(items),
        "workflow_last_run_status": "warning",
        "public_data_guard_status": "passed",
        "g2b_order_plan_status": "success",
        "g2b_order_plan_message": "정상 호출",
        "d2b_status": "disabled_stopped",
        "d2b_message": "D2B legacy stopped",
        "lh_contest_status": "success",
        "gh_contest_status": "success",
        "ih_contest_status": "success",
        "sh_contest_status": "not_collected",
        "items": items,
    }


def item(title: str, *, source_type: str, source: str = "나라장터", posted_at: str = "2026-07-13", **extra) -> dict:
    data = {
        "id": extra.pop("id", title),
        "title": title,
        "source": source,
        "source_name": source,
        "source_type": source_type,
        "posted_at": posted_at,
        "opportunity_status": extra.pop("opportunity_status", "active"),
        "external_original_url": extra.pop("external_original_url", "https://example.test/notice"),
    }
    data.update(extra)
    return data


def test_staleness_contract() -> None:
    require(staleness_bucket(None) == "unknown", "missing staleness should be unknown")
    require(staleness_bucket(12) == "current", "12h should be current")
    require(staleness_bucket(36) == "delayed", "36h should be delayed")
    require(staleness_bucket(60) == "stale_warning", "60h should be stale_warning")
    require(staleness_bucket(96) == "stale_source", "96h should be stale_source")


def test_source_matrix_separates_disabled_and_active_sources() -> None:
    data = payload(
        [
            item("제주대학교 의과대학 모듈러 교사 제작·설치 및 임차 용역", source_type="bid"),
            item("이천제일고 공간재구조화 개축 및 리모델링공사 모듈러 교실 임차용역", source_type="procurement_plan"),
            item("성의여자고등학교 임시교사(모듈러교실) 제작·설치 및 임차용역 2단계 입찰 공고", source_type="bid", is_known_important=True),
            item("LH 모듈러 공공주택 공모", source_type="public_agency_contest", source="LH"),
        ]
    )
    rows = build_source_matrix(data, [])
    by_key = {row["source_key"]: row for row in rows}
    require(by_key["d2b_legacy"]["status"] == "DISABLED_KNOWN", "D2B must be disabled known")
    require(by_key["known_important_bid"]["valid_records"] == 1, "known important bid count missing")
    require(by_key["g2b_procurement_plan"]["valid_records"] == 1, "procurement plan count missing")


def test_fixture_presence_and_known_important_impact() -> None:
    data = payload(
        [
            item("제주대학교 의과대학 모듈러 교사 제작·설치 및 임차 용역", source_type="bid"),
            item("부산전자공업고등학교 콘크리트 모듈러 기숙사 제작·설치 구매", source_type="bid"),
            item("이천제일고 공간재구조화 개축 및 리모델링공사 모듈러 교실 임차용역", source_type="procurement_plan"),
            item("성의여자고등학교 임시교사(모듈러교실) 제작·설치 및 임차용역 2단계 입찰 공고", source_type="bid", is_known_important=True),
        ]
    )
    fixtures = evaluate_fixtures(data)
    require(all(row["pass"] for row in fixtures), "expected business fixtures should be present")
    rows = build_source_matrix(data, [])
    require(known_important_impact(rows, fixtures) == "NO_DATA_IMPACT", "known important fixture should have no data impact")


def test_procurement_plan_stale_is_targeted_fix() -> None:
    spec = next(s for s in source_specs() if s.source_key == "g2b_procurement_plan")
    impact = classify_source_impact(
        spec=spec,
        status="success",
        exported_count=10,
        staleness="stale_source",
        consecutive_failure_count=0,
    )
    require(impact == "STALE_SOURCE", "stale procurement plan should be targeted")
    rows = [{"source_key": "g2b_procurement_plan", "status": "STALE_SOURCE", "valid_records": 10, "collector_status": "success"}]
    require(procurement_plan_impact(rows) == "STALE_SOURCE", "procurement impact should remain stale")
    require(impact_decision(rows, live_logs_status="available") == "HOLD_FOR_TARGETED_FIX", "stale source should hold for targeted fix")


def test_no_logs_produces_pending_live_logs_when_no_other_risk() -> None:
    rows = [{"status": "HEALTHY"}, {"status": "DISABLED_KNOWN"}]
    require(impact_decision(rows, live_logs_status="local_db_logs_unavailable") == "PENDING_LIVE_LOGS", "missing live logs should be explicit")


def main() -> int:
    tests = [
        test_staleness_contract,
        test_source_matrix_separates_disabled_and_active_sources,
        test_fixture_presence_and_known_important_impact,
        test_procurement_plan_stale_is_targeted_fix,
        test_no_logs_produces_pending_live_logs_when_no_other_risk,
    ]
    for test in tests:
        test()
    print(f"business collection impact tests passed: {len(tests)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
