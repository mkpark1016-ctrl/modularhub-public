import copy
import json
from pathlib import Path

from scripts.verify_general_contractor_financial_production import (
    REQUIRED_COMPANIES,
    compare_contractor_blocks,
    validate_payload,
)

ROOT = Path(__file__).resolve().parents[1]
INSIGHTS_PATH = ROOT / "frontend/public/data/companies/company_report_insights.json"


def load_current_payload():
    return json.loads(INSIGHTS_PATH.read_text(encoding="utf-8"))


def company_by_id(payload, company_id):
    return next(row for row in payload["companies"] if row["company_id"] == company_id)


def test_current_general_contractor_financial_contract_is_complete():
    payload = load_current_payload()
    assert validate_payload(payload) == []
    assert REQUIRED_COMPANIES.keys() <= {
        row["company_id"] for row in payload["companies"]
    }


def test_missing_general_contractor_is_rejected():
    payload = load_current_payload()
    payload["companies"] = [
        row for row in payload["companies"] if row["company_id"] != "dl-enc"
    ]
    errors = validate_payload(payload)
    assert any("dl-enc: company View Model missing" in error for error in errors)


def test_old_working_capital_semantics_are_rejected():
    payload = copy.deepcopy(load_current_payload())
    company = company_by_id(payload, "gs-ec")
    company["financial_health"]["working_capital"].update(
        {
            "rule_id": "receivables_to_revenue_observation",
            "threshold": 30,
            "metric_ids": ["receivables_total", "receivables_to_revenue_pct"],
        }
    )
    errors = validate_payload(payload)
    assert any("gs-ec: working_capital rule_id" in error for error in errors)
    assert any("gs-ec: working_capital threshold" in error for error in errors)
    assert any("gs-ec: working_capital does not use" in error for error in errors)


def test_production_drift_is_detected_per_contractor():
    expected = load_current_payload()
    actual = copy.deepcopy(expected)
    company = company_by_id(actual, "hyundai-engineering")
    company["financial_health"]["receivables_burden"]["actual_value"] = 999.9

    errors = compare_contractor_blocks(actual, expected)
    assert errors == ["production drift detected for hyundai-engineering"]
