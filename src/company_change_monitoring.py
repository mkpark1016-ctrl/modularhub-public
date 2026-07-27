from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from src.company_data_quality import load_public_company_universe, source_registry
from scripts.company_monitoring.common import MonitorCompany, canonical_url, normalize_title, safe_error_message

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config" / "company_change_monitoring"
NEWS_PATH = ROOT / "frontend" / "public" / "data" / "news.json"
REVIEW_QUEUE_PATH = ROOT / "data" / "company_change_monitoring" / "review_queue.json"
REPORT_DIR = ROOT / "reports" / "company_change_monitoring"
ARTIFACT_DIR = ROOT / "artifacts" / "company-change-monitor"

CONFIDENCE_VALUES = {"high", "medium", "low", "unknown"}
RISK_LEVELS = {"low", "moderate", "high", "critical"}
CANDIDATE_STATUSES = {"pending", "duplicate", "conflict", "insufficient_evidence", "rejected"}
SIGNAL_TYPES = {
    "identity_change",
    "executive_change",
    "headquarters_change",
    "financial_filing",
    "facility_opened",
    "facility_planned",
    "facility_expanded",
    "project_announced",
    "bid_announced",
    "contract_awarded",
    "construction_started",
    "project_completed",
    "project_cancelled",
    "patent_filed",
    "patent_published",
    "patent_registered",
    "patent_status_changed",
    "investment",
    "partnership",
    "overseas",
    "organizational",
    "modular_strategy",
    "news_signal",
    "unknown",
}

HIGH_REVIEW_FIELDS = {
    "company_profile.representative",
    "company_profile.legal_name",
    "headquarters",
    "production.operation_status",
    "production.reported_capacity",
    "financials",
    "project_portfolio.project_status",
    "project_portfolio.contract_amount",
    "technology.patent_owner",
    "technology.status",
}
CONFLICT_FIELD_PATHS = {
    "company_profile.representative",
    "company_profile.legal_name",
    "headquarters",
    "financials",
    "production.operation_status",
    "production.reported_capacity",
    "project_portfolio.project_status",
    "project_portfolio.contract_amount",
    "technology.patent_owner",
    "technology.status",
}

PROJECT_STATUS_ORDER = [
    "planned",
    "bid_announced",
    "selected",
    "contracted",
    "under_construction",
    "completed",
]
PATENT_STATUS_ORDER = ["filed", "published", "registered", "expired"]

TEXT_SPACE_RE = re.compile(r"\s+")
CORP_RE = re.compile(r"\b(주식회사|\(주\)|㈜|co\.?\s*ltd\.?|ltd\.?|inc\.?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class IdentityPolicy:
    company_id: str
    legal_name: str | None
    display_name: str
    english_names: tuple[str, ...]
    former_names: tuple[str, ...]
    aliases: tuple[str, ...]
    representative_names: tuple[str, ...]
    corp_code: str | None
    business_number_hash: str | None
    official_domains: tuple[str, ...]
    headquarters_regions: tuple[str, ...]
    positive_keywords: tuple[str, ...]
    negative_keywords: tuple[str, ...]
    excluded_entities: tuple[str, ...]
    modular_keywords: tuple[str, ...]

    @property
    def names(self) -> tuple[str, ...]:
        values = [self.legal_name, self.display_name, *self.aliases, *self.english_names, *self.former_names]
        deduped: list[str] = []
        for value in values:
            if value and value not in deduped:
                deduped.append(value)
        return tuple(deduped)


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def iso_now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = CORP_RE.sub(" ", text.lower())
    text = re.sub(r"[\[\]\(\){}<>\"'“”‘’|·,./\\:_-]", " ", text)
    return TEXT_SPACE_RE.sub(" ", text).strip()


def normalize_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return normalize_text(value)


def stable_hash(*parts: Any, length: int = 16) -> str:
    payload = "\n".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def parse_date(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S+00:00", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    if len(text) >= 10 and re.match(r"\d{4}-\d{2}-\d{2}", text):
        return text[:10]
    return None


def load_identity_policies(root: Path = ROOT) -> list[IdentityPolicy]:
    payload = read_json(root / "config" / "company_change_monitoring" / "company_identities.json")
    policies = []
    for row in payload.get("companies", []):
        policies.append(
            IdentityPolicy(
                company_id=row["companyId"],
                legal_name=row.get("legalName"),
                display_name=row["displayName"],
                english_names=tuple(row.get("englishNames") or []),
                former_names=tuple(row.get("formerNames") or []),
                aliases=tuple(row.get("aliases") or []),
                representative_names=tuple(row.get("representativeNames") or []),
                corp_code=row.get("corpCode"),
                business_number_hash=row.get("businessNumberHash"),
                official_domains=tuple(row.get("officialDomains") or []),
                headquarters_regions=tuple(row.get("headquartersRegions") or []),
                positive_keywords=tuple(row.get("positiveKeywords") or []),
                negative_keywords=tuple(row.get("negativeKeywords") or []),
                excluded_entities=tuple(row.get("excludedEntities") or []),
                modular_keywords=tuple(row.get("modularKeywords") or []),
            )
        )
    return policies


def load_source_policy(root: Path = ROOT) -> dict[str, Any]:
    return read_json(root / "config" / "company_change_monitoring" / "source_policy.json")


def source_configured(source_id: str) -> bool:
    if source_id == "public_news":
        return True
    if source_id == "naver_api_hub":
        return bool(os.getenv("NAVER_API_HUB_CLIENT_ID") and os.getenv("NAVER_API_HUB_CLIENT_SECRET"))
    if source_id == "dart":
        return bool(os.getenv("DART_API_KEY"))
    return False


def source_tier(source_id: str, root: Path = ROOT) -> str:
    policy = load_source_policy(root)
    for row in policy.get("sources", []):
        if row.get("sourceId") == source_id:
            return row.get("sourceTier") or "tier_2"
    return "tier_2"


def identity_policy_as_monitor_company(policy: IdentityPolicy, *, source_id: str) -> MonitorCompany:
    enabled_source = "naver_search" if source_id == "naver_api_hub" else source_id
    return MonitorCompany(
        company_id=policy.company_id,
        canonical_name=policy.display_name,
        aliases=policy.aliases,
        english_names=policy.english_names,
        dart_corp_code=policy.corp_code,
        stock_code=None,
        official_domains=policy.official_domains,
        positive_keywords=(*policy.positive_keywords, *policy.modular_keywords),
        negative_keywords=(*policy.negative_keywords, *policy.excluded_entities),
        enabled_sources=(enabled_source,),
        enabled=True,
    )


def company_index(root: Path = ROOT) -> dict[str, dict[str, Any]]:
    return {row["company_id"]: row for row in load_public_company_universe(root)}


def identity_score(policy: IdentityPolicy, title: str, summary: str = "", url: str = "") -> dict[str, Any]:
    text = normalize_text(f"{title} {summary}")
    url_text = (url or "").lower()
    matched_aliases = [name for name in policy.names if normalize_text(name) and normalize_text(name) in text]
    negative_hits = [keyword for keyword in policy.negative_keywords if normalize_text(keyword) in text]
    excluded_hits = [entity for entity in policy.excluded_entities if normalize_text(entity) in text]
    positive_hits = [keyword for keyword in policy.positive_keywords if normalize_text(keyword) in text]
    modular_hits = [keyword for keyword in policy.modular_keywords if normalize_text(keyword) in text]
    representative_hits = [name for name in policy.representative_names if normalize_text(name) and normalize_text(name) in text]
    region_hits = [region for region in policy.headquarters_regions if normalize_text(region) and normalize_text(region) in text]
    domain_hits = [domain for domain in policy.official_domains if domain and domain.lower() in url_text]

    if excluded_hits:
        return {
            "score": 0.0,
            "rejected": True,
            "matchedAlias": matched_aliases[:1],
            "matchedKeyword": positive_hits[:1] or modular_hits[:1],
            "reason": "excluded_entity",
            "negativeHits": [*negative_hits, *excluded_hits],
        }

    score = 0.0
    if matched_aliases:
        score += 0.35
    if representative_hits:
        score += 0.25
    if domain_hits:
        score += 0.25
    if region_hits:
        score += 0.12
    if positive_hits:
        score += 0.15
    if modular_hits:
        score += 0.18
    if negative_hits:
        score -= 0.35
    score = max(0.0, min(1.0, score))
    return {
        "score": round(score, 2),
        "rejected": score < 0.45,
        "matchedAlias": matched_aliases[:1],
        "matchedKeyword": (positive_hits or modular_hits)[:1],
        "reason": "identity_and_modular_context" if score >= 0.65 else "weak_identity_or_context",
        "negativeHits": negative_hits,
    }


def classify_signal(title: str, summary: str = "") -> dict[str, Any]:
    text = normalize_text(f"{title} {summary}")
    rules = [
        (("대표", "대표이사", "CEO"), "executive_change", "company_profile.representative"),
        (("본사", "이전", "주소"), "headquarters_change", "headquarters"),
        (("감사보고서", "사업보고서", "분기보고서", "반기보고서"), "financial_filing", "financials"),
        (("공장", "생산시설", "생산라인"), "facility_opened", "production"),
        (("증설", "투자"), "facility_expanded", "production"),
        (("입찰", "공고"), "bid_announced", "project_portfolio"),
        (("수주", "계약", "낙찰"), "contract_awarded", "project_portfolio"),
        (("착공", "공사 중"), "construction_started", "project_portfolio"),
        (("준공", "완공"), "project_completed", "project_portfolio"),
        (("취소", "해지"), "project_cancelled", "project_portfolio"),
        (("특허", "출원"), "patent_filed", "technology"),
        (("등록특허", "특허 등록"), "patent_registered", "technology"),
        (("MOU", "업무협약", "협약"), "partnership", "recent_signals"),
        (("해외", "수출", "진출"), "overseas", "recent_signals"),
        (("OSC", "모듈러", "프리패브"), "modular_strategy", "recent_signals"),
    ]
    for keywords, signal_type, field_path in rules:
        if any(normalize_text(keyword) in text for keyword in keywords):
            return {"signalType": signal_type, "fieldPath": field_path}
    return {"signalType": "news_signal", "fieldPath": "recent_signals"}


def raw_signal_from_news(news: dict[str, Any], policy: IdentityPolicy, match: dict[str, Any], fetched_at: str) -> dict[str, Any]:
    title = news.get("title") or ""
    url = news.get("original_url") or news.get("naver_url") or ""
    raw_id = f"raw-{stable_hash(policy.company_id, news.get('id'), title, url)}"
    return {
        "rawId": raw_id,
        "sourceId": "public_news",
        "companyId": policy.company_id,
        "query": "public_news_existing_dataset",
        "fetchedAt": fetched_at,
        "publishedAt": parse_date(news.get("published_at")),
        "title": title,
        "url": url,
        "originalPayloadRef": f"frontend/public/data/news.json#{news.get('id')}",
        "identityEvidence": {
            "score": match["score"],
            "matchedAlias": match["matchedAlias"],
            "matchedKeyword": match["matchedKeyword"],
            "matchReason": match["reason"],
        },
        "rawHash": stable_hash(policy.company_id, news.get("id"), title, url, length=32),
    }


def raw_signal_from_monitor_candidate(candidate: dict[str, Any], policy: IdentityPolicy, source_id: str, fetched_at: str) -> dict[str, Any]:
    title = candidate.get("title") or ""
    summary = candidate.get("summary") or title
    url = candidate.get("source_url") or ""
    published_at = parse_date(candidate.get("published_at"))
    raw_id = f"raw-{stable_hash(policy.company_id, source_id, candidate.get('source_id'), title, url)}"
    return {
        "rawId": raw_id,
        "sourceId": source_id,
        "companyId": policy.company_id,
        "query": candidate.get("query") or source_id,
        "fetchedAt": fetched_at,
        "publishedAt": published_at,
        "title": title,
        "url": url,
        "originalPayloadRef": f"{source_id}:{candidate.get('source_id') or candidate.get('document_id') or raw_id}",
        "identityEvidence": {
            "score": round(float(candidate.get("entity_match_score") or 0.0), 2),
            "matchedAlias": [],
            "matchedKeyword": [],
            "matchReason": "source_adapter_candidate",
        },
        "rawHash": stable_hash(policy.company_id, source_id, candidate.get("evidence_hash"), title, url, length=32),
        "summary": summary,
    }


def normalize_signal(raw: dict[str, Any], source_tier: str = "tier_2") -> dict[str, Any]:
    classified = classify_signal(raw.get("title", ""), raw.get("summary", ""))
    signal_id = f"signal-{stable_hash(raw['companyId'], raw['sourceId'], raw['rawHash'])}"
    return {
        "signalId": signal_id,
        "companyId": raw["companyId"],
        "sourceId": raw["sourceId"],
        "sourceTier": source_tier,
        "signalType": classified["signalType"],
        "title": raw.get("title"),
        "summary": raw.get("title"),
        "effectiveAt": raw.get("publishedAt"),
        "observedAt": raw.get("fetchedAt"),
        "url": raw.get("url"),
        "fieldHints": [classified["fieldPath"]],
        "identityScore": raw["identityEvidence"]["score"],
        "relevanceScore": 0.7 if classified["signalType"] != "news_signal" else 0.45,
        "confidence": "medium" if raw["identityEvidence"]["score"] >= 0.75 and source_tier in {"tier_1", "tier_2"} else "low",
        "evidence": [
            {
                "sourceId": raw["sourceId"],
                "title": raw.get("title"),
                "url": raw.get("url"),
                "publishedAt": raw.get("publishedAt"),
                "identityEvidence": raw.get("identityEvidence"),
            }
        ],
        "fingerprint": stable_hash(raw["companyId"], raw["sourceId"], normalize_text(raw.get("title")), raw.get("publishedAt")),
        "status": "normalized",
    }


def collect_public_news_signals(
    policies: list[IdentityPolicy],
    *,
    root: Path = ROOT,
    lookback_days: int = 30,
    fetched_at: str | None = None,
    max_per_company: int = 20,
) -> dict[str, Any]:
    fetched_at = fetched_at or iso_now()
    payload = read_json(root / NEWS_PATH.relative_to(ROOT))
    news_items = payload.get("news") or []
    latest = parse_date(payload.get("latest_public_news_published_at")) or parse_date(payload.get("generated_at")) or date.today().isoformat()
    cutoff = datetime.fromisoformat(latest).date() - timedelta(days=lookback_days)
    raw: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    per_company: Counter[str] = Counter()
    scanned_count = 0

    for news in news_items:
        published = parse_date(news.get("published_at"))
        if not published or datetime.fromisoformat(published).date() < cutoff:
            continue
        scanned_count += 1
        for policy in policies:
            if per_company[policy.company_id] >= max_per_company:
                continue
            match = identity_score(policy, news.get("title", ""), news.get("summary", ""), news.get("original_url") or news.get("naver_url") or "")
            if match["rejected"]:
                if match.get("negativeHits") or match["matchedAlias"]:
                    rejected.append(
                        {
                            "companyId": policy.company_id,
                            "title": news.get("title"),
                            "url": news.get("original_url") or news.get("naver_url"),
                            "reason": match["reason"],
                        }
                    )
                continue
            raw_signal = raw_signal_from_news(news, policy, match, fetched_at)
            raw.append(raw_signal)
            normalized.append(normalize_signal(raw_signal))
            per_company[policy.company_id] += 1

    return {
        "sourceId": "public_news",
        "sourceType": "snapshot",
        "configured": True,
        "attempted": True,
        "state": "success_with_candidates" if normalized else "success_empty",
        "raw": raw,
        "normalized": normalized,
        "rejected": rejected,
        "latestPublishedAt": latest,
        "fetchedAt": fetched_at,
        "queryCount": 0,
        "responseCount": scanned_count,
        "companyCountAttempted": len(policies),
        "companyCountWithResults": len(per_company),
        "companyCountSkipped": 0,
        "skipReasons": {},
        "diagnostics": {
            "snapshotPath": str(NEWS_PATH.relative_to(ROOT)),
            "lookbackDays": lookback_days,
            "snapshotItemsScanned": scanned_count,
            "matchedCompanyCount": len(per_company),
        },
        "companyResults": [
            {
                "companyId": policy.company_id,
                "attempted": True,
                "state": "success_with_candidates" if per_company[policy.company_id] else "success_empty",
                "rawRecordCount": per_company[policy.company_id],
                "candidateCount": per_company[policy.company_id],
                "rejectedCount": 0,
                "safeErrorCategory": "none",
            }
            for policy in policies
        ],
    }


def naver_safe_error_category(exc: Exception) -> str:
    from scripts.company_monitoring.collect_naver_search import naver_error_category

    return naver_error_category(exc)


def dart_safe_error_category(exc: Exception) -> str:
    text = str(exc).lower()
    if "api_key" in text or "crtfc_key" in text or "opendart_status_010" in text:
        return "auth_error"
    if "opendart_status_013" in text:
        return "success_empty"
    if "429" in text or "rate" in text:
        return "rate_limited"
    if "json" in text or "parse" in text:
        return "response_parse_error"
    return "transport_error"


def collect_naver_api_hub_signals(
    policies: list[IdentityPolicy],
    *,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    from scripts.company_monitoring.collect_naver_search import collect_for_company

    fetched_at = fetched_at or iso_now()
    configured = source_configured("naver_api_hub")
    raw: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    company_results: list[dict[str, Any]] = []
    error_categories: Counter[str] = Counter()
    latest: str | None = None

    if not configured:
        return {
            "sourceId": "naver_api_hub",
            "sourceType": "live",
            "configured": False,
            "attempted": False,
            "state": "source_not_configured",
            "raw": raw,
            "normalized": normalized,
            "rejected": rejected,
            "latestPublishedAt": None,
            "safeErrorCategory": "missing_secret_or_adapter",
            "companyResults": company_results,
            "queryCount": 0,
            "responseCount": 0,
            "companyCountAttempted": 0,
            "companyCountWithResults": 0,
            "companyCountSkipped": len(policies),
            "skipReasons": {"missing_secret_or_adapter": len(policies)},
        }

    tier = source_tier("naver_api_hub")
    for policy in policies:
        try:
            monitor_company = identity_policy_as_monitor_company(policy, source_id="naver_api_hub")
            result = collect_for_company(monitor_company, fetched_at)
            candidates = result.get("candidates") or []
            rejected_items = result.get("rejected") or []
            for candidate in candidates:
                raw_signal = raw_signal_from_monitor_candidate(candidate, policy, "naver_api_hub", fetched_at)
                raw.append(raw_signal)
                normalized.append(normalize_signal(raw_signal, source_tier=tier))
                if raw_signal.get("publishedAt") and (latest is None or raw_signal["publishedAt"] > latest):
                    latest = raw_signal["publishedAt"]
            rejected.extend({"companyId": policy.company_id, **item} for item in rejected_items)
            company_results.append(
                {
                    "companyId": policy.company_id,
                    "attempted": True,
                    "state": "success_with_candidates" if candidates else "success_empty",
                    "rawRecordCount": len(result.get("records") or []),
                    "candidateCount": len(candidates),
                    "rejectedCount": len(rejected_items),
                    "safeErrorCategory": "none",
                    "queryCount": len(result.get("queries") or []),
                }
            )
        except Exception as exc:  # source-level failure isolation
            category = naver_safe_error_category(exc)
            error_categories[category] += 1
            company_results.append(
                {
                    "companyId": policy.company_id,
                    "attempted": True,
                    "state": category,
                    "rawRecordCount": 0,
                    "candidateCount": 0,
                    "rejectedCount": 0,
                    "safeErrorCategory": category,
                    "safeErrorMessage": safe_error_message(exc, "naver_api_hub_error"),
                }
            )

    if normalized:
        state = "success_with_candidates"
    elif error_categories and len(error_categories) == len(policies):
        state = next(iter(error_categories))
    elif error_categories:
        state = "partial_success_with_source_warning"
    else:
        state = "success_empty"

    return {
        "sourceId": "naver_api_hub",
        "sourceType": "live",
        "configured": True,
        "attempted": True,
        "state": state,
        "raw": raw,
        "normalized": normalized,
        "rejected": rejected,
        "latestPublishedAt": latest,
        "safeErrorCategory": "none" if not error_categories else ",".join(sorted(error_categories)),
        "companyResults": company_results,
        "queryCount": sum(int(row.get("queryCount", 0) or 0) for row in company_results),
        "responseCount": sum(int(row.get("rawRecordCount", 0) or 0) for row in company_results),
        "companyCountAttempted": sum(1 for row in company_results if row.get("attempted")),
        "companyCountWithResults": sum(1 for row in company_results if int(row.get("candidateCount", 0) or 0) > 0),
        "companyCountSkipped": sum(1 for row in company_results if not row.get("attempted")),
        "skipReasons": dict(error_categories),
    }


def collect_dart_signals(
    policies: list[IdentityPolicy],
    *,
    lookback_days: int = 30,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    from scripts.company_monitoring.collect_dart import collect_for_company

    fetched_at = fetched_at or iso_now()
    configured = source_configured("dart")
    raw: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    company_results: list[dict[str, Any]] = []
    error_categories: Counter[str] = Counter()
    latest: str | None = None

    if not configured:
        return {
            "sourceId": "dart",
            "sourceType": "registry",
            "configured": False,
            "attempted": False,
            "state": "source_not_configured",
            "raw": raw,
            "normalized": normalized,
            "rejected": rejected,
            "latestPublishedAt": None,
            "safeErrorCategory": "missing_secret_or_adapter",
            "companyResults": company_results,
            "queryCount": 0,
            "responseCount": 0,
            "companyCountAttempted": 0,
            "companyCountWithResults": 0,
            "companyCountSkipped": len(policies),
            "skipReasons": {"missing_secret_or_adapter": len(policies)},
        }

    tier = source_tier("dart")
    for policy in policies:
        if not policy.corp_code:
            company_results.append(
                {
                    "companyId": policy.company_id,
                    "attempted": False,
                    "state": "identity_mapping_missing",
                    "rawRecordCount": 0,
                    "candidateCount": 0,
                    "rejectedCount": 0,
                    "safeErrorCategory": "identity_mapping_missing",
                    "queryCount": 0,
                }
            )
            continue
        try:
            monitor_company = identity_policy_as_monitor_company(policy, source_id="dart")
            result = collect_for_company(monitor_company, lookback_days, fetched_at)
            candidates = result.get("candidates") or []
            for candidate in candidates:
                raw_signal = raw_signal_from_monitor_candidate(candidate, policy, "dart", fetched_at)
                raw.append(raw_signal)
                normalized.append(normalize_signal(raw_signal, source_tier=tier))
                if raw_signal.get("publishedAt") and (latest is None or raw_signal["publishedAt"] > latest):
                    latest = raw_signal["publishedAt"]
            company_results.append(
                {
                    "companyId": policy.company_id,
                    "attempted": True,
                    "state": "success_with_candidates" if candidates else "success_empty",
                    "rawRecordCount": len(result.get("records") or []),
                    "candidateCount": len(candidates),
                    "rejectedCount": 0,
                    "safeErrorCategory": "none",
                    "queryCount": 1,
                }
            )
        except Exception as exc:  # source-level failure isolation
            category = dart_safe_error_category(exc)
            error_categories[category] += 1
            company_results.append(
                {
                    "companyId": policy.company_id,
                    "attempted": True,
                    "state": category,
                    "rawRecordCount": 0,
                    "candidateCount": 0,
                    "rejectedCount": 0,
                    "safeErrorCategory": category,
                    "safeErrorMessage": safe_error_message(exc, "dart_error"),
                }
            )

    attempted = any(row["attempted"] for row in company_results)
    identity_missing_count = sum(1 for row in company_results if row["state"] == "identity_mapping_missing")
    if normalized:
        state = "success_with_candidates"
    elif error_categories and sum(error_categories.values()) == len([row for row in company_results if row["attempted"]]):
        state = next(iter(error_categories))
    elif error_categories:
        state = "partial_success_with_source_warning"
    elif identity_missing_count == len(company_results):
        state = "identity_mapping_missing"
    else:
        state = "success_empty"

    return {
        "sourceId": "dart",
        "sourceType": "registry",
        "configured": True,
        "attempted": attempted,
        "state": state,
        "raw": raw,
        "normalized": normalized,
        "rejected": rejected,
        "latestPublishedAt": latest,
        "safeErrorCategory": "identity_mapping_missing" if state == "identity_mapping_missing" else "none" if not error_categories else ",".join(sorted(error_categories)),
        "companyResults": company_results,
        "queryCount": sum(int(row.get("queryCount", 0) or 0) for row in company_results),
        "responseCount": sum(int(row.get("rawRecordCount", 0) or 0) for row in company_results),
        "companyCountAttempted": sum(1 for row in company_results if row.get("attempted")),
        "companyCountWithResults": sum(1 for row in company_results if int(row.get("candidateCount", 0) or 0) > 0),
        "companyCountSkipped": sum(1 for row in company_results if not row.get("attempted")),
        "skipReasons": {"identity_mapping_missing": identity_missing_count, **dict(error_categories)},
    }


def get_current_value(company: dict[str, Any], field_path: str) -> Any:
    if field_path == "headquarters":
        return company.get("headquarters")
    if field_path == "company_profile.representative":
        return (company.get("company_profile") or {}).get("representative")
    if field_path == "financials":
        financials = company.get("financials") or []
        return financials[0] if financials else None
    if field_path == "production":
        return len(company.get("production") or [])
    if field_path == "project_portfolio":
        return len(company.get("project_portfolio") or [])
    if field_path == "technology":
        technology = company.get("technology") or {}
        if isinstance(technology, dict):
            return len(technology.get("patents") or technology.get("records") or [])
    return None


def candidate_entity_type(signal_type: str, field_path: str) -> str:
    if field_path.startswith("financials") or signal_type == "financial_filing":
        return "financial"
    if field_path.startswith("production") or signal_type.startswith("facility_"):
        return "facility"
    if field_path.startswith("project_portfolio") or signal_type in {
        "project_announced",
        "bid_announced",
        "contract_awarded",
        "construction_started",
        "project_completed",
        "project_cancelled",
    }:
        return "project"
    if field_path.startswith("technology") or signal_type.startswith("patent_"):
        return "technology"
    if field_path.startswith("company_profile") or field_path == "headquarters":
        return "identity"
    return "news"


def evidence_key_for_signal(signal: dict[str, Any]) -> str:
    url = canonical_url(signal.get("url"))
    if url:
        return f"url:{url}"
    title_key = normalize_title(signal.get("title"))
    effective = parse_date(signal.get("effectiveAt")) or signal.get("effectiveAt") or ""
    if title_key:
        return f"title-date:{title_key}:{effective}"
    return f"source-record:{signal.get('originalPayloadRef') or signal.get('signalId') or ''}"


def entity_key_for_signal(signal: dict[str, Any], entity_type: str, field_path: str) -> str:
    proposed = signal.get("proposedValue")
    if isinstance(proposed, dict):
        for key in (
            "entityKey",
            "documentId",
            "document_id",
            "receiptNumber",
            "receipt_number",
            "patentNumber",
            "patent_number",
            "projectId",
            "project_id",
            "facilityId",
            "facility_id",
        ):
            if proposed.get(key):
                return normalize_value(proposed.get(key))
    url_key = canonical_url(signal.get("url"))
    title_key = normalize_title(signal.get("title"))
    if entity_type in {"project", "technology", "facility", "news"}:
        return url_key or title_key or normalize_value(signal.get("signalId"))
    if entity_type == "financial":
        return normalize_value(signal.get("documentId") or signal.get("originalPayloadRef") or signal.get("effectiveAt") or field_path)
    return normalize_value(field_path)


def comparison_value_for_candidate(candidate: dict[str, Any]) -> str:
    value = candidate.get("comparisonValue")
    if value is None:
        value = candidate.get("proposedValue")
    return normalize_value(value)


def candidate_from_signal(company: dict[str, Any], signal: dict[str, Any]) -> dict[str, Any]:
    field_path = signal["fieldHints"][0] if signal.get("fieldHints") else "recent_signals"
    signal_type = signal.get("signalType", "unknown")
    change_type = "freshness_update"
    if signal_type in {"facility_opened", "facility_expanded", "project_announced", "contract_awarded", "patent_filed", "patent_registered"}:
        change_type = "new_record"
    if signal_type in {"executive_change", "headquarters_change"}:
        change_type = "new_value"
    if signal_type == "news_signal":
        change_type = "freshness_update"

    source_tiers = [signal.get("sourceTier", "tier_2")]
    confidence = signal.get("confidence", "unknown")
    risk = risk_level(field_path, confidence, signal.get("identityScore", 0.0), source_tiers)
    status = "pending"
    if signal_type == "news_signal" or confidence == "low":
        status = "insufficient_evidence"
    proposed_value = {
        "signalType": signal_type,
        "title": signal.get("title"),
        "url": signal.get("url"),
    }
    entity_type = candidate_entity_type(signal_type, field_path)
    entity_key = entity_key_for_signal(signal, entity_type, field_path)
    evidence_key = evidence_key_for_signal(signal)
    candidate_id = f"cand-{stable_hash(signal['companyId'], signal.get('sourceId'), signal.get('signalId'), change_type, field_path, evidence_key, signal.get('effectiveAt'), length=20)}"
    fingerprint = candidate_fingerprint(
        signal["companyId"],
        change_type,
        field_path,
        proposed_value,
        signal.get("effectiveAt"),
        signal.get("sourceId"),
        entity_key=entity_key,
        evidence_key=evidence_key,
    )
    return {
        "candidateId": candidate_id,
        "companyId": signal["companyId"],
        "changeType": change_type,
        "fieldPath": field_path,
        "entityType": entity_type,
        "entityKey": entity_key,
        "evidenceKey": evidence_key,
        "currentValue": get_current_value(company, field_path),
        "proposedValue": proposed_value,
        "comparisonValue": proposed_value,
        "effectiveAt": signal.get("effectiveAt"),
        "observedAt": signal.get("observedAt"),
        "sourceIds": [signal.get("sourceId")],
        "sourceTiers": source_tiers,
        "evidenceSummary": signal.get("title"),
        "identityScore": signal.get("identityScore"),
        "confidence": confidence,
        "priority": candidate_priority(confidence, risk, field_path),
        "riskLevel": risk,
        "status": status,
        "duplicateOf": None,
        "conflictsWith": [],
        "researchGapIds": [],
        "requiresHumanReview": field_path in HIGH_REVIEW_FIELDS or field_path.split(".")[0] in {"financials", "production", "project_portfolio", "technology"},
        "generatedAt": iso_now(),
        "fingerprint": fingerprint,
        "signalType": signal_type,
    }


def risk_level(field_path: str, confidence: str, identity_score_value: float, source_tiers: list[str]) -> str:
    if identity_score_value < 0.55:
        return "high"
    if field_path in {"company_profile.representative", "headquarters", "financials"}:
        return "high" if confidence != "high" else "moderate"
    if "tier_3" in source_tiers and field_path in {"production", "financials", "technology"}:
        return "high"
    if confidence == "low":
        return "moderate"
    return "low"


def candidate_priority(confidence: str, risk: str, field_path: str) -> str:
    if risk in {"high", "critical"}:
        return "high"
    if confidence == "high" or field_path in {"production", "project_portfolio", "technology"}:
        return "medium"
    return "low"


def candidate_fingerprint(
    company_id: str,
    change_type: str,
    field_path: str,
    proposed_value: Any,
    effective_at: str | None,
    source_id: str | None,
    *,
    entity_key: str | None = None,
    evidence_key: str | None = None,
) -> str:
    if isinstance(proposed_value, dict):
        url_key = canonical_url(proposed_value.get("url"))
        title_key = normalize_title(proposed_value.get("title"))
    else:
        url_key = ""
        title_key = normalize_text(proposed_value)
    evidence = evidence_key or (f"url:{url_key}" if url_key else f"title-date:{title_key}:{parse_date(effective_at) or effective_at or ''}")
    duplicate_entity = entity_key or evidence
    return stable_hash(company_id, source_id, change_type, field_path, duplicate_entity, evidence, length=32)


def assign_unique_candidate_ids(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: Counter[str] = Counter()
    for candidate in candidates:
        base_id = candidate["candidateId"]
        seen[base_id] += 1
        if seen[base_id] > 1:
            candidate["candidateId"] = f"{base_id}-{stable_hash(base_id, seen[base_id], candidate.get('fingerprint'), length=8)}"
    return candidates


def conflict_scope(candidate: dict[str, Any]) -> tuple[tuple[str, str, str, str], str] | None:
    if candidate.get("status") in {"duplicate", "insufficient_evidence", "rejected"}:
        return None
    if candidate.get("changeType") == "new_record":
        return None
    if candidate.get("signalType") == "news_signal" or candidate.get("fieldPath") == "recent_signals":
        return None
    field_path = candidate.get("fieldPath")
    if field_path not in CONFLICT_FIELD_PATHS:
        return None
    entity_key = candidate.get("entityKey") or normalize_value(field_path)
    effective_period = parse_date(candidate.get("effectiveAt")) or candidate.get("effectiveAt") or "current"
    scope = (candidate["companyId"], field_path, entity_key, effective_period)
    return scope, comparison_value_for_candidate(candidate)


def dedupe_and_conflict(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = assign_unique_candidate_ids(candidates)
    seen: dict[str, str] = {}
    scoped_values: dict[tuple[str, str, str, str], dict[str, str]] = defaultdict(dict)
    for candidate in candidates:
        candidate.setdefault("duplicateOf", None)
        candidate.setdefault("conflictsWith", [])
        fp = candidate["fingerprint"]
        if fp in seen:
            candidate["status"] = "duplicate"
            candidate["duplicateOf"] = seen[fp]
        else:
            seen[fp] = candidate["candidateId"]
        scoped = conflict_scope(candidate)
        if scoped:
            key, proposed = scoped
            for existing_value, existing_id in scoped_values[key].items():
                if existing_value != proposed:
                    candidate["status"] = "conflict"
                    candidate["conflictsWith"].append(existing_id)
                    break
            scoped_values[key][proposed] = candidate["candidateId"]
    return candidates


def classification_diagnostics(run: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
    candidates = run.get("candidates", []) if isinstance(run, dict) else run
    duplicate_groups: dict[str, list[str]] = defaultdict(list)
    conflict_groups: dict[str, list[str]] = defaultdict(list)
    for candidate in candidates:
        duplicate_groups[candidate.get("fingerprint") or ""].append(candidate.get("candidateId"))
        if candidate.get("status") == "conflict":
            conflict_key = stable_hash(candidate.get("companyId"), candidate.get("fieldPath"), candidate.get("entityKey"), candidate.get("effectiveAt"), length=16)
            conflict_groups[conflict_key].append(candidate.get("candidateId"))
    return {
        "schemaVersion": "company-change-classification-diagnostics-v1",
        "generatedAt": iso_now(),
        "candidateCount": len(candidates),
        "statusCounts": dict(Counter(candidate.get("status") for candidate in candidates)),
        "byCompany": dict(Counter(candidate.get("companyId") for candidate in candidates)),
        "bySource": dict(Counter(source for candidate in candidates for source in candidate.get("sourceIds", []))),
        "byEntityType": dict(Counter(candidate.get("entityType", "unknown") for candidate in candidates)),
        "byChangeType": dict(Counter(candidate.get("changeType") for candidate in candidates)),
        "duplicateGroupCount": sum(1 for rows in duplicate_groups.values() if len(rows) > 1),
        "maxDuplicateGroupSize": max((len(rows) for rows in duplicate_groups.values()), default=0),
        "conflictGroupCount": sum(1 for rows in conflict_groups.values() if len(rows) > 1),
        "maxConflictGroupSize": max((len(rows) for rows in conflict_groups.values()), default=0),
        "duplicateSamples": [
            {"fingerprint": fingerprint, "candidateIds": rows[:10]}
            for fingerprint, rows in sorted(duplicate_groups.items())
            if len(rows) > 1
        ][:20],
        "conflictSamples": [
            {"conflictGroup": group, "candidateIds": rows[:10]}
            for group, rows in sorted(conflict_groups.items())
            if len(rows) > 1
        ][:20],
    }


def research_gap_area(field_path: str) -> str:
    if field_path.startswith("company_profile") or field_path == "headquarters":
        return "identity"
    if field_path == "financials":
        return "financial"
    if field_path == "production":
        return "facility"
    if field_path == "project_portfolio":
        return "project"
    if field_path == "technology":
        return "patent"
    return "recentTrend"


def link_research_gaps(companies: dict[str, dict[str, Any]], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for company_id, company in companies.items():
        gaps = company.get("research_gaps") or []
        summary[company_id] = {
            "existingGapCount": len(gaps),
            "resolvedCandidateCount": 0,
            "newGapCount": 0,
            "conflictingGapCount": 0,
            "remainingGapCount": len(gaps),
        }
    for candidate in candidates:
        area = research_gap_area(candidate["fieldPath"])
        company = companies.get(candidate["companyId"], {})
        matched = []
        for index, gap in enumerate(company.get("research_gaps") or []):
            text = normalize_text(f"{gap.get('area')} {gap.get('description')}")
            if area in text or normalize_text(area) in text or candidate["fieldPath"].split(".")[0] in text:
                matched.append(f"{candidate['companyId']}:gap:{index}")
        candidate["researchGapIds"] = matched
        if matched and candidate["status"] in {"pending", "conflict"}:
            if candidate["status"] == "conflict":
                summary[candidate["companyId"]]["conflictingGapCount"] += len(matched)
            else:
                summary[candidate["companyId"]]["resolvedCandidateCount"] += len(matched)
        elif not matched and candidate["status"] != "duplicate":
            summary[candidate["companyId"]]["newGapCount"] += 1
    for row in summary.values():
        row["remainingGapCount"] = max(0, row["existingGapCount"] - row["resolvedCandidateCount"])
    return summary


def valid_project_transition(before: str | None, after: str | None) -> bool:
    if before not in PROJECT_STATUS_ORDER or after not in PROJECT_STATUS_ORDER:
        return False
    return PROJECT_STATUS_ORDER.index(after) - PROJECT_STATUS_ORDER.index(before) in {0, 1}


def valid_patent_transition(before: str | None, after: str | None) -> bool:
    if before not in PATENT_STATUS_ORDER or after not in PATENT_STATUS_ORDER:
        return False
    return PATENT_STATUS_ORDER.index(after) >= PATENT_STATUS_ORDER.index(before)


def build_change_monitor_run(
    *,
    root: Path = ROOT,
    companies: list[str] | None = None,
    sources: list[str] | None = None,
    lookback_days: int = 30,
    mode: str = "daily_signals",
    publish: bool = False,
    create_proposal: bool = False,
    acknowledge_proposal: bool = False,
    live: bool = False,
    acknowledge_live: bool = False,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    if publish:
        raise ValueError("publish=true is not allowed for company change monitoring")
    if create_proposal and not acknowledge_proposal:
        raise ValueError("create_proposal requires acknowledge_proposal=true")
    source_ids = sources or ["public_news"]
    policies = load_identity_policies(root)
    if companies:
        selected = set(companies)
        policies = [policy for policy in policies if policy.company_id in selected]
    company_map = company_index(root)
    missing = [policy.company_id for policy in policies if policy.company_id not in company_map]
    if len(company_map) != 11:
        raise ValueError(f"expected 11 companies, found {len(company_map)}")
    if missing:
        raise ValueError(f"identity policy references missing companies: {', '.join(missing)}")

    run_id = f"company-change-{stable_hash(mode, ','.join(policy.company_id for policy in policies), fetched_at or iso_now(), length=12)}"
    source_statuses: list[dict[str, Any]] = []
    raw: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    identity_rejected = 0

    for source_id in source_ids:
        if source_id == "public_news":
            result = collect_public_news_signals(policies, root=root, lookback_days=lookback_days, fetched_at=fetched_at, max_per_company=20)
        elif source_id == "naver_api_hub":
            if live and acknowledge_live:
                result = collect_naver_api_hub_signals(policies, fetched_at=fetched_at)
            else:
                result = {
                    "sourceId": source_id,
                    "sourceType": "live",
                    "configured": source_configured(source_id),
                    "attempted": False,
                    "state": "live_opt_in_required",
                    "raw": [],
                    "normalized": [],
                    "rejected": [],
                    "latestPublishedAt": None,
                    "safeErrorCategory": "live_opt_in_required",
                    "companyResults": [],
                }
        elif source_id == "dart":
            if live and acknowledge_live:
                result = collect_dart_signals(policies, lookback_days=lookback_days, fetched_at=fetched_at)
            else:
                result = {
                    "sourceId": source_id,
                    "sourceType": "registry",
                    "configured": source_configured(source_id),
                    "attempted": False,
                    "state": "live_opt_in_required",
                    "raw": [],
                    "normalized": [],
                    "rejected": [],
                    "latestPublishedAt": None,
                    "safeErrorCategory": "live_opt_in_required",
                    "companyResults": [],
                }
        else:
            configured = source_configured(source_id)
            result = {
                "sourceId": source_id,
                "configured": configured,
                "attempted": False,
                "state": "unsupported_source",
                "raw": [],
                "normalized": [],
                "rejected": [],
                "latestPublishedAt": None,
                "safeErrorCategory": "unsupported_source",
                "companyResults": [],
            }

        raw.extend(result["raw"])
        normalized.extend(result["normalized"])
        identity_rejected += len(result["rejected"])
        source_statuses.append(
            {
                "sourceId": source_id,
                "sourceType": result.get("sourceType") or "derived",
                "configured": result["configured"],
                "attempted": result.get("attempted", False),
                "state": result["state"],
                "rawCount": len(result["raw"]),
                "normalizedCount": len(result["normalized"]),
                "identityRejected": len(result["rejected"]),
                "latestPublishedAt": result["latestPublishedAt"],
                "safeErrorCategory": result.get("safeErrorCategory", "none"),
                "companyResults": result.get("companyResults", []),
                "queryCount": result.get("queryCount", 0),
                "responseCount": result.get("responseCount", len(result["raw"])),
                "companyCountAttempted": result.get("companyCountAttempted", 0),
                "companyCountWithResults": result.get("companyCountWithResults", 0),
                "companyCountSkipped": result.get("companyCountSkipped", 0),
                "skipReasons": result.get("skipReasons", {}),
                "diagnostics": result.get("diagnostics", {}),
            }
        )

    candidates = [candidate_from_signal(company_map[signal["companyId"]], signal) for signal in normalized]
    candidates = dedupe_and_conflict(candidates)
    gap_summary = link_research_gaps(company_map, candidates)
    status_counts = Counter(candidate["status"] for candidate in candidates)
    risk_counts = Counter(candidate["riskLevel"] for candidate in candidates)
    confidence_counts = Counter(candidate["confidence"] for candidate in candidates)
    diagnostics = classification_diagnostics(candidates)

    return {
        "schemaVersion": "company-change-monitor-run-v1",
        "generatedAt": fetched_at or iso_now(),
        "runId": run_id,
        "mode": mode,
        "companies": [policy.company_id for policy in policies],
        "sources": source_ids,
        "lookbackDays": lookback_days,
        "sourceStatuses": source_statuses,
        "rawSignals": raw,
        "normalizedSignals": normalized,
        "identityRejected": identity_rejected,
        "candidateCount": len(candidates),
        "pending": status_counts["pending"],
        "duplicate": status_counts["duplicate"],
        "conflict": status_counts["conflict"],
        "insufficientEvidence": status_counts["insufficient_evidence"],
        "rejected": status_counts["rejected"],
        "highPriority": sum(1 for candidate in candidates if candidate["priority"] == "high"),
        "statusCounts": dict(status_counts),
        "riskCounts": dict(risk_counts),
        "confidenceCounts": dict(confidence_counts),
        "classificationDiagnostics": diagnostics,
        "researchGapSummary": gap_summary,
        "candidates": candidates,
        "proposal": {
            "createProposal": create_proposal,
            "created": bool(create_proposal and acknowledge_proposal and any(candidate["confidence"] == "high" for candidate in candidates)),
            "guard": "acknowledge_proposal_required",
        },
        "publish": False,
        "publicDataChanged": False,
        "secretExposureDetected": False,
    }


def review_queue_payload(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": "company-change-review-queue-v1",
        "generatedAt": run["generatedAt"],
        "runId": run["runId"],
        "companies": run["companies"],
        "sources": run.get("sources", []),
        "candidateCount": run["candidateCount"],
        "pending": run["pending"],
        "duplicate": run["duplicate"],
        "conflict": run["conflict"],
        "insufficientEvidence": run["insufficientEvidence"],
        "rejected": run.get("rejected", 0),
        "highPriority": run["highPriority"],
        "sourceStatuses": run["sourceStatuses"],
        "researchGapSummary": run["researchGapSummary"],
        "classificationDiagnostics": run.get("classificationDiagnostics", {}),
        "candidates": run["candidates"],
    }


def digest_payload(run: dict[str, Any]) -> dict[str, Any]:
    by_company = Counter(candidate["companyId"] for candidate in run["candidates"])
    by_source = Counter(source for candidate in run["candidates"] for source in candidate.get("sourceIds", []))
    return {
        "schemaVersion": "company-change-digest-v1",
        "generatedAt": run["generatedAt"],
        "runId": run["runId"],
        "candidateCount": run["candidateCount"],
        "statusCounts": run["statusCounts"],
        "riskCounts": run["riskCounts"],
        "confidenceCounts": run["confidenceCounts"],
        "classificationDiagnostics": run.get("classificationDiagnostics", {}),
        "byCompany": dict(by_company),
        "bySource": dict(by_source),
        "highPriority": [candidate for candidate in run["candidates"] if candidate["priority"] == "high"][:20],
        "researchGapSummary": run["researchGapSummary"],
        "sourceStatuses": run["sourceStatuses"],
        "publicDataChanged": run["publicDataChanged"],
        "secretExposureDetected": run["secretExposureDetected"],
    }


def markdown_digest(run: dict[str, Any]) -> str:
    lines = [
        "# Company Change Monitoring Digest",
        "",
        f"- Run ID: `{run['runId']}`",
        f"- Mode: `{run['mode']}`",
        f"- Companies: `{len(run['companies'])}`",
        f"- Candidates: `{run['candidateCount']}`",
        f"- Pending: `{run['pending']}`",
        f"- Duplicate: `{run['duplicate']}`",
        f"- Conflict: `{run['conflict']}`",
        f"- Insufficient evidence: `{run['insufficientEvidence']}`",
        f"- Rejected: `{run.get('rejected', 0)}`",
        f"- High priority: `{run['highPriority']}`",
        f"- Public data changed: `{run['publicDataChanged']}`",
        f"- Secret exposure: `{run['secretExposureDetected']}`",
        "",
        "## Source Status",
        "",
    ]
    for source in run["sourceStatuses"]:
        lines.append(
            f"- `{source['sourceId']}`: state={source['state']}, configured={source['configured']}, raw={source['rawCount']}, normalized={source['normalizedCount']}"
        )
    lines.extend(["", "## Review Priorities", ""])
    for candidate in [row for row in run["candidates"] if row["priority"] == "high"][:20]:
        lines.append(f"- `{candidate['companyId']}` {candidate['changeType']} `{candidate['fieldPath']}`: {candidate['evidenceSummary']}")
    if not any(row["priority"] == "high" for row in run["candidates"]):
        lines.append("- High priority candidate 없음")
    return "\n".join(lines) + "\n"


def write_run_outputs(run: dict[str, Any], *, root: Path = ROOT, write_internal_queue: bool = True) -> dict[str, str]:
    queue = review_queue_payload(run)
    digest = digest_payload(run)
    paths = {
        "rawSummary": ARTIFACT_DIR / "raw-summary.json",
        "normalized": ARTIFACT_DIR / "normalized-signals.json",
        "reviewQueue": REVIEW_QUEUE_PATH,
        "digestJson": REPORT_DIR / "latest_digest.json",
        "digestMd": REPORT_DIR / "latest_digest.md",
        "classificationDiagnostics": ARTIFACT_DIR / "classification-diagnostics.json",
    }
    write_json(root / paths["rawSummary"].relative_to(ROOT), {"rawSignals": run["rawSignals"], "sourceStatuses": run["sourceStatuses"]})
    write_json(root / paths["normalized"].relative_to(ROOT), {"normalizedSignals": run["normalizedSignals"]})
    if write_internal_queue:
        write_json(root / paths["reviewQueue"].relative_to(ROOT), queue)
    write_json(root / paths["digestJson"].relative_to(ROOT), digest)
    write_text(root / paths["digestMd"].relative_to(ROOT), markdown_digest(run))
    write_json(root / paths["classificationDiagnostics"].relative_to(ROOT), run.get("classificationDiagnostics") or classification_diagnostics(run))
    return {key: str(value.relative_to(ROOT)) for key, value in paths.items()}


def duplicate_cycle_count(duplicate_map: dict[str, str]) -> int:
    cycles = 0
    for candidate_id in duplicate_map:
        seen: set[str] = set()
        current = candidate_id
        while current in duplicate_map:
            if current in seen:
                cycles += 1
                break
            seen.add(current)
            current = duplicate_map[current]
    return cycles


def audit_change_run(run: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    companies = company_index(root)
    candidates = run.get("candidates", [])
    candidate_ids = [candidate["candidateId"] for candidate in candidates]
    candidate_by_id = {candidate["candidateId"]: candidate for candidate in candidates}
    public_paths = [str(path).replace("\\", "/") for path in root.glob("frontend/public/**/*") if path.is_file()]
    serialized = json.dumps(run, ensure_ascii=False)
    secret_patterns = ["DART_API_KEY", "NAVER_API_HUB_CLIENT_SECRET", "Authorization", "request_headers", "raw_response"]
    invalid_candidates = []
    fingerprints = []
    status_by_id: dict[str, set[str]] = defaultdict(set)
    for candidate in candidates:
        status_by_id[candidate["candidateId"]].add(candidate.get("status"))
        if candidate.get("confidence") not in CONFIDENCE_VALUES:
            invalid_candidates.append(candidate["candidateId"])
        if candidate.get("riskLevel") not in RISK_LEVELS:
            invalid_candidates.append(candidate["candidateId"])
        if candidate.get("status") not in CANDIDATE_STATUSES:
            invalid_candidates.append(candidate["candidateId"])
        if not candidate.get("evidenceSummary") or not candidate.get("sourceIds"):
            invalid_candidates.append(candidate["candidateId"])
        fingerprints.append(candidate.get("fingerprint"))

    duplicate_fingerprint_errors = len(fingerprints) - len(set(fingerprints)) - int(run.get("duplicate", 0))
    duplicate_fingerprint_errors = max(0, duplicate_fingerprint_errors)
    duplicate_map = {
        candidate["candidateId"]: candidate.get("duplicateOf")
        for candidate in candidates
        if candidate.get("duplicateOf")
    }
    conflict_refs = [
        (candidate["candidateId"], target)
        for candidate in candidates
        for target in candidate.get("conflictsWith", [])
    ]
    orphan_duplicate = [target for target in duplicate_map.values() if target not in candidate_by_id]
    orphan_conflict = [target for _, target in conflict_refs if target not in candidate_by_id]
    cross_company_refs = []
    for candidate_id, target in [*duplicate_map.items(), *conflict_refs]:
        if target in candidate_by_id and candidate_by_id[candidate_id].get("companyId") != candidate_by_id[target].get("companyId"):
            cross_company_refs.append((candidate_id, target))

    status_counts = Counter(candidate.get("status") for candidate in candidates)
    status_total = sum(status_counts.get(status, 0) for status in CANDIDATE_STATUSES)
    selected_sources = set(run.get("sources") or [])
    source_statuses = run.get("sourceStatuses") or []
    deferred_source_statuses = [source for source in source_statuses if source.get("state") == "configured_deferred_to_source_adapter"]
    unattempted_configured_sources = [
        source
        for source in source_statuses
        if source.get("sourceId") in {"naver_api_hub", "dart"}
        and source.get("sourceId") in selected_sources
        and source.get("configured") is True
        and not source.get("attempted")
        and source.get("state") not in {"identity_mapping_missing"}
    ]
    contamination_terms = ["\ucd5c\ubcd1\ucc9c", "\uae40\ud574", "\uc790\ub3d9\ucc28 \ubd80\ud488", "\ub300\uc2b9\uadf8\ub8f9"]
    summary = {
        "schemaVersion": "company-change-audit-v1",
        "generatedAt": iso_now(),
        "valid": True,
        "companyCount": len(companies),
        "candidateCount": len(candidates),
        "statusCounts": {status: status_counts.get(status, 0) for status in sorted(CANDIDATE_STATUSES)},
        "statusConservationPassed": len(candidates) == status_total,
        "candidateIdUnique": len(candidate_ids) == len(set(candidate_ids)),
        "invalidCandidateCount": len(set(invalid_candidates)),
        "multiStatusCandidateCount": len([candidate_id for candidate_id, statuses in status_by_id.items() if len(statuses) > 1]),
        "missingDuplicateOfCount": len(orphan_duplicate),
        "orphanDuplicateReferenceCount": len(orphan_duplicate),
        "duplicateOfSelfCount": len([candidate_id for candidate_id, target in duplicate_map.items() if candidate_id == target]),
        "duplicateReferenceCycleCount": duplicate_cycle_count(duplicate_map),
        "orphanConflictReferenceCount": len(orphan_conflict),
        "conflictSelfReferenceCount": len([candidate_id for candidate_id, target in conflict_refs if candidate_id == target]),
        "crossCompanyContaminationCount": len(cross_company_refs),
        "duplicateFingerprintErrors": duplicate_fingerprint_errors,
        "deferredSourceStatusCount": len(deferred_source_statuses),
        "unattemptedConfiguredSourceCount": len(unattempted_configured_sources),
        "publicReviewQueueExposureCount": len([path for path in public_paths if "company-change" in path or "review_queue" in path]),
        "secretExposureDetected": any(pattern in serialized for pattern in secret_patterns),
        "publicDataChanged": bool(run.get("publicDataChanged")),
        "daeseungContaminationCount": len(
            [
                candidate
                for candidate in candidates
                if candidate["companyId"] == "daeseung-engineering"
                and any(term in normalize_text(candidate.get("evidenceSummary")) for term in contamination_terms)
            ]
        ),
        "classificationDiagnostics": run.get("classificationDiagnostics") or classification_diagnostics(run),
    }
    summary["valid"] = all(
        [
            summary["companyCount"] == 11,
            summary["statusConservationPassed"],
            summary["candidateIdUnique"],
            summary["invalidCandidateCount"] == 0,
            summary["multiStatusCandidateCount"] == 0,
            summary["orphanDuplicateReferenceCount"] == 0,
            summary["duplicateOfSelfCount"] == 0,
            summary["duplicateReferenceCycleCount"] == 0,
            summary["orphanConflictReferenceCount"] == 0,
            summary["conflictSelfReferenceCount"] == 0,
            summary["crossCompanyContaminationCount"] == 0,
            summary["duplicateFingerprintErrors"] == 0,
            summary["deferredSourceStatusCount"] == 0,
            summary["unattemptedConfiguredSourceCount"] == 0,
            summary["publicReviewQueueExposureCount"] == 0,
            not summary["secretExposureDetected"],
            not summary["publicDataChanged"],
            summary["daeseungContaminationCount"] == 0,
        ]
    )
    return summary


def write_audit_outputs(summary: dict[str, Any], *, root: Path = ROOT) -> dict[str, str]:
    json_path = ARTIFACT_DIR / "audit-summary.json"
    md_path = ARTIFACT_DIR / "audit-report.md"
    lines = [
        "# Company Change Candidate Audit",
        "",
        f"- Valid: `{summary['valid']}`",
        f"- Company count: `{summary['companyCount']}`",
        f"- Candidate IDs unique: `{summary['candidateIdUnique']}`",
        f"- Status conservation passed: `{summary.get('statusConservationPassed')}`",
        f"- Invalid candidates: `{summary['invalidCandidateCount']}`",
        f"- Missing duplicate refs: `{summary['missingDuplicateOfCount']}`",
        f"- Duplicate self refs: `{summary.get('duplicateOfSelfCount', 0)}`",
        f"- Duplicate ref cycles: `{summary.get('duplicateReferenceCycleCount', 0)}`",
        f"- Orphan conflict refs: `{summary.get('orphanConflictReferenceCount', 0)}`",
        f"- Conflict self refs: `{summary.get('conflictSelfReferenceCount', 0)}`",
        f"- Cross-company refs: `{summary.get('crossCompanyContaminationCount', 0)}`",
        f"- Multi-status candidates: `{summary.get('multiStatusCandidateCount', 0)}`",
        f"- Duplicate fingerprint errors: `{summary['duplicateFingerprintErrors']}`",
        f"- Deferred source statuses: `{summary['deferredSourceStatusCount']}`",
        f"- Unattempted configured sources: `{summary['unattemptedConfiguredSourceCount']}`",
        f"- Public review queue exposure: `{summary['publicReviewQueueExposureCount']}`",
        f"- Secret exposure: `{summary['secretExposureDetected']}`",
        f"- Daeseung contamination: `{summary['daeseungContaminationCount']}`",
    ]
    write_json(root / json_path.relative_to(ROOT), summary)
    write_text(root / md_path.relative_to(ROOT), "\n".join(lines) + "\n")
    return {"auditSummary": str(json_path.relative_to(ROOT)), "auditReport": str(md_path.relative_to(ROOT))}


def issue_fingerprint(candidate: dict[str, Any]) -> str:
    return f"company-change-{stable_hash(candidate['companyId'], candidate['fingerprint'], length=12)}"


def assert_no_public_publication(run: dict[str, Any]) -> None:
    if run.get("publish"):
        raise AssertionError("publish must remain false")
    if run.get("publicDataChanged"):
        raise AssertionError("public data changed")
