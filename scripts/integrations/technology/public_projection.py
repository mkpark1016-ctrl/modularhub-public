from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlsplit

from scripts.integrations.technology.base import (
    SENSITIVE_QUERY_KEYS,
    normalize_official_number,
    validate_public_source_url,
)
from scripts.integrations.technology.dry_run import load_companies
from scripts.integrations.technology.live_acceptance import (
    PROTECTED_PUBLIC_FILES,
    hash_files,
    security_metrics,
)
from scripts.integrations.technology.live_sources import KIPRIS_SOURCE_URL
from scripts.integrations.technology.reconciliation import baseline_identity_aliases


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_COMPANIES = ROOT / "frontend/public/data/companies/companies.json"
DEFAULT_EXACT_REPORT = (
    ROOT / "artifacts/company-technology/samsung-baseline-exact/baseline_match_report.json"
)
DEFAULT_EXACT_SUMMARY = ROOT / "artifacts/company-technology/samsung-baseline-exact/summary.json"
DEFAULT_STATUS_REPORT = (
    ROOT / "artifacts/company-technology/samsung-status-adjudication/status_adjudication_report.json"
)
DEFAULT_STATUS_SUMMARY = ROOT / "artifacts/company-technology/samsung-status-adjudication/summary.json"
DEFAULT_APPLICANT_CANDIDATES = (
    ROOT
    / "artifacts/company-technology/samsung-live/credentialed-acceptance/public_projection_candidates.json"
)
DEFAULT_APPLICANT_SUMMARY = (
    ROOT
    / "artifacts/company-technology/samsung-live/credentialed-acceptance/live_acceptance_summary.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "artifacts/company-technology/samsung-public-projection"
DEFAULT_COMPANY_ID = "samsung-ct-construction"

ALLOWED_ENRICHMENT_FIELDS = (
    "application_number",
    "patent_number",
    "application_date",
    "registration_date",
)
PUBLIC_TECHNOLOGY_FIELDS = (
    "technology_id",
    "name",
    "record_type",
    "registration_number",
    "application_number",
    "patent_number",
    "status",
    "technology_area",
    "application_date",
    "registration_date",
    "summary",
    "source_ids",
)
ACCEPTED_APPLICANT_DECISIONS = frozenset({
    "KIPRIS_LIVE_ACCEPTANCE_COMPLETE",
    "PARTIAL_SOURCE_ACCEPTANCE_KIPRIS_COMPLETE",
})


class ProjectionInputError(ValueError):
    pass


@dataclass(frozen=True)
class CompanyProjectionPolicy:
    company_id: str
    allowed_new_record_types: tuple[str, ...] = ("patent",)
    allowed_new_statuses: tuple[str, ...] = ("registered",)
    allowed_enrichment_fields: tuple[str, ...] = ALLOWED_ENRICHMENT_FIELDS
    allow_status_updates: bool = False
    published_application_policy: str = "review_only"
    technology_id_namespace: str | None = None
    schema_version: str = "company-technology-public-projection-v1"

    def __post_init__(self) -> None:
        if not self.company_id:
            raise ProjectionInputError("projection policy requires company_id")
        if self.published_application_policy not in {"review_only", "filter"}:
            raise ProjectionInputError("unsupported published application policy")


def build_company_public_projection(
    *,
    companies: Iterable[dict[str, Any]],
    exact_reports: Iterable[dict[str, Any]],
    status_reports: Iterable[dict[str, Any]],
    applicant_candidates: Iterable[dict[str, Any]],
    applicant_summary: dict[str, Any],
    policy: CompanyProjectionPolicy,
) -> dict[str, Any]:
    company_id = policy.company_id
    company_matches = [row for row in companies if row.get("company_id") == company_id]
    if len(company_matches) != 1:
        raise ProjectionInputError(f"company must resolve exactly once: {company_id}")
    company = company_matches[0]
    technology = company.get("technology") or {}
    newtech = deepcopy(list(technology.get("new_construction_technologies") or []))
    patents = deepcopy(list(technology.get("patents") or []))
    baseline = [*newtech, *patents]
    exact_by_id = _unique_by(exact_reports, "baseline_technology_id", "exact identity report")
    status_by_id = _unique_by(status_reports, "technology_id", "status adjudication report")
    projected_existing = []
    existing_diff = []
    conflict_count = 0
    enriched_existing_ids: set[str] = set()
    status_updated_ids: set[str] = set()

    for before in baseline:
        after = deepcopy(before)
        technology_id = str(before.get("technology_id") or "")
        field_changes = []
        conflicts = []
        evidence = []

        if before.get("record_type") == "patent":
            exact = exact_by_id.get(technology_id)
            if exact is None:
                conflicts.append("missing_exact_identity_evidence")
            else:
                evidence.append(_exact_evidence(exact))
                _apply_enrichment(
                    before,
                    after,
                    exact,
                    field_changes,
                    conflicts,
                    policy.allowed_enrichment_fields,
                )
                adjudication = status_by_id.get(technology_id)
                if policy.allow_status_updates:
                    _apply_status_update(before, after, exact, adjudication, field_changes, conflicts)
                elif set(exact.get("conflict_fields") or []) - {"status"}:
                    conflicts.extend(
                        f"exact_identity_conflict:{field}"
                        for field in sorted(set(exact.get("conflict_fields") or []) - {"status"})
                    )
                if adjudication:
                    evidence.append(_status_evidence(adjudication))

        if conflicts:
            after = deepcopy(before)
            field_changes = []
            classification = "CONFLICT"
            conflict_count += 1
        elif any(change["change_type"] == "STATUS_UPDATE" for change in field_changes):
            classification = "STATUS_UPDATE"
            status_updated_ids.add(technology_id)
        elif field_changes:
            classification = "ENRICHMENT"
        else:
            classification = "UNCHANGED"
        if any(change["change_type"] == "ENRICHMENT" for change in field_changes):
            enriched_existing_ids.add(technology_id)

        projected_existing.append(after)
        existing_diff.append({
            "technology_id": technology_id,
            "before": before,
            "after": after,
            "field_changes": field_changes,
            "official_evidence_sources": evidence,
            "change_classification": classification,
            "conflicts": sorted(set(conflicts)),
        })

    newtech_after = [
        row for row in projected_existing if row.get("record_type") == "construction_new_technology"
    ]
    patents_after = [row for row in projected_existing if row.get("record_type") == "patent"]
    if newtech_after != newtech:
        raise ProjectionInputError("non-patent baseline records must be preserved exactly")

    existing_alias_map: dict[str, set[str]] = {}
    for row in projected_existing:
        for alias in baseline_identity_aliases(row):
            existing_alias_map.setdefault(alias, set()).add(str(row.get("technology_id") or ""))
    identity_collision_count = sum(len(ids) > 1 for ids in existing_alias_map.values())

    accepted_people = {
        str(row.get("official_identity") or ""): list(row.get("applicants") or [])
        for row in applicant_summary.get("net_new_records", [])
        if isinstance(row, dict)
    }
    candidates = [dict(row) for row in applicant_candidates if isinstance(row, dict)]
    excluded_applicants = sorted(
        (row for row in candidates if not _company_match_confirmed(row, company_id)),
        key=_candidate_sort_key,
    )
    company_candidates = [row for row in candidates if _company_match_confirmed(row, company_id)]
    published_review = sorted(
        (
            row for row in company_candidates
            if row.get("modular_relevance") == "direct"
            and row.get("status") == "published"
            and "published" not in policy.allowed_new_statuses
            and policy.published_application_policy == "review_only"
        ),
        key=_candidate_sort_key,
    )
    direct = sorted(
        (
            row for row in company_candidates
            if row.get("modular_relevance") == "direct" and row not in published_review
        ),
        key=_candidate_sort_key,
    )
    adjacent = sorted(
        (row for row in company_candidates if row.get("modular_relevance") == "adjacent"),
        key=_candidate_sort_key,
    )
    accepted_new = []
    new_report = []
    seen_aliases: dict[str, dict[str, Any]] = {}
    direct_duplicate_count = 0
    ambiguous_count = 0
    credential_exposure_count = sum(
        _credential_bearing_url(row.get("source_url")) for row in candidates
    )

    for source in direct:
        reasons = _candidate_filter_reasons(source, policy)
        safe_source_url = source.get("source_url")
        try:
            safe_source_url = validate_public_source_url(safe_source_url)
        except ValueError:
            safe_source_url = None
            reasons.append(
                "credential_url" if _credential_bearing_url(source.get("source_url")) else "invalid_source_url"
            )

        aliases = set(baseline_identity_aliases(source))
        baseline_duplicates = sorted({
            technology_id
            for alias in aliases
            for technology_id in existing_alias_map.get(alias, set())
        })
        if baseline_duplicates:
            direct_duplicate_count += 1
            reasons.append("duplicate_with_baseline")

        prior = next((seen_aliases[alias] for alias in sorted(aliases) if alias in seen_aliases), None)
        if prior is not None:
            if _candidate_signature(prior) == _candidate_signature(source):
                direct_duplicate_count += 1
                reasons.append("duplicate_candidate")
            else:
                identity_collision_count += 1
                reasons.append("identity_collision")

        if source.get("company_match") in {"ambiguous", "unmatched"} or source.get("company_ids") != [company_id]:
            ambiguous_count += 1
        official_identity = str(source.get("official_identity") or "")
        public_record = _public_candidate(source, policy) if not reasons else None
        if public_record is not None:
            if public_record["technology_id"] in {
                str(row.get("technology_id") or "") for row in [*projected_existing, *accepted_new]
            }:
                identity_collision_count += 1
                reasons.append("technology_id_collision")
                public_record = None
            else:
                accepted_new.append(public_record)
                for alias in aliases:
                    seen_aliases[alias] = source

        new_report.append({
            "official_identity": official_identity or None,
            "title": source.get("name"),
            "applicant": accepted_people.get(official_identity, []),
            "application_number": source.get("application_number"),
            "registration_number": source.get("registration_number"),
            "patent_number": source.get("patent_number"),
            "application_date": source.get("application_date"),
            "registration_date": source.get("registration_date"),
            "status": source.get("status"),
            "technology_area": source.get("technology_area"),
            "relevance": source.get("modular_relevance"),
            "source_url": safe_source_url,
            "publication_decision": (
                "net_new_public_candidate" if public_record is not None else "filtered"
            ),
            "filter_reason": sorted(set(reasons)),
            "duplicate_baseline_technology_ids": baseline_duplicates,
        })

    adjacent_report = [
        {
            "classification": "REVIEW_ONLY_ADJACENT",
            "official_identity": row.get("official_identity"),
            "title": row.get("name"),
            "application_number": row.get("application_number"),
            "registration_number": row.get("registration_number"),
            "status": row.get("status"),
            "technology_area": row.get("technology_area"),
            "relevance": "adjacent",
            "publication_decision": "review_only_adjacent",
            "source_url": _safe_report_url(row.get("source_url")),
            "source_ids": sorted(set(row.get("source_ids") or [])),
            "applicants": list(row.get("applicants") or []),
        }
        for row in adjacent
    ]
    published_application_review = [
        _review_report_row(row, "application_only_review", ["status_not_allowed_by_policy:published"])
        for row in published_review
    ]
    excluded_applicant_report = [
        _review_report_row(row, "excluded_wrong_applicant", ["company_match_not_confirmed"])
        for row in excluded_applicants
    ]
    accepted_ids = {
        row["technology_id"] for row in accepted_new
    }
    registered_candidate_report = []
    for source, report in zip(direct, new_report, strict=True):
        technology_id = deterministic_technology_id(
            company_id,
            str(source.get("source") or ""),
            str(source.get("official_identity") or ""),
            namespace=policy.technology_id_namespace,
        )
        registered_candidate_report.append({
            **report,
            "technology_id": technology_id if technology_id in accepted_ids else None,
            "classification": (
                "PUBLICATION_ELIGIBLE_REGISTERED"
                if technology_id in accepted_ids
                else "FILTERED"
            ),
            "required_fields_present": not any(
                str(reason).startswith("missing_required_field:")
                for reason in report["filter_reason"]
            ),
            "source_ids": sorted(set(source.get("source_ids") or [])),
        })
    accepted_new.sort(key=lambda row: str(row["technology_id"]))
    candidate_patents = [*patents_after, *accepted_new]
    candidate_company = {
        "schema_version": policy.schema_version,
        "company_id": company_id,
        "technology": {
            "new_construction_technologies": newtech_after,
            "patents": candidate_patents,
        },
    }

    baseline_incomplete = sum(_information_incomplete(row) for row in baseline)
    candidate_items = [*newtech_after, *candidate_patents]
    candidate_incomplete = sum(_information_incomplete(row) for row in candidate_items)
    existing_modified = enriched_existing_ids | status_updated_ids
    metrics = {
        "baseline_count": len(baseline),
        "matched_official_count": sum(
            report.get("match_decision") == "MATCHED_OFFICIAL" for report in exact_by_id.values()
        ) + sum(
            report.get("decision") in {"CONFIRMED_EXPIRED", "CONFIRMED_REGISTERED_ACTIVE"}
            for report in status_by_id.values()
        ),
        "unchanged_count": sum(row["change_classification"] == "UNCHANGED" for row in existing_diff),
        "enriched_existing_count": len(enriched_existing_ids),
        "status_updated_existing_count": len(status_updated_ids),
        "existing_modified_total": len(existing_modified),
        "removed_count": len(baseline) - len(projected_existing),
        "direct_source_count": len(direct),
        "direct_duplicate_count": direct_duplicate_count,
        "direct_publishable_count": len(accepted_new),
        "direct_filtered_count": len(direct) - len(accepted_new),
        "net_new_count": len(accepted_new),
        "adjacent_review_count": len(adjacent_report),
        "candidate_total": len(candidate_items),
        "identity_collision_count": identity_collision_count,
        "conflict_count": conflict_count,
        "ambiguous_count": ambiguous_count,
        "credential_exposure_count": credential_exposure_count,
        "baseline_info_incomplete_count": baseline_incomplete,
        "candidate_info_incomplete_count": candidate_incomplete,
        "resolved_info_incomplete_count": baseline_incomplete - candidate_incomplete,
        "unexpected_existing_substantive_change_count": sum(
            change["field"] not in {
                *policy.allowed_enrichment_fields,
                *(('status',) if policy.allow_status_updates else ()),
            }
            for row in existing_diff
            for change in row["field_changes"]
        ),
        "published_application_review_count": len(published_application_review),
        "excluded_applicant_count": len(excluded_applicant_report),
    }
    return {
        "candidate_company_technology": candidate_company,
        "existing_diff_report": existing_diff,
        "new_candidate_report": new_report,
        "registered_candidate_report": registered_candidate_report,
        "published_application_review": published_application_review,
        "adjacent_review_report": adjacent_report,
        "excluded_applicant_report": excluded_applicant_report,
        "metrics": metrics,
    }


def build_samsung_public_projection(
    *,
    companies: Iterable[dict[str, Any]],
    exact_reports: Iterable[dict[str, Any]],
    status_reports: Iterable[dict[str, Any]],
    applicant_candidates: Iterable[dict[str, Any]],
    applicant_summary: dict[str, Any],
    company_id: str = DEFAULT_COMPANY_ID,
) -> dict[str, Any]:
    companies = list(companies)
    company = next((row for row in companies if row.get("company_id") == company_id), None)
    technology = (company or {}).get("technology") or {}
    newtech = list(technology.get("new_construction_technologies") or [])
    patents = list(technology.get("patents") or [])
    if len(newtech) != 1 or len(patents) != 6:
        raise ProjectionInputError("Samsung technology baseline must contain 1 new technology and 6 patents")
    generic = build_company_public_projection(
        companies=companies,
        exact_reports=exact_reports,
        status_reports=status_reports,
        applicant_candidates=applicant_candidates,
        applicant_summary=applicant_summary,
        policy=CompanyProjectionPolicy(
            company_id=company_id,
            allow_status_updates=True,
            technology_id_namespace="samsung",
            schema_version="samsung-technology-public-projection-v1",
        ),
    )
    return {
        "candidate_company_technology": generic["candidate_company_technology"],
        "existing_diff_report": generic["existing_diff_report"],
        "new_candidate_report": generic["new_candidate_report"],
        "adjacent_review_report": [
            {
                key: row.get(key)
                for key in (
                    "official_identity",
                    "title",
                    "application_number",
                    "registration_number",
                    "status",
                    "technology_area",
                    "relevance",
                    "publication_decision",
                    "source_url",
                )
            }
            for row in generic["adjacent_review_report"]
        ],
        "metrics": {
            key: value
            for key, value in generic["metrics"].items()
            if key not in {"published_application_review_count", "excluded_applicant_count"}
        },
    }


def run_public_projection(
    *,
    companies_path: Path = DEFAULT_COMPANIES,
    exact_report_path: Path = DEFAULT_EXACT_REPORT,
    exact_summary_path: Path = DEFAULT_EXACT_SUMMARY,
    status_report_path: Path = DEFAULT_STATUS_REPORT,
    status_summary_path: Path = DEFAULT_STATUS_SUMMARY,
    applicant_candidates_path: Path = DEFAULT_APPLICANT_CANDIDATES,
    applicant_summary_path: Path = DEFAULT_APPLICANT_SUMMARY,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    company_id: str = DEFAULT_COMPANY_ID,
) -> dict[str, Any]:
    input_paths = (
        exact_report_path,
        exact_summary_path,
        status_report_path,
        status_summary_path,
        applicant_candidates_path,
        applicant_summary_path,
    )
    missing = [str(path) for path in input_paths if not path.exists()]
    if missing:
        raise ProjectionInputError(f"accepted artifact inputs are missing: {', '.join(missing)}")

    companies = load_companies(companies_path)
    exact_reports = _read_list(exact_report_path)
    exact_summary = _read_object(exact_summary_path)
    status_reports = _read_list(status_report_path)
    status_summary = _read_object(status_summary_path)
    applicant_candidates = _read_list(applicant_candidates_path)
    applicant_summary = _read_object(applicant_summary_path)
    _validate_acceptance_inputs(
        exact_reports, exact_summary, status_reports, status_summary, applicant_candidates, applicant_summary
    )
    protected_before = hash_files(PROTECTED_PUBLIC_FILES)
    projection = build_samsung_public_projection(
        companies=companies,
        exact_reports=exact_reports,
        status_reports=status_reports,
        applicant_candidates=applicant_candidates,
        applicant_summary=applicant_summary,
        company_id=company_id,
    )
    protected_after = hash_files(PROTECTED_PUBLIC_FILES)
    metrics = projection["metrics"]
    generated_at = str(status_summary.get("generated_at") or applicant_summary.get("generated_at") or "")
    summary = {
        "schema_version": "samsung-technology-public-projection-summary-v1",
        "generated_at": generated_at,
        "company_id": company_id,
        **metrics,
        "kipris_request_count": 0,
        "kaia_request_count": 0,
        "llm_request_count": 0,
        "input_artifact_sha256": {
            path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in input_paths
        },
        "protected_public_hashes_before": protected_before,
        "protected_public_hashes_after": protected_after,
        "protected_public_data_unchanged": protected_before == protected_after,
        "public_write_performed": False,
        "security": {
            "credential_url_count": metrics["credential_exposure_count"],
            "secret_exposure_count": 0,
            "raw_public_field_count": 0,
        },
        "deterministic_content_sha256": {
            key: _content_hash(value)
            for key, value in projection.items()
            if key != "metrics"
        },
    }
    summary["decision"] = _decision(summary)

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "candidate_company_technology.json", projection["candidate_company_technology"])
    _write_json(output_dir / "existing_diff_report.json", projection["existing_diff_report"])
    _write_json(output_dir / "new_candidate_report.json", projection["new_candidate_report"])
    _write_json(output_dir / "adjacent_review_report.json", projection["adjacent_review_report"])
    _write_json(output_dir / "projection_summary.json", summary)
    _write_markdown(output_dir / "projection_report.md", summary)

    artifact_security = security_metrics(
        normalized_payload=[],
        candidates=_candidate_items(projection["candidate_company_technology"]),
        output_dir=output_dir,
        secrets=(),
    )
    summary["security"] = {
        "credential_url_count": metrics["credential_exposure_count"] + artifact_security["credential_url_count"],
        "secret_exposure_count": artifact_security["secret_exposure_count"],
        "raw_public_field_count": artifact_security["raw_public_field_count"],
    }
    summary["decision"] = _decision(summary)
    _write_json(output_dir / "projection_summary.json", summary)
    _write_markdown(output_dir / "projection_report.md", summary)
    return summary


def _apply_enrichment(
    before: dict[str, Any],
    after: dict[str, Any],
    exact: dict[str, Any],
    changes: list[dict[str, Any]],
    conflicts: list[str],
    allowed_fields: Iterable[str] = ALLOWED_ENRICHMENT_FIELDS,
) -> None:
    allowed_fields = tuple(allowed_fields)
    enrichment = exact.get("enrichment_fields") or {}
    unexpected = sorted(set(enrichment) - set(allowed_fields))
    conflicts.extend(f"unsupported_enrichment:{field}" for field in unexpected)
    for field in allowed_fields:
        if field not in enrichment:
            continue
        official = enrichment[field]
        before_value = before.get(field)
        if before_value not in (None, "", [], ()):
            if _comparable(field, before_value) != _comparable(field, official):
                conflicts.append(f"conflicting_enrichment:{field}")
            continue
        if official in (None, "", [], ()):
            continue
        after[field] = official
        changes.append({
            "field": field,
            "before": before_value,
            "after": official,
            "change_type": "ENRICHMENT",
            "evidence": "kipris_exact_identity",
        })


def _apply_status_update(
    before: dict[str, Any],
    after: dict[str, Any],
    exact: dict[str, Any],
    adjudication: dict[str, Any] | None,
    changes: list[dict[str, Any]],
    conflicts: list[str],
) -> None:
    exact_conflicts = set(exact.get("conflict_fields") or [])
    non_status_conflicts = sorted(exact_conflicts - {"status"})
    conflicts.extend(f"exact_identity_conflict:{field}" for field in non_status_conflicts)
    if exact.get("match_decision") == "MATCHED_OFFICIAL":
        return
    if exact_conflicts != {"status"}:
        conflicts.append("unresolved_exact_identity_decision")
        return
    if not adjudication or adjudication.get("decision") != "CONFIRMED_EXPIRED":
        conflicts.append("missing_accepted_status_adjudication")
        return
    if adjudication.get("status_field_semantics") != "current_lifecycle_status":
        conflicts.append("technology_status_semantics")
        return
    candidate = adjudication.get("status_update_candidate") or {}
    if candidate.get("from") != before.get("status") or candidate.get("to") != "expired":
        conflicts.append("status_update_contract_mismatch")
        return
    after["status"] = "expired"
    changes.append({
        "field": "status",
        "before": before.get("status"),
        "after": "expired",
        "change_type": "STATUS_UPDATE",
        "evidence": "kipris_st27_stop_right",
    })


def _candidate_filter_reasons(
    row: dict[str, Any],
    policy: CompanyProjectionPolicy,
) -> list[str]:
    reasons = []
    required = {
        "official_identity": row.get("official_identity"),
        "name": row.get("name"),
        "record_type": row.get("record_type"),
        "application_number": row.get("application_number"),
        "status": row.get("status"),
        "technology_area": row.get("technology_area"),
        "application_date": row.get("application_date"),
        "summary": row.get("summary"),
        "source_ids": row.get("source_ids"),
    }
    if row.get("status") == "registered":
        required.update({
            "registration_number": row.get("registration_number"),
            "registration_date": row.get("registration_date"),
        })
    reasons.extend(f"missing_required_field:{key}" for key, value in required.items() if value in (None, "", [], ()))
    if row.get("source") != "kipris":
        reasons.append("unsupported_official_source")
    if row.get("record_type") not in policy.allowed_new_record_types:
        reasons.append(f"record_type_not_allowed_by_policy:{row.get('record_type')}")
    if row.get("status") not in policy.allowed_new_statuses:
        reasons.append(f"status_not_allowed_by_policy:{row.get('status')}")
    if row.get("candidate_type") != "net_new":
        reasons.append("candidate_not_net_new")
    if row.get("modular_relevance") != "direct":
        reasons.append("not_direct_relevance")
    if not _company_match_confirmed(row, policy.company_id):
        reasons.append("company_match_not_confirmed")
    expected_identity = _identity_from_record(row)
    if expected_identity != row.get("official_identity"):
        reasons.append("official_identity_mismatch")
    return reasons


def deterministic_technology_id(
    company_id: str,
    source: str,
    official_identity: str,
    *,
    namespace: str | None = None,
) -> str:
    identity = str(official_identity).split(":", 1)[-1]
    parts = (namespace or company_id, source, identity)
    normalized = [re.sub(r"[^a-z0-9]+", "-", str(part).casefold()).strip("-") for part in parts]
    if not all(normalized):
        raise ProjectionInputError("deterministic technology identity components must be non-empty")
    return "tech-" + "-".join(normalized)


def _public_candidate(
    row: dict[str, Any],
    policy: CompanyProjectionPolicy,
) -> dict[str, Any]:
    public = {
        "technology_id": deterministic_technology_id(
            policy.company_id,
            str(row.get("source") or ""),
            str(row["official_identity"]),
            namespace=policy.technology_id_namespace,
        ),
        "name": row.get("name"),
        "record_type": row.get("record_type"),
        "registration_number": row.get("registration_number"),
        "application_number": row.get("application_number"),
        "patent_number": row.get("patent_number"),
        "status": row.get("status"),
        "technology_area": row.get("technology_area"),
        "application_date": row.get("application_date"),
        "registration_date": row.get("registration_date"),
        "summary": row.get("summary"),
        "source_ids": sorted(set(row.get("source_ids") or [])),
    }
    missing_keys = set(PUBLIC_TECHNOLOGY_FIELDS) - set(public)
    if missing_keys:
        raise ProjectionInputError(f"public technology contract fields missing: {sorted(missing_keys)}")
    return public


def _company_match_confirmed(row: dict[str, Any], company_id: str) -> bool:
    return row.get("company_ids") == [company_id] and row.get("company_match") not in {
        None,
        "ambiguous",
        "unmatched",
    }


def _review_report_row(
    row: dict[str, Any],
    decision: str,
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "classification": {
            "application_only_review": "APPLICATION_ONLY_REVIEW",
            "excluded_wrong_applicant": "EXCLUDED_WRONG_APPLICANT",
        }.get(decision, decision.upper()),
        "official_identity": row.get("official_identity"),
        "title": row.get("name"),
        "application_number": row.get("application_number"),
        "registration_number": row.get("registration_number"),
        "patent_number": row.get("patent_number"),
        "status": row.get("status"),
        "technology_area": row.get("technology_area"),
        "application_date": row.get("application_date"),
        "registration_date": row.get("registration_date"),
        "summary": row.get("summary"),
        "applicants": list(row.get("applicants") or []),
        "source_ids": sorted(set(row.get("source_ids") or [])),
        "relevance": row.get("modular_relevance"),
        "publication_decision": decision,
        "filter_reason": sorted(set(reasons)),
        "source_url": _safe_report_url(row.get("source_url")),
    }


def _validate_acceptance_inputs(
    exact_reports: list[dict[str, Any]],
    exact_summary: dict[str, Any],
    status_reports: list[dict[str, Any]],
    status_summary: dict[str, Any],
    applicant_candidates: list[dict[str, Any]],
    applicant_summary: dict[str, Any],
) -> None:
    if len(exact_reports) != 6 or exact_summary.get("baseline_patent_count") != 6:
        raise ProjectionInputError("exact identity evidence must contain six Samsung patents")
    if len(status_reports) != 2 or status_summary.get("decision") != "SAMSUNG_PATENT_STATUS_CONFLICT_RESOLVED":
        raise ProjectionInputError("accepted lifecycle adjudication is incomplete")
    if status_summary.get("remaining_conflict_count") != 0:
        raise ProjectionInputError("lifecycle adjudication still contains conflicts")
    if applicant_summary.get("acceptance_decision") not in ACCEPTED_APPLICANT_DECISIONS:
        raise ProjectionInputError("KIPRIS applicant acceptance decision is not publishable")
    security = (applicant_summary.get("metrics") or {}).get("security") or {}
    if any(int(security.get(key) or 0) for key in (
        "credential_url_count", "raw_public_field_count", "secret_exposure_count"
    )):
        raise ProjectionInputError("accepted applicant artifacts failed security validation")
    direct = sum(row.get("modular_relevance") == "direct" for row in applicant_candidates)
    adjacent = sum(row.get("modular_relevance") == "adjacent" for row in applicant_candidates)
    if direct != 6 or adjacent != 41:
        raise ProjectionInputError("accepted applicant candidate counts changed")


def _decision(summary: dict[str, Any]) -> str:
    blockers = (
        summary["removed_count"],
        summary["identity_collision_count"],
        summary["conflict_count"],
        summary["ambiguous_count"],
        summary["unexpected_existing_substantive_change_count"],
        summary["security"]["credential_url_count"],
        summary["security"]["secret_exposure_count"],
        summary["security"]["raw_public_field_count"],
    )
    if any(blockers) or not summary["protected_public_data_unchanged"]:
        return "HOLD_FOR_SAMSUNG_PUBLIC_PROJECTION_CONFLICT"
    if summary["candidate_total"] > 13 or summary["baseline_count"] != 7:
        return "HOLD_FOR_TECHNOLOGY_PUBLIC_SCHEMA_REVIEW"
    return "SAMSUNG_TECH_PUBLIC_PROJECTION_DRY_RUN_COMPLETE"


def _information_incomplete(row: dict[str, Any]) -> bool:
    application_date = row.get("application_date") or row.get("filed_at") or row.get("filed_date")
    registration_date = row.get("registration_date") or row.get("registered_at")
    return not application_date or not registration_date


def _candidate_items(candidate_company: dict[str, Any]) -> list[dict[str, Any]]:
    technology = candidate_company["technology"]
    return [
        *technology["new_construction_technologies"],
        *technology["patents"],
    ]


def _candidate_signature(row: dict[str, Any]) -> str:
    values = {
        key: row.get(key)
        for key in ("official_identity", "name", "application_number", "registration_number", "status")
    }
    return json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _candidate_sort_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("official_identity") or ""), str(row.get("name") or "")


def _identity_from_record(row: dict[str, Any]) -> str | None:
    number = normalize_official_number(
        row.get("application_number") or row.get("registration_number") or row.get("patent_number")
    )
    return f"patent:{number}" if number else None


def _unique_by(rows: Iterable[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    result = {}
    for row in rows:
        value = str(row.get(key) or "")
        if not value:
            raise ProjectionInputError(f"{label} is missing {key}")
        if value in result:
            raise ProjectionInputError(f"duplicate {label} identity: {value}")
        result[value] = dict(row)
    return result


def _comparable(field: str, value: Any) -> Any:
    return normalize_official_number(value) if field.endswith("_number") else str(value).casefold()


def _exact_evidence(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "kipris_exact_identity",
        "source_url": KIPRIS_SOURCE_URL,
        "application_number": report.get("official_application_number"),
        "registration_number": report.get("official_registration_number"),
        "match_decision": report.get("match_decision"),
    }


def _status_evidence(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "kipris_st27_stop_right",
        "source_url": "https://plus.kipris.or.kr/portal/data/service/DBII_000000000000540/view.do",
        "decision": report.get("decision"),
        "termination_events": report.get("termination_events") or [],
    }


def _safe_report_url(value: Any) -> str | None:
    try:
        return validate_public_source_url(value)
    except ValueError:
        return None


def _credential_bearing_url(value: Any) -> bool:
    parsed = urlsplit(str(value or ""))
    query_keys = {key.casefold() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    return bool(query_keys & SENSITIVE_QUERY_KEYS) or bool(parsed.username or parsed.password)


def _read_list(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        raise ProjectionInputError(f"expected JSON object array: {path}")
    return payload


def _read_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ProjectionInputError(f"expected JSON object: {path}")
    return payload


def _content_hash(payload: Any) -> str:
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_markdown(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Samsung technology public projection dry run",
        "",
        f"- Decision: `{summary['decision']}`",
        f"- Baseline: {summary['baseline_count']}",
        f"- Existing enriched: {summary['enriched_existing_count']}",
        f"- Existing status updated: {summary['status_updated_existing_count']}",
        f"- Removed: {summary['removed_count']}",
        f"- Direct source: {summary['direct_source_count']}",
        f"- Direct publishable: {summary['direct_publishable_count']}",
        f"- Adjacent review: {summary['adjacent_review_count']}",
        f"- Candidate total: {summary['candidate_total']}",
        f"- Conflicts: {summary['conflict_count']}",
        f"- Identity collisions: {summary['identity_collision_count']}",
        f"- Public write performed: {str(summary['public_write_performed']).lower()}",
        f"- Protected public data unchanged: {str(summary['protected_public_data_unchanged']).lower()}",
        f"- Secret exposure: {summary['security']['secret_exposure_count']}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the offline Samsung technology public projection")
    parser.add_argument("--companies", type=Path, default=DEFAULT_COMPANIES)
    parser.add_argument("--exact-report", type=Path, default=DEFAULT_EXACT_REPORT)
    parser.add_argument("--exact-summary", type=Path, default=DEFAULT_EXACT_SUMMARY)
    parser.add_argument("--status-report", type=Path, default=DEFAULT_STATUS_REPORT)
    parser.add_argument("--status-summary", type=Path, default=DEFAULT_STATUS_SUMMARY)
    parser.add_argument("--applicant-candidates", type=Path, default=DEFAULT_APPLICANT_CANDIDATES)
    parser.add_argument("--applicant-summary", type=Path, default=DEFAULT_APPLICANT_SUMMARY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    summary = run_public_projection(
        companies_path=args.companies,
        exact_report_path=args.exact_report,
        exact_summary_path=args.exact_summary,
        status_report_path=args.status_report,
        status_summary_path=args.status_summary,
        applicant_candidates_path=args.applicant_candidates,
        applicant_summary_path=args.applicant_summary,
        output_dir=args.output_dir,
    )
    print(json.dumps({
        key: value
        for key, value in summary.items()
        if key == "decision" or key.endswith("_count") or key in {"candidate_total", "public_write_performed"}
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["decision"] == "SAMSUNG_TECH_PUBLIC_PROJECTION_DRY_RUN_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
