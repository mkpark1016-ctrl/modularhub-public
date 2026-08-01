from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import scripts.validate_company_audit_financials as validator_module
from scripts.validate_company_audit_financials import (
    DEFAULT_INPUT,
    PROTECTED_PUBLIC_FILES,
    REQUIRED_BORROWING_FIELDS,
    REQUIRED_REVENUE_FIELDS,
    SOURCE_SECTION_BY_PARENT,
    SOURCE_SECTION_CODES,
    aggregate_reported,
    calculate_derived_metrics,
    contains_key,
    is_allowed_nrb_public_financial_summary_update,
    protected_public_diff_status,
    validate,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "company_reports" / "company_audit_financials_v1.schema.json"
KUMKANG_INPUT = ROOT / "data" / "company_reports" / "kumkang-kind" / "audit_financials_2023_2025.json"
DAESEUNG_INPUT = ROOT / "data" / "company_reports" / "daeseung-engineering" / "audit_financials_2023_2025.json"
PLANM_INPUT = ROOT / "data" / "company_reports" / "planm" / "audit_financials_2023_2025.json"
EXPECTED_REPORTED_VALUES = {
    "2023": {
        "revenue": 419041119841,
        "gross_profit": 26668499293,
        "operating_profit": 16108176475,
        "net_income": 17590723723,
        "total_assets": 224437469439,
        "total_liabilities": 171736412877,
        "total_equity": 52701056562,
    },
    "2024": {
        "revenue": 364024587969,
        "gross_profit": 33304897232,
        "operating_profit": 9124197103,
        "net_income": 10850960336,
        "total_assets": 210303317036,
        "total_liabilities": 147153608014,
        "total_equity": 63149709022,
    },
    "2025": {
        "revenue": 307684467052,
        "gross_profit": 33339609191,
        "operating_profit": 14867615594,
        "net_income": 5662989075,
        "total_assets": 270984904156,
        "total_liabilities": 200386015125,
        "total_equity": 70598889031,
    },
}
KUMKANG_EXPECTED_REPORTED_VALUES = {
    "2023": {
        "revenue": 856892700510,
        "gross_profit": 158067345706,
        "operating_profit": 66582089210,
        "net_income": 44788076295,
        "operating_cash_flow": 49382174440,
        "total_borrowings": 465321329651,
        "trade_receivables_gross": 142670856935,
        "receivables_total": 194543903760,
    },
    "2024": {
        "revenue": 801352012454,
        "gross_profit": 126755039109,
        "operating_profit": 33048202059,
        "net_income": 16844230742,
        "operating_cash_flow": 13010958488,
        "total_borrowings": 502257459579,
        "trade_receivables_gross": 154093751180,
        "receivables_total": 212687664676,
    },
    "2025": {
        "revenue": 802156014802,
        "gross_profit": 122216321060,
        "operating_profit": 10497395028,
        "net_income": -37353541440,
        "operating_cash_flow": 21874636165,
        "total_borrowings": 513762323953,
        "trade_receivables_gross": 150430873249,
        "receivables_total": 185921585924,
    },
}
DAESEUNG_EXPECTED_REPORTED_VALUES = {
    "2023": {
        "revenue": 32326080148,
        "gross_profit": 7530500530,
        "operating_profit": 4109790546,
        "net_income": 3009792401,
        "operating_cash_flow": 59283840033,
        "total_borrowings": 8442844880,
        "trade_receivables_gross": 1407373616,
        "receivables_total": 2589969463,
        "rental_revenue": 16324555370,
    },
    "2024": {
        "revenue": 84005687052,
        "gross_profit": 15685352450,
        "operating_profit": 10058636613,
        "net_income": 5203952176,
        "operating_cash_flow": 26430939883,
        "total_borrowings": 28842700552,
        "trade_receivables_gross": 1908992362,
        "receivables_total": 3632795139,
        "rental_revenue": 66404136368,
    },
    "2025": {
        "revenue": 61659861549,
        "gross_profit": 12681852632,
        "operating_profit": 6365339970,
        "net_income": 4376654645,
        "operating_cash_flow": -345400575,
        "total_borrowings": 53164938435,
        "trade_receivables_gross": 3165203872,
        "receivables_total": 3418283872,
        "rental_revenue": 25082978186,
    },
}


def load_payload() -> dict:
    return json.loads(DEFAULT_INPUT.read_text(encoding="utf-8"))


def load_kumkang_payload() -> dict:
    return json.loads(KUMKANG_INPUT.read_text(encoding="utf-8"))


def load_daeseung_payload() -> dict:
    return json.loads(DAESEUNG_INPUT.read_text(encoding="utf-8"))


def load_planm_staging_payload() -> dict:
    return json.loads(PLANM_INPUT.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def reported(record: dict, section: str, field: str) -> int:
    return record[section][field]["reported"]


def set_amount_unavailable(payload: dict, year: str, section: str, field: str, status: str = "not_disclosed") -> dict:
    metric = payload["financial_years"][year][section][field]
    metric["reported"] = None
    metric["disclosure_status"] = status
    metric["notes"] = f"Synthetic {status} test case."
    return metric


def schema_errors(payload: dict) -> list:
    validator = Draft202012Validator(load_schema())
    return sorted(validator.iter_errors(payload), key=lambda error: list(error.path))


def synthetic_company_payload() -> dict:
    payload = deepcopy(load_payload())
    payload["company_id"] = "sample-company"
    payload["company_name"] = "Sample Company"
    payload["reporting_entity"] = "Sample Company"
    payload["financial_years"] = {
        "2024": payload["financial_years"]["2023"],
        "2025": payload["financial_years"]["2024"],
        "2026": payload["financial_years"]["2025"],
    }
    payload["source_priority"] = {
        "2024": payload["source_priority"]["2023"],
        "2025": payload["source_priority"]["2024"],
        "2026": payload["source_priority"]["2025"],
    }
    for priority in payload["source_priority"].values():
        priority.pop("cross_check_source_refs", None)
    payload["financial_years"]["2026"]["cash_flow"]["operating_cash_flow"]["reported"] = 30830315410
    payload["entity_attribution"] = {
        "reporting_entity": "Sample Company",
        "financial_scope": "standalone",
        "related_entity_attribution_required": False,
        "modular_segment_revenue_disclosed": False,
        "attribution_warning": "Sample Company standalone financial information. Related entities are not automatically combined.",
        "special_events": [],
    }
    payload["validation_metadata"]["expected_years"] = [2024, 2025, 2026]
    payload["validation_metadata"]["validation_policy"] = {
        "forbidden_field_names": ["modular_revenue", "derived", "inference"]
    }
    return payload


def test_json_schema_contract_is_complete() -> None:
    schema = load_schema()
    defs = schema["$defs"]
    assert schema["properties"]["financial_years"]["$ref"] == "#/$defs/financialYears"
    assert defs["financialYears"]["patternProperties"]["^[0-9]{4}$"]["$ref"] == "#/$defs/financialYear"
    assert defs["financialYears"]["additionalProperties"] is False
    assert defs["sourcePriorityByYear"]["patternProperties"]["^[0-9]{4}$"]["$ref"] == "#/$defs/sourcePriority"
    assert defs["sourcePriorityByYear"]["additionalProperties"] is False
    assert defs["financialYear"]["required"] == [
        "income_statement",
        "balance_sheet",
        "cash_flow",
        "revenue_breakdown",
        "working_capital",
        "borrowings",
        "investment_signals",
        "source_refs",
    ]
    assert defs["incomeStatement"]["properties"]["revenue"]["$ref"] == "#/$defs/reportedAmount"
    assert "source_locations" in defs["reportedAmount"]["properties"]
    assert defs["reportedAmount"]["additionalProperties"] is False
    assert "verification_pending" in defs["reportedAmount"]["properties"]["disclosure_status"]["enum"]
    assert "auditor_report_date_verification_status" in defs["auditOpinion"]["properties"]
    assert "auditor_report_date_verification_status" in defs["sourceDocument"]["properties"]
    assert defs["entityAttribution"]["properties"]["financial_scope"]["enum"] == ["standalone", "consolidated", "standalone_and_consolidated"]
    assert "specialEvent" in defs
    assert "validationPolicy" in defs


def test_schema_accepts_verification_pending_null_amounts() -> None:
    payload = load_planm_staging_payload()
    metric = payload["financial_years"]["2023"]["balance_sheet"]["total_equity"]
    assert metric["reported"] is None
    assert metric["disclosure_status"] == "verification_pending"
    assert metric["notes"]
    assert metric["source_refs"]
    assert metric["source_locations"]
    assert schema_errors(payload) == []


def test_planm_staging_text_integrity_and_identity_fields() -> None:
    text = PLANM_INPUT.read_text(encoding="utf-8")
    payload = load_planm_staging_payload()
    assert "???" not in text
    assert "??" not in text
    assert "\ufffd" not in text
    assert payload["company_name"] == "플랜엠"
    assert payload["reporting_entity"] == "주식회사 플랜엠"
    assert payload["accounting_standard"]["label_ko"] == "일반기업회계기준"
    assert payload["entity_attribution"]["reporting_entity"] == "주식회사 플랜엠"


def test_planm_staging_modular_revenue_and_opinion_semantics() -> None:
    payload = load_planm_staging_payload()
    warning = payload["entity_attribution"]["attribution_warning"]
    assert payload["entity_attribution"]["modular_segment_revenue_disclosed"] is False
    for term in ["별도 재무제표", "모듈러 매출", "verification_pending"]:
        assert term in warning
        assert term in payload["validation_metadata"]["validation_policy"]["required_attribution_warning_terms"]
    limitations = "\n".join(payload["disclosure_limitations"])
    for term in [
        "감사보고서에서는 모듈러 사업부문 별도 매출을 공시하지 않음",
        "제품매출은 모듈러 매출로 자동 간주하지 않음",
        "임대매출은 모듈러 매출로 자동 간주하지 않음",
        "용역 및 F&B 매출은 모듈러 매출로 자동 간주하지 않음",
    ]:
        assert term in limitations
    assert {opinion["opinion"] for opinion in payload["audit_opinions"]} == {"unqualified"}
    assert {opinion["opinion_label_ko"] for opinion in payload["audit_opinions"]} == {"적정의견"}
    assert {document["audit_opinion"] for document in payload["source_documents"].values()} == {"적정의견"}
    assert all(event["related_entities"] == [] for event in payload["entity_attribution"]["special_events"])


def test_schema_rejects_verification_pending_reported_zero() -> None:
    payload = load_planm_staging_payload()
    metric = payload["financial_years"]["2023"]["balance_sheet"]["total_equity"]
    metric["reported"] = 0
    errors = schema_errors(payload)
    assert errors
    result = validate(payload, base_ref=None)
    assert not result["valid"]
    assert any(issue["code"] == "invalid_disclosure_status_for_reported_amount" for issue in result["issues"])


def test_verification_pending_is_distinct_from_not_disclosed_and_not_applicable() -> None:
    assert aggregate_reported([
        {"reported": None, "disclosure_status": "verification_pending"},
        {"reported": 10, "disclosure_status": "reported"},
    ]) == {"reported": None, "disclosure_status": "verification_pending"}
    assert aggregate_reported([
        {"reported": None, "disclosure_status": "not_disclosed"},
        {"reported": 10, "disclosure_status": "reported"},
    ]) == {"reported": None, "disclosure_status": "not_disclosed"}
    assert aggregate_reported([
        {"reported": None, "disclosure_status": "not_applicable"},
        {"reported": 10, "disclosure_status": "reported"},
    ]) == {"reported": 10, "disclosure_status": "reported"}


def test_planm_staging_validator_passes_with_warning_only() -> None:
    result = validate(load_planm_staging_payload(), base_ref=None)
    assert result["valid"], result["issues"]
    assert result["company_id"] == "planm"
    assert result["financial_years_loaded"] == ["2023", "2024", "2025"]
    assert any(issue["code"] == "accounting_equation_unavailable" and issue["severity"] == "warning" for issue in result["issues"])


def test_planm_2023_total_equity_is_excluded_from_derived_calculations() -> None:
    payload = load_planm_staging_payload()
    metric = payload["financial_years"]["2023"]["balance_sheet"]["total_equity"]
    assert metric["reported"] is None
    assert metric["disclosure_status"] == "verification_pending"
    derived = calculate_derived_metrics(payload)
    assert derived["2023"]["liabilities_to_equity_pct"] is None
    assert derived["2023"]["borrowings_to_equity_pct"] is None


def test_planm_2023_total_equity_uses_restatement_note_cross_check_location() -> None:
    payload = load_planm_staging_payload()
    metric = payload["financial_years"]["2023"]["balance_sheet"]["total_equity"]
    assert metric["reported"] is None
    assert metric["disclosure_status"] == "verification_pending"
    assert metric["source_locations"][1] == {
        "source_ref": "planm_audit_report_2026_06_25",
        "page_range": "48,50",
        "section": "note.restatement",
        "verification_status": "verified_section_range",
    }
    allowed = payload["validation_metadata"]["validation_policy"]["allowed_cross_check_year_mismatches"]
    assert allowed == [
        {
            "year": 2023,
            "source_ref": "planm_audit_report_2026_06_25",
            "reason": "2026년 감사보고서 주석 23이 2024년 기초 이익잉여금 조정을 통해 2023년말 자본총계 검증에 영향을 주기 때문",
            "source_locations": [metric["source_locations"][1]],
        }
    ]


def test_unlisted_cross_check_year_mismatch_still_fails() -> None:
    payload = load_planm_staging_payload()
    payload["validation_metadata"]["validation_policy"]["allowed_cross_check_year_mismatches"] = []
    result = validate(payload, base_ref=None)
    assert not result["valid"]
    issue_codes = {issue["code"] for issue in result["issues"]}
    assert "cross_check_source_year_mismatch" in issue_codes
    assert "source_location_parent_section_mismatch" in issue_codes


def test_planm_source_priority_and_selected_values_follow_restatement_policy() -> None:
    payload = load_planm_staging_payload()
    priority = payload["source_priority"]
    assert priority["2023"]["primary_source_ref"] == "planm_audit_report_2025_04_24"
    assert priority["2023"]["basis"] == "comparative_financial_statements"
    assert "planm_audit_report_2026_06_25" in priority["2023"]["cross_check_source_refs"]
    assert priority["2024"] == {
        "primary_source_ref": "planm_audit_report_2026_06_25",
        "basis": "comparative_financial_statements",
        "cross_check_source_refs": ["planm_audit_report_2025_04_24"],
    }
    assert priority["2025"] == {
        "primary_source_ref": "planm_audit_report_2026_06_25",
        "basis": "current_year_financial_statements",
        "cross_check_source_refs": [],
    }
    assert payload["financial_years"]["2024"]["income_statement"]["net_income"]["reported"] == 38537785703
    assert payload["financial_years"]["2024"]["balance_sheet"]["total_equity"]["reported"] == 70222157519
    assert payload["financial_years"]["2025"]["income_statement"]["revenue"]["reported"] == 59222859418
    assert payload["financial_years"]["2025"]["income_statement"]["net_income"]["reported"] == -9533441167


def test_curated_dataset_matches_schema() -> None:
    assert schema_errors(load_payload()) == []


def test_custom_financial_validator_passes() -> None:
    result = validate(load_payload(), base_ref=None)
    assert result["valid"], result["issues"]
    assert result["schema_version"] == "company_audit_financials_v1"
    assert result["financial_years_loaded"] == ["2023", "2024", "2025"]
    assert result["expected_years"] == ["2023", "2024", "2025"]


def test_schema_rejects_missing_financial_year_section() -> None:
    payload = deepcopy(load_payload())
    del payload["financial_years"]["2025"]["cash_flow"]
    errors = schema_errors(payload)
    assert any("cash_flow" in error.message for error in errors)


def test_schema_rejects_unknown_metric_field() -> None:
    payload = deepcopy(load_payload())
    payload["financial_years"]["2025"]["income_statement"]["unexpected_metric"] = {
        "reported": 1,
        "source_refs": ["yuchang_audit_report_2026_04_08"],
    }
    errors = schema_errors(payload)
    assert any("Additional properties" in error.message for error in errors)


def test_schema_accepts_generic_2024_to_2026_company() -> None:
    assert schema_errors(synthetic_company_payload()) == []


def test_validator_accepts_generic_company_without_yuchang_specific_policy() -> None:
    payload = synthetic_company_payload()
    result = validate(payload, base_ref=None)
    assert result["valid"], result["issues"]
    assert result["company_id"] == "sample-company"
    assert result["expected_years"] == ["2024", "2025", "2026"]
    assert "유창엠앤씨" not in payload["entity_attribution"]["attribution_warning"]


def test_validator_rejects_reported_value_without_source_refs() -> None:
    payload = deepcopy(load_payload())
    del payload["financial_years"]["2025"]["income_statement"]["revenue"]["source_refs"]
    result = validate(payload, base_ref=None)
    assert not result["valid"]
    assert any(issue["code"] == "missing_source_refs" for issue in result["issues"])


def test_reported_amount_source_locations_are_valid() -> None:
    payload = load_payload()
    result = validate(payload, base_ref=None)
    assert result["valid"], result["issues"]
    locations = [
        location
        for _, amount_record in validator_module.money_paths(payload["financial_years"])
        for location in amount_record.get("source_locations", [])
    ]
    assert len(locations) == 84
    assert sum(1 for location in locations if location["verification_status"] == "pending_manual_page_check") == 45
    assert sum(1 for location in locations if location["verification_status"] == "verified_section_range") == 39
    assert all(location["section"] in SOURCE_SECTION_CODES for location in locations)
    assert all("?" not in location["section"] for location in locations)


def test_source_location_sections_match_parent_financial_section() -> None:
    payload = load_payload()
    for year, record in payload["financial_years"].items():
        for parent_section, expected_code in SOURCE_SECTION_BY_PARENT.items():
            for metric_name, metric in record[parent_section].items():
                for location in metric.get("source_locations", []):
                    assert location["section"] == expected_code, (year, parent_section, metric_name)


def test_validator_rejects_corrupted_or_mismatched_source_location_section() -> None:
    payload = deepcopy(load_payload())
    payload["financial_years"]["2025"]["income_statement"]["revenue"]["source_locations"][0]["section"] = "?????"
    result = validate(payload, base_ref=None)
    assert not result["valid"]
    assert any(issue["code"] == "corrupted_source_location_section" for issue in result["issues"])

    payload = deepcopy(load_payload())
    payload["financial_years"]["2025"]["income_statement"]["revenue"]["source_locations"][0]["section"] = "note.borrowings"
    result = validate(payload, base_ref=None)
    assert not result["valid"]
    assert any(issue["code"] == "source_location_parent_section_mismatch" for issue in result["issues"])


def test_expected_years_are_read_from_dataset_metadata() -> None:
    payload = deepcopy(load_payload())
    payload["validation_metadata"]["expected_years"] = [2024, 2025]
    result = validate(payload, base_ref=None)
    assert not result["valid"]
    assert any(issue["code"] == "financial_years_mismatch" for issue in result["issues"])


def test_source_priority_years_must_match_expected_years() -> None:
    payload = deepcopy(load_payload())
    payload["source_priority"]["2026"] = payload["source_priority"]["2025"]
    result = validate(payload, base_ref=None)
    assert not result["valid"]
    assert any(issue["code"] == "source_priority_years_mismatch" for issue in result["issues"])


def test_cross_check_source_must_cover_the_financial_year() -> None:
    payload = load_daeseung_payload()
    payload["source_priority"]["2023"]["cross_check_source_refs"] = [
        "daeseung_audit_report_2024_09_19",
        "daeseung_audit_report_2025_09_17",
    ]
    result = validate(payload, base_ref=None)
    assert not result["valid"]
    assert any(issue["code"] == "cross_check_source_year_mismatch" and issue["source"] == "2023" for issue in result["issues"])


def test_base_ref_missing_returns_explicit_warning() -> None:
    status = protected_public_diff_status(base_ref="refs/heads/definitely-not-a-real-base-ref")
    assert status["mode"] == "worktree"
    assert status["changed_files"] == []
    assert status["warnings"]


def test_protected_file_change_in_branch_diff_fails_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        validator_module,
        "protected_public_diff_status",
        lambda base_ref=None: {
            "mode": "branch_vs_base",
            "base_ref": base_ref,
            "changed_files": ["frontend/public/data/news.json"],
            "warnings": [],
        },
    )
    result = validator_module.validate(load_payload(), base_ref="origin/main")
    assert not result["valid"]
    assert any(issue["code"] == "protected_public_file_changed" for issue in result["issues"])


def test_assets_equal_liabilities_plus_equity() -> None:
    for year, record in load_payload()["financial_years"].items():
        assert reported(record, "balance_sheet", "total_assets") == (
            reported(record, "balance_sheet", "total_liabilities") + reported(record, "balance_sheet", "total_equity")
        ), year


def test_revenue_breakdown_equals_revenue() -> None:
    fields = ["goods_revenue", "product_revenue", "construction_revenue", "rental_revenue", "other_revenue"]
    for year, record in load_payload()["financial_years"].items():
        assert reported(record, "income_statement", "revenue") == sum(reported(record, "revenue_breakdown", field) for field in fields), year


def test_borrowing_total_is_calculated_from_reported_values() -> None:
    derived = calculate_derived_metrics(load_payload())
    expected = {"2023": 40000000000, "2024": 63500000000, "2025": 112134492523}
    for year, total in expected.items():
        record = load_payload()["financial_years"][year]
        assert sum(record["borrowings"][field]["reported"] for field in REQUIRED_BORROWING_FIELDS) == total
        assert derived[year]["total_borrowings"] == total


def test_cash_flow_signs_are_preserved() -> None:
    payload = load_payload()
    assert reported(payload["financial_years"]["2023"], "cash_flow", "operating_cash_flow") > 0
    assert reported(payload["financial_years"]["2024"], "cash_flow", "operating_cash_flow") < 0
    assert reported(payload["financial_years"]["2025"], "cash_flow", "operating_cash_flow") < 0
    assert reported(payload["financial_years"]["2023"], "cash_flow", "investing_cash_flow") < 0
    assert reported(payload["financial_years"]["2024"], "cash_flow", "investing_cash_flow") < 0
    assert reported(payload["financial_years"]["2025"], "cash_flow", "investing_cash_flow") < 0
    result = validate(payload, base_ref=None)
    assert result["valid"], result["issues"]


def test_2025_revenue_breakdown_exact_sum() -> None:
    record = load_payload()["financial_years"]["2025"]
    assert reported(record, "income_statement", "revenue") == 307684467052
    assert (
        reported(record, "revenue_breakdown", "goods_revenue")
        + reported(record, "revenue_breakdown", "product_revenue")
        + reported(record, "revenue_breakdown", "construction_revenue")
        + reported(record, "revenue_breakdown", "rental_revenue")
        + reported(record, "revenue_breakdown", "other_revenue")
    ) == 307684467052


def test_2024_source_priority_uses_2026_comparative_report() -> None:
    priority = load_payload()["source_priority"]["2024"]
    assert priority["primary_source_ref"] == "yuchang_audit_report_2026_04_08"
    assert priority["basis"] == "comparative_financial_statements"


def test_2023_source_priority_uses_2025_comparative_report_with_cross_check() -> None:
    priority = load_payload()["source_priority"]["2023"]
    assert priority["primary_source_ref"] == "yuchang_audit_report_2025_04_04"
    assert priority["basis"] == "comparative_financial_statements"
    assert priority["cross_check_source_refs"] == ["yuchang_audit_report_2024_04_05"]


def test_no_modular_revenue_field_or_derived_values_are_stored() -> None:
    payload = load_payload()
    assert not contains_key(payload, "modular_revenue")
    assert not contains_key(payload, "derived")
    assert not contains_key(payload, "inference")


def test_entity_attribution_warning_exists() -> None:
    attribution = load_payload()["entity_attribution"]
    assert attribution["financial_scope"] == "standalone"
    assert attribution["special_events"][0]["event_type"] == "business_spin_off"
    warning = load_payload()["entity_attribution"]["attribution_warning"]
    assert "주식회사 유창이앤씨 별도 재무제표" in warning
    assert "유창엠앤씨" in warning
    assert "자동 합산하지 않는다" in warning


def test_validator_has_no_company_name_or_cash_flow_sign_hardcoding() -> None:
    source = (ROOT / "scripts" / "validate_company_audit_financials.py").read_text(encoding="utf-8")
    assert "유창엠앤씨" not in source
    assert "expected_signs = {" not in source


def test_public_data_files_are_not_changed() -> None:
    protected = [str(path.relative_to(ROOT)) for path in PROTECTED_PUBLIC_FILES if path.exists()]
    result = subprocess.run(
        ["git", "diff", "--name-only", "--", *protected],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    changed = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if changed == ["frontend/public/data/companies/companies.json"]:
        assert is_allowed_nrb_public_financial_summary_update(None)
    else:
        assert changed == []


def test_existing_yuchang_reported_values_remain_unchanged() -> None:
    payload = load_payload()
    for year, expected in EXPECTED_REPORTED_VALUES.items():
        record = payload["financial_years"][year]
        assert reported(record, "income_statement", "revenue") == expected["revenue"]
        assert reported(record, "income_statement", "gross_profit") == expected["gross_profit"]
        assert reported(record, "income_statement", "operating_profit") == expected["operating_profit"]
        assert reported(record, "income_statement", "net_income") == expected["net_income"]
        assert reported(record, "balance_sheet", "total_assets") == expected["total_assets"]
        assert reported(record, "balance_sheet", "total_liabilities") == expected["total_liabilities"]
        assert reported(record, "balance_sheet", "total_equity") == expected["total_equity"]


def test_kumkang_dataset_matches_schema_and_validator() -> None:
    payload = load_kumkang_payload()
    assert payload["company_id"] == "kumkang-kind"
    assert payload["entity_attribution"]["financial_scope"] == "consolidated"
    assert schema_errors(payload) == []
    result = validate(payload, base_ref=None)
    assert result["valid"], result["issues"]
    assert result["financial_years_loaded"] == ["2023", "2024", "2025"]


def test_kumkang_2024_corrected_report_has_priority() -> None:
    priority = load_kumkang_payload()["source_priority"]["2024"]
    assert priority["primary_source_ref"] == "kumkang_corrected_annual_report_2025_03_19"
    assert priority["basis"] == "current_year_financial_statements"
    assert priority["cross_check_source_refs"] == ["kumkang_annual_report_2026_03_12"]


def test_kumkang_2023_primary_source_matches_source_priority() -> None:
    priority = load_kumkang_payload()["source_priority"]["2023"]
    assert priority["primary_source_ref"] == "kumkang_annual_report_2024_03_14"
    assert priority["basis"] == "current_year_financial_statements"
    assert priority["cross_check_source_refs"] == [
        "kumkang_corrected_annual_report_2025_03_19",
        "kumkang_annual_report_2026_03_12",
    ]


def test_kumkang_auditor_report_date_is_not_copied_from_report_date() -> None:
    payload = load_kumkang_payload()
    for opinion in payload["audit_opinions"]:
        document = payload["source_documents"][opinion["source_ref"]]
        assert opinion["auditor_report_date"] is None
        assert document["auditor_report_date"] is None
        assert opinion["auditor_report_date_verification_status"] == "not_located_in_attached_business_report_pdf"
        assert document["auditor_report_date_verification_status"] == "not_located_in_attached_business_report_pdf"
        assert document["report_date"] is not None


def test_kumkang_reported_checkpoint_values_are_preserved() -> None:
    payload = load_kumkang_payload()
    derived = calculate_derived_metrics(payload)
    for year, expected in KUMKANG_EXPECTED_REPORTED_VALUES.items():
        record = payload["financial_years"][year]
        assert reported(record, "income_statement", "revenue") == expected["revenue"]
        assert reported(record, "income_statement", "gross_profit") == expected["gross_profit"]
        assert reported(record, "income_statement", "operating_profit") == expected["operating_profit"]
        assert reported(record, "income_statement", "net_income") == expected["net_income"]
        assert reported(record, "cash_flow", "operating_cash_flow") == expected["operating_cash_flow"]
        assert derived[year]["total_borrowings"] == expected["total_borrowings"]
        assert reported(record, "working_capital", "trade_receivables_gross") == expected["trade_receivables_gross"]
        assert derived[year]["receivables_total"] == expected["receivables_total"]


def test_kumkang_negative_2025_net_income_and_positive_cash_flows_are_preserved() -> None:
    payload = load_kumkang_payload()
    assert reported(payload["financial_years"]["2025"], "income_statement", "net_income") < 0
    for year in ["2023", "2024", "2025"]:
        assert reported(payload["financial_years"][year], "cash_flow", "operating_cash_flow") > 0
    result = validate(payload, base_ref=None)
    assert result["valid"], result["issues"]


def test_kumkang_trade_receivables_are_distinct_from_receivables_total() -> None:
    payload = load_kumkang_payload()
    derived = calculate_derived_metrics(payload)
    for year, expected in KUMKANG_EXPECTED_REPORTED_VALUES.items():
        trade_receivables = reported(payload["financial_years"][year], "working_capital", "trade_receivables_gross")
        assert trade_receivables == expected["trade_receivables_gross"]
        assert derived[year]["receivables_total"] == expected["receivables_total"]
        assert trade_receivables != derived[year]["receivables_total"]


def test_kumkang_source_locations_are_present_without_unknown_fields() -> None:
    payload = load_kumkang_payload()
    locations = [
        location
        for _, amount_record in validator_module.money_paths(payload["financial_years"])
        for location in amount_record.get("source_locations", [])
    ]
    assert len(locations) == 84
    assert all(location["verification_status"] == "verified_section_range" for location in locations)
    assert all(location.get("page_range") for location in locations)
    assert all(location["section"] in SOURCE_SECTION_CODES for location in locations)
    assert not contains_key(payload, "source_type")
    assert not contains_key(payload, "financial_statement_scope")


def test_daeseung_dataset_matches_schema_and_validator() -> None:
    payload = load_daeseung_payload()
    assert payload["company_id"] == "daeseung-engineering"
    assert payload["company_name"] == "대승엔지니어링"
    assert payload["reporting_entity"] == "주식회사 대승엔지니어링"
    assert payload["accounting_standard"]["code"] == "korean_gaap"
    assert payload["entity_attribution"]["financial_scope"] == "standalone"
    assert payload["validation_metadata"]["expected_years"] == [2023, 2024, 2025]
    assert sorted(payload["financial_years"]) == ["2023", "2024", "2025"]
    assert "2022" not in payload["financial_years"]
    assert schema_errors(payload) == []
    result = validate(payload, base_ref=None)
    assert result["valid"], result["issues"]
    assert result["financial_years_loaded"] == ["2023", "2024", "2025"]


def test_daeseung_report_dates_and_auditor_report_dates_are_distinct() -> None:
    payload = load_daeseung_payload()
    expected = {
        "2023": ("2023-09-19", "2023-09-11"),
        "2024": ("2024-09-19", "2024-09-13"),
        "2025": ("2025-09-17", "2025-09-16"),
    }
    for opinion in payload["audit_opinions"]:
        year = str(opinion["covered_years"][0])
        document = payload["source_documents"][opinion["source_ref"]]
        assert document["report_date"] == expected[year][0]
        assert document["auditor_report_date"] == expected[year][1]
        assert opinion["auditor_report_date"] == expected[year][1]
        assert document["report_date"] != opinion["auditor_report_date"]
        assert opinion["auditor"] == "미립회계법인"
        assert opinion["opinion_label_ko"] == "적정"


def test_daeseung_source_priority_and_cross_checks_are_recorded() -> None:
    priority = load_daeseung_payload()["source_priority"]
    assert priority["2023"]["primary_source_ref"] == "daeseung_audit_report_2023_09_19"
    assert priority["2023"]["basis"] == "current_year_financial_statements"
    assert priority["2023"]["cross_check_source_refs"] == ["daeseung_audit_report_2024_09_19"]
    assert priority["2024"]["primary_source_ref"] == "daeseung_audit_report_2024_09_19"
    assert priority["2024"]["cross_check_source_refs"] == ["daeseung_audit_report_2025_09_17"]
    assert priority["2025"]["primary_source_ref"] == "daeseung_audit_report_2025_09_17"


def test_daeseung_reported_checkpoint_values_are_preserved() -> None:
    payload = load_daeseung_payload()
    derived = calculate_derived_metrics(payload)
    for year, expected in DAESEUNG_EXPECTED_REPORTED_VALUES.items():
        record = payload["financial_years"][year]
        assert reported(record, "income_statement", "revenue") == expected["revenue"]
        assert reported(record, "income_statement", "gross_profit") == expected["gross_profit"]
        assert reported(record, "income_statement", "operating_profit") == expected["operating_profit"]
        assert reported(record, "income_statement", "net_income") == expected["net_income"]
        assert reported(record, "cash_flow", "operating_cash_flow") == expected["operating_cash_flow"]
        assert reported(record, "revenue_breakdown", "rental_revenue") == expected["rental_revenue"]
        assert derived[year]["total_borrowings"] == expected["total_borrowings"]
        assert reported(record, "working_capital", "trade_receivables_gross") == expected["trade_receivables_gross"]
        assert derived[year]["receivables_total"] == expected["receivables_total"]


def test_daeseung_cash_flow_and_modular_rental_disclosure_are_preserved() -> None:
    payload = load_daeseung_payload()
    derived = calculate_derived_metrics(payload)
    assert reported(payload["financial_years"]["2025"], "cash_flow", "operating_cash_flow") < 0
    assert derived["2023"]["rental_revenue_share_pct"] == "50.5"
    assert derived["2024"]["rental_revenue_share_pct"] == "79.0"
    assert derived["2025"]["rental_revenue_share_pct"] == "40.7"
    attribution = payload["entity_attribution"]
    assert attribution["modular_segment_revenue_disclosed"] is True
    warning = attribution["attribution_warning"]
    for term in ["모듈러교실임대료수입", "제품매출", "공사수입금", "관계기업"]:
        assert term in warning
    assert not contains_key(payload, "modular_revenue")
    assert not contains_key(payload, "fy2022")


def test_daeseung_industrial_property_rights_zero_and_reported_amounts_are_preserved() -> None:
    payload = load_daeseung_payload()
    expected = {"2023": 0, "2024": 0, "2025": 3417840}
    expected_refs = {
        "2023": ["daeseung_audit_report_2023_09_19"],
        "2024": ["daeseung_audit_report_2025_09_17"],
        "2025": ["daeseung_audit_report_2025_09_17"],
    }
    for year, amount_value in expected.items():
        metric = payload["financial_years"][year]["investment_signals"]["industrial_property_rights"]
        assert metric["reported"] == amount_value
        assert metric["disclosure_status"] == "reported"
        assert metric["source_refs"] == expected_refs[year]
    assert "explicitly shows" in payload["financial_years"]["2023"]["investment_signals"]["industrial_property_rights"]["notes"]
    assert "comparative balance sheet" in payload["financial_years"]["2024"]["investment_signals"]["industrial_property_rights"]["notes"]


def test_null_reported_amount_requires_not_disclosed_semantics() -> None:
    payload = load_daeseung_payload()
    metric = payload["financial_years"]["2023"]["investment_signals"]["industrial_property_rights"]
    metric["reported"] = None
    metric["disclosure_status"] = "not_disclosed"
    metric["notes"] = "Industrial property rights were not disclosed in this source."
    assert schema_errors(payload) == []
    result = validate(payload, base_ref=None)
    assert result["valid"], result["issues"]


def test_null_reported_amount_is_not_accepted_as_reported_zero() -> None:
    payload = load_daeseung_payload()
    metric = payload["financial_years"]["2023"]["investment_signals"]["industrial_property_rights"]
    metric["reported"] = None
    metric["disclosure_status"] = "reported"
    result = validate(payload, base_ref=None)
    assert not result["valid"]
    assert any(issue["code"] == "invalid_disclosure_status_for_null_reported" for issue in result["issues"])


def test_schema_rejects_null_without_disclosure_status() -> None:
    payload = load_daeseung_payload()
    metric = payload["financial_years"]["2023"]["investment_signals"]["industrial_property_rights"]
    metric["reported"] = None
    metric.pop("disclosure_status", None)
    errors = schema_errors(payload)
    assert errors


@pytest.mark.parametrize("status", ["not_disclosed", "not_applicable"])
def test_validator_requires_notes_and_sources_for_null_amounts(status: str) -> None:
    payload = load_daeseung_payload()
    metric = payload["financial_years"]["2023"]["investment_signals"]["industrial_property_rights"]
    metric["reported"] = None
    metric["disclosure_status"] = status
    metric.pop("notes", None)
    metric.pop("source_locations", None)
    result = validate(payload, base_ref=None)
    assert not result["valid"]
    issue_codes = {issue["code"] for issue in result["issues"]}
    assert "missing_null_reported_note" in issue_codes
    assert "missing_null_reported_source_location" in issue_codes


@pytest.mark.parametrize("status", ["not_disclosed", "not_applicable"])
def test_validator_rejects_non_reported_status_for_integer_amounts(status: str) -> None:
    payload = load_daeseung_payload()
    metric = payload["financial_years"]["2023"]["investment_signals"]["industrial_property_rights"]
    assert metric["reported"] == 0
    metric["disclosure_status"] = status
    result = validate(payload, base_ref=None)
    assert not result["valid"]
    assert any(issue["code"] == "invalid_disclosure_status_for_reported_amount" for issue in result["issues"])


def test_derived_metrics_keep_unavailable_values_as_json_null() -> None:
    payload = load_daeseung_payload()
    payload["financial_years"]["2024"]["income_statement"]["revenue"]["reported"] = None
    payload["financial_years"]["2024"]["income_statement"]["revenue"]["disclosure_status"] = "not_disclosed"
    payload["financial_years"]["2024"]["income_statement"]["revenue"]["notes"] = "Revenue was not disclosed in this synthetic test case."
    derived = calculate_derived_metrics(payload)
    assert derived["2024"]["revenue_yoy_pct"] is None
    assert derived["2024"]["gross_margin_pct"] is None
    assert derived["2024"]["operating_margin_pct"] is None
    assert "None" not in json.dumps(derived, ensure_ascii=False)
    assert "NaN" not in json.dumps(derived, ensure_ascii=False)
    assert "Infinity" not in json.dumps(derived, ensure_ascii=False)


def test_aggregate_reported_preserves_zero_and_distinguishes_unavailable_statuses() -> None:
    assert aggregate_reported([
        {"reported": 0, "disclosure_status": "reported"},
        {"reported": 7, "disclosure_status": "reported"},
    ]) == {"reported": 7, "disclosure_status": "reported"}
    assert aggregate_reported([
        {"reported": None, "disclosure_status": "not_disclosed"},
        {"reported": 7, "disclosure_status": "reported"},
    ]) == {"reported": None, "disclosure_status": "not_disclosed"}
    assert aggregate_reported([
        {"reported": None, "disclosure_status": "not_applicable"},
        {"reported": 7, "disclosure_status": "reported"},
    ]) == {"reported": 7, "disclosure_status": "reported"}
    assert aggregate_reported([
        {"reported": None, "disclosure_status": "not_applicable"},
        {"reported": None, "disclosure_status": "not_applicable"},
    ]) == {"reported": None, "disclosure_status": "not_applicable"}


def test_borrowing_and_receivable_totals_follow_disclosure_status_rules() -> None:
    payload = load_daeseung_payload()
    record = payload["financial_years"]["2025"]
    record["borrowings"]["current_portion_long_term_borrowings"]["reported"] = None
    record["borrowings"]["current_portion_long_term_borrowings"]["disclosure_status"] = "not_disclosed"
    record["borrowings"]["current_portion_long_term_borrowings"]["notes"] = "Synthetic not disclosed component."
    record["working_capital"]["construction_receivables_gross"]["reported"] = None
    record["working_capital"]["construction_receivables_gross"]["disclosure_status"] = "not_applicable"
    record["working_capital"]["construction_receivables_gross"]["notes"] = "Synthetic not applicable component."
    derived = calculate_derived_metrics(payload)
    assert derived["2025"]["total_borrowings"] is None
    assert derived["2025"]["borrowings_to_equity_pct"] is None
    assert derived["2025"]["receivables_total"] == record["working_capital"]["trade_receivables_gross"]["reported"]
    assert derived["2025"]["receivables_to_revenue_pct"] == "5.1"


def test_accounting_equation_null_total_assets_returns_warning_not_exception() -> None:
    payload = load_daeseung_payload()
    set_amount_unavailable(payload, "2025", "balance_sheet", "total_assets")
    result = validate(payload, base_ref=None)
    assert result["valid"], result["issues"]
    assert any(issue["code"] == "accounting_equation_unavailable" and issue["severity"] == "warning" for issue in result["issues"])
    assert not any(issue["code"] == "asset_equation_mismatch" for issue in result["issues"])


def test_accounting_equation_null_liabilities_returns_warning_not_exception() -> None:
    payload = load_daeseung_payload()
    set_amount_unavailable(payload, "2025", "balance_sheet", "total_liabilities")
    result = validate(payload, base_ref=None)
    assert result["valid"], result["issues"]
    assert any(issue["code"] == "accounting_equation_unavailable" for issue in result["issues"])


def test_accounting_equation_explicit_zero_uses_numeric_path() -> None:
    payload = load_daeseung_payload()
    record = payload["financial_years"]["2025"]["balance_sheet"]
    record["total_liabilities"]["reported"] = 0
    record["total_liabilities"]["disclosure_status"] = "reported"
    record["total_equity"]["reported"] = record["total_assets"]["reported"]
    record["total_equity"]["disclosure_status"] = "reported"
    result = validate(payload, base_ref=None)
    assert result["valid"], result["issues"]
    assert not any(issue["code"] == "accounting_equation_unavailable" for issue in result["issues"])
    assert not any(issue["code"] == "asset_equation_mismatch" for issue in result["issues"])


def test_revenue_null_returns_breakdown_warning_not_exception() -> None:
    payload = load_daeseung_payload()
    set_amount_unavailable(payload, "2025", "income_statement", "revenue")
    result = validate(payload, base_ref=None)
    assert result["valid"], result["issues"]
    assert any(issue["code"] == "revenue_breakdown_check_unavailable" and issue["severity"] == "warning" for issue in result["issues"])
    assert not any(issue["code"] == "revenue_breakdown_mismatch" for issue in result["issues"])


def test_revenue_component_not_disclosed_skips_breakdown_mismatch() -> None:
    payload = load_daeseung_payload()
    set_amount_unavailable(payload, "2025", "revenue_breakdown", "product_revenue")
    result = validate(payload, base_ref=None)
    assert result["valid"], result["issues"]
    assert any(issue["code"] == "revenue_breakdown_check_unavailable" for issue in result["issues"])
    assert not any(issue["code"] == "revenue_breakdown_mismatch" for issue in result["issues"])


def test_revenue_component_not_applicable_is_excluded_from_breakdown_sum() -> None:
    payload = load_daeseung_payload()
    assert payload["financial_years"]["2025"]["revenue_breakdown"]["goods_revenue"]["reported"] == 0
    set_amount_unavailable(payload, "2025", "revenue_breakdown", "goods_revenue", status="not_applicable")
    result = validate(payload, base_ref=None)
    assert result["valid"], result["issues"]
    assert not any(issue["code"] == "revenue_breakdown_check_unavailable" for issue in result["issues"])
    assert not any(issue["code"] == "revenue_breakdown_mismatch" for issue in result["issues"])


def test_all_revenue_components_not_applicable_skips_breakdown_check() -> None:
    payload = load_daeseung_payload()
    for field in REQUIRED_REVENUE_FIELDS:
        set_amount_unavailable(payload, "2025", "revenue_breakdown", field, status="not_applicable")
    result = validate(payload, base_ref=None)
    assert result["valid"], result["issues"]
    assert any(issue["code"] == "revenue_breakdown_check_unavailable" for issue in result["issues"])
    assert not any(issue["code"] == "revenue_breakdown_mismatch" for issue in result["issues"])


def test_cash_flow_sign_null_returns_warning_not_exception() -> None:
    payload = load_daeseung_payload()
    set_amount_unavailable(payload, "2025", "cash_flow", "operating_cash_flow")
    result = validate(payload, base_ref=None)
    assert result["valid"], result["issues"]
    assert any(issue["code"] == "cash_flow_sign_unavailable" and issue["severity"] == "warning" for issue in result["issues"])
    assert not any(issue["code"] == "cash_flow_sign_mismatch" for issue in result["issues"])


def test_warning_only_results_remain_valid_but_numeric_mismatches_fail() -> None:
    payload = load_daeseung_payload()
    set_amount_unavailable(payload, "2025", "balance_sheet", "total_assets")
    warning_result = validate(payload, base_ref=None)
    assert warning_result["valid"], warning_result["issues"]

    payload = load_daeseung_payload()
    payload["financial_years"]["2025"]["balance_sheet"]["total_assets"]["reported"] += 1
    mismatch_result = validate(payload, base_ref=None)
    assert not mismatch_result["valid"]
    assert any(issue["code"] == "asset_equation_mismatch" and issue["severity"] == "error" for issue in mismatch_result["issues"])


def test_daeseung_modular_classroom_assets_are_documented_without_schema_extension() -> None:
    payload = load_daeseung_payload()
    expected_additions = {
        "2023": 60458172626,
        "2024": 44579274828,
        "2025": 5314128869,
    }
    for year, value in expected_additions.items():
        metric = payload["financial_years"][year]["investment_signals"]["construction_in_progress"]
        assert metric["reported"] == value
        assert "modular classroom" in metric["notes"]
    limitations = " ".join(payload["disclosure_limitations"])
    assert "FY2022" in limitations
    assert "modular classroom rental asset" in limitations


def test_daeseung_source_locations_are_fully_verified() -> None:
    payload = load_daeseung_payload()
    locations = [
        location
        for _, amount_record in validator_module.money_paths(payload["financial_years"])
        for location in amount_record.get("source_locations", [])
    ]
    assert len(locations) == 84
    assert all(location["verification_status"] == "verified_section_range" for location in locations)
    assert all(location.get("page_range") or location.get("page") for location in locations)
    assert all(location["section"] in SOURCE_SECTION_CODES for location in locations)
    assert all("?" not in location["section"] for location in locations)
