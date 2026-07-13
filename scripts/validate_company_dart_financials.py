#!/usr/bin/env python3
"""Validate DART identity, filing, audit, and financial fields for Wave 1 companies."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"
WAVE1_IDS = ["yuchang-enc", "kumkang-kind", "planm", "daeseung-engineering"]

IDENTITY_STATUSES = {"confirmed", "probable", "ambiguous", "not_found", "api_key_required"}
FINANCIAL_AREA_STATUSES = {
    "verified",
    "partially_verified",
    "filing_found_extraction_pending",
    "no_filing_found",
    "identity_ambiguous",
    "api_key_required",
    "collecting",
    "confirmed",
    "probable",
    "ambiguous",
    "not_found",
}
REPORTING_SCOPES = {"consolidated", "separate", "company_total", "modular_segment", "unknown"}
NORMALIZED_UNITS = {"KRW", "KRW_MILLION"}


def load_payload(path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def wave1_companies(path: Path = DEFAULT_INPUT) -> list[dict[str, Any]]:
    companies = load_payload(path).get("companies", [])
    by_id = {company["company_id"]: company for company in companies}
    return [by_id[company_id] for company_id in WAVE1_IDS if company_id in by_id]


def add_issue(issues: list[dict[str, Any]], code: str, company_id: str, path: str, message: str, severity: str = "error") -> None:
    issues.append({"code": code, "company_id": company_id, "path": path, "message": message, "severity": severity})


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def has_source_ids(record: dict[str, Any]) -> bool:
    return isinstance(record.get("source_ids"), list) and bool(record.get("source_ids"))


def numeric_values(record: Any) -> list[tuple[str, Any]]:
    values: list[tuple[str, Any]] = []
    if isinstance(record, dict):
        for key, value in record.items():
            if isinstance(value, (int, float)):
                values.append((key, value))
            elif isinstance(value, (dict, list)):
                values.extend((f"{key}.{path}", item) for path, item in numeric_values(value))
    elif isinstance(record, list):
        for index, item in enumerate(record):
            values.extend((f"[{index}].{path}", value) for path, value in numeric_values(item))
    return values


def validate_financial_value(company_id: str, record: dict[str, Any], path: str, issues: list[dict[str, Any]]) -> None:
    for field in ["source_value", "normalized_value"]:
        if record.get(field) is not None and not has_source_ids(record):
            add_issue(issues, "number_without_source", company_id, f"{path}.{field}", "financial numeric values require source_ids")
    if record.get("normalized_value") is not None and record.get("normalized_unit") not in NORMALIZED_UNITS:
        add_issue(issues, "unit_missing_or_invalid", company_id, f"{path}.normalized_unit", str(record.get("normalized_unit")))
    if record.get("source_value") is not None and not record.get("source_unit"):
        add_issue(issues, "unit_missing_or_invalid", company_id, f"{path}.source_unit", "source_unit is required")
    if record.get("source_value") is not None and record.get("normalization_factor") is None:
        add_issue(issues, "unit_missing_or_invalid", company_id, f"{path}.normalization_factor", "normalization_factor is required")


def validate_company(company: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    company_id = company["company_id"]
    identity = company.get("dart_identity")
    if not isinstance(identity, dict):
        add_issue(issues, "missing_dart_identity", company_id, "dart_identity", "dart_identity is required")
    else:
        if identity.get("identity_status") not in IDENTITY_STATUSES:
            add_issue(issues, "invalid_identity_status", company_id, "dart_identity.identity_status", str(identity.get("identity_status")))
        if not identity.get("dart_corp_code") and identity.get("identity_status") in {"confirmed", "probable"}:
            add_issue(issues, "missing_corp_code", company_id, "dart_identity.dart_corp_code", "confirmed/probable identity requires dart_corp_code")
        if identity.get("verified_at"):
            parsed = parse_date(identity.get("verified_at"))
            if parsed is None or parsed > date.today():
                add_issue(issues, "future_or_invalid_date", company_id, "dart_identity.verified_at", str(identity.get("verified_at")))

    filing = company.get("filing_availability")
    if not isinstance(filing, dict):
        add_issue(issues, "missing_filing_availability", company_id, "filing_availability", "filing availability is required")
    else:
        if not filing.get("searched_period"):
            add_issue(issues, "missing_search_scope", company_id, "filing_availability.searched_period", "searched_period is required")
        if not filing.get("searched_report_types"):
            add_issue(issues, "missing_search_scope", company_id, "filing_availability.searched_report_types", "searched_report_types is required")

    for index, audit in enumerate(company.get("audit_information", []) or []):
        path = f"audit_information[{index}]"
        if not audit.get("reporting_scope"):
            add_issue(issues, "reporting_scope_missing", company_id, f"{path}.reporting_scope", "audit reporting_scope is required")
        if not has_source_ids(audit):
            add_issue(issues, "source_id_missing", company_id, path, "audit information requires source_ids")
        if not audit.get("unit"):
            add_issue(issues, "unit_missing_or_invalid", company_id, f"{path}.unit", "audit unit is required")

    for index, financial in enumerate(company.get("financials", []) or []):
        path = f"financials[{index}]"
        if financial.get("reporting_scope") not in REPORTING_SCOPES:
            add_issue(issues, "reporting_scope_missing", company_id, f"{path}.reporting_scope", str(financial.get("reporting_scope")))
        if not has_source_ids(financial):
            add_issue(issues, "source_id_missing", company_id, path, "financial records require source_ids")
        for key, value in financial.items():
            if isinstance(value, dict):
                validate_financial_value(company_id, value, f"{path}.{key}", issues)
        if numeric_values(financial) and not has_source_ids(financial):
            add_issue(issues, "number_without_source", company_id, path, "financial numbers require source_ids")

    summary = company.get("financial_summary", {}) or {}
    if summary and summary.get("financial_area_status") not in FINANCIAL_AREA_STATUSES:
        add_issue(issues, "invalid_financial_area_status", company_id, "financial_summary.financial_area_status", str(summary.get("financial_area_status")))
    if summary.get("modular_segment_revenue") is not None and summary.get("modular_segment_available") is not True:
        add_issue(issues, "modular_segment_misclassification", company_id, "financial_summary.modular_segment_revenue", "modular revenue requires explicit segment availability")

    return issues


def validate(path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    companies = wave1_companies(path)
    issues = [issue for company in companies for issue in validate_company(company)]
    identities = [company.get("dart_identity", {}) for company in companies]
    corp_codes = [identity.get("dart_corp_code") for identity in identities if identity.get("dart_corp_code")]
    duplicate_corp_codes = len(corp_codes) - len(set(corp_codes))
    if duplicate_corp_codes:
        issues.append({"code": "duplicate_corp_code", "company_id": "", "path": "dart_identity.dart_corp_code", "message": "duplicate DART corp_code", "severity": "error"})
    financial_years = sum(len(company.get("financials", []) or []) for company in companies)
    reports_found = sum(int((company.get("filing_availability", {}) or {}).get("reports_found_count") or 0) for company in companies)
    status_counts: dict[str, int] = {}
    for identity in identities:
        status = identity.get("identity_status", "missing")
        status_counts[status] = status_counts.get(status, 0) + 1
    issue_counts = {
        "missing_dart_identity": sum(1 for issue in issues if issue["code"] == "missing_dart_identity"),
        "corp_code_duplicate": duplicate_corp_codes,
        "ambiguous_identity": status_counts.get("ambiguous", 0),
        "api_key_required": status_counts.get("api_key_required", 0),
        "reports_found": reports_found,
        "audit_report_years": sum(len(company.get("audit_information", []) or []) for company in companies),
        "financial_years": financial_years,
        "reporting_scope_missing": sum(1 for issue in issues if issue["code"] == "reporting_scope_missing"),
        "source_id_missing": sum(1 for issue in issues if issue["code"] == "source_id_missing"),
        "unit_missing": sum(1 for issue in issues if issue["code"] == "unit_missing_or_invalid"),
        "value_mismatch": sum(1 for issue in issues if issue["code"] == "value_mismatch"),
        "asset_equation_mismatch": sum(1 for issue in issues if issue["code"] == "asset_equation_mismatch"),
        "cashflow_mismatch": sum(1 for issue in issues if issue["code"] == "cashflow_mismatch"),
        "mixed_reporting_scope": sum(1 for issue in issues if issue["code"] == "mixed_reporting_scope"),
        "pre_correction_report_used": sum(1 for issue in issues if issue["code"] == "pre_correction_report_used"),
        "modular_segment_misclassification": sum(1 for issue in issues if issue["code"] == "modular_segment_misclassification"),
        "number_without_source": sum(1 for issue in issues if issue["code"] == "number_without_source"),
        "future_date": sum(1 for issue in issues if issue["code"] == "future_or_invalid_date"),
        "manual_review_required": sum(1 for issue in issues if issue["severity"] == "warning"),
    }
    return {
        "valid": not any(issue["severity"] == "error" for issue in issues),
        "wave_1_company_count": len(companies),
        "identity_status_counts": status_counts,
        "issue_counts": issue_counts,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Wave 1 DART financial enrichment fields.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    result = validate(args.input)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
