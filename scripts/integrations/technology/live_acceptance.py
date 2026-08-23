from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlsplit

from dotenv import load_dotenv

from scripts.integrations.technology.base import KAIA_API_KEY_ENV, KIPRIS_API_KEY_ENV, SENSITIVE_QUERY_KEYS
from scripts.integrations.technology.dry_run import load_companies
from scripts.integrations.technology.live_sources import (
    KaiaLiveClient,
    KiprisLiveClient,
    TechnologyCollectionResult,
    artifact_contains_credentials,
    filter_samsung_participants,
)
from scripts.integrations.technology.matching import company_identities, match_companies
from scripts.integrations.technology.reconciliation import (
    ENRICHABLE_FIELDS,
    baseline_technology_records,
    normalize_fixture_records,
    reconcile_technology_records,
)
from scripts.integrations.technology.relevance import assess_modular_relevance


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_COMPANIES = ROOT / "frontend/public/data/companies/companies.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts/company-technology/samsung-live"
DEFAULT_COMPANY_ID = "samsung-ct-construction"
PROTECTED_PUBLIC_FILES = (
    ROOT / "frontend/public/data/companies/companies.json",
    ROOT / "frontend/public/data/business.json",
    ROOT / "frontend/public/data/meta.json",
    ROOT / "frontend/public/data/news.json",
)
RAW_PUBLIC_FORBIDDEN_FIELDS = frozenset({
    "headers",
    "request_headers",
    "raw_response",
    "accesskey",
    "apikey",
    "servicekey",
    "authorization",
    "token",
})
OFFICIAL_NUMBER_FIELDS = frozenset({
    "application_number",
    "registration_number",
    "patent_number",
    "newtech_number",
})


def run_live_acceptance(
    *,
    companies_path: Path = DEFAULT_COMPANIES,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    company_id: str = DEFAULT_COMPANY_ID,
    kipris_client: KiprisLiveClient | None = None,
    kaia_client: KaiaLiveClient | None = None,
    collected_at: str | None = None,
    protected_before: dict[str, str] | None = None,
) -> dict[str, Any]:
    collected_at = collected_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    companies = [row for row in load_companies(companies_path) if row.get("company_id") == company_id]
    if len(companies) != 1:
        raise ValueError(f"pilot company must resolve exactly once: {company_id}")
    company = companies[0]
    aliases = _company_aliases(company)
    designation_numbers = _baseline_newtech_numbers(company)

    protected_before = protected_before or hash_files(PROTECTED_PUBLIC_FILES)
    kipris_client_instance = kipris_client or KiprisLiveClient()
    kaia_client_instance = kaia_client or KaiaLiveClient()
    kipris = kipris_client_instance.collect(
        aliases,
        collected_at=collected_at,
    )
    kaia = kaia_client_instance.collect(
        designation_numbers=designation_numbers,
        collected_at=collected_at,
    )

    source_results = (kipris, kaia)
    selected_records = [
        record
        for result in source_results
        for record in filter_samsung_participants(result.records, aliases)
    ]
    normalization = normalize_fixture_records(selected_records)
    candidates, reconciliation = reconcile_technology_records(companies, normalization)

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_raw_pages(output_dir, source_results)
    normalized_payload = [record.as_dict() for record in normalization.records]
    detail = build_acceptance_detail(companies, normalization.records, reconciliation)
    _write_json(output_dir / "normalized_records.json", normalized_payload)
    _write_json(output_dir / "public_projection_candidates.json", candidates)
    _write_json(output_dir / "reconciliation_report.json", reconciliation)
    _write_json(output_dir / "acceptance_detail.json", detail)

    protected_after = hash_files(PROTECTED_PUBLIC_FILES)
    security = security_metrics(
        normalized_payload=normalized_payload,
        candidates=candidates,
        output_dir=output_dir,
        secrets=(
            kipris_client_instance.api_key,
            kaia_client_instance.api_key,
        ),
    )
    summary = build_summary(
        source_results=source_results,
        normalization=normalization,
        reconciliation=reconciliation,
        candidates=candidates,
        detail=detail,
        protected_before=protected_before,
        protected_after=protected_after,
        security=security,
        collected_at=collected_at,
        company_id=company_id,
    )
    summary["deterministic_content_sha256"] = {
        "normalized_records": _content_hash(normalized_payload),
        "public_projection_candidates": _content_hash(candidates),
        "reconciliation_report": _content_hash(reconciliation),
        "acceptance_detail": _content_hash(detail),
    }
    _write_json(output_dir / "live_acceptance_summary.json", summary)
    _write_markdown(output_dir / "live_acceptance_report.md", summary)
    final_security = security_metrics(
        normalized_payload=normalized_payload,
        candidates=candidates,
        output_dir=output_dir,
        secrets=(kipris_client_instance.api_key, kaia_client_instance.api_key),
    )
    if final_security != summary["metrics"]["security"]:
        summary["metrics"]["security"] = final_security
        _write_json(output_dir / "live_acceptance_summary.json", summary)
        _write_markdown(output_dir / "live_acceptance_report.md", summary)
    return summary


def build_summary(
    *,
    source_results: Iterable[TechnologyCollectionResult],
    normalization: Any,
    reconciliation: dict[str, Any],
    candidates: list[dict[str, Any]],
    detail: dict[str, Any],
    protected_before: dict[str, str],
    protected_after: dict[str, str],
    security: dict[str, int],
    collected_at: str,
    company_id: str,
) -> dict[str, Any]:
    results = {result.source: result for result in source_results}
    per_source_records = Counter(record.source for record in normalization.records)
    per_source_match = Counter()
    per_source_relevance: dict[str, Counter[str]] = {}
    identities = company_identities([{"company_id": company_id, "company_name": "삼성물산 건설부문", "aliases": ["삼성물산", "Samsung C&T Construction"]}])
    for record in normalization.records:
        match = match_companies(record, identities)
        if match.outcome in {"exact", "normalized_alias"}:
            per_source_match[record.source] += 1
        per_source_relevance.setdefault(record.source, Counter())[assess_modular_relevance(record).level] += 1

    enrichment_counts = Counter()
    official_number_enrichment_count = 0
    for candidate in candidates:
        fields = set(candidate.get("enrichment_fields") or {})
        for field in ENRICHABLE_FIELDS:
            if field in fields:
                enrichment_counts[field] += 1
        if fields & OFFICIAL_NUMBER_FIELDS:
            official_number_enrichment_count += 1

    kipris = results["kipris"]
    kaia = results["kaia_newtech"]
    official_relevant_count = reconciliation["modular_direct_count"] + reconciliation["modular_adjacent_count"]
    source_statuses = {
        "kipris": kipris.diagnostic.as_dict(),
        "kaia": kaia.diagnostic.as_dict(),
    }
    decision = acceptance_decision(kipris.diagnostic.status, kaia.diagnostic.status)
    return {
        "schema_version": "company-technology-live-acceptance-v1",
        "generated_at": collected_at,
        "company_id": company_id,
        "public_write_performed": False,
        "source_status": source_statuses,
        "metrics": {
            "source": {
                "kipris_status": kipris.diagnostic.status,
                "kaia_status": kaia.diagnostic.status,
            },
            "kipris": {
                "request_attempted": kipris.diagnostic.request_attempted,
                "request_count": kipris.diagnostic.pages_requested,
                "attempt_count": kipris.diagnostic.attempt_count,
                "received_count": kipris.diagnostic.received_count,
                "unique_identity_count": per_source_records["kipris"],
                "normalized_count": per_source_records["kipris"],
                "company_matched_count": per_source_match["kipris"],
                "direct_count": per_source_relevance.get("kipris", Counter())["direct"],
                "adjacent_count": per_source_relevance.get("kipris", Counter())["adjacent"],
                "irrelevant_count": per_source_relevance.get("kipris", Counter())["irrelevant"],
                "alias_queries": kipris.diagnostic.query_metrics,
            },
            "kaia": {
                "received_count": kaia.diagnostic.received_count,
                "normalized_count": per_source_records["kaia_newtech"],
                "company_matched_count": per_source_match["kaia_newtech"],
            },
            "reconciliation": {
                "baseline_count": reconciliation["baseline_count"],
                "official_relevant_count": official_relevant_count,
                "existing_matched_count": reconciliation["existing_matched_count"],
                "manual_only_count": reconciliation["manual_only_count"],
                "net_new_count": reconciliation["net_new_count"],
                "conflict_count": reconciliation["conflict_count"],
                "ambiguous_count": reconciliation["ambiguous_company_count"],
                "duplicate_identity_count": reconciliation["duplicate_identity_count"],
            },
            "enrichment": {
                "application_date_enrichment_count": enrichment_counts["application_date"],
                "registration_date_enrichment_count": enrichment_counts["registration_date"],
                "status_enrichment_count": enrichment_counts["status"],
                "official_number_enrichment_count": official_number_enrichment_count,
            },
            "security": security,
        },
        "baseline_detail_count": len(detail["baseline_records"]),
        "net_new_records": detail["net_new_records"],
        "protected_public_hashes_before": protected_before,
        "protected_public_hashes_after": protected_after,
        "protected_public_data_unchanged": protected_before == protected_after,
        "acceptance_decision": decision,
    }


def build_acceptance_detail(
    companies: list[dict[str, Any]],
    normalized_records: Iterable[Any],
    reconciliation: dict[str, Any],
) -> dict[str, Any]:
    records_by_alias: dict[str, Any] = {}
    for record in normalized_records:
        for alias in record.identity_aliases():
            records_by_alias.setdefault(alias, record)
    decisions_by_identity = {
        decision["identity"]: decision
        for decision in reconciliation["decisions"]
    }

    details = []
    for baseline in baseline_technology_records(companies):
        official = next(
            (records_by_alias[alias] for alias in baseline.identity_aliases if alias in records_by_alias),
            None,
        )
        decision = decisions_by_identity.get(official.identity_key()) if official else None
        details.append({
            "baseline_title": baseline.record.get("name"),
            "baseline_official_number": (
                baseline.record.get("application_number")
                or baseline.record.get("registration_number")
                or baseline.record.get("patent_number")
                or baseline.record.get("newtech_number")
            ),
            "source": official.source if official else None,
            "official_identity": official.identity_key() if official else None,
            "match_status": decision.get("category") if decision else "manual_only",
            "official_title": official.title if official else None,
            "application_date": official.application_date if official else None,
            "registration_date": official.registration_date if official else None,
            "status": official.status if official else None,
            "relevance": decision.get("relevance", {}).get("level") if decision else None,
            "enrichment_fields": sorted((decision or {}).get("enrichment_fields") or {}),
        })
    details.sort(key=lambda item: (str(item["baseline_official_number"] or ""), str(item["baseline_title"] or "")))
    official_by_identity = {record.identity_key(): record for record in normalized_records}
    net_new = []
    for decision in reconciliation["decisions"]:
        if decision["category"] != "net_new":
            continue
        official = official_by_identity.get(decision["identity"])
        net_new.append({
            "official_identity": decision["identity"],
            "source": decision["source"],
            "external_id": decision["external_id"],
            "title": decision["title"],
            "applicants": list(official.applicants) if official else [],
            "application_date": official.application_date if official else None,
            "registration_date": official.registration_date if official else None,
            "status": official.status if official else None,
            "relevance": decision["relevance"]["level"],
            "technology_area": official.technology_area if official else None,
        })
    return {
        "schema_version": "company-technology-live-acceptance-detail-v1",
        "baseline_records": details,
        "net_new_records": net_new,
    }


def acceptance_decision(kipris_status: str, kaia_status: str) -> str:
    if kipris_status == "healthy" and kaia_status == "healthy":
        return "SAMSUNG_TECH_LIVE_SOURCE_ACCEPTANCE_COMPLETE"
    if kipris_status == "healthy":
        return "PARTIAL_SOURCE_ACCEPTANCE_KIPRIS_COMPLETE"
    if kipris_status in {"authentication_denied", "service_denied"}:
        return "HOLD_FOR_KIPRIS_ACCESS_APPROVAL"
    if kipris_status == "schema_error" or kaia_status == "schema_error":
        return "HOLD_FOR_LIVE_SCHEMA_REVIEW"
    if kaia_status in {"authentication_denied", "service_denied"}:
        return "HOLD_FOR_KAIA_ACCESS_APPROVAL"
    return "HOLD_FOR_LIVE_SCHEMA_REVIEW"


def security_metrics(
    *,
    normalized_payload: Any,
    candidates: Any,
    output_dir: Path,
    secrets: Iterable[str],
) -> dict[str, int]:
    credential_url_count = 0
    for row in [*normalized_payload, *candidates]:
        source_url = row.get("source_url") if isinstance(row, dict) else None
        if source_url:
            query_keys = {key.casefold() for key, _ in parse_qsl(urlsplit(source_url).query)}
            credential_url_count += int(bool(query_keys & SENSITIVE_QUERY_KEYS))

    raw_public_field_count = _count_forbidden_fields(candidates)
    secret_exposure_count = 0
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            secret_exposure_count += int(artifact_contains_credentials(text, secrets=secrets))
    return {
        "credential_url_count": credential_url_count,
        "secret_exposure_count": secret_exposure_count,
        "raw_public_field_count": raw_public_field_count,
    }


def hash_files(paths: Iterable[Path]) -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def _company_aliases(company: dict[str, Any]) -> tuple[str, ...]:
    values = (
        company.get("company_name"),
        company.get("legal_name"),
        company.get("display_name"),
        *(company.get("aliases") or []),
    )
    return tuple(dict.fromkeys(str(value).strip() for value in values if str(value or "").strip()))


def _baseline_newtech_numbers(company: dict[str, Any]) -> tuple[str, ...]:
    numbers = []
    for record in (company.get("technology") or {}).get("new_construction_technologies", []):
        value = (
            record.get("newtech_number")
            or record.get("registration_number")
            or ""
        )
        digits = "".join(character for character in str(value) if character.isdigit())
        if digits:
            numbers.append(digits)
    return tuple(dict.fromkeys(numbers))


def _write_raw_pages(output_dir: Path, results: Iterable[TechnologyCollectionResult]) -> None:
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for result in results:
        for index, content in enumerate(result.raw_pages, start=1):
            (raw_dir / f"{result.source}_{index:03d}.xml").write_text(content, encoding="utf-8")
        _write_json(raw_dir / f"{result.source}_diagnostic.json", result.diagnostic.as_dict())


def _count_forbidden_fields(payload: Any) -> int:
    count = 0
    if isinstance(payload, dict):
        count += sum(str(key).casefold() in RAW_PUBLIC_FORBIDDEN_FIELDS for key in payload)
        count += sum(_count_forbidden_fields(value) for value in payload.values())
    elif isinstance(payload, list):
        count += sum(_count_forbidden_fields(value) for value in payload)
    return count


def _content_hash(payload: Any) -> str:
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_markdown(path: Path, summary: dict[str, Any]) -> None:
    metrics = summary["metrics"]
    lines = [
        "# Samsung technology live source acceptance",
        "",
        f"- Decision: `{summary['acceptance_decision']}`",
        f"- KIPRIS status: `{metrics['source']['kipris_status']}`",
        f"- KAIA status: `{metrics['source']['kaia_status']}`",
        f"- Baseline: {metrics['reconciliation']['baseline_count']}",
        f"- Existing matched: {metrics['reconciliation']['existing_matched_count']}",
        f"- Manual only: {metrics['reconciliation']['manual_only_count']}",
        f"- Net new: {metrics['reconciliation']['net_new_count']}",
        f"- Conflicts: {metrics['reconciliation']['conflict_count']}",
        f"- Secret exposure: {metrics['security']['secret_exposure_count']}",
        f"- Public data unchanged: {str(summary['protected_public_data_unchanged']).lower()}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Samsung-only official technology source acceptance.")
    parser.add_argument("--companies", type=Path, default=DEFAULT_COMPANIES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--company-id", default=DEFAULT_COMPANY_ID)
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=False)
    else:
        load_dotenv(override=False)
    before = hash_files(PROTECTED_PUBLIC_FILES)
    summary = run_live_acceptance(
        companies_path=args.companies,
        output_dir=args.output_dir,
        company_id=args.company_id,
        protected_before=before,
    )
    safe_output = {
        "decision": summary["acceptance_decision"],
        "kipris_status": summary["metrics"]["source"]["kipris_status"],
        "kaia_status": summary["metrics"]["source"]["kaia_status"],
        "kipris_configured": summary["source_status"]["kipris"]["configured"],
        "kaia_configured": summary["source_status"]["kaia"]["configured"],
        "public_data_unchanged": summary["protected_public_data_unchanged"],
        "secret_exposure_count": summary["metrics"]["security"]["secret_exposure_count"],
    }
    print(json.dumps(safe_output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["acceptance_decision"] in {
        "SAMSUNG_TECH_LIVE_SOURCE_ACCEPTANCE_COMPLETE",
        "PARTIAL_SOURCE_ACCEPTANCE_KIPRIS_COMPLETE",
    } else 3


if __name__ == "__main__":
    raise SystemExit(main())
