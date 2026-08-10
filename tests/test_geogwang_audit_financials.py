from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_company_audit_financials import validate

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "company_reports" / "geogwang-enterprise" / "audit_financials_2023_2025.json"
INSIGHTS = ROOT / "frontend" / "public" / "data" / "companies" / "company_report_insights.json"
COVERAGE = ROOT / "data" / "company_reports" / "company_data_coverage_snapshot.json"


def load_source() -> dict:
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def load_geogwang_insight() -> dict:
    payload = json.loads(INSIGHTS.read_text(encoding="utf-8"))
    return next(row for row in payload["companies"] if row["company_id"] == "geogwang-enterprise")


def test_geogwang_source_validates_as_three_year_standalone_audit_record() -> None:
    payload = load_source()
    result = validate(payload, expected_year_override=[2023, 2024, 2025], base_ref=None)
    assert result["valid"], result["issues"]
    assert payload["schema_version"] == "company_audit_financials_v1"
    assert payload["company_id"] == "geogwang-enterprise"
    assert payload["entity_attribution"]["financial_scope"] == "standalone"
    assert sorted(payload["financial_years"]) == ["2023", "2024", "2025"]


def test_geogwang_audit_opinions_preserve_qualified_inventory_scope_limitations() -> None:
    payload = load_source()
    opinions = payload["audit_opinions"]
    assert len(opinions) == 3
    assert {row["opinion"] for row in opinions} == {"qualified"}
    assert {row["opinion_label_ko"] for row in opinions} == {"한정의견"}
    assert {row["auditor"] for row in opinions} == {"태성회계법인"}
    limitations = "\n".join(payload["disclosure_limitations"])
    assert "재고자산" in limitations
    assert "한정의견" in limitations
    assert "영업활동현금흐름" in limitations


def test_geogwang_primary_and_cross_check_source_priority_is_explicit() -> None:
    priority = load_source()["source_priority"]
    assert priority["2025"]["primary_source_ref"] == "geogwang_audit_report_2026_04_09"
    assert priority["2024"]["primary_source_ref"] == "geogwang_audit_report_2026_04_09"
    assert priority["2024"]["cross_check_source_refs"] == ["geogwang_audit_report_2025_04_14"]
    assert priority["2023"]["primary_source_ref"] == "geogwang_audit_report_2025_04_14"
    assert priority["2023"]["cross_check_source_refs"] == ["geogwang_audit_report_2024_04_12"]


def test_geogwang_reported_profit_and_cash_flow_values_are_exact() -> None:
    years = load_source()["financial_years"]
    expected = {
        "2023": (11579964740, 588952920, 1095001351, 2477599303),
        "2024": (16085433038, 783313827, 1081053226, 4707490650),
        "2025": (16133052916, 2654581705, 2594631088, 2927766375),
    }
    for year, values in expected.items():
        revenue, operating_profit, net_income, operating_cash_flow = values
        assert years[year]["income_statement"]["revenue"]["reported"] == revenue
        assert years[year]["income_statement"]["operating_profit"]["reported"] == operating_profit
        assert years[year]["income_statement"]["net_income"]["reported"] == net_income
        assert years[year]["cash_flow"]["operating_cash_flow"]["reported"] == operating_cash_flow


def test_geogwang_2025_balance_sheet_values_are_exact() -> None:
    balance = load_source()["financial_years"]["2025"]["balance_sheet"]
    assert balance["total_assets"]["reported"] == 21205762497
    assert balance["total_liabilities"]["reported"] == 7186716202
    assert balance["total_equity"]["reported"] == 14019046295
    assert balance["current_assets"]["reported"] == 8468957399
    assert balance["current_liabilities"]["reported"] == 2622871586


def test_geogwang_null_semantics_are_not_coerced_to_zero() -> None:
    years = load_source()["financial_years"]
    construction_receivables = years["2025"]["working_capital"]["construction_receivables_gross"]
    assert construction_receivables["reported"] is None
    assert construction_receivables["disclosure_status"] == "not_disclosed"
    current_long_term = years["2025"]["borrowings"]["current_portion_long_term_borrowings"]
    assert current_long_term["reported"] is None
    assert current_long_term["disclosure_status"] == "not_applicable"
    work_in_progress_2024 = years["2024"]["working_capital"]["work_in_progress"]
    assert work_in_progress_2024["reported"] is None
    assert work_in_progress_2024["disclosure_status"] == "not_disclosed"


def test_geogwang_public_insight_exposes_latest_cash_flow_and_qualified_opinion() -> None:
    company = load_geogwang_insight()
    assert company["available_years"] == [2023, 2024, 2025]
    assert company["latest_year"] == 2025
    assert company["latest_metrics"]["revenue"]["raw_krw"] == 16133052916
    assert company["latest_metrics"]["operating_cash_flow"]["raw_krw"] == 2927766375
    assert company["latest_metrics"]["operating_cash_flow"]["display_text"] == "29.3억원"
    assert company["derived_metrics"]["2025"]["operating_margin_pct"]["display_text"] == "16.5%"
    assert {row["opinion"] for row in company["source_summary"]["audit_opinions"]} == {"qualified"}


def test_geogwang_coverage_is_complete_and_audit_universe_is_seven() -> None:
    payload = json.loads(COVERAGE.read_text(encoding="utf-8"))
    assert payload["audit_record_count"] == 7
    assert payload["audit_backed_in_effective_universe_count"] == 7
    assert payload["full_three_year_audit_record_count"] == 7
    company = next(row for row in payload["company_coverage_states"] if row["company_id"] == "geogwang-enterprise")
    assert company["audit_coverage_state"] == "complete"
    assert "missing_audit_financials" not in company["recommendation_reason_codes"]
