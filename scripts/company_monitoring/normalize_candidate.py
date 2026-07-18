from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from scripts.company_monitoring.common import (
    MonitorCompany,
    canonical_url,
    hash_evidence,
    iso_now,
    normalize_title,
    source_id,
    strip_html,
)


def parse_date(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).replace(tzinfo=UTC).date().isoformat()
        except ValueError:
            pass
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC).date().isoformat()
    except (TypeError, ValueError, IndexError):
        return None


def entity_match_score(company: MonitorCompany, title: str, summary: str, url: str = "") -> float:
    haystack = f"{title} {summary} {url}".lower()
    aliases = [company.canonical_name, *company.aliases, *company.english_names]
    exact_matches = sum(1 for alias in aliases if alias and alias.lower() in haystack)
    domain_matches = sum(1 for domain in company.official_domains if domain and domain.lower() in url.lower())
    if exact_matches and domain_matches:
        return 1.0
    if exact_matches >= 2:
        return 0.95
    if exact_matches == 1:
        return 0.82
    if domain_matches:
        return 0.75
    return 0.0


def relevance_score(company: MonitorCompany, title: str, summary: str, query: str = "") -> float:
    haystack = f"{title} {summary} {query}".lower()
    positive = sum(1 for word in company.positive_keywords if word and word.lower() in haystack)
    negative = sum(1 for word in company.negative_keywords if word and word.lower() in haystack)
    score = 0.2 + min(0.65, positive * 0.18) - min(0.45, negative * 0.15)
    return max(0.0, min(1.0, round(score, 3)))


def confidence(entity_score: float, relevance: float, source_tier: str) -> str:
    if source_tier in {"A", "B"} and entity_score >= 0.75 and relevance >= 0.35:
        return "high"
    if entity_score >= 0.75 and relevance >= 0.25:
        return "medium"
    return "low"


def make_candidate(
    *,
    company: MonitorCompany,
    candidate_kind: str,
    domain: str,
    title: str,
    summary: str,
    source_type: str,
    source_tier: str,
    publisher: str,
    source_url: str,
    document_id: str | None = None,
    published_at: str | None = None,
    proposed_value: Any = None,
    current_value: Any = None,
    query: str | None = None,
    event_status: str | None = None,
    project_credit: bool | None = None,
    promotion_blockers: list[str] | None = None,
    raw_ref: str | None = None,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    clean_title = strip_html(title)
    clean_summary = strip_html(summary)
    clean_url = canonical_url(source_url)
    normalized_date = parse_date(published_at)
    evidence_hash = hash_evidence(company.company_id, source_type, document_id or clean_url, normalize_title(clean_title), normalized_date)
    match = entity_match_score(company, clean_title, clean_summary, clean_url)
    relevance = relevance_score(company, clean_title, clean_summary, query or "")
    sid = source_id(source_type, company.company_id, document_id, clean_url, clean_title)
    return {
        "candidate_id": f"cand-{evidence_hash[:20]}",
        "company_id": company.company_id,
        "candidate_kind": candidate_kind,
        "domain": domain,
        "title": clean_title,
        "summary": clean_summary,
        "proposed_value": proposed_value,
        "current_value": current_value,
        "source_id": sid,
        "source_type": source_type,
        "source_tier": source_tier,
        "publisher": publisher,
        "source_url": clean_url,
        "document_id": document_id,
        "published_at": normalized_date,
        "fetched_at": fetched_at or iso_now(),
        "evidence_hash": evidence_hash,
        "entity_match_score": match,
        "relevance_score": relevance,
        "confidence": confidence(match, relevance, source_tier),
        "review_status": "pending",
        "promotion_blockers": promotion_blockers or [],
        "duplicate_of": None,
        "event_status": event_status,
        "project_credit": project_credit,
        "query": query,
        "raw_ref": raw_ref,
    }


def normalize_raw_record(company: MonitorCompany, record: dict[str, Any], source_tier: str = "C") -> dict[str, Any]:
    return make_candidate(
        company=company,
        candidate_kind=record.get("candidate_kind", "evidence"),
        domain=record.get("domain", "market"),
        title=record.get("title", ""),
        summary=record.get("summary") or record.get("description") or "",
        source_type=record.get("source_type", "naver_search"),
        source_tier=record.get("source_tier", source_tier),
        publisher=record.get("publisher", ""),
        source_url=record.get("source_url") or record.get("original_link") or record.get("link") or "",
        document_id=record.get("document_id"),
        published_at=record.get("published_at") or record.get("pub_date") or record.get("rcept_dt"),
        proposed_value=record.get("proposed_value"),
        current_value=record.get("current_value"),
        query=record.get("query"),
        raw_ref=record.get("raw_ref"),
        fetched_at=record.get("fetched_at"),
    )
