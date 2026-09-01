from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from scripts.integrations.business.base import clean_text
from scripts.integrations.technology.base import normalize_official_number
from scripts.integrations.technology.matching import (
    CompanyIdentity,
    normalize_company_name,
)


READY_EXACT_IDENTITY = "READY_EXACT_IDENTITY"
READY_VERIFIED_REGISTRATION_IDENTITY = "READY_VERIFIED_REGISTRATION_IDENTITY"
NEEDS_EXACT_LOOKUP = "NEEDS_EXACT_LOOKUP"
IDENTITY_INSUFFICIENT = "IDENTITY_INSUFFICIENT"
KAIA_MANUAL_BASELINE = "KAIA_MANUAL_BASELINE"

READINESS_DECISIONS = frozenset({
    READY_EXACT_IDENTITY,
    READY_VERIFIED_REGISTRATION_IDENTITY,
    NEEDS_EXACT_LOOKUP,
    IDENTITY_INSUFFICIENT,
    KAIA_MANUAL_BASELINE,
})

COLLECTION_COMPLETENESS = "completeness"
COLLECTION_FALLBACK_DISCOVERY = "fallback_discovery"
COLLECTION_DISABLED = "disabled"
COLLECTION_MODES = frozenset({
    COLLECTION_COMPLETENESS,
    COLLECTION_FALLBACK_DISCOVERY,
    COLLECTION_DISABLED,
})


@dataclass(frozen=True)
class AliasDecision:
    allowed: bool
    category: str
    matched_value: str | None = None
    collection_mode: str | None = None


def _approved_alias_collection_mode(entry: dict[str, Any]) -> str:
    explicit_mode = entry.get("collection_mode")
    if explicit_mode is None:
        return COLLECTION_COMPLETENESS if entry.get("live_enabled", True) else COLLECTION_DISABLED
    mode = str(explicit_mode)
    if mode not in COLLECTION_MODES:
        raise ValueError(f"unsupported approved-alias collection_mode={mode!r}")
    return mode


def classify_baseline_identity(record: dict[str, Any]) -> str:
    if record.get("record_type") == "construction_new_technology":
        return KAIA_MANUAL_BASELINE
    if _valid_application_number(record.get("application_number")):
        return READY_EXACT_IDENTITY
    if _valid_registration_number(record.get("registration_number")) or normalize_official_number(
        record.get("patent_number")
    ):
        return READY_VERIFIED_REGISTRATION_IDENTITY
    if any(record.get(field) for field in ("application_number", "registration_number", "patent_number")):
        return NEEDS_EXACT_LOOKUP
    return IDENTITY_INSUFFICIENT


def inventory_company(company: dict[str, Any]) -> dict[str, Any]:
    records = _technology_records(company)
    title_groups: dict[str, list[str]] = defaultdict(list)
    identity_groups: dict[str, list[str]] = defaultdict(list)
    readiness = Counter()
    rows = []
    for record in records:
        decision = classify_baseline_identity(record)
        readiness[decision] += 1
        technology_id = str(record.get("technology_id") or "")
        title = clean_text(record.get("name") or record.get("title")) or ""
        title_groups[_normalized_title(title)].append(technology_id)
        identity = _official_identity(record)
        if identity:
            identity_groups[identity].append(technology_id)
        rows.append({
            "technology_id": technology_id,
            "title": title,
            "record_type": record.get("record_type"),
            "registration_number": record.get("registration_number"),
            "application_number": record.get("application_number"),
            "patent_number": record.get("patent_number"),
            "status": record.get("status"),
            "technology_area": record.get("technology_area"),
            "application_date": record.get("application_date") or record.get("filed_at"),
            "registration_date": record.get("registration_date") or record.get("registered_at"),
            "source_ids": list(record.get("source_ids") or []),
            "identity_readiness": decision,
        })

    patents = [row for row in rows if row["record_type"] == "patent"]
    newtech = [row for row in rows if row["record_type"] == "construction_new_technology"]
    return {
        "company_id": company.get("company_id"),
        "company_name": company.get("company_name"),
        "company_type": company.get("company_type"),
        "aliases": list(company.get("aliases") or []),
        "total_technology_count": len(rows),
        "patent_count": len(patents),
        "construction_new_technology_count": len(newtech),
        "application_number_present_count": sum(bool(row["application_number"]) for row in rows),
        "registration_number_present_count": sum(bool(row["registration_number"]) for row in rows),
        "patent_number_present_count": sum(bool(row["patent_number"]) for row in rows),
        "records_without_official_identifier": sum(not _official_identity(row) for row in rows),
        "duplicate_title_count": sum(1 for ids in title_groups.values() if len(ids) > 1),
        "duplicate_official_identity_count": sum(1 for ids in identity_groups.values() if len(ids) > 1),
        "readiness_counts": {decision: readiness[decision] for decision in sorted(READINESS_DECISIONS)},
        "records": rows,
    }


def company_identity_for_alias_contract(
    company: dict[str, Any],
    contract: dict[str, Any],
    *,
    include_historical: bool = False,
) -> CompanyIdentity:
    aliases = [
        entry["value"]
        for entry in contract.get("approved_aliases", [])
        if _approved_alias_collection_mode(entry) != COLLECTION_DISABLED
    ]
    if include_historical:
        aliases.extend(entry["value"] for entry in contract.get("historical_alias_candidates", []))
    return CompanyIdentity(
        str(company["company_id"]),
        (str(contract["canonical_applicant"]),),
        tuple(dict.fromkeys(aliases)),
    )


def alias_decision(contract: dict[str, Any], value: str, *, allow_historical: bool = False) -> AliasDecision:
    normalized = normalize_company_name(value)
    for category, field in (
        ("ambiguous", "ambiguous_aliases"),
        ("excluded", "excluded_aliases"),
    ):
        for entry in contract.get(field, []):
            if normalize_company_name(entry["value"]) == normalized:
                return AliasDecision(False, category, entry["value"])
    for entry in contract.get("approved_aliases", []):
        if normalize_company_name(entry["value"]) == normalized:
            collection_mode = _approved_alias_collection_mode(entry)
            return AliasDecision(
                collection_mode != COLLECTION_DISABLED,
                f"approved_{collection_mode}",
                entry["value"],
                collection_mode,
            )
    for entry in contract.get("historical_alias_candidates", []):
        if normalize_company_name(entry["value"]) == normalized:
            return AliasDecision(allow_historical, "historical_explicit_only", entry["value"])
    return AliasDecision(False, "unapproved")


def validate_alias_contracts(contracts: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    approved: dict[str, list[tuple[str, str]]] = defaultdict(list)
    historical: dict[str, list[tuple[str, str]]] = defaultdict(list)
    invalid = []
    for contract in contracts:
        company_id = str(contract.get("company_id") or "")
        rejected = {
            normalize_company_name(entry["value"])
            for field in ("ambiguous_aliases", "excluded_aliases")
            for entry in contract.get(field, [])
        }
        for entry in contract.get("approved_aliases", []):
            normalized = normalize_company_name(entry["value"])
            approved[normalized].append((company_id, entry["value"]))
            if normalized in rejected:
                invalid.append({"company_id": company_id, "alias": entry["value"], "reason": "approved_and_rejected"})
            try:
                _approved_alias_collection_mode(entry)
            except ValueError:
                invalid.append({
                    "company_id": company_id,
                    "alias": entry["value"],
                    "reason": "invalid_collection_mode",
                })
        for entry in contract.get("historical_alias_candidates", []):
            historical[normalize_company_name(entry["value"])].append((company_id, entry["value"]))
    return {
        "approved_collisions": _cross_company_alias_collisions(approved),
        "historical_collisions": _cross_company_alias_collisions(historical),
        "invalid_entries": invalid,
    }


def build_live_request_plan(
    contract: dict[str, Any],
    defaults: dict[str, Any],
    *,
    include_fallback: bool = False,
) -> dict[str, Any]:
    aliases = sorted(
        (
            entry
            for entry in contract.get("approved_aliases", [])
            if _approved_alias_collection_mode(entry) == COLLECTION_COMPLETENESS
            or (
                include_fallback
                and _approved_alias_collection_mode(entry) == COLLECTION_FALLBACK_DISCOVERY
            )
        ),
        key=lambda entry: (int(entry.get("order", 999)), entry["value"]),
    )
    page_size = int(defaults["page_size"])
    max_pages = int(defaults["max_pages_per_alias"])
    max_records = int(defaults["max_records"])
    return {
        "company_id": contract["company_id"],
        "planned_alias_order": [entry["value"] for entry in aliases],
        "maximum_pages_per_alias": max_pages,
        "page_size": page_size,
        "maximum_records": min(max_records, len(aliases) * max_pages * page_size),
        "maximum_requests": len(aliases) * max_pages,
    }


def build_exact_lookup_budget(company: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        record for record in _technology_records(company)
        if record.get("record_type") == "patent" and classify_baseline_identity(record) == NEEDS_EXACT_LOOKUP
    ]
    return {
        "company_id": company["company_id"],
        "exact_lookup_candidate_count": len(candidates),
        "maximum_exact_lookup_requests": len(candidates),
        "technology_ids": [record.get("technology_id") for record in candidates],
    }


def official_identity_collisions(companies: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    identities: dict[str, list[dict[str, str]]] = defaultdict(list)
    for company in companies:
        for record in _technology_records(company):
            if record.get("record_type") != "patent":
                continue
            identity = _official_identity(record)
            if identity:
                identities[identity].append({
                    "company_id": str(company.get("company_id")),
                    "technology_id": str(record.get("technology_id")),
                })
    return [
        {"official_identity": identity, "records": records}
        for identity, records in sorted(identities.items())
        if len({record["company_id"] for record in records}) > 1
    ]


def _technology_records(company: dict[str, Any]) -> list[dict[str, Any]]:
    technology = company.get("technology") or {}
    records = []
    for field in ("patents", "new_construction_technologies"):
        records.extend(record for record in technology.get(field, []) if isinstance(record, dict))
    return sorted(records, key=lambda record: str(record.get("technology_id") or ""))


def _valid_application_number(value: Any) -> bool:
    normalized = normalize_official_number(value)
    return bool(normalized and len(normalized) == 13)


def _valid_registration_number(value: Any) -> bool:
    normalized = normalize_official_number(value)
    return bool(normalized and len(normalized) in {9, 13})


def _official_identity(record: dict[str, Any]) -> str | None:
    for field in ("application_number", "registration_number", "patent_number"):
        normalized = normalize_official_number(record.get(field))
        if normalized:
            return f"{field}:{normalized}"
    return None


def _normalized_title(value: str) -> str:
    return normalize_company_name(value)


def _cross_company_alias_collisions(values: dict[str, list[tuple[str, str]]]) -> list[dict[str, Any]]:
    return [
        {"normalized_alias": normalized, "companies": sorted({company for company, _ in rows}), "aliases": sorted({alias for _, alias in rows})}
        for normalized, rows in sorted(values.items())
        if len({company for company, _ in rows}) > 1
    ]
