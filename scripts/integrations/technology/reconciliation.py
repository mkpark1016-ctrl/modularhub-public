from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import json
import re
from typing import Any, Iterable

from scripts.integrations.business.base import clean_text
from scripts.integrations.technology.adapters import adapter_for_source
from scripts.integrations.technology.base import NormalizedTechnologyRecord, normalize_official_number
from scripts.integrations.technology.matching import CompanyIdentity, CompanyMatch, company_identities, match_companies
from scripts.integrations.technology.relevance import RelevanceDecision, assess_modular_relevance


ENRICHABLE_FIELDS = (
    "application_number",
    "registration_number",
    "patent_number",
    "newtech_number",
    "application_date",
    "registration_date",
    "designation_date",
    "expiration_date",
    "status",
    "technology_area",
)
CRITICAL_FIELDS = (
    "title",
    "applicants",
    "owners",
    "developers",
    "application_number",
    "registration_number",
    "patent_number",
    "newtech_number",
    "status",
)


@dataclass(frozen=True)
class NormalizationResult:
    records: tuple[NormalizedTechnologyRecord, ...]
    source_input_count: int
    duplicate_identity_count: int
    invalid: tuple[dict[str, Any], ...]
    identity_conflicts: tuple[dict[str, Any], ...]
    credential_exposure_count: int


@dataclass(frozen=True)
class BaselineTechnologyRecord:
    company_id: str
    record: dict[str, Any]
    identity_aliases: tuple[str, ...]


def normalize_fixture_records(raw_records: Iterable[dict[str, Any]]) -> NormalizationResult:
    grouped: dict[str, list[NormalizedTechnologyRecord]] = defaultdict(list)
    invalid = []
    credential_exposure_count = 0
    source_input_count = 0
    for index, raw in enumerate(raw_records):
        source_input_count += 1
        try:
            if not isinstance(raw, dict):
                raise ValueError("source record must be an object")
            source = str(raw.get("source") or "")
            record = adapter_for_source(source).normalize_raw_record(raw)
            grouped[record.identity_key()].append(record)
        except (TypeError, ValueError) as exc:
            message = str(exc)
            if any(term in message for term in ("credential", "sensitive", "source_url")):
                credential_exposure_count += 1
            invalid.append({"index": index, "error": _sanitized_error(message)})

    records = []
    duplicate_identity_count = 0
    conflicts = []
    for identity in sorted(grouped):
        candidates = grouped[identity]
        signatures = {_critical_signature(record) for record in candidates}
        winner = min(candidates, key=_canonical_record_json)
        records.append(winner)
        duplicate_identity_count += len(candidates) - 1
        if len(signatures) > 1:
            conflicts.append({
                "identity": identity,
                "candidate_count": len(candidates),
                "differing_fields": _differing_fields(candidates),
            })

    return NormalizationResult(
        records=tuple(sorted(records, key=lambda record: (record.record_type, record.identity_key(), record.source))),
        source_input_count=source_input_count,
        duplicate_identity_count=duplicate_identity_count,
        invalid=tuple(invalid),
        identity_conflicts=tuple(conflicts),
        credential_exposure_count=credential_exposure_count,
    )


def baseline_technology_records(companies: Iterable[dict[str, Any]]) -> list[BaselineTechnologyRecord]:
    baseline = []
    for company in companies:
        company_id = clean_text(company.get("company_id") or company.get("id"))
        if not company_id:
            continue
        technology = company.get("technology") or {}
        for collection in sorted(technology):
            values = technology.get(collection)
            if not isinstance(values, list):
                continue
            for record in values:
                if not isinstance(record, dict):
                    continue
                aliases = baseline_identity_aliases(record)
                if aliases:
                    baseline.append(BaselineTechnologyRecord(company_id, record, aliases))
    return sorted(baseline, key=lambda item: (item.company_id, item.identity_aliases, str(item.record.get("technology_id") or "")))


def baseline_identity_aliases(record: dict[str, Any]) -> tuple[str, ...]:
    record_type = clean_text(record.get("record_type")) or "patent"
    if record_type == "construction_new_technology":
        values = (record.get("newtech_number"), record.get("registration_number"))
    else:
        values = (record.get("application_number"), record.get("registration_number"), record.get("patent_number"))
    return tuple(
        dict.fromkeys(
            f"{record_type}:{number}"
            for number in (normalize_official_number(value) for value in values)
            if number
        )
    )


def reconcile_technology_records(
    companies: Iterable[dict[str, Any]],
    normalization: NormalizationResult,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    company_rows = list(companies)
    identities = company_identities(company_rows)
    baseline = baseline_technology_records(company_rows)
    baseline_by_alias: dict[str, list[BaselineTechnologyRecord]] = defaultdict(list)
    for item in baseline:
        for alias in item.identity_aliases:
            baseline_by_alias[alias].append(item)

    conflicts = list(normalization.identity_conflicts)
    conflict_identities = {item["identity"] for item in normalization.identity_conflicts}
    decisions = []
    candidates = []
    matched_baseline_keys: set[tuple[str, str]] = set()
    match_counts: Counter[str] = Counter()
    relevance_counts: Counter[str] = Counter()
    existing_matched = 0
    net_new = 0

    for record in normalization.records:
        company_match = match_companies(record, identities)
        relevance = assess_modular_relevance(record)
        match_counts[company_match.outcome] += 1
        relevance_counts[relevance.level] += 1
        decision = {
            "identity": record.identity_key(),
            "source": record.source,
            "external_id": record.external_id,
            "title": record.title,
            "company_match": company_match.as_dict(),
            "relevance": relevance.as_dict(),
            "category": "unmatched",
        }

        if record.identity_key() in conflict_identities:
            decision["category"] = "conflict"
            decisions.append(decision)
            continue
        if company_match.outcome == "ambiguous":
            decision["category"] = "ambiguous"
            decisions.append(decision)
            continue
        if company_match.outcome == "unmatched":
            decisions.append(decision)
            continue

        existing_matches = _matching_baselines(record, company_match, baseline_by_alias)
        if len(existing_matches) > 1:
            decision["category"] = "conflict"
            decision["conflicting_fields"] = ["baseline_identity_collision"]
            conflicts.append({
                "identity": record.identity_key(),
                "differing_fields": ["baseline_identity_collision"],
                "baseline_technology_ids": sorted(
                    str(item.record.get("technology_id") or "") for item in existing_matches
                ),
            })
            decisions.append(decision)
            continue
        if existing_matches:
            existing = existing_matches[0]
            baseline_conflict = _baseline_conflict(record, existing)
            if baseline_conflict:
                decision["category"] = "conflict"
                decision["conflicting_fields"] = baseline_conflict
                conflicts.append({"identity": record.identity_key(), "differing_fields": baseline_conflict})
            else:
                decision["category"] = "matched"
                existing_matched += 1
                enrichment = _enrichment_fields(record, existing.record)
                decision["baseline_technology_id"] = existing.record.get("technology_id")
                decision["enrichment_fields"] = enrichment
                matched_baseline_keys.add((existing.company_id, str(existing.record.get("technology_id") or existing.identity_aliases[0])))
                if enrichment:
                    candidates.append(_candidate(record, company_match, relevance, "enrichment_candidate", enrichment))
            decisions.append(decision)
            continue

        if relevance.level in {"direct", "adjacent"}:
            decision["category"] = "net_new"
            net_new += 1
            candidates.append(_candidate(record, company_match, relevance, "net_new", {}))
        else:
            decision["category"] = "irrelevant"
        decisions.append(decision)

    manual_only = []
    for item in baseline:
        key = (item.company_id, str(item.record.get("technology_id") or item.identity_aliases[0]))
        if key not in matched_baseline_keys:
            manual_only.append({
                "company_id": item.company_id,
                "technology_id": item.record.get("technology_id"),
                "identity_aliases": list(item.identity_aliases),
                "title": item.record.get("name"),
                "category": "manual_only",
            })

    candidates.sort(key=lambda item: (item["company_ids"], item["record_type"], item["official_identity"]))
    decisions.sort(key=lambda item: (item["identity"], item["source"], item["external_id"]))
    manual_only.sort(key=lambda item: (item["company_id"], str(item["technology_id"] or "")))
    report = {
        "schema_version": "company-technology-reconciliation-v1",
        "baseline_count": len(baseline),
        "source_input_count": normalization.source_input_count,
        "normalized_count": len(normalization.records),
        "company_matched_count": match_counts["exact"] + match_counts["normalized_alias"],
        "ambiguous_company_count": match_counts["ambiguous"],
        "unmatched_company_count": match_counts["unmatched"],
        "modular_direct_count": relevance_counts["direct"],
        "modular_adjacent_count": relevance_counts["adjacent"],
        "irrelevant_count": relevance_counts["irrelevant"],
        "existing_matched_count": existing_matched,
        "manual_only_count": len(manual_only),
        "net_new_count": net_new,
        "conflict_count": len(conflicts),
        "duplicate_identity_count": normalization.duplicate_identity_count,
        "invalid_count": len(normalization.invalid),
        "credential_exposure_count": normalization.credential_exposure_count,
        "public_candidate_count": len(candidates),
        "public_write_performed": False,
        "manual_baseline_preserved": True,
        "identity_uses_title": False,
        "decisions": decisions,
        "manual_only": manual_only,
        "conflicts": sorted(conflicts, key=lambda item: str(item.get("identity") or "")),
        "invalid": list(normalization.invalid),
    }
    return candidates, report


def _matching_baselines(
    record: NormalizedTechnologyRecord,
    company_match: CompanyMatch,
    baseline_by_alias: dict[str, list[BaselineTechnologyRecord]],
) -> list[BaselineTechnologyRecord]:
    candidates = {
        (item.company_id, str(item.record.get("technology_id") or item.identity_aliases[0])): item
        for alias in record.identity_aliases()
        for item in baseline_by_alias.get(alias, [])
        if item.company_id in company_match.company_ids
    }
    return [candidates[key] for key in sorted(candidates)]


def _baseline_conflict(record: NormalizedTechnologyRecord, baseline: BaselineTechnologyRecord) -> list[str]:
    conflicts = []
    baseline_title = _normalize_text(baseline.record.get("name"))
    if baseline_title and baseline_title != _normalize_text(record.title):
        conflicts.append("title")
    baseline_status = clean_text(baseline.record.get("status"))
    if baseline_status and record.status and baseline_status.casefold() != record.status.casefold():
        conflicts.append("status")
    return conflicts


def _enrichment_fields(record: NormalizedTechnologyRecord, baseline: dict[str, Any]) -> dict[str, Any]:
    official = record.as_dict()
    enrichment = {}
    for field in ENRICHABLE_FIELDS:
        value = official.get(field)
        if value not in (None, "", [], ()) and baseline.get(field) in (None, "", [], ()):
            enrichment[field] = value
    return enrichment


def _candidate(
    record: NormalizedTechnologyRecord,
    company_match: CompanyMatch,
    relevance: RelevanceDecision,
    category: str,
    enrichment: dict[str, Any],
) -> dict[str, Any]:
    return {
        "candidate_type": category,
        "official_identity": record.identity_key(),
        "company_ids": list(company_match.company_ids),
        "source": record.source,
        "source_record_type": record.record_type,
        "external_id": record.external_id,
        "name": record.title,
        "record_type": record.record_type,
        "application_number": record.application_number,
        "registration_number": record.registration_number,
        "patent_number": record.patent_number,
        "newtech_number": record.newtech_number,
        "status": record.status,
        "technology_area": relevance.technology_area,
        "application_date": record.application_date,
        "registration_date": record.registration_date,
        "designation_date": record.designation_date,
        "expiration_date": record.expiration_date,
        "summary": record.abstract,
        "source_url": record.source_url,
        "source_ids": [f"official:{record.source}:{record.external_id}"],
        "company_match": company_match.outcome,
        "modular_relevance": relevance.level,
        "matched_terms": list(relevance.matched_terms),
        "relevance_reason": relevance.relevance_reason,
        "enrichment_fields": enrichment,
    }


def _critical_signature(record: NormalizedTechnologyRecord) -> str:
    values = {field: getattr(record, field) for field in CRITICAL_FIELDS}
    return json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _differing_fields(records: list[NormalizedTechnologyRecord]) -> list[str]:
    return [
        field
        for field in CRITICAL_FIELDS
        if len({_stable_value(getattr(record, field)) for record in records}) > 1
    ]


def _canonical_record_json(record: NormalizedTechnologyRecord) -> str:
    payload = record.as_dict().copy()
    payload.pop("external_id", None)
    payload.pop("collected_at", None)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _stable_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_text(value: Any) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(value or "").casefold())


def _sanitized_error(message: str) -> str:
    return re.sub(r"(?i)(accesskey|apikey|api_key|authorization|servicekey)=?[^\s&,]*", r"\1=<redacted>", message)
