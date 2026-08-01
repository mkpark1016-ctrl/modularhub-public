from __future__ import annotations

import json
from pathlib import Path

from scripts.build_company_report_insights import DEFAULT_INPUT_ROOT, DEFAULT_OUTPUT, discover_source_files
from scripts.validate_company_audit_financials import validate

ROOT = Path(__file__).resolve().parents[1]
STAGING_PATH = ROOT / "data" / "company_reports" / "nrb" / "staging" / "audit_financials_2023_2025.json"
COMPANIES_PATH = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"


def load_staging() -> dict:
    return json.loads(STAGING_PATH.read_text(encoding="utf-8"))


def reported(payload: dict, year: str, section: str, field: str) -> int | None:
    return payload["financial_years"][year][section][field]["reported"]


def walk(value: object):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def test_nrb_uses_existing_company_id_and_stays_in_staging() -> None:
    companies = json.loads(COMPANIES_PATH.read_text(encoding="utf-8"))
    assert any(company["company_id"] == "nrb" for company in companies["companies"])

    payload = load_staging()
    assert payload["company_id"] == "nrb"
    assert payload["company_name"] == "\uc5d4\uc54c\ube44"
    assert payload["reporting_entity"] == "\uc8fc\uc2dd\ud68c\uc0ac \uc5d4\uc54c\ube44"
    assert payload["entity_attribution"]["financial_scope"] == "standalone"

    public_companies = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))["companies"]
    assert "nrb" not in {company["company_id"] for company in public_companies}
    assert STAGING_PATH not in discover_source_files(DEFAULT_INPUT_ROOT)


def test_nrb_staging_validator_passes_with_revenue_breakdown_warnings_only() -> None:
    result = validate(load_staging(), base_ref="origin/main")
    assert result["valid"], result["issues"]
    assert {issue["code"] for issue in result["issues"]} == {"revenue_breakdown_check_unavailable"}
    assert result["protected_public_diff"]["changed_files"] == []


def test_nrb_source_priority_and_audit_dates_are_explicit() -> None:
    payload = load_staging()
    assert list(payload["financial_years"]) == ["2023", "2024", "2025"]
    assert payload["source_priority"]["2023"]["primary_source_ref"] == "nrb_annual_report_2026_03_18"
    assert payload["source_priority"]["2024"]["primary_source_ref"] == "nrb_annual_report_2026_03_18"
    assert payload["source_priority"]["2025"]["primary_source_ref"] == "nrb_annual_report_2026_03_18"

    audit_by_source = {opinion["source_ref"]: opinion for opinion in payload["audit_opinions"]}
    assert audit_by_source["nrb_audit_report_2024_04_08"]["auditor_report_date"] == "2024-03-27"
    assert audit_by_source["nrb_audit_report_2025_04_01"]["auditor_report_date"] == "2025-03-21"
    assert audit_by_source["nrb_annual_report_2026_03_18"]["auditor_report_date"] is None
    assert (
        audit_by_source["nrb_annual_report_2026_03_18"]["auditor_report_date_verification_status"]
        == "not_located_in_attached_business_report_pdf"
    )
    assert payload["source_documents"]["nrb_annual_report_2026_03_18"]["report_date"] == "2026-03-18"
    assert payload["source_documents"]["nrb_annual_report_2026_03_18"]["auditor_report_date"] is None


def test_nrb_restated_2023_current_liabilities_are_preserved() -> None:
    payload = load_staging()
    assert reported(payload, "2023", "balance_sheet", "current_liabilities") == 81185943632
    assert reported(payload, "2023", "balance_sheet", "current_liabilities") != 48527580433

    mismatches = payload["validation_metadata"]["validation_policy"]["allowed_cross_check_year_mismatches"]
    current_liability_mismatch = next(item for item in mismatches if item["year"] == 2023)
    assert current_liability_mismatch["source_ref"] == "nrb_audit_report_2024_04_08"
    assert "48,527,580,433" not in json.dumps(payload["financial_years"]["2023"], ensure_ascii=False)


def test_nrb_2024_operating_cash_flow_mismatch_blocks_public_promotion() -> None:
    payload = load_staging()
    assert reported(payload, "2024", "cash_flow", "operating_cash_flow") == 20142350922

    mismatches = payload["validation_metadata"]["validation_policy"]["allowed_cross_check_year_mismatches"]
    cash_flow_mismatch = next(item for item in mismatches if item["year"] == 2024)
    assert cash_flow_mismatch["source_ref"] == "nrb_audit_report_2025_04_01"
    assert "-2,611,715,083" in cash_flow_mismatch["reason"]
    assert any("operating cash flow mismatch" in limitation for limitation in payload["disclosure_limitations"])


def test_nrb_2025_standalone_values_and_public_margin_difference() -> None:
    payload = load_staging()
    assert reported(payload, "2025", "income_statement", "revenue") == 59481544678
    assert reported(payload, "2025", "income_statement", "operating_profit") == 4461258309
    assert reported(payload, "2025", "income_statement", "net_income") == -563349199
    assert reported(payload, "2025", "cash_flow", "operating_cash_flow") == 3068742998

    operating_margin = reported(payload, "2025", "income_statement", "operating_profit") / reported(
        payload, "2025", "income_statement", "revenue"
    )
    assert round(operating_margin * 100, 1) == 7.5
    assert any("7.6%" in limitation and "7.5%" in limitation for limitation in payload["disclosure_limitations"])


def test_nrb_borrowings_scope_excludes_other_financing_classes() -> None:
    payload = load_staging()
    total_borrowings_2025 = (
        reported(payload, "2025", "borrowings", "short_term_borrowings")
        + reported(payload, "2025", "borrowings", "current_portion_long_term_borrowings")
        + reported(payload, "2025", "borrowings", "long_term_borrowings")
    )
    assert total_borrowings_2025 == 44695538901
    assert total_borrowings_2025 != 44695538901 + 13264836073
    assert any("Convertible bonds" in limitation for limitation in payload["disclosure_limitations"])


def test_nrb_revenue_breakdown_is_not_copied_from_consolidated_table() -> None:
    payload = load_staging()
    assert payload["entity_attribution"]["modular_segment_revenue_disclosed"] is True

    for year, record in payload["financial_years"].items():
        for field, metric in record["revenue_breakdown"].items():
            assert metric["reported"] is None, f"{year} {field} must not copy consolidated revenue"
            assert metric["disclosure_status"] == "not_disclosed"
            assert "consolidated" in metric["notes"]


def test_nrb_source_locations_are_complete_and_refs_exist() -> None:
    payload = load_staging()
    source_refs = set(payload["source_documents"])
    for key, child in walk(payload):
        if key == "source_refs":
            assert set(child) <= source_refs
        if key == "source_ref":
            assert child in source_refs
        if key == "source_locations":
            assert child
            for location in child:
                assert location["source_ref"] in source_refs
                assert location["section"]
                assert location.get("page_range") or location.get("page")
                assert location["verification_status"] in {"verified", "verified_section_range"}


def test_nrb_payload_has_no_placeholder_or_forbidden_fields() -> None:
    text = STAGING_PATH.read_text(encoding="utf-8")
    assert "???" not in text
    assert "\ufffd" not in text

    payload = load_staging()
    for key, child in walk(payload):
        if key not in {"forbidden_field_names"}:
            assert key not in {"consolidated_net_income", "consolidated_operating_cash_flow"}
        if isinstance(child, float):
            assert child == child
            assert child not in {float("inf"), float("-inf")}
