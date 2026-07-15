#!/usr/bin/env python3
"""Audit direct competitor project portfolio coverage and generate artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_company_projects import DEFAULT_INPUT, validate_company_projects

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_DIR = ROOT / "artifacts" / "company-project-portfolio-wave-1"
DIRECT_COMPETITOR = "direct_competitor"
PRIMARY_SOURCE_TYPES = {
    "official_website",
    "official_press_release",
    "regulatory_filing",
    "procurement_notice",
    "government_release",
    "public_agency_release",
    "certification_record",
}
VERIFIED_STATUSES = {"verified", "partially_verified"}
ROLE_CLEAR_VALUES = {
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
}
SCALE_FIELDS = (
    "contract_amount",
    "floor_count",
    "floors",
    "building_count",
    "unit_count",
    "room_count",
    "households",
    "module_count",
    "gross_floor_area",
)
RECENT_YEAR_CUTOFF = datetime.now(timezone.utc).year - 5


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def source_lookup(company: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(source.get("source_id")): source for source in company.get("sources", []) or [] if source.get("source_id")}


def project_sources(company: dict[str, Any], project: dict[str, Any]) -> list[dict[str, Any]]:
    sources = source_lookup(company)
    return [sources[source_id] for source_id in project.get("source_ids", []) or [] if source_id in sources]


def has_primary_source(company: dict[str, Any], project: dict[str, Any]) -> bool:
    return any(source.get("primary_source") or source.get("source_type") in PRIMARY_SOURCE_TYPES for source in project_sources(company, project))


def has_scale(project: dict[str, Any]) -> bool:
    return any(project.get(field) is not None for field in SCALE_FIELDS)


def project_year(project: dict[str, Any]) -> int | None:
    for field in ("completion_date", "contract_date", "construction_start_date", "verified_at"):
        value = project.get(field)
        if not value:
            continue
        try:
            return int(str(value)[:4])
        except ValueError:
            continue
    return None


def is_verified_project(project: dict[str, Any]) -> bool:
    return project.get("evidence_status") in VERIFIED_STATUSES and bool(project.get("source_ids"))


def project_coverage(company: dict[str, Any]) -> dict[str, Any]:
    projects = company.get("project_portfolio", []) or []
    verified = [project for project in projects if is_verified_project(project)]
    source_backed = [project for project in projects if project.get("source_ids")]
    role_clear = [project for project in projects if project.get("company_role") in ROLE_CLEAR_VALUES]
    scale_backed = [project for project in projects if has_scale(project)]
    recent = [project for project in projects if (project_year(project) or 0) >= RECENT_YEAR_CUTOFF]
    primary = [project for project in projects if has_primary_source(company, project)]
    gap = 0
    if not verified:
        gap += 3
    if len(source_backed) < len(projects):
        gap += 2
    if len(role_clear) < max(1, len(projects)):
        gap += 2
    if not scale_backed:
        gap += 1
    if not recent:
        gap += 1
    return {
        "company_id": company.get("company_id"),
        "company_name": company.get("company_name"),
        "analysis_tier": company.get("analysis_tier"),
        "project_count": len(projects),
        "verified_project_count": len(verified),
        "source_backed_project_count": len(source_backed),
        "primary_source_project_count": len(primary),
        "clear_role_project_count": len(role_clear),
        "scale_project_count": len(scale_backed),
        "recent_5y_project_count": len(recent),
        "project_gap_score": gap,
    }


def tier_rank(company: dict[str, Any]) -> int:
    return {"tier_1": 0, "tier_1b": 1, "tier_2": 2, "tier_3": 3}.get(str(company.get("analysis_tier")), 9)


def select_wave_targets(companies: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    indexed = [(index, company) for index, company in enumerate(companies) if company.get("competitive_role") == DIRECT_COMPETITOR]
    ranked = sorted(
        indexed,
        key=lambda item: (
            -project_coverage(item[1])["project_gap_score"],
            project_coverage(item[1])["verified_project_count"],
            project_coverage(item[1])["source_backed_project_count"],
            project_coverage(item[1])["clear_role_project_count"],
            project_coverage(item[1])["scale_project_count"],
            tier_rank(item[1]),
            item[0],
        ),
    )
    return [company for _, company in ranked[:limit]]


def rows_for_projects(companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for company in companies:
        for project in company.get("project_portfolio", []) or []:
            rows.append(
                {
                    "company_id": company.get("company_id"),
                    "company_name": company.get("company_name"),
                    "project_id": project.get("project_id"),
                    "project_name": project.get("project_name"),
                    "sector": project.get("sector") or project.get("building_use"),
                    "company_role": project.get("company_role"),
                    "structure_type": project.get("structure_type") or project.get("modular_method"),
                    "project_status": project.get("project_status"),
                    "source_count": len(project.get("source_ids", []) or []),
                    "primary_source_count": sum(1 for source in project_sources(company, project) if source.get("primary_source") or source.get("source_type") in PRIMARY_SOURCE_TYPES),
                    "has_scale": has_scale(project),
                    "verified_at": project.get("verified_at"),
                    "evidence_status": project.get("evidence_status"),
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def audit_projects(input_path: Path = DEFAULT_INPUT, artifact_dir: Path = DEFAULT_ARTIFACT_DIR) -> dict[str, Any]:
    payload = read_json(input_path)
    companies = payload.get("companies", [])
    direct = [company for company in companies if company.get("competitive_role") == DIRECT_COMPETITOR]
    coverage = [project_coverage(company) for company in direct]
    targets = select_wave_targets(companies)
    validation = validate_company_projects(input_path)
    all_project_rows = rows_for_projects(companies)
    target_rows = []
    for company in targets:
        row = project_coverage(company)
        reasons = []
        if row["verified_project_count"] == 0:
            reasons.append("verified_project_count=0")
        if row["clear_role_project_count"] == 0:
            reasons.append("role_gap")
        if row["scale_project_count"] == 0:
            reasons.append("scale_gap")
        target_rows.append({**row, "selection_reason": "; ".join(reasons) or "highest_gap_score"})

    artifact_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        artifact_dir / "target_selection.csv",
        target_rows,
        [
            "company_id",
            "company_name",
            "analysis_tier",
            "project_count",
            "verified_project_count",
            "source_backed_project_count",
            "primary_source_project_count",
            "clear_role_project_count",
            "scale_project_count",
            "recent_5y_project_count",
            "project_gap_score",
            "selection_reason",
        ],
    )
    write_csv(
        artifact_dir / "company_project_coverage.csv",
        coverage,
        [
            "company_id",
            "company_name",
            "analysis_tier",
            "project_count",
            "verified_project_count",
            "source_backed_project_count",
            "primary_source_project_count",
            "clear_role_project_count",
            "scale_project_count",
            "recent_5y_project_count",
            "project_gap_score",
        ],
    )
    project_fields = [
        "company_id",
        "company_name",
        "project_id",
        "project_name",
        "sector",
        "company_role",
        "structure_type",
        "project_status",
        "source_count",
        "primary_source_count",
        "has_scale",
        "verified_at",
        "evidence_status",
    ]
    write_csv(artifact_dir / "verified_projects.csv", all_project_rows, project_fields)
    write_csv(artifact_dir / "project_participants.csv", all_project_rows, project_fields)
    write_csv(artifact_dir / "project_role_matrix.csv", all_project_rows, project_fields)
    write_csv(artifact_dir / "project_sector_distribution.csv", all_project_rows, project_fields)
    write_csv(artifact_dir / "project_scale_inventory.csv", all_project_rows, project_fields)

    source_rows: list[dict[str, Any]] = []
    for company in companies:
        for project in company.get("project_portfolio", []) or []:
            for source in project_sources(company, project):
                source_rows.append(
                    {
                        "company_id": company.get("company_id"),
                        "project_id": project.get("project_id"),
                        "source_id": source.get("source_id"),
                        "source_type": source.get("source_type"),
                        "primary_source": source.get("primary_source"),
                        "supported_claims": ", ".join(source.get("supported_claims", []) or []),
                    }
                )
    write_csv(artifact_dir / "project_source_matrix.csv", source_rows, ["company_id", "project_id", "source_id", "source_type", "primary_source", "supported_claims"])

    validation_rows = validation["issues"]
    write_csv(artifact_dir / "validation_errors.csv", validation_rows, ["code", "company_id", "path", "message", "severity"])
    write_csv(artifact_dir / "duplicate_project_candidates.csv", [row for row in validation_rows if row["code"] == "duplicate_project_candidate"], ["code", "company_id", "path", "message", "severity"])
    write_csv(artifact_dir / "conflicting_values.csv", [], ["company_id", "project_id", "field", "value_a", "value_b", "evidence", "confidence"])
    write_csv(artifact_dir / "unsupported_claims.csv", [], ["company_id", "project_id", "claim", "reason", "recommended_follow_up"])
    write_csv(
        artifact_dir / "research_gaps.csv",
        [
            {
                "company_id": row["company_id"],
                "company_name": row["company_name"],
                "missing_section": "project_portfolio",
                "gap": row["selection_reason"],
                "priority": "P1" if row["company_id"] in {target.get("company_id") for target in targets} else "P2",
            }
            for row in target_rows
            if row["verified_project_count"] == 0 or row["clear_role_project_count"] == 0 or row["scale_project_count"] == 0
        ],
        ["company_id", "company_name", "missing_section", "gap", "priority"],
    )

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": str(input_path.relative_to(ROOT)),
        "direct_competitor_count": len(direct),
        "wave_target_count": len(targets),
        "wave_targets": [company.get("company_id") for company in targets],
        "project_count": sum(row["project_count"] for row in coverage),
        "verified_project_count": sum(row["verified_project_count"] for row in coverage),
        "primary_source_project_count": sum(row["primary_source_project_count"] for row in coverage),
        "validation": validation,
    }
    (artifact_dir / "project_portfolio_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = [
        "# Company Project Portfolio Wave 1 Audit",
        "",
        f"- Generated at: {result['generated_at']}",
        f"- Direct competitors: {result['direct_competitor_count']}",
        f"- Wave targets: {', '.join(result['wave_targets'])}",
        f"- Project records: {result['project_count']}",
        f"- Verified or partially verified project records: {result['verified_project_count']}",
        f"- Validation errors: {sum(1 for issue in validation['issues'] if issue['severity'] == 'error')}",
        "",
        "## Target Selection",
        "",
        "| Company | Projects | Verified | Role Clear | Scale | Reason |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in target_rows:
        markdown.append(
            f"| {row['company_name']} | {row['project_count']} | {row['verified_project_count']} | {row['clear_role_project_count']} | {row['scale_project_count']} | {row['selection_reason']} |"
        )
    (artifact_dir / "project_portfolio_audit.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit direct competitor project portfolio coverage.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    args = parser.parse_args()
    result = audit_projects(args.input, args.artifact_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["validation"]["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
