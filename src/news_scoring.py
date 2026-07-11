from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from statistics import median
from typing import Any

from src.keywords import (
    GDELT_DOC_NEWS_CONSTRUCTION_CONTEXT,
    GDELT_DOC_NEWS_EXCLUDE_CONTEXT,
    GDELT_DOC_NEWS_STRONG_PHRASES,
    NAVER_NEWS_COMPETITOR_KEYWORDS,
    NAVER_NEWS_PUBLIC_KEYWORDS,
)


SCORE_VERSION = "unified-v2"
RELEVANCE_LEVELS = {"direct", "adjacent", "reference", "excluded"}

STRONG_PHRASES = [
    "모듈러 건축",
    "모듈러 건설",
    "모듈러 주택",
    "모듈러 공동주택",
    "모듈러 교실",
    "모듈러교실",
    "스틸 모듈러",
    "pc 모듈러",
    "공업화주택",
    "osc 건설",
    *GDELT_DOC_NEWS_STRONG_PHRASES,
]

WEAK_MODULAR_TERMS = [
    "모듈러",
    "osc",
    "프리패브",
    "프리팹",
    "조립식",
    "modular",
    "prefab",
    "prefabricated",
    "offsite",
    "off-site",
    "volumetric",
]

CONSTRUCTION_CONTEXT = [
    "건축",
    "건설",
    "시공",
    "제작",
    "설치",
    "주택",
    "공동주택",
    "학교",
    "교실",
    "기숙사",
    "병원",
    "호텔",
    "공장",
    "시설",
    "프로젝트",
    "공급",
    "착공",
    "수주",
    *GDELT_DOC_NEWS_CONSTRUCTION_CONTEXT,
    "classroom",
    "manufacturing",
]

REFERENCE_CONTEXT = [
    "건설 정책",
    "건설기술",
    "건설 기술",
    "스마트건설",
    "스마트 건설",
    "건설산업",
    "전문건설",
    "ai 건설",
    "로봇 건설",
    "construction policy",
    "construction technology",
    "smart construction",
    "robot construction",
    "ai construction",
]

EXCLUDED_CONTEXT = [
    "소프트웨어 모듈",
    "파이썬 모듈",
    "전자부품 모듈",
    "전자 부품 모듈",
    "자동차 전자부품 모듈",
    "자동차 모듈",
    "소형모듈원전",
    "소형 모듈 원전",
    *GDELT_DOC_NEWS_EXCLUDE_CONTEXT,
]

TITLE_BUSINESS_TERMS = [
    "수주",
    "계약",
    "발주",
    "프로젝트",
    "공급",
    "착공",
    "공장",
    "투자",
    "사업",
    "확대",
    "지원",
    "contract",
    "award",
    "awarded",
    "project",
    "supply",
    "supplies",
    "deliver",
    "delivery",
    "construction starts",
    "starts",
    "factory",
    "investment",
    "funding",
    "development",
    "expands",
    "expansion",
]

SUMMARY_BUSINESS_TERMS = [
    *TITLE_BUSINESS_TERMS,
    "developer",
    "contractor",
    "manufacturer",
    "manufacturing",
]

PUBLIC_OR_COMPANY_TERMS = [
    "공공기관",
    "발주기관",
    "한국토지주택공사",
    "lh",
    "gh",
    "sh",
    "국방부",
    "교육청",
    "public agency",
    "government",
    "council",
    "authority",
    "developer",
    "contractor",
    *NAVER_NEWS_PUBLIC_KEYWORDS,
    *[keyword.replace(" 모듈러", "") for keyword in NAVER_NEWS_COMPETITOR_KEYWORDS],
]


@dataclass(frozen=True)
class ScoreResult:
    relevance_score: int
    relevance_level: str
    relevance_score_version: str
    relevance_reasons: list[str]
    relevance_components: dict[str, int]


def clean_news_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_news_text(value: Any) -> str:
    return clean_news_text(value).casefold()


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = normalize_news_text(phrase)
    if not normalized_phrase:
        return False
    if re.fullmatch(r"[a-z0-9]+", normalized_phrase):
        return re.search(rf"(?<![a-z0-9]){re.escape(normalized_phrase)}(?![a-z0-9])", text) is not None
    return normalized_phrase in text


def _first_match(text: str, phrases: list[str]) -> str:
    for phrase in phrases:
        if _contains_phrase(text, phrase):
            return phrase
    return ""


def parse_news_date(value: Any) -> date | None:
    text = clean_news_text(value)
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).date()
        except ValueError:
            pass
    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).date()
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def _item_date(item: dict[str, Any]) -> date | None:
    return parse_news_date(item.get("published_at") or item.get("posted_at") or item.get("pub_date"))


def _item_organization(item: dict[str, Any]) -> str:
    return clean_news_text(item.get("organization") or item.get("media") or item.get("publisher") or item.get("source_name") or item.get("source"))


def _core_score(title: str, summary: str) -> tuple[int, str, list[str]]:
    combined = f"{title} {summary}".strip()
    excluded = _first_match(combined, EXCLUDED_CONTEXT)
    if excluded:
        return 0, "excluded", [f"제외 문맥: {excluded}"]

    title_strong = _first_match(title, STRONG_PHRASES)
    if title_strong:
        return 60, "direct", [f"제목 직접 구문: {title_strong}"]

    title_weak = _first_match(title, WEAK_MODULAR_TERMS)
    title_context = _first_match(title, CONSTRUCTION_CONTEXT)
    if title_weak and title_context:
        return 50, "direct", [f"제목 모듈러+건설 문맥: {title_weak}, {title_context}"]

    if title_weak:
        return 40, "adjacent", [f"제목 모듈러 약신호: {title_weak}"]

    summary_strong = _first_match(summary, STRONG_PHRASES)
    if summary_strong:
        return 35, "adjacent", [f"요약 직접 구문: {summary_strong}"]

    summary_weak = _first_match(summary, WEAK_MODULAR_TERMS)
    summary_context = _first_match(summary, CONSTRUCTION_CONTEXT)
    if summary_weak and summary_context:
        return 25, "adjacent", [f"요약 모듈러+건설 문맥: {summary_weak}, {summary_context}"]

    reference = _first_match(combined, REFERENCE_CONTEXT)
    if reference:
        return 15, "reference", [f"참고 건설 문맥: {reference}"]

    return 0, "excluded", ["관련 신호 없음"]


def _business_score(title: str, summary: str) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    title_business = _first_match(title, TITLE_BUSINESS_TERMS)
    if title_business:
        score += 10
        reasons.append(f"제목 사업 신호: {title_business}")
    title_entity = _first_match(title, PUBLIC_OR_COMPANY_TERMS)
    if title_entity:
        score += 5
        reasons.append(f"기관/기업 신호: {title_entity}")
    summary_business = _first_match(summary, SUMMARY_BUSINESS_TERMS)
    if summary_business:
        score += 5
        reasons.append(f"요약 사업 신호: {summary_business}")
    return min(20, score), reasons


def _freshness_score(item: dict[str, Any], today: date) -> tuple[int, list[str]]:
    published = _item_date(item)
    if not published:
        return 0, []
    age_days = max(0, (today - published).days)
    if (today - published).days < 0:
        reason = "미래 게시일: 0일 경과로 처리"
    else:
        reason = f"게시 {age_days}일 경과"
    if age_days <= 3:
        return 15, [reason]
    if age_days <= 7:
        return 10, [reason]
    if age_days <= 14:
        return 5, [reason]
    return 0, [reason]


def _completeness_score(item: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if _item_date(item):
        score += 2
        reasons.append("게시일 확인")
    if clean_news_text(item.get("summary") or item.get("description")):
        score += 2
        reasons.append("요약 있음")
    if _item_organization(item):
        score += 1
        reasons.append("출처 확인")
    return min(5, score), reasons


def score_news_item(item: dict[str, Any], today: date | datetime | None = None) -> ScoreResult:
    if isinstance(today, datetime):
        today_date = today.astimezone(timezone.utc).date() if today.tzinfo else today.date()
    else:
        today_date = today or date.today()

    title = normalize_news_text(item.get("title"))
    summary = normalize_news_text(item.get("summary") or item.get("description"))
    core, level, reasons = _core_score(title, summary)
    if level == "excluded":
        return ScoreResult(
            relevance_score=0,
            relevance_level="excluded",
            relevance_score_version=SCORE_VERSION,
            relevance_reasons=reasons,
            relevance_components={"core": 0, "business": 0, "freshness": 0, "completeness": 0},
        )

    business, business_reasons = _business_score(title, summary)
    freshness, freshness_reasons = _freshness_score(item, today_date)
    completeness, completeness_reasons = _completeness_score(item)
    score = min(100, core + business + freshness + completeness)
    return ScoreResult(
        relevance_score=int(score),
        relevance_level=level,
        relevance_score_version=SCORE_VERSION,
        relevance_reasons=[*reasons, *business_reasons, *freshness_reasons, *completeness_reasons],
        relevance_components={
            "core": int(core),
            "business": int(business),
            "freshness": int(freshness),
            "completeness": int(completeness),
        },
    )


def apply_unified_news_score(item: dict[str, Any], today: date | datetime | None = None) -> dict[str, Any]:
    scored = score_news_item(item, today=today)
    copied = dict(item)
    copied["relevance_score"] = scored.relevance_score
    copied["relevance_level"] = scored.relevance_level
    copied["relevance_score_version"] = scored.relevance_score_version
    copied["relevance_reasons"] = scored.relevance_reasons
    copied["relevance_components"] = scored.relevance_components
    return copied


def apply_unified_news_scores(items: list[dict[str, Any]], today: date | datetime | None = None) -> list[dict[str, Any]]:
    return [apply_unified_news_score(item, today=today) for item in items]


def _score_values(items: list[dict[str, Any]]) -> list[int]:
    values: list[int] = []
    for item in items:
        try:
            score = int(item.get("relevance_score"))
        except (TypeError, ValueError):
            continue
        values.append(score)
    return values


def _score_stats(values: list[int]) -> dict[str, int | None]:
    if not values:
        return {"min": None, "median": None, "max": None}
    return {
        "min": min(values),
        "median": int(median(values)),
        "max": max(values),
    }


def news_score_audit_stats(
    before_items: list[dict[str, Any]],
    after_items: list[dict[str, Any]],
) -> dict[str, Any]:
    domestic = [item for item in after_items if item.get("source") != "해외 모듈러 RSS"]
    overseas = [item for item in after_items if item.get("source") == "해외 모듈러 RSS"]
    level_counts = {level: 0 for level in ("direct", "adjacent", "reference", "excluded")}
    range_violation_count = 0
    missing_level_count = 0
    missing_version_count = 0
    for item in after_items:
        try:
            score = int(item.get("relevance_score"))
        except (TypeError, ValueError):
            range_violation_count += 1
            score = None
        if score is not None and (score < 0 or score > 100):
            range_violation_count += 1
        level = item.get("relevance_level")
        if level in level_counts:
            level_counts[level] += 1
        else:
            missing_level_count += 1
        if item.get("relevance_score_version") != SCORE_VERSION:
            missing_version_count += 1

    before_ids = {str(item.get("id")) for item in before_items if item.get("id") is not None}
    after_ids = {str(item.get("id")) for item in after_items if item.get("id") is not None}
    return {
        "score_version": SCORE_VERSION,
        "news_score_total_count": len(after_items),
        "news_score_domestic_count": len(domestic),
        "news_score_overseas_count": len(overseas),
        "news_score_level_counts": level_counts,
        "news_score_domestic_score_stats": _score_stats(_score_values(domestic)),
        "news_score_overseas_score_stats": _score_stats(_score_values(overseas)),
        "news_score_range_violation_count": range_violation_count,
        "news_score_missing_level_count": missing_level_count,
        "news_score_missing_version_count": missing_version_count,
        "news_score_existing_id_retained_count": len(before_ids & after_ids),
        "news_score_existing_id_missing_count": len(before_ids - after_ids),
    }
