from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.build_company_data_coverage import (
    DEFAULT_COMPANIES,
    DEFAULT_REPORT_INSIGHTS,
    FRESHNESS_POLICIES,
    SCHEMA_VERSION,
    build_payload,
    build_snapshot,
    check_outputs,
    metric_status,
    stable_json,
    write_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
AS_OF_DATE = "2026-08-09"
SCHEMA_PATH = ROOT / "schemas" / "company_reports" / "company_data_coverage_v1.schema.json"


def generated_payload() -> dict:
    from scripts.build_company_data_coverage import parse_date

    parsed = parse_date(AS_OF_DATE)
    assert parsed is not None
    return build_payload(as_of_date=parsed)


def test_company_data_coverage_schema_passes() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    payload = generated_payload()
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    assert errors == []


def test_discovers_public_company_universe_and_audit_backed_companies() -> None:
    payload = generated_payload()
    companies = json.loads(DEFAULT_COMPANIES.read_text(encoding="utf-8"))["companies"]
    insights = json.loads(DEFAULT_REPORT_INSIGHTS.read_text(encoding="utf-8"))["companies"]
    assert payload["summary"]["total_company_count"] == len(companies)
    assert payload["summary"]["audit_backed_company_count"] == len(insights)
    assert payload["summary"]["audit_backed_company_count"] == 6
    assert payload["summary"]["full_three_year_audit_count"] == 6
    assert payload["summary"]["company_ids"] == sorted(company["company_id"] for company in companies)
    assert payload["summary"]["audit_company_ids"] == sorted(company["company_id"] for company in insights)


def test_reports_audit_companies_outside_public_universe_without_promoting_them() -> None:
    payload = generated_payload()
    assert "daeseung-engineering" in payload["summary"]["audit_company_ids"]
    assert "daeseung-engineering" not in payload["summary"]["company_ids"]
    assert payload["summary"]["audit_company_ids_not_in_universe"] == ["daeseung-engineering"]
    assert all(company["company_id"] != "daeseung-engineering" for company in payload["companies"])


def test_metric_status_preserves_zero_and_null_meanings() -> None:
    assert metric_status({"raw_krw": 0}) == "reported"
    assert metric_status({"raw_krw": -1}) == "reported"
    assert metric_status({"raw_krw": None, "disclosure_status": "not_disclosed"}) == "not_disclosed"
    assert metric_status({"raw_krw": None, "disclosure_status": "not_applicable"}) == "not_applicable"
    assert metric_status({"raw_krw": None, "disclosure_status": "verification_pending"}) == "verification_pending"
    assert metric_status({"raw_krw": None}) == "missing"
    assert metric_status(None) == "missing"


def test_audit_states_are_state_labels_not_scores() -> None:
    payload = generated_payload()
    states = {company["audit_coverage_state"] for company in payload["companies"]}
    assert states <= {"complete", "partial", "unavailable", "verification_pending"}
    rendered = json.dumps(payload, ensure_ascii=False)
    assert "company_score" not in rendered
    assert "competitiveness_score" not in rendered
    assert "rank_score" not in rendered


def test_audit_complete_verification_pending_and_unavailable_are_distinguished() -> None:
    companies = {company["company_id"]: company for company in generated_payload()["companies"]}
    assert companies["kumkang-kind"]["audit_coverage_state"] == "complete"
    assert companies["planm"]["audit_coverage_state"] == "verification_pending"
    assert companies["gs-ec"]["audit_coverage_state"] == "unavailable"


def test_operational_and_freshness_states_are_calculated() -> None:
    payload = generated_payload()
    assert payload["summary"]["operational_coverage_state_counts"]["sufficiently_covered"] >= 1
    assert payload["summary"]["freshness_state_counts"]["current"] == payload["summary"]["total_company_count"]
    assert all(company["freshness_state"] in {"current", "aging", "stale", "unknown"} for company in payload["companies"])


def test_priority_queue_contains_data_work_priorities() -> None:
    payload = generated_payload()
    queue = payload["priority_queue"]
    assert queue
    assert payload["summary"]["priority_counts"]["P1"] >= 1
    gs = next(item for item in queue if item["company_id"] == "gs-ec")
    assert gs["priority"] == "P1"
    assert gs["recommended_next_action"] == "audit_report_onboarding"
    assert "missing_audit_financials" in gs["reason_codes"]


def test_builder_is_deterministic_for_fixed_as_of_date() -> None:
    assert stable_json(generated_payload()) == stable_json(generated_payload())
    assert stable_json(build_snapshot(generated_payload())) == stable_json(build_snapshot(generated_payload()))


def test_check_output_detects_and_accepts_generated_files(tmp_path: Path) -> None:
    payload = generated_payload()
    artifact_dir = tmp_path / "artifacts"
    snapshot = tmp_path / "snapshot.json"
    assert check_outputs(payload, artifact_dir, snapshot)
    write_outputs(payload, artifact_dir, snapshot)
    assert check_outputs(payload, artifact_dir, snapshot) == []


def test_new_company_and_removed_company_are_reflected_from_input_files(tmp_path: Path) -> None:
    from scripts.build_company_data_coverage import parse_date

    parsed = parse_date(AS_OF_DATE)
    assert parsed is not None
    companies_payload = json.loads(DEFAULT_COMPANIES.read_text(encoding="utf-8"))
    original_count = len(companies_payload["companies"])
    sample_company = dict(companies_payload["companies"][0])
    sample_company["company_id"] = "sample-new-company"
    sample_company["company_name"] = "Sample New Company"
    companies_payload["companies"].append(sample_company)
    companies_path = tmp_path / "companies-added.json"
    companies_path.write_text(json.dumps(companies_payload, ensure_ascii=False), encoding="utf-8")
    added = build_payload(as_of_date=parsed, companies_path=companies_path)
    assert added["summary"]["total_company_count"] == original_count + 1
    assert "sample-new-company" in added["summary"]["company_ids"]

    companies_payload["companies"] = companies_payload["companies"][:-2]
    removed_path = tmp_path / "companies-removed.json"
    removed_path.write_text(json.dumps(companies_payload, ensure_ascii=False), encoding="utf-8")
    removed = build_payload(as_of_date=parsed, companies_path=removed_path)
    assert removed["summary"]["total_company_count"] == original_count - 1


def test_missing_dates_are_safe_unknown_values() -> None:
    from scripts.build_company_data_coverage import freshness_state

    assert freshness_state(None, date(2026, 8, 9), FRESHNESS_POLICIES["company_profile"]) == "unknown"


def test_priority_filter_limits_queue() -> None:
    from scripts.build_company_data_coverage import parse_date

    parsed = parse_date(AS_OF_DATE)
    assert parsed is not None
    payload = build_payload(as_of_date=parsed, priority="P2")
    assert payload["priority_queue"]
    assert {item["priority"] for item in payload["priority_queue"]} == {"P2"}
