from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPANIES = ROOT / "frontend/public/data/companies/companies.json"
DEFAULT_DAESEUNG = ROOT / "frontend/src/data/daeseungEngineeringCompany.js"
DEFAULT_NEWS = ROOT / "frontend/public/data/news.json"
DEFAULT_BUSINESS = ROOT / "frontend/public/data/business.json"
DEFAULT_OUTPUT = ROOT / "frontend/public/data/companies/company-activities.json"
DEFAULT_AUDIT_DIR = ROOT / "artifacts/company_activity_timeline"

SCHEMA_VERSION = "company-activities-v1"
MAX_ACTIVITIES_PER_COMPANY = 100
RETENTION_MONTHS = 24
SAFE_SUMMARY_LIMIT = 240

MODULAR_CONTEXT_TERMS = [
    "모듈러",
    "프리패브",
    "prefab",
    "prefabricated",
    "modular",
    "volumetric",
    "offsite",
    "factory-built",
]

AMBIGUOUS_ALIASES = {
    "gs",
    "dl",
    "삼성",
    "현대",
    "금강",
    "대승",
    "plan",
}

BLOCKED_DAESEUNG_CONTEXT = [
    "최병천",
    "김해",
    "수처리",
    "제진기",
    "자동차",
    "대승그룹",
    "대승공업",
]

ACTIVITY_KEYWORDS = [
    ("factory", ["공장", "생산시설", "증설", "생산라인", "제작시설", "factory", "plant", "production line"]),
    ("investment", ["투자", "증자", "자금조달", "인수", "매각", "investment", "funding", "acquisition"]),
    ("technology", ["특허", "신기술", "인증", "연구개발", "r&d", "patent", "technology", "certification"]),
    ("financial", ["실적", "매출", "영업이익", "감사보고서", "revenue", "profit", "earnings"]),
    ("partnership", ["협약", "mou", "업무협약", "공동개발", "파트너십", "partnership"]),
    ("contract", ["수주", "계약", "선정", "우선협상", "낙찰", "contract", "awarded"]),
    ("bid", ["입찰", "공고", "발주계획", "공모", "bid", "tender"]),
    ("project", ["프로젝트", "사업", "착공", "준공", "시공", "공급", "project", "construction"]),
    ("management", ["대표이사", "임원", "조직개편", "ceo", "executive"]),
]

FILTER_CONFIDENCES = {"high", "medium"}


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").normalize("NFC") if hasattr(str(value or ""), "normalize") else str(value or "")).strip().lower()


def normalized_search_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def items_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "companies"):
            if isinstance(payload.get(key), list):
                return [item for item in payload[key] if isinstance(item, dict)]
    return []


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    candidates = [text, text.replace("Z", "+00:00")]
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        return None


def iso_date(value: Any) -> str:
    parsed = parse_datetime(value)
    if not parsed:
        return ""
    return parsed.date().isoformat()


def safe_url(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return text


def short_summary(*values: Any) -> str | None:
    text = re.sub(r"\s+", " ", " ".join(str(value or "") for value in values if value)).strip()
    if not text:
        return None
    return text[:SAFE_SUMMARY_LIMIT]


def stable_hash(*parts: Any, length: int = 16) -> str:
    payload = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def parse_js_string_array(text: str, key: str) -> list[str]:
    match = re.search(rf"{re.escape(key)}\s*:\s*\[(.*?)\]", text, flags=re.S)
    if not match:
        return []
    return re.findall(r'"([^"]+)"', match.group(1))


def parse_js_string_value(text: str, key: str) -> str:
    match = re.search(rf"{re.escape(key)}\s*:\s*\"([^\"]*)\"", text)
    return match.group(1) if match else ""


def load_daeseung_company(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    company_id = parse_js_string_value(text, "company_id")
    company_name = parse_js_string_value(text, "company_name")
    if not company_id or not company_name:
        return None
    return {
        "company_id": company_id,
        "company_name": company_name,
        "company_name_en": parse_js_string_value(text, "company_name_en"),
        "legal_name": parse_js_string_value(text, "legal_name"),
        "aliases": parse_js_string_array(text, "aliases"),
    }


def load_companies(companies_path: Path, daeseung_path: Path) -> list[dict[str, Any]]:
    companies = items_from_payload(load_json(companies_path))
    daeseung = load_daeseung_company(daeseung_path)
    if daeseung and all(row.get("company_id") != daeseung["company_id"] for row in companies):
        companies.append(daeseung)
    return companies


def is_ambiguous_alias(alias: str) -> bool:
    normalized = normalized_search_text(alias)
    compact = re.sub(r"[\s().㈜주식회사&]+", "", normalized)
    if not compact or compact in AMBIGUOUS_ALIASES:
        return True
    if len(compact) <= 1:
        return True
    if len(compact) <= 2 and not re.search(r"[가-힣]", compact):
        return True
    return False


def build_alias_registry(companies: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    collisions: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    for company in companies:
        company_id = str(company.get("company_id") or "")
        candidates: list[tuple[str, str]] = []
        for key, match_type in (
            ("company_name", "display_name"),
            ("legal_name", "legal_name"),
            ("company_name_en", "english_name"),
        ):
            if company.get(key):
                candidates.append((str(company[key]), match_type))
        for alias in company.get("aliases") or []:
            candidates.append((str(alias), "alias"))
        unique: dict[str, str] = {}
        for alias, match_type in candidates:
            cleaned = re.sub(r"\s+", " ", alias.strip())
            if cleaned:
                unique.setdefault(cleaned, match_type)
        for alias, match_type in unique.items():
            normalized = normalized_search_text(alias)
            ambiguous = is_ambiguous_alias(alias)
            previous_company = seen.get(normalized)
            if previous_company and previous_company != company_id:
                ambiguous = True
                collisions.append({"alias": alias, "companyIds": sorted([previous_company, company_id])})
            seen.setdefault(normalized, company_id)
            rows.append(
                {
                    "companyId": company_id,
                    "alias": alias,
                    "matchType": match_type,
                    "caseSensitive": False,
                    "ambiguous": ambiguous,
                }
            )
    return rows, collisions


def has_modular_context(text: str) -> bool:
    folded = normalized_search_text(text)
    return any(term.casefold() in folded for term in MODULAR_CONTEXT_TERMS)


def alias_in_text(alias: str, text: str) -> bool:
    if not alias or not text:
        return False
    folded_alias = normalized_search_text(alias)
    folded_text = normalized_search_text(text)
    if re.fullmatch(r"[a-z0-9&.\s]+", folded_alias):
        pattern = rf"(?<![a-z0-9]){re.escape(folded_alias)}(?![a-z0-9])"
        return bool(re.search(pattern, folded_text))
    return folded_alias in folded_text


def find_company_matches(record: dict[str, Any], aliases: list[dict[str, Any]], *, source_kind: str) -> tuple[list[dict[str, Any]], Counter[str]]:
    stats: Counter[str] = Counter()
    title = str(record.get("title") or "")
    summary = str(record.get("summary") or record.get("description") or "")
    project_name = str(record.get("project_name") or "")
    organization = str(record.get("organization") or record.get("demand_org") or "")
    body = " ".join([title, summary, project_name, organization])
    context_ok = has_modular_context(body)
    matches: list[dict[str, Any]] = []

    for alias in aliases:
        if alias.get("ambiguous"):
            if alias_in_text(alias["alias"], body):
                stats["ambiguous_excluded"] += 1
            continue
        alias_text = alias["alias"]
        title_match = alias_in_text(alias_text, " ".join([title, project_name]))
        summary_match = alias_in_text(alias_text, summary)
        org_only_match = alias_in_text(alias_text, organization) and not title_match and not summary_match
        if not (title_match or summary_match or org_only_match):
            continue
        if alias["companyId"] == "daeseung-engineering" and any(term in body for term in BLOCKED_DAESEUNG_CONTEXT):
            stats["identity_guard_excluded"] += 1
            continue
        if org_only_match and source_kind == "business":
            stats["ordering_org_only_excluded"] += 1
            continue
        if title_match:
            confidence = "high"
            reason = "title_or_project_name_alias"
        elif summary_match and context_ok:
            confidence = "medium"
            reason = "summary_alias_with_modular_context"
        else:
            stats["low_confidence_excluded"] += 1
            continue
        matches.append(
            {
                "companyId": alias["companyId"],
                "matchedAlias": alias_text,
                "matchReason": reason,
                "confidence": confidence,
            }
        )
    deduped: dict[str, dict[str, Any]] = {}
    rank = {"high": 2, "medium": 1}
    for match in matches:
        current = deduped.get(match["companyId"])
        if not current or rank[match["confidence"]] > rank[current["confidence"]]:
            deduped[match["companyId"]] = match
    return list(deduped.values()), stats


def classify_activity(text: str, source_kind: str) -> str:
    if source_kind == "business":
        return "bid"
    folded = normalized_search_text(text)
    for activity_type, keywords in ACTIVITY_KEYWORDS:
        if any(keyword.casefold() in folded for keyword in keywords):
            return activity_type
    return "general_news"


def news_activity(record: dict[str, Any], match: dict[str, Any]) -> dict[str, Any]:
    source_url = safe_url(record.get("original_url")) or safe_url(record.get("naver_url"))
    published_at = iso_date(record.get("published_at"))
    title = str(record.get("title") or "").strip()
    activity_type = classify_activity(" ".join([title, str(record.get("summary") or "")]), "news")
    record_id = str(record.get("id") or "")
    return {
        "activityId": f"news-{match['companyId']}-{stable_hash(source_url, record_id, title, published_at)}",
        "companyId": match["companyId"],
        "activityType": activity_type,
        "title": title,
        "summary": short_summary(record.get("summary")),
        "publishedAt": published_at,
        "sourceType": "news",
        "sourceName": record.get("source") or record.get("source_name") or record.get("media") or "뉴스",
        "sourceUrl": source_url,
        "sourceRecordId": record_id or None,
        "matchedAlias": match["matchedAlias"],
        "matchReason": match["matchReason"],
        "confidence": match["confidence"],
        "projectName": None,
        "organization": record.get("media") or record.get("publisher_name"),
        "region": record.get("publisher_country_name") or record.get("publisher_region"),
        "amount": None,
        "status": record.get("relevance_level") or None,
    }


def business_activity(record: dict[str, Any], match: dict[str, Any]) -> dict[str, Any]:
    source_url = safe_url(record.get("external_original_url"))
    published_at = iso_date(record.get("posted_at") or record.get("last_seen_at"))
    title = str(record.get("title") or record.get("project_name") or "").strip()
    record_id = str(record.get("source_record_id") or record.get("bid_no") or record.get("id") or "")
    return {
        "activityId": f"business-{match['companyId']}-{stable_hash(record_id, source_url, title, published_at)}",
        "companyId": match["companyId"],
        "activityType": classify_activity(" ".join([title, str(record.get("summary") or ""), str(record.get("source_type") or "")]), "business"),
        "title": title,
        "summary": short_summary(record.get("summary")),
        "publishedAt": published_at,
        "sourceType": "business",
        "sourceName": record.get("source_name") or record.get("source") or "사업정보",
        "sourceUrl": source_url,
        "sourceRecordId": record_id or None,
        "matchedAlias": match["matchedAlias"],
        "matchReason": match["matchReason"],
        "confidence": match["confidence"],
        "projectName": record.get("project_name") or None,
        "organization": record.get("organization") or record.get("demand_org") or None,
        "region": record.get("region") or None,
        "amount": record.get("amount") if isinstance(record.get("amount"), (int, float)) else None,
        "status": record.get("opportunity_status") or record.get("notice_status") or None,
    }


def dedupe_key(activity: dict[str, Any]) -> tuple[str, str, str]:
    company_id = str(activity.get("companyId") or "")
    if activity.get("sourceUrl"):
        return (company_id, "url", str(activity["sourceUrl"]))
    if activity.get("sourceRecordId"):
        return (company_id, "record", f"{activity.get('sourceType')}:{activity['sourceRecordId']}")
    title_key = re.sub(r"\W+", "", str(activity.get("title") or "").casefold())
    return (company_id, "title-date", f"{title_key}:{activity.get('publishedAt')}")


def sort_key(activity: dict[str, Any]) -> tuple[str, str]:
    return (str(activity.get("publishedAt") or ""), str(activity.get("activityId") or ""))


def build_timeline(
    *,
    companies: list[dict[str, Any]],
    news_items: list[dict[str, Any]],
    business_items: list[dict[str, Any]],
    existing_payload: dict[str, Any] | None,
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    aliases, collisions = build_alias_registry(companies)
    stats: Counter[str] = Counter()
    by_company: dict[str, list[dict[str, Any]]] = defaultdict(list)

    cutoff = now - timedelta(days=RETENTION_MONTHS * 31)

    for record in news_items:
        matches, match_stats = find_company_matches(record, aliases, source_kind="news")
        stats.update(match_stats)
        for match in matches:
            activity = news_activity(record, match)
            if activity["confidence"] in FILTER_CONFIDENCES and parse_datetime(activity["publishedAt"]) and parse_datetime(activity["publishedAt"]) >= cutoff:
                by_company[activity["companyId"]].append(activity)
                stats["news_activity_count"] += 1

    for record in business_items:
        matches, match_stats = find_company_matches(record, aliases, source_kind="business")
        stats.update(match_stats)
        for match in matches:
            activity = business_activity(record, match)
            if activity["confidence"] in FILTER_CONFIDENCES and parse_datetime(activity["publishedAt"]) and parse_datetime(activity["publishedAt"]) >= cutoff:
                by_company[activity["companyId"]].append(activity)
                stats["business_activity_count"] += 1

    if existing_payload:
        for company_row in existing_payload.get("companies") or []:
            company_id = company_row.get("companyId")
            if not company_id:
                continue
            for activity in company_row.get("activities") or []:
                if isinstance(activity, dict) and activity.get("confidence") in FILTER_CONFIDENCES:
                    by_company[str(company_id)].append(activity)
                    stats["existing_activity_count"] += 1

    company_ids = [str(company.get("company_id")) for company in companies if company.get("company_id")]
    output_rows = []
    duplicate_excluded = 0
    for company_id in company_ids:
        deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
        for activity in sorted(by_company.get(company_id, []), key=sort_key):
            key = dedupe_key(activity)
            if key in deduped:
                duplicate_excluded += 1
            deduped[key] = activity
        activities = sorted(deduped.values(), key=sort_key, reverse=True)[:MAX_ACTIVITIES_PER_COMPANY]
        output_rows.append({"companyId": company_id, "activityCount": len(activities), "activities": activities})

    audit = {
        "schemaVersion": "company-activity-audit-v1",
        "generatedAt": now.isoformat(),
        "companyCount": len(company_ids),
        "totalActivityCount": sum(row["activityCount"] for row in output_rows),
        "companiesWithActivities": sum(1 for row in output_rows if row["activityCount"]),
        "companyActivityCounts": {row["companyId"]: row["activityCount"] for row in output_rows},
        "newsActivityCount": stats["news_activity_count"],
        "businessActivityCount": stats["business_activity_count"],
        "existingActivityCount": stats["existing_activity_count"],
        "highConfidenceCount": sum(1 for row in output_rows for item in row["activities"] if item.get("confidence") == "high"),
        "mediumConfidenceCount": sum(1 for row in output_rows for item in row["activities"] if item.get("confidence") == "medium"),
        "lowConfidenceExcludedCount": stats["low_confidence_excluded"],
        "ambiguousExcludedCount": stats["ambiguous_excluded"],
        "identityGuardExcludedCount": stats["identity_guard_excluded"],
        "orderingOrgOnlyExcludedCount": stats["ordering_org_only_excluded"],
        "duplicateExcludedCount": duplicate_excluded,
        "aliasCollisionCount": len(collisions),
        "aliasCollisions": collisions,
        "zeroActivityCompanies": [row["companyId"] for row in output_rows if row["activityCount"] == 0],
        "sourceTypeCounts": dict(Counter(item["sourceType"] for row in output_rows for item in row["activities"])),
        "confidenceCounts": dict(Counter(item["confidence"] for row in output_rows for item in row["activities"])),
    }
    output = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": now.isoformat(),
        "companyCount": len(company_ids),
        "companies": output_rows,
    }
    return output, audit


def render_audit_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# Company Activity Timeline Audit",
        "",
        f"- Company count: {audit['companyCount']}",
        f"- Total activities: {audit['totalActivityCount']}",
        f"- Companies with activities: {audit['companiesWithActivities']}",
        f"- News-based activities: {audit['newsActivityCount']}",
        f"- Business-based activities: {audit['businessActivityCount']}",
        f"- High confidence: {audit['highConfidenceCount']}",
        f"- Medium confidence: {audit['mediumConfidenceCount']}",
        f"- Low confidence excluded: {audit['lowConfidenceExcludedCount']}",
        f"- Ambiguous alias excluded: {audit['ambiguousExcludedCount']}",
        f"- Identity guard excluded: {audit['identityGuardExcludedCount']}",
        f"- Ordering-org-only excluded: {audit['orderingOrgOnlyExcludedCount']}",
        f"- Duplicate excluded: {audit['duplicateExcludedCount']}",
        "",
        "## Company Activity Counts",
        "",
    ]
    for company_id, count in sorted(audit["companyActivityCounts"].items()):
        lines.append(f"- {company_id}: {count}")
    lines.extend(["", "## Zero Activity Companies", ""])
    if audit["zeroActivityCompanies"]:
        for company_id in audit["zeroActivityCompanies"]:
            lines.append(f"- {company_id}")
    else:
        lines.append("- None")
    if audit["aliasCollisions"]:
        lines.extend(["", "## Alias Collisions", ""])
        for row in audit["aliasCollisions"]:
            lines.append(f"- {row['alias']}: {', '.join(row['companyIds'])}")
    return "\n".join(lines) + "\n"


def write_outputs(output: dict[str, Any], audit: dict[str, Any], output_path: Path, audit_dir: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "company-activity-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (audit_dir / "company-activity-audit.md").write_text(render_audit_markdown(audit), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build company activity timelines from public news and business data.")
    parser.add_argument("--companies", type=Path, default=DEFAULT_COMPANIES)
    parser.add_argument("--daeseung-source", type=Path, default=DEFAULT_DAESEUNG)
    parser.add_argument("--news", type=Path, default=DEFAULT_NEWS)
    parser.add_argument("--business", type=Path, default=DEFAULT_BUSINESS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT_DIR)
    parser.add_argument("--now", default="")
    args = parser.parse_args()

    now = parse_datetime(args.now) if args.now else datetime.now(timezone.utc)
    if now is None:
        raise SystemExit("--now must be an ISO datetime")
    existing = load_json(args.output) if args.output.exists() else None
    companies = load_companies(args.companies, args.daeseung_source)
    news_items = items_from_payload(load_json(args.news))
    business_items = items_from_payload(load_json(args.business))
    output, audit = build_timeline(
        companies=companies,
        news_items=news_items,
        business_items=business_items,
        existing_payload=existing,
        now=now,
    )
    write_outputs(output, audit, args.output, args.audit_dir)
    print(
        "company_activity_timeline "
        f"companies={audit['companyCount']} "
        f"activities={audit['totalActivityCount']} "
        f"with_activities={audit['companiesWithActivities']} "
        f"news={audit['newsActivityCount']} "
        f"business={audit['businessActivityCount']} "
        f"ambiguous_excluded={audit['ambiguousExcludedCount']} "
        f"duplicates={audit['duplicateExcludedCount']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
