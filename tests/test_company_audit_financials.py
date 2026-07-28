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
    calculate_derived_metrics,
    contains_key,
    protected_public_diff_status,
    validate,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "company_reports" / "company_audit_financials_v1.schema.json"
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


def load_payload() -> dict:
    return json.loads(DEFAULT_INPUT.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def reported(record: dict, section: str, field: str) -> int:
    return record[section][field]["reported"]


def schema_errors(payload: dict) -> list:
    validator = Draft202012Validator(load_schema())
    return sorted(validator.iter_errors(payload), key=lambda error: list(error.path))


def test_json_schema_contract_is_complete() -> None:
    schema = load_schema()
    defs = schema["$defs"]
    assert schema["properties"]["financial_years"]["$ref"] == "#/$defs/financialYearsPilot"
    assert defs["financialYearsPilot"]["additionalProperties"] is False
    assert set(defs["financialYearsPilot"]["properties"]) == {"2023", "2024", "2025"}
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


def test_expected_years_are_read_from_dataset_metadata() -> None:
    payload = deepcopy(load_payload())
    payload["validation_metadata"]["expected_years"] = [2024, 2025]
    result = validate(payload, base_ref=None)
    assert not result["valid"]
    assert any(issue["code"] == "financial_years_mismatch" for issue in result["issues"])


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
    warning = load_payload()["entity_attribution"]["attribution_warning"]
    assert "주식회사 유창이앤씨 별도 재무제표" in warning
    assert "유창엠앤씨" in warning
    assert "자동 합산하지 않는다" in warning


def test_public_data_files_are_not_changed() -> None:
    protected = [str(path.relative_to(ROOT)) for path in PROTECTED_PUBLIC_FILES if path.exists()]
    result = subprocess.run(
        ["git", "diff", "--name-only", "--", *protected],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.stdout.strip() == ""


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
