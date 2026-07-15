"""Regression checks for the Tier 1 DART follow-up enrichment."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPANIES_PATH = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"
AUDIT_PATH = ROOT / "artifacts" / "company-tier1-dart-follow-up" / "follow_up_audit.json"


def load_companies() -> dict[str, dict]:
    payload = json.loads(COMPANIES_PATH.read_text(encoding="utf-8"))
    return {company["company_id"]: company for company in payload["companies"]}


def assert_metric(record: dict, metric: str) -> None:
    value = record.get(metric)
    assert isinstance(value, dict), f"{record.get('year')} {metric} missing"
    assert value.get("source_ids"), f"{record.get('year')} {metric} source_ids missing"
    assert value.get("source_unit") == "KRW", f"{record.get('year')} {metric} source unit mismatch"
    assert value.get("normalized_unit") == "KRW_MILLION", f"{record.get('year')} {metric} normalized unit mismatch"


def main() -> None:
    companies = load_companies()
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

    assert audit["audit_status"] == "passed"
    assert audit["summary"]["target_company_ids"] == ["m3-systems", "jinwoo-inc"]
    assert audit["summary"]["source_id_missing_count"] == 0
    assert audit["summary"]["unit_missing_count"] == 0
    assert audit["summary"]["mixed_scope_count"] == 0
    assert audit["summary"]["api_key_exposure_count"] == 0
    assert audit["summary"]["existing_company_regression_count"] == 0

    m3 = companies["m3-systems"]
    assert (m3.get("dart_identity") or {}).get("identity_status") == "confirmed"
    assert (m3.get("dart_identity") or {}).get("dart_corp_code") == "01915408"
    by_year = {item["year"]: item for item in m3.get("financials", [])}
    assert sorted(by_year, reverse=True) == [2025, 2024]
    assert by_year[2025].get("evidence_type") == "standalone_annual_report"
    assert by_year[2024].get("evidence_type") == "comparative_financial_statement"
    assert by_year[2024].get("source_report_year") == 2025
    assert by_year[2024].get("source_rcept_no") == "20260409001882"
    assert by_year[2024]["revenue"]["source_value"] == 3_100_399_898
    assert by_year[2024]["operating_profit"]["source_value"] == -408_806_238
    assert by_year[2024]["net_income"]["source_value"] == -485_882_562
    for year in [2025, 2024]:
        record = by_year[year]
        assert record.get("reporting_scope") == "separate"
        assert record["total_assets"]["source_value"] == record["total_liabilities"]["source_value"] + record["total_equity"]["source_value"]
        for metric in [
            "revenue",
            "cost_of_sales",
            "gross_profit",
            "operating_profit",
            "net_income",
            "total_assets",
            "total_liabilities",
            "total_equity",
            "current_assets",
            "current_liabilities",
            "operating_cash_flow",
            "investing_cash_flow",
            "financing_cash_flow",
        ]:
            assert_metric(record, metric)
    m3_audits = {item["fiscal_year"]: item for item in m3.get("audit_information", [])}
    assert m3_audits[2025]["auditor"] == "공인회계사 김덕수"
    assert m3_audits[2025]["audit_opinion"] == "unmodified"
    assert m3_audits[2024]["evidence_type"] == "comparative_financial_statement"

    jinwoo = companies["jinwoo-inc"]
    assert (jinwoo.get("dart_identity") or {}).get("identity_status") == "manual_review_required"
    assert not jinwoo.get("financials")
    assert not jinwoo.get("audit_information")

    geogwang = companies["geogwang-enterprise"]
    assert {item["audit_opinion"] for item in geogwang.get("audit_information", [])} == {"qualified"}
    assert len(geogwang.get("financials", [])) == 3

    print("TIER 1 DART FOLLOW-UP TESTS PASSED")


if __name__ == "__main__":
    main()
