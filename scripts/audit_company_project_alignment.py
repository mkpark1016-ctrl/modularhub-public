#!/usr/bin/env python3
"""Audit Wave 1 project target alignment and generate internal candidates."""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from audit_company_projects import (
    DEFAULT_INPUT,
    ROOT,
    has_primary_source,
    is_verified_project,
    project_coverage,
    select_wave_targets,
)
from validate_company_projects import validate_company_projects

DEFAULT_BUSINESS = ROOT / "frontend" / "public" / "data" / "business.json"
DEFAULT_NEWS = ROOT / "frontend" / "public" / "data" / "news.json"
DEFAULT_ARTIFACT_DIR = ROOT / "artifacts" / "company-project-portfolio-wave-1-r1"
PROJECT_CONTEXT_TERMS = ("수주", "발주", "제작", "납품", "설치", "준공", "공사", "프로젝트", "출시", "협업", "계약")
MODULAR_TERMS = ("모듈러", "OSC", "프리패브", "prefab", "modular")
REJECT_CONTEXT_TERMS = ("채용", "주가", "재무", "실적 발표", "행사", "박람회", "인사")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def aliases_for(company: dict[str, Any]) -> list[str]:
    values = [company.get("company_name"), company.get("company_name_en"), *(company.get("aliases") or [])]
    seen: set[str] = set()
    aliases: list[str] = []
    for value in values:
        text = str(value or "").strip()
        key = normalize(text)
        if text and key not in seen:
            seen.add(key)
            aliases.append(text)
    return aliases


def first_match(text: str, terms: tuple[str, ...] | list[str]) -> str | None:
    lower = normalize(text)
    for term in terms:
        if normalize(term) in lower:
            return term
    return None


def context_excerpt(text: str, alias: str, width: int = 80) -> str:
    index = normalize(text).find(normalize(alias))
    if index < 0:
        return text[: width * 2]
    start = max(0, index - width)
    end = min(len(text), index + len(alias) + width)
    return text[start:end].strip()


def business_text(record: dict[str, Any]) -> str:
    fields = [
        "title",
        "organization",
        "demand_org",
        "summary",
        "keywords",
        "project_name",
        "source_record_id",
        "source_record_no",
    ]
    return " ".join(str(record.get(field) or "") for field in fields)


def news_text(record: dict[str, Any]) -> str:
    return " ".join(str(record.get(field) or "") for field in ("title", "summary", "keywords", "media", "publisher_name"))


def candidate_status(text: str, dataset: str) -> tuple[str, str, str]:
    if first_match(text, REJECT_CONTEXT_TERMS):
        return "rejected", "low", "excluded_context"
    modular = first_match(text, MODULAR_TERMS)
    project = first_match(text, PROJECT_CONTEXT_TERMS)
    if modular and project:
        if dataset == "business":
            return "verification_pending", "official_notice_candidate", "alias_modular_project_context"
        return "verification_pending", "media_candidate", "alias_modular_project_context"
    if modular:
        return "rejected", "low", "modular_context_without_project_role"
    return "rejected", "low", "alias_without_modular_project_context"


def generate_candidates(
    companies: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    business_rows: list[dict[str, Any]],
    news_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for company in targets:
        for dataset_name, rows, text_fn in (
            ("business", business_rows, business_text),
            ("news", news_rows, news_text),
        ):
            for record in rows:
                text = text_fn(record)
                matched_alias = first_match(text, aliases_for(company))
                if not matched_alias:
                    continue
                review_status, evidence_level, reason = candidate_status(text, dataset_name)
                row = {
                    "candidate_id": f"{dataset_name}-{company['company_id']}-{record.get('id') or record.get('source_record_id')}",
                    "company_id": company.get("company_id"),
                    "company_name": company.get("company_name"),
                    "candidate_title": record.get("title") or record.get("project_name"),
                    "candidate_type": "internal_project_candidate",
                    "source_dataset": dataset_name,
                    "source_record_id": record.get("id") or record.get("source_record_id"),
                    "source_url": record.get("external_original_url") or record.get("original_url") or record.get("naver_url"),
                    "matched_alias": matched_alias,
                    "matched_context": context_excerpt(text, matched_alias),
                    "possible_client": record.get("organization") or record.get("demand_org"),
                    "possible_location": record.get("region"),
                    "possible_role": None,
                    "possible_project_status": "candidate",
                    "evidence_level": evidence_level,
                    "review_status": review_status,
                    "rejection_reason": "" if review_status == "verification_pending" else reason,
                }
                if review_status == "verification_pending":
                    candidates.append(row)
                else:
                    rejected.append(row)
    # Avoid repeating the same article/notice per company in the primary candidate list.
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in candidates:
        key = (str(row["company_id"]), str(row["source_dataset"]), str(row["source_record_id"]))
        unique.setdefault(key, row)
    return list(unique.values()), rejected


def classify_projects(companies: list[dict[str, Any]], target_ids: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for company in companies:
        for project in company.get("project_portfolio", []) or []:
            is_target = company.get("company_id") in target_ids
            enrichment_status = project.get("enrichment_status") or ("wave1_verified_new" if is_target and is_verified_project(project) else "preexisting_verified")
            if not is_target and is_verified_project(project):
                classification = "preexisting_verified"
            elif is_target and is_verified_project(project):
                classification = "wave1_verified_new"
            else:
                classification = "unverified"
            rows.append(
                {
                    "company_id": company.get("company_id"),
                    "company_name": company.get("company_name"),
                    "project_id": project.get("project_id"),
                    "project_name": project.get("project_name"),
                    "is_wave1_target": is_target,
                    "classification": classification,
                    "research_wave": project.get("research_wave") or ("baseline" if not is_target else "wave_1"),
                    "enrichment_status": enrichment_status,
                    "evidence_status": project.get("evidence_status"),
                    "company_role": project.get("company_role"),
                    "source_count": len(project.get("source_ids", []) or []),
                    "primary_source": has_primary_source(company, project),
                }
            )
    return rows


def company_research_rows(targets: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_company: dict[str, list[dict[str, Any]]] = {}
    for row in candidates:
        by_company.setdefault(str(row["company_id"]), []).append(row)
    rows: list[dict[str, Any]] = []
    for company in targets:
        projects = company.get("project_portfolio", []) or []
        verified = [project for project in projects if is_verified_project(project)]
        candidate_count = len(by_company.get(str(company.get("company_id")), []))
        status = "verified_projects_available" if verified else "candidate_projects_found" if candidate_count else "research_gap"
        rows.append(
            {
                "company_id": company.get("company_id"),
                "company_name": company.get("company_name"),
                "research_status": status,
                "verified_project_count": len(verified),
                "candidate_project_count": candidate_count,
                "official_sources_checked": "existing_company_sources;internal_business_news",
                "datasets_checked": "business.json;news.json;companies.json",
                "research_gap_count": 0 if verified or candidate_count else 1,
                "last_project_research_at": datetime.now(timezone.utc).date().isoformat(),
            }
        )
    return rows


def audit_alignment(
    companies_path: Path = DEFAULT_INPUT,
    business_path: Path = DEFAULT_BUSINESS,
    news_path: Path = DEFAULT_NEWS,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
) -> dict[str, Any]:
    company_payload = read_json(companies_path)
    companies = company_payload.get("companies", [])
    business_rows = read_json(business_path).get("items", [])
    news_rows = read_json(news_path).get("items", [])
    targets = select_wave_targets(companies)
    target_ids = {str(company.get("company_id")) for company in targets}
    candidates, rejected = generate_candidates(companies, targets, business_rows, news_rows)
    classifications = classify_projects(companies, target_ids)
    company_rows = company_research_rows(targets, candidates)
    validation = validate_company_projects(companies_path)

    artifact_dir.mkdir(parents=True, exist_ok=True)
    snapshot_rows = [
        {
            "company_id": company.get("company_id"),
            "company_name": company.get("company_name"),
            "competition_relation": company.get("competitive_role"),
            "tier": company.get("analysis_tier"),
            "selection_reason": project_coverage(company).get("project_gap_score"),
            "snapshot_source": "dynamic_project_gap_selection",
        }
        for company in targets
    ]
    write_csv(artifact_dir / "wave1_target_snapshot.csv", snapshot_rows, ["company_id", "company_name", "competition_relation", "tier", "selection_reason", "snapshot_source"])
    write_csv(artifact_dir / "project_classification.csv", classifications, ["company_id", "company_name", "project_id", "project_name", "is_wave1_target", "classification", "research_wave", "enrichment_status", "evidence_status", "company_role", "source_count", "primary_source"])
    write_csv(artifact_dir / "wave1_company_coverage.csv", company_rows, ["company_id", "company_name", "research_status", "verified_project_count", "candidate_project_count", "official_sources_checked", "datasets_checked", "research_gap_count", "last_project_research_at"])
    candidate_fields = ["candidate_id", "company_id", "company_name", "candidate_title", "candidate_type", "source_dataset", "source_record_id", "source_url", "matched_alias", "matched_context", "possible_client", "possible_location", "possible_role", "possible_project_status", "evidence_level", "review_status", "rejection_reason"]
    write_csv(artifact_dir / "project_candidates.csv", candidates, candidate_fields)
    write_csv(artifact_dir / "business_candidate_matches.csv", [row for row in candidates if row["source_dataset"] == "business"], candidate_fields)
    write_csv(artifact_dir / "news_candidate_matches.csv", [row for row in candidates if row["source_dataset"] == "news"], candidate_fields)
    write_csv(artifact_dir / "rejected_candidates.csv", rejected, candidate_fields)
    write_csv(artifact_dir / "verified_wave1_projects.csv", [row for row in classifications if row["classification"] == "wave1_verified_new"], ["company_id", "company_name", "project_id", "project_name", "classification", "evidence_status", "company_role", "source_count", "primary_source"])
    write_csv(artifact_dir / "preexisting_verified_projects.csv", [row for row in classifications if row["classification"] == "preexisting_verified"], ["company_id", "company_name", "project_id", "project_name", "classification", "evidence_status", "company_role", "source_count", "primary_source"])
    write_csv(artifact_dir / "source_check_matrix.csv", company_rows, ["company_id", "company_name", "official_sources_checked", "datasets_checked", "research_status"])
    write_csv(artifact_dir / "research_gaps.csv", [row for row in company_rows if row["research_gap_count"]], ["company_id", "company_name", "research_status", "datasets_checked", "research_gap_count", "last_project_research_at"])

    validation_errors = list(validation.get("issues", []))
    non_target_wave1 = [row for row in classifications if row["classification"] == "wave1_verified_new" and not row["is_wave1_target"]]
    if non_target_wave1:
        for row in non_target_wave1:
            validation_errors.append({"code": "non_target_project_counted_as_wave1", "company_id": row["company_id"], "path": row["project_id"], "message": "non-target project counted as Wave 1", "severity": "error"})
    candidate_verified = [row for row in candidates if row["review_status"] == "verified"]
    if candidate_verified:
        for row in candidate_verified:
            validation_errors.append({"code": "candidate_marked_verified", "company_id": row["company_id"], "path": row["candidate_id"], "message": "candidate cannot be verified without promotion", "severity": "error"})
    write_csv(artifact_dir / "validation_errors.csv", validation_errors, ["code", "company_id", "path", "message", "severity"])

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "wave1_targets": [company.get("company_id") for company in targets],
        "total_verified_projects": sum(1 for row in classifications if row["classification"] in {"preexisting_verified", "wave1_verified_new"}),
        "preexisting_verified_projects": sum(1 for row in classifications if row["classification"] == "preexisting_verified"),
        "wave1_verified_projects": sum(1 for row in classifications if row["classification"] == "wave1_verified_new"),
        "wave1_candidate_projects": len(candidates),
        "wave1_target_companies_with_verified_projects": sum(1 for row in company_rows if row["verified_project_count"]),
        "wave1_target_companies_with_candidates": sum(1 for row in company_rows if row["candidate_project_count"]),
        "wave1_target_companies_with_research_gaps": sum(1 for row in company_rows if row["research_gap_count"]),
        "business_candidate_count": sum(1 for row in candidates if row["source_dataset"] == "business"),
        "news_candidate_count": sum(1 for row in candidates if row["source_dataset"] == "news"),
        "rejected_candidate_count": len(rejected),
        "non_target_wave1_count": len(non_target_wave1),
        "candidate_marked_verified_count": len(candidate_verified),
        "validation_error_count": sum(1 for row in validation_errors if row.get("severity") == "error"),
        "validation_errors": validation_errors,
    }
    status = "PASS_WITH_RESEARCH_GAPS" if result["validation_error_count"] == 0 else "HOLD_FOR_FIX"
    result["status"] = status
    (artifact_dir / "wave1_alignment_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = [
        "# Wave 1 Project Alignment Audit",
        "",
        f"- Status: {status}",
        f"- Wave 1 targets: {', '.join(result['wave1_targets'])}",
        f"- Total verified projects: {result['total_verified_projects']}",
        f"- Preexisting verified projects: {result['preexisting_verified_projects']}",
        f"- Wave 1 verified projects: {result['wave1_verified_projects']}",
        f"- Wave 1 candidate projects: {result['wave1_candidate_projects']}",
        f"- Non-target projects counted as Wave 1: {result['non_target_wave1_count']}",
        "",
        "## Company Coverage",
        "",
        "| Company | Status | Verified | Candidates | Gaps |",
        "|---|---|---:|---:|---:|",
    ]
    for row in company_rows:
        markdown.append(f"| {row['company_name']} | {row['research_status']} | {row['verified_project_count']} | {row['candidate_project_count']} | {row['research_gap_count']} |")
    (artifact_dir / "wave1_alignment_audit.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Wave 1 project target alignment.")
    parser.add_argument("--companies", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--business", type=Path, default=DEFAULT_BUSINESS)
    parser.add_argument("--news", type=Path, default=DEFAULT_NEWS)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    args = parser.parse_args()
    result = audit_alignment(args.companies, args.business, args.news, args.artifact_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] != "HOLD_FOR_FIX" else 1


if __name__ == "__main__":
    raise SystemExit(main())
