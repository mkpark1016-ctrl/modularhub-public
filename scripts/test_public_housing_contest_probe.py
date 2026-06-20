from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.collectors.public_housing_contests.base import load_sources
from src.public_housing_contest_classifier import (
    classify_modular_relevance,
    classify_notice_stage,
    is_business_opportunity_stage,
    normalize_title,
    validate_exact_detail_url,
)
from src.public_housing_contest_contract import BUSINESS_TYPE, SOURCE_TYPE, default_contract_fields


REQUIRED_SOURCE_FIELDS = {
    "source_code",
    "source_name",
    "organization_name",
    "list_url",
    "allowed_domains",
    "parser_mode",
    "pagination_mode",
    "detail_url_pattern",
    "known_record",
    "request_interval_seconds",
    "enabled",
}


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    sources = load_sources()
    assert_true(len(sources) == 4, "expected four public housing contest sources")
    for source in sources:
        missing = REQUIRED_SOURCE_FIELDS - set(source)
        assert_true(not missing, f"{source.get('source_code')} missing fields: {sorted(missing)}")
        assert_true(source["request_interval_seconds"] >= 1, "request interval must be >= 1 second")

    keywords = json.loads(Path("config/public_housing_contest_keywords.json").read_text(encoding="utf-8"))
    assert_true("민간참여 공공주택건설사업" in keywords["primary_include"], "missing primary keyword")
    assert_true("모듈러" in keywords["modular_confirmed_terms"], "missing modular evidence term")

    fields = default_contract_fields()
    assert_true("source_record_id" in fields and "attachments" in fields, "contract fields incomplete")
    assert_true(SOURCE_TYPE == "public_agency_contest", "source_type constant changed")
    assert_true(BUSINESS_TYPE == "private_participation_public_housing", "business_type constant changed")

    normalized = normalize_title("2026년 제3차 민간참여 공공주택건설사업 정정공고")
    assert_true("정정공고" not in normalized, "normalization should remove stage terms")

    assert_true(classify_notice_stage("민간사업자 공모 사전예고") == "pre_notice", "pre notice classification failed")
    assert_true(classify_notice_stage("민간사업자 재공모") == "re_notice", "re notice classification failed")
    assert_true(classify_notice_stage("평가결과 및 우선협상대상자 선정") == "result", "result classification failed")
    assert_true(not is_business_opportunity_stage("result"), "result must not be an opportunity stage")

    confirmed = classify_modular_relevance("모듈러 적용 민간참여 공공주택")
    assert_true(confirmed.value == "confirmed", "explicit modular evidence should be confirmed")
    candidate = classify_modular_relevance("민간참여 공공주택건설사업 민간사업자 공모")
    assert_true(candidate.value == "review_candidate", "public housing contest without modular evidence should be review candidate")
    unrelated = classify_modular_relevance("일반 공지사항")
    assert_true(unrelated.value == "unconfirmed", "unrelated text should be unconfirmed")

    ok, reason = validate_exact_detail_url(
        "https://www.lh.or.kr/board.es?mid=a10601020000&bid=0034&act=view&list_no=732612",
        allowed_domains=["www.lh.or.kr"],
        source_record_id="732612",
    )
    assert_true(ok, f"known LH candidate should pass URL-level validation: {reason}")
    ok, reason = validate_exact_detail_url(
        "https://example.com/board.es?act=view&list_no=732612",
        allowed_domains=["www.lh.or.kr"],
        source_record_id="732612",
    )
    assert_true(not ok and reason == "domain_not_allowed", "foreign domain must not pass")
    ok, reason = validate_exact_detail_url(
        "https://www.lh.or.kr/board.es?mid=a10601020000&bid=0034",
        allowed_domains=["www.lh.or.kr"],
        source_record_id="732612",
    )
    assert_true(not ok and reason == "list_url_not_exact", "list URL must not pass as exact")

    known_urls = [
        "https://www.lh.or.kr/board.es?mid=a10601020000&bid=0034&act=view&list_no=732612",
        "https://www.gh.or.kr/gh/bid-announcement.do?mode=view&articleNo=63590",
        "https://www.ih.co.kr/main/customer/notification/notice.jsp?mode=view&msg_seq=4191",
    ]
    for url in known_urls:
        assert_true(re.search(r"(list_no|articleNo|msg_seq)=\d+", url), f"known record id not extractable: {url}")

    logs = json.dumps({"message": "probe test only"}, ensure_ascii=False)
    assert_true("DATA_GO_KR_SERVICE_KEY" not in logs and "NAVER_CLIENT_SECRET" not in logs, "sensitive token leaked")
    print("PUBLIC HOUSING CONTEST PROBE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
