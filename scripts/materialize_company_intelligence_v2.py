#!/usr/bin/env python3
"""Materialize public Company Intelligence V2 and the compatible companies.json view."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

from migrate_company_intelligence_v2 import DEFAULT_COMPANIES, DEFAULT_OUTPUT, ROOT, protected_hash, read_json, write_json

DEFAULT_PUBLIC_V2 = ROOT / "frontend" / "public" / "data" / "companies" / "company_intelligence_v2.json"

ROLE_SUMMARY_LABELS = {
    "direct_competitor": "직접 경쟁사",
    "substitute_competitor": "대체 공법 경쟁사",
    "strategic_benchmark": "전략 벤치마크",
    "design_influencer": "설계 영향 기업",
    "internal_baseline": "내부 비교 기준",
    "watchlist": "관찰 대상",
}


def public_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [deepcopy(record) for record in records if record.get("visibility") == "public"]


def public_v2_payload(payload: dict[str, Any]) -> dict[str, Any]:
    companies = public_records(payload.get("companies", []))
    company_ids = {company["company_id"] for company in companies}
    facts = [fact for fact in public_records(payload.get("facts", [])) if fact.get("company_id") in company_ids]
    events = [event for event in public_records(payload.get("events", [])) if event.get("company_id") in company_ids]
    evidence = public_records(payload.get("evidence", []))
    corrections = public_records(payload.get("corrections", []))
    summaries = [
        deepcopy(summary) for summary in payload.get("materialized_summaries", [])
        if summary.get("company_id") in company_ids
    ]
    return {
        "schema_version": payload["schema_version"],
        "generated_at": payload["generated_at"],
        "companies": companies,
        "facts": facts,
        "events": events,
        "evidence": evidence,
        "corrections": corrections,
        "materialized_summaries": summaries,
        "audit_metadata": {
            "source_schema_version": payload["schema_version"],
            "public_company_count": len(companies),
            "public_fact_count": len(facts),
            "public_event_count": len(events),
            "public_evidence_count": len(evidence),
            "public_correction_count": len(corrections),
            "visibility_filter": "visibility=public",
        },
    }


def korean_summary(company: dict[str, Any], summary: dict[str, Any]) -> str:
    role = ROLE_SUMMARY_LABELS.get(company.get("competitive_role"), "분석 대상 기업")
    overall = summary.get("overall_data_status")
    if overall == "core_verified":
        return f"스틸 모듈러 관점의 {role}로, 법인·재무 핵심 정보와 주요 사업 근거를 영역별로 확인했습니다."
    if overall == "partially_verified":
        return f"스틸 모듈러 관점의 {role}로, 확인된 공개자료와 추가 조사가 필요한 영역을 구분해 관리합니다."
    if overall == "insufficient_public_data":
        return f"스틸 모듈러 관점의 {role}이며, 현재 공개자료가 부족해 추가 확인이 필요합니다."
    return f"스틸 모듈러 관점의 {role}로, 공개자료를 영역별로 추가 조사 중입니다."


def group_sources(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in evidence:
        source_type = source.get("source_type")
        tier = source.get("source_tier")
        if source_type in {"regulatory_filing", "audit_report"}:
            key = "dart"
        elif tier == "B":
            key = "company_official"
        elif tier == "A":
            key = "public_official"
        elif tier == "C":
            key = "media_and_research"
        else:
            key = "other"
        grouped[key].append(source)
    return [
        {
            "group_type": key,
            "count": len(items),
            "sources": [
                {
                    "source_id": item.get("source_id"),
                    "source_type": item.get("source_type"),
                    "source_tier": item.get("source_tier"),
                    "publisher": item.get("publisher"),
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "published_at": item.get("published_at"),
                    "retrieved_at": item.get("retrieved_at"),
                    "document_id": item.get("document_id"),
                    "status": item.get("status"),
                }
                for item in items
            ],
        }
        for key, items in sorted(grouped.items())
    ]


def materialize_companies(legacy: dict[str, Any], public_v2: dict[str, Any], canonical_v2: dict[str, Any]) -> dict[str, Any]:
    summaries = {item["company_id"]: item for item in public_v2.get("materialized_summaries", [])}
    events_by_company: dict[str, list[dict[str, Any]]] = defaultdict(list)
    facts_by_company: dict[str, list[dict[str, Any]]] = defaultdict(list)
    evidence_by_id = {item["source_id"]: item for item in public_v2.get("evidence", [])}
    for event in public_v2.get("events", []):
        events_by_company[event["company_id"]].append(event)
    for fact in public_v2.get("facts", []):
        facts_by_company[fact["company_id"]].append(fact)
    output = deepcopy(legacy)
    for company in output.get("companies", []):
        company_id = company["company_id"]
        expected_hash = canonical_v2.get("audit_metadata", {}).get("protected_company_hashes", {}).get(company_id)
        if expected_hash and protected_hash(company) != expected_hash:
            raise ValueError(f"protected legacy fields changed before materialization: {company_id}")
        summary = deepcopy(summaries.get(company_id, {}))
        source_ids = {
            source_id
            for item in events_by_company.get(company_id, []) + facts_by_company.get(company_id, [])
            for source_id in item.get("source_ids", [])
        }
        source_ids.update(
            item["source_id"]
            for item in public_v2.get("evidence", [])
            if f"company:{company_id}" in item.get("supports", [])
        )
        sources = [evidence_by_id[source_id] for source_id in sorted(source_ids) if source_id in evidence_by_id]
        company["intelligence_v2"] = {
            **summary,
            "summary_ko": korean_summary(company, summary),
            "events": sorted(events_by_company.get(company_id, []), key=lambda item: (item.get("updated_at") or "", item["event_id"]), reverse=True),
            "source_groups": group_sources(sources),
        }
    output.setdefault("metadata", {})["company_intelligence_v2"] = {
        "schema_version": public_v2["schema_version"],
        "generated_at": public_v2["generated_at"],
        "source": "data/companies/company_intelligence_v2.json",
        "visibility_filter": "public",
    }
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--companies", type=Path, default=DEFAULT_COMPANIES)
    parser.add_argument("--public-output", type=Path, default=DEFAULT_PUBLIC_V2)
    parser.add_argument("--write-companies", action="store_true")
    args = parser.parse_args()
    canonical = read_json(args.input)
    legacy = read_json(args.companies)
    public = public_v2_payload(canonical)
    materialized = materialize_companies(legacy, public, canonical)
    write_json(args.public_output, public)
    if args.write_companies:
        write_json(args.companies, materialized)
    print(json.dumps({
        "status": "PASS",
        "public_companies": len(public["companies"]),
        "public_facts": len(public["facts"]),
        "public_events": len(public["events"]),
        "public_evidence": len(public["evidence"]),
        "companies_written": args.write_companies,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
