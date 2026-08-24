from __future__ import annotations

import json

import pytest
import requests

from scripts.integrations.technology.baseline_exact import (
    CONFLICT,
    IDENTITY_INSUFFICIENT,
    MATCHED_OFFICIAL,
    NOT_FOUND_OFFICIAL,
    build_exact_lookup_plan,
    evaluate_baseline_patent,
    reconcile_prior_candidates,
)
from scripts.integrations.technology.live_sources import (
    KIPRIS_APPLICATION_EXACT_ENDPOINT,
    KIPRIS_REGISTRATION_EXACT_ENDPOINT,
    KiprisExactLookupClient,
    normalize_kipris_exact_query_identifier,
)
from scripts.integrations.technology.matching import company_identities


class FakeResponse:
    def __init__(self, content: bytes | str, status_code: int = 200) -> None:
        self.content = content.encode("utf-8") if isinstance(content, str) else content
        self.status_code = status_code
        self.encoding = "utf-8"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


def exact_xml(
    *,
    title: str = "브래킷을 이용한 모듈러 시스템 접합구조 및 시공방법",
    applicant: str = "삼성물산 주식회사",
    application: str = "1020150054321",
    registration: str = "1016724690000",
    public_number: str = "1020160123456",
) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<response><header><resultCode>00</resultCode></header><items>
<PatentUtilityInfo>
<Applicant>{applicant}</Applicant>
<RegistrationDate>20161102</RegistrationDate>
<RegistrationNumber>{registration}</RegistrationNumber>
<RegistrationStatus>등록</RegistrationStatus>
<ApplicationDate>20150403</ApplicationDate>
<ApplicationNumber>{application}</ApplicationNumber>
<OpeningNumber>{public_number}</OpeningNumber>
<SerialNumber>exact-1</SerialNumber>
<InventionName>{title}</InventionName>
</PatentUtilityInfo>
<docsStart>1</docsStart><totalSearchCount>1</totalSearchCount>
</items></response>"""


def samsung_company() -> dict:
    return {
        "company_id": "samsung-ct-construction",
        "company_name": "삼성물산 건설부문",
        "legal_name": "삼성물산 주식회사",
        "aliases": ["삼성물산", "삼성물산(주)"],
    }


def baseline(**overrides) -> dict:
    row = {
        "technology_id": "tech-samsung-006",
        "record_type": "patent",
        "name": "브래킷을 이용한 모듈러 시스템 접합구조 및 시공방법",
        "application_number": None,
        "registration_number": "10-1672469",
        "patent_number": None,
        "application_date": None,
        "registration_date": None,
        "status": "registered",
    }
    row.update(overrides)
    return row


def exact_result(xml: str):
    return KiprisExactLookupClient(
        api_key="fixture-key",
        request_get=lambda *args, **kwargs: FakeResponse(xml),
    ).lookup("registration_number", "10-1672469", collected_at="2026-08-24T00:00:00+00:00")


def test_exact_lookup_uses_official_number_endpoints_and_parameters() -> None:
    calls = []

    def request_get(url, *, params, timeout):
        calls.append((url, dict(params), timeout))
        return FakeResponse(exact_xml())

    client = KiprisExactLookupClient(api_key="fixture-key", request_get=request_get)
    registration = client.lookup("registration_number", "10-1672469")
    application = client.lookup("application_number", "10-2015-0054321")

    assert registration.diagnostic.status == "healthy"
    assert application.diagnostic.status == "healthy"
    assert calls == [
        (
            KIPRIS_REGISTRATION_EXACT_ENDPOINT,
            {"registerNumber": "1016724690000", "docsStart": 1, "accessKey": "fixture-key"},
            (5, 20),
        ),
        (
            KIPRIS_APPLICATION_EXACT_ENDPOINT,
            {"applicationNumber": "1020150054321", "docsStart": 1, "accessKey": "fixture-key"},
            (5, 20),
        ),
    ]


def test_exact_identifier_normalization_is_strict() -> None:
    assert normalize_kipris_exact_query_identifier("10-1672469", "registration_number") == "1016724690000"
    assert normalize_kipris_exact_query_identifier("10-2015-0054321", "application_number") == "1020150054321"
    with pytest.raises(ValueError):
        normalize_kipris_exact_query_identifier("10-123", "registration_number")
    with pytest.raises(ValueError):
        normalize_kipris_exact_query_identifier("10-1672469", "application_number")


def test_exact_response_completes_missing_official_identity_fields() -> None:
    row = baseline()
    plan = build_exact_lookup_plan([row])[0]
    report = evaluate_baseline_patent(row, plan, exact_result(exact_xml()), samsung_company())

    assert report["match_decision"] == MATCHED_OFFICIAL
    assert report["official_application_number"] == "10-2015-0054321"
    assert report["official_registration_number"] == "10-1672469"
    assert report["official_application_date"] == "2015-04-03"
    assert report["official_registration_date"] == "2016-11-02"
    assert report["official_status"] == "registered"
    assert report["official_patent_public_number"] == "1020160123456"
    assert report["enrichment_fields"]["application_number"] == "10-2015-0054321"
    assert report["enrichment_fields"]["patent_number"] == "1020160123456"


def test_matching_identifier_accepts_deterministic_substantive_title_extension() -> None:
    row = baseline(
        name="철골 콘크리트 합성보와 경량 콘크리트 패널이 합성된 바닥 구조체 및 시공방법"
    )
    plan = build_exact_lookup_plan([row])[0]
    report = evaluate_baseline_patent(
        row,
        plan,
        exact_result(exact_xml(
            title="철골 콘크리트 합성보와 경량 콘크리트 패널이 합성된 바닥 구조체 및 이의 시공방법"
        )),
        samsung_company(),
    )

    assert report["match_decision"] == MATCHED_OFFICIAL
    assert report["title_match"] == "substantive"


def test_same_title_with_different_official_identity_is_conflict() -> None:
    row = baseline()
    plan = build_exact_lookup_plan([row])[0]
    result = exact_result(exact_xml(registration="1099999990000"))
    report = evaluate_baseline_patent(row, plan, result, samsung_company())

    assert report["match_decision"] == CONFLICT
    assert report["conflict_fields"] == ["official_identifier_not_returned"]


def test_matching_identifier_with_title_or_company_conflict_is_blocked() -> None:
    row = baseline()
    plan = build_exact_lookup_plan([row])[0]
    report = evaluate_baseline_patent(
        row,
        plan,
        exact_result(exact_xml(title="반도체 패키지", applicant="다른 주식회사")),
        samsung_company(),
    )

    assert report["match_decision"] == CONFLICT
    assert report["conflict_fields"] == ["applicant_or_right_holder", "title"]


def test_not_found_and_insufficient_identity_are_distinct() -> None:
    planned = baseline()
    plan = build_exact_lookup_plan([planned])[0]
    empty = KiprisExactLookupClient(
        api_key="fixture-key",
        request_get=lambda *args, **kwargs: FakeResponse(
            "<response><resultCode>00</resultCode><items/><totalSearchCount>0</totalSearchCount></response>"
        ),
    ).lookup("registration_number", "10-1672469")
    assert evaluate_baseline_patent(planned, plan, empty, samsung_company())["match_decision"] == NOT_FOUND_OFFICIAL

    unplanned = baseline(registration_number=None)
    insufficient_plan = build_exact_lookup_plan([unplanned])[0]
    assert insufficient_plan["planning_decision"] == IDENTITY_INSUFFICIENT
    assert evaluate_baseline_patent(unplanned, insufficient_plan, None, samsung_company())["match_decision"] == IDENTITY_INSUFFICIENT


def test_exact_diagnostics_and_raw_page_do_not_expose_credentials() -> None:
    result = exact_result(
        exact_xml().replace("</response>", "<requestUrl>https://example.test?accessKey=fixture-key</requestUrl></response>")
    )
    serialized = json.dumps(result.diagnostic.as_dict(), ensure_ascii=False)

    assert "fixture-key" not in serialized
    assert "accessKey=" not in serialized
    assert "fixture-key" not in result.raw_pages[0]
    assert "accessKey=" not in result.raw_pages[0]


def test_prior_candidate_reconciliation_removes_only_official_identity_duplicates() -> None:
    reports = [{
        "baseline_technology_id": "tech-samsung-006",
        "baseline_application_number": None,
        "baseline_registration_number": "10-1672469",
        "baseline_patent_number": None,
        "official_application_number": "10-2015-0054321",
        "official_registration_number": "10-1672469",
        "official_patent_public_number": "10-2016-0123456",
        "match_decision": MATCHED_OFFICIAL,
    }]
    candidates = [
        {
            "record_type": "patent",
            "official_identity": "patent:1020150054321",
            "application_number": "10-2015-0054321",
            "name": "same official record",
            "modular_relevance": "direct",
        },
        {
            "record_type": "patent",
            "official_identity": "patent:1020999999999",
            "application_number": "10-2099-9999999",
            "name": "different official record",
            "modular_relevance": "direct",
        },
        {
            "record_type": "patent",
            "official_identity": "patent:1020888888888",
            "application_number": "10-2088-8888888",
            "name": "adjacent record",
            "modular_relevance": "adjacent",
        },
    ]

    first = reconcile_prior_candidates(candidates, reports)
    second = reconcile_prior_candidates(list(reversed(candidates)), reports)

    assert first == second
    assert first["direct_total_before"] == 2
    assert first["direct_duplicate_with_baseline"] == 1
    assert first["direct_net_new_after"] == 1
    assert first["adjacent_review_after"] == 1


def test_company_identity_fixture_contains_samsung_legal_name() -> None:
    identities = company_identities([samsung_company()])
    assert identities[0].company_id == "samsung-ct-construction"
    assert "삼성물산 주식회사" in identities[0].canonical_names
