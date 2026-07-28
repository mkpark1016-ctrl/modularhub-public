from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.validate_company_audit_financials import (
    DEFAULT_INPUT,
    PROTECTED_PUBLIC_FILES,
    REQUIRED_BORROWING_FIELDS,
    calculate_derived_metrics,
    contains_key,
    validate,
)

ROOT = Path(__file__).resolve().parents[1]


def load_payload() -> dict:
    return json.loads(DEFAULT_INPUT.read_text(encoding="utf-8"))


def reported(record: dict, section: str, field: str) -> int:
    return record[section][field]["reported"]


def test_schema_validation_passes() -> None:
    result = validate(load_payload())
    assert result["valid"], result["issues"]
    assert result["schema_version"] == "company_audit_financials_v1"
    assert result["financial_years_loaded"] == ["2023", "2024", "2025"]


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
