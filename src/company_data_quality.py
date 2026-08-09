from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_COMPANIES_PATH = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"

VERIFICATION_STATUSES = {
    "verified_primary",
    "verified_cross_source",
    "partially_verified",
    "secondary_only",
    "conflicting",
    "stale",
    "unverified",
    "research_required",
    "not_publicly_available",
    "not_applicable",
}

CONFIDENCE_VALUES = {"high", "medium", "low", "unknown"}
CANONICAL_ROLES = {"general_contractor", "specialist_manufacturer", "modular_integrator", "modular_specialist"}
FACILITY_STATUSES = {"active", "operating", "under_construction", "planned", "suspended", "closed", "unknown"}
PROJECT_STATUSES = {
    "planned",
    "proposed",
    "bid",
    "bid_announced",
    "bid_submitted",
    "selected",
    "awarded",
    "contracted",
    "under_construction",
    "completed",
    "cancelled",
    "suspended",
    "unconfirmed",
    "unknown",
}
TECH_STATUSES = {"registered", "applied", "filed", "published", "expired", "rejected", "withdrawn", "invalidated", "claimed", "active", "unknown"}

SOURCE_TIER_BY_TYPE = {
    "dart": "tier_1",
    "company_official": "tier_1",
    "public_official": "tier_1",
    "patent": "tier_1",
    "public_procurement": "tier_1",
    "media_and_research": "tier_2",
    "media": "tier_2",
    "research": "tier_2",
    "company_information": "tier_3",
    "factory_database": "tier_3",
    "manual_verified_research": "internal_verified",
}

FIELD_AREAS = {
    "identity": [
        "company_name",
        "company_profile.established_at",
        "company_profile.representative",
        "headquarters",
        "website_url",
        "company_profile.major_businesses",
    ],
    "financials": ["financials"],
    "production": ["production"],
    "projects": ["project_portfolio"],
    "technology": ["technology"],
    "recent_signals": ["recent_signals"],
    "sources": ["sources", "field_sources"],
    "metadata": ["last_verified_at", "data_confidence", "review_status"],
}

@dataclass(frozen=True)
class QualityWeights:
    completeness: int = 30
    source_quality: int = 25
    freshness: int = 20
    consistency: int = 15
    modular_specificity: int = 10


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlsplit(str(url).strip())
    query = "&".join(
        part
        for part in parsed.query.split("&")
        if part and not part.lower().startswith(("utm_", "fbclid=", "gclid="))
    )
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/") or parsed.path, query, ""))


def get_path_value(row: dict[str, Any], path: str) -> Any:
    value: Any = row
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def is_populated(value: Any) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        return any(is_populated(item) for item in value.values())
    return True


def source_tier(source: dict[str, Any]) -> str:
    if source.get("source_tier"):
        return str(source["source_tier"])
    return SOURCE_TIER_BY_TYPE.get(str(source.get("source_type")), "tier_3")


def load_public_company_universe(root: Path = ROOT) -> list[dict[str, Any]]:
    payload = read_json(root / PUBLIC_COMPANIES_PATH.relative_to(ROOT))
    return [dict(row, source_file="frontend/public/data/companies/companies.json") for row in payload.get("companies", [])]


def source_registry(companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    registry: dict[tuple[str, str | None], dict[str, Any]] = {}
    for company in companies:
        for source in company.get("sources", []) or []:
            source_id = str(source.get("source_id") or "")
            url = clean_url(source.get("source_url") or source.get("url"))
            key = (source_id, url)
            entry = registry.setdefault(
                key,
                {
                    "sourceId": source_id,
                    "companyIds": [],
                    "title": source.get("title") or source.get("source_name") or source_id,
                    "publisher": source.get("publisher"),
                    "url": url,
                    "sourceType": source.get("source_type"),
                    "sourceTier": source_tier(source),
                    "publishedAt": source.get("published_at"),
                    "accessedAt": source.get("accessed_at"),
                    "language": "ko",
                    "supports": sorted(set(source.get("supported_claims") or source.get("supports") or [])),
                    "archiveStatus": "not_archived",
                    "notes": source.get("verification_note") or source.get("notes"),
                },
            )
            if company["company_id"] not in entry["companyIds"]:
                entry["companyIds"].append(company["company_id"])
            entry["companyIds"].sort()
    return sorted(registry.values(), key=lambda item: (item["sourceTier"], item["sourceId"]))


def quality_rows(companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for company in companies:
        sources = company.get("sources", []) or []
        tiers = Counter(source_tier(source) for source in sources)
        field_count = sum(len(paths) for paths in FIELD_AREAS.values())
        populated = 0
        unresolved = len(company.get("research_gaps", []) or [])
        for paths in FIELD_AREAS.values():
            for path in paths:
                populated += 1 if is_populated(get_path_value(company, path)) else 0
        source_count = len(sources)
        tier1_count = tiers.get("tier_1", 0)
        source_quality_ratio = min(1.0, (tier1_count * 1.0 + tiers.get("tier_2", 0) * 0.65 + tiers.get("tier_3", 0) * 0.35 + tiers.get("internal_verified", 0) * 0.45) / max(1, source_count))
        completeness_ratio = populated / max(1, field_count)
        latest_year = latest_verification_year(company)
        freshness_ratio = 1 if latest_year >= 2026 else 0.75 if latest_year == 2025 else 0.5 if latest_year >= 2024 else 0.25
        conflicts = len(company.get("conflicting_values", []) or [])
        consistency_ratio = 1 if conflicts == 0 else max(0, 1 - conflicts / 3)
        modular_ratio = modular_specificity(company)
        weights = QualityWeights()
        score = round(
            completeness_ratio * weights.completeness
            + source_quality_ratio * weights.source_quality
            + freshness_ratio * weights.freshness
            + consistency_ratio * weights.consistency
            + modular_ratio * weights.modular_specificity,
            1,
        )
        rows.append(
            {
                "companyId": company["company_id"],
                "displayName": company.get("company_name"),
                "canonicalRole": company.get("company_type"),
                "detailRoute": f"/companies/{company['company_id']}",
                "sourceFile": company.get("source_file"),
                "totalFields": field_count,
                "populatedFields": populated,
                "sourcedFields": sourced_record_count(company),
                "tier1SourcedFields": tier1_count,
                "verifiedFields": verified_record_count(company),
                "conflictingFields": conflicts,
                "staleFields": 0 if latest_year >= 2025 else 1,
                "unresolvedFields": unresolved,
                "sourceCounts": dict(tiers),
                "score": score,
                "scoreBand": score_band(score),
                "components": {
                    "completeness": round(completeness_ratio * weights.completeness, 1),
                    "sourceQuality": round(source_quality_ratio * weights.source_quality, 1),
                    "freshness": round(freshness_ratio * weights.freshness, 1),
                    "consistency": round(consistency_ratio * weights.consistency, 1),
                    "modularSpecificity": round(modular_ratio * weights.modular_specificity, 1),
                },
                "topResearchGaps": top_research_gaps(company, tiers),
            }
        )
    return sorted(rows, key=lambda item: item["score"])


def latest_verification_year(company: dict[str, Any]) -> int:
    values = [company.get("last_verified_at")]
    values += [source.get("accessed_at") or source.get("published_at") for source in company.get("sources", []) or []]
    years = []
    for value in values:
        if not value:
            continue
        match = re.search(r"(20\d{2})", str(value))
        if match:
            years.append(int(match.group(1)))
    return max(years) if years else 0


def sourced_record_count(company: dict[str, Any]) -> int:
    count = 0
    for collection in ["financials", "production", "project_portfolio", "recent_signals"]:
        for record in company.get(collection, []) or []:
            if record.get("source_ids"):
                count += 1
    for records in (company.get("technology") or {}).values():
        if isinstance(records, list):
            count += sum(1 for record in records if isinstance(record, dict) and record.get("source_ids"))
    return count


def verified_record_count(company: dict[str, Any]) -> int:
    count = 0
    for collection in ["production", "project_portfolio"]:
        for record in company.get(collection, []) or []:
            status = str(record.get("verification_status") or record.get("evidence_status") or "")
            if status in {"official_verified", "verified", "cross_verified", "partially_verified"}:
                count += 1
    for records in (company.get("technology") or {}).values():
        if isinstance(records, list):
            count += sum(1 for record in records if str(record.get("verification_status") or record.get("status")) in {"official_verified", "registered", "verified"})
    return count


def modular_specificity(company: dict[str, Any]) -> float:
    score = 0
    if company.get("modular_methods"):
        score += 0.25
    if company.get("target_markets"):
        score += 0.2
    if company.get("project_portfolio"):
        score += 0.25
    if company.get("technology") and any(company["technology"].values()):
        score += 0.2
    if company.get("production"):
        score += 0.1
    return min(1.0, score)


def score_band(score: float) -> str:
    if score >= 90:
        return "검증 우수"
    if score >= 75:
        return "운영 가능"
    if score >= 60:
        return "보강 필요"
    if score >= 40:
        return "주의"
    return "핵심 조사 필요"


def top_research_gaps(company: dict[str, Any], tiers: Counter[str]) -> list[str]:
    gaps = []
    for gap in company.get("research_gaps", []) or []:
        text = gap.get("description") or gap.get("note") or gap.get("area")
        if text and str(text) not in gaps:
            gaps.append(str(text))
    if not tiers.get("tier_1"):
        gaps.append("공식·공공 원천 출처 registry 연결 필요")
    if not company.get("website_url"):
        gaps.append("공식 홈페이지 확인 필요")
    if not company.get("production"):
        gaps.append("운영 생산시설 공개자료 확인 필요")
    if not company.get("recent_signals"):
        gaps.append("최근 24개월 동향 근거 추가 확인 필요")
    return gaps[:5]


def identity_status(company: dict[str, Any]) -> dict[str, Any]:
    profile = company.get("company_profile") or {}
    missing = []
    checks = {
        "legalName": profile.get("legal_name") or company.get("company_name"),
        "displayName": company.get("company_name"),
        "representative": profile.get("representative"),
        "foundedDate": profile.get("established_at"),
        "headquarters": company.get("headquarters"),
        "officialWebsite": company.get("website_url"),
        "mainBusiness": profile.get("major_businesses"),
        "modularRole": company.get("company_type"),
    }
    for key, value in checks.items():
        if not is_populated(value):
            missing.append(key)
    return {
        "companyId": company["company_id"],
        "displayName": company.get("company_name"),
        "status": "partially_verified" if missing else "verified_cross_source",
        "missingFields": missing,
        "sameNameRisk": "explicitly_controlled" if company["company_id"] == "daeseung-engineering" else "not_detected",
    }


def validate_quality_artifacts(companies: list[dict[str, Any]], registry: list[dict[str, Any]], quality: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues = []
    if len(companies) != 11:
        issues.append({"code": "company_count", "message": f"expected 11 companies, got {len(companies)}"})
    ids = [company.get("company_id") for company in companies]
    for duplicated in [item for item, count in Counter(ids).items() if count > 1]:
        issues.append({"code": "duplicate_company_id", "companyId": duplicated})
    for company in companies:
        if company.get("company_type") not in CANONICAL_ROLES:
            issues.append({"code": "invalid_company_role", "companyId": company.get("company_id"), "value": company.get("company_type")})
        if company.get("data_confidence") not in CONFIDENCE_VALUES:
            issues.append({"code": "invalid_confidence", "companyId": company.get("company_id"), "value": company.get("data_confidence")})
        if company.get("company_id") == "daeseung-engineering":
            blob = json.dumps(company, ensure_ascii=False)
            for forbidden in ["최병천", "대승그룹", "자동차 부품"]:
                if forbidden in blob:
                    issues.append({"code": "daeseung_same_name_contamination", "value": forbidden})
        for record in company.get("production", []) or []:
            status = record.get("operation_status", "unknown")
            if status not in FACILITY_STATUSES:
                issues.append({"code": "invalid_facility_status", "companyId": company.get("company_id"), "value": status})
        for record in company.get("project_portfolio", []) or []:
            status = record.get("project_status", "unknown")
            if status not in PROJECT_STATUSES:
                issues.append({"code": "invalid_project_status", "companyId": company.get("company_id"), "value": status})
        for records in (company.get("technology") or {}).values():
            if isinstance(records, list):
                for record in records:
                    status = record.get("status", "unknown")
                    if status not in TECH_STATUSES:
                        issues.append({"code": "invalid_technology_status", "companyId": company.get("company_id"), "value": status})
    source_ids = [item.get("sourceId") for item in registry]
    for duplicated in [item for item, count in Counter(source_ids).items() if item and count > 1]:
        issues.append({"code": "duplicate_source_id", "sourceId": duplicated})
    for row in quality:
        if row["score"] < 0 or row["score"] > 100:
            issues.append({"code": "invalid_quality_score", "companyId": row["companyId"], "score": row["score"]})
    return issues


def build_quality_audit(root: Path = ROOT) -> dict[str, Any]:
    companies = load_public_company_universe(root)
    registry = source_registry(companies)
    quality = quality_rows(companies)
    identities = [identity_status(company) for company in companies]
    issues = validate_quality_artifacts(companies, registry, quality)
    return {
        "schemaVersion": "company-data-quality-audit-v1",
        "generatedAt": current_timestamp(),
        "companyCount": len(companies),
        "companies": quality,
        "identityChecks": identities,
        "sourceSummary": dict(Counter(item["sourceTier"] for item in registry)),
        "sourceCount": len(registry),
        "validationIssues": issues,
        "status": "passed" if not issues else "failed",
    }
