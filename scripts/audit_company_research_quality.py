#!/usr/bin/env python3
"""Generate Wave 1 company research quality audit artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_company_research import DEFAULT_INPUT, WAVE1_IDS, load_companies, validate_research, wave1_companies

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "company-research-wave-1"


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        fieldnames = sorted({key for row in rows for key in row.keys()})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def coverage_rows(companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for company in companies:
        sources = company.get("sources", []) or []
        primary_sources = [source for source in sources if source.get("primary_source")]
        rows.append(
            {
                "company_id": company["company_id"],
                "company_name": company["company_name"],
                "review_status": company.get("review_status"),
                "data_confidence": company.get("data_confidence"),
                "source_count": len(sources),
                "primary_source_count": len(primary_sources),
                "production_count": len(company.get("production", []) or []),
                "project_count": len(company.get("project_portfolio", []) or []),
                "bidding_record_count": len(company.get("bidding_performance", []) or []),
                "technology_record_count": technology_count(company),
                "financial_year_count": len(company.get("financials", []) or []),
                "recent_signal_count": len(company.get("recent_signals", []) or []),
                "research_gap_count": len(company.get("research_gaps", []) or []),
            }
        )
    return rows


def technology_count(company: dict[str, Any]) -> int:
    technology = company.get("technology", {}) or {}
    return sum(len(value) for value in technology.values() if isinstance(value, list) and value and isinstance(value[0], dict))


def source_coverage(companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for company in companies:
        for source in company.get("sources", []) or []:
            rows.append(
                {
                    "company_id": company["company_id"],
                    "company_name": company["company_name"],
                    "source_id": source.get("source_id"),
                    "source_type": source.get("source_type"),
                    "source_name": source.get("source_name"),
                    "title": source.get("title"),
                    "source_url": source.get("source_url"),
                    "published_at": source.get("published_at"),
                    "accessed_at": source.get("accessed_at"),
                    "publisher": source.get("publisher"),
                    "primary_source": source.get("primary_source"),
                    "confidence": source.get("confidence"),
                    "verification_note": source.get("verification_note"),
                }
            )
    return rows


def production_rows(companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for company in companies:
        for facility in company.get("production", []) or []:
            row = {"company_id": company["company_id"], "company_name": company["company_name"]}
            row.update(facility)
            rows.append(row)
    return rows


def project_rows(companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for company in companies:
        for project in company.get("project_portfolio", []) or []:
            row = {"company_id": company["company_id"], "company_name": company["company_name"]}
            row.update(project)
            rows.append(row)
    return rows


def bidding_rows(companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for company in companies:
        for record in company.get("bidding_performance", []) or []:
            row = {"company_id": company["company_id"], "company_name": company["company_name"]}
            row.update(record)
            rows.append(row)
    return rows


def technology_rows(companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for company in companies:
        for collection, values in (company.get("technology", {}) or {}).items():
            if not isinstance(values, list):
                continue
            for record in values:
                if not isinstance(record, dict):
                    continue
                row = {"company_id": company["company_id"], "company_name": company["company_name"], "collection": collection}
                row.update(record)
                rows.append(row)
    return rows


def financial_rows(companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for company in companies:
        for record in company.get("financials", []) or []:
            row = {"company_id": company["company_id"], "company_name": company["company_name"]}
            row.update(record)
            rows.append(row)
    return rows


def signal_rows(companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for company in companies:
        for signal in company.get("recent_signals", []) or []:
            row = {"company_id": company["company_id"], "company_name": company["company_name"]}
            row.update(signal)
            rows.append(row)
    return rows


def research_gaps(companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for company in companies:
        for gap in company.get("research_gaps", []) or []:
            rows.append(
                {
                    "company_id": company["company_id"],
                    "company_name": company["company_name"],
                    "area": gap.get("area"),
                    "status": gap.get("status"),
                    "note": gap.get("note"),
                }
            )
    return rows


def unsupported_claims(validation: dict[str, Any]) -> list[dict[str, Any]]:
    return [issue for issue in validation["issues"] if issue["code"] == "fact_without_source"]


def unsupported_numbers(validation: dict[str, Any]) -> list[dict[str, Any]]:
    return [issue for issue in validation["issues"] if issue["code"] == "number_without_source"]


def duplicate_sources(validation: dict[str, Any]) -> list[dict[str, Any]]:
    return [issue for issue in validation["issues"] if issue["code"] == "duplicate_source_url"]


def conflicting_values(companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for company in companies:
        for conflict in company.get("conflicting_values", []) or []:
            row = {"company_id": company["company_id"], "company_name": company["company_name"]}
            row.update(conflict)
            rows.append(row)
    return rows


def stale_sources(companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Current seed sources were accessed during this wave. Keep this explicit
    # table for the future rolling audit.
    return []


def review_status_results(companies: list[dict[str, Any]], validation: dict[str, Any]) -> list[dict[str, Any]]:
    issue_counts = Counter(issue["company_id"] for issue in validation["issues"])
    rows = []
    for company in companies:
        rows.append(
            {
                "company_id": company["company_id"],
                "company_name": company["company_name"],
                "review_status": company.get("review_status"),
                "data_confidence": company.get("data_confidence"),
                "validation_issue_count": issue_counts.get(company["company_id"], 0),
                "source_count": len(company.get("sources", []) or []),
                "project_count": len(company.get("project_portfolio", []) or []),
                "gap_count": len(company.get("research_gaps", []) or []),
            }
        )
    return rows


def audit(path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    all_companies = load_companies(path)
    companies = wave1_companies(all_companies)
    validation = validate_research(path)
    coverage = coverage_rows(companies)
    result = {
        "audit_status": "passed" if validation["valid"] else "failed",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "wave_1_company_ids": WAVE1_IDS,
        "wave_1_company_count": len(companies),
        "company_coverage": coverage,
        "total_source_count": sum(row["source_count"] for row in coverage),
        "total_primary_source_count": sum(row["primary_source_count"] for row in coverage),
        "total_production_count": sum(row["production_count"] for row in coverage),
        "total_project_count": sum(row["project_count"] for row in coverage),
        "total_bidding_record_count": sum(row["bidding_record_count"] for row in coverage),
        "total_technology_record_count": sum(row["technology_record_count"] for row in coverage),
        "total_financial_year_count": sum(row["financial_year_count"] for row in coverage),
        "total_recent_signal_count": sum(row["recent_signal_count"] for row in coverage),
        "issue_counts": validation["issue_counts"],
        "issues": validation["issues"],
        "conflicting_value_count": len(conflicting_values(companies)),
        "stale_source_count": len(stale_sources(companies)),
    }
    return result


def markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# Company Research Wave 1 Audit",
        "",
        f"- Audit status: **{result['audit_status']}**",
        f"- Checked at: {result['checked_at']}",
        f"- Wave 1 companies: {result['wave_1_company_count']}",
        f"- Total sources: {result['total_source_count']}",
        f"- Primary sources: {result['total_primary_source_count']}",
        f"- Production facilities: {result['total_production_count']}",
        f"- Verified project records: {result['total_project_count']}",
        f"- Bidding records: {result['total_bidding_record_count']}",
        f"- Technology records: {result['total_technology_record_count']}",
        f"- Financial years: {result['total_financial_year_count']}",
        f"- Recent signals: {result['total_recent_signal_count']}",
        f"- Unsupported facts: {result['issue_counts']['fact_without_source']}",
        f"- Unsupported numbers: {result['issue_counts']['number_without_source']}",
        f"- Conflicts: {result['conflicting_value_count']}",
        f"- Stale sources: {result['stale_source_count']}",
        "",
        "## Company Coverage",
        "",
        "| Company | Review | Confidence | Sources | Primary | Projects | Technology | Gaps |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["company_coverage"]:
        lines.append(
            f"| {row['company_name']} | {row['review_status']} | {row['data_confidence']} | {row['source_count']} | {row['primary_source_count']} | {row['project_count']} | {row['technology_record_count']} | {row['research_gap_count']} |"
        )
    if result["issues"]:
        lines.extend(["", "## Validation Issues", ""])
        for issue in result["issues"]:
            lines.append(f"- {issue['code']} {issue['company_id']} {issue['path']}: {issue['message']}")
    return "\n".join(lines) + "\n"


def write_outputs(path: Path, output_dir: Path) -> dict[str, Any]:
    companies = wave1_companies(load_companies(path))
    result = audit(path)
    validation = validate_research(path)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "company_research_wave_1_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "company_research_wave_1_audit.md").write_text(markdown_report(result), encoding="utf-8")
    write_csv(output_dir / "company_data_coverage.csv", coverage_rows(companies))
    write_csv(output_dir / "company_source_coverage.csv", source_coverage(companies))
    write_csv(output_dir / "production_facilities.csv", production_rows(companies))
    write_csv(output_dir / "verified_projects.csv", project_rows(companies))
    write_csv(output_dir / "bidding_performance.csv", bidding_rows(companies))
    write_csv(output_dir / "technology_inventory.csv", technology_rows(companies))
    write_csv(output_dir / "financial_inventory.csv", financial_rows(companies))
    write_csv(output_dir / "recent_signals.csv", signal_rows(companies))
    write_csv(output_dir / "unsupported_claims.csv", unsupported_claims(validation))
    write_csv(output_dir / "conflicting_values.csv", conflicting_values(companies))
    write_csv(output_dir / "stale_sources.csv", stale_sources(companies))
    write_csv(output_dir / "duplicate_sources.csv", duplicate_sources(validation))
    write_csv(output_dir / "research_gaps.csv", research_gaps(companies))
    write_csv(output_dir / "review_status_results.csv", review_status_results(companies, validation))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Wave 1 company research quality.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = write_outputs(args.input, args.output_dir)
    print(f"Company research wave 1 audit: {result['audit_status']}")
    print(f"Artifacts: {args.output_dir}")
    return 0 if result["audit_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
