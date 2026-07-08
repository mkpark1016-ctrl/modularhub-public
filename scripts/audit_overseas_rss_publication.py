from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.keywords import GDELT_DOC_NEWS_EXCLUDE_CONTEXT  # noqa: E402
from src.overseas_news_rules import overseas_news_content_key  # noqa: E402

OVERSEAS_RSS_SOURCE = "해외 모듈러 RSS"
RECENT_DAYS = 14
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
}


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


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


def normalized_url(value: Any) -> str:
    text = str(value or "").strip()
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
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            "",
            query,
            "",
        )
    )


def split_keywords(value: Any) -> list[str]:
    if isinstance(value, list):
        parts = value
    else:
        parts = re.split(r"[,;|]", str(value or ""))
    return [str(part).strip() for part in parts if str(part).strip()]


def has_excluded_context(item: dict[str, Any]) -> str:
    haystack = normalize_text(f"{item.get('title', '')} {item.get('summary', '')}")
    for phrase in GDELT_DOC_NEWS_EXCLUDE_CONTEXT:
        if normalize_text(phrase) in haystack:
            return phrase
    return ""


def load_news_items(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [], [{"code": "json_parse_error", "message": str(exc), "path": str(path)}]
    except OSError as exc:
        return [], [{"code": "json_read_error", "message": str(exc), "path": str(path)}]

    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and isinstance(payload.get("items"), list):
        items = payload["items"]
    else:
        return [], [{"code": "json_structure_error", "message": "news payload must be an array or contain an items array"}]

    normalized_items: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if isinstance(item, dict):
            normalized_items.append(item)
        else:
            errors.append({"code": "item_structure_error", "index": index, "message": "news item must be an object"})
    return normalized_items, errors


def add_issue(bucket: list[dict[str, Any]], code: str, item: dict[str, Any], message: str, **extra: Any) -> None:
    bucket.append(
        {
            "code": code,
            "id": item.get("id"),
            "title": item.get("title"),
            "message": message,
            **extra,
        }
    )


def audit_news_items(items: list[dict[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    threshold = now - timedelta(days=RECENT_DAYS)
    overseas = [item for item in items if item.get("source") == OVERSEAS_RSS_SOURCE]

    validation_errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    invalid_ids: set[int | str] = set()
    url_seen: dict[str, dict[str, Any]] = {}
    title_date_seen: dict[str, dict[str, Any]] = {}
    google_news_rss_url_sample: list[dict[str, Any]] = []

    counters: Counter[str] = Counter()
    media_distribution: Counter[str] = Counter()
    keyword_distribution: Counter[str] = Counter()

    for item in overseas:
        item_key = item.get("id") or f"title:{item.get('title', '')}"
        item_errors_before = len(validation_errors)
        title = str(item.get("title") or "").strip()
        media = str(item.get("media") or item.get("source_name") or "").strip()
        published_at = item.get("published_at")
        parsed_date = parse_datetime(published_at)
        original = item.get("original_url")
        canonical = normalized_url(original)
        keywords = split_keywords(item.get("keywords"))
        relevance = item.get("relevance_score")

        if not title:
            counters["title_missing_count"] += 1
            add_issue(validation_errors, "title_missing", item, "title is required")

        if not canonical:
            counters["invalid_url_count"] += 1
            add_issue(validation_errors, "invalid_url", item, "original_url must be http or https", original_url=original)
        elif canonical in url_seen:
            counters["duplicate_url_count"] += 1
            add_issue(
                validation_errors,
                "duplicate_original_url",
                item,
                "duplicate original_url",
                duplicate_of=url_seen[canonical].get("id"),
                original_url=canonical,
            )
        else:
            url_seen[canonical] = item

        try:
            score = float(relevance)
        except (TypeError, ValueError):
            score = 0.0
        if score < 70:
            counters["low_relevance_count"] += 1
            add_issue(validation_errors, "low_relevance_score", item, "relevance_score must be at least 70", relevance_score=relevance)

        if not keywords:
            counters["keywords_missing_count"] += 1
            add_issue(validation_errors, "keywords_missing", item, "keywords must not be empty")
        else:
            keyword_distribution.update(keywords)

        excluded_phrase = has_excluded_context(item)
        if excluded_phrase:
            counters["excluded_context_count"] += 1
            add_issue(validation_errors, "excluded_context_public", item, "excluded context is present", excluded_context=excluded_phrase)

        if not media:
            counters["media_missing_count"] += 1
            add_issue(warnings, "media_missing", item, "media or source name is missing")
        else:
            media_distribution.update([media])

        if not published_at:
            counters["date_missing_count"] += 1
            add_issue(warnings, "published_at_missing", item, "published_at is missing")
        elif not parsed_date:
            counters["date_invalid_count"] += 1
            add_issue(warnings, "published_at_invalid", item, "published_at is not parseable", published_at=published_at)
        else:
            if parsed_date >= threshold:
                counters["recent_14_day_count"] += 1
            title_date_key = overseas_news_content_key(title, published_at)
            if all(title_date_key):
                if title_date_key in title_date_seen:
                    counters["duplicate_title_date_count"] += 1
                    add_issue(
                        validation_errors,
                        "duplicate_title_published_at",
                        item,
                        "duplicate normalized title and published_at",
                        duplicate_of=title_date_seen[title_date_key].get("id"),
                        published_at=published_at,
                    )
                else:
                    title_date_seen[title_date_key] = item

        if canonical and urlparse(canonical).hostname == "news.google.com":
            counters["google_news_rss_url_count"] += 1
            if len(google_news_rss_url_sample) < 5:
                google_news_rss_url_sample.append(
                    {
                        "id": item.get("id"),
                        "title": item.get("title"),
                        "original_url": canonical,
                    }
                )

        if len(validation_errors) > item_errors_before:
            invalid_ids.add(item_key)

    if not overseas:
        warnings.append({"code": "overseas_rss_empty", "message": "No overseas RSS news items are currently published"})
    if overseas and counters["recent_14_day_count"] < 5:
        warnings.append(
            {
                "code": "recent_14_day_low_count",
                "message": "Fewer than 5 overseas RSS items were published in the last 14 days",
                "recent_14_day_count": counters["recent_14_day_count"],
            }
        )

    invalid_count = len(invalid_ids)
    audit_status = "failed" if validation_errors else ("passed_with_warnings" if warnings else "passed")
    return {
        "generated_at": now.isoformat(),
        "total_news_count": len(items),
        "overseas_rss_count": len(overseas),
        "recent_14_day_count": counters["recent_14_day_count"],
        "valid_count": max(0, len(overseas) - invalid_count),
        "invalid_count": invalid_count,
        "warning_count": len(warnings),
        "duplicate_url_count": counters["duplicate_url_count"],
        "duplicate_title_date_count": counters["duplicate_title_date_count"],
        "invalid_url_count": counters["invalid_url_count"],
        "low_relevance_count": counters["low_relevance_count"],
        "excluded_context_count": counters["excluded_context_count"],
        "media_missing_count": counters["media_missing_count"],
        "date_missing_count": counters["date_missing_count"],
        "date_invalid_count": counters["date_invalid_count"],
        "keywords_missing_count": counters["keywords_missing_count"],
        "google_news_rss_url_count": counters["google_news_rss_url_count"],
        "google_news_rss_url_sample": google_news_rss_url_sample,
        "google_news_rss_url_policy": "allowed_intermediary_url",
        "media_distribution": dict(sorted(media_distribution.items())),
        "keyword_distribution": dict(sorted(keyword_distribution.items())),
        "validation_errors": validation_errors,
        "warnings": warnings,
        "audit_status": audit_status,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Overseas RSS Publication Audit",
        "",
        f"- Audit Status: {report['audit_status']}",
        f"- Total news count: {report['total_news_count']}",
        f"- Overseas RSS count: {report['overseas_rss_count']}",
        f"- Recent 14 day count: {report['recent_14_day_count']}",
        f"- Valid count: {report['valid_count']}",
        f"- Invalid count: {report['invalid_count']}",
        f"- Warning count: {report['warning_count']}",
        f"- Duplicate URL count: {report['duplicate_url_count']}",
        f"- Duplicate title/date count: {report['duplicate_title_date_count']}",
        f"- Excluded context count: {report['excluded_context_count']}",
        "",
        "## Information",
        "",
        f"- Google News RSS intermediary URL count: {report.get('google_news_rss_url_count', 0)}",
        f"- Google News RSS URL policy: {report.get('google_news_rss_url_policy', 'allowed_intermediary_url')}",
        "",
    ]
    samples = report.get("google_news_rss_url_sample") or []
    if samples:
        lines.append("### Google News RSS URL Samples")
        for sample in samples[:5]:
            lines.append(f"- {sample.get('id')}: {sample.get('title')} ({sample.get('original_url')})")
        lines.append("")
    if report["validation_errors"]:
        lines.append("## Validation Errors")
        for error in report["validation_errors"]:
            lines.append(f"- {error.get('code')}: {error.get('title') or error.get('message')}")
        lines.append("")
    lines.append("## Warnings")
    if report["warnings"]:
        for warning in report["warnings"]:
            lines.append(f"- {warning.get('code')}: {warning.get('title') or warning.get('message')}")
        lines.append("")
    else:
        lines.append("- None")
        lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "overseas_rss_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "overseas_rss_audit.md").write_text(render_markdown(report), encoding="utf-8")


def audit_file(input_path: Path, output_dir: Path) -> dict[str, Any]:
    items, load_errors = load_news_items(input_path)
    if load_errors:
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_news_count": 0,
            "overseas_rss_count": 0,
            "recent_14_day_count": 0,
            "valid_count": 0,
            "invalid_count": 0,
            "warning_count": 0,
            "duplicate_url_count": 0,
            "duplicate_title_date_count": 0,
            "invalid_url_count": 0,
            "low_relevance_count": 0,
            "excluded_context_count": 0,
            "media_missing_count": 0,
            "date_missing_count": 0,
            "date_invalid_count": 0,
            "keywords_missing_count": 0,
            "google_news_rss_url_count": 0,
            "google_news_rss_url_sample": [],
            "google_news_rss_url_policy": "allowed_intermediary_url",
            "media_distribution": {},
            "keyword_distribution": {},
            "validation_errors": load_errors,
            "warnings": [],
            "audit_status": "failed",
        }
    else:
        report = audit_news_items(items)
    write_outputs(report, output_dir)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit published overseas RSS news items in public news.json.")
    parser.add_argument("--input", type=Path, default=ROOT / "frontend/public/data/news.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/overseas_rss_audit")
    args = parser.parse_args()

    report = audit_file(args.input, args.output_dir)
    print(
        "overseas_rss_audit "
        f"status={report['audit_status']} "
        f"overseas={report['overseas_rss_count']} "
        f"google_news_rss_urls={report.get('google_news_rss_url_count', 0)} "
        f"errors={len(report['validation_errors'])} "
        f"warnings={len(report['warnings'])}"
    )
    return 1 if report["audit_status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
