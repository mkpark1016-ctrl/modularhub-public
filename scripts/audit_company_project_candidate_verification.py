#!/usr/bin/env python3
"""Cluster Wave 1 raw project articles and audit candidate verification status."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from audit_company_project_alignment import DEFAULT_ARTIFACT_DIR as ALIGNMENT_ARTIFACT_DIR
from audit_company_project_alignment import audit_alignment
from audit_company_projects import DEFAULT_INPUT, ROOT, select_wave_targets

DEFAULT_OUTPUT = ROOT / "artifacts" / "company-project-candidate-verification-wave-1"
DEFAULT_COMPANIES = DEFAULT_INPUT
RAW_CANDIDATE_FILE = ALIGNMENT_ARTIFACT_DIR / "project_candidates.csv"
R1_REJECTED_FILE = ALIGNMENT_ARTIFACT_DIR / "rejected_candidates.csv"

PENDING_ROLE = "role_unknown"
TODAY = "2026-07-15"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def normalize_text(value: Any) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]|㈜|주식회사|\(주\)", " ", text)
    text = re.sub(r"[^\w가-힣]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def article_text(row: dict[str, Any]) -> str:
    return " ".join(str(row.get(field) or "") for field in ("candidate_title", "matched_context", "possible_client", "possible_location"))


def cluster_key(row: dict[str, Any]) -> tuple[str, str]:
    text = normalize_text(article_text(row))
    company_id = str(row.get("company_id") or "")
    if any(term in text for term in ("ai 모듈러 홈", "ai 모듈러홈", "공간제작소", "smartthings", "스마트싱스", "화성")):
        return company_id, "samsung-ai-modular-home"
    if any(term in text for term in ("공동주택형 모듈러", "업무협약", "mou", "협약")):
        return company_id, "samsung-apartment-modular-mou"
    if any(term in text for term in ("해외수주", "해외건설", "중동", "수주 다변화", "간담회", "정부")):
        return company_id, "overseas-construction-policy-meeting"
    tokens = [token for token in text.split() if token not in {"모듈러", "프로젝트", "사업", "공사", "출시", "기사"}]
    return company_id, "-".join(tokens[:8]) or "unclassified"


def cluster_name(key: str) -> str:
    return {
        "samsung-ai-modular-home": "삼성 AI 모듈러 홈",
        "samsung-apartment-modular-mou": "삼성전자 공동주택형 모듈러 주택 개발 업무협약",
        "overseas-construction-policy-meeting": "해외건설 수주 다변화 간담회",
    }.get(key, key.replace("-", " "))


def cluster_rejection_reason(key: str, rows: list[dict[str, Any]]) -> str:
    text = normalize_text(" ".join(article_text(row) for row in rows))
    if key == "overseas-construction-policy-meeting":
        return "market_article"
    if key == "samsung-apartment-modular-mou":
        return "mou_only"
    if not any(term in text for term in ("공사", "납품", "제작", "설치", "준공", "수주", "발주", "프로젝트", "홈")):
        return "no_project_entity"
    return ""


def priority_for_cluster(key: str, rows: list[dict[str, Any]], rejection_reason: str) -> tuple[int, str, list[str]]:
    if rejection_reason:
        return 20, "P3", [rejection_reason]
    text = normalize_text(" ".join(article_text(row) for row in rows))
    score = 30
    reasons: list[str] = []
    if len({row.get("source_url") for row in rows if row.get("source_url")}) > 1:
        score += 12
        reasons.append("복수 기사")
    if any(term in text for term in ("삼성전자", "공간제작소")):
        score += 12
        reasons.append("참여기관 명시")
    if any(term in text for term in ("제작", "생산", "설치", "출시")):
        score += 10
        reasons.append("제작·출시 문맥")
    if key == "samsung-ai-modular-home":
        score += 8
        reasons.append("프로젝트명 고유성")
    if not reasons:
        reasons.append("검증 정보 부족")
    if score >= 60:
        return score, "P1", reasons
    if score >= 40:
        return score, "P2", reasons
    return score, "P3", reasons


def official_source_checks_for(cluster: dict[str, Any]) -> list[dict[str, Any]]:
    if cluster["verification_status"] != "official_source_pending":
        return []
    query = f"{cluster['canonical_project_name']} {cluster['company_name']}"
    return [
        {
            "project_candidate_id": cluster["project_candidate_id"],
            "company_id": cluster["company_id"],
            "check_target": "company_or_partner_official_material",
            "query": query,
            "status": "not_confirmed",
            "official_source_id": "",
            "note": "No first-party source in the repository confirms the Wave 1 company role for this candidate.",
        },
        {
            "project_candidate_id": cluster["project_candidate_id"],
            "company_id": cluster["company_id"],
            "check_target": "procurement_or_owner_record",
            "query": query,
            "status": "not_found_in_internal_data",
            "official_source_id": "",
            "note": "No business.json procurement candidate matched this project cluster.",
        },
    ]


def build_raw_articles(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        article_id = f"article-{row.get('company_id')}-{row.get('source_dataset')}-{row.get('source_record_id')}"
        key = (str(row.get("company_id")), str(row.get("source_dataset")), str(row.get("source_record_id")))
        if key in seen:
            continue
        seen.add(key)
        articles.append(
            {
                "candidate_article_id": article_id,
                "company_id": row.get("company_id"),
                "company_name": row.get("company_name"),
                "source_dataset": row.get("source_dataset"),
                "source_record_id": row.get("source_record_id"),
                "title": row.get("candidate_title"),
                "publisher": "",
                "published_at": "",
                "source_url": row.get("source_url"),
                "matched_alias": row.get("matched_alias"),
                "matched_context": row.get("matched_context"),
                "cluster_key": cluster_key(row)[1],
            }
        )
    return articles


def build_clusters(rows: list[dict[str, str]], companies_by_id: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[cluster_key(row)].append(row)

    clusters: list[dict[str, Any]] = []
    cluster_members: list[dict[str, Any]] = []
    duplicate_articles: list[dict[str, Any]] = []
    for (company_id, key), members in sorted(grouped.items()):
        company = companies_by_id.get(company_id, {})
        source_article_ids = [f"article-{row.get('company_id')}-{row.get('source_dataset')}-{row.get('source_record_id')}" for row in members]
        rejection_reason = cluster_rejection_reason(key, members)
        score, level, reasons = priority_for_cluster(key, members, rejection_reason)
        verification_status = "rejected" if rejection_reason else "official_source_pending"
        cluster = {
            "project_candidate_id": f"{company_id}-{key}",
            "company_id": company_id,
            "company_name": company.get("company_name") or members[0].get("company_name"),
            "canonical_project_name": cluster_name(key),
            "aliases": "; ".join(sorted({str(row.get("candidate_title") or "")[:80] for row in members if row.get("candidate_title")})),
            "possible_client": "삼성전자" if key.startswith("samsung-") else "",
            "possible_location": "경기 화성" if key == "samsung-ai-modular-home" else "",
            "possible_year": "2026" if key == "samsung-ai-modular-home" else "",
            "possible_use_type": "single_family_modular_home" if key == "samsung-ai-modular-home" else "",
            "possible_method": "steel_modular_unconfirmed" if key.startswith("samsung-") else "",
            "possible_company_role": PENDING_ROLE,
            "project_status": "candidate" if not rejection_reason else "not_project",
            "verification_status": verification_status,
            "source_article_ids": ";".join(source_article_ids),
            "source_count": len(source_article_ids),
            "official_source_ids": "",
            "evidence_level": "media_cluster" if not rejection_reason else "rejected_context",
            "confidence": "low" if rejection_reason else "medium",
            "rejection_reason": rejection_reason,
            "manual_review_required": "true" if not rejection_reason else "false",
            "verification_priority_score": score,
            "verification_priority_level": level,
            "priority_reasons": ";".join(reasons),
        }
        clusters.append(cluster)
        for index, row in enumerate(members):
            article_id = f"article-{row.get('company_id')}-{row.get('source_dataset')}-{row.get('source_record_id')}"
            cluster_members.append(
                {
                    "project_candidate_id": cluster["project_candidate_id"],
                    "candidate_article_id": article_id,
                    "company_id": company_id,
                    "source_record_id": row.get("source_record_id"),
                    "source_url": row.get("source_url"),
                    "membership_type": "primary" if index == 0 else "duplicate_evidence",
                }
            )
            if index > 0:
                duplicate_articles.append(
                    {
                        "candidate_article_id": article_id,
                        "project_candidate_id": cluster["project_candidate_id"],
                        "company_id": company_id,
                        "duplicate_reason": "same_project_cluster",
                        "source_record_id": row.get("source_record_id"),
                    }
                )
    return clusters, cluster_members, duplicate_articles


def rejected_rows_from_clusters(clusters: list[dict[str, Any]], members: list[dict[str, Any]], r1_rejected: list[dict[str, str]]) -> list[dict[str, Any]]:
    rejected_cluster_ids = {cluster["project_candidate_id"]: cluster for cluster in clusters if cluster["verification_status"] == "rejected"}
    rows: list[dict[str, Any]] = []
    for member in members:
        cluster = rejected_cluster_ids.get(member["project_candidate_id"])
        if not cluster:
            continue
        rows.append(
            {
                "candidate_article_id": member["candidate_article_id"],
                "company_id": member["company_id"],
                "project_candidate_id": member["project_candidate_id"],
                "rejection_reason": cluster["rejection_reason"],
                "source_record_id": member["source_record_id"],
                "source_url": member["source_url"],
            }
        )
    for row in r1_rejected:
        rows.append(
            {
                "candidate_article_id": f"r1-rejected-{row.get('company_id')}-{row.get('source_dataset')}-{row.get('source_record_id')}",
                "company_id": row.get("company_id"),
                "project_candidate_id": "",
                "rejection_reason": row.get("rejection_reason") or "insufficient_evidence",
                "source_record_id": row.get("source_record_id"),
                "source_url": row.get("source_url"),
            }
        )
    return rows


def alias_review_rows(targets: list[dict[str, Any]], raw_articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_company: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for article in raw_articles:
        by_company[str(article["company_id"])].append(article)
    rows: list[dict[str, Any]] = []
    for company in targets:
        aliases = [company.get("company_name"), company.get("company_name_en"), *(company.get("aliases") or [])]
        rows.append(
            {
                "company_id": company.get("company_id"),
                "company_name": company.get("company_name"),
                "aliases_checked": ";".join(str(alias) for alias in aliases if alias),
                "raw_candidate_article_count": len(by_company.get(str(company.get("company_id")), [])),
                "expanded_keywords_checked": "모듈러;철골 모듈러;스틸 모듈러;OSC;이동식 건축물;조립식 건축물;학교 모듈러;임시교사;기숙사;제작;납품;설치;임차;수주;준공",
                "result": "candidates_found" if by_company.get(str(company.get("company_id"))) else "no_internal_candidate_found",
            }
        )
    return rows


def coverage_rows(targets: list[dict[str, Any]], raw_articles: list[dict[str, Any]], clusters: list[dict[str, Any]], rejected: list[dict[str, Any]], checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_count = defaultdict(int)
    pending_count = defaultdict(int)
    rejected_count = defaultdict(int)
    official_count = defaultdict(int)
    source_check_count = defaultdict(int)
    for article in raw_articles:
        raw_count[str(article["company_id"])] += 1
    for cluster in clusters:
        if cluster["verification_status"] == "official_source_pending":
            pending_count[str(cluster["company_id"])] += 1
        if cluster["verification_status"] == "rejected":
            rejected_count[str(cluster["company_id"])] += int(cluster["source_count"])
    for row in rejected:
        rejected_count[str(row["company_id"])] += 0 if row["project_candidate_id"] else 1
    for check in checks:
        source_check_count[str(check["company_id"])] += 1
        if check["status"] == "confirmed":
            official_count[str(check["company_id"])] += 1

    rows: list[dict[str, Any]] = []
    for company in targets:
        company_id = str(company.get("company_id"))
        if pending_count[company_id]:
            status = "official_source_pending"
        elif raw_count[company_id]:
            status = "research_exhausted_no_verified_project"
        else:
            status = "research_exhausted_no_verified_project"
        rows.append(
            {
                "company_id": company_id,
                "company_name": company.get("company_name"),
                "research_status": status,
                "raw_candidate_article_count": raw_count[company_id],
                "project_candidate_cluster_count": pending_count[company_id],
                "verified_project_count": 0,
                "rejected_candidate_count": rejected_count[company_id],
                "official_source_count": official_count[company_id],
                "sources_checked_count": source_check_count[company_id],
                "last_project_research_at": TODAY,
            }
        )
    return rows


def validation_errors(clusters: list[dict[str, Any]], coverage: list[dict[str, Any]]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    seen_projects: set[str] = set()
    for cluster in clusters:
        candidate_id = str(cluster["project_candidate_id"])
        if candidate_id in seen_projects:
            errors.append({"code": "duplicate_project_candidate_id", "company_id": cluster["company_id"], "path": candidate_id, "message": "duplicate project candidate id", "severity": "error"})
        seen_projects.add(candidate_id)
        if cluster["verification_status"] == "verified":
            if not cluster.get("official_source_ids"):
                errors.append({"code": "verified_without_official_source", "company_id": cluster["company_id"], "path": candidate_id, "message": "verified project needs official source", "severity": "error"})
            if cluster.get("possible_company_role") == PENDING_ROLE:
                errors.append({"code": "verified_without_role", "company_id": cluster["company_id"], "path": candidate_id, "message": "verified project needs confirmed role", "severity": "error"})
    for row in coverage:
        if int(row["raw_candidate_article_count"]) and int(row["project_candidate_cluster_count"]) == 0 and row["research_status"] == "official_source_pending":
            errors.append({"code": "status_count_mismatch", "company_id": row["company_id"], "path": "coverage", "message": "official_source_pending requires pending project clusters", "severity": "error"})
    return errors


def update_companies(companies_path: Path, coverage: list[dict[str, Any]], clusters: list[dict[str, Any]]) -> None:
    payload = read_json(companies_path)
    by_company_clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cluster in clusters:
        if cluster["verification_status"] != "official_source_pending":
            continue
        by_company_clusters[str(cluster["company_id"])].append(cluster)
    coverage_by_id = {row["company_id"]: row for row in coverage}
    for company in payload.get("companies", []):
        company_id = str(company.get("company_id"))
        if company_id not in coverage_by_id:
            continue
        row = coverage_by_id[company_id]
        company["project_research_status"] = {
            "research_wave": "wave_1",
            "research_status": row["research_status"],
            "verified_project_count": int(row["verified_project_count"]),
            "candidate_project_count": int(row["project_candidate_cluster_count"]),
            "raw_candidate_article_count": int(row["raw_candidate_article_count"]),
            "project_candidate_cluster_count": int(row["project_candidate_cluster_count"]),
            "rejected_candidate_count": int(row["rejected_candidate_count"]),
            "official_source_count": int(row["official_source_count"]),
            "sources_checked_count": int(row["sources_checked_count"]),
            "research_gap_count": 0 if int(row["project_candidate_cluster_count"]) else 1,
            "last_project_research_at": TODAY,
            "snapshot_source": "artifacts/company-project-candidate-verification-wave-1/company_project_coverage.csv",
            "note": "Raw news articles are clustered into project candidates; article count is not treated as project count.",
        }
        company["project_candidates"] = [
            {
                "project_candidate_id": cluster["project_candidate_id"],
                "canonical_project_name": cluster["canonical_project_name"],
                "aliases": [alias for alias in str(cluster["aliases"]).split("; ") if alias][:5],
                "possible_client": cluster["possible_client"] or None,
                "possible_location": cluster["possible_location"] or None,
                "possible_year": cluster["possible_year"] or None,
                "possible_use_type": cluster["possible_use_type"] or None,
                "possible_method": cluster["possible_method"] or None,
                "possible_company_role": cluster["possible_company_role"],
                "project_status": cluster["project_status"],
                "verification_status": cluster["verification_status"],
                "source_article_ids": str(cluster["source_article_ids"]).split(";") if cluster["source_article_ids"] else [],
                "source_article_count": int(cluster["source_count"]),
                "official_source_ids": [],
                "evidence_level": cluster["evidence_level"],
                "confidence": cluster["confidence"],
                "manual_review_required": True,
                "verification_priority_score": int(cluster["verification_priority_score"]),
                "verification_priority_level": cluster["verification_priority_level"],
                "priority_reasons": str(cluster["priority_reasons"]).split(";") if cluster["priority_reasons"] else [],
                "verification_note": "Official source confirmation is required before this candidate can become a verified project.",
            }
            for cluster in by_company_clusters.get(company_id, [])
        ][:5]
        gaps = company.get("research_gaps") if isinstance(company.get("research_gaps"), list) else []
        gaps = [gap for gap in gaps if gap.get("area") != "project_candidate_verification_wave_1"]
        gaps.append(
            {
                "area": "project_candidate_verification_wave_1",
                "status": row["research_status"],
                "note": "Project candidates are clustered from internal news articles. Verified promotion is blocked until official source and company role are confirmed.",
                "raw_candidate_article_count": int(row["raw_candidate_article_count"]),
                "project_candidate_cluster_count": int(row["project_candidate_cluster_count"]),
                "source_ids": [],
                "verified_at": TODAY,
            }
        )
        company["research_gaps"] = gaps
    write_json(companies_path, payload)


def audit_candidate_verification(companies_path: Path = DEFAULT_COMPANIES, output_dir: Path = DEFAULT_OUTPUT, write_companies: bool = False) -> dict[str, Any]:
    if not RAW_CANDIDATE_FILE.exists():
        audit_alignment()
    company_payload = read_json(companies_path)
    companies = company_payload.get("companies", [])
    targets = select_wave_targets(companies)
    companies_by_id = {str(company.get("company_id")): company for company in companies}
    raw_rows = read_csv(RAW_CANDIDATE_FILE)
    r1_rejected = read_csv(R1_REJECTED_FILE)
    target_ids = {str(company.get("company_id")) for company in targets}
    raw_rows = [row for row in raw_rows if str(row.get("company_id")) in target_ids]
    raw_articles = build_raw_articles(raw_rows)
    clusters, members, duplicate_articles = build_clusters(raw_rows, companies_by_id)
    checks = [check for cluster in clusters for check in official_source_checks_for(cluster)]
    rejected = rejected_rows_from_clusters(clusters, members, r1_rejected)
    coverage = coverage_rows(targets, raw_articles, clusters, rejected, checks)
    errors = validation_errors(clusters, coverage)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "raw_candidate_articles.csv", raw_articles, ["candidate_article_id", "company_id", "company_name", "source_dataset", "source_record_id", "title", "publisher", "published_at", "source_url", "matched_alias", "matched_context", "cluster_key"])
    cluster_fields = ["project_candidate_id", "company_id", "company_name", "canonical_project_name", "aliases", "possible_client", "possible_location", "possible_year", "possible_use_type", "possible_method", "possible_company_role", "project_status", "verification_status", "source_article_ids", "source_count", "official_source_ids", "evidence_level", "confidence", "rejection_reason", "manual_review_required", "verification_priority_score", "verification_priority_level", "priority_reasons"]
    write_csv(output_dir / "project_candidate_clusters.csv", clusters, cluster_fields)
    write_csv(output_dir / "cluster_members.csv", members, ["project_candidate_id", "candidate_article_id", "company_id", "source_record_id", "source_url", "membership_type"])
    write_csv(output_dir / "duplicate_articles.csv", duplicate_articles, ["candidate_article_id", "project_candidate_id", "company_id", "duplicate_reason", "source_record_id"])
    write_csv(output_dir / "verification_priority.csv", clusters, ["project_candidate_id", "company_id", "canonical_project_name", "verification_priority_score", "verification_priority_level", "priority_reasons", "verification_status", "rejection_reason"])
    write_csv(output_dir / "official_source_checks.csv", checks, ["project_candidate_id", "company_id", "check_target", "query", "status", "official_source_id", "note"])
    write_csv(output_dir / "verified_projects.csv", [cluster for cluster in clusters if cluster["verification_status"] == "verified"], cluster_fields)
    write_csv(output_dir / "pending_projects.csv", [cluster for cluster in clusters if cluster["verification_status"] == "official_source_pending"], cluster_fields)
    write_csv(output_dir / "rejected_candidates.csv", rejected, ["candidate_article_id", "company_id", "project_candidate_id", "rejection_reason", "source_record_id", "source_url"])
    write_csv(output_dir / "company_project_coverage.csv", coverage, ["company_id", "company_name", "research_status", "raw_candidate_article_count", "project_candidate_cluster_count", "verified_project_count", "rejected_candidate_count", "official_source_count", "sources_checked_count", "last_project_research_at"])
    write_csv(output_dir / "alias_review.csv", alias_review_rows(targets, raw_articles), ["company_id", "company_name", "aliases_checked", "raw_candidate_article_count", "expanded_keywords_checked", "result"])
    write_csv(output_dir / "research_gaps.csv", [row for row in coverage if row["verified_project_count"] == 0], ["company_id", "company_name", "research_status", "raw_candidate_article_count", "project_candidate_cluster_count", "official_source_count", "sources_checked_count", "last_project_research_at"])
    write_csv(output_dir / "validation_errors.csv", errors, ["code", "company_id", "path", "message", "severity"])

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_WITH_RESEARCH_GAPS" if not errors else "HOLD_FOR_FIX",
        "wave1_targets": [company.get("company_id") for company in targets],
        "raw_candidate_article_count": len(raw_articles),
        "duplicate_article_count": len(duplicate_articles),
        "project_candidate_cluster_count": sum(1 for cluster in clusters if cluster["verification_status"] == "official_source_pending"),
        "all_cluster_count": len(clusters),
        "verified_project_count": sum(1 for cluster in clusters if cluster["verification_status"] == "verified"),
        "pending_project_count": sum(1 for cluster in clusters if cluster["verification_status"] == "official_source_pending"),
        "rejected_candidate_count": len(rejected),
        "official_source_check_count": len(checks),
        "official_source_confirmed_count": sum(1 for check in checks if check["status"] == "confirmed"),
        "role_unknown_pending_count": sum(1 for cluster in clusters if cluster["verification_status"] == "official_source_pending" and cluster["possible_company_role"] == PENDING_ROLE),
        "verified_without_official_source_count": sum(1 for cluster in clusters if cluster["verification_status"] == "verified" and not cluster.get("official_source_ids")),
        "verified_without_role_count": sum(1 for cluster in clusters if cluster["verification_status"] == "verified" and cluster.get("possible_company_role") == PENDING_ROLE),
        "validation_error_count": len(errors),
        "company_coverage": coverage,
    }
    write_json(output_dir / "candidate_verification_audit.json", result)
    lines = [
        "# Wave 1 Project Candidate Verification Audit",
        "",
        f"- Status: {result['status']}",
        f"- Raw candidate articles: {result['raw_candidate_article_count']}",
        f"- Duplicate articles: {result['duplicate_article_count']}",
        f"- Pending project clusters: {result['pending_project_count']}",
        f"- Verified projects: {result['verified_project_count']}",
        f"- Rejected candidates: {result['rejected_candidate_count']}",
        "",
        "## Company Coverage",
        "",
        "| Company | Status | Articles | Project Candidates | Verified | Rejected | Official Checks |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in coverage:
        lines.append(f"| {row['company_name']} | {row['research_status']} | {row['raw_candidate_article_count']} | {row['project_candidate_cluster_count']} | {row['verified_project_count']} | {row['rejected_candidate_count']} | {row['sources_checked_count']} |")
    (output_dir / "candidate_verification_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if write_companies:
        update_companies(companies_path, coverage, clusters)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Cluster and audit Wave 1 project candidates.")
    parser.add_argument("--companies", type=Path, default=DEFAULT_COMPANIES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--write-companies", action="store_true")
    args = parser.parse_args()
    result = audit_candidate_verification(args.companies, args.output_dir, args.write_companies)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] != "HOLD_FOR_FIX" else 1


if __name__ == "__main__":
    raise SystemExit(main())
