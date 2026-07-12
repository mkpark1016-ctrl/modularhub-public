from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from statistics import mean, median
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.news_publisher_country import COUNTRY_NAMES  # noqa: E402
from src.news_scoring import SCORE_VERSION  # noqa: E402
from src.news_publisher_region import publisher_region_fields  # noqa: E402
from src.overseas_news_rules import overseas_news_content_key  # noqa: E402


OVERSEAS_RSS_SOURCE = "해외 모듈러 RSS"
LEVEL_ORDER = {"direct": 0, "adjacent": 1, "reference": 2, "excluded": 3}
ALLOWED_LEVELS = set(LEVEL_ORDER)
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
}

REFERENCE_OR_UNRELATED_HINTS = (
    "software module",
    "modular software",
    "electronic module",
    "automotive module",
    "small modular reactor",
    "nuclear reactor",
)
COLLECTION_WARNINGS = [
    {
        "code": "known_important_bid_collection_failed",
        "impact": "Does not change scoring for existing public news; may delay new bid visibility.",
        "suggested_priority": "separate collector hotfix",
    },
    {
        "code": "g2b_procurement_plan_collection_failed",
        "impact": "Does not change scoring for existing public news; may reduce newly collected procurement-plan coverage.",
        "suggested_priority": "separate procurement-plan hotfix",
    },
    {
        "code": "partial_bid_or_news_collector_failure",
        "impact": "Existing public JSON is preserved by cumulative export guards; newly available records may be missing.",
        "suggested_priority": "inspect failing collector logs",
    },
    {
        "code": "d2b_legacy_api_stopped",
        "impact": "Known disabled source; not a relevance scoring issue.",
        "suggested_priority": "separate D2B GW API migration",
    },
    {
        "code": "node_action_runtime_deprecation",
        "impact": "No effect on news scores or public JSON content.",
        "suggested_priority": "workflow maintenance",
    },
]


def clean_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_datetime(value: Any) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
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
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def normalized_url(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    query = urlencode(
        sorted(
            (key, val)
            for key, val in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in TRACKING_PARAMS
        ),
        doseq=True,
    )
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", "", query, ""))


def domain_from_item(item: dict[str, Any]) -> str:
    for key in ("original_url", "url", "link", "naver_url"):
        url = normalized_url(item.get(key))
        if url:
            host = urlparse(url).hostname or ""
            return host.removeprefix("www.").lower()
    media = clean_text(item.get("media") or item.get("organization"))
    if "." in media and " " not in media:
        return media.removeprefix("www.").lower()
    return ""


def masked_url_for_report(value: Any) -> str:
    url = normalized_url(value)
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.hostname == "news.google.com" and parsed.query:
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "query=masked", ""))
    return url


def collector_region(item: dict[str, Any]) -> str:
    value = item.get("collection_pipeline")
    if value in {"domestic_pipeline", "rss_overseas_pipeline"}:
        return str(value)
    return str(publisher_region_fields(item).get("collection_pipeline") or "domestic_pipeline")


def publisher_region_candidate(item: dict[str, Any]) -> str:
    return str(publisher_region_fields(item).get("publisher_region") or "unknown")


def confirmed_publisher_country_code(item: dict[str, Any]) -> str:
    code = clean_text(item.get("publisher_country_code")).upper()
    confidence = clean_text(item.get("publisher_country_confidence")).lower()
    if code not in COUNTRY_NAMES:
        return ""
    if confidence == "unknown":
        return ""
    return code


def display_region_reason(item: dict[str, Any]) -> dict[str, str]:
    country_code = confirmed_publisher_country_code(item)
    if country_code:
        return {
            "region": "domestic" if country_code == "KR" else "overseas",
            "basis": "publisher_country_code",
        }
    publisher_region = clean_text(item.get("publisher_region"))
    if publisher_region in {"domestic", "overseas"}:
        return {"region": publisher_region, "basis": "publisher_region"}
    pipeline = clean_text(item.get("collection_pipeline"))
    if pipeline == "domestic_pipeline":
        return {"region": "domestic", "basis": "collection_pipeline"}
    if pipeline == "rss_overseas_pipeline":
        return {"region": "overseas", "basis": "collection_pipeline"}
    source_text = " ".join(
        clean_text(item.get(key)).casefold()
        for key in ("collection_source", "source", "source_name")
        if clean_text(item.get(key))
    )
    if "naver" in source_text or "국내" in source_text:
        return {"region": "domestic", "basis": "collection_source"}
    if "rss" in source_text or "overseas" in source_text or "해외" in source_text:
        return {"region": "overseas", "basis": "collection_source"}
    return {"region": "domestic", "basis": "fallback"}


def load_news_payload(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {}, [], [{"code": "json_read_error", "message": str(exc), "path": str(path)}]
    if isinstance(payload, list):
        raw_items = payload
        normalized_payload: dict[str, Any] = {}
    elif isinstance(payload, dict) and isinstance(payload.get("items"), list):
        raw_items = payload["items"]
        normalized_payload = payload
    else:
        return payload if isinstance(payload, dict) else {}, [], [{"code": "json_structure_error", "message": "news payload must contain an items array"}]

    errors: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items):
        if isinstance(item, dict):
            items.append(item)
        else:
            errors.append({"code": "item_structure_error", "index": index})
    return normalized_payload, items, errors


def percentile(values: list[int], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return float(ordered[lower])
    ratio = pos - lower
    return float(ordered[lower] * (1 - ratio) + ordered[upper] * ratio)


def score_distribution(items: list[dict[str, Any]]) -> dict[str, Any]:
    scores: list[int] = []
    for item in items:
        try:
            scores.append(int(item.get("relevance_score")))
        except (TypeError, ValueError):
            pass
    bins = {
        "0_19": sum(0 <= score <= 19 for score in scores),
        "20_39": sum(20 <= score <= 39 for score in scores),
        "40_59": sum(40 <= score <= 59 for score in scores),
        "60_79": sum(60 <= score <= 79 for score in scores),
        "80_100": sum(80 <= score <= 100 for score in scores),
    }
    level_counts = {level: 0 for level in ("direct", "adjacent", "reference", "excluded")}
    for item in items:
        level = item.get("relevance_level")
        if level in level_counts:
            level_counts[level] += 1
    return {
        "count": len(items),
        "min": min(scores) if scores else None,
        "p25": percentile(scores, 0.25),
        "median": median(scores) if scores else None,
        "average": round(mean(scores), 2) if scores else None,
        "p75": percentile(scores, 0.75),
        "max": max(scores) if scores else None,
        "level_counts": level_counts,
        "score_bins": bins,
    }


def component_stats(items: list[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    result: dict[str, dict[str, float | None]] = {}
    for component in ("core", "business", "freshness", "completeness"):
        values: list[int] = []
        for item in items:
            components = item.get("relevance_components")
            if isinstance(components, dict):
                try:
                    values.append(int(components.get(component)))
                except (TypeError, ValueError):
                    pass
        result[component] = {
            "average": round(mean(values), 2) if values else None,
            "median": median(values) if values else None,
        }
    return result


def sort_timestamp(item: dict[str, Any]) -> float:
    parsed = parse_datetime(item.get("published_at"))
    return parsed.timestamp() if parsed else 0.0


def news_sort_key(item: dict[str, Any]) -> tuple[int, int, float, str]:
    level = item.get("relevance_level")
    try:
        score = int(item.get("relevance_score"))
    except (TypeError, ValueError):
        score = -1
    return (
        LEVEL_ORDER.get(str(level), 99),
        -score,
        -sort_timestamp(item),
        clean_text(item.get("title")).casefold(),
    )


def contract_audit(items: list[dict[str, Any]]) -> dict[str, Any]:
    counters: Counter[str] = Counter()
    issues: list[dict[str, Any]] = []
    ids: dict[str, dict[str, Any]] = {}
    urls: dict[str, dict[str, Any]] = {}
    title_dates: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        item_id = item.get("id")
        title = clean_text(item.get("title"))
        if item.get("relevance_score_version") != SCORE_VERSION:
            counters["score_version_mismatch_count"] += 1
            issues.append({"code": "score_version_mismatch", "id": item_id, "title": title})
        level = item.get("relevance_level")
        if not level:
            counters["relevance_level_missing_count"] += 1
            issues.append({"code": "relevance_level_missing", "id": item_id, "title": title})
        elif level not in ALLOWED_LEVELS:
            counters["relevance_level_invalid_count"] += 1
            issues.append({"code": "relevance_level_invalid", "id": item_id, "title": title, "level": level})
        try:
            score = int(item.get("relevance_score"))
        except (TypeError, ValueError):
            counters["relevance_score_missing_count"] += 1
            issues.append({"code": "relevance_score_missing", "id": item_id, "title": title})
            score = None
        if score is not None and not 0 <= score <= 100:
            counters["relevance_score_range_violation_count"] += 1
            issues.append({"code": "relevance_score_range_violation", "id": item_id, "title": title, "score": score})
        if not isinstance(item.get("relevance_components"), dict):
            counters["relevance_components_missing_count"] += 1
            issues.append({"code": "relevance_components_missing", "id": item_id, "title": title})
        if not isinstance(item.get("relevance_reasons"), list) or not item.get("relevance_reasons"):
            counters["relevance_reasons_missing_count"] += 1
            issues.append({"code": "relevance_reasons_missing", "id": item_id, "title": title})
        if level == "excluded":
            counters["excluded_public_count"] += 1
            issues.append({"code": "excluded_public", "id": item_id, "title": title})
        if item_id in (None, ""):
            counters["id_missing_count"] += 1
            issues.append({"code": "id_missing", "title": title})
        else:
            item_id_text = str(item_id)
            if item_id_text in ids:
                counters["id_duplicate_count"] += 1
                issues.append({"code": "id_duplicate", "id": item_id, "duplicate_of": ids[item_id_text].get("id"), "title": title})
            else:
                ids[item_id_text] = item
        url = normalized_url(item.get("original_url") or item.get("url"))
        if url:
            if url in urls:
                counters["url_duplicate_count"] += 1
                issues.append({"code": "url_duplicate", "id": item_id, "duplicate_of": urls[url].get("id"), "title": title, "domain": urlparse(url).hostname})
            else:
                urls[url] = item
        title_date = overseas_news_content_key(title, item.get("published_at"))
        if all(title_date):
            if title_date in title_dates:
                counters["title_published_at_duplicate_count"] += 1
                issues.append(
                    {
                        "code": "title_published_at_duplicate",
                        "id": item_id,
                        "duplicate_of": title_dates[title_date].get("id"),
                        "title": title,
                        "published_at": item.get("published_at"),
                    }
                )
            else:
                title_dates[title_date] = item
    return {
        "counts": dict(counters),
        "issue_count": len(issues),
        "issues_sample": issues[:100],
    }


def region_audit(items: list[dict[str, Any]]) -> dict[str, Any]:
    mismatches: list[dict[str, Any]] = []
    unknowns: list[dict[str, Any]] = []
    cross_pipeline_rows: list[dict[str, Any]] = []
    counters: Counter[str] = Counter()
    for item in items:
        calculated = publisher_region_fields(item)
        c_region = collector_region(item)
        p_region = str(item.get("publisher_region") or calculated.get("publisher_region") or "unknown")
        display = display_region_reason(item)
        display_region = display["region"]
        display_basis = display["basis"]
        country_code = confirmed_publisher_country_code(item)
        counters[f"collector_{c_region}"] += 1
        counters[f"publisher_{p_region}"] += 1
        counters[f"display_region_{display_region}"] += 1
        counters[f"display_region_basis_{display_basis}"] += 1
        row = {
            "id": item.get("id"),
            "title": item.get("title"),
            "media": item.get("media") or item.get("organization"),
            "domain": item.get("publisher_domain") or calculated.get("publisher_domain") or "",
            "source": item.get("source"),
            "collector_region": c_region,
            "publisher_region_candidate": p_region,
            "publisher_country_code": item.get("publisher_country_code") or "",
            "publisher_country_confidence": item.get("publisher_country_confidence") or "",
            "display_region": display_region,
            "display_region_basis": display_basis,
            "calculated_collection_pipeline": calculated.get("collection_pipeline"),
            "calculated_publisher_region": calculated.get("publisher_region"),
            "original_url": masked_url_for_report(item.get("original_url") or item.get("url")),
        }
        if p_region == "unknown":
            unknowns.append(row)
        if c_region == "rss_overseas_pipeline" and p_region == "domestic":
            counters["rss_overseas_pipeline_domestic_publisher_count"] += 1
            cross_pipeline_rows.append(row)
        elif c_region == "domestic_pipeline" and p_region == "overseas":
            counters["domestic_pipeline_overseas_publisher_count"] += 1
            cross_pipeline_rows.append(row)
        if country_code == "KR" and display_region == "overseas":
            counters["known_kr_country_displayed_overseas_count"] += 1
            mismatches.append({**row, "code": "known_kr_country_displayed_overseas"})
        if country_code and country_code != "KR" and display_region == "domestic":
            counters["known_non_kr_country_displayed_domestic_count"] += 1
            mismatches.append({**row, "code": "known_non_kr_country_displayed_domestic"})
        if display_region == "overseas" and p_region == "domestic":
            counters["domestic_publisher_in_overseas_result_count"] += 1
        if display_region == "domestic" and p_region == "overseas":
            counters["overseas_publisher_in_domestic_result_count"] += 1
        if display_region == "overseas" and country_code:
            expected_country_option = "unknown" if country_code == "KR" else country_code
            if expected_country_option == "unknown":
                counters["unknown_country_option_containing_known_country_count"] += 1
        if (
            item.get("collection_pipeline") != calculated.get("collection_pipeline")
            or item.get("publisher_region") != calculated.get("publisher_region")
            or item.get("publisher_domain", "") != calculated.get("publisher_domain", "")
        ):
            counters["stored_region_mismatch_count"] += 1
            mismatches.append(row)
    return {
        "counts": dict(counters),
        "unknown_count": len(unknowns),
        "mismatch_count": len(mismatches),
        "mismatch_samples": mismatches[:30],
        "cross_pipeline_region_samples": cross_pipeline_rows[:30],
        "unknown_samples": unknowns[:30],
    }


def top50_audit(sorted_items: list[dict[str, Any]]) -> dict[str, Any]:
    top = sorted_items[:50]
    level_counts = Counter(str(item.get("relevance_level") or "missing") for item in top)
    publisher_counts = Counter(publisher_region_candidate(item) for item in top)
    title_dates: Counter[tuple[str, str]] = Counter()
    unrelated_count = 0
    unnatural_count = 0
    for item in top:
        title_dates[overseas_news_content_key(item.get("title"), item.get("published_at"))] += 1
        level = item.get("relevance_level")
        title_summary = f"{item.get('title', '')} {item.get('summary', '')}".casefold()
        if level == "excluded" or any(hint in title_summary for hint in REFERENCE_OR_UNRELATED_HINTS):
            unrelated_count += 1
        try:
            score = int(item.get("relevance_score"))
        except (TypeError, ValueError):
            unnatural_count += 1
            continue
        if level not in ALLOWED_LEVELS or not 0 <= score <= 100:
            unnatural_count += 1
    adjacent_positions = [index for index, item in enumerate(sorted_items) if item.get("relevance_level") == "adjacent"]
    direct_positions = [index for index, item in enumerate(sorted_items) if item.get("relevance_level") == "direct"]
    adjacent_before_direct_count = 0
    if adjacent_positions and direct_positions and min(adjacent_positions) < max(direct_positions):
        adjacent_before_direct_count = 1
    duplicate_same_issue_count = sum(count - 1 for key, count in title_dates.items() if all(key) and count > 1)
    return {
        "level_counts": dict(level_counts),
        "publisher_region_counts": dict(publisher_counts),
        "actual_modular_unrelated_count": unrelated_count,
        "same_issue_duplicate_count": duplicate_same_issue_count,
        "unnatural_score_level_count": unnatural_count,
        "adjacent_before_direct_count": adjacent_before_direct_count,
        "top_items": [
            {
                "rank": index + 1,
                "id": item.get("id"),
                "title": item.get("title"),
                "media": item.get("media") or item.get("organization"),
                "source": item.get("source"),
                "publisher_region_candidate": publisher_region_candidate(item),
                "relevance_level": item.get("relevance_level"),
                "relevance_score": item.get("relevance_score"),
            }
            for index, item in enumerate(top)
        ],
    }


def audit_opinion(item: dict[str, Any]) -> str:
    c_region = collector_region(item)
    p_region = publisher_region_candidate(item)
    if c_region == "rss_overseas_pipeline" and p_region == "domestic":
        return "지역 오분류"
    if item.get("relevance_level") == "excluded":
        return "제외 검토"
    try:
        score = int(item.get("relevance_score"))
    except (TypeError, ValueError):
        return "과대평가 가능"
    if item.get("relevance_level") == "direct" and score < 40:
        return "과소평가 가능"
    if item.get("relevance_level") == "reference" and score >= 60:
        return "과대평가 가능"
    return "정상"


def sample_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {
        "domestic_pipeline_direct_top10": [
            item for item in items if collector_region(item) == "domestic_pipeline" and item.get("relevance_level") == "direct"
        ],
        "domestic_pipeline_adjacent_top10": [
            item for item in items if collector_region(item) == "domestic_pipeline" and item.get("relevance_level") == "adjacent"
        ],
        "rss_overseas_pipeline_direct_top10": [
            item for item in items if collector_region(item) == "rss_overseas_pipeline" and item.get("relevance_level") == "direct"
        ],
        "rss_overseas_pipeline_adjacent_top10": [
            item for item in items if collector_region(item) == "rss_overseas_pipeline" and item.get("relevance_level") == "adjacent"
        ],
        "rss_overseas_pipeline_domestic_publisher_top10": [
            item for item in items if collector_region(item) == "rss_overseas_pipeline" and publisher_region_candidate(item) == "domestic"
        ],
        "lowest_score_top10": sorted(items, key=lambda item: (int(item.get("relevance_score") or 0), clean_text(item.get("title")).casefold())),
    }
    rows: list[dict[str, Any]] = []
    for group, group_items in groups.items():
        if group != "lowest_score_top10":
            group_items = sorted(group_items, key=news_sort_key)
        for item in group_items[:10]:
            calculated = publisher_region_fields(item)
            rows.append(
                {
                    "sample_group": group,
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "media": item.get("media") or item.get("organization"),
                    "domain": item.get("publisher_domain") or calculated.get("publisher_domain") or "",
                    "source": item.get("source"),
                    "collector_region": collector_region(item),
                    "publisher_region_candidate": publisher_region_candidate(item),
                    "relevance_level": item.get("relevance_level"),
                    "relevance_score": item.get("relevance_score"),
                    "relevance_components": json.dumps(item.get("relevance_components") or {}, ensure_ascii=False, sort_keys=True),
                    "relevance_reasons": " | ".join(str(reason) for reason in (item.get("relevance_reasons") or [])),
                    "audit_opinion": audit_opinion(item),
                }
            )
    return rows


def compare_components(domestic_stats: dict[str, Any], overseas_stats: dict[str, Any]) -> dict[str, Any]:
    differences: dict[str, float] = {}
    for component in ("core", "business", "freshness", "completeness"):
        left = domestic_stats.get(component, {}).get("average")
        right = overseas_stats.get(component, {}).get("average")
        if left is not None and right is not None:
            differences[component] = round(abs(float(left) - float(right)), 2)
    largest = max(differences.items(), key=lambda pair: pair[1], default=(None, None))
    return {
        "average_absolute_differences": differences,
        "largest_difference_component": largest[0],
        "largest_difference": largest[1],
    }


def final_status(contract: dict[str, Any], region: dict[str, Any], top50: dict[str, Any]) -> str:
    counts = defaultdict(int, contract.get("counts", {}))
    fail_keys = (
        "score_version_mismatch_count",
        "relevance_level_missing_count",
        "relevance_level_invalid_count",
        "relevance_score_missing_count",
        "relevance_score_range_violation_count",
        "excluded_public_count",
        "id_missing_count",
        "id_duplicate_count",
        "url_duplicate_count",
        "title_published_at_duplicate_count",
    )
    if any(counts[key] for key in fail_keys):
        return "FAIL"
    if top50.get("adjacent_before_direct_count", 0) or top50.get("unnatural_score_level_count", 0):
        return "FAIL"
    region_counts = defaultdict(int, region.get("counts", {}))
    display_fail_keys = (
        "known_kr_country_displayed_overseas_count",
        "known_non_kr_country_displayed_domestic_count",
        "domestic_publisher_in_overseas_result_count",
        "unknown_country_option_containing_known_country_count",
    )
    if any(region_counts[key] for key in display_fail_keys):
        return "FAIL"
    if region.get("counts", {}).get("stored_region_mismatch_count", 0):
        return "PASS_WITH_REGION_FIX_REQUIRED"
    return "PASS"


def build_report(news_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    payload, items, load_errors = load_news_payload(news_path)
    domestic_pipeline = [item for item in items if collector_region(item) == "domestic_pipeline"]
    rss_pipeline = [item for item in items if collector_region(item) == "rss_overseas_pipeline"]
    contract = contract_audit(items)
    distributions = {
        "overall": score_distribution(items),
        "domestic_pipeline": score_distribution(domestic_pipeline),
        "rss_overseas_pipeline": score_distribution(rss_pipeline),
    }
    components = {
        "domestic_pipeline": component_stats(domestic_pipeline),
        "rss_overseas_pipeline": component_stats(rss_pipeline),
    }
    component_comparison = compare_components(components["domestic_pipeline"], components["rss_overseas_pipeline"])
    region = region_audit(items)
    sorted_items = sorted(items, key=news_sort_key)
    top50 = top50_audit(sorted_items)
    samples = sample_rows(items)
    status = final_status(contract, region, top50)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_path": str(news_path),
        "public_news_generated_at": payload.get("generated_at"),
        "public_news_last_updated_at": payload.get("last_updated_at"),
        "total_news_count": len(items),
        "domestic_pipeline_count": len(domestic_pipeline),
        "rss_overseas_pipeline_count": len(rss_pipeline),
        "load_errors": load_errors,
        "unified_v2_contract": contract,
        "score_distribution": distributions,
        "relevance_component_stats": components,
        "component_comparison": component_comparison,
        "region_audit": region,
        "relevance_sort_top50_audit": top50,
        "collection_warnings_observed": COLLECTION_WARNINGS,
        "final_status": "FAIL" if load_errors else status,
        "next_recommendations": recommendations(status, region, contract),
    }
    mismatch_rows = region.get("mismatch_samples", [])
    return report, samples, mismatch_rows


def recommendations(status: str, region: dict[str, Any], contract: dict[str, Any] | None = None) -> list[str]:
    recs: list[str] = []
    counts = defaultdict(int, (contract or {}).get("counts", {}))
    if counts["excluded_public_count"]:
        recs.append("Fix public export or collection policy so relevance_level=excluded items are not published.")
    if counts["title_published_at_duplicate_count"]:
        recs.append("Add whole-news title/date duplicate normalization or review duplicate carry-over in cumulative public news.")
    if counts["url_duplicate_count"]:
        recs.append("Normalize duplicate original_url values before final public news publication.")
    if status == "PASS_WITH_REGION_FIX_REQUIRED":
        recs.append("Split collector_region from publisher_region in frontend filtering before changing production data.")
        recs.append("Keep overseas RSS collector active, but display Korean publishers from RSS as domestic publisher candidates.")
    if region.get("counts", {}).get("rss_overseas_pipeline_domestic_publisher_count", 0):
        recs.append("RSS-sourced domestic publishers are expected to use publisher_region=domestic in UI filters.")
    if region.get("unknown_count", 0):
        recs.append("Add explicit publisher-domain mappings for high-volume unknown publishers after manual review.")
    recs.append("Keep unified-v2 scoring unchanged until region-display behavior is fixed in a separate hotfix.")
    return recs


def render_markdown(report: dict[str, Any]) -> str:
    contract_counts = defaultdict(int, report["unified_v2_contract"]["counts"])
    region_counts = defaultdict(int, report["region_audit"]["counts"])
    dist = report["score_distribution"]
    comp = report["component_comparison"]
    top50 = report["relevance_sort_top50_audit"]
    lines = [
        "# Unified News Live Audit",
        "",
        f"- Final status: {report['final_status']}",
        f"- Public news generated_at: {report.get('public_news_generated_at')}",
        f"- Total news count: {report['total_news_count']}",
        f"- Domestic pipeline count: {report['domestic_pipeline_count']}",
        f"- RSS overseas pipeline count: {report['rss_overseas_pipeline_count']}",
        "",
        "## Unified-v2 Contract",
        "",
        f"- Score version mismatch: {contract_counts['score_version_mismatch_count']}",
        f"- Relevance level missing: {contract_counts['relevance_level_missing_count']}",
        f"- Relevance level invalid: {contract_counts['relevance_level_invalid_count']}",
        f"- Relevance score missing: {contract_counts['relevance_score_missing_count']}",
        f"- Score range violation: {contract_counts['relevance_score_range_violation_count']}",
        f"- Components missing: {contract_counts['relevance_components_missing_count']}",
        f"- Reasons missing: {contract_counts['relevance_reasons_missing_count']}",
        f"- Excluded public count: {contract_counts['excluded_public_count']}",
        f"- ID missing: {contract_counts['id_missing_count']}",
        f"- ID duplicate: {contract_counts['id_duplicate_count']}",
        f"- URL duplicate: {contract_counts['url_duplicate_count']}",
        f"- Title/date duplicate: {contract_counts['title_published_at_duplicate_count']}",
        "",
        "## Score Distribution",
        "",
    ]
    for name in ("overall", "domestic_pipeline", "rss_overseas_pipeline"):
        value = dist[name]
        lines.extend(
            [
                f"### {name}",
                f"- Count: {value['count']}",
                f"- Min / P25 / Median / Average / P75 / Max: {value['min']} / {value['p25']} / {value['median']} / {value['average']} / {value['p75']} / {value['max']}",
                f"- Levels: {value['level_counts']}",
                f"- Score bins: {value['score_bins']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Component Comparison",
            "",
            f"- Largest component difference: {comp['largest_difference_component']} ({comp['largest_difference']})",
            f"- Average absolute differences: {comp['average_absolute_differences']}",
            "",
            "## Region Audit",
            "",
            f"- RSS overseas pipeline with domestic publisher candidate: {region_counts['rss_overseas_pipeline_domestic_publisher_count']}",
            f"- Domestic pipeline with overseas publisher candidate: {region_counts['domestic_pipeline_overseas_publisher_count']}",
            f"- Stored publisher-region mismatch count: {region_counts['stored_region_mismatch_count']}",
            f"- Unknown publisher region count: {report['region_audit']['unknown_count']}",
            f"- Display region domestic count: {region_counts['display_region_domestic']}",
            f"- Display region overseas count: {region_counts['display_region_overseas']}",
            f"- Display basis publisher country code: {region_counts['display_region_basis_publisher_country_code']}",
            f"- Known KR country displayed overseas: {region_counts['known_kr_country_displayed_overseas_count']}",
            f"- Known non-KR country displayed domestic: {region_counts['known_non_kr_country_displayed_domestic_count']}",
            f"- Domestic publisher in overseas result: {region_counts['domestic_publisher_in_overseas_result_count']}",
            f"- Unknown country option containing known country: {region_counts['unknown_country_option_containing_known_country_count']}",
            "",
            "## Relevance Sort Top 50",
            "",
            f"- Level counts: {top50['level_counts']}",
            f"- Publisher region counts: {top50['publisher_region_counts']}",
            f"- Adjacent before direct violations: {top50['adjacent_before_direct_count']}",
            f"- Unnatural score/level count: {top50['unnatural_score_level_count']}",
            f"- Same issue duplicate count: {top50['same_issue_duplicate_count']}",
            f"- Potential unrelated count: {top50['actual_modular_unrelated_count']}",
            "",
            "## Collection Warnings",
            "",
        ]
    )
    for warning in report["collection_warnings_observed"]:
        lines.append(f"- {warning['code']}: {warning['impact']} Next: {warning['suggested_priority']}")
    lines.extend(["", "## Recommendations", ""])
    for rec in report["next_recommendations"]:
        lines.append(f"- {rec}")
    lines.append("")
    return "\n".join(lines)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(report: dict[str, Any], samples: list[dict[str, Any]], mismatches: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "unified_news_live_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "unified_news_live_audit.md").write_text(render_markdown(report), encoding="utf-8")
    sample_fields = [
        "sample_group",
        "id",
        "title",
        "media",
        "domain",
        "source",
        "collector_region",
        "publisher_region_candidate",
        "relevance_level",
        "relevance_score",
        "relevance_components",
        "relevance_reasons",
        "audit_opinion",
    ]
    mismatch_fields = [
        "id",
        "title",
        "media",
        "domain",
        "source",
        "collector_region",
        "publisher_region_candidate",
        "publisher_country_code",
        "publisher_country_confidence",
        "display_region",
        "display_region_basis",
        "original_url",
    ]
    write_csv(output_dir / "news_score_samples.csv", samples, sample_fields)
    write_csv(output_dir / "news_region_mismatch_candidates.csv", mismatches, mismatch_fields)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit unified-v2 scoring and publisher-region consistency for all public news.")
    parser.add_argument("--input", type=Path, default=ROOT / "frontend/public/data/news.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/unified_news_live_audit")
    args = parser.parse_args()

    report, samples, mismatches = build_report(args.input)
    write_outputs(report, samples, mismatches, args.output_dir)
    contract_counts = defaultdict(int, report["unified_v2_contract"]["counts"])
    region_counts = defaultdict(int, report["region_audit"]["counts"])
    print(
        "unified_news_live_audit "
        f"status={report['final_status']} "
        f"total={report['total_news_count']} "
        f"domestic_pipeline={report['domestic_pipeline_count']} "
        f"rss_overseas_pipeline={report['rss_overseas_pipeline_count']} "
        f"score_version_mismatch={contract_counts['score_version_mismatch_count']} "
        f"score_range_violation={contract_counts['relevance_score_range_violation_count']} "
        f"stored_region_mismatch={region_counts['stored_region_mismatch_count']} "
        f"rss_domestic_publishers={region_counts['rss_overseas_pipeline_domestic_publisher_count']}"
    )
    return 1 if report["final_status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
