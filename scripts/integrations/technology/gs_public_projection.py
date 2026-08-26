from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

from scripts.integrations.technology.base import (
    NormalizedTechnologyRecord,
    validate_public_source_url,
)
from scripts.integrations.technology.dry_run import load_companies
from scripts.integrations.technology.live_acceptance import (
    PROTECTED_PUBLIC_FILES,
    hash_files,
    security_metrics,
)
from scripts.integrations.technology.matching import match_companies
from scripts.integrations.technology.public_projection import (
    ALLOWED_ENRICHMENT_FIELDS,
    CompanyProjectionPolicy,
    ProjectionInputError,
    build_company_public_projection,
    build_public_evidence_source_id,
)
from scripts.integrations.technology.live_sources import KIPRIS_SOURCE_URL
from scripts.integrations.technology.readiness import (
    company_identity_for_alias_contract,
    validate_alias_contracts,
)


ROOT = Path(__file__).resolve().parents[3]
COMPANY_ID = "gs-ec"
DEFAULT_COMPANIES = ROOT / "frontend/public/data/companies/companies.json"
DEFAULT_READINESS = ROOT / "config/company_technology/kipris_expansion_readiness.json"
DEFAULT_INPUT_DIR = (
    ROOT
    / "artifacts/company-technology/multi-company-live/gs-ec/20260826T020500Z-final-reconciliation"
)
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts/company-technology/gs-public-projection-dry-run"
EXPECTED_COUNTS = {
    "baseline_count": 3,
    "enriched_existing_count": 3,
    "net_new_count": 4,
    "published_application_review_count": 3,
    "adjacent_review_count": 186,
    "excluded_applicant_count": 3,
    "candidate_total": 7,
}


def run_gs_public_projection(
    *,
    companies_path: Path = DEFAULT_COMPANIES,
    readiness_path: Path = DEFAULT_READINESS,
    input_dir: Path = DEFAULT_INPUT_DIR,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    required = {
        name: input_dir / name
        for name in (
            "final_reconciliation_summary.json",
            "existing_enrichment_candidates.json",
            "registered_publication_candidates.json",
            "published_application_review.json",
            "adjacent_review_only.json",
            "excluded_wrong_applicant.json",
            "security_audit.json",
        )
    }
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        raise ProjectionInputError(f"GS reconciliation artifacts are missing: {', '.join(missing)}")

    summary = _read_object(required["final_reconciliation_summary.json"])
    security = _read_object(required["security_audit.json"])
    if summary.get("decision") != "GS_FULL_CORPUS_FINAL_RECONCILIATION_COMPLETE":
        raise ProjectionInputError("GS final reconciliation is not accepted")
    if not security.get("passed") or int(security.get("secret_exposure") or 0):
        raise ProjectionInputError("GS reconciliation security audit is not clean")

    companies = load_companies(companies_path)
    company = _exactly_one(companies, "company_id", COMPANY_ID, "company")
    readiness = _read_object(readiness_path)
    contracts = list(readiness.get("companies") or [])
    contract = _exactly_one(contracts, "company_id", COMPANY_ID, "readiness contract")
    collisions = validate_alias_contracts(contracts)
    if any(collisions.values()):
        raise ProjectionInputError("readiness alias contracts contain collisions or invalid entries")
    identity = company_identity_for_alias_contract(company, contract)

    existing = _read_list(required["existing_enrichment_candidates.json"])
    registered = _read_list(required["registered_publication_candidates.json"])
    published = _read_list(required["published_application_review.json"])
    adjacent = _read_list(required["adjacent_review_only.json"])
    excluded = _read_list(required["excluded_wrong_applicant.json"])
    _validate_artifact_counts(existing, registered, published, adjacent, excluded)

    confirmed = [*_adapt_candidates(registered, identity), *_adapt_candidates(published, identity)]
    confirmed.extend(_adapt_candidates(adjacent, identity))
    wrong = list(_adapt_candidates(excluded, identity, expect_match=False))
    applicant_rows = [*confirmed, *wrong]
    exact_reports = [_adapt_existing(row) for row in existing]
    applicant_summary = {
        "net_new_records": [
            {"official_identity": row["official_identity"], "applicants": row.get("applicants") or []}
            for row in confirmed
        ]
    }

    protected_before = hash_files(PROTECTED_PUBLIC_FILES)
    projection = build_company_public_projection(
        companies=companies,
        exact_reports=exact_reports,
        status_reports=[],
        applicant_candidates=applicant_rows,
        applicant_summary=applicant_summary,
        policy=CompanyProjectionPolicy(
            company_id=COMPANY_ID,
            allowed_new_record_types=("patent",),
            allowed_new_statuses=("registered",),
            allowed_enrichment_fields=ALLOWED_ENRICHMENT_FIELDS,
            allow_status_updates=False,
            published_application_policy="review_only",
        ),
    )
    protected_after = hash_files(PROTECTED_PUBLIC_FILES)
    metrics = projection["metrics"]
    for key, expected in EXPECTED_COUNTS.items():
        if metrics.get(key) != expected:
            raise ProjectionInputError(f"GS projection metric drift: {key}={metrics.get(key)} expected={expected}")
    for key in ("removed_count", "conflict_count", "identity_collision_count", "ambiguous_count"):
        if metrics.get(key) != 0:
            raise ProjectionInputError(f"GS projection blocker: {key}={metrics.get(key)}")
    if protected_before != protected_after:
        raise ProjectionInputError("protected public data changed during GS projection")

    public_evidence_sources = [
        build_public_evidence_source_candidate(row, accessed_at=str(summary.get("generated_at") or ""))
        for row in registered
    ]
    candidate_company = deepcopy(company)
    candidate_company["technology"] = deepcopy(
        projection["candidate_company_technology"]["technology"]
    )
    existing_source_ids = {
        str(row.get("source_id") or "") for row in candidate_company.get("sources") or []
    }
    candidate_company["sources"] = [
        *deepcopy(list(candidate_company.get("sources") or [])),
        *[row for row in public_evidence_sources if row["source_id"] not in existing_source_ids],
    ]
    evidence_resolution = build_evidence_resolution_report(
        candidate_company,
        projection["candidate_company_technology"]["technology"]["patents"],
    )
    if evidence_resolution["linked_count"] != 4 or evidence_resolution["source_pending_count"]:
        raise ProjectionInputError("GS public evidence resolution is incomplete")
    if evidence_resolution["duplicate_source_id_count"]:
        raise ProjectionInputError("GS public evidence source IDs are not unique")

    generated_at = str(summary.get("generated_at") or "")
    if output_dir is None:
        stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
        output_dir = DEFAULT_OUTPUT_ROOT / stamp
    output_dir.mkdir(parents=True, exist_ok=False)
    outputs = {
        "candidate_company_technology.json": projection["candidate_company_technology"],
        "existing_diff_report.json": projection["existing_diff_report"],
        "registered_candidate_report.json": projection["registered_candidate_report"],
        "published_application_review.json": projection["published_application_review"],
        "adjacent_review_report.json": projection["adjacent_review_report"],
        "excluded_applicant_report.json": projection["excluded_applicant_report"],
        "public_evidence_sources.json": public_evidence_sources,
        "evidence_resolution_report.json": evidence_resolution,
    }
    for name, payload in outputs.items():
        _write_json(output_dir / name, payload)

    artifact_security = security_metrics(
        normalized_payload=public_evidence_sources,
        candidates=[*projection["candidate_company_technology"]["technology"]["patents"]],
        output_dir=output_dir,
        secrets=(),
    )
    local_path_exposure_count = _local_path_exposure_count(outputs)
    security_audit = {
        "schema_version": "gs-company-technology-public-projection-security-v1",
        **artifact_security,
        "local_path_exposure_count": local_path_exposure_count,
        "passed": not any(artifact_security.values()) and local_path_exposure_count == 0,
    }
    _write_json(output_dir / "security_audit.json", security_audit)
    if not security_audit["passed"]:
        raise ProjectionInputError("GS public evidence artifacts failed security validation")
    result = {
        "schema_version": "gs-company-technology-public-projection-summary-v1",
        "generated_at": generated_at,
        "company_id": COMPANY_ID,
        "policy": "registered_only_policy_a",
        **metrics,
        "external_calls": {
            "KIPRIS": 0,
            "KAIA": 0,
            "ST27": 0,
            "D2B": 0,
            "G2B": 0,
            "LLM": 0,
        },
        "public_write_performed": False,
        "protected_public_hashes_before": protected_before,
        "protected_public_hashes_after": protected_after,
        "protected_public_data_unchanged": True,
        "public_evidence_source_count": len(public_evidence_sources),
        "evidence_linked_count": evidence_resolution["linked_count"],
        "source_pending_count": evidence_resolution["source_pending_count"],
        "duplicate_source_id_count": evidence_resolution["duplicate_source_id_count"],
        "security": security_audit,
        "input_artifact_sha256": {
            path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in required.values()
        },
        "deterministic_content_sha256": {
            name: _content_hash(payload) for name, payload in outputs.items()
        },
        "decision": "GS_COMPANY_TECH_PUBLIC_PROJECTION_DRY_RUN_COMPLETE",
    }
    _write_json(output_dir / "projection_summary.json", result)
    _write_report(output_dir / "projection_report.md", result)
    return result


def build_public_evidence_source_candidate(
    row: dict[str, Any],
    *,
    accessed_at: str = "",
) -> dict[str, Any]:
    if row.get("source") != "kipris" or row.get("record_type") != "patent":
        raise ProjectionInputError("GS public evidence candidate must be a KIPRIS patent")
    title = str(row.get("title") or row.get("name") or "").strip()
    document_id = str(row.get("application_number") or "").strip()
    if not title or not document_id:
        raise ProjectionInputError("public patent evidence requires title and application number")
    accepted_source_url = validate_public_source_url(row.get("source_url"))
    if accepted_source_url != KIPRIS_SOURCE_URL:
        raise ProjectionInputError("public patent evidence must use the accepted KIPRIS portal URL")
    source_url = validate_public_source_url(KIPRIS_SOURCE_URL)
    return {
        "source_id": build_public_evidence_source_id(
            str(row["source"]),
            str(row["record_type"]),
            str(row.get("official_identity") or ""),
        ),
        "source_type": "patent",
        "source_name": "KIPRIS Plus",
        "title": title,
        "source_url": source_url,
        "published_at": None,
        "accessed_at": accessed_at or None,
        "publisher": "KIPRIS Plus",
        "document_id": document_id,
        "primary_source": True,
        "confidence": "high",
        "verification_status": "official",
        "verification_note": "Official KIPRIS patent evidence identified by application identity.",
        "supported_claims": [
            "technology",
            "patent",
            "patent_identity",
            "applicant_identity",
        ],
        "visibility": "public",
    }


def build_evidence_resolution_report(
    company: dict[str, Any],
    patents: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    source_rows = []
    seen = set()
    for group in (company.get("intelligence_v2") or {}).get("source_groups") or []:
        for source in group.get("sources") or []:
            source_id = str(source.get("source_id") or "")
            if source_id and source_id not in seen:
                source_rows.append(source)
                seen.add(source_id)
    registry_rows = list(company.get("sources") or [])
    source_id_counts: dict[str, int] = {}
    for source in registry_rows:
        source_id = str(source.get("source_id") or "")
        if source_id:
            source_id_counts[source_id] = source_id_counts.get(source_id, 0) + 1
        if source_id and source_id not in seen:
            source_rows.append(source)
            seen.add(source_id)
    available = {str(source.get("source_id") or "") for source in source_rows}
    rows = []
    for patent in patents:
        source_ids = sorted(set(patent.get("source_ids") or []))
        if not any(str(source_id).startswith("official:kipris:patent:") for source_id in source_ids):
            continue
        resolved = [source_id for source_id in source_ids if source_id in available]
        rows.append({
            "technology_id": patent.get("technology_id"),
            "source_ids": source_ids,
            "resolved_source_ids": resolved,
            "resolved_source_count": len(resolved),
            "evidence_status": "linked" if resolved else "source_pending",
        })
    return {
        "schema_version": "gs-public-evidence-resolution-v1",
        "company_id": company.get("company_id"),
        "records": rows,
        "linked_count": sum(row["evidence_status"] == "linked" for row in rows),
        "source_pending_count": sum(row["evidence_status"] == "source_pending" for row in rows),
        "duplicate_source_id_count": sum(count > 1 for count in source_id_counts.values()),
    }


def _local_path_exposure_count(payload: Any) -> int:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return len(re.findall(r"(?i)\b[a-z]:[\\/]", text))


def _adapt_existing(row: dict[str, Any]) -> dict[str, Any]:
    enrichment = {
        str(item["field"]): item.get("official_value")
        for item in row.get("enrichment_fields") or []
        if item.get("classification") == "SAFE_EMPTY_FIELD_ENRICHMENT"
        and item.get("field") in ALLOWED_ENRICHMENT_FIELDS
    }
    return {
        "baseline_technology_id": row.get("technology_id"),
        "match_decision": "MATCHED_OFFICIAL",
        "official_application_number": row.get("application_number"),
        "official_registration_number": row.get("registration_number"),
        "enrichment_fields": enrichment,
        "conflict_fields": list(row.get("conflicts") or []),
    }


def _adapt_candidates(
    rows: Iterable[dict[str, Any]],
    identity: Any,
    *,
    expect_match: bool = True,
) -> Iterable[dict[str, Any]]:
    for row in rows:
        record = NormalizedTechnologyRecord(
            source=str(row.get("source") or "kipris"),
            external_id=str(row.get("source_external_id") or row.get("official_identity") or ""),
            title=str(row.get("title") or ""),
            record_type=str(row.get("record_type") or "patent"),
            applicants=tuple(row.get("applicants") or ()),
            application_number=row.get("application_number"),
            registration_number=row.get("registration_number"),
            patent_number=row.get("patent_number"),
        )
        match = match_companies(record, [identity])
        matched = match.company_ids == (COMPANY_ID,) and match.outcome in {"exact", "normalized_alias"}
        if matched != expect_match:
            raise ProjectionInputError(
                f"GS applicant re-match drift for {row.get('official_identity')}: {match.outcome}"
            )
        adapted = dict(row)
        adapted.update({
            "name": row.get("title"),
            "candidate_type": "net_new",
            "company_ids": [COMPANY_ID] if matched else [],
            "company_match": match.outcome,
        })
        yield adapted


def _validate_artifact_counts(*groups: list[dict[str, Any]]) -> None:
    actual = tuple(len(group) for group in groups)
    expected = (3, 4, 3, 186, 3)
    if actual != expected:
        raise ProjectionInputError(f"GS accepted artifact count drift: {actual} expected={expected}")


def _exactly_one(rows: Iterable[dict[str, Any]], key: str, value: str, label: str) -> dict[str, Any]:
    matches = [row for row in rows if row.get(key) == value]
    if len(matches) != 1:
        raise ProjectionInputError(f"{label} must resolve exactly once: {value}")
    return matches[0]


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


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _content_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _write_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# GS E&C company-generic technology public projection",
        "",
        f"- Decision: `{summary['decision']}`",
        f"- Policy: `{summary['policy']}`",
        f"- Baseline: {summary['baseline_count']}",
        f"- Existing enriched: {summary['enriched_existing_count']}",
        f"- Registered new candidates: {summary['net_new_count']}",
        f"- Published application review: {summary['published_application_review_count']}",
        f"- Adjacent review only: {summary['adjacent_review_count']}",
        f"- Wrong applicant excluded: {summary['excluded_applicant_count']}",
        f"- Final candidate total: {summary['candidate_total']}",
        f"- Public evidence sources: {summary['public_evidence_source_count']}",
        f"- Evidence linked: {summary['evidence_linked_count']}",
        f"- Evidence source pending: {summary['source_pending_count']}",
        f"- Public write performed: {str(summary['public_write_performed']).lower()}",
        f"- Protected public data unchanged: {str(summary['protected_public_data_unchanged']).lower()}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the offline GS E&C Policy A public projection")
    parser.add_argument("--companies", type=Path, default=DEFAULT_COMPANIES)
    parser.add_argument("--readiness", type=Path, default=DEFAULT_READINESS)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    summary = run_gs_public_projection(
        companies_path=args.companies,
        readiness_path=args.readiness,
        input_dir=args.input_dir,
        output_dir=args.output_dir,
    )
    print(json.dumps({key: value for key, value in summary.items() if key == "decision" or key.endswith("_count") or key == "candidate_total"}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
