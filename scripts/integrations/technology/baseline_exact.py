from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

from dotenv import load_dotenv

from scripts.integrations.technology.base import normalize_official_number
from scripts.integrations.technology.dry_run import load_companies
from scripts.integrations.technology.live_acceptance import (
    PROTECTED_PUBLIC_FILES,
    hash_files,
    security_metrics,
)
from scripts.integrations.technology.live_sources import (
    KiprisExactLookupClient,
    TechnologyCollectionResult,
    normalize_kipris_exact_query_identifier,
)
from scripts.integrations.technology.matching import company_identities, match_companies
from scripts.integrations.technology.reconciliation import (
    baseline_identity_aliases,
    normalize_fixture_records,
)


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_COMPANIES = ROOT / "frontend/public/data/companies/companies.json"
DEFAULT_PRIOR_CANDIDATES = (
    ROOT
    / "artifacts/company-technology/samsung-live/credentialed-acceptance/public_projection_candidates.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "artifacts/company-technology/samsung-baseline-exact"
DEFAULT_COMPANY_ID = "samsung-ct-construction"

MATCHED_OFFICIAL = "MATCHED_OFFICIAL"
NOT_FOUND_OFFICIAL = "NOT_FOUND_OFFICIAL"
IDENTITY_INSUFFICIENT = "IDENTITY_INSUFFICIENT"
CONFLICT = "CONFLICT"
MATCH_DECISIONS = frozenset({MATCHED_OFFICIAL, NOT_FOUND_OFFICIAL, IDENTITY_INSUFFICIENT, CONFLICT})
LOOKUP_PRIORITY = (
    ("application_number", "application_number"),
    ("registration_number", "registration_number"),
    ("patent_number", "registration_number"),
)
ENRICHMENT_FIELDS = (
    "application_number",
    "registration_number",
    "patent_number",
    "application_date",
    "registration_date",
    "status",
)


def extract_samsung_patent_baseline(
    companies: Iterable[dict[str, Any]],
    company_id: str = DEFAULT_COMPANY_ID,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    matches = [company for company in companies if company.get("company_id") == company_id]
    if len(matches) != 1:
        raise ValueError(f"company must resolve exactly once: {company_id}")
    company = matches[0]
    patents = [
        dict(record)
        for record in (company.get("technology") or {}).get("patents", [])
        if isinstance(record, dict) and record.get("record_type") == "patent"
    ]
    patents.sort(key=lambda record: str(record.get("technology_id") or ""))
    return company, patents


def build_exact_lookup_plan(patents: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    plan = []
    for baseline in patents:
        item = {
            "technology_id": baseline.get("technology_id"),
            "lookup_type": None,
            "lookup_identifier": None,
            "query_identifier": None,
            "planning_decision": IDENTITY_INSUFFICIENT,
        }
        for field, lookup_type in LOOKUP_PRIORITY:
            identifier = baseline.get(field)
            if not identifier:
                continue
            try:
                query_identifier = normalize_kipris_exact_query_identifier(str(identifier), lookup_type)
            except ValueError:
                continue
            item.update({
                "lookup_type": lookup_type,
                "lookup_identifier": str(identifier),
                "query_identifier": query_identifier,
                "planning_decision": None,
            })
            break
        plan.append(item)
    return plan


def evaluate_baseline_patent(
    baseline: dict[str, Any],
    plan: dict[str, Any],
    result: TechnologyCollectionResult | None,
    company: dict[str, Any],
) -> dict[str, Any]:
    report = _baseline_report_shell(baseline, plan)
    if plan.get("planning_decision") == IDENTITY_INSUFFICIENT:
        report["match_decision"] = IDENTITY_INSUFFICIENT
        return report
    if result is None or not result.records:
        report["match_decision"] = NOT_FOUND_OFFICIAL
        return report

    normalization = normalize_fixture_records(result.records)
    lookup_type = str(plan["lookup_type"])
    target_value = baseline.get(lookup_type)
    if lookup_type == "registration_number" and not target_value:
        target_value = baseline.get("patent_number")
    target_identity = normalize_official_number(target_value)
    candidates = [
        record
        for record in normalization.records
        if normalize_official_number(getattr(record, lookup_type)) == target_identity
    ]
    if len(candidates) != 1:
        report["match_decision"] = CONFLICT
        report["conflict_fields"] = [
            "official_identifier_not_returned" if not candidates else "official_identifier_collision"
        ]
        return report

    official = candidates[0]
    company_match = match_companies(official, company_identities([company]))
    title_match = _title_match_kind(baseline.get("name") or baseline.get("title"), official.title)
    conflicts = []
    if title_match == "conflict":
        conflicts.append("title")
    if company.get("company_id") not in company_match.company_ids:
        conflicts.append("applicant_or_right_holder")
    conflicts.extend(_existing_value_conflicts(baseline, official.as_dict()))

    raw = _matching_raw_record(result.records, official.as_dict())
    public_number = _pick(
        raw,
        "OpeningNumber",
        "openingNumber",
        "PublicNumber",
        "publicationNumber",
        "patentNumber",
    )
    official_values = {
        "application_number": official.application_number,
        "registration_number": official.registration_number,
        "patent_number": public_number or official.patent_number,
        "application_date": official.application_date,
        "registration_date": official.registration_date,
        "status": official.status,
    }
    report.update({
        "official_application_number": official.application_number,
        "official_registration_number": official.registration_number,
        "official_patent_public_number": public_number or official.patent_number,
        "official_title": official.title,
        "official_applicant": list(official.applicants),
        "official_right_holder": list(official.owners),
        "official_application_date": official.application_date,
        "official_registration_date": official.registration_date,
        "official_status": official.status,
        "company_match": company_match.outcome,
        "title_match": title_match,
    })
    if conflicts:
        report["match_decision"] = CONFLICT
        report["conflict_fields"] = sorted(dict.fromkeys(conflicts))
        return report

    report["match_decision"] = MATCHED_OFFICIAL
    report["enrichment_fields"] = {
        field: value
        for field, value in official_values.items()
        if value not in (None, "", [], ()) and baseline.get(field) in (None, "", [], ())
    }
    return report


def reconcile_prior_candidates(
    prior_candidates: Iterable[dict[str, Any]],
    baseline_reports: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    alias_to_baseline: dict[str, set[str]] = defaultdict(set)
    for report in baseline_reports:
        technology_id = str(report.get("baseline_technology_id") or "")
        identity_record = {
            "record_type": "patent",
            "application_number": report.get("baseline_application_number"),
            "registration_number": report.get("baseline_registration_number"),
            "patent_number": report.get("baseline_patent_number"),
        }
        if report.get("match_decision") == MATCHED_OFFICIAL:
            identity_record.update({
                "application_number": report.get("official_application_number")
                or identity_record["application_number"],
                "registration_number": report.get("official_registration_number")
                or identity_record["registration_number"],
                "patent_number": report.get("official_patent_public_number")
                or identity_record["patent_number"],
            })
        for alias in baseline_identity_aliases(identity_record):
            alias_to_baseline[alias].add(technology_id)

    counts: Counter[str] = Counter()
    rows = []
    for candidate in prior_candidates:
        relevance = str(candidate.get("modular_relevance") or "")
        if relevance not in {"direct", "adjacent"}:
            continue
        counts[f"{relevance}_total_before"] += 1
        aliases = baseline_identity_aliases(candidate)
        duplicate_ids = sorted({
            technology_id
            for alias in aliases
            for technology_id in alias_to_baseline.get(alias, set())
        })
        duplicate = bool(duplicate_ids)
        if duplicate:
            counts[f"{relevance}_duplicate_with_baseline"] += 1
        rows.append({
            "official_identity": candidate.get("official_identity"),
            "name": candidate.get("name"),
            "modular_relevance": relevance,
            "duplicate_with_baseline": duplicate,
            "baseline_technology_ids": duplicate_ids,
        })

    direct_total = counts["direct_total_before"]
    direct_duplicates = counts["direct_duplicate_with_baseline"]
    adjacent_total = counts["adjacent_total_before"]
    adjacent_duplicates = counts["adjacent_duplicate_with_baseline"]
    rows.sort(key=lambda row: (row["modular_relevance"], str(row["official_identity"] or "")))
    return {
        "schema_version": "samsung-kipris-candidate-reconciliation-v1",
        "direct_total_before": direct_total,
        "direct_duplicate_with_baseline": direct_duplicates,
        "direct_net_new_after": direct_total - direct_duplicates,
        "adjacent_total_before": adjacent_total,
        "adjacent_duplicate_with_baseline": adjacent_duplicates,
        "adjacent_review_after": adjacent_total - adjacent_duplicates,
        "records": rows,
    }


def run_baseline_exact_identity(
    *,
    companies_path: Path = DEFAULT_COMPANIES,
    prior_candidates_path: Path = DEFAULT_PRIOR_CANDIDATES,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    company_id: str = DEFAULT_COMPANY_ID,
    client: KiprisExactLookupClient | None = None,
    collected_at: str | None = None,
) -> dict[str, Any]:
    collected_at = collected_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    companies = load_companies(companies_path)
    company, patents = extract_samsung_patent_baseline(companies, company_id)
    plans = build_exact_lookup_plan(patents)
    exact_client = client or KiprisExactLookupClient()
    protected_before = hash_files(PROTECTED_PUBLIC_FILES)

    results: dict[tuple[str, str], TechnologyCollectionResult] = {}
    for plan in plans:
        lookup_type = plan.get("lookup_type")
        query_identifier = plan.get("query_identifier")
        if not lookup_type or not query_identifier:
            continue
        key = (str(lookup_type), str(query_identifier))
        if key not in results:
            results[key] = exact_client.lookup(
                str(lookup_type),
                str(query_identifier),
                collected_at=collected_at,
            )

    reports = []
    for baseline, plan in zip(patents, plans, strict=True):
        key = (str(plan.get("lookup_type")), str(plan.get("query_identifier")))
        reports.append(evaluate_baseline_patent(baseline, plan, results.get(key), company))

    prior_candidates = _read_json_list(prior_candidates_path)
    candidate_reconciliation = reconcile_prior_candidates(prior_candidates, reports)
    normalized = normalize_fixture_records(
        record
        for result in results.values()
        for record in result.records
    )
    normalized_payload = [record.as_dict() for record in normalized.records]
    decision_counts = Counter(report["match_decision"] for report in reports)
    enrichment_counts = Counter(
        field
        for report in reports
        for field in (report.get("enrichment_fields") or {})
    )
    source_statuses = sorted({result.diagnostic.status for result in results.values()})
    protected_after = hash_files(PROTECTED_PUBLIC_FILES)

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for (lookup_type, query_identifier), result in sorted(results.items()):
        stem = f"{lookup_type}-{query_identifier}"
        for index, raw_page in enumerate(result.raw_pages, start=1):
            (raw_dir / f"{stem}-{index:02d}.xml").write_text(raw_page, encoding="utf-8")
        _write_json(raw_dir / f"{stem}-diagnostic.json", result.diagnostic.as_dict())
    _write_json(output_dir / "normalized_records.json", normalized_payload)
    _write_json(output_dir / "baseline_match_report.json", reports)
    _write_json(output_dir / "candidate_reconciliation_report.json", candidate_reconciliation)

    summary = {
        "schema_version": "samsung-kipris-baseline-exact-v1",
        "generated_at": collected_at,
        "company_id": company_id,
        "baseline_patent_count": len(patents),
        "broad_applicant_request_count": 0,
        "kaia_request_count": 0,
        "exact_lookup_request_count": sum(result.diagnostic.pages_requested for result in results.values()),
        "exact_lookup_unique_identifier_count": len(results),
        "kipris_configured": exact_client.configured(),
        "kipris_source_statuses": source_statuses,
        "http_statuses": sorted({
            result.diagnostic.http_status
            for result in results.values()
            if result.diagnostic.http_status is not None
        }),
        "api_result_codes": sorted({
            result.diagnostic.api_result_code
            for result in results.values()
            if result.diagnostic.api_result_code is not None
        }),
        "matched_official_count": decision_counts[MATCHED_OFFICIAL],
        "not_found_official_count": decision_counts[NOT_FOUND_OFFICIAL],
        "identity_insufficient_count": decision_counts[IDENTITY_INSUFFICIENT],
        "conflict_count": decision_counts[CONFLICT],
        "application_number_completed_count": enrichment_counts["application_number"],
        "registration_number_completed_count": enrichment_counts["registration_number"],
        "patent_public_number_completed_count": enrichment_counts["patent_number"],
        "application_date_enrichment_count": enrichment_counts["application_date"],
        "registration_date_enrichment_count": enrichment_counts["registration_date"],
        "status_enrichment_count": enrichment_counts["status"],
        "candidate_reconciliation": {
            key: value
            for key, value in candidate_reconciliation.items()
            if key != "records"
        },
        "protected_public_hashes_before": protected_before,
        "protected_public_hashes_after": protected_after,
        "protected_public_data_unchanged": protected_before == protected_after,
        "public_write_performed": False,
        "security": {
            "credential_url_count": 0,
            "secret_exposure_count": 0,
            "raw_public_field_count": 0,
        },
        "deterministic_content_sha256": {
            "normalized_records": _content_hash(normalized_payload),
            "baseline_match_report": _content_hash(reports),
            "candidate_reconciliation_report": _content_hash(candidate_reconciliation),
        },
    }
    summary["decision"] = _decision(summary)
    _write_json(output_dir / "summary.json", summary)
    _write_markdown(output_dir / "report.md", summary)

    summary["security"] = security_metrics(
        normalized_payload=normalized_payload,
        candidates=[],
        output_dir=output_dir,
        secrets=(exact_client.api_key,),
    )
    summary["decision"] = _decision(summary)
    _write_json(output_dir / "summary.json", summary)
    _write_markdown(output_dir / "report.md", summary)
    return summary


def _decision(summary: dict[str, Any]) -> str:
    if summary["security"]["secret_exposure_count"] or summary["security"]["credential_url_count"]:
        return "HOLD_FOR_KIPRIS_SECURITY_REVIEW"
    if any(status not in {"healthy", "empty_result"} for status in summary["kipris_source_statuses"]):
        return "HOLD_FOR_KIPRIS_EXACT_LOOKUP_CONTRACT"
    if summary["conflict_count"]:
        return "HOLD_FOR_SAMSUNG_BASELINE_IDENTITY_CONFLICT"
    if summary["matched_official_count"] == summary["baseline_patent_count"]:
        return "SAMSUNG_KIPRIS_BASELINE_IDENTITY_COMPLETE"
    return "SAMSUNG_KIPRIS_BASELINE_PARTIAL_COMPLETE"


def _baseline_report_shell(baseline: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "baseline_technology_id": baseline.get("technology_id"),
        "baseline_title": baseline.get("name") or baseline.get("title"),
        "baseline_application_number": baseline.get("application_number"),
        "baseline_registration_number": baseline.get("registration_number"),
        "baseline_patent_number": baseline.get("patent_number"),
        "baseline_source_ids": list(baseline.get("source_ids") or []),
        "lookup_identifier": plan.get("lookup_identifier"),
        "lookup_type": plan.get("lookup_type"),
        "official_application_number": None,
        "official_registration_number": None,
        "official_patent_public_number": None,
        "official_title": None,
        "official_applicant": [],
        "official_right_holder": [],
        "official_application_date": None,
        "official_registration_date": None,
        "official_status": None,
        "company_match": None,
        "title_match": None,
        "match_decision": None,
        "enrichment_fields": {},
        "conflict_fields": [],
    }


def _existing_value_conflicts(baseline: dict[str, Any], official: dict[str, Any]) -> list[str]:
    conflicts = []
    for field in ENRICHMENT_FIELDS:
        baseline_value = baseline.get(field)
        official_value = official.get(field)
        if baseline_value in (None, "", [], ()) or official_value in (None, "", [], ()):
            continue
        if field.endswith("_number"):
            differs = normalize_official_number(str(baseline_value)) != normalize_official_number(str(official_value))
        else:
            differs = str(baseline_value).casefold() != str(official_value).casefold()
        if differs:
            conflicts.append(field)
    return conflicts


def _matching_raw_record(records: Iterable[dict[str, Any]], official: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        normalize_official_number(official.get("application_number")),
        normalize_official_number(official.get("registration_number")),
    } - {None}
    for record in records:
        record_aliases = {
            normalize_official_number(_pick(record, "ApplicationNumber", "applicationNumber")),
            normalize_official_number(_pick(record, "RegistrationNumber", "registrationNumber")),
        } - {None}
        if aliases & record_aliases:
            return record
    return {}


def _pick(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if record.get(key) not in (None, ""):
            return record[key]
    return None


def _normalize_title(value: Any) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(value or "").casefold())


def _title_match_kind(baseline_title: Any, official_title: Any) -> str:
    if _normalize_title(baseline_title) == _normalize_title(official_title):
        return "exact"
    baseline_terms = set(_title_terms(baseline_title))
    official_terms = set(_title_terms(official_title))
    if len(baseline_terms) >= 4 and baseline_terms.issubset(official_terms):
        return "substantive"
    return "conflict"


def _title_terms(value: Any) -> tuple[str, ...]:
    return tuple(
        term
        for term in re.findall(r"[0-9a-z가-힣]+", str(value or "").casefold())
        if term not in {"이의", "이에", "의한"}
    )


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        raise ValueError(f"expected JSON object array: {path}")
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
    candidate = summary["candidate_reconciliation"]
    lines = [
        "# Samsung KIPRIS baseline exact identity",
        "",
        f"- Decision: `{summary['decision']}`",
        f"- Baseline patents: {summary['baseline_patent_count']}",
        f"- Matched official: {summary['matched_official_count']}",
        f"- Not found official: {summary['not_found_official_count']}",
        f"- Identity insufficient: {summary['identity_insufficient_count']}",
        f"- Conflicts: {summary['conflict_count']}",
        f"- Exact lookup requests: {summary['exact_lookup_request_count']}",
        "- Broad applicant requests: 0",
        "- KAIA requests: 0",
        f"- Direct duplicate with baseline: {candidate['direct_duplicate_with_baseline']}",
        f"- Direct net new: {candidate['direct_net_new_after']}",
        f"- Adjacent duplicate with baseline: {candidate['adjacent_duplicate_with_baseline']}",
        f"- Adjacent remaining review: {candidate['adjacent_review_after']}",
        f"- Secret exposure: {summary['security']['secret_exposure_count']}",
        f"- Public data unchanged: {str(summary['protected_public_data_unchanged']).lower()}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Complete Samsung patent baseline identities with exact KIPRIS lookups.")
    parser.add_argument("--companies", type=Path, default=DEFAULT_COMPANIES)
    parser.add_argument("--prior-candidates", type=Path, default=DEFAULT_PRIOR_CANDIDATES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=False)
    else:
        load_dotenv(override=False)
    summary = run_baseline_exact_identity(
        companies_path=args.companies,
        prior_candidates_path=args.prior_candidates,
        output_dir=args.output_dir,
    )
    safe = {
        "decision": summary["decision"],
        "kipris_configured": summary["kipris_configured"],
        "broad_applicant_request_count": 0,
        "kaia_request_count": 0,
        "exact_lookup_request_count": summary["exact_lookup_request_count"],
        "matched_official_count": summary["matched_official_count"],
        "conflict_count": summary["conflict_count"],
        "secret_exposure_count": summary["security"]["secret_exposure_count"],
        "public_data_unchanged": summary["protected_public_data_unchanged"],
    }
    print(json.dumps(safe, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["decision"] in {
        "SAMSUNG_KIPRIS_BASELINE_IDENTITY_COMPLETE",
        "SAMSUNG_KIPRIS_BASELINE_PARTIAL_COMPLETE",
    } else 3


if __name__ == "__main__":
    raise SystemExit(main())
