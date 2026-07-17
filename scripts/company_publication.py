from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ALLOWLIST = ROOT / "config" / "companies" / "public_verified_company_ids.json"


def load_public_company_ids(path: Path = PUBLIC_ALLOWLIST) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get("company_ids")
    if not isinstance(values, list) or not values:
        raise RuntimeError(f"{path} must contain a non-empty company_ids array")
    ids = [str(value) for value in values]
    if len(ids) != len(set(ids)):
        raise RuntimeError(f"{path} contains duplicate company_ids")
    return ids


def public_company_id_set(path: Path = PUBLIC_ALLOWLIST) -> set[str]:
    return set(load_public_company_ids(path))


def source_ids_from_company(company: dict[str, Any]) -> set[str]:
    source_ids: set[str] = set()
    for source in company.get("sources", []) or []:
        if source.get("source_id"):
            source_ids.add(str(source["source_id"]))
    for collection_name in ("financials", "production", "project_portfolio", "project_candidates", "recent_signals"):
        for item in company.get(collection_name, []) or []:
            for source_id in item.get("source_ids", []) or []:
                source_ids.add(str(source_id))
    technology = company.get("technology") if isinstance(company.get("technology"), dict) else {}
    for values in technology.values():
        if isinstance(values, list):
            for item in values:
                if isinstance(item, dict):
                    for source_id in item.get("source_ids", []) or []:
                        source_ids.add(str(source_id))
    return source_ids


def filter_v1_public(v1: dict[str, Any], allowed_ids: set[str]) -> dict[str, Any]:
    result = copy.deepcopy(v1)
    result["companies"] = [
        company
        for company in result.get("companies", []) or []
        if company.get("company_id") in allowed_ids
    ]
    return result


def filter_v2_public(v2: dict[str, Any], v1_public: dict[str, Any], allowed_ids: set[str]) -> dict[str, Any]:
    result = copy.deepcopy(v2)

    result["companies"] = [
        company
        for company in result.get("companies", []) or []
        if company.get("company_id") in allowed_ids
    ]
    result["facts"] = [
        fact
        for fact in result.get("facts", []) or []
        if fact.get("company_id") in allowed_ids
    ]
    result["events"] = [
        event
        for event in result.get("events", []) or []
        if event.get("company_id") in allowed_ids
    ]
    result["corrections"] = [
        correction
        for correction in result.get("corrections", []) or []
        if correction.get("company_id") in allowed_ids
    ]
    result["materialized_summaries"] = [
        summary
        for summary in result.get("materialized_summaries", []) or []
        if summary.get("company_id") in allowed_ids
    ]

    kept_fact_ids = {fact.get("fact_id") for fact in result["facts"]}
    kept_event_ids = {event.get("event_id") for event in result["events"]}
    kept_record_ids = kept_fact_ids | kept_event_ids
    kept_source_ids: set[str] = set()
    for company in v1_public.get("companies", []) or []:
        kept_source_ids |= source_ids_from_company(company)
    for item in result["facts"] + result["events"] + result["corrections"]:
        for source_id in item.get("source_ids", []) or []:
            kept_source_ids.add(str(source_id))

    evidence = []
    for source in result.get("evidence", []) or []:
        source_id = source.get("source_id")
        supports = [value for value in source.get("supports", []) or [] if value in kept_record_ids]
        contradicts = [value for value in source.get("contradicts", []) or [] if value in kept_record_ids]
        if source_id in kept_source_ids or supports or contradicts:
            item = copy.deepcopy(source)
            item["supports"] = supports
            item["contradicts"] = contradicts
            evidence.append(item)
    result["evidence"] = evidence

    result.setdefault("audit_metadata", {})["public_publication_allowlist"] = {
        "company_count": len(allowed_ids),
        "company_ids": sorted(allowed_ids),
    }
    return result


def filter_public_payloads(v1: dict[str, Any], v2: dict[str, Any], allowed_ids: set[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    v1_public = filter_v1_public(v1, allowed_ids)
    v2_public = filter_v2_public(v2, v1_public, allowed_ids)
    return v1_public, v2_public
