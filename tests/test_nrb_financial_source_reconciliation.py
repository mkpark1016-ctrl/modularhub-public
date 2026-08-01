from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from scripts.build_company_report_insights import DEFAULT_INPUT_ROOT, DEFAULT_OUTPUT, discover_source_files
from scripts.validate_company_audit_financials import validate

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_INPUT_PATH = ROOT / "data" / "company_reports" / "nrb" / "audit_financials_2023_2025.json"
STAGING_PATH = ROOT / "data" / "company_reports" / "nrb" / "staging" / "audit_financials_2023_2025.json"
COMPANIES_PATH = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"


def load_public_input() -> dict:
    return json.loads(PUBLIC_INPUT_PATH.read_text(encoding="utf-8"))


def load_public_output_company() -> dict:
    public_companies = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))["companies"]
    return next(company for company in public_companies if company["company_id"] == "nrb")


def reported(payload: dict, year: str, section: str, field: str) -> int | None:
    return payload["financial_years"][year][section][field]["reported"]


def revenue_breakdown_total(payload: dict, year: str) -> int:
    total = 0
    for metric in payload["financial_years"][year]["revenue_breakdown"].values():
        if isinstance(metric["reported"], int):
            total += metric["reported"]
    return total


def walk(value: object):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def test_nrb_uses_existing_company_id_and_is_publicly_discovered() -> None:
    companies = json.loads(COMPANIES_PATH.read_text(encoding="utf-8"))
    assert any(company["company_id"] == "nrb" for company in companies["companies"])

    payload = load_public_input()
    assert payload["company_id"] == "nrb"
    assert payload["company_name"] == "\uc5d4\uc54c\ube44"
    assert payload["reporting_entity"] == "\uc8fc\uc2dd\ud68c\uc0ac \uc5d4\uc54c\ube44"
    assert payload["entity_attribution"]["financial_scope"] == "standalone"

    public_companies = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))["companies"]
    assert {company["company_id"] for company in public_companies} == {
        "daeseung-engineering",
        "kumkang-kind",
        "nrb",
        "planm",
        "yuchang-enc",
    }
    assert sum(company["company_id"] == "nrb" for company in public_companies) == 1
    assert PUBLIC_INPUT_PATH in discover_source_files(DEFAULT_INPUT_ROOT)
    assert STAGING_PATH not in discover_source_files(DEFAULT_INPUT_ROOT)
    assert not STAGING_PATH.exists()


def test_nrb_public_input_validator_passes_without_revenue_breakdown_warnings() -> None:
    result = validate(load_public_input(), base_ref="origin/main")
    assert result["valid"], result["issues"]
    assert result["issues"] == []
    assert result["protected_public_diff"]["changed_files"] == []


def test_nrb_source_priority_and_audit_dates_are_explicit() -> None:
    payload = load_public_input()
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
    payload = load_public_input()
    assert reported(payload, "2023", "balance_sheet", "current_liabilities") == 81185943632
    assert reported(payload, "2023", "balance_sheet", "current_liabilities") != 48527580433

    mismatches = payload["validation_metadata"]["validation_policy"]["allowed_cross_check_year_mismatches"]
    assert all(item.get("year") != 2023 for item in mismatches)
    event = next(item for item in payload["entity_attribution"]["special_events"] if item["event_type"] == "current_liability_policy_reclassification")
    assert event["attribution_effect"] == "resolved_retrospective_current_liability_reclassification"
    assert "K-IFRS 1001" in event["description"]
    assert "32,658,363,199" in event["description"]
    assert "48,527,580,433" not in json.dumps(payload["financial_years"]["2023"], ensure_ascii=False)


def test_nrb_2024_operating_cash_flow_policy_change_is_resolved() -> None:
    payload = load_public_input()
    assert reported(payload, "2024", "cash_flow", "operating_cash_flow") == 20142350922

    mismatches = payload["validation_metadata"]["validation_policy"]["allowed_cross_check_year_mismatches"]
    assert all(item.get("year") != 2024 for item in mismatches)
    event = next(item for item in payload["entity_attribution"]["special_events"] if item["event_type"] == "cash_flow_presentation_policy_change")
    assert event["attribution_effect"] == "resolved_retrospective_cash_flow_presentation_change"
    assert "K-IFRS 1008" in event["description"]
    assert "-2,611,715 thousand KRW" in event["description"]
    assert "20,142,351 thousand KRW" in event["description"]
    assert not any("operating cash flow mismatch" in limitation for limitation in payload["disclosure_limitations"])


def test_nrb_2025_standalone_values_and_public_margin_difference() -> None:
    payload = load_public_input()
    assert reported(payload, "2025", "income_statement", "revenue") == 59481544678
    assert reported(payload, "2025", "income_statement", "operating_profit") == 4461258309
    assert reported(payload, "2025", "income_statement", "net_income") == -563349199
    assert reported(payload, "2025", "cash_flow", "operating_cash_flow") == 3068742998

    operating_margin = reported(payload, "2025", "income_statement", "operating_profit") / reported(
        payload, "2025", "income_statement", "revenue"
    )
    assert round(operating_margin * 100, 1) == 7.5
    assert any("7.6%" in limitation and "7.5%" in limitation for limitation in payload["disclosure_limitations"])
    company = load_public_output_company()
    assert company["latest_metrics"]["revenue"]["raw_krw"] == 59481544678
    assert company["latest_metrics"]["operating_profit"]["raw_krw"] == 4461258309
    assert company["derived_metrics"]["2025"]["operating_margin_pct"]["display_text"] == "7.5%"


def test_nrb_borrowings_scope_excludes_other_financing_classes() -> None:
    payload = load_public_input()
    total_borrowings_2025 = (
        reported(payload, "2025", "borrowings", "short_term_borrowings")
        + reported(payload, "2025", "borrowings", "current_portion_long_term_borrowings")
        + reported(payload, "2025", "borrowings", "long_term_borrowings")
    )
    assert total_borrowings_2025 == 44695538901
    assert total_borrowings_2025 != 44695538901 + 13264836073
    assert any("Convertible bonds" in limitation for limitation in payload["disclosure_limitations"])


def test_nrb_standalone_revenue_breakdown_is_disclosed_with_service_revenue() -> None:
    payload = load_public_input()
    assert payload["entity_attribution"]["modular_segment_revenue_disclosed"] is True

    expected = {
        "2023": {
            "product_revenue": 14334820000,
            "rental_revenue": 23313498000,
            "service_revenue": 13381205000,
            "construction_revenue": None,
            "other_revenue": 503093000,
            "source_ref": "nrb_audit_report_2025_04_01",
            "page_range": "p.77",
        },
        "2024": {
            "product_revenue": 9567358000,
            "rental_revenue": 31289418000,
            "service_revenue": 11622765000,
            "construction_revenue": None,
            "other_revenue": 321520000,
            "source_ref": "nrb_annual_report_2026_03_18",
            "page_range": "p.208",
        },
        "2025": {
            "product_revenue": 14800741000,
            "rental_revenue": 24586780000,
            "service_revenue": 12270351000,
            "construction_revenue": 7667780000,
            "other_revenue": 155893000,
            "source_ref": "nrb_annual_report_2026_03_18",
            "page_range": "p.208",
        },
    }
    for year, values in expected.items():
        breakdown = payload["financial_years"][year]["revenue_breakdown"]
        assert breakdown["goods_revenue"]["reported"] is None
        assert breakdown["goods_revenue"]["disclosure_status"] == "not_applicable"
        for field in ["product_revenue", "rental_revenue", "service_revenue", "other_revenue"]:
            assert breakdown[field]["reported"] == values[field]
        if values["construction_revenue"] is None:
            assert breakdown["construction_revenue"]["reported"] is None
            assert breakdown["construction_revenue"]["disclosure_status"] == "not_applicable"
        else:
            assert breakdown["construction_revenue"]["reported"] == values["construction_revenue"]
        for metric in breakdown.values():
            assert metric["source_refs"] == [values["source_ref"]]
            assert metric["source_locations"][0]["page_range"] == values["page_range"]
            assert metric["source_locations"][0]["section"] == "note.revenue_breakdown"
        revenue = reported(payload, year, "income_statement", "revenue")
        assert abs(revenue - revenue_breakdown_total(payload, year)) <= 999


def test_nrb_public_view_model_includes_service_revenue_without_zero_filling() -> None:
    company = load_public_output_company()
    by_year = {str(row["year"]): row["metrics"] for row in company["financial_series"]}
    assert by_year["2023"]["service_revenue"]["raw_krw"] == 13381205000
    assert by_year["2024"]["service_revenue"]["raw_krw"] == 11622765000
    assert by_year["2025"]["service_revenue"]["raw_krw"] == 12270351000
    assert company["derived_metrics"]["2023"]["service_revenue_share_pct"]["display_text"] == "26.0%"
    assert company["derived_metrics"]["2024"]["service_revenue_share_pct"]["display_text"] == "22.0%"
    assert company["derived_metrics"]["2025"]["service_revenue_share_pct"]["display_text"] == "20.6%"
    assert by_year["2023"]["construction_revenue"]["raw_krw"] is None
    assert by_year["2023"]["construction_revenue"]["display_text"] == "\ud574\ub2f9 \uc5c6\uc74c"
    assert by_year["2024"]["construction_revenue"]["raw_krw"] is None
    assert by_year["2024"]["construction_revenue"]["display_text"] == "\ud574\ub2f9 \uc5c6\uc74c"
    assert by_year["2025"]["construction_revenue"]["raw_krw"] == 7667780000


def test_nrb_public_company_summary_is_reconciled_to_audited_standalone_values() -> None:
    companies = json.loads(COMPANIES_PATH.read_text(encoding="utf-8"))
    nrb = next(company for company in companies["companies"] if company["company_id"] == "nrb")
    source_id = "nrb-audit-financials-2023-2025"
    assert any(source["source_id"] == source_id for source in nrb["sources"])
    latest = next(row for row in nrb["financials"] if row["year"] == 2025)
    assert latest["basis"] == "audit_report_structured_contract"
    assert latest["accounting_standard"] == "k_ifrs"
    assert latest["revenue"]["source_value"] == 59481544678
    assert latest["gross_profit"]["source_value"] == 12130397786
    assert latest["operating_profit"]["source_value"] == 4461258309
    assert latest["net_income"]["source_value"] == -563349199
    assert latest["operating_cash_flow"]["source_value"] == 3068742998
    assert latest["source_ids"] == [source_id]
    assert nrb["financial_summary"]["source_ids"] == [source_id]


def test_nrb_revenue_breakdown_over_tolerance_fails() -> None:
    payload = deepcopy(load_public_input())
    payload["financial_years"]["2025"]["revenue_breakdown"]["other_revenue"]["reported"] += 1000

    result = validate(payload, base_ref=None)
    assert not result["valid"]
    assert any(issue["code"] == "revenue_breakdown_mismatch" and issue["source"] == "2025" for issue in result["issues"])


def test_nrb_source_locations_are_complete_and_refs_exist() -> None:
    payload = load_public_input()
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
    text = PUBLIC_INPUT_PATH.read_text(encoding="utf-8")
    assert "???" not in text
    assert "\ufffd" not in text

    payload = load_public_input()
    for key, child in walk(payload):
        if key not in {"forbidden_field_names"}:
            assert key not in {"consolidated_net_income", "consolidated_operating_cash_flow"}
        if isinstance(child, float):
            assert child == child
            assert child not in {float("inf"), float("-inf")}
