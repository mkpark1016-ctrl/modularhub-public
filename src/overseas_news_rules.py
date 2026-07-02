from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

from src.keywords import (
    GDELT_DOC_NEWS_CONSTRUCTION_CONTEXT,
    GDELT_DOC_NEWS_EXCLUDE_CONTEXT,
    GDELT_DOC_NEWS_STRONG_PHRASES,
)


TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
}
WEAK_MODULAR_TERMS = ("modular", "prefab", "prefabricated", "offsite", "off-site")


def clean_overseas_news_text(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_overseas_news_text(value: Any) -> str:
    text = clean_overseas_news_text(value).lower()
    text = text.replace("off site", "offsite")
    return re.sub(r"\s+", " ", text).strip()


def normalize_title(value: Any) -> str:
    return re.sub(r"\s+", " ", clean_overseas_news_text(value).lower()).strip()


def matches_excluded_context(title: Any, summary: Any = "") -> bool:
    normalized = normalize_overseas_news_text(f"{title or ''} {summary or ''}")
    return any(phrase.lower() in normalized for phrase in GDELT_DOC_NEWS_EXCLUDE_CONTEXT)


def calculate_overseas_news_relevance(title: Any, summary: Any = "") -> tuple[float, list[str]]:
    title_text = normalize_overseas_news_text(title)
    summary_text = normalize_overseas_news_text(summary)
    combined = f"{title_text} {summary_text}".strip()
    if not combined or matches_excluded_context(title_text, summary_text):
        return 0.0, []

    title_strong = [phrase for phrase in GDELT_DOC_NEWS_STRONG_PHRASES if phrase.lower() in title_text]
    if title_strong:
        score = 90.0 + min(10.0, float((len(title_strong) - 1) * 5))
        return min(100.0, score), title_strong

    title_weak = [term for term in WEAK_MODULAR_TERMS if term in title_text]
    title_context = [term for term in GDELT_DOC_NEWS_CONSTRUCTION_CONTEXT if term.lower() in title_text]
    if title_weak and title_context:
        return 80.0, sorted(set(title_weak + title_context))

    summary_strong = [phrase for phrase in GDELT_DOC_NEWS_STRONG_PHRASES if phrase.lower() in summary_text]
    if summary_strong:
        return 70.0, summary_strong

    return 0.0, []


def canonicalize_url(value: Any) -> str:
    text = clean_overseas_news_text(value)
    if not text:
        return ""
    try:
        parts = urlsplit(text)
    except ValueError:
        return ""
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return ""
    host = parts.hostname.lower() if parts.hostname else ""
    if not host:
        return ""
    port = parts.port
    netloc = host
    if port and not ((parts.scheme.lower() == "http" and port == 80) or (parts.scheme.lower() == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = quote(unquote(parts.path or "/"), safe="/:@")
    query = [
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS
    ]
    query.sort(key=lambda item: (item[0].lower(), item[1]))
    return urlunsplit((parts.scheme.lower(), netloc, path.rstrip("/") or "/", urlencode(query), ""))
