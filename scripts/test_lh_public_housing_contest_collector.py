from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.collectors.public_housing_contests.lh import (  # noqa: E402
    BOARD_URL,
    LHCollectStats,
    LHContestRecord,
    apply_records,
    canonical_attachments,
    extract_lh_list_items,
    extract_page_title,
    extract_sites_and_blocks,
    html_to_text,
    verify_lh_detail_url,
)
from src.public_housing_contest_classifier import (  # noqa: E402
    classify_modular_relevance,
    classify_notice_stage,
    is_business_opportunity_stage,
    validate_exact_detail_url,
)


FIXTURE_DIR = ROOT / "tests" / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def build_record() -> LHContestRecord:
    return LHContestRecord(
        source_code="LH_CONTEST",
        source_name="LH",
        organization="한국토지주택공사",
        source_type="public_agency_contest",
        business_type="private_participation_public_housing",
        display_type="민간사업자 공모",
        source_record_id="732612",
        title="2026년 제3차 민간참여 공공주택건설사업 민간사업자 공모",
        normalized_title="민간참여 공공주택건설사업 민간사업자 공모",
        posted_at="2026-06-01",
        deadline_at="2026-08-20",
        application_schedule_text="사업신청서 제출 마감은 2026.08.20입니다.",
        estimated_cost=None,
        household_count=None,
        housing_type=None,
        project_name="민간참여 공공주택건설사업 민간사업자 공모",
        project_sites=["인천검단"],
        project_blocks=["AA-1BL"],
        body_summary="한국토지주택공사는 공공주택건설사업 민간사업자 공모를 시행합니다.",
        original_url="https://www.lh.or.kr/board.es?mid=a10601020000&bid=0034&act=view&list_no=732612",
        board_url=BOARD_URL,
        attachments=[
            {
                "name": "공모공고문.pdf",
                "file_type": "pdf",
                "url": "https://www.lh.or.kr/boardDownload.es?bid=0034&list_no=732612&seq=1",
            }
        ],
        status="ok",
        notice_stage="main_notice",
        modular_relevance="review_candidate",
        modular_relevance_score=3,
        modular_evidence=["민간참여 공공주택 공모"],
        collected_at="2026-06-20T07:00:00+09:00",
        fingerprint="fixture",
        related_group_key="한국토지주택공사|민간참여 공공주택건설사업 민간사업자 공모|인천검단|AA-1BL",
        exact_link_verified=True,
        link_validation_reason="verified",
    )


def test_offline_parser() -> None:
    list_html = read_fixture("lh_contest_list.html")
    detail_html = read_fixture("lh_contest_detail.html")
    list_items = extract_lh_list_items(list_html, "https://www.lh.or.kr/board.es?mid=a10601020000&bid=0034")
    assert len(list_items) == 2, list_items
    assert list_items[0]["source_record_id"] == "732612"
    assert "list_no=732612" in list_items[0]["href"]

    body = html_to_text(detail_html)
    title = extract_page_title(detail_html)
    assert "민간참여 공공주택건설사업" in title
    assert "민간사업자 공모" in body

    attachments = canonical_attachments(
        [
            {"file_name": "공모공고문.pdf", "url": "/boardDownload.es?bid=0034&list_no=732612&seq=1"},
            {"file_name": "지침서.hwpx", "url": "/boardDownload.es?bid=0034&list_no=732612&seq=2"},
        ],
        "https://www.lh.or.kr/board.es?mid=a10601020000&bid=0034&act=view&list_no=732612",
        ["www.lh.or.kr", "lh.or.kr"],
    )
    assert len(attachments) == 2
    assert attachments[0]["file_type"] == "pdf"
    assert attachments[1]["file_type"] == "hwpx"

    sites, blocks = extract_sites_and_blocks(title, body)
    assert "AA-1BL" in blocks

    verified, reason = verify_lh_detail_url(
        url="https://www.lh.or.kr/board.es?mid=a10601020000&bid=0034&act=view&list_no=732612",
        allowed_domains=["www.lh.or.kr", "lh.or.kr"],
        source_record_id="732612",
        expected_title=title,
        status_code=200,
        detail_title=title,
        body=body,
    )
    assert verified, reason


def test_classification_rules() -> None:
    assert classify_notice_stage("민간참여 공공주택건설사업 민간사업자 공모") == "main_notice"
    assert classify_notice_stage("민간참여 공공주택건설사업 민간사업자 재공모") == "re_notice"
    assert classify_notice_stage("민간참여 공공주택건설사업 우선협상대상자 선정결과") == "result"
    assert is_business_opportunity_stage("main_notice")
    assert not is_business_opportunity_stage("result")

    relevance = classify_modular_relevance("민간참여 공공주택건설사업 민간사업자 공모")
    assert relevance.value == "review_candidate"
    assert relevance.value != "confirmed"
    confirmed = classify_modular_relevance("모듈러 적용 민간참여 공공주택건설사업")
    assert confirmed.value == "confirmed"

    ok, reason = validate_exact_detail_url(
        BOARD_URL,
        allowed_domains=["www.lh.or.kr", "lh.or.kr"],
        source_record_id="732612",
    )
    assert not ok
    assert reason == "list_url_not_exact"
    ok, reason = validate_exact_detail_url(
        "https://example.com/board.es?act=view&list_no=732612",
        allowed_domains=["www.lh.or.kr", "lh.or.kr"],
        source_record_id="732612",
    )
    assert not ok
    assert reason == "domain_not_allowed"


def test_duplicate_upsert() -> None:
    record = build_record()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test.sqlite"
        first = LHCollectStats(records=[record])
        apply_records(first, db_path=db_path)
        second = LHCollectStats(records=[record])
        apply_records(second, db_path=db_path)
        with sqlite3.connect(db_path) as conn:
            item_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            detail_count = conn.execute("SELECT COUNT(*) FROM source_details").fetchone()[0]
        assert item_count == 1
        assert detail_count == 1
        assert first.inserted == 1
        assert second.unchanged == 1


def test_optional_live_smoke() -> None:
    if os.getenv("RUN_LH_CONTEST_LIVE_TEST") != "1":
        print("optional live smoke skipped; set RUN_LH_CONTEST_LIVE_TEST=1 to enable")
        return
    from src.collectors.public_housing_contests.lh import collect_lh_public_housing_contests

    stats = collect_lh_public_housing_contests(dry_run=True, known_record_only=True, limit=1)
    if not stats.records:
        print("WARNING: live smoke did not collect a known LH record")
        return
    record = stats.records[0]
    assert record.source_record_id
    assert record.original_url and record.source_record_id in record.original_url


def main() -> int:
    test_offline_parser()
    test_classification_rules()
    test_duplicate_upsert()
    test_optional_live_smoke()
    print("LH public housing contest collector tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
