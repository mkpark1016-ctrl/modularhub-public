from __future__ import annotations

import json
from pathlib import Path

from scripts.integrations.technology import (
    KAIA_MANUAL_BASELINE,
    READY_EXACT_IDENTITY,
    READY_VERIFIED_REGISTRATION_IDENTITY,
    NormalizedTechnologyRecord,
    alias_decision,
    assess_modular_relevance,
    build_exact_lookup_budget,
    build_live_request_plan,
    classify_baseline_identity,
    company_identity_for_alias_contract,
    inventory_company,
    match_companies,
    normalize_fixture_records,
    official_identity_collisions,
    validate_alias_contracts,
)


ROOT = Path(__file__).resolve().parents[1]
COMPANIES_PATH = ROOT / "frontend/public/data/companies/companies.json"
CONFIG_PATH = ROOT / "config/company_technology/kipris_expansion_readiness.json"
TARGET_IDS = ("gs-ec", "hyundai-engineering", "dl-enc")


def _payloads():
    companies = json.loads(COMPANIES_PATH.read_text(encoding="utf-8"))["companies"]
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    company_map = {company["company_id"]: company for company in companies}
    contract_map = {company["company_id"]: company for company in config["companies"]}
    return companies, config, company_map, contract_map


def _patent(applicant: str, **overrides) -> NormalizedTechnologyRecord:
    values = {
        "source": "kipris",
        "external_id": "fixture",
        "title": "모듈러 건축 접합 구조",
        "application_number": "10-2026-0000001",
        "applicants": (applicant,),
    }
    values.update(overrides)
    return NormalizedTechnologyRecord(**values)


def test_exact_alias_matching_is_isolated_for_first_cohort() -> None:
    _, _, company_map, contract_map = _payloads()
    for company_id in TARGET_IDS:
        identity = company_identity_for_alias_contract(company_map[company_id], contract_map[company_id])
        record = _patent(contract_map[company_id]["canonical_applicant"])
        result = match_companies(record, [identity])
        assert result.outcome == "exact"
        assert result.company_ids == (company_id,)


def test_excluded_group_companies_do_not_match() -> None:
    _, _, company_map, contract_map = _payloads()
    excluded = {"gs-ec": "GS칼텍스", "hyundai-engineering": "현대건설", "dl-enc": "DL건설"}
    for company_id, applicant in excluded.items():
        identity = company_identity_for_alias_contract(company_map[company_id], contract_map[company_id])
        assert match_companies(_patent(applicant), [identity]).outcome == "unmatched"
        assert alias_decision(contract_map[company_id], applicant).category == "excluded"


def test_ambiguous_aliases_are_rejected() -> None:
    _, _, _, contracts = _payloads()
    for company_id, alias in {"gs-ec": "GS", "hyundai-engineering": "현대", "dl-enc": "DL"}.items():
        decision = alias_decision(contracts[company_id], alias)
        assert decision.allowed is False
        assert decision.category == "ambiguous"


def test_historical_alias_is_explicit_only() -> None:
    _, _, _, contracts = _payloads()
    contract = contracts["dl-enc"]
    assert alias_decision(contract, "대림산업").allowed is False
    explicit = alias_decision(contract, "대림산업", allow_historical=True)
    assert explicit.allowed is True
    assert explicit.category == "historical_explicit_only"
    assert "대림산업" not in build_live_request_plan(contract, {"page_size": 100, "max_pages_per_alias": 1, "max_records": 200})["planned_alias_order"]


def test_cross_company_alias_contract_has_no_approved_collision() -> None:
    _, config, _, _ = _payloads()
    result = validate_alias_contracts(config["companies"])
    assert result["approved_collisions"] == []
    assert result["historical_collisions"] == []
    assert result["invalid_entries"] == []


def test_application_number_has_identity_priority() -> None:
    record = {
        "record_type": "patent",
        "application_number": "10-2026-0000001",
        "registration_number": "10-1234567",
    }
    assert classify_baseline_identity(record) == READY_EXACT_IDENTITY


def test_same_title_different_identity_is_preserved() -> None:
    result = normalize_fixture_records([
        {"source": "kipris", "externalId": "one", "inventionTitle": "모듈러 유닛 접합부 구조", "applicationNumber": "10-2026-0000001", "applicantName": "현대엔지니어링"},
        {"source": "kipris", "externalId": "two", "inventionTitle": "모듈러 유닛 접합부 구조", "applicationNumber": "10-2026-0000002", "applicantName": "현대엔지니어링"},
    ])
    assert len(result.records) == 2
    assert result.duplicate_identity_count == 0


def test_same_identity_is_detected_as_duplicate() -> None:
    result = normalize_fixture_records([
        {"source": "kipris", "externalId": "one", "inventionTitle": "모듈러 접합 A", "applicationNumber": "10-2026-0000003", "applicantName": "GS건설"},
        {"source": "kipris", "externalId": "two", "inventionTitle": "모듈러 접합 A", "applicationNumber": "10-2026-0000003", "applicantName": "GS건설"},
    ])
    assert result.duplicate_identity_count == 1
    assert len(result.records) == 1


def test_construction_new_technology_is_not_kipris_patent_identity() -> None:
    assert classify_baseline_identity({
        "record_type": "construction_new_technology",
        "registration_number": "건설신기술 제770호",
    }) == KAIA_MANUAL_BASELINE


def test_electronics_and_software_module_false_positives_are_blocked() -> None:
    electronics = assess_modular_relevance(_patent("GS건설", title="통신 장치용 전자 모듈 및 반도체 회로"))
    software = assess_modular_relevance(_patent("현대엔지니어링", title="소프트웨어 모듈 및 데이터 처리 장치"))
    assert electronics.level == "irrelevant"
    assert software.level == "irrelevant"


def test_request_plan_is_deterministic_and_bounded() -> None:
    _, config, _, contracts = _payloads()
    first = build_live_request_plan(contracts["gs-ec"], config["request_defaults"])
    second = build_live_request_plan(contracts["gs-ec"], config["request_defaults"])
    assert first == second
    assert first == {
        "company_id": "gs-ec",
        "planned_alias_order": ["지에스건설 주식회사", "지에스건설", "GS건설"],
        "maximum_pages_per_alias": 1,
        "page_size": 100,
        "maximum_records": 200,
        "maximum_requests": 3,
    }


def test_baseline_inventory_and_exact_lookup_budgets_match_public_baseline() -> None:
    _, _, companies, _ = _payloads()
    expected = {
        "gs-ec": (3, 3, 0, 0),
        "hyundai-engineering": (14, 13, 1, 1),
        "dl-enc": (21, 21, 0, 0),
    }
    for company_id, (total, patents, newtech, duplicate_titles) in expected.items():
        inventory = inventory_company(companies[company_id])
        assert inventory["total_technology_count"] == total
        assert inventory["patent_count"] == patents
        assert inventory["construction_new_technology_count"] == newtech
        assert inventory["duplicate_title_count"] == duplicate_titles
        assert inventory["duplicate_official_identity_count"] == 0
        assert inventory["records_without_official_identifier"] == 0
        assert inventory["readiness_counts"][READY_VERIFIED_REGISTRATION_IDENTITY] == patents
        assert build_exact_lookup_budget(companies[company_id])["maximum_exact_lookup_requests"] == 0


def test_first_cohort_has_no_official_identity_collision_with_samsung() -> None:
    all_companies, _, _, _ = _payloads()
    selected = [company for company in all_companies if company["company_id"] in {*TARGET_IDS, "samsung-ct-construction"}]
    assert official_identity_collisions(selected) == []


def test_artifact_and_publication_isolation_contract() -> None:
    _, config, _, _ = _payloads()
    assert config["artifact_root"] == "artifacts/company-technology/multi-company-live/<company-id>/"
    assert config["publication_sequence"] == list(TARGET_IDS)
    assert "artifacts/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
