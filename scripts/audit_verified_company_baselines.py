#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from company_publication import load_public_company_ids  # noqa: E402
from verified_company_source import load_verified_companies  # noqa: E402

V1_PATH = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"
V2_PATH = ROOT / "frontend" / "public" / "data" / "companies" / "company_intelligence_v2.json"
APP_PATH = ROOT / "frontend" / "src" / "App.jsx"
COMPANY_COMPONENT_ROOT = ROOT / "frontend" / "src" / "components" / "company"
BUSINESS_PATH = ROOT / "frontend" / "public" / "data" / "business.json"
NEWS_PATH = ROOT / "frontend" / "public" / "data" / "news.json"
META_PATH = ROOT / "frontend" / "public" / "data" / "meta.json"
REPORT_MD = ROOT / "reports" / "company_verified_baseline_audit.md"
REPORT_JSON = ROOT / "reports" / "company_verified_baseline_audit.json"

ISSUE_GENERATION = "GENERATION_MISSING"
ISSUE_V2 = "V2_MAPPING_MISSING"
ISSUE_UI = "UI_NOT_RENDERED"
ISSUE_TRUNCATED = "UI_TRUNCATED"
ISSUE_STATUS = "STATUS_CLASSIFICATION_ERROR"
ISSUE_ORPHAN = "ORPHAN_REFERENCE"
ISSUE_UNIT = "UNIT_ERROR"
ISSUE_SOURCE = "SOURCE_MISSING"

PROJECT_CREDIT_V1_ALLOWED = {"completed", "under_construction", "contracted", "awarded"}
PROJECT_CREDIT_V2_ALLOWED = {"completed", "in_progress", "contract_signed", "award_confirmed"}
PROJECT_CREDIT_FALSE_STATUSES = {
    "preferred_bidder",
    "planned",
    "unconfirmed",
    "cancelled",
    "mou_signed",
    "partnership_discussion",
    "r_and_d",
    "exhibition",
    "pre_con",
    "not_signed",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def technology_records(company: dict[str, Any]) -> list[dict[str, Any]]:
    technology = company.get("technology") if isinstance(company.get("technology"), dict) else {}
    records: list[dict[str, Any]] = []
    for values in technology.values():
        if isinstance(values, list):
            records.extend(item for item in values if isinstance(item, dict))
    return records


def metric_value(metric: Any) -> Any:
    return metric.get("source_value") if isinstance(metric, dict) else None


def add_issue(issues: list[dict[str, Any]], company_id: str, code: str, field: str, detail: str, severity: str = "warning") -> None:
    issues.append(
        {
            "company_id": company_id,
            "code": code,
            "field": field,
            "detail": detail,
            "severity": severity,
        }
    )


def count_v2_facts(v2: dict[str, Any], company_id: str, domain: str | None = None, field: str | None = None) -> int:
    facts = [item for item in v2.get("facts", []) if item.get("company_id") == company_id]
    if domain is not None:
        facts = [item for item in facts if item.get("domain") == domain]
    if field is not None:
        facts = [item for item in facts if item.get("field") == field]
    return len(facts)


def count_v2_events(v2: dict[str, Any], company_id: str, event_type: str | None = None) -> int:
    events = [item for item in v2.get("events", []) if item.get("company_id") == company_id]
    if event_type is not None:
        events = [item for item in events if item.get("event_type") == event_type]
    return len(events)


def ui_source_text() -> str:
    paths = [APP_PATH]
    if COMPANY_COMPONENT_ROOT.exists():
        paths.extend(sorted(path for path in COMPANY_COMPONENT_ROOT.rglob("*") if path.suffix in {".js", ".jsx"}))
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def ui_capabilities() -> dict[str, Any]:
    text = ui_source_text()
    return {
        "technology_slice_limit": 8 if ".slice(0, 8)" in text and "technologyItems" in text else None,
        "renders_gross_profit": "gross_profit" in text,
        "renders_established_at": "established_at" in text,
        "renders_representative": "representative" in text,
        "renders_employee_count": "employee_count" in text,
        "renders_major_businesses": "major_businesses" in text,
    }


def source_ids_from_public_json(company: dict[str, Any]) -> set[str]:
    source_ids: set[str] = set()
    for source in company.get("sources", []) or []:
        if source.get("source_id"):
            source_ids.add(source["source_id"])
    for collection in ("financials", "production", "project_portfolio", "recent_signals"):
        for item in company.get(collection, []) or []:
            source_ids.update(str(value) for value in item.get("source_ids", []) or [])
    for record in technology_records(company):
        source_ids.update(str(value) for value in record.get("source_ids", []) or [])
    return source_ids


def audit() -> dict[str, Any]:
    allowed_ids = load_public_company_ids()
    allowed_set = set(allowed_ids)
    sources = load_verified_companies()
    source_by_id = {item["company_id"]: item for item in sources}
    v1 = load_json(V1_PATH)
    v2 = load_json(V2_PATH)
    ui = ui_capabilities()

    issues: list[dict[str, Any]] = []
    company_rows: list[dict[str, Any]] = []

    v1_companies = {item["company_id"]: item for item in v1.get("companies", [])}
    v2_companies = {item["company_id"]: item for item in v2.get("companies", [])}
    v2_evidence_ids = {item.get("source_id") for item in v2.get("evidence", [])}
    v2_record_ids = {item.get("fact_id") for item in v2.get("facts", [])} | {item.get("event_id") for item in v2.get("events", [])}

    if set(source_by_id) != allowed_set:
        add_issue(issues, "", ISSUE_SOURCE, "allowlist", "Allowlist and verified source modules differ", "critical")
    if set(v1_companies) != allowed_set:
        add_issue(issues, "", ISSUE_ORPHAN, "companies.json", f"Public V1 ids differ from allowlist: {sorted(set(v1_companies) ^ allowed_set)}", "critical")
    if set(v2_companies) != allowed_set:
        add_issue(issues, "", ISSUE_ORPHAN, "company_intelligence_v2.json", f"Public V2 ids differ from allowlist: {sorted(set(v2_companies) ^ allowed_set)}", "critical")

    for source in sources:
        company_id = source["company_id"]
        company = v1_companies.get(company_id, {})
        source_profile = source["company"]
        source_technology_count = len(source.get("technology", []))
        v1_technology_count = len(technology_records(company))
        v2_technology_count = count_v2_facts(v2, company_id, "technology")
        source_project_count = len(source.get("projects", []))
        v1_project_count = len(company.get("project_portfolio", []) or [])
        v2_project_count = count_v2_events(v2, company_id, "project")
        source_facility_count = len(source.get("production", []))
        v1_facility_count = len(company.get("production", []) or [])
        v2_production_count = count_v2_facts(v2, company_id, "production")
        source_financial_years = sorted([item["year"] for item in source.get("financials", [])], reverse=True)
        v1_financial_years = sorted([item.get("year") for item in company.get("financials", []) or []], reverse=True)

        missing_fields: list[str] = []
        hidden_fields: list[str] = []
        classification_errors: list[str] = []

        for source_field, v1_path in (
            ("established_at", ("company_profile", "established_at")),
            ("representative", ("company_profile", "representative")),
            ("employee_count_research_value", ("company_profile", "employee_count")),
            ("major_businesses", ("company_profile", "major_businesses")),
            ("headquarters", ("headquarters",)),
        ):
            source_value = source_profile.get(source_field)
            target: Any = company
            for part in v1_path:
                target = target.get(part) if isinstance(target, dict) else None
            if source_value not in (None, [], {}) and target in (None, [], {}):
                missing_fields.append(".".join(v1_path))
                add_issue(issues, company_id, ISSUE_GENERATION, ".".join(v1_path), f"Source field {source_field} is not present in companies.json", "critical")

        for ui_field, capability_key in (
            ("established_at", "renders_established_at"),
            ("representative", "renders_representative"),
            ("employee_count", "renders_employee_count"),
            ("major_businesses", "renders_major_businesses"),
        ):
            if company.get("company_profile", {}).get(ui_field) not in (None, [], {}) and not ui[capability_key]:
                hidden_fields.append(ui_field)
                add_issue(issues, company_id, ISSUE_UI, ui_field, "Field exists in companies.json but App.jsx does not render it", "warning")

        if source_financial_years != v1_financial_years:
            add_issue(issues, company_id, ISSUE_GENERATION, "financials.year", f"Source years {source_financial_years} != V1 years {v1_financial_years}", "critical")
        for financial in company.get("financials", []) or []:
            if metric_value(financial.get("gross_profit")) is not None and not ui["renders_gross_profit"]:
                hidden_fields.append(f"gross_profit:{financial.get('year')}")
                add_issue(issues, company_id, ISSUE_UI, "financials.gross_profit", f"Gross profit for {financial.get('year')} exists but is not rendered", "warning")
            for field in ("revenue", "gross_profit", "operating_profit", "modular_segment_revenue"):
                metric = financial.get(field)
                if isinstance(metric, dict) and not metric.get("source_ids"):
                    add_issue(issues, company_id, ISSUE_ORPHAN, f"financials.{field}.source_ids", "Financial metric lacks source_ids", "critical")

        for label, source_count, v1_count, v2_count, code in (
            ("production", source_facility_count, v1_facility_count, v2_production_count, ISSUE_GENERATION),
            ("projects", source_project_count, v1_project_count, v2_project_count, ISSUE_GENERATION),
            ("technology", source_technology_count, v1_technology_count, v2_technology_count, ISSUE_V2),
        ):
            if source_count != v1_count:
                add_issue(issues, company_id, code, label, f"Source count {source_count} != V1 count {v1_count}", "critical")
            if source_count != v2_count and label != "production":
                add_issue(issues, company_id, ISSUE_V2, label, f"Source count {source_count} != V2 count {v2_count}", "critical")

        if ui["technology_slice_limit"] is not None and v1_technology_count > ui["technology_slice_limit"]:
            hidden = v1_technology_count - ui["technology_slice_limit"]
            hidden_fields.append(f"technology:{hidden}")
            add_issue(issues, company_id, ISSUE_TRUNCATED, "technology", f"{hidden} technology records are hidden by slice(0, 8)", "warning")

        for project in company.get("project_portfolio", []) or []:
            status = project.get("project_status")
            credit = bool(project.get("project_credit"))
            if credit and status not in PROJECT_CREDIT_V1_ALLOWED:
                classification_errors.append(project.get("project_id") or project.get("project_name") or "unknown")
                add_issue(issues, company_id, ISSUE_STATUS, "project_portfolio.project_credit", f"{status} cannot receive project credit", "critical")
            if status in PROJECT_CREDIT_FALSE_STATUSES and credit:
                add_issue(issues, company_id, ISSUE_STATUS, "project_portfolio.project_credit", f"{status} must remain project_credit=false", "critical")
            if project.get("contract_amount") is not None and not project.get("contract_amount_unit"):
                add_issue(issues, company_id, ISSUE_UNIT, "project_portfolio.contract_amount_unit", "Contract amount requires a unit", "critical")

        for event in [item for item in v2.get("events", []) if item.get("company_id") == company_id]:
            if event.get("project_credit") and event.get("event_status") not in PROJECT_CREDIT_V2_ALLOWED:
                add_issue(issues, company_id, ISSUE_STATUS, "events.project_credit", f"{event.get('event_status')} cannot receive project credit", "critical")
            if event.get("event_status") in PROJECT_CREDIT_FALSE_STATUSES and event.get("project_credit"):
                add_issue(issues, company_id, ISSUE_STATUS, "events.project_credit", f"{event.get('event_status')} must remain project_credit=false", "critical")

        for facility in company.get("production", []) or []:
            if facility.get("capacity_value") is not None or facility.get("reported_capacity") is not None:
                if not facility.get("capacity_unit") or not facility.get("capacity_basis"):
                    add_issue(issues, company_id, ISSUE_UNIT, "production.capacity", "Capacity requires unit and basis", "critical")
            if not facility.get("source_ids"):
                add_issue(issues, company_id, ISSUE_ORPHAN, "production.source_ids", "Production facility lacks source_ids", "critical")

        for source_id in source_ids_from_public_json(company):
            if source_id not in v2_evidence_ids:
                add_issue(issues, company_id, ISSUE_ORPHAN, "source_id", f"{source_id} is used in V1 but missing from V2 evidence", "critical")

        company_rows.append(
            {
                "company_id": company_id,
                "company_name": source_profile.get("company_name"),
                "source": {
                    "financial_years": source_financial_years,
                    "facility_count": source_facility_count,
                    "project_count": source_project_count,
                    "technology_count": source_technology_count,
                    "strategy_event_count": len(source.get("strategy_events", [])),
                },
                "companies_json": {
                    "financial_years": v1_financial_years,
                    "facility_count": v1_facility_count,
                    "project_count": v1_project_count,
                    "technology_count": v1_technology_count,
                },
                "company_intelligence_v2": {
                    "financial_fact_count": count_v2_facts(v2, company_id, "financial"),
                    "production_fact_count": v2_production_count,
                    "project_event_count": v2_project_count,
                    "technology_fact_count": v2_technology_count,
                },
                "ui": {
                    "technology_display_count": min(v1_technology_count, ui["technology_slice_limit"] or v1_technology_count),
                    "technology_hidden_count": max(0, v1_technology_count - (ui["technology_slice_limit"] or v1_technology_count)),
                    "gross_profit_rendered": ui["renders_gross_profit"],
                },
                "missing_fields": missing_fields,
                "hidden_fields": hidden_fields,
                "classification_errors": classification_errors,
                "severity": "critical"
                if any(issue["company_id"] == company_id and issue["severity"] == "critical" for issue in issues)
                else ("warning" if hidden_fields else "ok"),
            }
        )

    duplicate_checks = {
        "company_id_duplicates": len(v1.get("companies", [])) - len({item.get("company_id") for item in v1.get("companies", [])}),
        "fact_id_duplicates": len(v2.get("facts", [])) - len({item.get("fact_id") for item in v2.get("facts", [])}),
        "event_id_duplicates": len(v2.get("events", [])) - len({item.get("event_id") for item in v2.get("events", [])}),
        "evidence_id_duplicates": len(v2.get("evidence", [])) - len({item.get("source_id") for item in v2.get("evidence", [])}),
    }
    for key, count in duplicate_checks.items():
        if count:
            add_issue(issues, "", ISSUE_ORPHAN, key, f"Duplicate count={count}", "critical")

    for source in v2.get("evidence", []) or []:
        for target in source.get("supports", []) + source.get("contradicts", []):
            if target not in v2_record_ids:
                add_issue(issues, "", ISSUE_ORPHAN, "evidence.supports", f"{source.get('source_id')} references missing {target}", "critical")

    new_pdf_files = [str(path.relative_to(ROOT)) for path in ROOT.rglob("*.pdf") if ".git" not in path.parts]
    if new_pdf_files:
        add_issue(issues, "", ISSUE_SOURCE, "pdf", f"PDF files are present in repository: {new_pdf_files}", "critical")

    issue_counts = Counter(issue["code"] for issue in issues)
    severity_counts = Counter(issue["severity"] for issue in issues)
    result = {
        "valid": severity_counts.get("critical", 0) == 0,
        "generated_at": "2026-07-17",
        "public_company_count": len(v1.get("companies", [])),
        "allowlist_company_count": len(allowed_ids),
        "v1_company_ids": [item.get("company_id") for item in v1.get("companies", [])],
        "v2_company_ids": [item.get("company_id") for item in v2.get("companies", [])],
        "source_company_ids": [item.get("company_id") for item in sources],
        "protected_hashes": {
            "business_json": sha256(BUSINESS_PATH),
            "news_json": sha256(NEWS_PATH),
            "meta_json": sha256(META_PATH),
        },
        "ui_capabilities": ui,
        "duplicate_checks": duplicate_checks,
        "issue_counts": dict(issue_counts),
        "severity_counts": dict(severity_counts),
        "companies": company_rows,
        "issues": issues,
        "recommendations": [
            "Remove the technology detail slice limit or add pagination so all source technology records are reachable.",
            "Add profile rows for establishment date, representative, employee count, and major businesses.",
            "Add gross profit and margin display to the three-year financial table while keeping original KRW values unchanged.",
        ],
    }
    return result


def write_reports(result: dict[str, Any]) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Company Verified Baseline Audit",
        "",
        f"- Valid: `{result['valid']}`",
        f"- Public companies: {result['public_company_count']} / allowlist {result['allowlist_company_count']}",
        f"- V1 ids: {', '.join(result['v1_company_ids'])}",
        f"- V2 ids: {', '.join(result['v2_company_ids'])}",
        f"- Critical issues: {result['severity_counts'].get('critical', 0)}",
        f"- Warnings: {result['severity_counts'].get('warning', 0)}",
        "",
        "## Issue Counts",
        "",
    ]
    for code, count in sorted(result["issue_counts"].items()):
        lines.append(f"- {code}: {count}")
    lines.extend(
        [
            "",
            "## Company Summary",
            "",
            "| company_id | name | source projects | V1 projects | V2 project events | source tech | V1 tech | UI hidden | severity |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in result["companies"]:
        lines.append(
            "| {company_id} | {company_name} | {sp} | {vp} | {v2p} | {st} | {vt} | {hidden} | {severity} |".format(
                company_id=row["company_id"],
                company_name=row["company_name"],
                sp=row["source"]["project_count"],
                vp=row["companies_json"]["project_count"],
                v2p=row["company_intelligence_v2"]["project_event_count"],
                st=row["source"]["technology_count"],
                vt=row["companies_json"]["technology_count"],
                hidden=row["ui"]["technology_hidden_count"],
                severity=row["severity"],
            )
        )
    lines.extend(["", "## Findings", ""])
    if result["issues"]:
        for issue in result["issues"]:
            lines.append(f"- `{issue['severity']}` `{issue['code']}` {issue['company_id']} {issue['field']}: {issue['detail']}")
    else:
        lines.append("- No issues found.")
    lines.extend(["", "## Recommendations", ""])
    for item in result["recommendations"]:
        lines.append(f"- {item}")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    result = audit()
    write_reports(result)
    print(json.dumps({
        "valid": result["valid"],
        "public_company_count": result["public_company_count"],
        "issue_counts": result["issue_counts"],
        "severity_counts": result["severity_counts"],
        "report_json": str(REPORT_JSON.relative_to(ROOT)),
        "report_md": str(REPORT_MD.relative_to(ROOT)),
    }, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
