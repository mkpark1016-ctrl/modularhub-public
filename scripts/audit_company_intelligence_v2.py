#!/usr/bin/env python3
"""Generate the Company Intelligence V2 migration and truth-layer audit artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from migrate_company_intelligence_v2 import DEFAULT_COMPANIES, DEFAULT_OUTPUT, ROOT, read_json, write_json
from validate_company_intelligence_v2 import DEFAULT_PUBLIC_V2, validate_v2

OUTPUT_DIR = ROOT / "artifacts" / "company-intelligence-v2-truth-layer"


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def audit_v2(
    payload_path: Path = DEFAULT_OUTPUT,
    public_path: Path = DEFAULT_PUBLIC_V2,
    companies_path: Path = DEFAULT_COMPANIES,
    output_dir: Path = OUTPUT_DIR,
) -> dict[str, Any]:
    payload = read_json(payload_path)
    public = read_json(public_path)
    legacy = read_json(companies_path)
    validation = validate_v2(payload_path, public_path, companies_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    companies = {item["company_id"]: item for item in payload["companies"]}
    summaries = payload["materialized_summaries"]
    events = payload["events"]
    evidence = payload["evidence"]

    domain_rows = []
    for summary in summaries:
        domain_rows.append({
            "company_id": summary["company_id"],
            "company_name": companies[summary["company_id"]]["company_name"],
            "overall_data_status": summary["overall_data_status"],
            **summary["domain_statuses"],
        })
    domain_fields = ["company_id", "company_name", "overall_data_status", "identity_status", "financial_status", "production_status", "project_status", "technology_status", "recent_signal_status"]
    write_csv(output_dir / "company_domain_status.csv", domain_rows, domain_fields)

    type_counts = Counter((event["event_type"], event["event_status"], event["project_credit"]) for event in events)
    event_distribution = [
        {"event_type": key[0], "event_status": key[1], "project_credit": key[2], "count": count}
        for key, count in sorted(type_counts.items())
    ]
    write_csv(output_dir / "event_type_distribution.csv", event_distribution, ["event_type", "event_status", "project_credit", "count"])

    event_fields = ["event_id", "company_id", "title", "event_type", "event_status", "project_role", "project_credit", "verification_status", "source_count"]
    def event_row(event: dict[str, Any]) -> dict[str, Any]:
        return {**event, "source_count": len(event.get("source_ids", []))}
    write_csv(output_dir / "verified_project_inventory.csv", [event_row(event) for event in events if event["event_type"] == "project" and event["project_credit"]], event_fields)
    write_csv(output_dir / "project_candidate_inventory.csv", [event_row(event) for event in events if event["event_type"] == "project" and not event["project_credit"]], event_fields)
    write_csv(output_dir / "partnership_mou_inventory.csv", [event_row(event) for event in events if event["event_type"] in {"partnership", "mou"}], event_fields)
    write_csv(output_dir / "r_and_d_exhibition_inventory.csv", [event_row(event) for event in events if event["event_type"] in {"r_and_d", "exhibition"}], event_fields)

    duplicate_rows = payload.get("audit_metadata", {}).get("duplicate_event_clusters", [])
    write_csv(output_dir / "duplicate_event_clusters.csv", duplicate_rows, ["company_id", "kept_event_id", "merged_signal_id", "reason"])
    correction_rows = payload.get("audit_metadata", {}).get("correction_application_results", [])
    write_csv(output_dir / "correction_application_results.csv", correction_rows, ["correction_id", "target_id", "applied", "reason_code", "visibility"])

    visibility_rows = []
    for collection in ["companies", "facts", "events", "evidence", "corrections"]:
        canonical_counts = Counter(item.get("visibility") for item in payload.get(collection, []))
        public_counts = Counter(item.get("visibility") for item in public.get(collection, []))
        for visibility in sorted(set(canonical_counts) | set(public_counts)):
            visibility_rows.append({
                "collection": collection,
                "visibility": visibility,
                "canonical_count": canonical_counts[visibility],
                "public_export_count": public_counts[visibility],
                "violation": visibility != "public" and public_counts[visibility] > 0,
            })
    write_csv(output_dir / "public_private_visibility_audit.csv", visibility_rows, ["collection", "visibility", "canonical_count", "public_export_count", "violation"])
    write_csv(output_dir / "raw_ui_code_exposure.csv", validation.get("raw_ui_exposures", []), ["code", "offset", "match"])

    legacy_project_count = sum(len(company.get("project_portfolio") or []) for company in legacy["companies"])
    legacy_candidate_count = sum(len(company.get("project_candidates") or []) for company in legacy["companies"])
    before_after = [
        {"metric": "company_count", "before": len(legacy["companies"]), "after": len(payload["companies"])},
        {"metric": "legacy_project_records", "before": legacy_project_count, "after": legacy_project_count},
        {"metric": "legacy_candidate_records", "before": legacy_candidate_count, "after": legacy_candidate_count},
        {"metric": "v2_fact_count", "before": 0, "after": len(payload["facts"])},
        {"metric": "v2_event_count", "before": 0, "after": len(events)},
        {"metric": "v2_evidence_count", "before": 0, "after": len(evidence)},
        {"metric": "verified_project_credit_count", "before": "not_defined", "after": sum(1 for event in events if event["project_credit"])},
        {"metric": "article_evidence_count", "before": "mixed_candidate_metadata", "after": sum(1 for item in evidence if item["source_type"] == "media_article")},
    ]
    write_csv(output_dir / "before_after_company_counts.csv", before_after, ["metric", "before", "after"])
    write_csv(output_dir / "validation_errors.csv", validation["errors"], ["code", "path", "message", "severity"])

    overall_distribution = Counter(summary["overall_data_status"] for summary in summaries)
    domain_distribution = {
        field: dict(Counter(summary["domain_statuses"][field] for summary in summaries))
        for field in ["identity_status", "financial_status", "production_status", "project_status", "technology_status", "recent_signal_status"]
    }
    correction = next((row for row in correction_rows if row.get("correction_id") == "correction-yuchang-samsung-ai-modular-home"), None)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if validation["status"] == "PASS" else "HOLD_FOR_FIX",
        "company_count": len(payload["companies"]),
        "direct_competitor_count": sum(1 for company in payload["companies"] if company["competitive_role"] == "direct_competitor"),
        "fact_count": len(payload["facts"]),
        "event_count": len(events),
        "evidence_count": len(evidence),
        "verified_project_count": sum(1 for event in events if event["event_type"] == "project" and event["project_credit"]),
        "project_candidate_count": sum(1 for event in events if event["event_type"] == "project" and not event["project_credit"]),
        "partnership_mou_count": sum(1 for event in events if event["event_type"] in {"partnership", "mou"}),
        "r_and_d_exhibition_count": sum(1 for event in events if event["event_type"] in {"r_and_d", "exhibition"}),
        "duplicate_merged_event_count": len(duplicate_rows),
        "article_evidence_count": sum(1 for item in evidence if item["source_type"] == "media_article"),
        "yuchang_samsung_correction": correction,
        "overall_status_distribution": dict(overall_distribution),
        "domain_status_distribution": domain_distribution,
        "raw_ui_code_exposure_count": validation["metrics"]["raw_ui_code_exposure_count"],
        "english_summary_exposure_count": sum(1 for company in legacy["companies"] if not re_has_korean(company.get("intelligence_v2", {}).get("summary_ko"))),
        "internal_public_export_count": validation["metrics"]["internal_public_export_count"],
        "secret_exposure_count": validation["metrics"]["secret_exposure_count"],
        "validation_error_count": len(validation["errors"]),
        "source_hashes": payload.get("audit_metadata", {}).get("source_hashes", {}),
    }
    write_json(output_dir / "migration_audit.json", result)
    lines = [
        "# Company Intelligence V2 Truth Layer Audit",
        "",
        f"- Status: {result['status']}",
        f"- Companies: {result['company_count']}",
        f"- Facts / events / evidence: {result['fact_count']} / {result['event_count']} / {result['evidence_count']}",
        f"- Verified project credit / candidates: {result['verified_project_count']} / {result['project_candidate_count']}",
        f"- Partnership and MOU events: {result['partnership_mou_count']}",
        f"- Article evidence: {result['article_evidence_count']} (never included in project counts)",
        f"- Duplicate events merged: {result['duplicate_merged_event_count']}",
        f"- Raw UI code exposure: {result['raw_ui_code_exposure_count']}",
        f"- Internal records in public export: {result['internal_public_export_count']}",
        f"- Validation errors: {result['validation_error_count']}",
        "",
        "The YooChang/Samsung media cluster is classified as an unsigned partnership signal, not a project or signed MOU. Its articles remain evidence only.",
    ]
    (output_dir / "migration_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def re_has_korean(value: Any) -> bool:
    return bool(value and any("가" <= char <= "힣" for char in str(value)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--public", type=Path, default=DEFAULT_PUBLIC_V2)
    parser.add_argument("--companies", type=Path, default=DEFAULT_COMPANIES)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    result = audit_v2(args.input, args.public, args.companies, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
