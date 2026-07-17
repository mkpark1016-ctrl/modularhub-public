#!/usr/bin/env python3
"""Validate source-backed company research records for Wave 1."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from company_publication import load_public_company_ids

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"
WAVE1_IDS = load_public_company_ids()

PROFILE_FIELDS_REQUIRING_SOURCES = [
    "company_name_en",
    "headquarters",
    "website_url",
    "listed_market",
    "ticker",
    "summary",
    "business_status",
    "modular_methods",
    "target_markets",
]
NUMBER_FIELDS = {
    "capacity_value",
    "floors",
    "households",
    "module_count",
    "gross_floor_area",
    "contract_amount",
    "participation_count",
    "award_count",
    "award_rate",
    "school_participation_count",
    "housing_participation_count",
    "rental_participation_count",
    "average_bid_amount",
    "average_award_amount",
    "average_award_unit_price",
    "revenue",
    "gross_profit",
    "operating_profit",
    "net_income",
    "operating_cash_flow",
    "total_assets",
    "total_liabilities",
    "debt_ratio",
    "modular_segment_revenue",
}
PROJECT_STATUSES = {
    "planned",
    "proposed",
    "bid",
    "awarded",
    "contracted",
    "under_construction",
    "completed",
    "suspended",
    "cancelled",
    "unconfirmed",
    "unknown",
}
COMPANY_ROLES = {
    "modular_manufacturer",
    "specialist_contractor",
    "engineering",
    "supplier",
    "developer",
    "designer",
    "manufacturer",
    "general_contractor",
    "installer",
    "structural_supplier",
    "rental_provider",
    "consortium_member",
    "technology_provider",
    "modular_integrator",
    "unknown",
}
TECH_RECORD_TYPES = {
    "patent",
    "patent_application",
    "construction_new_technology",
    "certification",
    "innovative_product",
    "design_award",
    "research_project",
    "proprietary_system",
    "structural_performance_certification",
}
TECH_STATUSES = {"registered", "applied", "expired", "claimed", "active", "unknown"}
FINANCIAL_SCOPES = {"consolidated", "separate", "company_total", "modular_segment", "unknown"}
REVIEW_STATUSES = {"unresearched", "collecting", "partially_verified", "verified", "update_required"}


def load_companies(path: Path = DEFAULT_INPUT) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("companies", [])


def wave1_companies(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {row["company_id"]: row for row in rows}
    return [by_id[company_id] for company_id in WAVE1_IDS if company_id in by_id]


def source_ids(company: dict[str, Any]) -> set[str]:
    return {str(source.get("source_id")) for source in company.get("sources", []) if source.get("source_id")}


def add_issue(issues: list[dict[str, Any]], code: str, company_id: str, path: str, message: str, severity: str = "error") -> None:
    issues.append({"code": code, "company_id": company_id, "path": path, "message": message, "severity": severity})


def has_source_ids(record: dict[str, Any]) -> bool:
    values = record.get("source_ids")
    return isinstance(values, list) and any(values)


def validate_record_sources(company: dict[str, Any], record: dict[str, Any], path: str, issues: list[dict[str, Any]]) -> None:
    known = source_ids(company)
    if not has_source_ids(record):
        add_issue(issues, "fact_without_source", company["company_id"], path, "record requires source_ids")
        return
    for source_id in record.get("source_ids", []):
        if source_id not in known:
            add_issue(issues, "unknown_source_reference", company["company_id"], path, f"unknown source_id={source_id}")


def validate_sources(company: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    seen_urls: dict[str, str] = {}
    for index, source in enumerate(company.get("sources", []) or []):
        path = f"sources[{index}]"
        if not source.get("source_id"):
            add_issue(issues, "missing_source_id", company["company_id"], path, "source_id is required")
        if source.get("source_type") == "manual_verified_research":
            pass
        elif not source.get("source_url"):
            add_issue(issues, "missing_source_url", company["company_id"], path, "source_url is required")
        else:
            url = str(source["source_url"]).strip().lower()
            if url in seen_urls:
                add_issue(issues, "duplicate_source_url", company["company_id"], path, f"duplicate URL with {seen_urls[url]}")
            seen_urls[url] = str(source.get("source_id"))
        if source.get("accessed_at"):
            validate_not_future(company["company_id"], path + ".accessed_at", source["accessed_at"], issues)
        else:
            add_issue(issues, "missing_accessed_at", company["company_id"], path, "source accessed_at is required")


def validate_not_future(company_id: str, path: str, value: Any, issues: list[dict[str, Any]]) -> None:
    if not value:
        return
    raw = str(value)
    try:
        if re.fullmatch(r"\d{4}", raw):
            parsed = date(int(raw), 1, 1)
        elif re.fullmatch(r"\d{4}-\d{2}", raw):
            year, month = [int(part) for part in raw.split("-")]
            parsed = date(year, month, 1)
        else:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            parsed = date.fromisoformat(raw[:10])
        except ValueError:
            add_issue(issues, "invalid_date", company_id, path, str(value))
            return
    if parsed > date.today():
        add_issue(issues, "future_date", company_id, path, str(value))


def validate_profile_sources(company: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    field_sources = company.get("field_sources", {}) or {}
    known = source_ids(company)
    if any(source.get("source_type") == "manual_verified_research" for source in company.get("sources", []) or []):
        return
    for field in PROFILE_FIELDS_REQUIRING_SOURCES:
        value = company.get(field)
        if value is None or value == "" or value == []:
            continue
        linked = field_sources.get(field)
        if not linked:
            add_issue(issues, "fact_without_source", company["company_id"], field, "profile field requires field_sources")
            continue
        for source_id in linked:
            if source_id not in known:
                add_issue(issues, "unknown_source_reference", company["company_id"], field, f"unknown source_id={source_id}")


def validate_numbers(company: dict[str, Any], record: dict[str, Any], path: str, issues: list[dict[str, Any]]) -> None:
    for field, value in record.items():
        if isinstance(value, dict):
            validate_numbers(company, value, f"{path}.{field}", issues)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    validate_numbers(company, item, f"{path}.{field}[{index}]", issues)
        elif field in NUMBER_FIELDS and value is not None and not has_source_ids(record):
            add_issue(issues, "number_without_source", company["company_id"], f"{path}.{field}", "numeric value requires source_ids")


def validate_company(company: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    validate_sources(company, issues)
    validate_profile_sources(company, issues)
    if company.get("review_status") not in REVIEW_STATUSES:
        add_issue(issues, "invalid_enum", company["company_id"], "review_status", str(company.get("review_status")))

    for index, facility in enumerate(company.get("production", []) or []):
        path = f"production[{index}]"
        validate_record_sources(company, facility, path, issues)
        if facility.get("capacity_value") is not None and not facility.get("capacity_unit"):
            add_issue(issues, "production_capacity_without_unit", company["company_id"], path + ".capacity_unit", "capacity unit required")
        validate_numbers(company, facility, path, issues)

    for index, project in enumerate(company.get("project_portfolio", []) or []):
        path = f"project_portfolio[{index}]"
        validate_record_sources(company, project, path, issues)
        if project.get("project_status") not in PROJECT_STATUSES:
            add_issue(issues, "project_status_missing_or_invalid", company["company_id"], path + ".project_status", str(project.get("project_status")))
        if project.get("company_role") not in COMPANY_ROLES:
            add_issue(issues, "project_role_missing_or_invalid", company["company_id"], path + ".company_role", str(project.get("company_role")))
        validate_numbers(company, project, path, issues)

    for index, bid in enumerate(company.get("bidding_performance", []) or []):
        path = f"bidding_performance[{index}]"
        validate_record_sources(company, bid, path, issues)
        validate_numbers(company, bid, path, issues)

    technology_records = []
    technology = company.get("technology", {}) or {}
    for key, value in technology.items():
        if isinstance(value, list):
            technology_records.extend((key, item) for item in value if isinstance(item, dict))
    for index, (collection, tech) in enumerate(technology_records):
        path = f"technology.{collection}[{index}]"
        validate_record_sources(company, tech, path, issues)
        if tech.get("record_type") not in TECH_RECORD_TYPES:
            add_issue(issues, "invalid_enum", company["company_id"], path + ".record_type", str(tech.get("record_type")))
        if tech.get("status") not in TECH_STATUSES:
            add_issue(issues, "technology_status_missing_or_invalid", company["company_id"], path + ".status", str(tech.get("status")))

    for index, financial in enumerate(company.get("financials", []) or []):
        path = f"financials[{index}]"
        validate_record_sources(company, financial, path, issues)
        if financial.get("reporting_scope") not in FINANCIAL_SCOPES:
            add_issue(issues, "financial_reporting_scope_missing", company["company_id"], path + ".reporting_scope", str(financial.get("reporting_scope")))
        validate_numbers(company, financial, path, issues)

    for index, signal in enumerate(company.get("recent_signals", []) or []):
        path = f"recent_signals[{index}]"
        validate_record_sources(company, signal, path, issues)
        validate_not_future(company["company_id"], path + ".occurred_at", signal.get("occurred_at"), issues)

    if company.get("review_status") == "verified" and issues:
        add_issue(issues, "review_status_contract_violation", company["company_id"], "review_status", "verified company must have no validation issues")
    return issues


def validate_research(path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    rows = wave1_companies(load_companies(path))
    issues = [issue for company in rows for issue in validate_company(company)]
    by_company = {company["company_id"]: validate_company(company) for company in rows}
    return {
        "valid": not any(issue["severity"] == "error" for issue in issues),
        "wave_1_company_count": len(rows),
        "issues": issues,
        "issue_counts": {
            "fact_without_source": sum(1 for issue in issues if issue["code"] == "fact_without_source"),
            "number_without_source": sum(1 for issue in issues if issue["code"] == "number_without_source"),
            "production_capacity_without_unit": sum(1 for issue in issues if issue["code"] == "production_capacity_without_unit"),
            "project_role_missing": sum(1 for issue in issues if issue["code"] == "project_role_missing_or_invalid"),
            "project_status_missing": sum(1 for issue in issues if issue["code"] == "project_status_missing_or_invalid"),
            "financial_reporting_scope_missing": sum(1 for issue in issues if issue["code"] == "financial_reporting_scope_missing"),
            "technology_status_missing": sum(1 for issue in issues if issue["code"] == "technology_status_missing_or_invalid"),
            "duplicate_source_url": sum(1 for issue in issues if issue["code"] == "duplicate_source_url"),
            "future_date": sum(1 for issue in issues if issue["code"] == "future_date"),
            "invalid_enum": sum(1 for issue in issues if issue["code"] == "invalid_enum"),
            "review_status_contract_violation": sum(1 for issue in issues if issue["code"] == "review_status_contract_violation"),
        },
        "issues_by_company": {company_id: len(company_issues) for company_id, company_issues in by_company.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Wave 1 company research quality.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    result = validate_research(args.input)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
