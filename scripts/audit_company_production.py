#!/usr/bin/env python3
"""Create Wave 1 production enrichment audit artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from validate_company_production import CONFIRMED_STATUSES, DEFAULT_INPUT, WAVE1_IDS, load_payload, validate

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "company-wave-1-production-enrichment"


def wave1(payload: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {company["company_id"]: company for company in payload.get("companies", [])}
    return [by_id[company_id] for company_id in WAVE1_IDS if company_id in by_id]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def source_lookup(company: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {source["source_id"]: source for source in company.get("sources", []) if source.get("source_id")}


def primary_secondary_counts(company: dict[str, Any], source_ids: list[str]) -> tuple[int, int]:
    sources = source_lookup(company)
    primary = 0
    secondary = 0
    for source_id in source_ids:
        source = sources.get(source_id)
        if not source:
            continue
        if source.get("primary_source"):
            primary += 1
        else:
            secondary += 1
    return primary, secondary


def latest_source_date(company: dict[str, Any], source_ids: list[str]) -> str:
    sources = source_lookup(company)
    dates = [sources[source_id].get("accessed_at") or sources[source_id].get("published_at") for source_id in source_ids if source_id in sources]
    return max((value for value in dates if value), default="")


def is_stale(value: str) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        parsed = date.fromisoformat(value[:10])
    return (date.today() - parsed).days > 365 * 3


def audit(payload: dict[str, Any]) -> dict[str, Any]:
    validation = validate(payload)
    companies = wave1(payload)
    summaries = []
    facilities = []
    capacities = []
    manufacturing = []
    source_claims = []
    stale_sources = []
    research_gaps = []
    conflicts = []

    for company in companies:
        summary = company.get("production_summary") or {}
        source_ids = summary.get("source_ids") or []
        primary_count, secondary_count = primary_secondary_counts(company, source_ids)
        confirmed_facility_count = int(summary.get("confirmed_facility_count") or 0)
        remaining_gaps = [gap for gap in company.get("research_gaps", []) if gap.get("area") == "production"]
        summaries.append({
            "company_id": company["company_id"],
            "company_name": company["company_name"],
            "research_status": summary.get("research_status", ""),
            "manufacturing_model": summary.get("manufacturing_model", ""),
            "own_facility_status": summary.get("own_facility_status", ""),
            "confirmed_facility_count": confirmed_facility_count,
            "reported_capacity_available": summary.get("reported_capacity_available"),
            "primary_source_count": primary_count,
            "secondary_source_count": secondary_count,
            "latest_source_date": latest_source_date(company, source_ids),
            "confidence": summary.get("data_confidence", ""),
            "remaining_gap_count": len(remaining_gaps),
        })
        manufacturing.append({
            "company_id": company["company_id"],
            "company_name": company["company_name"],
            "manufacturing_model": summary.get("manufacturing_model", ""),
            "own_facility_status": summary.get("own_facility_status", ""),
            "summary": summary.get("summary", ""),
            "source_ids": "|".join(source_ids),
        })
        for source in company.get("sources", []):
            if source.get("source_id") in source_ids and is_stale(source.get("accessed_at") or source.get("published_at") or ""):
                stale_sources.append({
                    "company_id": company["company_id"],
                    "source_id": source.get("source_id", ""),
                    "source_name": source.get("source_name", ""),
                    "source_url": source.get("source_url", ""),
                    "published_at": source.get("published_at", ""),
                    "accessed_at": source.get("accessed_at", ""),
                })
            for claim in source.get("supported_claims") or []:
                source_claims.append({
                    "company_id": company["company_id"],
                    "company_name": company["company_name"],
                    "source_id": source.get("source_id", ""),
                    "source_type": source.get("source_type", ""),
                    "primary_source": source.get("primary_source", False),
                    "supported_claim": claim,
                    "source_url": source.get("source_url", ""),
                })
        for facility in company.get("production") or []:
            facilities.append({
                "company_id": company["company_id"],
                "company_name": company["company_name"],
                "facility_id": facility.get("facility_id", ""),
                "facility_name": facility.get("facility_name", ""),
                "facility_type": facility.get("facility_type", ""),
                "own_facility_status": facility.get("own_facility_status", ""),
                "ownership_type": facility.get("ownership_type", ""),
                "operation_status": facility.get("operation_status", ""),
                "country": facility.get("country", ""),
                "region": facility.get("region", ""),
                "city": facility.get("city", ""),
                "address": facility.get("address", ""),
                "site_area_m2": facility.get("site_area_m2", ""),
                "building_area_m2": facility.get("building_area_m2", ""),
                "production_scope": "|".join(facility.get("production_scope") or []),
                "source_ids": "|".join(facility.get("source_ids") or []),
                "verified_at": facility.get("verified_at", ""),
                "confidence": facility.get("confidence", ""),
            })
            capacities.append({
                "company_id": company["company_id"],
                "company_name": company["company_name"],
                "facility_id": facility.get("facility_id", ""),
                "facility_name": facility.get("facility_name", ""),
                "reported_capacity": facility.get("reported_capacity", ""),
                "capacity_value": facility.get("capacity_value", ""),
                "capacity_unit": facility.get("capacity_unit", ""),
                "capacity_period": facility.get("capacity_period", ""),
                "capacity_basis": facility.get("capacity_basis", ""),
                "capacity_as_of": facility.get("capacity_as_of", ""),
                "source_ids": "|".join(facility.get("source_ids") or []),
            })
        for gap in remaining_gaps:
            research_gaps.append({
                "company_id": company["company_id"],
                "company_name": company["company_name"],
                "area": gap.get("area", ""),
                "status": gap.get("status", ""),
                "note": gap.get("note", gap.get("description", "")),
                "source_ids": "|".join(gap.get("source_ids") or []),
            })

    unsupported = [issue for issue in validation["issues"] if issue["code"] == "unsupported_claim"]
    return {
        "audit_status": "passed" if validation["valid"] and not unsupported else "failed",
        "validation": validation,
        "summary": {
            "target_company_count": len(companies),
            "confirmed_facility_company_count": sum(1 for row in summaries if int(row["confirmed_facility_count"]) > 0),
            "confirmed_facility_count": sum(int(row["confirmed_facility_count"]) for row in summaries),
            "reported_capacity_available_count": sum(1 for row in summaries if row["reported_capacity_available"] is True),
            "stale_source_count": len(stale_sources),
            "unsupported_claim_count": len(unsupported),
            "source_id_missing_count": validation["issue_counts"].get("source_id_missing", 0),
            "number_without_source_count": validation["issue_counts"].get("number_without_source", 0),
        },
        "rows": {
            "company_production_summary": summaries,
            "verified_facilities": facilities,
            "production_capacity_inventory": capacities,
            "manufacturing_model_inventory": manufacturing,
            "source_claim_matrix": source_claims,
            "unsupported_claims": unsupported,
            "stale_sources": stale_sources,
            "conflicting_values": conflicts,
            "research_gaps": research_gaps,
        },
    }


def write_artifacts(result: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "production_enrichment_audit.json").write_text(json.dumps({k: v for k, v in result.items() if k != "rows"}, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(output_dir / "company_production_summary.csv", result["rows"]["company_production_summary"])
    write_csv(output_dir / "verified_facilities.csv", result["rows"]["verified_facilities"])
    write_csv(output_dir / "production_capacity_inventory.csv", result["rows"]["production_capacity_inventory"])
    write_csv(output_dir / "manufacturing_model_inventory.csv", result["rows"]["manufacturing_model_inventory"])
    write_csv(output_dir / "source_claim_matrix.csv", result["rows"]["source_claim_matrix"])
    write_csv(output_dir / "unsupported_claims.csv", result["rows"]["unsupported_claims"])
    write_csv(output_dir / "stale_sources.csv", result["rows"]["stale_sources"])
    write_csv(output_dir / "conflicting_values.csv", result["rows"]["conflicting_values"])
    write_csv(output_dir / "research_gaps.csv", result["rows"]["research_gaps"])
    summary = result["summary"]
    lines = [
        "# Wave 1 Production Enrichment Audit",
        "",
        f"- Audit status: {result['audit_status']}",
        f"- Target companies: {summary['target_company_count']}",
        f"- Confirmed facility companies: {summary['confirmed_facility_company_count']}",
        f"- Confirmed facilities: {summary['confirmed_facility_count']}",
        f"- Reported capacity available: {summary['reported_capacity_available_count']}",
        f"- Source ID missing: {summary['source_id_missing_count']}",
        f"- Number without source: {summary['number_without_source_count']}",
        f"- Unsupported claims: {summary['unsupported_claim_count']}",
        f"- Stale sources: {summary['stale_source_count']}",
    ]
    (output_dir / "production_enrichment_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Wave 1 production enrichment.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    result = audit(load_payload(Path(args.input)))
    write_artifacts(result, Path(args.output_dir))
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, ensure_ascii=False, indent=2))
    if result["audit_status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
