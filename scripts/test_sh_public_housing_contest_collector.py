from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.collectors.public_housing_contests.sh import (  # noqa: E402
    BID_LIST_URL,
    BOARD_URL,
    SHCollectStats,
    SHContestRecord,
    SHG2BDiscovery,
    apply_sh_stats,
    classify_sh_candidate,
    extract_title,
    html_to_text,
    official_attachments,
    parse_bid_list_rows,
    parse_down_list,
    parse_landing_notice_links,
    parse_date,
    verify_sh_detail_url,
)
from src.collectors.public_housing_contests.sh_probe import build_g2b_bid_url  # noqa: E402
from src.database import init_db, upsert_item  # noqa: E402
from src.models import Item  # noqa: E402


FIXTURE_DIR = ROOT / "tests" / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def build_record() -> SHContestRecord:
    return SHContestRecord(
        source_code="SH_CONTEST",
        source_name="SH",
        organization="서울주택도시개발공사",
        source_type="public_agency_contest",
        business_type="private_participation_public_housing",
        display_type="민간사업자 공모",
        source_record_id="306155",
        title="고덕강일 A-1BL 민간참여 공공주택건설사업 민간사업자 공모 공고",
        normalized_title="고덕강일 A-1BL 민간참여 공공주택건설사업 민간사업자 공모 공고",
        posted_at="2026-06-05",
        deadline_at="2026-08-20",
        application_schedule_text="사업신청서 제출 마감일은 2026-08-20입니다.",
        estimated_cost=None,
        household_count=None,
        housing_type=None,
        project_name="고덕강일 A-1BL 민간참여 공공주택건설사업 민간사업자 공모 공고",
        project_sites=["고덕강일"],
        project_blocks=["A-1BL"],
        body_summary="서울주택도시개발공사는 공공주택건설사업을 위한 민간사업자 공모를 시행합니다.",
        original_url="https://www.i-sh.co.kr/main/lay2/program/S1T294C299/www/brd/m_255/view.do?multi_itm_seq=8&seq=306155",
        board_url=BOARD_URL,
        source_page_url="https://www.i-sh.co.kr/main/lay2/program/S1T294C299/www/brd/m_255/view.do?multi_itm_seq=8&seq=306155",
        attachments=[
            {
                "name": "고덕강일 A-1BL 민간참여 공공주택건설사업 민간사업자 공모 공고문.pdf",
                "file_type": "pdf",
                "url": "https://www.i-sh.co.kr/main/com/util/htmlConverter.do?brd_id=GS0401&seq=306155&data_tp=A&file_seq=1",
            }
        ],
        status="ok",
        stage="notice",
        classification_status="confirmed",
        modular_relevance="review_candidate",
        modular_relevance_score=3,
        modular_evidence=["민간참여 공공주택 공모"],
        collected_at="2026-06-23T09:00:00+09:00",
        fingerprint="fixture",
        related_group_key="서울주택도시개발공사|고덕강일 A-1BL",
        exact_link_verified=True,
        link_validation_reason="verified",
    )


def build_g2b_item() -> Item:
    return Item(
        source_type="bid",
        source_name="나라장터",
        title="고덕강일 체육공원 및 녹지 조경공사 PE관 구매",
        organization="서울주택도시개발공사",
        posted_at=parse_date("2026-06-22"),
        due_at=parse_date("2026-06-29"),
        amount=None,
        region=None,
        keywords="모듈러",
        summary="기존 나라장터 공고 fixture",
        url="https://www.g2b.go.kr",
        relevance_score=70,
        unique_hash="fixture-g2b-R26BK01594237-000",
        is_mock=0,
        data_quality="real",
        original_url=None,
        source_search_url="https://www.g2b.go.kr",
        source_record_id="R26BK01594237",
        source_record_no="000",
        bid_no="R26BK01594237",
        bid_order="000",
        business_type="물품",
    )


def test_parsers() -> None:
    list_html = read_fixture("sh_contest_list_minimal.html")
    notices = parse_landing_notice_links(list_html, "https://www.i-sh.co.kr/main/")
    assert notices
    assert notices[0]["source_record_id"] == "305155"

    rows = parse_bid_list_rows(list_html)
    assert len(rows) == 2
    assert rows[0]["bid_no"] == "R26BK01594237"
    assert rows[0]["bid_order"] == "000"
    assert rows[0]["detail_url"] == build_g2b_bid_url("R26BK01594237", "000")

    empty_rows = parse_bid_list_rows(read_fixture("sh_contest_empty_list_minimal.html"))
    assert empty_rows == []


def test_classification_and_exact_url() -> None:
    detail_url = "https://www.i-sh.co.kr/main/lay2/program/S1T294C299/www/brd/m_255/view.do?multi_itm_seq=8&seq=306155"
    public_html = read_fixture("sh_contest_public_notice_detail_minimal.html")
    body = html_to_text(public_html)
    title = extract_title(public_html)
    attachments = official_attachments(parse_down_list(public_html, detail_url))
    classification, stage = classify_sh_candidate(title, body, [item["name"] for item in attachments])
    assert classification == "confirmed"
    assert stage == "notice"
    assert attachments and attachments[0]["file_type"] == "pdf"

    exact, reason = verify_sh_detail_url(
        url=detail_url,
        source_record_id="306155",
        expected_title=title,
        detail_title=title,
        body=body,
        status_code=200,
    )
    assert exact, reason

    result_html = read_fixture("sh_contest_result_detail_minimal.html")
    result_title = extract_title(result_html)
    result_classification, result_stage = classify_sh_candidate(result_title, html_to_text(result_html), [])
    assert result_classification == "result"
    assert result_stage == "result"

    irrelevant_html = read_fixture("sh_contest_irrelevant_detail_minimal.html")
    irrelevant_title = extract_title(irrelevant_html)
    irrelevant_classification, _ = classify_sh_candidate(irrelevant_title, html_to_text(irrelevant_html), [])
    assert irrelevant_classification in {"review_required", "excluded"}

    exact, reason = verify_sh_detail_url(
        url=BID_LIST_URL,
        source_record_id="306155",
        expected_title=title,
        detail_title=title,
        body=body,
        status_code=200,
    )
    assert not exact
    assert reason == "list_url_not_exact"


def test_duplicate_upsert_and_g2b_merge() -> None:
    record = build_record()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test.sqlite"
        init_db(db_path)
        first = SHCollectStats(records=[record])
        apply_sh_stats(first, db_path=db_path)
        second = SHCollectStats(records=[record])
        apply_sh_stats(second, db_path=db_path)
        with sqlite3.connect(db_path) as conn:
            item_count = conn.execute("SELECT COUNT(*) FROM items WHERE source_name = 'SH'").fetchone()[0]
            detail_count = conn.execute("SELECT COUNT(*) FROM source_details WHERE source_name = 'SH' AND source_type = 'public_agency_contest'").fetchone()[0]
        assert item_count == 1
        assert detail_count == 1
        assert first.inserted == 1
        assert second.unchanged == 1

        upsert_item(build_g2b_item(), db_path=db_path)
        discovery = SHG2BDiscovery(
            bid_no="R26BK01594237",
            bid_order="000",
            title="고덕강일 체육공원 및 녹지 조경공사 PE관 구매",
            posted_at="2026-06-22",
            detail_url=build_g2b_bid_url("R26BK01594237", "000"),
            source_page_url=BID_LIST_URL,
        )
        merge_stats = SHCollectStats(g2b_discoveries=[discovery])
        apply_sh_stats(merge_stats, db_path=db_path)
        apply_sh_stats(merge_stats, db_path=db_path)
        with sqlite3.connect(db_path) as conn:
            g2b_items = conn.execute("SELECT COUNT(*) FROM items WHERE bid_no = 'R26BK01594237'").fetchone()[0]
            sh_discoveries = conn.execute(
                "SELECT COUNT(*) FROM source_details WHERE source_name = 'SH' AND source_type = 'bid'"
            ).fetchone()[0]
        assert g2b_items == 1
        assert sh_discoveries == 1


def main() -> int:
    test_parsers()
    test_classification_and_exact_url()
    test_duplicate_upsert_and_g2b_merge()
    print("SH public housing contest collector tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
