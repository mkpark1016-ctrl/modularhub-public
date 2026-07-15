#!/usr/bin/env python3
"""Migrate the legacy company dataset into the Company Intelligence V2 truth layer."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPANIES = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"
DEFAULT_OUTPUT = ROOT / "data" / "companies" / "company_intelligence_v2.json"
PUBLIC_CORRECTIONS = ROOT / "config" / "companies" / "manual_corrections.public.json"
PRIVATE_CORRECTIONS = ROOT / "config" / "companies" / "manual_corrections.private.json"
PROTECTED_PUBLIC_FILES = {
    "business.json": ROOT / "frontend" / "public" / "data" / "business.json",
    "news.json": ROOT / "frontend" / "public" / "data" / "news.json",
    "meta.json": ROOT / "frontend" / "public" / "data" / "meta.json",
}
PROTECTED_COMPANY_FIELDS = [
    "dart_identity",
    "financials",
    "financial_summary",
    "audit_information",
    "production",
    "production_summary",
    "project_portfolio",
]
TODAY = "2026-07-15"

ALLOWED_PROJECT_CREDIT_STATUSES = {"completed", "in_progress", "contract_signed", "award_confirmed"}
UNKNOWN_PROJECT_ROLES = {None, "", "unknown", "role_unknown"}
STATUS_MAP = {
    "completed": "completed",
    "under_construction": "in_progress",
    "contracted": "contract_signed",
    "awarded": "award_confirmed",
    "bid": "bid_participation",
    "bidding": "bid_participation",
    "planned": "planned",
    "proposed": "planned",
    "cancelled": "cancelled",
}
SIGNAL_EVENT_TYPES = {
    "new_contract": "project",
    "project_award": "project",
    "factory_expansion": "facility_investment",
    "investment": "facility_investment",
    "mou": "mou",
    "technology_development": "r_and_d",
    "certification": "product_launch",
    "overseas_expansion": "business_strategy",
    "partnership": "partnership",
    "management_change": "organization_change",
    "restructuring": "organization_change",
    "business_reduction": "business_strategy",
}
SIGNAL_EVENT_STATUSES = {
    "new_contract": "contract_signed",
    "project_award": "award_confirmed",
    "factory_expansion": "in_progress",
    "investment": "planned",
    "mou": "mou_signed",
    "technology_development": "r_and_d",
    "certification": "completed",
    "partnership": "partnership_discussion",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def protected_hash(company: dict[str, Any]) -> str:
    return stable_hash({field: company.get(field) for field in PROTECTED_COMPANY_FIELDS})


def clean_ids(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return sorted({str(value) for value in values if value})


def has_value(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def source_tier(source_type: str) -> str:
    value = str(source_type or "").lower()
    if value in {
        "regulatory_filing", "audit_report", "procurement_notice", "procurement_contract",
        "government_release", "public_agency", "patent_record", "certification_record",
        "construction_new_technology", "law", "official_document",
    }:
        return "A"
    if value in {"official_website", "official_press_release", "official_brochure", "ir_material"}:
        return "B"
    if value in {"industry_news", "general_news", "research_report", "media_article", "trade_media"}:
        return "C"
    return "D"


def normalize_title(value: Any) -> str:
    text = unicodedata.normalize("NFC", str(value or "")).lower()
    text = re.sub(r"(?:주식회사|㈜|\(주\))", "", text)
    return re.sub(r"[^0-9a-z가-힣]+", "", text)


def verification_from_confidence(confidence: Any, source_ids: list[str]) -> str:
    if source_ids and confidence == "high":
        return "official_verified"
    if source_ids:
        return "partially_verified"
    return "internally_confirmed"


def load_corrections() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    public = read_json(PUBLIC_CORRECTIONS).get("corrections", []) if PUBLIC_CORRECTIONS.exists() else []
    private = read_json(PRIVATE_CORRECTIONS).get("corrections", []) if PRIVATE_CORRECTIONS.exists() else []
    return public, private


def collect_source_records(companies: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for company in companies:
        for source in company.get("sources") or []:
            source_id = source.get("source_id")
            if not source_id:
                continue
            candidate = deepcopy(source)
            candidate.setdefault("company_ids", [])
            candidate["company_ids"] = sorted(set(candidate["company_ids"] + [company["company_id"]]))
            if source_id in records:
                records[source_id]["company_ids"] = sorted(set(records[source_id].get("company_ids", []) + candidate["company_ids"]))
            else:
                records[source_id] = candidate
    return records


def add_fact(
    facts: list[dict[str, Any]],
    supports: dict[str, set[str]],
    *,
    company_id: str,
    domain: str,
    field: str,
    value: Any,
    unit: str | None = None,
    period: str | int | None = None,
    as_of: str | None = None,
    verification_status: str = "not_verified",
    confidence: str = "unknown",
    source_ids: list[str] | None = None,
    suffix: str | None = None,
) -> None:
    if not has_value(value):
        return
    ids = clean_ids(source_ids or [])
    parts = [company_id, domain, field]
    if period is not None:
        parts.append(str(period))
    if suffix:
        parts.append(suffix)
    fact_id = "fact-" + re.sub(r"[^0-9a-zA-Z_-]+", "-", "-".join(parts)).strip("-").lower()
    fact = {
        "fact_id": fact_id,
        "company_id": company_id,
        "domain": domain,
        "field": field,
        "value": value,
        "unit": unit,
        "period": period,
        "as_of": as_of,
        "verification_status": verification_status,
        "confidence": confidence or "unknown",
        "source_ids": ids,
        "visibility": "public",
        "updated_at": as_of or TODAY,
    }
    facts.append(fact)
    for source_id in ids:
        supports[source_id].add(fact_id)


def migrate_facts(companies: list[dict[str, Any]], supports: dict[str, set[str]]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    identity_fields = ["company_name", "company_name_en", "aliases", "headquarters", "website_url", "listed_market", "ticker"]
    for company in companies:
        company_id = company["company_id"]
        field_sources = company.get("field_sources") if isinstance(company.get("field_sources"), dict) else {}
        for field in identity_fields:
            source_ids = clean_ids(field_sources.get(field, []))
            add_fact(
                facts, supports, company_id=company_id, domain="identity", field=field,
                value=company.get(field), source_ids=source_ids, as_of=company.get("last_verified_at"),
                verification_status=verification_from_confidence(company.get("data_confidence"), source_ids),
                confidence=company.get("data_confidence") or "unknown",
            )
        for domain, field in [
            ("organization", "company_type"), ("strategy", "competitive_role"),
            ("strategy", "analysis_tier"), ("market", "target_markets"), ("market", "modular_methods"),
        ]:
            source_ids = clean_ids(field_sources.get(field, []))
            add_fact(
                facts, supports, company_id=company_id, domain=domain, field=field,
                value=company.get(field), source_ids=source_ids, as_of=company.get("last_verified_at"),
                verification_status=verification_from_confidence(company.get("data_confidence"), source_ids),
                confidence=company.get("data_confidence") or "unknown",
            )

        for financial in company.get("financials") or []:
            year = financial.get("year")
            scope = financial.get("reporting_scope") or financial.get("scope") or "unknown"
            for metric in [
                "revenue", "cost_of_sales", "gross_profit", "operating_profit", "net_income",
                "operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "total_assets",
                "current_assets", "total_liabilities", "current_liabilities", "total_equity",
            ]:
                record = financial.get(metric)
                if not isinstance(record, dict) or record.get("source_value") is None:
                    continue
                source_ids = clean_ids(record.get("source_ids") or financial.get("source_ids") or [])
                add_fact(
                    facts, supports, company_id=company_id, domain="financial", field=metric,
                    value=record.get("source_value"), unit=record.get("source_unit") or financial.get("currency"),
                    period=year, as_of=financial.get("verified_at"), source_ids=source_ids,
                    verification_status="official_verified" if source_ids else "not_verified",
                    confidence=record.get("confidence") or financial.get("confidence") or "unknown", suffix=scope,
                )

        production_summary = company.get("production_summary") if isinstance(company.get("production_summary"), dict) else {}
        for field in ["manufacturing_model", "own_facility_status", "facility_count", "official_capacity_available"]:
            add_fact(
                facts, supports, company_id=company_id, domain="production", field=field,
                value=production_summary.get(field), as_of=production_summary.get("verified_at"),
                source_ids=clean_ids(production_summary.get("source_ids")),
                verification_status=("official_verified" if production_summary.get("verification_status") == "verified" else "partially_verified" if production_summary.get("source_ids") else "unavailable"),
                confidence=production_summary.get("data_confidence") or "unknown",
            )
        for facility in company.get("production") or []:
            facility_id = facility.get("facility_id") or "facility"
            source_ids = clean_ids(facility.get("source_ids"))
            for field in [
                "facility_name", "facility_type", "modular_system_type", "ownership_type", "operator_name",
                "operation_status", "address", "region", "city", "production_scope", "production_processes",
                "line_count", "major_equipment", "site_area", "building_area", "capacity_value", "capacity_scope",
            ]:
                unit = None
                if field == "site_area":
                    unit = facility.get("site_area_unit")
                elif field == "building_area":
                    unit = facility.get("building_area_unit")
                elif field == "capacity_value":
                    unit = facility.get("capacity_unit")
                add_fact(
                    facts, supports, company_id=company_id, domain="production", field=field,
                    value=facility.get(field), unit=unit,
                    period=facility.get("capacity_period") if field == "capacity_value" else None,
                    as_of=facility.get("verified_at"), source_ids=source_ids,
                    verification_status="official_verified" if source_ids else "not_verified",
                    confidence=facility.get("data_confidence") or facility.get("confidence") or "unknown", suffix=facility_id,
                )

        technology = company.get("technology") if isinstance(company.get("technology"), dict) else {}
        for group, values in technology.items():
            if not isinstance(values, list):
                continue
            for index, record in enumerate(values):
                if not isinstance(record, dict) or not any(record.get(key) for key in ["name", "registration_number", "application_number", "technology_id"]):
                    continue
                source_ids = clean_ids(record.get("source_ids"))
                record_id = record.get("technology_id") or record.get("registration_number") or str(index)
                add_fact(
                    facts, supports, company_id=company_id, domain="technology", field=group,
                    value=record, period=record.get("registered_at"), as_of=record.get("verified_at"),
                    source_ids=source_ids,
                    verification_status="official_verified" if source_ids and record.get("registration_number") else "company_claimed" if source_ids else "not_verified",
                    confidence=record.get("confidence") or "unknown", suffix=str(record_id),
                )
    return facts


def project_event(project: dict[str, Any], company_id: str, source_records: dict[str, dict[str, Any]], supports: dict[str, set[str]]) -> dict[str, Any]:
    source_ids = clean_ids(project.get("source_ids"))
    event_status = STATUS_MAP.get(project.get("project_status"), "unconfirmed")
    role = project.get("company_role")
    has_official_source = any(source_tier(source_records.get(source_id, {}).get("source_type", "")) in {"A", "B"} for source_id in source_ids)
    project_credit = event_status in ALLOWED_PROJECT_CREDIT_STATUSES and role not in UNKNOWN_PROJECT_ROLES and has_official_source
    evidence_status = project.get("evidence_status")
    verification_status = "official_verified" if project_credit else "partially_verified" if evidence_status in {"verified", "partially_verified"} else "not_verified"
    event_id = f"event-{project.get('project_id') or stable_hash(project)[:12]}"
    event = {
        "event_id": event_id,
        "company_id": company_id,
        "event_type": "project",
        "event_status": event_status,
        "title": project.get("project_name") or "프로젝트명 미확인",
        "counterparties": sorted({value for value in [project.get("client"), project.get("client_name"), project.get("ordering_agency")] if value}),
        "client": project.get("client_name") or project.get("client") or project.get("ordering_agency"),
        "project_role": role,
        "project_credit": project_credit,
        "announced_at": None,
        "contracted_at": project.get("contract_date"),
        "started_at": project.get("construction_start_date") or project.get("start_date"),
        "completed_at": project.get("completion_date"),
        "amount": project.get("contract_amount"),
        "amount_unit": project.get("contract_amount_unit") or project.get("amount_scope"),
        "location": project.get("location"),
        "market_segment": project.get("sector") or project.get("building_use"),
        "method": project.get("structure_type") or project.get("modular_type") or project.get("modular_method"),
        "source_ids": source_ids,
        "verification_status": verification_status,
        "visibility": "public",
        "updated_at": project.get("verified_at") or TODAY,
    }
    for source_id in source_ids:
        supports[source_id].add(event_id)
    return event


def candidate_event(candidate: dict[str, Any], company_id: str, supports: dict[str, set[str]]) -> dict[str, Any]:
    candidate_id = candidate.get("project_candidate_id") or candidate.get("candidate_id") or stable_hash(candidate)[:12]
    event_id = f"event-{candidate_id}"
    source_ids = clean_ids(candidate.get("source_article_ids") or candidate.get("source_ids") or [])
    event = {
        "event_id": event_id,
        "company_id": company_id,
        "event_type": "project",
        "event_status": "unconfirmed",
        "title": candidate.get("canonical_project_name") or candidate.get("candidate_title") or "사업 후보",
        "counterparties": sorted({value for value in [candidate.get("possible_client")] if value}),
        "client": candidate.get("possible_client"),
        "project_role": candidate.get("possible_company_role") if candidate.get("possible_company_role") not in UNKNOWN_PROJECT_ROLES else None,
        "project_credit": False,
        "announced_at": candidate.get("possible_year"),
        "contracted_at": None,
        "started_at": None,
        "completed_at": None,
        "amount": None,
        "amount_unit": None,
        "location": candidate.get("possible_location"),
        "market_segment": candidate.get("possible_use_type"),
        "method": candidate.get("possible_method"),
        "source_ids": source_ids,
        "verification_status": "not_verified",
        "visibility": "public",
        "updated_at": candidate.get("research_closed_at") or TODAY,
    }
    for source_id in source_ids:
        supports[source_id].add(event_id)
    return event


def titles_overlap(signal: dict[str, Any], project: dict[str, Any]) -> bool:
    signal_text = normalize_title(" ".join(str(signal.get(key) or "") for key in ["title", "summary"]))
    names = [project.get("project_name")] + list(project.get("aliases") or [])
    return any(name and normalize_title(name) and normalize_title(name) in signal_text for name in names)


def migrate_events(
    companies: list[dict[str, Any]], source_records: dict[str, dict[str, Any]], supports: dict[str, set[str]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    duplicate_clusters: list[dict[str, Any]] = []
    for company in companies:
        company_id = company["company_id"]
        projects = company.get("project_portfolio") or []
        project_events: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for project in projects:
            event = project_event(project, company_id, source_records, supports)
            events.append(event)
            project_events.append((project, event))
        for candidate in company.get("project_candidates") or []:
            events.append(candidate_event(candidate, company_id, supports))
        for signal in company.get("recent_signals") or []:
            signal_type = signal.get("signal_type") or "other"
            source_ids = clean_ids(signal.get("source_ids"))
            matching = [(project, event) for project, event in project_events if titles_overlap(signal, project)]
            if signal_type == "project_award" and len(matching) == 1:
                _, target = matching[0]
                target["source_ids"] = sorted(set(target["source_ids"] + source_ids))
                target["announced_at"] = target["announced_at"] or signal.get("occurred_at")
                for source_id in source_ids:
                    supports[source_id].add(target["event_id"])
                duplicate_clusters.append({
                    "company_id": company_id,
                    "kept_event_id": target["event_id"],
                    "merged_signal_id": signal.get("signal_id"),
                    "reason": "same_project_signal",
                })
                continue
            event_type = SIGNAL_EVENT_TYPES.get(signal_type, "policy_signal")
            event_status = SIGNAL_EVENT_STATUSES.get(signal_type, "unconfirmed")
            event_id = f"event-{signal.get('signal_id') or stable_hash(signal)[:12]}"
            event = {
                "event_id": event_id,
                "company_id": company_id,
                "event_type": event_type,
                "event_status": event_status,
                "title": signal.get("title") or "최근 동향",
                "counterparties": [],
                "client": None,
                "project_role": None,
                "project_credit": False,
                "announced_at": signal.get("occurred_at"),
                "contracted_at": None,
                "started_at": None,
                "completed_at": None,
                "amount": None,
                "amount_unit": None,
                "location": None,
                "market_segment": None,
                "method": None,
                "source_ids": source_ids,
                "verification_status": "partially_verified" if source_ids else "not_verified",
                "visibility": "public",
                "updated_at": signal.get("verified_at") or TODAY,
            }
            events.append(event)
            for source_id in source_ids:
                supports[source_id].add(event_id)
    return events, duplicate_clusters


def apply_corrections(events: list[dict[str, Any]], corrections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {event["event_id"]: event for event in events}
    results: list[dict[str, Any]] = []
    for correction in corrections:
        target = by_id.get(correction.get("target_id"))
        applied = False
        if target and correction.get("target_type") == "event" and correction.get("action") in {"replace", "reclassify"}:
            corrected = correction.get("corrected_value")
            if isinstance(corrected, dict):
                target.update(corrected)
                applied = True
        if target and correction.get("action") == "suppress":
            target["visibility"] = "internal"
            applied = True
        results.append({
            "correction_id": correction.get("correction_id"),
            "target_id": correction.get("target_id"),
            "applied": applied,
            "reason_code": correction.get("reason_code"),
            "visibility": correction.get("visibility"),
        })
    return results


def build_evidence(
    source_records: dict[str, dict[str, Any]], events: list[dict[str, Any]], supports: dict[str, set[str]]
) -> list[dict[str, Any]]:
    article_ids = {
        source_id
        for event in events
        for source_id in event.get("source_ids", [])
        if source_id.startswith("article-")
    }
    evidence: list[dict[str, Any]] = []
    for source_id in sorted(set(source_records) | article_ids):
        source = source_records.get(source_id, {})
        is_article = source_id in article_ids and not source
        url = source.get("source_url")
        if url and ".cache" in str(url):
            url = None
        source_type = source.get("source_type") or ("media_article" if is_article else "unknown")
        company_supports = {f"company:{company_id}" for company_id in source.get("company_ids", [])}
        evidence.append({
            "source_id": source_id,
            "source_type": source_type,
            "source_tier": source_tier(source_type),
            "publisher": source.get("publisher") or source.get("source_name"),
            "title": source.get("title") or ("관련 기사 근거" if is_article else source.get("source_name")),
            "url": url,
            "published_at": source.get("published_at"),
            "retrieved_at": source.get("accessed_at"),
            "document_id": source.get("document_number") or source.get("receipt_number"),
            "document_hash": stable_hash([source_id, url, source.get("title")]),
            "excerpt": None,
            "supports": sorted(set(supports.get(source_id, set())) | company_supports),
            "contradicts": [],
            "visibility": "public",
            "stale_after": None,
            "status": source.get("source_status") or "active",
        })
    return evidence


def domain_statuses(company: dict[str, Any], facts: list[dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, str]:
    company_id = company["company_id"]
    own_facts = [fact for fact in facts if fact["company_id"] == company_id]
    own_events = [event for event in events if event["company_id"] == company_id]
    identity = "official_verified" if company.get("dart_identity", {}).get("identity_status") == "confirmed" else "partially_verified" if company.get("sources") else "internally_confirmed"
    years = {fact.get("period") for fact in own_facts if fact["domain"] == "financial" and fact["field"] == "revenue" and fact["source_ids"]}
    financial = "official_verified" if len(years) >= 3 else "partially_verified" if years else "unavailable"
    production_summary = company.get("production_summary") if isinstance(company.get("production_summary"), dict) else {}
    if production_summary.get("verification_status") == "verified":
        production = "official_verified"
    elif company.get("production"):
        production = "partially_verified"
    elif production_summary.get("verification_status") in {"research_exhausted", "not_applicable"}:
        production = "unavailable"
    else:
        production = "not_verified"
    project_events = [event for event in own_events if event["event_type"] == "project"]
    if any(event["project_credit"] for event in project_events):
        project = "official_verified"
    elif any(event["verification_status"] == "partially_verified" for event in project_events):
        project = "partially_verified"
    elif project_events:
        project = "not_verified"
    else:
        project = "unavailable"
    tech_facts = [fact for fact in own_facts if fact["domain"] == "technology"]
    if any(fact["verification_status"] == "official_verified" for fact in tech_facts):
        technology = "official_verified"
    elif any(fact["verification_status"] == "company_claimed" for fact in tech_facts):
        technology = "company_claimed"
    elif tech_facts:
        technology = "not_verified"
    else:
        technology = "unavailable"
    signal_events = [event for event in own_events if event["event_type"] != "project"]
    if any(event["verification_status"] in {"official_verified", "cross_verified"} for event in signal_events):
        recent = "official_verified"
    elif any(event["verification_status"] == "partially_verified" for event in signal_events):
        recent = "partially_verified"
    elif signal_events:
        recent = "not_verified"
    else:
        recent = "unavailable"
    return {
        "identity_status": identity,
        "financial_status": financial,
        "production_status": production,
        "project_status": project,
        "technology_status": technology,
        "recent_signal_status": recent,
    }


def overall_status(company: dict[str, Any], statuses: dict[str, str]) -> str:
    if company.get("competitive_role") == "watchlist":
        return "watchlist"
    strong = {"official_verified", "cross_verified"}
    supported = strong | {"partially_verified", "company_claimed", "third_party_reported"}
    core_ok = statuses["identity_status"] in strong and statuses["financial_status"] in strong
    supporting_count = sum(statuses[key] in supported for key in ["production_status", "project_status", "technology_status", "recent_signal_status"])
    if core_ok and supporting_count >= 2:
        return "core_verified"
    if core_ok or sum(value in supported for value in statuses.values()) >= 2:
        return "partially_verified"
    if company.get("sources") or company.get("research_gaps"):
        return "research_in_progress"
    return "insufficient_public_data"


def source_group(source_type: str) -> str:
    tier = source_tier(source_type)
    if source_type in {"regulatory_filing", "audit_report"}:
        return "dart"
    if tier == "B":
        return "company_official"
    if tier == "A":
        return "public_official"
    if tier == "C":
        return "media_and_research"
    return "other"


def materialized_summaries(
    companies: list[dict[str, Any]], facts: list[dict[str, Any]], events: list[dict[str, Any]], evidence: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    evidence_by_id = {item["source_id"]: item for item in evidence}
    summaries: list[dict[str, Any]] = []
    for company in companies:
        company_id = company["company_id"]
        statuses = domain_statuses(company, facts, events)
        own_events = [event for event in events if event["company_id"] == company_id]
        event_counts = Counter()
        for event in own_events:
            if event["event_type"] == "project" and event["project_credit"]:
                event_counts["verified_projects"] += 1
            elif event["event_type"] == "project":
                event_counts["project_candidates"] += 1
            elif event["event_type"] in {"partnership", "mou"}:
                event_counts["partnerships_mou"] += 1
            elif event["event_type"] in {"r_and_d", "exhibition"}:
                event_counts["r_and_d_exhibition"] += 1
            else:
                event_counts["other_events"] += 1
        source_ids = {source_id for event in own_events for source_id in event.get("source_ids", [])}
        source_ids.update(fact_source for fact in facts if fact["company_id"] == company_id for fact_source in fact["source_ids"])
        groups = Counter(source_group(evidence_by_id[source_id]["source_type"]) for source_id in source_ids if source_id in evidence_by_id)
        summaries.append({
            "company_id": company_id,
            "overall_data_status": overall_status(company, statuses),
            "domain_statuses": statuses,
            "event_counts": {
                "verified_projects": event_counts["verified_projects"],
                "project_candidates": event_counts["project_candidates"],
                "partnerships_mou": event_counts["partnerships_mou"],
                "r_and_d_exhibition": event_counts["r_and_d_exhibition"],
                "other_events": event_counts["other_events"],
            },
            "article_evidence_count": sum(1 for source_id in source_ids if evidence_by_id.get(source_id, {}).get("source_type") == "media_article"),
            "source_group_counts": dict(sorted(groups.items())),
            "updated_at": company.get("last_verified_at") or TODAY,
        })
    return summaries


def build_v2_dataset(companies_path: Path = DEFAULT_COMPANIES) -> dict[str, Any]:
    legacy = read_json(companies_path)
    companies = legacy.get("companies", [])
    supports: dict[str, set[str]] = defaultdict(set)
    source_records = collect_source_records(companies)
    facts = migrate_facts(companies, supports)
    events, duplicate_clusters = migrate_events(companies, source_records, supports)
    public_corrections, private_corrections = load_corrections()
    correction_results = apply_corrections(events, public_corrections + private_corrections)
    evidence = build_evidence(source_records, events, supports)
    summaries = materialized_summaries(companies, facts, events, evidence)
    source_hashes = {name: sha256_file(path) for name, path in PROTECTED_PUBLIC_FILES.items()}
    source_hashes["companies.json"] = sha256_file(companies_path)
    if DEFAULT_OUTPUT.exists():
        previous_hashes = read_json(DEFAULT_OUTPUT).get("audit_metadata", {}).get("source_hashes")
        if isinstance(previous_hashes, dict):
            source_hashes = previous_hashes
    return {
        "schema_version": "2.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "companies": [
            {
                "company_id": company["company_id"],
                "company_name": company["company_name"],
                "company_type": company["company_type"],
                "competitive_role": company["competitive_role"],
                "analysis_tier": company["analysis_tier"],
                "visibility": "public",
            }
            for company in companies
        ],
        "facts": facts,
        "events": events,
        "evidence": evidence,
        "corrections": [correction for correction in public_corrections if correction.get("visibility") == "public"],
        "materialized_summaries": summaries,
        "audit_metadata": {
            "legacy_schema_version": legacy.get("schema_version"),
            "source_hashes": source_hashes,
            "protected_company_hashes": {company["company_id"]: protected_hash(company) for company in companies},
            "duplicate_event_clusters": duplicate_clusters,
            "correction_application_results": correction_results,
            "private_correction_count": len(private_corrections),
            "count_definitions": {
                "project_count": "events where event_type=project and project_credit=true",
                "project_candidate_count": "events where event_type=project and project_credit=false",
                "article_evidence_count": "distinct media_article evidence records; never added to project_count",
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--companies", type=Path, default=DEFAULT_COMPANIES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    payload = build_v2_dataset(args.companies)
    if not args.dry_run:
        write_json(args.output, payload)
    print(json.dumps({
        "status": "PASS",
        "companies": len(payload["companies"]),
        "facts": len(payload["facts"]),
        "events": len(payload["events"]),
        "evidence": len(payload["evidence"]),
        "corrections": len(payload["corrections"]),
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
