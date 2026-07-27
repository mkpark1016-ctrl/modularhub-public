from __future__ import annotations

import json
from copy import deepcopy

from scripts.resolve_company_dart_identities import apply_resolution, normalize_company_name, resolve_identities
from scripts.validate_dart_identity_registry import validate_registry


class FakeOpenDartClient:
    def __init__(self, overviews: dict[str, dict[str, str]]) -> None:
        self.overviews = overviews

    def list_corp_codes(self) -> list[dict[str, str]]:
        return []

    def company_overview(self, corp_code: str) -> dict[str, str]:
        return self.overviews[corp_code]


def identity(company_id: str, legal_name: str, *, domains: list[str] | None = None, aliases: list[str] | None = None) -> dict[str, object]:
    return {
        "companyId": company_id,
        "legalName": legal_name,
        "displayName": legal_name,
        "aliases": aliases or [],
        "formerNames": [],
        "officialDomains": domains or [],
        "corpCode": None,
    }


def registry_row(company_id: str, *, status: str = "not_verified", corp_code: str | None = None) -> dict[str, object]:
    return {
        "companyId": company_id,
        "corpCode": corp_code,
        "mappingStatus": status,
        "identityRisk": "moderate",
        "evidenceType": "official_opendart_registry_and_company_profile" if status == "verified" else "internal_verified_identity_without_dart_code",
    }


def test_dart_identity_registry_contains_all_monitored_companies() -> None:
    identities = {"companies": [identity("a", "주식회사 에이"), identity("b", "주식회사 비")]}
    registry = {"policy": {"corpCodeInferenceAllowed": False}, "companies": [registry_row("a"), registry_row("b")]}
    report = validate_registry(identities=identities, registry=registry, policy={"minimumDartMappingCoverage": 0})
    assert report["expectedCompanyCount"] == 2
    assert report["registryCompanyCount"] == 2
    assert report["valid"] is True


def test_verified_dart_identity_requires_corp_code() -> None:
    identities = {"companies": [{**identity("a", "주식회사 에이"), "corpCode": None}]}
    registry = {"policy": {"corpCodeInferenceAllowed": False}, "companies": [registry_row("a", status="verified", corp_code=None)]}
    report = validate_registry(identities=identities, registry=registry, policy={"minimumDartMappingCoverage": 0})
    assert report["valid"] is False
    assert any(issue["code"] == "verified_missing_corp_code" for issue in report["issues"])


def test_dart_corp_codes_are_unique() -> None:
    identities = {"companies": [{**identity("a", "주식회사 에이"), "corpCode": "00123456"}, {**identity("b", "주식회사 비"), "corpCode": "00123456"}]}
    registry = {
        "policy": {"corpCodeInferenceAllowed": False},
        "companies": [registry_row("a", status="verified", corp_code="00123456"), registry_row("b", status="verified", corp_code="00123456")],
    }
    report = validate_registry(identities=identities, registry=registry, policy={"minimumDartMappingCoverage": 0})
    assert report["duplicateCorpCodeCount"] == 1
    assert report["valid"] is False


def test_company_identity_and_dart_registry_codes_match() -> None:
    identities = {"companies": [{**identity("a", "주식회사 에이"), "corpCode": "00123456"}]}
    registry = {"policy": {"corpCodeInferenceAllowed": False}, "companies": [registry_row("a", status="verified", corp_code="00999999")]}
    report = validate_registry(identities=identities, registry=registry, policy={"minimumDartMappingCoverage": 0})
    assert report["corpCodeMismatchCount"] == 1


def test_dart_mapping_coverage_meets_policy_threshold() -> None:
    identities = {
        "companies": [
            {**identity(str(index), f"주식회사 {index}"), "corpCode": f"0012345{index}" if index < 9 else None}
            for index in range(11)
        ]
    }
    registry = {
        "policy": {"corpCodeInferenceAllowed": False},
        "companies": [
            registry_row(str(index), status="verified", corp_code=f"0012345{index}") if index < 9 else registry_row(str(index))
            for index in range(11)
        ],
    }
    report = validate_registry(identities=identities, registry=registry, policy={"minimumDartMappingCoverage": 0.8})
    assert report["valid"] is True
    assert report["verifiedCompanyCount"] == 9
    assert report["coverageRatio"] == 0.8182


def test_unverified_identity_is_not_inferred_from_alias_only() -> None:
    identities = {"companies": [identity("x", "주식회사 정확", aliases=["별칭회사"])]}
    registry = {"companies": [registry_row("x")]}
    corp_rows = [{"corp_code": "00123456", "corp_name": "별칭회사", "stock_code": "123456", "modify_date": "20260727"}]
    client = FakeOpenDartClient({"00123456": {"status": "000", "corp_name": "별칭회사", "stock_code": "123456"}})
    result = resolve_identities(companies=["x"], client=client, identities=identities, registry=registry, corp_rows=corp_rows)
    assert result["results"][0]["mappingStatus"] == "not_verified"
    assert result["results"][0]["resolvedCorpCode"] is None


def test_ambiguous_legal_name_is_not_auto_applied_without_profile_disambiguation() -> None:
    identities = {"companies": [identity("x", "주식회사 현대엔지니어링", domains=["hec.co.kr"])]}
    registry = {"companies": [registry_row("x")]}
    corp_rows = [
        {"corp_code": "00111111", "corp_name": "현대엔지니어링", "stock_code": "", "modify_date": "20200101"},
        {"corp_code": "00222222", "corp_name": "현대엔지니어링", "stock_code": "", "modify_date": "20200101"},
    ]
    client = FakeOpenDartClient(
        {
            "00111111": {"status": "000", "corp_name": "현대엔지니어링(주)", "stock_code": ""},
            "00222222": {"status": "000", "corp_name": "(주)현대엔지니어링", "stock_code": ""},
        }
    )
    result = resolve_identities(companies=["x"], client=client, identities=identities, registry=registry, corp_rows=corp_rows)
    assert result["results"][0]["mappingStatus"] == "ambiguous"
    assert result["results"][0]["resolvedCorpCode"] is None


def test_dart_resolver_dry_run_does_not_modify_files() -> None:
    identities = {"companies": [identity("a", "주식회사 에이")]}
    registry = {"companies": [registry_row("a")]}
    before_identities = deepcopy(identities)
    before_registry = deepcopy(registry)
    corp_rows = [{"corp_code": "00123456", "corp_name": "에이", "stock_code": "123456", "modify_date": "20260727"}]
    client = FakeOpenDartClient({"00123456": {"status": "000", "corp_name": "에이(주)", "stock_code": "123456"}})
    resolve_identities(companies=["a"], client=client, identities=identities, registry=registry, corp_rows=corp_rows)
    assert identities == before_identities
    assert registry == before_registry


def test_dart_resolver_does_not_expose_secret() -> None:
    identities = {"companies": [identity("a", "주식회사 에이")]}
    registry = {"companies": [registry_row("a")]}
    corp_rows = [{"corp_code": "00123456", "corp_name": "에이", "stock_code": "123456", "modify_date": "20260727"}]
    client = FakeOpenDartClient({"00123456": {"status": "000", "corp_name": "에이(주)", "stock_code": "123456", "jurir_no": "sensitive-value", "bizr_no": "sensitive-value"}})
    result = resolve_identities(companies=["a"], client=client, identities=identities, registry=registry, corp_rows=corp_rows)
    text = json.dumps(result, ensure_ascii=False)
    assert "jurir_no" not in text
    assert "bizr_no" not in text
    assert "sensitive-value" not in text


def test_samsung_construction_uses_corporate_identity_with_manual_review_guard() -> None:
    identities = {"companies": [identity("samsung-ct-construction", "삼성물산 주식회사", aliases=["삼성물산 건설부문"])]}
    registry = {"companies": [registry_row("samsung-ct-construction")]}
    corp_rows = [{"corp_code": "00149655", "corp_name": "삼성물산", "stock_code": "028260", "modify_date": "20260323"}]
    client = FakeOpenDartClient({"00149655": {"status": "000", "corp_name": "삼성물산(주)", "stock_code": "028260"}})
    result = resolve_identities(companies=["samsung-ct-construction"], client=client, identities=identities, registry=registry, corp_rows=corp_rows)
    applied_identities, applied_registry = apply_resolution(result, identities=identities, registry=registry)
    row = applied_registry["companies"][0]
    assert row["corpCode"] == "00149655"
    assert row["mappingStatus"] == "verified"
    assert row["identityRisk"] == "moderate"
    assert applied_identities["companies"][0]["corpCode"] == "00149655"


def test_normalize_company_name_removes_corporate_suffixes() -> None:
    assert normalize_company_name("지에스건설 주식회사") == normalize_company_name("지에스건설(주)")
