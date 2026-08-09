from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.build_company_data_coverage import (
    DEFAULT_COMPANIES,
    DEFAULT_REPORT_INSIGHTS,
    DEFAULT_SUPPLEMENTS,
    FRESHNESS_POLICIES,
    SCHEMA_VERSION,
    build_payload,
    build_snapshot,
    check_outputs,
    date_is_future,
    discover_public_audit_source,
    effective_company_universe,
    metric_status,
    parse_date,
    stable_json,
    write_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
AS_OF_DATE = "2026-08-09"
SCHEMA_PATH = ROOT / "schemas" / "company_reports" / "company_data_coverage_v1.schema.json"
SUPPLEMENT_SCHEMA_PATH = ROOT / "schemas" / "company_reports" / "public_company_supplements_v1.schema.json"


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


def test_public_company_supplements_schema_passes() -> None:
    schema = json.loads(SUPPLEMENT_SCHEMA_PATH.read_text(encoding="utf-8"))
    payload = json.loads(DEFAULT_SUPPLEMENTS.read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    assert errors == []
    assert payload["companies"] == []


def test_discovers_public_company_universe_and_audit_backed_companies() -> None:
    payload = generated_payload()
    companies = json.loads(DEFAULT_COMPANIES.read_text(encoding="utf-8"))["companies"]
    supplements = json.loads(DEFAULT_SUPPLEMENTS.read_text(encoding="utf-8"))["companies"]
    insights = json.loads(DEFAULT_REPORT_INSIGHTS.read_text(encoding="utf-8"))["companies"]
    assert payload["summary"]["canonical_company_count"] == len(companies) == 11
    assert payload["summary"]["supplemental_public_company_count"] == len(supplements) == 0
    assert payload["summary"]["effective_public_company_count"] == 11
    assert payload["summary"]["total_company_count"] == 11
    assert payload["summary"]["audit_backed_company_count"] == len(insights)
    assert payload["summary"]["audit_backed_company_count"] == 6
    assert payload["summary"]["full_three_year_audit_count"] == 6
    assert payload["summary"]["canonical_company_ids"] == sorted(company["company_id"] for company in companies)
    assert payload["summary"]["supplemental_company_ids"] == []
    assert payload["summary"]["company_ids"] == payload["summary"]["effective_public_company_ids"]
    assert "daeseung-engineering" in payload["summary"]["canonical_company_ids"]
    assert "daeseung-engineering" in payload["summary"]["effective_public_company_ids"]
    assert payload["summary"]["audit_company_ids"] == sorted(company["company_id"] for company in insights)


def test_canonical_daeseung_is_effective_public_company_not_orphan() -> None:
    payload = generated_payload()
    assert "daeseung-engineering" in payload["summary"]["audit_company_ids"]
    assert "daeseung-engineering" in payload["summary"]["canonical_company_ids"]
    assert "daeseung-engineering" not in payload["summary"]["supplemental_company_ids"]
    assert "daeseung-engineering" in payload["summary"]["effective_public_company_ids"]
    assert payload["summary"]["audit_company_ids_not_in_universe"] == []
    daeseung = next(company for company in payload["companies"] if company["company_id"] == "daeseung-engineering")
    assert daeseung["company_record_source"] == "canonical"
    assert daeseung["audit_financials_available"] is True
    assert daeseung["audit_coverage_state"] == "complete"
    assert payload["consistency"]["status"] == "clean"
    assert payload["consistency"]["issue_count"] == 0
    assert payload["consistency"]["audit_record_without_company_master_ids"] == []
    daeseung_items = [item for item in payload["priority_queue"] if item["company_id"] == "daeseung-engineering"]
    assert all(item["recommended_next_action"] != "canonical_company_migration" for item in daeseung_items)
    assert all("supplemental_profile_not_canonicalized" not in item["reason_codes"] for item in daeseung_items)


def test_true_orphan_audit_record_remains_p0_with_empty_supplements(tmp_path: Path) -> None:
    parsed = parse_date(AS_OF_DATE)
    assert parsed is not None
    companies_payload = {
        "companies": [{"company_id": "canonical-sample", "company_name": "Canonical Sample", "last_verified_at": AS_OF_DATE}]
    }
    insights_payload = {
        "schema_version": "company_report_insights_v1",
        "companies": [
            {
                "company_id": "orphan-audit",
                "company_name": "Orphan Audit",
                "available_years": [2023, 2024, 2025],
                "latest_year": 2025,
                "financial_series": [],
                "source_summary": {"latest_report_date": AS_OF_DATE},
                "data_quality": {},
                "evidence_health": [],
            }
        ],
    }
    companies_path = tmp_path / "companies.json"
    insights_path = tmp_path / "company_report_insights.json"
    companies_path.write_text(json.dumps(companies_payload), encoding="utf-8")
    insights_path.write_text(json.dumps(insights_payload), encoding="utf-8")
    write_audit_source(tmp_path / "orphan-audit" / "audit_financials_2023_2025.json", [2023, 2024, 2025])
    payload = build_payload(
        as_of_date=parsed,
        companies_path=companies_path,
        report_insights_path=insights_path,
        supplements_path=write_supplements(tmp_path / "supplements.json"),
        source_root=tmp_path,
    )
    assert payload["consistency"]["audit_record_without_company_master_ids"] == ["orphan-audit"]
    item = next(item for item in payload["priority_queue"] if item["company_id"] == "orphan-audit")
    assert item["item_type"] == "consistency_issue"
    assert item["priority"] == "P0"
    assert item["recommended_next_action"] == "company_universe_reconciliation"


def test_synthetic_supplement_is_discovered_without_python_company_id_hardcoding(tmp_path: Path) -> None:
    parsed = parse_date(AS_OF_DATE)
    assert parsed is not None
    companies_payload = {
        "companies": [{"company_id": "canonical-sample", "company_name": "Canonical Sample", "last_verified_at": AS_OF_DATE}]
    }
    insights_payload = {
        "schema_version": "company_report_insights_v1",
        "companies": [
            {
                "company_id": "synthetic-supplement",
                "company_name": "Synthetic Supplement",
                "available_years": [2023, 2024, 2025],
                "latest_year": 2025,
                "financial_series": [],
                "source_summary": {"latest_report_date": AS_OF_DATE},
                "data_quality": {},
                "evidence_health": [],
            }
        ],
    }
    supplements = [
        {"company_id": "synthetic-supplement", "company_name": "Synthetic Supplement", "last_verified_at": AS_OF_DATE}
    ]
    companies_path = tmp_path / "companies.json"
    insights_path = tmp_path / "company_report_insights.json"
    companies_path.write_text(json.dumps(companies_payload), encoding="utf-8")
    insights_path.write_text(json.dumps(insights_payload), encoding="utf-8")
    write_audit_source(tmp_path / "synthetic-supplement" / "audit_financials_2023_2025.json", [2023, 2024, 2025])
    payload = build_payload(
        as_of_date=parsed,
        companies_path=companies_path,
        report_insights_path=insights_path,
        supplements_path=write_supplements(tmp_path / "supplements.json", supplements),
        source_root=tmp_path,
    )
    company = next(item for item in payload["companies"] if item["company_id"] == "synthetic-supplement")
    assert company["company_record_source"] == "supplemental"
    assert payload["consistency"]["audit_record_without_company_master_ids"] == []
    assert "synthetic-supplement" in payload["summary"]["supplemental_company_ids"]
    assert "daeseung-engineering" not in (ROOT / "scripts" / "build_company_data_coverage.py").read_text(encoding="utf-8")


def test_effective_universe_deduplicates_supplements_with_canonical_precedence() -> None:
    effective = effective_company_universe(
        [{"company_id": "sample", "company_name": "Canonical Name"}],
        [
            {"company_id": "sample", "company_name": "Supplement Name"},
            {"company_id": "supplement-only", "company_name": "Supplement Only"},
        ],
    )
    by_id = {company["company_id"]: company for company in effective}
    assert sorted(by_id) == ["sample", "supplement-only"]
    assert by_id["sample"]["company_name"] == "Canonical Name"
    assert by_id["sample"]["company_record_source"] == "canonical"
    assert by_id["supplement-only"]["company_record_source"] == "supplemental"


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
    assert payload["summary"]["work_item_priority_counts"]["P1"] >= 1
    gs = next(item for item in queue if item["company_id"] == "gs-ec")
    assert gs["item_type"] == "company_data_gap"
    assert gs["priority"] == "P1"
    assert gs["recommended_next_action"] == "audit_report_onboarding"
    assert "missing_audit_financials" in gs["reason_codes"]


def test_company_priority_counts_and_work_item_counts_are_separate() -> None:
    payload = generated_payload()
    company_counts = payload["summary"]["company_priority_counts"]
    work_item_counts = payload["summary"]["work_item_priority_counts"]
    assert sum(company_counts.values()) == payload["summary"]["total_company_count"]
    assert sum(work_item_counts.values()) == len(payload["priority_queue"])
    assert company_counts["P3"] > 0
    assert work_item_counts["P0"] == 0
    assert work_item_counts["P2"] >= 1
    assert payload["summary"]["priority_counts"] == work_item_counts


def test_audit_record_counts_are_split_between_all_records_and_public_universe() -> None:
    payload = generated_payload()
    assert payload["summary"]["audit_record_count"] == 6
    assert payload["summary"]["audit_backed_company_count"] == 6
    assert payload["summary"]["audit_backed_in_canonical_universe_count"] == 6
    assert payload["summary"]["audit_backed_in_universe_count"] == 6
    assert payload["summary"]["audit_backed_in_effective_universe_count"] == 6
    assert payload["summary"]["full_three_year_audit_record_count"] == 6
    assert payload["summary"]["full_three_year_audit_in_canonical_universe_count"] == 6
    assert payload["summary"]["full_three_year_audit_in_universe_count"] == 6
    assert payload["summary"]["full_three_year_audit_in_effective_universe_count"] == 6


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
    supplements_path = write_supplements(tmp_path / "supplements.json")
    added = build_payload(as_of_date=parsed, companies_path=companies_path, supplements_path=supplements_path)
    assert added["summary"]["total_company_count"] == original_count + 1
    assert "sample-new-company" in added["summary"]["company_ids"]

    companies_payload["companies"] = companies_payload["companies"][:-2]
    removed_path = tmp_path / "companies-removed.json"
    removed_path.write_text(json.dumps(companies_payload, ensure_ascii=False), encoding="utf-8")
    removed = build_payload(as_of_date=parsed, companies_path=removed_path, supplements_path=supplements_path)
    assert removed["summary"]["total_company_count"] == original_count - 1


def test_missing_dates_are_safe_unknown_values() -> None:
    from scripts.build_company_data_coverage import freshness_state

    assert freshness_state(None, date(2026, 8, 9), FRESHNESS_POLICIES["company_profile"]) == "unknown"


def test_partial_and_iso_date_parser_contract() -> None:
    assert parse_date("2026-08-09") == date(2026, 8, 9)
    assert parse_date("2026-08") == date(2026, 8, 1)
    assert parse_date("2026") == date(2026, 1, 1)
    assert parse_date("2026-08-09T10:15:00+09:00") == date(2026, 8, 9)
    assert parse_date("2026-08-09T01:15:00Z") == date(2026, 8, 9)
    assert parse_date("invalid") is None
    assert parse_date("") is None
    assert parse_date(None) is None


def test_future_date_signal_becomes_p0_consistency_reason(tmp_path: Path) -> None:
    from scripts.build_company_data_coverage import parse_date

    parsed = parse_date(AS_OF_DATE)
    assert parsed is not None
    companies_payload = json.loads(DEFAULT_COMPANIES.read_text(encoding="utf-8"))
    companies_payload["companies"] = [dict(companies_payload["companies"][0])]
    companies_payload["companies"][0]["last_verified_at"] = "2027-01-01"
    companies_path = tmp_path / "companies.json"
    companies_path.write_text(json.dumps(companies_payload, ensure_ascii=False), encoding="utf-8")
    insight_payload = {"schema_version": "company_report_insights_v1", "companies": []}
    insights_path = tmp_path / "company_report_insights.json"
    insights_path.write_text(json.dumps(insight_payload), encoding="utf-8")
    payload = build_payload(
        as_of_date=parsed,
        companies_path=companies_path,
        report_insights_path=insights_path,
        supplements_path=write_supplements(tmp_path / "supplements.json"),
        source_root=tmp_path / "reports",
    )
    company = payload["companies"][0]
    assert date_is_future("2027-01-01", parsed)
    assert "future_verification_date" in company["recommendation_reason_codes"]
    assert company["recommendation_priority"] == "P0"


def test_priority_filter_limits_queue() -> None:
    from scripts.build_company_data_coverage import parse_date

    parsed = parse_date(AS_OF_DATE)
    assert parsed is not None
    payload = build_payload(as_of_date=parsed, priority="P2")
    assert payload["priority_queue"]
    assert {item["priority"] for item in payload["priority_queue"]} == {"P2"}


def write_audit_source(path: Path, years: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "company_audit_financials_v1",
        "financial_years": {str(year): {} for year in years},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_supplements(path: Path, companies: list[dict] | None = None) -> Path:
    payload = {"schema_version": "public_company_supplements_v1", "companies": companies or []}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_public_audit_source_discovery_accepts_future_year_filename(tmp_path: Path) -> None:
    write_audit_source(tmp_path / "sample" / "audit_financials_2024_2026.json", [2024, 2025, 2026])
    discovered = discover_public_audit_source("sample", tmp_path)
    assert discovered["status"] == "found"
    assert discovered["path"].name == "audit_financials_2024_2026.json"


def test_public_audit_source_discovery_excludes_onboarding_staging_and_candidates(tmp_path: Path) -> None:
    write_audit_source(tmp_path / "sample" / "audit_financials_2023_2025.json", [2023, 2024, 2025])
    write_audit_source(tmp_path / "sample" / "staging" / "audit_financials_2026_2028.json", [2026, 2027, 2028])
    write_audit_source(tmp_path / "sample" / "onboarding" / "candidate_audit_financials.json", [2026, 2027, 2028])
    write_audit_source(tmp_path / "sample" / "audit_financials_candidate_2026_2028.json", [2026, 2027, 2028])
    discovered = discover_public_audit_source("sample", tmp_path)
    assert discovered["status"] == "found"
    assert discovered["path"].name == "audit_financials_2023_2025.json"


def test_public_audit_source_discovery_uses_latest_year_then_filename_tiebreak(tmp_path: Path) -> None:
    write_audit_source(tmp_path / "sample" / "audit_financials_2021_2023.json", [2021, 2022, 2023])
    write_audit_source(tmp_path / "sample" / "audit_financials_2024_2026.json", [2024, 2025, 2026])
    discovered = discover_public_audit_source("sample", tmp_path)
    assert discovered["path"].name == "audit_financials_2024_2026.json"


def test_public_audit_source_discovery_flags_same_span_ambiguity(tmp_path: Path) -> None:
    write_audit_source(tmp_path / "sample" / "audit_financials_2023_2025.json", [2023, 2024, 2025])
    write_audit_source(tmp_path / "sample" / "audit_financials_2023_2025_revised.json", [2023, 2024, 2025])
    discovered = discover_public_audit_source("sample", tmp_path)
    assert discovered["status"] == "ambiguous"
    assert discovered["ambiguous"] is True
    assert discovered["path"].name == "audit_financials_2023_2025.json"


def test_referential_integrity_detects_insight_without_source_and_source_without_insight(tmp_path: Path) -> None:
    from scripts.build_company_data_coverage import parse_date

    parsed = parse_date(AS_OF_DATE)
    assert parsed is not None
    companies_payload = {
        "companies": [
            {"company_id": "with-source-only", "company_name": "With Source", "last_verified_at": AS_OF_DATE},
            {"company_id": "with-insight-only", "company_name": "With Insight", "last_verified_at": AS_OF_DATE},
        ]
    }
    insights_payload = {
        "schema_version": "company_report_insights_v1",
        "companies": [
            {
                "company_id": "with-insight-only",
                "company_name": "With Insight",
                "available_years": [2023, 2024, 2025],
                "latest_year": 2025,
                "financial_series": [],
                "source_summary": {"latest_report_date": AS_OF_DATE},
                "data_quality": {},
                "evidence_health": [],
            }
        ],
    }
    companies_path = tmp_path / "companies.json"
    insights_path = tmp_path / "company_report_insights.json"
    companies_path.write_text(json.dumps(companies_payload), encoding="utf-8")
    insights_path.write_text(json.dumps(insights_payload), encoding="utf-8")
    write_audit_source(tmp_path / "with-source-only" / "audit_financials_2023_2025.json", [2023, 2024, 2025])
    payload = build_payload(
        as_of_date=parsed,
        companies_path=companies_path,
        report_insights_path=insights_path,
        supplements_path=write_supplements(tmp_path / "supplements.json"),
        source_root=tmp_path,
    )
    assert payload["consistency"]["audit_insight_without_public_source_ids"] == ["with-insight-only"]
    assert payload["consistency"]["public_source_without_audit_insight_ids"] == ["with-source-only"]
    assert {item["reason_codes"][0] for item in payload["consistency_priority_queue"]} == {
        "audit_insight_without_public_source",
        "public_source_without_audit_insight",
    }


def test_referential_integrity_clean_state_with_matching_master_insight_and_source(tmp_path: Path) -> None:
    from scripts.build_company_data_coverage import parse_date

    parsed = parse_date(AS_OF_DATE)
    assert parsed is not None
    companies_payload = {"companies": [{"company_id": "sample", "company_name": "Sample", "last_verified_at": AS_OF_DATE}]}
    insights_payload = {
        "schema_version": "company_report_insights_v1",
        "companies": [{"company_id": "sample", "company_name": "Sample", "available_years": [2023, 2024, 2025], "latest_year": 2025, "financial_series": [], "source_summary": {"latest_report_date": AS_OF_DATE}, "data_quality": {}, "evidence_health": []}],
    }
    companies_path = tmp_path / "companies.json"
    insights_path = tmp_path / "company_report_insights.json"
    companies_path.write_text(json.dumps(companies_payload), encoding="utf-8")
    insights_path.write_text(json.dumps(insights_payload), encoding="utf-8")
    write_audit_source(tmp_path / "sample" / "audit_financials_2023_2025.json", [2023, 2024, 2025])
    payload = build_payload(
        as_of_date=parsed,
        companies_path=companies_path,
        report_insights_path=insights_path,
        supplements_path=write_supplements(tmp_path / "supplements.json"),
        source_root=tmp_path,
    )
    assert payload["consistency"]["status"] == "clean"
    assert payload["consistency_priority_queue"] == []
