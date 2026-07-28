from __future__ import annotations

import json
import subprocess
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.build_company_report_insights import DEFAULT_OUTPUT, build_view_model, stable_json
from scripts.validate_company_audit_financials import load_payload, validate

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "company_reports" / "company_report_insights_v1.schema.json"


def load_output() -> dict:
    return json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))


def yuchang_company(payload: dict) -> dict:
    return next(company for company in payload["companies"] if company["company_id"] == "yuchang-enc")


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
