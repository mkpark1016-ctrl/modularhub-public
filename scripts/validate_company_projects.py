#!/usr/bin/env python3
"""Validate source-backed company project portfolio records."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"

DIRECT_COMPETITOR = "direct_competitor"
TIER_1_VALUES = {"tier_1"}
CONFIRMED_PROJECT_STATUSES = {"contracted", "under_construction", "completed"}
PROJECT_STATUSES = {
    "planned",
    "bidding",
    "bid",
    "awarded",
    "contracted",
    "under_construction",
    "completed",
    "suspended",
    "cancelled",
    "unknown",
}
COMPANY_ROLES = {
    "modular_manufacturer",
    "general_contractor",
    "specialist_contractor",
    "designer",
    "engineering",
    "supplier",
    "installer",
    "developer",
    "consortium_member",
    "manufacturer",
    "structural_supplier",
    "rental_provider",
    "technology_provider",
    "unknown",
}
STRUCTURE_TYPES = {
    "steel_modular",
    "steel_volumetric",
    "steel_frame_panelized",
    "precast_concrete_modular",
    "precast_concrete",
    "timber_modular",
    "container",
    "hybrid",
    "unknown",
}
EVIDENCE_STATUSES = {"verified", "partially_verified", "claimed", "unresolved"}
NUMBER_FIELDS = {
    "contract_amount",
    "floor_count",
    "floors",
    "building_count",
    "unit_count",
    "room_count",
    "households",
    "module_count",
    "gross_floor_area",
}
UNIT_FIELDS = {
    "contract_amount": "contract_amount_unit",
    "gross_floor_area": "gross_floor_area_unit",
}


def load_payload(path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_companies(path: Path = DEFAULT_INPUT) -> list[dict[str, Any]]:
    return load_payload(path).get("companies", [])


def source_id_set(company: dict[str, Any]) -> set[str]:
    return {str(source.get("source_id")) for source in company.get("sources", []) or [] if source.get("source_id")}


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def project_key(project: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        normalize_text(project.get("project_name")),
        normalize_text(project.get("client_name") or project.get("client") or project.get("ordering_agency")),
        normalize_text(project.get("location")),
        normalize_text(project.get("contract_date") or project.get("completion_date")),
    )


def add_issue(
    issues: list[dict[str, Any]],
    code: str,
    company_id: str,
    path: str,
    message: str,
    severity: str = "error",
) -> None:
    issues.append(
        {
            "code": code,
            "company_id": company_id,
            "path": path,
            "message": message,
            "severity": severity,
        }
    )


def has_source_ids(project: dict[str, Any]) -> bool:
    return isinstance(project.get("source_ids"), list) and any(project.get("source_ids"))


def validate_date(value: Any) -> bool:
    if not value:
        return True
    try:
        parsed = date.fromisoformat(str(value)[:10])
    except ValueError:
        return False
    return parsed <= date.today()


def validate_project(
    company: dict[str, Any],
    project: dict[str, Any],
    index: int,
    known_sources: set[str],
    issues: list[dict[str, Any]],
) -> None:
    company_id = company.get("company_id", "unknown")
    path = f"project_portfolio[{index}]"
    if not project.get("project_id"):
        add_issue(issues, "missing_project_id", company_id, path, "project_id is required")
    if not project.get("project_name"):
        add_issue(issues, "missing_project_name", company_id, path, "project_name is required")
    if not has_source_ids(project):
        add_issue(issues, "project_without_source", company_id, path, "project requires source_ids")
    else:
        for source_id in project.get("source_ids", []):
            if str(source_id) not in known_sources:
                add_issue(issues, "unknown_project_source", company_id, path, f"unknown source_id={source_id}")

    status = project.get("project_status")
    if status not in PROJECT_STATUSES:
        add_issue(issues, "invalid_project_status", company_id, path + ".project_status", str(status))
    role = project.get("company_role")
    if role not in COMPANY_ROLES:
        add_issue(issues, "invalid_company_role", company_id, path + ".company_role", str(role))

    evidence_status = project.get("evidence_status")
    if evidence_status is not None and evidence_status not in EVIDENCE_STATUSES:
        add_issue(issues, "invalid_evidence_status", company_id, path + ".evidence_status", str(evidence_status))
    if evidence_status == "verified" and role == "unknown":
        add_issue(issues, "verified_project_role_unknown", company_id, path + ".company_role", "verified project needs an explicit company role")

    structure_type = project.get("structure_type") or project.get("modular_method") or project.get("modular_type")
    if structure_type and structure_type not in STRUCTURE_TYPES:
        add_issue(issues, "invalid_structure_type", company_id, path + ".structure_type", str(structure_type))

    for field in ("contract_date", "construction_start_date", "completion_date", "verified_at"):
        if not validate_date(project.get(field)):
            add_issue(issues, "invalid_or_future_date", company_id, path + f".{field}", str(project.get(field)))

    for field in NUMBER_FIELDS:
        value = project.get(field)
        if value is None:
            continue
        if not isinstance(value, (int, float)):
            add_issue(issues, "non_numeric_project_value", company_id, path + f".{field}", str(value))
        if not has_source_ids(project):
            add_issue(issues, "project_number_without_source", company_id, path + f".{field}", "numeric project value requires source_ids")
        unit_field = UNIT_FIELDS.get(field)
        if unit_field and not project.get(unit_field):
            add_issue(issues, "project_number_unit_missing", company_id, path + f".{unit_field}", f"{field} requires {unit_field}")

    if project.get("evidence_type") == "mou" and project.get("project_status") == "completed":
        add_issue(issues, "mou_marked_completed", company_id, path, "MOU must not be classified as completed project")
    if company.get("dart_identity", {}).get("identity_status") == "manual_review_required" and evidence_status == "verified":
        add_issue(issues, "manual_review_company_verified_project", company_id, path, "manual-review company cannot have verified project linkage")


def validate_company_projects(path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    companies = load_companies(path)
    issues: list[dict[str, Any]] = []
    project_ids: dict[str, str] = {}
    duplicate_keys: dict[tuple[str, str, str, str], str] = {}
    direct_competitors = [c for c in companies if c.get("competitive_role") == DIRECT_COMPETITOR]

    for company in companies:
        known_sources = source_id_set(company)
        for index, project in enumerate(company.get("project_portfolio", []) or []):
            validate_project(company, project, index, known_sources, issues)
            project_id = project.get("project_id")
            if project_id:
                if project_id in project_ids:
                    add_issue(issues, "duplicate_project_id", company.get("company_id", "unknown"), f"project_portfolio[{index}].project_id", f"duplicate with {project_ids[project_id]}")
                project_ids[str(project_id)] = str(company.get("company_id"))
            key = project_key(project)
            if key[0] and key in duplicate_keys:
                add_issue(issues, "duplicate_project_candidate", company.get("company_id", "unknown"), f"project_portfolio[{index}]", f"possible duplicate with {duplicate_keys[key]}", severity="warning")
            elif key[0]:
                duplicate_keys[key] = str(project_id or company.get("company_id"))

    return {
        "valid": not any(issue["severity"] == "error" for issue in issues),
        "company_count": len(companies),
        "direct_competitor_count": len(direct_competitors),
        "project_count": sum(len(c.get("project_portfolio", []) or []) for c in companies),
        "issues": issues,
        "issue_counts": {
            "duplicate_project_id": sum(1 for issue in issues if issue["code"] == "duplicate_project_id"),
            "project_without_source": sum(1 for issue in issues if issue["code"] == "project_without_source"),
            "project_number_without_source": sum(1 for issue in issues if issue["code"] == "project_number_without_source"),
            "project_number_unit_missing": sum(1 for issue in issues if issue["code"] == "project_number_unit_missing"),
            "invalid_company_role": sum(1 for issue in issues if issue["code"] == "invalid_company_role"),
            "invalid_project_status": sum(1 for issue in issues if issue["code"] == "invalid_project_status"),
            "manual_review_company_verified_project": sum(1 for issue in issues if issue["code"] == "manual_review_company_verified_project"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate company project portfolio records.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    result = validate_company_projects(args.input)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
