from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests
from requests.exceptions import ConnectTimeout

from scripts.integrations.technology.live_acceptance import (
    PROTECTED_PUBLIC_FILES,
    acceptance_decision,
    build_acceptance_detail,
    hash_files,
    run_live_acceptance,
)
from scripts.integrations.technology.live_sources import (
    KAIA_NEWTECH_ENDPOINT,
    KIPRIS_APPLICANT_ENDPOINT,
    KaiaLiveClient,
    KiprisLiveClient,
    artifact_contains_credentials,
    parse_kaia_newtech_response,
    parse_kipris_applicant_response,
    sanitize_response_text,
)
from scripts.integrations.technology.reconciliation import normalize_fixture_records


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/company_technology"
COMPANIES = ROOT / "frontend/public/data/companies/companies.json"


class FakeResponse:
    def __init__(self, content: bytes | str, status_code: int = 200) -> None:
        self.content = content.encode("utf-8") if isinstance(content, str) else content
        self.status_code = status_code
        self.encoding = "utf-8"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def single_kipris_xml(
    *,
    serial: str,
    application: str,
    registration: str,
    total: int,
    title: str = "모듈러 건축 유닛 접합 기술",
) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<response><header><resultCode>00</resultCode></header><items>
<PatentUtilityInfo>
<Applicant>삼성물산 주식회사</Applicant>
<RegistrationDate>20240320</RegistrationDate>
<RegistrationNumber>{registration}</RegistrationNumber>
<RegistrationStatus>등록</RegistrationStatus>
<ApplicationDate>20210611</ApplicationDate>
<ApplicationNumber>{application}</ApplicationNumber>
<Abstract>모듈러 건축 구조 기술</Abstract>
<SerialNumber>{serial}</SerialNumber>
<InventionName>{title}</InventionName>
<InternationalpatentclassificationNumber>E04B 1/348</InternationalpatentclassificationNumber>
</PatentUtilityInfo>
<docsStart>1</docsStart><totalSearchCount>{total}</totalSearchCount>
</items></response>"""


def test_live_parsers_follow_documented_kipris_and_kaia_fields() -> None:
    kipris_rows, kipris_total, kipris_fields, result_code = parse_kipris_applicant_response(
        fixture("kipris_applicant_live.xml"),
        collected_at="2026-08-23T00:00:00+00:00",
    )
    kaia_rows, kaia_total, kaia_fields = parse_kaia_newtech_response(
        fixture("kaia_newtech_live.xml"),
        collected_at="2026-08-23T00:00:00+00:00",
    )

    assert result_code == "00"
    assert kipris_total == 2
    assert len(kipris_rows) == 2
    assert {"ApplicationNumber", "RegistrationNumber", "InventionName", "Applicant"}.issubset(kipris_fields)
    assert kipris_rows[0]["sourceUrl"].startswith("https://plus.kipris.or.kr/")
    assert kaia_total == 1
    assert len(kaia_rows) == 1
    assert {"newtecId", "apntNo", "newtecNm", "dvlprNm"}.issubset(kaia_fields)
    assert kaia_rows[0]["sourceUrl"].startswith("https://www.kaia.re.kr/")


def test_live_schema_normalizes_kipris_numbers_status_and_dates() -> None:
    rows, _, _, _ = parse_kipris_applicant_response(fixture("kipris_applicant_live.xml"))
    result = normalize_fixture_records(rows)

    assert len(result.records) == 2
    first = result.records[0]
    assert first.application_number == "10-2020-0000010"
    assert first.registration_number == "10-2388438"
    assert first.registration_date == "2022-04-12"
    assert first.status == "registered"


def test_same_live_title_with_different_official_numbers_remains_distinct() -> None:
    rows, _, _, _ = parse_kipris_applicant_response(fixture("kipris_applicant_live.xml"))
    result = normalize_fixture_records(rows)

    assert result.records[0].title == result.records[1].title
    assert result.records[0].identity_key() != result.records[1].identity_key()
    assert result.duplicate_identity_count == 0


def test_duplicate_live_official_identity_is_deduplicated() -> None:
    rows, _, _, _ = parse_kipris_applicant_response(fixture("kipris_applicant_live.xml"))
    result = normalize_fixture_records([rows[0], dict(rows[0], SerialNumber="duplicate")])

    assert len(result.records) == 1
    assert result.duplicate_identity_count == 1


def test_kipris_pagination_is_bounded_and_deterministic() -> None:
    responses = iter([
        FakeResponse(single_kipris_xml(
            serial="page-1",
            application="1020260000001",
            registration="1027000010000",
            total=2,
        )),
        FakeResponse(single_kipris_xml(
            serial="page-2",
            application="1020260000002",
            registration="1027000020000",
            total=2,
        )),
    ])
    calls = []

    def request_get(url, *, params, timeout):
        calls.append((url, dict(params), timeout))
        return next(responses)

    result = KiprisLiveClient(
        api_key="fixture-key",
        request_get=request_get,
        sleep_func=lambda _: None,
    ).collect(
        ["삼성물산"],
        page_size=1,
        max_pages=2,
        max_records=2,
        collected_at="2026-08-23T00:00:00+00:00",
    )

    assert result.diagnostic.status == "healthy"
    assert result.diagnostic.pages_requested == 2
    assert result.diagnostic.received_count == 2
    assert len(calls) == 2
    assert [call[1]["docsStart"] for call in calls] == [1, 2]
    assert all(call[2] == (5, 20) for call in calls)
    assert result.diagnostic.query_metrics == [{
        "alias": "삼성물산",
        "query_attempted": True,
        "received_count": 2,
        "unique_application_identity_count": 2,
    }]


def test_kipris_docs_start_uses_record_offset_for_full_pages() -> None:
    responses = iter([
        FakeResponse(single_kipris_xml(
            serial="page-1",
            application="1020260000001",
            registration="1027000010000",
            total=200,
        )),
        FakeResponse(single_kipris_xml(
            serial="page-2",
            application="1020260000101",
            registration="1027000010100",
            total=200,
        )),
    ])
    starts = []

    def request_get(url, *, params, timeout):
        starts.append(params["docsStart"])
        return next(responses)

    KiprisLiveClient(
        api_key="fixture-key",
        request_get=request_get,
    ).collect(["삼성물산"], page_size=100, max_pages=2, max_records=200)

    assert starts == [1, 101]


def test_kipris_continuation_uses_bounded_offsets_without_first_page() -> None:
    starts = []
    counts = []

    def request_get(url, *, params, timeout):
        starts.append(params["docsStart"])
        counts.append(params["docsCount"])
        return FakeResponse(single_kipris_xml(
            serial=f"continuation-{params['docsStart']}",
            application=f"102026{params['docsStart']:07d}",
            registration=f"1027{params['docsStart']:05d}0000",
            total=678,
        ))

    result = KiprisLiveClient(
        api_key="fixture-key",
        request_get=request_get,
    ).collect(
        ["지에스건설 주식회사"],
        page_size=100,
        max_pages=6,
        max_records=600,
        start_offset=101,
        continuation=True,
    )

    assert starts == [101, 201, 301, 401, 501, 601]
    assert 1 not in starts
    assert counts == [100] * 6
    assert result.diagnostic.pages_requested == 6


def test_kipris_continuation_rejects_first_page() -> None:
    with pytest.raises(ValueError, match="must not request the accepted first page"):
        KiprisLiveClient(api_key="fixture-key").collect(
            ["지에스건설 주식회사"],
            start_offset=1,
            continuation=True,
        )


def test_kipris_continuation_stops_before_offset_beyond_reported_total() -> None:
    starts = []

    def request_get(url, *, params, timeout):
        starts.append(params["docsStart"])
        return FakeResponse(single_kipris_xml(
            serial="continuation-final",
            application="1020260000101",
            registration="1027001010000",
            total=150,
        ))

    result = KiprisLiveClient(
        api_key="fixture-key",
        request_get=request_get,
    ).collect(
        ["지에스건설 주식회사"],
        page_size=100,
        max_pages=6,
        max_records=600,
        start_offset=101,
        continuation=True,
    )

    assert starts == [101]
    assert result.diagnostic.pages_requested == 1


def test_kipris_alias_metrics_preserve_unattempted_queries_after_record_bound() -> None:
    result = KiprisLiveClient(
        api_key="fixture-key",
        request_get=lambda *args, **kwargs: FakeResponse(single_kipris_xml(
            serial="bounded",
            application="1020260000001",
            registration="1027000010000",
            total=1,
        )),
    ).collect(["삼성물산 주식회사", "삼성물산(주)"], max_pages=1, max_records=1)

    assert result.diagnostic.query_metrics == [
        {
            "alias": "삼성물산 주식회사",
            "query_attempted": True,
            "received_count": 1,
            "unique_application_identity_count": 1,
        },
        {
            "alias": "삼성물산(주)",
            "query_attempted": False,
            "received_count": 0,
            "unique_application_identity_count": 0,
        },
    ]


def test_transient_timeout_retries_once_then_succeeds() -> None:
    attempts = []

    def request_get(url, *, params, timeout):
        attempts.append((url, timeout))
        if len(attempts) == 1:
            raise ConnectTimeout("temporary")
        return FakeResponse(fixture("kipris_applicant_live.xml"))

    result = KiprisLiveClient(
        api_key="fixture-key",
        request_get=request_get,
        sleep_func=lambda _: None,
        max_attempts=2,
    ).collect(["삼성물산"], max_pages=1)

    assert result.diagnostic.status == "healthy"
    assert result.diagnostic.attempt_count == 2
    assert len(attempts) == 2


def test_timeout_exhaustion_is_sanitized_transport_error() -> None:
    def request_get(url, *, params, timeout):
        raise ConnectTimeout(f"{url}?accessKey=fixture-key")

    result = KiprisLiveClient(
        api_key="fixture-key",
        request_get=request_get,
        sleep_func=lambda _: None,
        max_attempts=2,
    ).collect(["삼성물산"], max_pages=1)
    serialized = json.dumps(result.diagnostic.as_dict(), ensure_ascii=False)

    assert result.diagnostic.status == "transport_error"
    assert result.diagnostic.final_exception_type == "ConnectTimeout"
    assert result.diagnostic.attempt_count == 2
    assert "fixture-key" not in serialized
    assert "accessKey=" not in serialized


def test_authentication_failure_is_not_retried_or_leaked() -> None:
    calls = 0

    def request_get(url, *, params, timeout):
        nonlocal calls
        calls += 1
        return FakeResponse("<error>denied</error>", status_code=403)

    result = KiprisLiveClient(
        api_key="fixture-key",
        request_get=request_get,
        sleep_func=lambda _: None,
        max_attempts=3,
    ).collect(["삼성물산"], max_pages=1)

    assert calls == 1
    assert result.diagnostic.status == "authentication_denied"
    assert result.diagnostic.http_status == 403
    assert "fixture-key" not in json.dumps(result.diagnostic.as_dict())


def test_api_result_authentication_failure_is_classified_without_retry() -> None:
    payload = "<response><resultCode>30</resultCode><resultMsg>INVALID SERVICE KEY</resultMsg></response>"
    calls = 0

    def request_get(url, *, params, timeout):
        nonlocal calls
        calls += 1
        return FakeResponse(payload)

    result = KiprisLiveClient(
        api_key="fixture-key",
        request_get=request_get,
        max_attempts=3,
    ).collect(["삼성물산"], max_pages=1)

    assert calls == 1
    assert result.diagnostic.status == "authentication_denied"
    assert result.diagnostic.api_result_code == "30"


def test_empty_result_is_explicit_for_each_source() -> None:
    kipris = KiprisLiveClient(
        api_key="fixture-key",
        request_get=lambda *args, **kwargs: FakeResponse(
            "<response><resultCode>00</resultCode><items/><totalSearchCount>0</totalSearchCount></response>"
        ),
    ).collect(["삼성물산"], max_pages=1)
    kaia = KaiaLiveClient(
        api_key="fixture-key",
        request_get=lambda *args, **kwargs: FakeResponse("<response><cnt>0</cnt></response>"),
    ).collect(designation_numbers=["1005"])

    assert kipris.diagnostic.status == "empty_result"
    assert kaia.diagnostic.status == "empty_result"


def test_kaia_request_uses_official_parameter_contract() -> None:
    calls = []

    def request_get(url, *, params, timeout):
        calls.append((url, dict(params), timeout))
        return FakeResponse(fixture("kaia_newtech_live.xml"))

    result = KaiaLiveClient(
        api_key="fixture-key",
        request_get=request_get,
    ).collect(
        designation_numbers=["1005"],
        page_size=10,
        max_records=10,
        collected_at="2026-08-23T00:00:00+00:00",
    )

    assert result.diagnostic.status == "healthy"
    assert result.diagnostic.received_count == 1
    assert calls == [(
        KAIA_NEWTECH_ENDPOINT,
        {"apiKey": "fixture-key", "apntNo": "1005", "firstIndex": 1, "lastIndex": 10},
        (5, 20),
    )]


def test_credentials_are_removed_from_raw_text_and_diagnostics() -> None:
    response = FakeResponse(
        "<response><requestUrl>https://example.test?apiKey=fixture-key</requestUrl><cnt>0</cnt></response>"
    )
    sanitized = sanitize_response_text(response, secrets=("fixture-key",))

    assert "fixture-key" not in sanitized
    assert "apiKey=" not in sanitized
    assert artifact_contains_credentials(sanitized, secrets=("fixture-key",)) is False


def test_kaia_unavailable_does_not_invalidate_healthy_kipris(tmp_path: Path) -> None:
    kipris = KiprisLiveClient(
        api_key="fixture-key",
        request_get=lambda *args, **kwargs: FakeResponse(fixture("kipris_applicant_live.xml")),
    )
    kaia = KaiaLiveClient(api_key="")
    summary = run_live_acceptance(
        companies_path=COMPANIES,
        output_dir=tmp_path / "partial",
        kipris_client=kipris,
        kaia_client=kaia,
        collected_at="2026-08-23T00:00:00+00:00",
        protected_before=hash_files(PROTECTED_PUBLIC_FILES),
    )

    assert summary["metrics"]["source"] == {
        "kipris_status": "healthy",
        "kaia_status": "authentication_denied",
    }
    assert summary["acceptance_decision"] == "PARTIAL_SOURCE_ACCEPTANCE_KIPRIS_COMPLETE"
    assert summary["metrics"]["security"] == {
        "credential_url_count": 0,
        "secret_exposure_count": 0,
        "raw_public_field_count": 0,
    }
    assert summary["protected_public_data_unchanged"] is True
    assert summary["metrics"]["kipris"]["request_attempted"] is True
    assert summary["metrics"]["kipris"]["request_count"] == sum(
        int(row["query_attempted"]) for row in summary["metrics"]["kipris"]["alias_queries"]
    )
    assert summary["metrics"]["kipris"]["unique_identity_count"] == 2


def test_net_new_detail_preserves_live_enrichment_fields() -> None:
    rows, _, _, _ = parse_kipris_applicant_response(fixture("kipris_applicant_live.xml"))
    record = normalize_fixture_records([rows[0]]).records[0]
    detail = build_acceptance_detail([], [record], {
        "decisions": [{
            "category": "net_new",
            "identity": record.identity_key(),
            "source": record.source,
            "external_id": record.external_id,
            "title": record.title,
            "relevance": {"level": "direct"},
        }],
    })

    assert {
        "applicants",
        "application_date",
        "registration_date",
        "status",
        "technology_area",
    }.issubset(detail["net_new_records"][0])


def test_acceptance_run_is_deterministic_with_fixed_inputs(tmp_path: Path) -> None:
    def run(output: Path):
        return run_live_acceptance(
            companies_path=COMPANIES,
            output_dir=output,
            kipris_client=KiprisLiveClient(
                api_key="fixture-key",
                request_get=lambda *args, **kwargs: FakeResponse(fixture("kipris_applicant_live.xml")),
            ),
            kaia_client=KaiaLiveClient(
                api_key="fixture-key",
                request_get=lambda *args, **kwargs: FakeResponse(fixture("kaia_newtech_live.xml")),
            ),
            collected_at="2026-08-23T00:00:00+00:00",
            protected_before=hash_files(PROTECTED_PUBLIC_FILES),
        )

    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first = run(first_dir)
    second = run(second_dir)

    assert first == second
    assert first["acceptance_decision"] == "SAMSUNG_TECH_LIVE_SOURCE_ACCEPTANCE_COMPLETE"
    first_files = sorted(path.relative_to(first_dir) for path in first_dir.rglob("*") if path.is_file())
    second_files = sorted(path.relative_to(second_dir) for path in second_dir.rglob("*") if path.is_file())
    assert first_files == second_files
    for relative in first_files:
        assert (first_dir / relative).read_bytes() == (second_dir / relative).read_bytes()


def test_acceptance_decision_contract() -> None:
    assert acceptance_decision("healthy", "healthy") == "SAMSUNG_TECH_LIVE_SOURCE_ACCEPTANCE_COMPLETE"
    assert acceptance_decision("healthy", "authentication_denied") == "PARTIAL_SOURCE_ACCEPTANCE_KIPRIS_COMPLETE"
    assert acceptance_decision("authentication_denied", "healthy") == "HOLD_FOR_KIPRIS_ACCESS_APPROVAL"
    assert acceptance_decision("schema_error", "healthy") == "HOLD_FOR_LIVE_SCHEMA_REVIEW"


def test_live_clients_use_verified_https_hosts() -> None:
    assert KIPRIS_APPLICANT_ENDPOINT == (
        "https://plus.kipris.or.kr/openapi/rest/"
        "patUtiModInfoSearchSevice/applicantNameSearchInfo"
    )
    assert KAIA_NEWTECH_ENDPOINT == "https://www.kaia.re.kr/portal/openApi/newtecListData.xml"
