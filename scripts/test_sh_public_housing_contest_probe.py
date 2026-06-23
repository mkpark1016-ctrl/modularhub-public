from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collectors.public_housing_contests.sh_probe import (  # noqa: E402
    LANDING_URL,
    build_g2b_bid_url,
    extract_seq,
    find_bid_list_url,
    keyword_flags,
    parse_bid_list_rows,
    parse_landing_notice_links,
    parse_notice_detail,
    parse_page_count,
)


FIXTURE_DIR = Path("tests/fixtures")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    list_html = (FIXTURE_DIR / "sh_contest_list_minimal.html").read_text(encoding="utf-8")
    detail_html = (FIXTURE_DIR / "sh_contest_detail_minimal.html").read_text(encoding="utf-8")

    bid_url = find_bid_list_url(list_html, LANDING_URL)
    require("BidblancList.do" in bid_url, "SH bid list URL was not detected")

    rows = parse_bid_list_rows(list_html)
    require(len(rows) == 2, f"expected 2 bid rows, got {len(rows)}")
    require(rows[0]["bid_no"] == "R26BK01594237", "bid number extraction failed")
    require(rows[0]["bid_order"] == "000", "bid order extraction failed")
    require(rows[0]["posted_at"] == "2026-06-22", "posted date extraction failed")
    require(rows[0]["detail_url"] == build_g2b_bid_url("R26BK01594237", "000"), "G2B detail URL construction failed")
    require(rows[1]["housing_context_match"], "public housing context keyword was not detected")

    page_count = parse_page_count("총 10 건 [1/1페이지]")
    require(page_count["total_count"] == 10 and page_count["page_count"] == 1, "page count parsing failed")

    notices = parse_landing_notice_links(list_html, LANDING_URL)
    require(len(notices) == 1, f"expected 1 notice link, got {len(notices)}")
    require(notices[0]["source_record_id"] == "305155", "notice seq extraction failed")
    require(notices[0]["general_private_contest_candidate"], "private contest keyword was not detected")
    require(not notices[0]["public_housing_candidate"], "non-housing private contest must not be public housing candidate")

    detail_url = "https://www.i-sh.co.kr/main/lay2/program/S1T294C299/www/brd/m_255/view.do?multi_itm_seq=8&seq=305155"
    detail = parse_notice_detail(detail_html, detail_url)
    require(detail["source_record_id"] == "305155", "detail seq extraction failed")
    require(extract_seq(detail_url) == "305155", "extract_seq failed")
    require(detail["posted_at"] == "2026-06-05", "detail posted date extraction failed")
    require(detail["attachment_count"] == 1, "attachment extraction failed")
    attachment = detail["attachments"][0]
    require(attachment["file_type"] == "jpg", "attachment file type failed")
    require("htmlConverter.do" in attachment["url"], "attachment official preview URL missing")
    require(attachment["brd_id"] == "GS0401" and attachment["file_seq"] == "1", "attachment metadata mismatch")

    result_flags = keyword_flags("민간참여 공공주택사업 우선협상대상자 선정결과")
    require(result_flags["public_housing_candidate"], "public housing candidate keyword failed")
    require(result_flags["result_keyword"], "result keyword classification failed")

    empty_rows = parse_bid_list_rows("<table><tbody><tr><td>조건에 맞는 정보가 없습니다.</td></tr></tbody></table>")
    require(empty_rows == [], "empty list should produce no rows")

    print("SH PUBLIC HOUSING CONTEST PROBE TEST PASSED")


if __name__ == "__main__":
    main()
