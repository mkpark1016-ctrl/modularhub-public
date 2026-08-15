from __future__ import annotations

import json

import pytest

from scripts.integrations.business import normalize_source_record_type
from scripts.integrations.business.sources import D2BBusinessAdapter, KepcoBusinessAdapter, LHBusinessAdapter
from scripts.integrations.technology import KIPRIS_API_KEY_ENV, NormalizedTechnologyRecord


def assert_public_safe(record: dict) -> None:
    payload = json.dumps(record, ensure_ascii=False)
    for forbidden in ("serviceKey", "apiKey", "request_headers", "raw_response", "LH_SERVICE_KEY", "D2B_SERVICE_KEY", "KEPCO_API_KEY"):
        assert forbidden not in payload


def test_lh_fixture_normalizes_to_business_contract() -> None:
    raw = {
        "bidNum": "LH-2026-0001",
        "bidName": "모듈러 임시주거 제작 설치",
        "orderOrgName": "한국토지주택공사",
        "bidType": "공사",
        "regionName": "세종",
        "budgetAmount": "1,250,000,000",
        "bidStartDate": "20260801",
        "bidCloseDate": "2026-08-20 17:00:00",
        "bidStatus": "공고",
        "contractMethod": "제한경쟁",
        "detailUrl": "https://ebid.lh.or.kr/example",
        "serviceKey": "must-not-leak",
    }
    normalized = LHBusinessAdapter().normalize_raw_record(raw)

    assert normalized.source == "LH"
    assert normalized.source_record_type == "bid_notice"
    assert normalized.external_id == "LH-2026-0001"
    assert normalized.estimated_amount == 1_250_000_000
    assert normalized.published_at == "2026-08-01"
    assert normalized.deadline_at == "2026-08-20"
    assert_public_safe(normalized.as_dict())
    assert normalized.to_existing_collector_item()["source_type"] == "bid"


def test_d2b_fixture_supports_procurement_plan_alias() -> None:
    raw = {
        "recordType": "plan",
        "noticeNo": "D2B-PLAN-1",
        "noticeName": "군 숙소 모듈러 발주계획",
        "agencyName": "방위사업청",
        "businessType": "시설",
        "estimatedPrice": "980000000",
        "noticeDate": "2026.08.02",
    }
    normalized = D2BBusinessAdapter().normalize_raw_record(raw)

    assert normalized.source == "D2B"
    assert normalized.source_record_type == "procurement_plan"
    assert normalized.to_existing_collector_item()["source_type"] == "procurement_plan"
    assert_public_safe(normalized.as_dict())


def test_kepco_fixture_supports_contract_record() -> None:
    raw = {
        "record_type": "contract",
        "bid_no": "KEPCO-CT-1",
        "bid_title": "변전소 모듈러 부속동 계약",
        "department": "한국전력공사",
        "estimated_amount": "120000000.5",
        "currency": "KRW",
        "published_at": "2026/08/03",
        "status": "계약",
    }
    normalized = KepcoBusinessAdapter().normalize_raw_record(raw)

    assert normalized.source_record_type == "contract"
    assert normalized.estimated_amount == 120000000.5
    assert normalized.currency == "KRW"
    assert normalized.published_at == "2026-08-03"
    assert_public_safe(normalized.as_dict())


def test_source_record_type_rejects_unknown_values() -> None:
    assert normalize_source_record_type("award") == "bid_result"
    with pytest.raises(ValueError, match="unsupported source_record_type"):
        normalize_source_record_type("newsletter")


def test_configured_status_never_returns_secret_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEPCO_API_KEY", "secret-value")
    status = KepcoBusinessAdapter.configured_status()

    assert status == {
        "source": "KEPCO",
        "api_key_env": "KEPCO_API_KEY",
        "configured": True,
    }
    assert "secret-value" not in json.dumps(status)


def test_kipris_patent_contract_is_public_safe() -> None:
    patent = NormalizedTechnologyRecord(
        source="KIPRIS",
        external_id="KR102761128B1",
        title="모듈러 건축물의 접합부 결합 고정방법",
        applicant="주식회사 예시",
        registration_number="10-2761128",
        status="registered",
        filed_at="20240131",
        registered_at="2025.01.10",
    )

    assert KIPRIS_API_KEY_ENV == "KIPRIS_API_KEY"
    assert patent.filed_at == "2024-01-31"
    assert patent.registered_at == "2025-01-10"
    assert_public_safe(patent.as_dict())
