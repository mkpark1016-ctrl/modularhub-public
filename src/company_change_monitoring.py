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

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config" / "company_change_monitoring"
NEWS_PATH = ROOT / "frontend" / "public" / "data" / "news.json"
REVIEW_QUEUE_PATH = ROOT / "data" / "company_change_monitoring" / "review_queue.json"
REPORT_DIR = ROOT / "reports" / "company_change_monitoring"
ARTIFACT_DIR = ROOT / "artifacts" / "company-change-monitor"

CONFIDENCE_VALUES = {"high", "medium", "low", "unknown"}
RISK_LEVELS = {"low", "moderate", "high", "critical"}
CANDIDATE_STATUSES = {"pending", "duplicate", "conflict", "insufficient_evidence", "rejected", "accepted", "proposed", "published"}
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


def normalize_signal(raw: dict[str, Any], source_tier: str = "tier_2") -> dict[str, Any]:
    classified = classify_signal(raw.get("title", ""), "")
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

    for news in news_items:
        published = parse_date(news.get("published_at"))
        if not published or datetime.fromisoformat(published).date() < cutoff:
            continue
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
        "configured": True,
        "state": "success",
        "raw": raw,
        "normalized": normalized,
        "rejected": rejected,
        "latestPublishedAt": latest,
        "fetchedAt": fetched_at,
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
    candidate_id = f"cand-{stable_hash(signal['companyId'], change_type, field_path, signal['fingerprint'])}"
    proposed_value = {
        "signalType": signal_type,
        "title": signal.get("title"),
        "url": signal.get("url"),
    }
    fingerprint = candidate_fingerprint(signal["companyId"], change_type, field_path, proposed_value, signal.get("effectiveAt"), signal.get("sourceId"))
    return {
        "candidateId": candidate_id,
        "companyId": signal["companyId"],
        "changeType": change_type,
        "fieldPath": field_path,
        "currentValue": get_current_value(company, field_path),
        "proposedValue": proposed_value,
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


def candidate_fingerprint(company_id: str, change_type: str, field_path: str, proposed_value: Any, effective_at: str | None, source_id: str | None) -> str:
    return stable_hash(company_id, change_type, field_path, normalize_value(proposed_value), effective_at, source_id, length=32)


def dedupe_and_conflict(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, str] = {}
    field_values: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    for candidate in candidates:
        fp = candidate["fingerprint"]
        if fp in seen:
            candidate["status"] = "duplicate"
            candidate["duplicateOf"] = seen[fp]
        else:
            seen[fp] = candidate["candidateId"]
        if candidate["status"] != "duplicate":
            key = (candidate["companyId"], candidate["fieldPath"])
            proposed = normalize_value(candidate["proposedValue"])
            for existing_value, existing_id in field_values[key].items():
                if existing_value != proposed:
                    candidate["status"] = "conflict"
                    candidate["conflictsWith"].append(existing_id)
                    break
            field_values[key][proposed] = candidate["candidateId"]
    return candidates


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
            raw.extend(result["raw"])
            normalized.extend(result["normalized"])
            identity_rejected += len(result["rejected"])
            source_statuses.append(
                {
                    "sourceId": source_id,
                    "configured": True,
                    "state": result["state"],
                    "rawCount": len(result["raw"]),
                    "normalizedCount": len(result["normalized"]),
                    "identityRejected": len(result["rejected"]),
                    "latestPublishedAt": result["latestPublishedAt"],
                    "safeErrorCategory": "none",
                }
            )
        else:
            configured = source_configured(source_id)
            source_statuses.append(
                {
                    "sourceId": source_id,
                    "configured": configured,
                    "state": "configured_deferred_to_source_adapter" if configured else "source_not_configured",
                    "rawCount": 0,
                    "normalizedCount": 0,
                    "identityRejected": 0,
                    "latestPublishedAt": None,
                    "safeErrorCategory": "none" if configured else "missing_secret_or_adapter",
                }
            )

    candidates = [candidate_from_signal(company_map[signal["companyId"]], signal) for signal in normalized]
    candidates = dedupe_and_conflict(candidates)
    gap_summary = link_research_gaps(company_map, candidates)
    status_counts = Counter(candidate["status"] for candidate in candidates)
    risk_counts = Counter(candidate["riskLevel"] for candidate in candidates)
    confidence_counts = Counter(candidate["confidence"] for candidate in candidates)

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
        "highPriority": sum(1 for candidate in candidates if candidate["priority"] == "high"),
        "statusCounts": dict(status_counts),
        "riskCounts": dict(risk_counts),
        "confidenceCounts": dict(confidence_counts),
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
        "candidateCount": run["candidateCount"],
        "pending": run["pending"],
        "duplicate": run["duplicate"],
        "conflict": run["conflict"],
        "insufficientEvidence": run["insufficientEvidence"],
        "highPriority": run["highPriority"],
        "sourceStatuses": run["sourceStatuses"],
        "researchGapSummary": run["researchGapSummary"],
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
    }
    write_json(root / paths["rawSummary"].relative_to(ROOT), {"rawSignals": run["rawSignals"], "sourceStatuses": run["sourceStatuses"]})
    write_json(root / paths["normalized"].relative_to(ROOT), {"normalizedSignals": run["normalizedSignals"]})
    if write_internal_queue:
        write_json(root / paths["reviewQueue"].relative_to(ROOT), queue)
    write_json(root / paths["digestJson"].relative_to(ROOT), digest)
    write_text(root / paths["digestMd"].relative_to(ROOT), markdown_digest(run))
    return {key: str(value.relative_to(ROOT)) for key, value in paths.items()}


def audit_change_run(run: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    companies = company_index(root)
    candidate_ids = [candidate["candidateId"] for candidate in run.get("candidates", [])]
    duplicate_targets = {candidate["duplicateOf"] for candidate in run.get("candidates", []) if candidate.get("duplicateOf")}
    public_paths = [str(path).replace("\\", "/") for path in root.glob("frontend/public/**/*") if path.is_file()]
    serialized = json.dumps(run, ensure_ascii=False)
    secret_patterns = ["DART_API_KEY", "NAVER_API_HUB_CLIENT_SECRET", "Authorization", "request_headers", "raw_response"]
    invalid_candidates = []
    fingerprints = []
    for candidate in run.get("candidates", []):
        if candidate.get("confidence") not in CONFIDENCE_VALUES:
            invalid_candidates.append(candidate["candidateId"])
        if candidate.get("riskLevel") not in RISK_LEVELS:
            invalid_candidates.append(candidate["candidateId"])
        if candidate.get("status") not in CANDIDATE_STATUSES:
            invalid_candidates.append(candidate["candidateId"])
        if not candidate.get("evidenceSummary") or not candidate.get("sourceIds"):
            invalid_candidates.append(candidate["candidateId"])
        fingerprints.append(candidate.get("fingerprint"))
    duplicate_fingerprint_errors = len(fingerprints) - len(set(fingerprints)) - run.get("duplicate", 0)
    duplicate_fingerprint_errors = max(0, duplicate_fingerprint_errors)
    summary = {
        "schemaVersion": "company-change-audit-v1",
        "generatedAt": iso_now(),
        "valid": True,
        "companyCount": len(companies),
        "candidateIdUnique": len(candidate_ids) == len(set(candidate_ids)),
        "invalidCandidateCount": len(set(invalid_candidates)),
        "missingDuplicateOfCount": len([target for target in duplicate_targets if target not in set(candidate_ids)]),
        "duplicateFingerprintErrors": duplicate_fingerprint_errors,
        "publicReviewQueueExposureCount": len([path for path in public_paths if "company-change" in path or "review_queue" in path]),
        "secretExposureDetected": any(pattern in serialized for pattern in secret_patterns),
        "publicDataChanged": bool(run.get("publicDataChanged")),
        "daeseungContaminationCount": len(
            [
                candidate
                for candidate in run.get("candidates", [])
                if candidate["companyId"] == "daeseung-engineering"
                and any(term in normalize_text(candidate.get("evidenceSummary")) for term in ["최병천", "김해", "자동차 부품", "대승그룹"])
            ]
        ),
    }
    summary["valid"] = all(
        [
            summary["companyCount"] == 11,
            summary["candidateIdUnique"],
            summary["invalidCandidateCount"] == 0,
            summary["missingDuplicateOfCount"] == 0,
            summary["duplicateFingerprintErrors"] == 0,
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
        f"- Invalid candidates: `{summary['invalidCandidateCount']}`",
        f"- Missing duplicate refs: `{summary['missingDuplicateOfCount']}`",
        f"- Duplicate fingerprint errors: `{summary['duplicateFingerprintErrors']}`",
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
