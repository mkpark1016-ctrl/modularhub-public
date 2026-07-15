#!/usr/bin/env python3
"""Regression tests for company project portfolio contracts."""

from __future__ import annotations

from audit_company_projects import project_coverage, select_wave_targets
from validate_company_projects import load_companies, validate_company_projects


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def by_id(rows: list[dict], company_id: str) -> dict:
    for row in rows:
        if row.get("company_id") == company_id:
            return row
    raise AssertionError(f"missing company_id={company_id}")


def main() -> int:
    companies = load_companies()
    direct = [company for company in companies if company.get("competitive_role") == "direct_competitor"]
    require(len(direct) == 8, "direct competitor count must remain 8")

    targets = select_wave_targets(companies)
    require(1 <= len(targets) <= 4, "Wave 1 target selection must return at most 4 direct competitors")
    require(all(company.get("competitive_role") == "direct_competitor" for company in targets), "targets must be direct competitors")
    require(all(company.get("company_id") != "gs-ec" for company in targets), "internal baseline must not be selected")

    kumkang = by_id(companies, "kumkang-kind")
    projects = kumkang.get("project_portfolio") or []
    require(len(projects) == 3, "Kumkang should keep 3 official project records")
    require(all(project.get("source_ids") for project in projects), "Kumkang projects require source_ids")
    require(all(project.get("company_role") != "unknown" for project in projects), "Kumkang project roles should be explicit")
    require(all(project.get("structure_type") in {"steel_modular", "steel_volumetric"} for project in projects), "Kumkang projects must be steel modular")
    require(any("Goryeong" in " ".join(project.get("aliases", [])) or "고령군" in project.get("project_name", "") for project in projects), "Goryeong modular project should remain searchable")

    ids = [project.get("project_id") for company in companies for project in (company.get("project_portfolio") or [])]
    require(len(ids) == len(set(ids)), "project_id values must be unique")
    require(all(project.get("contract_amount") is not None or project.get("contract_amount") is None for company in companies for project in (company.get("project_portfolio") or [])), "null project amounts must stay null, not zero-filled")

    validation = validate_company_projects()
    require(validation["valid"], f"project validation failed: {validation['issues'][:3]}")
    require(validation["issue_counts"]["project_number_without_source"] == 0, "project numeric values without source must be 0")
    require(validation["issue_counts"]["duplicate_project_id"] == 0, "duplicate project_id count must be 0")
    require(validation["issue_counts"]["manual_review_company_verified_project"] == 0, "manual review companies must not have verified projects")

    coverage = {company["company_id"]: project_coverage(company) for company in direct}
    require(coverage["kumkang-kind"]["source_backed_project_count"] == 3, "Kumkang source-backed project count should be 3")
    require(coverage["jinwoo-inc"]["project_count"] == 0, "Jinwoo must not receive unresolved project linkage")

    print("COMPANY PROJECT TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
