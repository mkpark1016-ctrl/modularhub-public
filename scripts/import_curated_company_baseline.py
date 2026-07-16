#!/usr/bin/env python3
"""Merge a curated company baseline into ModularHub V1 and V2 company datasets.

The importer is intentionally conservative: existing DART/financial records are preserved,
unsupported capacity values remain null, and project credit is stored separately from MOU,
planned, preferred-bidder, and unconfirmed events.
"""
from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CURATED = ROOT / "config/companies/curated/kumkang-kind.json"
DEFAULT_V1 = ROOT / "frontend/public/data/companies/companies.json"
DEFAULT_V2 = ROOT / "frontend/public/data/companies/company_intelligence_v2.json"

STATUS_TO_EVENT = {
    "completed": "completed",
    "under_construction": "in_progress",
    "contracted": "contract_signed",
    "awarded": "award_confirmed",
    "preferred_bidder": "preferred_bidder",
    "planned": "planned",
    "cancelled": "cancelled",
    "unconfirmed": "unconfirmed",
    "unknown": "unconfirmed",
}


def load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def dump(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def upsert(items: list[dict[str, Any]], key: str, value: dict[str, Any]) -> None:
    target = value.get(key)
    for index, item in enumerate(items):
        if item.get(key) == target:
            merged = copy.deepcopy(item)
            merged.update(copy.deepcopy(value))
            items[index] = merged
            return
    items.append(copy.deepcopy(value))


def source_record(curated: dict[str, Any]) -> dict[str, Any]:
    source = curated["source"]
    return {
        "source_id": source["source_id"],
        "source_type": source["source_type"],
        "source_name": source["title"],
        "title": source["title"],
        "source_url": None,
        "published_at": None,
        "accessed_at": curated["reviewed_at"],
        "publisher": "Internal competitor research",
        "primary_source": False,
        "confidence": source["confidence"],
        "verification_note": source["note"],
    }


def normalize_project(project: dict[str, Any], company_id: str, source_id: str, reviewed_at: str) -> dict[str, Any]:
    result = copy.deepcopy(project)
    result["company_id"] = company_id
    result.setdefault("aliases", [])
    result.setdefault("country_code", "KR")
    result.setdefault("sector", result.get("market_segment") or result.get("building_use") or "other")
    result.setdefault("structure_type", result.get("modular_method") or "unknown")
    result.setdefault("modular_type", result.get("modular_method") or "unknown")
    result.setdefault("evidence_status", result.get("verification_status", "internally_confirmed"))
    result.setdefault("data_confidence", result.get("confidence", "medium"))
    result.setdefault("source_ids", [source_id])
    result.setdefault("verified_at", reviewed_at[:10])
    result.setdefault("client_name", result.get("client"))
    result.setdefault("role_detail", result.get("summary"))
    result.setdefault("project_summary", result.get("summary"))
    result.setdefault("source_count", 1)
    result.setdefault("primary_source_count", 0)
    result.setdefault("research_wave", "curated_baseline_pilot")
    result.setdefault("enrichment_status", "curated_internal_baseline")
    return result


def merge_v1(data: dict[str, Any], curated: dict[str, Any]) -> dict[str, Any]:
    company_id = curated["company_id"]
    companies = data.get("companies", [])
    company = next((item for item in companies if item.get("company_id") == company_id), None)
    if company is None:
        raise RuntimeError(f"Company not found in V1 dataset: {company_id}")

    reviewed_at = curated["reviewed_at"]
    source_id = curated["source"]["source_id"]
    profile = curated["company"]

    for field in ("company_name", "company_name_en", "aliases", "company_type", "competitive_role", "analysis_tier", "business_status", "modular_methods", "target_markets"):
        if field in profile:
            company[field] = copy.deepcopy(profile[field])

    company["summary"] = profile["summary_ko"]
    company["last_verified_at"] = reviewed_at
    company["data_confidence"] = "medium"
    company["review_status"] = "partially_verified"
    company.setdefault("company_profile", {})
    company["company_profile"].update({
        "established_at": profile.get("established_at"),
        "listed_at": profile.get("listed_at"),
        "representative": profile.get("representative"),
        "employee_count": profile.get("employee_count_research_value"),
        "employee_count_as_of": profile.get("employee_count_as_of"),
    })

    production = company.setdefault("production", [])
    for facility in curated.get("production", []):
        normalized = copy.deepcopy(facility)
        normalized["company_id"] = company_id
        normalized.setdefault("source_ids", [source_id])
        normalized.setdefault("verified_at", reviewed_at[:10])
        normalized.setdefault("data_confidence", normalized.get("confidence", "medium"))
        upsert(production, "facility_id", normalized)

    projects = company.setdefault("project_portfolio", [])
    for project in curated.get("projects", []):
        upsert(projects, "project_id", normalize_project(project, company_id, source_id, reviewed_at))

    technology = company.get("technology")
    if technology is None:
        technology = {}
        company["technology"] = technology
    elif not isinstance(technology, dict):
        raise RuntimeError("V1 company technology must be an object")
    patents = technology.setdefault("patents", [])
    curated_technology = curated.get("technology", [])
    if isinstance(curated_technology, dict):
        technology_records = curated_technology.get("patents", [])
    elif isinstance(curated_technology, list):
        technology_records = curated_technology
    else:
        raise RuntimeError("Curated technology must be a list or object")
    for patent in technology_records:
        normalized = copy.deepcopy(patent)
        normalized.setdefault("source_ids", [source_id])
        normalized.setdefault("verified_at", reviewed_at[:10])
        upsert(patents, "technology_id", normalized)

    signals = company.setdefault("recent_signals", [])
    for event in curated.get("strategy_events", []):
        signal = {
            "signal_id": event["event_id"],
            "signal_type": event["event_type"],
            "title": event["title"],
            "occurred_at": event.get("announced_at") or event.get("contracted_at"),
            "summary": event.get("summary"),
            "significance": event.get("summary"),
            "source_ids": [source_id],
            "verified_at": reviewed_at[:10],
            "confidence": event.get("confidence", "medium"),
        }
        upsert(signals, "signal_id", signal)

    sources = company.setdefault("sources", [])
    upsert(sources, "source_id", source_record(curated))

    intelligence = company.setdefault("intelligence_v2", {})
    intelligence["summary_ko"] = profile["summary_ko"]
    intelligence["overall_data_status"] = "partially_verified"
    domains = intelligence.setdefault("domain_statuses", {})
    domains.update({
        "identity_status": domains.get("identity_status", "partially_verified"),
        "financial_status": domains.get("financial_status", "partially_verified"),
        "production_status": "partially_verified",
        "project_status": "internally_confirmed",
        "technology_status": "internally_confirmed",
        "recent_signal_status": "internally_confirmed",
    })
    intelligence["updated_at"] = reviewed_at

    return data


def fact(company_id: str, domain: str, field: str, value: Any, unit: str | None, period: str | int | None, source_id: str, reviewed_at: str) -> dict[str, Any]:
    suffix = str(period) if period is not None else "current"
    return {
        "fact_id": f"fact-{company_id}-{domain}-{field}-{suffix}",
        "company_id": company_id,
        "domain": domain,
        "field": field,
        "value": value,
        "unit": unit,
        "period": period,
        "as_of": reviewed_at,
        "verification_status": "internally_confirmed",
        "confidence": "medium",
        "source_ids": [source_id],
        "visibility": "public",
        "updated_at": reviewed_at,
    }


def merge_v2(data: dict[str, Any], curated: dict[str, Any]) -> dict[str, Any]:
    company_id = curated["company_id"]
    reviewed_at = curated["reviewed_at"]
    source = curated["source"]
    source_id = source["source_id"]

    companies = data.setdefault("companies", [])
    if not any(item.get("company_id") == company_id for item in companies):
        raise RuntimeError(f"Company not found in V2 dataset: {company_id}")

    facts = data.setdefault("facts", [])
    profile = curated["company"]
    new_facts = [
        fact(company_id, "organization", "established_at", profile.get("established_at"), None, None, source_id, reviewed_at),
        fact(company_id, "organization", "listed_at", profile.get("listed_at"), None, None, source_id, reviewed_at),
        fact(company_id, "organization", "representative", profile.get("representative"), None, None, source_id, reviewed_at),
        fact(company_id, "organization", "employee_count", profile.get("employee_count_research_value"), "person", profile.get("employee_count_as_of"), source_id, reviewed_at),
    ]
    for item in curated.get("modular_revenue_research", []):
        new_facts.append(fact(company_id, "financial", "modular_revenue_research", item["value"], item["unit"], item["year"], source_id, reviewed_at))
    for facility in curated.get("production", []):
        new_facts.append(fact(company_id, "production", f"facility_{facility['facility_id']}", {
            "facility_name": facility.get("facility_name"),
            "site_area_m2": facility.get("site_area_m2"),
            "capacity_value": facility.get("reported_capacity"),
            "capacity_status": facility.get("capacity_status"),
            "operation_status": facility.get("operation_status"),
        }, None, None, source_id, reviewed_at))
    for item in new_facts:
        upsert(facts, "fact_id", item)

    events = data.setdefault("events", [])
    for project in curated.get("projects", []):
        event = {
            "event_id": f"event-{project['project_id']}",
            "company_id": company_id,
            "event_type": "project",
            "event_status": STATUS_TO_EVENT.get(project.get("project_status"), "unconfirmed"),
            "title": project["project_name"],
            "counterparties": [value for value in [project.get("client")] if value],
            "client": project.get("client"),
            "project_role": project.get("company_role"),
            "project_credit": bool(project.get("project_credit")),
            "announced_at": project.get("announced_at") or project.get("awarded_at"),
            "contracted_at": project.get("contract_date"),
            "started_at": project.get("start_date"),
            "completed_at": project.get("completion_date"),
            "amount": project.get("contract_amount"),
            "amount_unit": project.get("contract_amount_unit"),
            "location": project.get("location"),
            "market_segment": project.get("market_segment"),
            "method": project.get("modular_method"),
            "source_ids": [source_id],
            "verification_status": project.get("verification_status", "internally_confirmed"),
            "visibility": "public",
            "updated_at": reviewed_at,
        }
        upsert(events, "event_id", event)
    for item in curated.get("strategy_events", []):
        event = copy.deepcopy(item)
        event.setdefault("company_id", company_id)
        event.setdefault("counterparties", [])
        event.setdefault("client", None)
        event.setdefault("project_role", None)
        event.setdefault("project_credit", False)
        for field in ("announced_at", "contracted_at", "started_at", "completed_at", "amount", "amount_unit", "location", "market_segment", "method"):
            event.setdefault(field, None)
        event.setdefault("source_ids", [source_id])
        event.setdefault("verification_status", "internally_confirmed")
        event.setdefault("visibility", "public")
        event.setdefault("updated_at", reviewed_at)
        event.pop("confidence", None)
        event.pop("summary", None)
        upsert(events, "event_id", event)

    evidence = data.setdefault("evidence", [])
    evidence_item = {
        "source_id": source_id,
        "source_type": source["source_type"],
        "source_tier": source["source_tier"],
        "publisher": "Internal competitor research",
        "title": source["title"],
        "url": None,
        "published_at": None,
        "retrieved_at": reviewed_at,
        "document_id": None,
        "document_hash": None,
        "excerpt": source["note"],
        "supports": [item["fact_id"] for item in new_facts] + [f"event-{p['project_id']}" for p in curated.get("projects", [])],
        "contradicts": [],
        "visibility": "internal",
        "stale_after": None,
        "status": "active",
    }
    upsert(evidence, "source_id", evidence_item)

    summaries = data.setdefault("materialized_summaries", [])
    summary = next((item for item in summaries if item.get("company_id") == company_id), None)
    if summary:
        summary["overall_data_status"] = "partially_verified"
        summary.setdefault("domain_statuses", {}).update({
            "production_status": "partially_verified",
            "project_status": "internally_confirmed",
            "technology_status": "internally_confirmed",
            "recent_signal_status": "internally_confirmed",
        })
        summary["event_counts"] = {
            "verified_projects": sum(1 for item in curated.get("projects", []) if item.get("project_credit")),
            "project_candidates": sum(1 for item in curated.get("projects", []) if not item.get("project_credit")),
            "partnerships_mou": sum(1 for item in curated.get("strategy_events", []) if item.get("event_type") in {"partnership", "mou"}),
            "r_and_d_exhibition": sum(1 for item in curated.get("strategy_events", []) if item.get("event_type") in {"r_and_d", "exhibition"}),
            "other_events": 0,
        }
        summary["updated_at"] = reviewed_at

    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--curated", type=Path, default=DEFAULT_CURATED)
    parser.add_argument("--v1", type=Path, default=DEFAULT_V1)
    parser.add_argument("--v2", type=Path, default=DEFAULT_V2)
    parser.add_argument("--check", action="store_true", help="Validate merge without writing files")
    args = parser.parse_args()

    curated = load(args.curated)
    v1_original = load(args.v1)
    v2_original = load(args.v2)
    v1 = merge_v1(copy.deepcopy(v1_original), curated)
    v2 = merge_v2(copy.deepcopy(v2_original), curated)

    if len(v1.get("companies", [])) != len(v1_original.get("companies", [])):
        raise RuntimeError("Company count changed unexpectedly")
    if len({item.get("company_id") for item in v1.get("companies", [])}) != len(v1.get("companies", [])):
        raise RuntimeError("Duplicate V1 company_id detected")
    for collection, key in ((v2.get("facts", []), "fact_id"), (v2.get("events", []), "event_id"), (v2.get("evidence", []), "source_id")):
        values = [item.get(key) for item in collection]
        if len(values) != len(set(values)):
            raise RuntimeError(f"Duplicate {key} detected")

    if not args.check:
        dump(args.v1, v1)
        dump(args.v2, v2)
    print(json.dumps({
        "company_id": curated["company_id"],
        "company_count": len(v1["companies"]),
        "facts": len(v2.get("facts", [])) - len(v2_original.get("facts", [])),
        "events": len(v2.get("events", [])) - len(v2_original.get("events", [])),
        "evidence": len(v2.get("evidence", [])) - len(v2_original.get("evidence", [])),
        "mode": "check" if args.check else "write",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
