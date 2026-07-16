#!/usr/bin/env python3
"""Apply curated Wave 1B baselines for YooChang, NRB, and PlanM.

The wrapper reuses the conservative single-company importer, applies three files in
one deterministic transaction, preserves domain statuses when a curated file has no
records for that domain, removes null internal-only facts, and keeps the output stable
across repeated runs.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
IMPORTER_PATH = ROOT / "scripts/import_curated_company_baseline.py"
V1_PATH = ROOT / "frontend/public/data/companies/companies.json"
V2_PATH = ROOT / "frontend/public/data/companies/company_intelligence_v2.json"
CURATED_PATHS = [
    ROOT / "config/companies/curated/yuchang-enc.json",
    ROOT / "config/companies/curated/nrb.json",
    ROOT / "config/companies/curated/planm.json",
]
FIXED_GENERATED_AT = "2026-07-16T21:30:00+09:00"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_importer():
    spec = importlib.util.spec_from_file_location("curated_importer", IMPORTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load curated importer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def company_by_id(data: dict[str, Any], company_id: str) -> dict[str, Any]:
    return next(item for item in data.get("companies", []) if item.get("company_id") == company_id)


def summary_by_id(data: dict[str, Any], company_id: str) -> dict[str, Any] | None:
    return next(
        (item for item in data.get("materialized_summaries", []) if item.get("company_id") == company_id),
        None,
    )


def preserve_empty_domains(
    v1_before: dict[str, Any],
    v2_before: dict[str, Any],
    v1_after: dict[str, Any],
    v2_after: dict[str, Any],
    curated: dict[str, Any],
) -> None:
    company_id = curated["company_id"]
    before_company = company_by_id(v1_before, company_id)
    after_company = company_by_id(v1_after, company_id)

    before_domains = copy.deepcopy(before_company.get("intelligence_v2", {}).get("domain_statuses", {}))
    after_domains = after_company.setdefault("intelligence_v2", {}).setdefault("domain_statuses", {})

    domain_map = {
        "production": "production_status",
        "projects": "project_status",
        "technology": "technology_status",
        "strategy_events": "recent_signal_status",
    }
    for curated_key, domain_key in domain_map.items():
        if not curated.get(curated_key):
            if domain_key in before_domains:
                after_domains[domain_key] = before_domains[domain_key]

    if not curated.get("production"):
        after_company["production_summary"] = copy.deepcopy(before_company.get("production_summary", {}))

    before_summary = summary_by_id(v2_before, company_id)
    after_summary = summary_by_id(v2_after, company_id)
    if before_summary and after_summary:
        before_summary_domains = before_summary.get("domain_statuses", {})
        after_summary_domains = after_summary.setdefault("domain_statuses", {})
        for curated_key, domain_key in domain_map.items():
            if not curated.get(curated_key) and domain_key in before_summary_domains:
                after_summary_domains[domain_key] = before_summary_domains[domain_key]


def prune_null_internal_facts(v2: dict[str, Any], source_ids: set[str]) -> int:
    before = len(v2.get("facts", []))
    kept = []
    for item in v2.get("facts", []):
        item_sources = set(item.get("source_ids", []))
        value = item.get("value")
        if item_sources & source_ids and value in (None, [], {}):
            continue
        kept.append(item)
    v2["facts"] = kept
    return before - len(kept)


def link_strategy_events_to_evidence(v2: dict[str, Any], curated_files: list[dict[str, Any]]) -> None:
    evidence_by_id = {item.get("source_id"): item for item in v2.get("evidence", [])}
    for curated in curated_files:
        source_id = curated["source"]["source_id"]
        evidence = evidence_by_id.get(source_id)
        if not evidence:
            continue
        supports = list(evidence.get("supports", []))
        for event in curated.get("strategy_events", []):
            event_id = event["event_id"]
            if event_id not in supports:
                supports.append(event_id)
        evidence["supports"] = supports


def validate(v1: dict[str, Any], v2: dict[str, Any], original_company_count: int) -> None:
    companies = v1.get("companies", [])
    if len(companies) != original_company_count:
        raise RuntimeError("Company count changed unexpectedly")
    company_ids = [item.get("company_id") for item in companies]
    if len(company_ids) != len(set(company_ids)):
        raise RuntimeError("Duplicate V1 company_id detected")

    for collection, key in (
        (v2.get("facts", []), "fact_id"),
        (v2.get("events", []), "event_id"),
        (v2.get("evidence", []), "source_id"),
    ):
        values = [item.get(key) for item in collection]
        if len(values) != len(set(values)):
            raise RuntimeError(f"Duplicate {key} detected")

    for company_id in ("yuchang-enc", "nrb", "planm"):
        company_by_id(v1, company_id)
        if not any(item.get("company_id") == company_id for item in v2.get("companies", [])):
            raise RuntimeError(f"Missing V2 company: {company_id}")

    samsung_event = next(
        item
        for item in v2.get("events", [])
        if item.get("event_id") == "event-yuchang-enc-samsung-ai-modular-home"
    )
    if samsung_event.get("event_type") != "partnership":
        raise RuntimeError("YooChang-Samsung event must remain a partnership")
    if samsung_event.get("event_status") != "not_signed" or samsung_event.get("project_credit"):
        raise RuntimeError("YooChang-Samsung event must remain not-signed and excluded from project credit")

    for company_id in ("nrb", "planm"):
        company = company_by_id(v1, company_id)
        if company.get("production"):
            raise RuntimeError(f"Unverified production facility was created for {company_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Validate without writing")
    args = parser.parse_args()

    importer = load_importer()
    v1_original = load_json(V1_PATH)
    v2_original = load_json(V2_PATH)
    v1 = copy.deepcopy(v1_original)
    v2 = copy.deepcopy(v2_original)
    curated_files = [load_json(path) for path in CURATED_PATHS]

    for curated in curated_files:
        before_v1 = copy.deepcopy(v1)
        before_v2 = copy.deepcopy(v2)
        v1 = importer.merge_v1(v1, curated)
        v2 = importer.merge_v2(v2, curated)
        preserve_empty_domains(before_v1, before_v2, v1, v2, curated)

    source_ids = {item["source"]["source_id"] for item in curated_files}
    removed_null_facts = prune_null_internal_facts(v2, source_ids)
    link_strategy_events_to_evidence(v2, curated_files)

    v1["generated_at"] = FIXED_GENERATED_AT
    v2["generated_at"] = FIXED_GENERATED_AT
    validate(v1, v2, len(v1_original.get("companies", [])))

    if not args.check:
        dump_json(V1_PATH, v1)
        dump_json(V2_PATH, v2)

    result = {
        "companies": [item["company_id"] for item in curated_files],
        "company_count": len(v1.get("companies", [])),
        "facts_added": len(v2.get("facts", [])) - len(v2_original.get("facts", [])),
        "events_added": len(v2.get("events", [])) - len(v2_original.get("events", [])),
        "evidence_added": len(v2.get("evidence", [])) - len(v2_original.get("evidence", [])),
        "null_internal_facts_removed": removed_null_facts,
        "mode": "check" if args.check else "write",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
