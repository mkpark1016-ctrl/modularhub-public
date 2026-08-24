from __future__ import annotations

import json
from pathlib import Path

import requests

from scripts.integrations.technology.live_sources import (
    KIPRIS_LEGAL_STATUS_BASIC_ENDPOINT,
    KIPRIS_LEGAL_STATUS_STOP_RIGHT_ENDPOINT,
    KiprisLegalStatusClient,
    parse_kipris_legal_status_response,
)
from scripts.integrations.technology.status_adjudication import (
    CONFIRMED_EXPIRED,
    CONFIRMED_REGISTERED_ACTIVE,
    CURRENT_LIFECYCLE_STATUS,
    UNRESOLVED_STATUS,
    adjudicate_patent_status,
    run_status_adjudication,
)


class FakeResponse:
    def __init__(self, content: bytes | str, status_code: int = 200) -> None:
        self.content = content.encode("utf-8") if isinstance(content, str) else content
        self.status_code = status_code
        self.encoding = "utf-8"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


def basic_xml(application: str, *, status: str = "권리유지", event_date: str = "20161102") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<response><header><resultCode>00</resultCode></header><body><items>
<legalStatusST27Info>
<applicationNumber>{application}</applicationNumber>
<supplySerialNumber>1</supplySerialNumber>
<registrationNumber>1016724690000</registrationNumber>
<registrationDate>20161102</registrationDate>
<eventDate>{event_date}</eventDate>
<legalStatusName>{status}</legalStatusName>
</legalStatusST27Info>
</items><totalCount>1</totalCount></body></response>"""


def stop_xml(
    application: str,
    *,
    cause_date: str = "20231101",
    cause_name: str = "등록료 불납으로 권리 소멸",
) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<response><header><resultCode>00</resultCode></header><body><items>
<legalStatusST27StopRightInfo>
<applicationNumber>{application}</applicationNumber>
<SerialNumber>1</SerialNumber>
<terminationRegistrationCauseDate>{cause_date}</terminationRegistrationCauseDate>
<terminationRegistrationCauseName>{cause_name}</terminationRegistrationCauseName>
</legalStatusST27StopRightInfo>
</items><totalCount>1</totalCount></body></response>"""


def empty_xml() -> str:
    return "<response><header><resultCode>00</resultCode></header><items/><totalCount>0</totalCount></response>"


def test_st27_parsers_preserve_basic_and_termination_history() -> None:
    basic, basic_total, basic_fields, basic_code = parse_kipris_legal_status_response(
        basic_xml("1020140184710"), operation="basic"
    )
    stop, stop_total, stop_fields, stop_code = parse_kipris_legal_status_response(
        stop_xml("1020140184710"), operation="stop_right"
    )

    assert basic_total == stop_total == 1
    assert basic_code == stop_code == "00"
    assert basic[0]["applicationNumber"] == "1020140184710"
    assert basic[0]["eventDate"] == "20161102"
    assert stop[0]["terminationRegistrationCauseDate"] == "20231101"
    assert "currentStageCode" not in basic_fields
    assert "terminationRegistrationCauseName" in stop_fields


def test_explicit_termination_confirms_expired_status() -> None:
    result = adjudicate_patent_status(
        [{"eventDate": "20161102", "legalStatusName": "권리유지"}],
        [{
            "terminationRegistrationCauseDate": "20231101",
            "terminationRegistrationCauseName": "등록료 불납으로 권리 소멸",
        }],
    )

    assert result["decision"] == CONFIRMED_EXPIRED
    assert result["current_status"] == "expired"
    assert result["status_field_semantics"] == CURRENT_LIFECYCLE_STATUS


def test_explicit_active_status_without_termination_confirms_active() -> None:
    result = adjudicate_patent_status(
        [{"eventDate": "20260801", "legalStatusName": "권리유지"}], []
    )

    assert result["decision"] == CONFIRMED_REGISTERED_ACTIVE
    assert result["current_status"] == "registered"


def test_later_active_event_after_termination_remains_unresolved() -> None:
    result = adjudicate_patent_status(
        [{"eventDate": "20260801", "legalStatusName": "권리유지"}],
        [{
            "terminationRegistrationCauseDate": "20240101",
            "terminationRegistrationCauseName": "권리 소멸",
        }],
    )

    assert result["decision"] == UNRESOLVED_STATUS
    assert result["current_status"] is None


def test_legal_status_client_uses_exact_official_contract_and_sanitizes_secret() -> None:
    calls = []

    def request_get(url, *, params, timeout):
        calls.append((url, dict(params), timeout))
        payload = basic_xml("1020140184710").replace(
            "</response>",
            "<requestUrl>https://example.test?accessKey=fixture-key</requestUrl></response>",
        )
        return FakeResponse(payload)

    client = KiprisLegalStatusClient(api_key="fixture-key", request_get=request_get)
    result = client.lookup("basic", "10-2014-0184710")

    assert result.diagnostic.status == "healthy"
    assert calls == [(
        KIPRIS_LEGAL_STATUS_BASIC_ENDPOINT,
        {"applicationNumber": "1020140184710", "accessKey": "fixture-key"},
        (5, 20),
    )]
    assert "fixture-key" not in result.raw_pages[0]
    assert "accessKey=" not in result.raw_pages[0]
    assert "fixture-key" not in json.dumps(result.diagnostic.as_dict())


def test_access_denial_is_not_retried() -> None:
    calls = []

    def request_get(url, *, params, timeout):
        calls.append(url)
        return FakeResponse(
            "<response><resultCode>20</resultCode><resultMsg>SERVICE ACCESS DENIED</resultMsg></response>"
        )

    result = KiprisLegalStatusClient(
        api_key="fixture-key", request_get=request_get, max_attempts=3
    ).lookup("basic", "10-2014-0184710")

    assert result.diagnostic.status == "service_denied"
    assert result.diagnostic.api_result_code == "20"
    assert calls == [KIPRIS_LEGAL_STATUS_BASIC_ENDPOINT]


def test_two_target_run_is_bounded_and_generates_update_candidates(tmp_path: Path) -> None:
    companies = [{
        "company_id": "samsung-ct-construction",
        "technology": {"patents": [
            {
                "technology_id": "tech-samsung-006",
                "name": "브래킷을 이용한 모듈러 시스템 접합구조 및 시공방법",
                "registration_number": "10-1672469",
                "status": "registered",
            },
            {
                "technology_id": "tech-samsung-007",
                "name": "결합플레이트를 이용한 모듈러 시스템 접합구조 및 시공방법",
                "registration_number": "10-1632681",
                "status": "registered",
            },
        ]},
    }]
    companies_path = tmp_path / "companies.json"
    prior_path = tmp_path / "prior-summary.json"
    companies_path.write_text(json.dumps(companies, ensure_ascii=False), encoding="utf-8")
    prior_path.write_text(json.dumps({"matched_official_count": 4}), encoding="utf-8")
    calls = []

    def request_get(url, *, params, timeout):
        calls.append((url, params["applicationNumber"]))
        if url == KIPRIS_LEGAL_STATUS_BASIC_ENDPOINT:
            return FakeResponse(basic_xml(params["applicationNumber"]))
        return FakeResponse(stop_xml(params["applicationNumber"]))

    summary = run_status_adjudication(
        companies_path=companies_path,
        prior_summary_path=prior_path,
        output_dir=tmp_path / "artifacts",
        client=KiprisLegalStatusClient(api_key="fixture-key", request_get=request_get),
        collected_at="2026-08-24T00:00:00+00:00",
    )

    assert len(calls) == 4
    assert summary["confirmed_expired_count"] == 2
    assert summary["status_update_candidate_count"] == 2
    assert summary["matched_official_count_after_adjudication"] == 6
    assert summary["remaining_conflict_count"] == 0
    assert summary["decision"] == "SAMSUNG_PATENT_STATUS_CONFLICT_RESOLVED"
    assert summary["public_write_performed"] is False
    assert summary["security"] == {
        "credential_url_count": 0,
        "secret_exposure_count": 0,
        "raw_public_field_count": 0,
    }


def test_frontend_contract_treats_status_as_current_lifecycle_state() -> None:
    root = Path(__file__).resolve().parents[1]
    labels = (root / "frontend/src/companyInsights.js").read_text(encoding="utf-8")
    decision_model = (root / "frontend/src/companyDecisionModel.js").read_text(encoding="utf-8")

    assert 'expired: "만료"' in labels
    assert '["registered", "granted"].includes(normalizedStatus(item))' in decision_model
    assert "expired" not in decision_model.split("function isRegisteredStatus", 1)[1].split("}", 1)[0]
