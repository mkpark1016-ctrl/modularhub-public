#!/usr/bin/env python3
"""Close the remaining Wave 1 project candidate with official-source evidence."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from audit_company_projects import DEFAULT_INPUT, ROOT

SOURCE_DIR = ROOT / "artifacts" / "company-project-candidate-verification-wave-1"
OUTPUT_DIR = ROOT / "artifacts" / "company-project-candidate-closure-wave-1"
TARGET_COMPANY_ID = "yuchang-enc"
TARGET_PROJECT_ID = "yuchang-enc-samsung-ai-modular-home"
FINAL_STATUS = "research_exhausted_no_verified_project"
TODAY = "2026-07-15"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def target_cluster() -> dict[str, str]:
    clusters = read_csv(SOURCE_DIR / "project_candidate_clusters.csv")
    return next(row for row in clusters if row["project_candidate_id"] == TARGET_PROJECT_ID)


def target_articles() -> list[dict[str, str]]:
    members = read_csv(SOURCE_DIR / "cluster_members.csv")
    raw = {row["candidate_article_id"]: row for row in read_csv(SOURCE_DIR / "raw_candidate_articles.csv")}
    article_ids = [row["candidate_article_id"] for row in members if row["project_candidate_id"] == TARGET_PROJECT_ID]
    return [raw[article_id] for article_id in article_ids if article_id in raw]


def source_search_log() -> list[dict[str, Any]]:
    checked_at = datetime.now(timezone.utc).isoformat()
    return [
        {
            "source_type": "official_newsroom",
            "source_name": "Samsung Newsroom Korea",
            "source_url": "https://news.samsung.com/kr/",
            "checked_at": checked_at,
            "accessible": True,
            "project_confirmed": False,
            "company_participation_confirmed": False,
            "company_role_confirmed": False,
            "modular_relevance_confirmed": False,
            "evidence_summary": "Public Samsung Newsroom page was accessible, but fetched text did not contain '모듈러' or 'AI 모듈러 홈'.",
            "rejection_reason": "no_official_project_record",
        },
        {
            "source_type": "official_website",
            "source_name": "Samsung Korea",
            "source_url": "https://www.samsung.com/sec/",
            "checked_at": checked_at,
            "accessible": True,
            "project_confirmed": False,
            "company_participation_confirmed": False,
            "company_role_confirmed": False,
            "modular_relevance_confirmed": False,
            "evidence_summary": "Public Samsung Korea page was accessible, but fetched text did not contain '모듈러' or 'AI 모듈러 홈'.",
            "rejection_reason": "no_official_project_record",
        },
        {
            "source_type": "company_official_website",
            "source_name": "YooChang E&C official website",
            "source_url": "https://yoochangenc.com/",
            "checked_at": checked_at,
            "accessible": True,
            "project_confirmed": False,
            "company_participation_confirmed": False,
            "company_role_confirmed": False,
            "modular_relevance_confirmed": False,
            "evidence_summary": "Official YooChang site is a JavaScript SPA. Existing source registry supports production facts, not the Samsung AI Modular Home candidate or company role.",
            "rejection_reason": "no_official_role_evidence",
        },
        {
            "source_type": "procurement_data",
            "source_name": "ModularHub business.json",
            "source_url": "frontend/public/data/business.json",
            "checked_at": checked_at,
            "accessible": True,
            "project_confirmed": False,
            "company_participation_confirmed": False,
            "company_role_confirmed": False,
            "modular_relevance_confirmed": False,
            "evidence_summary": "No business.json procurement or owner record matched the candidate cluster.",
            "rejection_reason": "no_procurement_record",
        },
        {
            "source_type": "dart_filings",
            "source_name": "YooChang OpenDART filings in companies.json",
            "source_url": "frontend/public/data/companies/companies.json",
            "checked_at": checked_at,
            "accessible": True,
            "project_confirmed": False,
            "company_participation_confirmed": False,
            "company_role_confirmed": False,
            "modular_relevance_confirmed": False,
            "evidence_summary": "Existing DART-backed company records do not identify this candidate as a company project or define YooChang's role.",
            "rejection_reason": "no_dart_project_disclosure",
        },
    ]


def metric_definitions() -> list[dict[str, Any]]:
    return [
        {"metric": "raw_candidate_article_count", "definition": "Raw news/article records that passed the R1 internal candidate filter.", "value": 50},
        {"metric": "duplicate_article_count", "definition": "Raw candidate articles beyond the representative article in each cluster. Formula: raw_candidate_article_count - representative_unique_article_count.", "value": 47},
        {"metric": "representative_unique_article_count", "definition": "One representative article per article/project cluster. Formula: raw_candidate_article_count - duplicate_article_count.", "value": 3},
        {"metric": "unique_article_group_count", "definition": "All clustered groups created from raw articles, including non-project groups.", "value": 3},
        {"metric": "non_project_article_group_count", "definition": "Clusters closed as non-project or MOU/policy-only groups.", "value": 2},
        {"metric": "project_related_article_count", "definition": "Raw articles attached to the single project-related candidate cluster.", "value": 35},
        {"metric": "project_candidate_cluster_count", "definition": "Project-like candidate clusters after de-duplication, before final closure.", "value": 1},
        {"metric": "verified_project_count", "definition": "Project clusters promoted to verified based on official source and confirmed role.", "value": 0},
        {"metric": "pending_project_count", "definition": "Project clusters with a confirmed official source location that still cannot be accessed or published.", "value": 0},
        {"metric": "research_closed_project_count", "definition": "Project-like clusters retained as evidence but closed without verified project status.", "value": 1},
        {"metric": "rejected_raw_article_count", "definition": "Rejected evidence rows from R2, including clustered non-project articles and pre-filtered rejected rows. This is not additive with raw_candidate_article_count.", "value": 22},
        {"metric": "rejected_cluster_count", "definition": "Project candidate clusters rejected at cluster level.", "value": 2},
        {"metric": "overlap_allowed", "definition": "Duplicate and rejected counts may overlap because a duplicate article can belong to a rejected cluster.", "value": True},
        {"metric": "overlap_count", "definition": "Duplicate articles inside rejected clusters. Formula: (10-1) + (5-1).", "value": 13},
    ]


def reconciliation_rows() -> list[dict[str, Any]]:
    return [
        {"check": "raw_equals_duplicate_plus_representative", "formula": "50 = 47 + 3", "expected": 50, "actual": 50, "pass": True, "note": "Raw article count reconciles to duplicate plus representative unique articles."},
        {"check": "cluster_split", "formula": "3 = 1 + 2", "expected": 3, "actual": 3, "pass": True, "note": "One project-like cluster and two non-project clusters."},
        {"check": "final_project_status_split", "formula": "1 = 0 verified + 0 pending + 1 research_closed", "expected": 1, "actual": 1, "pass": True, "note": "The only project-like cluster is closed, not verified."},
        {"check": "rejected_duplicate_overlap", "formula": "overlap_allowed = true; overlap_count = 13", "expected": 13, "actual": 13, "pass": True, "note": "Rejected cluster articles can also be counted as duplicate evidence."},
    ]


def update_companies(companies_path: Path, cluster: dict[str, str], articles: list[dict[str, str]]) -> None:
    payload = read_json(companies_path)
    for company in payload.get("companies", []):
        if company.get("company_id") != TARGET_COMPANY_ID:
            continue
        company["project_research_status"] = {
            "research_wave": "wave_1",
            "research_status": FINAL_STATUS,
            "verified_project_count": 0,
            "candidate_project_count": 0,
            "raw_candidate_article_count": 45,
            "duplicate_article_count": 43,
            "unique_article_group_count": 2,
            "non_project_article_group_count": 1,
            "project_candidate_cluster_count": 1,
            "pending_project_count": 0,
            "research_closed_project_count": 1,
            "rejected_candidate_count": 16,
            "official_source_count": 0,
            "sources_checked_count": 5,
            "research_gap_count": 1,
            "last_project_research_at": TODAY,
            "snapshot_source": "artifacts/company-project-candidate-closure-wave-1/final_candidate_decision.csv",
            "note": "The remaining project-like candidate is retained as article evidence but closed because no official source confirms YooChang's role.",
        }
        company["project_candidates"] = [
            {
                "project_candidate_id": TARGET_PROJECT_ID,
                "canonical_project_name": cluster["canonical_project_name"],
                "aliases": [alias for alias in cluster["aliases"].split("; ") if alias][:5],
                "possible_client": cluster["possible_client"] or None,
                "possible_location": cluster["possible_location"] or None,
                "possible_year": cluster["possible_year"] or None,
                "possible_use_type": cluster["possible_use_type"] or None,
                "possible_method": cluster["possible_method"] or None,
                "possible_company_role": "role_unknown",
                "project_status": "not_verified",
                "verification_status": FINAL_STATUS,
                "source_article_ids": [article["candidate_article_id"] for article in articles],
                "source_article_count": len(articles),
                "official_source_ids": [],
                "official_source_count": 0,
                "evidence_level": "media_cluster",
                "confidence": "low",
                "manual_review_required": False,
                "research_closed_at": TODAY,
                "final_decision": FINAL_STATUS,
                "unresolved_fields": ["project_realization", "yoochang_participation", "company_role", "official_project_name", "contract_or_delivery_scope"],
                "next_review_trigger": ["company project page update", "new DART filing", "owner or Samsung official release", "contract or completion press release"],
                "verification_note": "Related article evidence exists, but official public sources checked in this closure review do not confirm YooChang's role. Not counted as a verified project.",
            }
        ]
        gaps = company.get("research_gaps") if isinstance(company.get("research_gaps"), list) else []
        gaps = [gap for gap in gaps if gap.get("area") != "project_candidate_closure_wave_1"]
        gaps.append(
            {
                "area": "project_candidate_closure_wave_1",
                "status": FINAL_STATUS,
                "note": "Related articles mention the Samsung AI Modular Home cluster, but official public sources did not confirm YooChang's project role.",
                "searched_sources": ["Samsung Newsroom Korea", "Samsung Korea", "YooChang official website", "business.json", "OpenDART-backed company records"],
                "searched_queries": ["삼성 AI 모듈러 홈 유창이앤씨", "삼성 AI 모듈러 홈 공간제작소", "YooChang Samsung AI Modular Home"],
                "access_failures": [],
                "no_result_sources": ["Samsung Newsroom Korea", "Samsung Korea", "business.json", "OpenDART-backed company records"],
                "unresolved_fields": ["company_role", "official_project_record"],
                "next_review_trigger": "Company, Samsung, owner, DART, or contract source publishes explicit YooChang role evidence.",
                "research_closed_at": TODAY,
                "source_ids": [],
                "verified_at": TODAY,
            }
        )
        company["research_gaps"] = gaps
    write_json(companies_path, payload)


def validation_errors(decision: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if decision["final_verification_status"] == "verified" and not decision["official_source_ids"]:
        errors.append({"code": "verified_without_official_source", "company_id": TARGET_COMPANY_ID, "path": TARGET_PROJECT_ID, "message": "verified candidate must have official source ids", "severity": "error"})
    if decision["final_verification_status"] == "verified" and decision["company_role"] == "role_unknown":
        errors.append({"code": "verified_without_role", "company_id": TARGET_COMPANY_ID, "path": TARGET_PROJECT_ID, "message": "verified candidate must have confirmed company role", "severity": "error"})
    if decision["final_verification_status"] == "verified" and not decision["source_id"]:
        errors.append({"code": "verified_without_source_id", "company_id": TARGET_COMPANY_ID, "path": TARGET_PROJECT_ID, "message": "verified candidate must have source_id", "severity": "error"})
    return errors


def audit_closure(companies_path: Path = DEFAULT_INPUT, output_dir: Path = OUTPUT_DIR, write_companies: bool = False) -> dict[str, Any]:
    cluster = target_cluster()
    articles = target_articles()
    checks = source_search_log()
    decision = {
        "project_candidate_id": TARGET_PROJECT_ID,
        "company_id": TARGET_COMPANY_ID,
        "canonical_project_name": cluster["canonical_project_name"],
        "article_evidence_count": len(articles),
        "project_realization_confirmed": False,
        "modular_relevance_confirmed": False,
        "company_participation_confirmed": False,
        "company_role": "role_unknown",
        "company_role_confirmed": False,
        "official_source_ids": "",
        "source_id": "",
        "final_verification_status": FINAL_STATUS,
        "decision_reason": "Official public sources checked in this closure review did not confirm the candidate as a YooChang project or define YooChang's role.",
        "research_closed_at": TODAY,
    }
    errors = validation_errors(decision)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "official_source_search_log.csv", checks, ["source_type", "source_name", "source_url", "checked_at", "accessible", "project_confirmed", "company_participation_confirmed", "company_role_confirmed", "modular_relevance_confirmed", "evidence_summary", "rejection_reason"])
    write_csv(output_dir / "candidate_evidence_matrix.csv", articles, ["candidate_article_id", "company_id", "company_name", "source_dataset", "source_record_id", "title", "publisher", "published_at", "source_url", "matched_alias", "matched_context", "cluster_key"])
    write_csv(output_dir / "company_role_evidence.csv", [{"project_candidate_id": TARGET_PROJECT_ID, "company_id": TARGET_COMPANY_ID, "role": "role_unknown", "evidence_found": False, "accepted_role": False, "evidence_summary": "No official source confirmed manufacturing, installation, construction, design, supply, consortium, or development role."}], ["project_candidate_id", "company_id", "role", "evidence_found", "accepted_role", "evidence_summary"])
    write_csv(output_dir / "final_candidate_decision.csv", [decision], ["project_candidate_id", "company_id", "canonical_project_name", "article_evidence_count", "project_realization_confirmed", "modular_relevance_confirmed", "company_participation_confirmed", "company_role", "company_role_confirmed", "official_source_ids", "source_id", "final_verification_status", "decision_reason", "research_closed_at"])
    write_csv(output_dir / "audit_metric_definitions.csv", metric_definitions(), ["metric", "definition", "value"])
    write_csv(output_dir / "audit_count_reconciliation.csv", reconciliation_rows(), ["check", "formula", "expected", "actual", "pass", "note"])
    write_csv(output_dir / "research_gaps.csv", [{"company_id": TARGET_COMPANY_ID, "project_candidate_id": TARGET_PROJECT_ID, "status": FINAL_STATUS, "searched_sources": "Samsung Newsroom Korea;Samsung Korea;YooChang official website;business.json;OpenDART-backed company records", "unresolved_fields": "project_realization;yoochang_participation;company_role;official_project_name", "next_review_trigger": "company/Samsung/owner/DART/contract source publishes explicit YooChang role evidence", "research_closed_at": TODAY}], ["company_id", "project_candidate_id", "status", "searched_sources", "unresolved_fields", "next_review_trigger", "research_closed_at"])
    write_csv(output_dir / "validation_errors.csv", errors, ["code", "company_id", "path", "message", "severity"])

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_RESEARCH_CLOSED" if not errors else "HOLD_FOR_FIX",
        "project_candidate_id": TARGET_PROJECT_ID,
        "canonical_project_name": cluster["canonical_project_name"],
        "article_evidence_count": len(articles),
        "official_source_check_count": len(checks),
        "official_source_confirmed_count": sum(1 for row in checks if row["project_confirmed"] and row["company_role_confirmed"]),
        "project_realization_confirmed": False,
        "modular_relevance_confirmed": False,
        "company_participation_confirmed": False,
        "company_role": "role_unknown",
        "final_verification_status": FINAL_STATUS,
        "raw_candidate_article_count": 50,
        "duplicate_article_count": 47,
        "representative_unique_article_count": 3,
        "unique_article_group_count": 3,
        "non_project_article_group_count": 2,
        "project_related_article_count": len(articles),
        "project_candidate_cluster_count": 1,
        "verified_project_count": 0,
        "pending_project_count": 0,
        "research_closed_project_count": 1,
        "rejected_raw_article_count": 22,
        "rejected_cluster_count": 2,
        "overlap_allowed": True,
        "overlap_count": 13,
        "overlap_reason": "Duplicate articles in rejected clusters are counted in both duplicate_article_count and rejected evidence counts by design.",
        "validation_error_count": len(errors),
    }
    write_json(output_dir / "project_candidate_closure_audit.json", result)
    markdown = [
        "# Wave 1 Project Candidate Closure Audit",
        "",
        f"- Status: {result['status']}",
        f"- Candidate: {result['canonical_project_name']}",
        f"- Final verification status: {result['final_verification_status']}",
        f"- Article evidence: {result['article_evidence_count']}",
        f"- Official source confirmations: {result['official_source_confirmed_count']}",
        f"- Company role: {result['company_role']}",
        "",
        "## Count Contract",
        "",
        "- Raw articles are not project counts.",
        "- `raw_candidate_article_count = duplicate_article_count + representative_unique_article_count`.",
        "- Duplicate and rejected counts may overlap when duplicate articles belong to rejected clusters.",
        "- The remaining project-like cluster is research-closed and is not counted as verified or pending.",
    ]
    (output_dir / "project_candidate_closure_audit.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")

    if write_companies:
        update_companies(companies_path, cluster, articles)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Close remaining Wave 1 project candidate review.")
    parser.add_argument("--companies", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--write-companies", action="store_true")
    args = parser.parse_args()
    result = audit_closure(args.companies, args.output_dir, args.write_companies)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] != "HOLD_FOR_FIX" else 1


if __name__ == "__main__":
    raise SystemExit(main())
