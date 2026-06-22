from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.collectors.public_housing_contests.agency import (  # noqa: E402
    AgencyCollectStats,
    AgencyContestRecord,
    apply_records,
    canonical_attachments,
    extract_detail_attachments,
    extract_list_items,
    extract_page_title,
    html_to_text,
    verify_detail_url,
)
from src.collectors.public_housing_contests.gh import collect_gh_public_housing_contests  # noqa: E402
from src.public_housing_contest_classifier import classify_modular_relevance, classify_notice_stage  # noqa: E402


FIXTURE_DIR = ROOT / "tests" / "fixtures"
BOARD_URL = "https://www.gh.or.kr/gh/bid-announcement.do"
DETAIL_URL = f"{BOARD_URL}?mode=view&articleNo=63590"


def read_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def build_record() -> AgencyContestRecord:
    return AgencyContestRecord(
        source_code="GH_CONTEST",
        source_name="GH",
        organization="경기주택도시공사",
        source_type="public_agency_contest",
        business_type="private_participation_public_housing",
        display_type="민간사업자 공모",
        source_record_id="63590",
        title="하남교산 A3블록 민간참여 공공주택사업 민간사업자 재공모 정정공고",
        normalized_title="하남교산 A3블록 민간참여 공공주택사업 민간사업자 공모",
        posted_at="2026-05-14",
        deadline_at="2026-07-20",
        application_schedule_text="사업신청서 제출 마감은 2026.07.20입니다.",
        estimated_cost=None,
        household_count=None,
        housing_type=None,
        project_name="하남교산 A3블록 민간참여 공공주택사업 민간사업자 공모",
        project_sites=["하남교산지구"],
        project_blocks=["A3블록"],
        body_summary="경기주택도시공사는 민간참여 공공주택사업 민간사업자 공모를 시행합니다.",
        original_url=DETAIL_URL,
        board_url=BOARD_URL,
        attachments=[
            {
                "name": "공고문.hwp",
                "file_type": "hwp",
                "url": f"{BOARD_URL}?mode=download&articleNo=63590&attachNo=1",
            }
        ],
        status="ok",
        notice_stage="correction",
        modular_relevance="review_candidate",
        modular_relevance_score=3,
        modular_evidence=["민간참여 공공주택 공모"],
        collected_at="2026-06-22T07:00:00+09:00",
        fingerprint="fixture",
        related_group_key="경기주택도시공사|하남교산 A3블록 민간참여 공공주택사업 민간사업자 공모",
        exact_link_verified=True,
        link_validation_reason="verified",
    )


def test_offline_parser() -> None:
    list_html = read_fixture("gh_contest_list.html")
    detail_html = read_fixture("gh_contest_detail.html")
    items = extract_list_items(list_html, BOARD_URL, source_code="GH_CONTEST", record_keys=("articleNo",))
    assert len(items) == 1, items
    assert items[0]["source_record_id"] == "63590"
    assert "articleNo=63590" in items[0]["href"]

    body = html_to_text(detail_html)
    title = extract_page_title(detail_html)
    assert "민간참여 공공주택사업" in title
    assert classify_notice_stage(title, body) == "correction"
    assert classify_modular_relevance(title, body).value == "review_candidate"

    attachments = extract_detail_attachments(detail_html, DETAIL_URL, ["www.gh.or.kr", "gh.or.kr"])
    assert len(attachments) == 2
    assert attachments[0]["url"].startswith("https://www.gh.or.kr/")

    verified, reason = verify_detail_url(
        url=DETAIL_URL,
        allowed_domains=["www.gh.or.kr", "gh.or.kr"],
        source_record_id="63590",
        expected_title=title,
        status_code=200,
        detail_title=title,
        body=body,
    )
    assert verified, reason

    blocked = canonical_attachments(
        [{"file_name": "bad.pdf", "url": "https://example.com/bad.pdf"}],
        DETAIL_URL,
        ["www.gh.or.kr", "gh.or.kr"],
    )
    assert blocked == []


def test_duplicate_upsert() -> None:
    record = build_record()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test.sqlite"
        first = AgencyCollectStats(source_code="GH_CONTEST", collector_name="GHPublicHousingContestCollector", records=[record])
        apply_records(first, db_path=db_path)
        second = AgencyCollectStats(source_code="GH_CONTEST", collector_name="GHPublicHousingContestCollector", records=[record])
        apply_records(second, db_path=db_path)
        with sqlite3.connect(db_path) as conn:
            item_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            detail_count = conn.execute("SELECT COUNT(*) FROM source_details").fetchone()[0]
        assert item_count == 1
        assert detail_count == 1
        assert first.inserted == 1
        assert second.unchanged == 1


def test_optional_live_smoke() -> None:
    if os.getenv("RUN_GH_CONTEST_LIVE_TEST") != "1":
        print("optional GH live smoke skipped; set RUN_GH_CONTEST_LIVE_TEST=1 to enable")
        return
    stats = collect_gh_public_housing_contests(dry_run=True, known_record_only=True, limit=1)
    if not stats.records:
        print("WARNING: live smoke did not collect a known GH record")
        return
    record = stats.records[0]
    assert record.source_record_id == "63590"
    assert record.original_url and "articleNo=63590" in record.original_url


def main() -> int:
    test_offline_parser()
    test_duplicate_upsert()
    test_optional_live_smoke()
    print("GH public housing contest collector tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
