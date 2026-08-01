from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from scripts.build_company_report_insights import DEFAULT_OUTPUT, aggregate_reported, build_view_model, combined_metric, discover_source_files, money_metric, stable_json
from scripts.validate_company_audit_financials import SOURCE_SECTION_CODES, load_payload, validate

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "company_reports" / "company_report_insights_v1.schema.json"


def load_output() -> dict:
    return json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))


def yuchang_company(payload: dict) -> dict:
    return next(company for company in payload["companies"] if company["company_id"] == "yuchang-enc")


def kumkang_company(payload: dict) -> dict:
    return next(company for company in payload["companies"] if company["company_id"] == "kumkang-kind")


def daeseung_company(payload: dict) -> dict:
    return next(company for company in payload["companies"] if company["company_id"] == "daeseung-engineering")


def planm_company(payload: dict) -> dict:
    return next(company for company in payload["companies"] if company["company_id"] == "planm")


def contains_key(value: object, target: str) -> bool:
    if isinstance(value, dict):
        return any(key == target or contains_key(child, target) for key, child in value.items())
    if isinstance(value, list):
        return any(contains_key(child, target) for child in value)
    return False


def test_source_validator_passes_before_build() -> None:
    result = validate(load_payload(), base_ref=None)
    assert result["valid"], result["issues"]


def test_view_model_schema_passes() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(load_output()))
    assert errors == []


def test_yuchang_years_and_latest_metrics() -> None:
    company = yuchang_company(load_output())
    assert company["available_years"] == [2023, 2024, 2025]
    assert company["latest_year"] == 2025
    assert company["latest_metrics"]["revenue"]["raw_krw"] == 307684467052
    assert company["latest_metrics"]["revenue"]["display_eok"] == 3076.8
    assert company["latest_metrics"]["revenue"]["display_text"] == "3,076.8억원"


def test_view_model_contains_yuchang_kumkang_and_daeseung() -> None:
    payload = load_output()
    assert [company["company_id"] for company in payload["companies"]] == ["daeseung-engineering", "kumkang-kind", "planm", "yuchang-enc"]


def test_kumkang_years_scope_and_latest_metrics() -> None:
    company = kumkang_company(load_output())
    assert company["available_years"] == [2023, 2024, 2025]
    assert company["latest_year"] == 2025
    assert company["financial_scope"] == "consolidated"
    assert company["latest_metrics"]["revenue"]["raw_krw"] == 802156014802
    assert company["latest_metrics"]["revenue"]["display_eok"] == 8021.6
    assert company["latest_metrics"]["operating_profit"]["raw_krw"] == 10497395028
    assert company["latest_metrics"]["net_income"]["raw_krw"] == -37353541440
    assert company["latest_metrics"]["operating_cash_flow"]["raw_krw"] == 21874636165


def test_kumkang_common_calculations_and_source_locations() -> None:
    company = kumkang_company(load_output())
    assert company["derived_metrics"]["2023"]["operating_margin_pct"]["display_text"] == "7.8%"
    assert company["derived_metrics"]["2024"]["operating_margin_pct"]["display_text"] == "4.1%"
    assert company["derived_metrics"]["2025"]["operating_margin_pct"]["display_text"] == "1.3%"
    assert company["derived_metrics"]["2025"]["net_margin_pct"]["display_text"] == "-4.7%"
    assert company["financial_series"][0]["metrics"]["total_borrowings"]["raw_krw"] == 465321329651
    assert company["financial_series"][1]["metrics"]["total_borrowings"]["raw_krw"] == 502257459579
    assert company["financial_series"][2]["metrics"]["total_borrowings"]["raw_krw"] == 513762323953
    assert company["financial_series"][2]["metrics"]["receivables_total"]["raw_krw"] == 185921585924
    assert company["financial_series"][2]["metrics"]["receivables_total"]["raw_krw"] != company["financial_series"][2]["metrics"]["inventory"]["raw_krw"]
    assert company["data_quality"]["source_location_count"] == 84
    assert company["data_quality"]["pending_manual_page_check_count"] == 0
    assert company["source_summary"]["verified_location_count"] == 84
    assert company["source_summary"]["pending_location_count"] == 0


def test_kumkang_modular_segment_disclosure_does_not_emit_not_disclosed_warning() -> None:
    company = kumkang_company(load_output())
    warning_codes = [warning["code"] for warning in company["disclosure_warnings"]]
    assert company["attribution"]["modular_segment_revenue_disclosed"] is True
    assert "modular_segment_revenue_not_disclosed" not in warning_codes
    assert "product_revenue_not_modular_revenue" in warning_codes


def test_kumkang_auditor_report_dates_are_not_submission_dates() -> None:
    company = kumkang_company(load_output())
    assert [opinion["auditor_report_date"] for opinion in company["source_summary"]["audit_opinions"]] == [None, None, None]
    assert {
        opinion["auditor_report_date_verification_status"]
        for opinion in company["source_summary"]["audit_opinions"]
    } == {"not_located_in_attached_business_report_pdf"}


def test_yuchang_item_is_semantically_unchanged_from_main() -> None:
    old_text = subprocess.check_output(
        ["git", "show", "origin/main:frontend/public/data/companies/company_report_insights.json"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    )
    assert yuchang_company(load_output()) == yuchang_company(json.loads(old_text))


def test_kumkang_item_is_semantically_unchanged_from_main() -> None:
    old_text = subprocess.check_output(
        ["git", "show", "origin/main:frontend/public/data/companies/company_report_insights.json"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    )
    assert kumkang_company(load_output()) == kumkang_company(json.loads(old_text))


def test_daeseung_years_scope_latest_metrics_and_source_quality() -> None:
    company = daeseung_company(load_output())
    assert company["available_years"] == [2023, 2024, 2025]
    assert company["latest_year"] == 2025
    assert company["financial_scope"] == "standalone"
    assert company["latest_metrics"]["revenue"]["raw_krw"] == 61659861549
    assert company["latest_metrics"]["revenue"]["display_eok"] == 616.6
    assert company["latest_metrics"]["revenue"]["display_text"] == "616.6억원"
    assert company["latest_metrics"]["operating_cash_flow"]["raw_krw"] == -345400575
    assert company["latest_metrics"]["operating_cash_flow"]["display_text"] == "-3.5억원"
    assert company["latest_metrics"]["total_borrowings"]["raw_krw"] == 53164938435
    assert company["latest_metrics"]["receivables_total"]["raw_krw"] == 3418283872
    assert company["data_quality"]["source_location_count"] == 84
    assert company["data_quality"]["pending_manual_page_check_count"] == 0
    assert company["source_summary"]["verified_location_count"] == 84
    assert company["source_summary"]["pending_location_count"] == 0


def test_daeseung_modular_rental_metrics_and_warnings() -> None:
    company = daeseung_company(load_output())
    assert company["derived_metrics"]["2023"]["rental_revenue_share_pct"]["display_text"] == "50.5%"
    assert company["derived_metrics"]["2024"]["rental_revenue_share_pct"]["display_text"] == "79.0%"
    assert company["derived_metrics"]["2025"]["rental_revenue_share_pct"]["display_text"] == "40.7%"
    assert company["derived_metrics"]["2025"]["revenue_yoy_pct"]["display_text"] == "-26.6%"
    warning_codes = [warning["code"] for warning in company["disclosure_warnings"]]
    assert company["attribution"]["modular_segment_revenue_disclosed"] is True
    assert "modular_segment_revenue_not_disclosed" not in warning_codes
    assert "product_revenue_not_modular_revenue" in warning_codes
    assert "construction_revenue_not_modular_revenue" in warning_codes
    assert "related_entity_results_not_combined" in warning_codes
    assert "모듈러교실임대료수입" in " ".join(warning["message"] for warning in company["disclosure_warnings"])


def test_daeseung_auditor_dates_and_source_priority_are_public() -> None:
    company = daeseung_company(load_output())
    assert [opinion["auditor_report_date"] for opinion in company["source_summary"]["audit_opinions"]] == [
        "2023-09-11",
        "2024-09-13",
        "2025-09-16",
    ]
    priority = company["source_summary"]["source_priority_by_year"]
    assert priority["2023"]["primary_source_ref"] == "daeseung_audit_report_2023_09_19"
    assert priority["2023"]["cross_check_source_refs"] == ["daeseung_audit_report_2024_09_19"]
    assert priority["2024"]["primary_source_ref"] == "daeseung_audit_report_2024_09_19"
    assert priority["2025"]["primary_source_ref"] == "daeseung_audit_report_2025_09_17"


def test_view_model_money_metric_preserves_null_as_not_disclosed() -> None:
    metric = money_metric(
        raw_krw=None,
        source_refs=["sample_report"],
        source_locations=[],
        disclosure_status="not_disclosed",
    )
    assert metric["raw_krw"] is None
    assert metric["display_eok"] is None
    assert metric["display_text"] == "공시되지 않음"
    assert metric["calculation_basis"] == "not_disclosed"
    assert metric["disclosure_status"] == "not_disclosed"


def test_view_model_money_metric_preserves_null_as_not_applicable() -> None:
    metric = money_metric(
        raw_krw=None,
        source_refs=["sample_report"],
        source_locations=[],
        disclosure_status="not_applicable",
    )
    assert metric["raw_krw"] is None
    assert metric["display_eok"] is None
    assert metric["display_text"] == "해당 없음"
    assert metric["calculation_basis"] == "not_applicable"
    assert metric["disclosure_status"] == "not_applicable"


def test_view_model_money_metric_preserves_reported_zero() -> None:
    metric = money_metric(
        raw_krw=0,
        source_refs=["sample_report"],
        source_locations=[],
        disclosure_status="reported",
    )
    assert metric["raw_krw"] == 0
    assert metric["display_eok"] == 0.0
    assert metric["display_text"] == "0.0억원"
    assert metric["calculation_basis"] == "reported"
    assert metric["disclosure_status"] == "reported"


def test_view_model_money_metric_rejects_null_without_status() -> None:
    with pytest.raises(ValueError):
        money_metric(raw_krw=None, source_refs=["sample_report"], source_locations=[])


def test_view_model_money_metric_accepts_verification_pending_as_null_only() -> None:
    metric = money_metric(
        raw_krw=None,
        source_refs=["sample_report"],
        source_locations=[],
        disclosure_status="verification_pending",
    )
    assert metric["raw_krw"] is None
    assert metric["display_eok"] is None
    assert metric["display_text"] == "검증 보류"
    assert metric["calculation_basis"] == "verification_pending"
    assert metric["disclosure_status"] == "verification_pending"


def test_view_model_schema_rejects_invalid_null_and_status_combinations() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    payload = load_output()
    metric = daeseung_company(payload)["financial_series"][0]["metrics"]["revenue"]
    metric["raw_krw"] = None
    metric["display_eok"] = 0
    metric["calculation_basis"] = "reported"
    metric["disclosure_status"] = "reported"
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    assert errors


def test_view_model_combined_metric_distinguishes_not_disclosed_and_not_applicable() -> None:
    refs = ["sample_report"]
    part = {"reported": 10, "disclosure_status": "reported", "source_refs": refs, "source_locations": []}
    not_disclosed = {"reported": None, "disclosure_status": "not_disclosed", "source_refs": refs, "source_locations": []}
    not_applicable = {"reported": None, "disclosure_status": "not_applicable", "source_refs": refs, "source_locations": []}
    assert aggregate_reported([part, not_applicable]) == {"reported": 10, "disclosure_status": "reported"}
    included_metric = combined_metric(10, [part, not_applicable])
    assert included_metric["raw_krw"] == 10
    assert "disclosure_status" not in included_metric
    blocked_metric = combined_metric(None, [part, not_disclosed])
    assert blocked_metric["raw_krw"] is None
    assert blocked_metric["display_text"] == "공시되지 않음"
    assert blocked_metric["calculation_basis"] == "not_disclosed"
    all_na_metric = combined_metric(None, [not_applicable])
    assert all_na_metric["display_text"] == "해당 없음"
    assert all_na_metric["calculation_basis"] == "not_applicable"


def test_view_model_combined_metric_keeps_verification_pending_out_of_calculations() -> None:
    refs = ["sample_report"]
    part = {"reported": 10, "disclosure_status": "reported", "source_refs": refs, "source_locations": []}
    pending = {"reported": None, "disclosure_status": "verification_pending", "source_refs": refs, "source_locations": []}
    assert aggregate_reported([part, pending]) == {"reported": None, "disclosure_status": "verification_pending"}
    blocked_metric = combined_metric(None, [part, pending])
    assert blocked_metric["raw_krw"] is None
    assert blocked_metric["calculation_basis"] == "verification_pending"
    assert blocked_metric["disclosure_status"] == "verification_pending"


def test_public_builder_does_not_discover_planm_staging_json() -> None:
    discovered = {path.relative_to(ROOT).as_posix() for path in discover_source_files()}
    assert "data/company_reports/planm/audit_financials_2023_2025.json" in discovered
    assert "data/company_reports/planm/staging/audit_financials_2023_2025.json" not in discovered
    assert all("/staging/" not in path for path in discovered)


def test_planm_public_view_model_promotes_verified_metrics_and_blocks_pending_equity() -> None:
    company = planm_company(load_output())
    assert company["available_years"] == [2023, 2024, 2025]
    assert company["latest_year"] == 2025
    assert company["financial_scope"] == "standalone"

    equity_2023 = company["financial_series"][0]["metrics"]["total_equity"]
    assert equity_2023["raw_krw"] is None
    assert equity_2023["display_eok"] is None
    assert equity_2023["display_text"] == "검증 보류"
    assert equity_2023["calculation_basis"] == "verification_pending"
    assert equity_2023["disclosure_status"] == "verification_pending"
    assert equity_2023["source_locations"] == [
        {
            "page_range": "7-8",
            "section": "statement.balance_sheet",
            "source_ref": "planm_audit_report_2025_04_24",
            "verification_status": "verified_section_range",
        },
        {
            "page_range": "48,50",
            "section": "note.restatement",
            "source_ref": "planm_audit_report_2026_06_25",
            "verification_status": "verified_section_range",
        },
    ]

    assert company["derived_metrics"]["2023"]["liabilities_to_equity_pct"]["value"] is None
    assert company["derived_metrics"]["2023"]["borrowings_to_equity_pct"]["value"] is None
    for key in ["liabilities_to_equity_pct", "borrowings_to_equity_pct"]:
        display_text = company["derived_metrics"]["2023"][key]["display_text"]
        assert display_text not in {"0.0%", "NaN%", "Infinity%"}
        assert "None" not in display_text

    assert company["financial_series"][1]["metrics"]["total_equity"]["raw_krw"] == 70222157519
    assert company["financial_series"][2]["metrics"]["revenue"]["raw_krw"] == 59222859418
    warning_codes = [warning["code"] for warning in company["disclosure_warnings"]]
    assert "verification_pending_total_equity" in warning_codes
    assert "modular_segment_revenue_not_disclosed" in warning_codes
    assert "product_revenue_not_modular_revenue" in warning_codes
    assert "construction_revenue_not_modular_revenue" in warning_codes
    assert company["attribution"]["modular_segment_revenue_disclosed"] is False
    assert company["data_quality"]["source_location_count"] == 85


def test_planm_public_view_model_excludes_unsupported_requested_amount() -> None:
    rendered = json.dumps(planm_company(load_output()), ensure_ascii=False)
    assert "3,529,782,000" not in rendered
    assert "3529782000" not in rendered
    assert "3,529,017" in rendered


def test_calculated_money_metrics_preserve_raw_krw() -> None:
    latest = yuchang_company(load_output())["latest_metrics"]
    assert latest["total_borrowings"]["raw_krw"] == 112134492523
    assert latest["receivables_total"]["raw_krw"] == 115786145992
    assert latest["operating_cash_flow"]["raw_krw"] == -30830315410


def test_no_modular_revenue_and_required_warnings() -> None:
    assert not contains_key(load_output(), "modular_revenue")
    company = yuchang_company(load_output())
    messages = [warning["message"] for warning in company["disclosure_warnings"]]
    assert any("제품매출을 모듈러 매출로 간주할 수 없다" in message for message in messages)
    assert any("공사매출을 모듈러 매출로 간주할 수 없다" in message for message in messages)
    assert any("유창엠앤씨" in message and "자동 합산하지 않는다" in message for message in messages)


def test_source_location_counts_and_quality() -> None:
    company = yuchang_company(load_output())
    assert company["data_quality"]["source_location_count"] == 84
    assert company["data_quality"]["pending_manual_page_check_count"] == 45
    assert company["source_summary"]["verified_location_count"] == 39
    assert company["source_summary"]["pending_location_count"] == 45


def test_public_source_location_sections_are_standard_codes() -> None:
    payload = load_output()
    sections = []
    for company in payload["companies"]:
        for series in company["financial_series"]:
            for metric in series["metrics"].values():
                sections.extend(location["section"] for location in metric.get("source_locations", []))
        for metric in company["latest_metrics"].values():
            sections.extend(location["section"] for location in metric.get("source_locations", []))
    assert sections
    assert all(section in SOURCE_SECTION_CODES for section in sections)
    assert all("?" not in section for section in sections)


def test_deterministic_generation_matches_stored_output() -> None:
    generated = stable_json(build_view_model(base_ref=None))
    assert generated == DEFAULT_OUTPUT.read_text(encoding="utf-8")


def test_existing_company_public_data_files_are_not_changed() -> None:
    protected = [
        "frontend/public/data/companies/companies.json",
        "frontend/public/data/companies/company_intelligence_v2.json",
    ]
    result = subprocess.run(
        ["git", "diff", "--name-only", "--", *protected],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.stdout.strip() == ""
