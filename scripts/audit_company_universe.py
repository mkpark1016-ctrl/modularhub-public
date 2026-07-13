#!/usr/bin/env python3
"""Create audit artifacts for the ModularHub company universe."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_company_universe import DEFAULT_INPUT, load_universe, validate_universe

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "company-universe-audit"


def companies(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return payload.get("companies", []) if isinstance(payload.get("companies"), list) else []


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        fieldnames = sorted({key for row in rows for key in row.keys()})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def company_inventory(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "company_id": row.get("company_id"),
            "company_name": row.get("company_name"),
            "company_type": row.get("company_type"),
            "competitive_role": row.get("competitive_role"),
            "analysis_tier": row.get("analysis_tier"),
            "country_code": row.get("country_code"),
            "review_status": row.get("review_status"),
            "data_confidence": row.get("data_confidence"),
            "alias_count": len(row.get("aliases", []) or []),
            "source_count": len(row.get("sources", []) or []),
        }
        for row in rows
    ]


def aliases(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        for alias in row.get("aliases", []) or []:
            output.append(
                {
                    "company_id": row.get("company_id"),
                    "company_name": row.get("company_name"),
                    "alias": alias,
                }
            )
    return output


def distribution(counter: Counter) -> list[dict[str, Any]]:
    return [{"value": key, "count": count} for key, count in sorted(counter.items())]


def missing_required_fields(validation: dict[str, Any]) -> list[dict[str, Any]]:
    return [error for error in validation["errors"] if error["code"] == "missing_required_field"]


def source_inventory(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        for source in row.get("sources", []) or []:
            output.append(
                {
                    "company_id": row.get("company_id"),
                    "company_name": row.get("company_name"),
                    "source_id": source.get("source_id"),
                    "source_type": source.get("source_type"),
                    "source_name": source.get("source_name"),
                    "source_url": source.get("source_url"),
                    "published_at": source.get("published_at"),
                    "accessed_at": source.get("accessed_at"),
                    "confidence": source.get("confidence"),
                    "verification_note": source.get("verification_note"),
                }
            )
    return output


def research_required(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        missing_production = not bool(row.get("production"))
        missing_projects = not bool(row.get("project_portfolio"))
        missing_bidding = not bool(row.get("bidding_performance"))
        missing_technology = not any(
            [
                row.get("technology", {}).get("structural_systems"),
                row.get("technology", {}).get("connection_technologies"),
                row.get("technology", {}).get("patents"),
                row.get("technology", {}).get("new_construction_technologies"),
            ]
        )
        missing_financials = not bool(row.get("financials"))
        missing_recent_signals = not bool(row.get("recent_signals"))
        tier = row.get("analysis_tier")
        role = row.get("competitive_role")
        if tier == "tier_1":
            priority = "P0"
        elif tier == "tier_1b":
            priority = "P1"
        elif role == "strategic_benchmark":
            priority = "P2"
        else:
            priority = "P3"
        output.append(
            {
                "company_id": row.get("company_id"),
                "company_name": row.get("company_name"),
                "analysis_tier": tier,
                "missing_production": missing_production,
                "missing_projects": missing_projects,
                "missing_bidding": missing_bidding,
                "missing_technology": missing_technology,
                "missing_financials": missing_financials,
                "missing_recent_signals": missing_recent_signals,
                "research_priority": priority,
            }
        )
    return output


def audit(payload: dict[str, Any]) -> dict[str, Any]:
    rows = companies(payload)
    validation = validate_universe(payload)
    tier_counts = Counter(row.get("analysis_tier") for row in rows)
    role_counts = Counter(row.get("competitive_role") for row in rows)
    type_counts = Counter(row.get("company_type") for row in rows)
    research_rows = research_required(rows)
    result = {
        "audit_status": "passed" if validation["valid"] else "failed",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": payload.get("schema_version"),
        "company_count": len(rows),
        "tier_counts": dict(tier_counts),
        "role_counts": dict(role_counts),
        "company_type_counts": dict(type_counts),
        "direct_competitor_count": role_counts.get("direct_competitor", 0),
        "internal_baseline_count": role_counts.get("internal_baseline", 0),
        "company_id_duplicate_count": validation["company_id_duplicate_count"],
        "alias_collision_count": validation["alias_collision_count"],
        "required_field_missing_count": validation["required_field_missing_count"],
        "invalid_enum_count": validation["invalid_enum_count"],
        "unverified_numeric_count": validation["unverified_numeric_count"],
        "production_capacity_without_unit_count": validation["production_capacity_without_unit_count"],
        "financial_scope_missing_count": validation["financial_scope_missing_count"],
        "research_required_count": len([row for row in research_rows if row["research_priority"] in {"P0", "P1", "P2", "P3"}]),
        "tier_1_research_required_count": len([row for row in research_rows if row["analysis_tier"] == "tier_1"]),
        "validation_errors": validation["errors"],
        "validation_warnings": validation["warnings"],
    }
    return result


def markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# Company Universe Audit",
        "",
        f"- Audit status: **{result['audit_status']}**",
        f"- Checked at: {result['checked_at']}",
        f"- Company count: {result['company_count']}",
        f"- Direct competitors: {result['direct_competitor_count']}",
        f"- Internal baseline: {result['internal_baseline_count']}",
        f"- Company ID duplicates: {result['company_id_duplicate_count']}",
        f"- Alias collisions: {result['alias_collision_count']}",
        f"- Missing required fields: {result['required_field_missing_count']}",
        f"- Invalid enum values: {result['invalid_enum_count']}",
        f"- Unverified seed numbers: {result['unverified_numeric_count']}",
        "",
        "## Tier Distribution",
        "",
    ]
    for key, count in sorted(result["tier_counts"].items()):
        lines.append(f"- {key}: {count}")
    lines.extend(["", "## Role Distribution", ""])
    for key, count in sorted(result["role_counts"].items()):
        lines.append(f"- {key}: {count}")
    if result["validation_errors"]:
        lines.extend(["", "## Validation Errors", ""])
        for error in result["validation_errors"]:
            lines.append(f"- {error['code']} {error['company_id']} {error['field']}: {error['message']}")
    return "\n".join(lines) + "\n"


def write_outputs(payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    rows = companies(payload)
    result = audit(payload)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "company_universe_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "company_universe_audit.md").write_text(markdown_report(result), encoding="utf-8")
    write_csv(output_dir / "company_inventory.csv", company_inventory(rows))
    write_csv(output_dir / "company_aliases.csv", aliases(rows), ["company_id", "company_name", "alias"])
    write_csv(output_dir / "company_tier_distribution.csv", distribution(Counter(row.get("analysis_tier") for row in rows)))
    write_csv(output_dir / "company_role_distribution.csv", distribution(Counter(row.get("competitive_role") for row in rows)))
    write_csv(output_dir / "missing_required_fields.csv", missing_required_fields(validate_universe(payload)))
    write_csv(output_dir / "research_required.csv", research_required(rows))
    write_csv(output_dir / "source_inventory.csv", source_inventory(rows), ["company_id", "company_name", "source_id", "source_type", "source_name", "source_url", "published_at", "accessed_at", "confidence", "verification_note"])
    write_csv(output_dir / "validation_errors.csv", result["validation_errors"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit ModularHub company universe.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = load_universe(args.input)
    result = write_outputs(payload, args.output_dir)
    print(f"Company universe audit: {result['audit_status']}")
    print(f"Artifacts: {args.output_dir}")
    return 0 if result["audit_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
