from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "data" / "company_reports" / "planm" / "restatement_source_matrix_2023_2025.json"
PROTECTED_PUBLIC_FILES = [
    ROOT / "frontend" / "public" / "data" / "companies" / "company_report_insights.json",
    ROOT / "frontend" / "public" / "data" / "companies" / "companies.json",
    ROOT / "frontend" / "public" / "data" / "companies" / "company_intelligence_v2.json",
    ROOT / "frontend" / "public" / "data" / "news.json",
    ROOT / "frontend" / "public" / "data" / "business.json",
]


def load_matrix() -> dict:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def final_metric(payload: dict, year: str, metric: str) -> dict:
    return payload["financial_years"][year]["metrics"][metric]["final_selected"]


def all_amount_nodes(value):
    if isinstance(value, dict):
        if "amount_krw" in value:
            yield value
        for child in value.values():
            yield from all_amount_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from all_amount_nodes(child)


def test_planm_restatement_matrix_identity_and_years() -> None:
    payload = load_matrix()
    assert payload["schema_version"] == "planm_restatement_source_matrix_v1"
    assert payload["company_id"] == "planm"
    assert payload["company_name"] == "주식회사 플랜엠"
    assert sorted(payload["financial_years"]) == ["2023", "2024", "2025"]
    assert payload["validation_metadata"]["public_application_status"] == "not_applied"
    assert payload["validation_metadata"]["pdf_files_copied_to_repository"] is False


def test_source_priority_keeps_original_and_restated_sources_distinct() -> None:
    payload = load_matrix()
    assert payload["source_priority"]["2023"]["original_source_ref"] == "planm_audit_report_2024_04_15"
    assert payload["source_priority"]["2023"]["selected_source_ref"] == "planm_audit_report_2025_04_24"
    assert payload["source_priority"]["2023"]["selected_basis"] == "first_restated_comparative_financial_statements"
    assert payload["source_priority"]["2024"]["selected_source_ref"] == "planm_audit_report_2026_06_25"
    assert payload["source_priority"]["2024"]["selected_basis"] == "latest_restated_comparative_financial_statements"
    assert payload["source_priority"]["2025"]["selected_source_ref"] == "planm_audit_report_2026_06_25"
    assert payload["source_priority"]["2025"]["selected_basis"] == "current_year_financial_statements"


def test_minimum_metric_set_exists_for_every_year() -> None:
    payload = load_matrix()
    required = set(payload["validation_metadata"]["minimum_metric_set"])
    assert len(required) == 37
    for year, record in payload["financial_years"].items():
        assert set(record["metrics"]) == required, year


def test_all_amounts_are_integer_won_or_explicit_null() -> None:
    for node in all_amount_nodes(load_matrix()):
        amount = node["amount_krw"]
        assert amount is None or isinstance(amount, int)
        if amount is None:
            assert node["status"] in {"not_disclosed", "not_applicable", "pending_manual_page_check"}


def test_final_selected_metrics_have_source_and_location() -> None:
    payload = load_matrix()
    locations = payload["source_locations"]
    for year, record in payload["financial_years"].items():
        for metric, metric_record in record["metrics"].items():
            final = metric_record["final_selected"]
            assert final["source_ref"], (year, metric)
            assert final["source_location_id"] in locations, (year, metric)
            assert final["status"], (year, metric)


def test_original_reported_and_final_selected_are_distinguished_for_restatements() -> None:
    payload = load_matrix()
    revenue_2023 = payload["financial_years"]["2023"]["metrics"]["revenue"]
    assert revenue_2023["original_reported"]["amount_krw"] == 65396340955
    assert revenue_2023["first_restated"]["amount_krw"] == 59483443620
    assert revenue_2023["final_selected"]["amount_krw"] == 59483443620

    net_income_2024 = payload["financial_years"]["2024"]["metrics"]["net_income"]
    assert net_income_2024["original_reported"]["amount_krw"] == 15401744703
    assert net_income_2024["latest_restated"]["amount_krw"] == 38537785703
    assert net_income_2024["final_selected"]["source_ref"] == "planm_audit_report_2026_06_25"


def test_2025_current_values_use_2026_report() -> None:
    payload = load_matrix()
    assert final_metric(payload, "2025", "revenue") == {
        "amount_krw": 59222859418,
        "source_ref": "planm_audit_report_2026_06_25",
        "source_location_id": "loc_2026_is_9_10",
        "status": "reported",
    }
    assert final_metric(payload, "2025", "net_income")["amount_krw"] == -9533441167
    assert final_metric(payload, "2025", "operating_cash_flow")["amount_krw"] == -12031387244


def test_uncertain_or_not_applicable_values_are_not_stored_as_zero() -> None:
    payload = load_matrix()
    fnb_2023 = final_metric(payload, "2023", "fnb_revenue")
    bonds_2023 = final_metric(payload, "2023", "bonds")
    assert fnb_2023["amount_krw"] is None
    assert fnb_2023["status"] == "not_applicable"
    assert bonds_2023["amount_krw"] is None
    assert bonds_2023["status"] == "not_applicable"


def test_pending_manual_page_check_is_explicitly_recorded() -> None:
    payload = load_matrix()
    statuses = [
        item["status"]
        for item in payload["unresolved_items"]
    ]
    assert "pending_manual_page_check" in statuses
    assert payload["source_documents"]["planm_audit_report_2024_04_15"]["auditor_report_date"] is None
    assert (
        payload["source_documents"]["planm_audit_report_2024_04_15"][
            "auditor_report_date_verification_status"
        ]
        == "pending_manual_page_check"
    )


def test_restatement_events_capture_required_adjustments() -> None:
    events = {event["event_id"]: event for event in load_matrix()["restatement_events"]}
    assert events["planm_2023_prior_period_error_correction"]["adjustment_amount"] == 8153938000
    assert events["planm_2024_period_attribution_error"]["adjustment_amount"] == 4306868000
    assert events["planm_2023_additional_opening_restatement_cross_check"]["adjustment_amount"] == 777851000
    assert events["planm_revenue_recognition_timing_change"]["adjustment_amount"] == 5912897000
    assert events["planm_rental_asset_useful_life_policy_change"]["adjustment_amount"] == 26665058000


def test_existing_company_report_insights_and_public_json_are_unchanged() -> None:
    protected = [str(path.relative_to(ROOT)) for path in PROTECTED_PUBLIC_FILES if path.exists()]
    result = subprocess.run(
        ["git", "diff", "--name-only", "--", *protected],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.stdout.strip() == ""
