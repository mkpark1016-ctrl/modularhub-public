from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.integrations.technology import (
    KAIA_NEWTECH_CONTRACT,
    KIPRIS_PATENT_CONTRACT,
    CompanyIdentity,
    NormalizedTechnologyRecord,
    assess_modular_relevance,
    match_companies,
    normalize_fixture_records,
    reconcile_technology_records,
)
from scripts.integrations.technology.dry_run import run_dry_run


ROOT = Path(__file__).resolve().parents[1]
COMPANIES_PATH = ROOT / "frontend/public/data/companies/companies.json"
FIXTURE_PATH = ROOT / "tests/fixtures/company_technology/samsung_official_records.json"


def load_samsung() -> dict:
    payload = json.loads(COMPANIES_PATH.read_text(encoding="utf-8"))
    return next(company for company in payload["companies"] if company["company_id"] == "samsung-ct-construction")


def fixture_records() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["records"]


def patent(**overrides) -> NormalizedTechnologyRecord:
    values = {
        "source": "kipris",
        "external_id": "fixture-1",
        "title": "모듈러 건축 유닛 접합 기술",
        "application_number": "10-2026-000001",
        "applicants": ("삼성물산 건설부문",),
    }
    values.update(overrides)
    return NormalizedTechnologyRecord(**values)


def test_official_source_contracts_are_fixture_only_and_use_existing_secret() -> None:
    assert KIPRIS_PATENT_CONTRACT.secret_env == "KIPRIS_API_KEY"
    assert KIPRIS_PATENT_CONTRACT.network_enabled is False
    assert "applicationNumber" in KIPRIS_PATENT_CONTRACT.official_fields
    assert KAIA_NEWTECH_CONTRACT.secret_env is None
    assert KAIA_NEWTECH_CONTRACT.network_enabled is False
    assert {"newtecId", "apntNo", "dvlprNm"}.issubset(KAIA_NEWTECH_CONTRACT.official_fields)


def test_title_is_not_identity_and_same_title_different_numbers_are_preserved() -> None:
    first = patent(application_number="10-2026-000001")
    second = patent(external_id="fixture-2", application_number="10-2026-000002")

    assert first.title == second.title
    assert first.identity_key() != second.identity_key()
    result = normalize_fixture_records([
        {"source": "kipris", "externalId": first.external_id, "inventionTitle": first.title,
         "applicationNumber": first.application_number, "applicantName": "삼성물산 건설부문"},
        {"source": "kipris", "externalId": second.external_id, "inventionTitle": second.title,
         "applicationNumber": second.application_number, "applicantName": "삼성물산 건설부문"},
    ])
    assert len(result.records) == 2
    assert result.duplicate_identity_count == 0


def test_same_application_number_is_deduplicated() -> None:
    result = normalize_fixture_records(fixture_records())

    assert len(result.records) == 8
    assert result.duplicate_identity_count == 1
    assert len({record.identity_key() for record in result.records}) == 8


def test_samsung_fixture_reconciliation_preserves_manual_baseline() -> None:
    normalization = normalize_fixture_records(fixture_records())
    candidates, report = reconcile_technology_records([load_samsung()], normalization)

    assert report["baseline_count"] == 7
    assert report["source_input_count"] == 10
    assert report["normalized_count"] == 8
    assert report["company_matched_count"] == 8
    assert report["existing_matched_count"] == 4
    assert report["manual_only_count"] == 3
    assert report["net_new_count"] == 2
    assert report["conflict_count"] == 0
    assert report["manual_baseline_preserved"] is True
    assert report["identity_uses_title"] is False
    matched_ids = {
        item.get("baseline_technology_id")
        for item in report["decisions"]
        if item["category"] == "matched"
    }
    assert {"tech-samsung-003", "tech-samsung-004"}.issubset(matched_ids)
    excluded = {item["external_id"]: item["category"] for item in report["decisions"]}
    assert excluded["KIPRIS-NON-MOD-1"] == "irrelevant"
    assert excluded["KIPRIS-ELECTRONIC-MODULE-1"] == "irrelevant"
    assert len(candidates) == 6


def test_official_match_can_only_propose_empty_field_enrichment() -> None:
    normalization = normalize_fixture_records(fixture_records())
    candidates, _ = reconcile_technology_records([load_samsung()], normalization)
    candidate = next(item for item in candidates if item["registration_number"] == "10-2388438")

    assert candidate["candidate_type"] == "enrichment_candidate"
    assert candidate["enrichment_fields"] == {
        "application_date": "2020-01-10",
        "application_number": "10-2020-000001",
        "registration_date": "2022-04-12",
    }


def test_modular_relevance_is_deterministic_and_rejects_electronic_module() -> None:
    direct = assess_modular_relevance(patent(title="모듈러 건축 유닛 연결 시스템"))
    adjacent = assess_modular_relevance(patent(title="철골 패널 바닥 구조체 및 현장 시공방법"))
    electronic = assess_modular_relevance(patent(title="통신 장치용 전자 모듈 및 안테나 회로"))
    generic = assess_modular_relevance(patent(title="범용 기계 모듈"))

    assert direct.level == "direct"
    assert adjacent.level == "adjacent"
    assert electronic.level == "irrelevant"
    assert electronic.relevance_reason == "electronic_or_non_construction_module_context"
    assert generic.level == "irrelevant"
    assert "모듈" not in direct.matched_terms


def test_company_matching_supports_alias_ambiguity_and_multiple_companies() -> None:
    record = patent(applicants=("공동기술",))
    ambiguous = match_companies(record, [
        CompanyIdentity("one", ("회사 하나",), ("공동기술",)),
        CompanyIdentity("two", ("회사 둘",), ("공동기술",)),
    ])
    joint = patent(applicants=("회사 하나", "회사 둘"))
    multiple = match_companies(joint, [
        CompanyIdentity("one", ("회사 하나",), ()),
        CompanyIdentity("two", ("회사 둘",), ()),
    ])

    assert ambiguous.outcome == "ambiguous"
    assert ambiguous.company_ids == ()
    assert multiple.outcome == "exact"
    assert multiple.company_ids == ("one", "two")


def test_ambiguous_company_record_is_not_public_candidate() -> None:
    companies = [
        {"company_id": "one", "company_name": "회사 하나", "aliases": ["공동기술"], "technology": {}},
        {"company_id": "two", "company_name": "회사 둘", "aliases": ["공동기술"], "technology": {}},
    ]
    normalization = normalize_fixture_records([
        {"source": "kipris", "externalId": "ambiguous", "inventionTitle": "모듈러 건축 기술",
         "applicationNumber": "10-2026-000008", "applicantName": "공동기술"}
    ])
    candidates, report = reconcile_technology_records(companies, normalization)

    assert report["ambiguous_company_count"] == 1
    assert report["decisions"][0]["category"] == "ambiguous"
    assert candidates == []


def test_credential_bearing_url_and_sensitive_raw_fields_fail_closed() -> None:
    with pytest.raises(ValueError, match="credential"):
        patent(source_url="https://plus.kipris.or.kr/detail?accessKey=do-not-log")

    result = normalize_fixture_records([
        {"source": "kipris", "externalId": "unsafe", "inventionTitle": "모듈러 건축",
         "applicationNumber": "10-2026-000009", "applicantName": "삼성물산", "serviceKey": "do-not-log"}
    ])
    serialized = json.dumps(result.invalid, ensure_ascii=False)
    assert len(result.invalid) == 1
    assert result.credential_exposure_count == 1
    assert "do-not-log" not in serialized


def test_duplicate_baseline_identity_is_a_conflict_not_net_new() -> None:
    companies = [{
        "company_id": "one",
        "company_name": "회사 하나",
        "technology": {
            "patents": [
                {"technology_id": "a", "record_type": "patent", "name": "모듈러 건축 기술",
                 "registration_number": "10-9999999", "status": "registered"},
                {"technology_id": "b", "record_type": "patent", "name": "모듈러 건축 기술",
                 "registration_number": "10-9999999", "status": "registered"},
            ]
        },
    }]
    normalization = normalize_fixture_records([
        {"source": "kipris", "externalId": "collision", "inventionTitle": "모듈러 건축 기술",
         "registrationNumber": "10-9999999", "applicantName": "회사 하나", "registrationStatus": "registered"}
    ])
    candidates, report = reconcile_technology_records(companies, normalization)

    assert report["conflict_count"] == 1
    assert report["net_new_count"] == 0
    assert report["decisions"][0]["category"] == "conflict"
    assert candidates == []


def test_conflicting_same_official_identity_is_not_silently_overwritten() -> None:
    rows = [
        {"source": "kipris", "externalId": "one", "inventionTitle": "모듈러 건축 A",
         "applicationNumber": "10-2026-000010", "applicantName": "삼성물산"},
        {"source": "kipris", "externalId": "two", "inventionTitle": "모듈러 건축 B",
         "applicationNumber": "10-2026-000010", "applicantName": "삼성물산"},
    ]
    result = normalize_fixture_records(rows)

    assert result.duplicate_identity_count == 1
    assert len(result.identity_conflicts) == 1
    assert result.identity_conflicts[0]["differing_fields"] == ["title"]


def test_fixture_dry_run_is_byte_deterministic(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first = run_dry_run(COMPANIES_PATH, FIXTURE_PATH, first_dir)
    second = run_dry_run(COMPANIES_PATH, FIXTURE_PATH, second_dir)

    assert first == second
    assert sorted(path.name for path in first_dir.iterdir()) == sorted(path.name for path in second_dir.iterdir())
    for first_path in first_dir.iterdir():
        assert first_path.read_bytes() == (second_dir / first_path.name).read_bytes()


def test_dry_run_candidates_are_sanitized_and_public_write_is_disabled(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    report = run_dry_run(COMPANIES_PATH, FIXTURE_PATH, output_dir)
    candidates = json.loads((output_dir / "public_projection_candidates.json").read_text(encoding="utf-8"))
    serialized = json.dumps(candidates, ensure_ascii=False).casefold()

    assert report["public_write_performed"] is False
    assert report["credential_exposure_count"] == 1
    assert "fixture-secret" not in serialized
    assert "accesskey" not in serialized
    assert "raw_response" not in serialized
    assert all(item["modular_relevance"] in {"direct", "adjacent"} for item in candidates)
