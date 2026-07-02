from __future__ import annotations

import hashlib
import html
import re
from datetime import date, datetime
from typing import Any, Callable
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

import requests

from src.collectors.base import BaseCollector
from src.config import (
    GDELT_DOC_NEWS_ENDPOINT,
    GDELT_DOC_NEWS_LANGUAGE,
    GDELT_DOC_NEWS_MAX_RECORDS,
    GDELT_DOC_NEWS_MIN_RELEVANCE_SCORE,
    GDELT_DOC_NEWS_TIMESPAN,
    GDELT_DOC_NEWS_TIMEOUT_SECONDS,
)
from src.keywords import (
    GDELT_DOC_NEWS_CONSTRUCTION_CONTEXT,
    GDELT_DOC_NEWS_EXCLUDE_CONTEXT,
    GDELT_DOC_NEWS_STRONG_PHRASES,
)


SOURCE_NAME = "GDELT 해외뉴스"
SOURCE_PORTAL_NAME = "GDELT DOC"
TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
}
WEAK_TERMS = ("modular", "prefab", "prefabricated", "offsite", "off-site")
RAW_ARTICLE_KEYS = {
    "url",
    "url_mobile",
    "title",
    "seendate",
    "domain",
    "language",
    "sourcecountry",
    "socialimage",
    "snippet",
    "description",
}


class GdeltDocNewsError(RuntimeError):
    def __init__(self, error_code: str, message: str, *, status_code: int | None = None, retry_after: str = "unknown"):
        self.error_code = error_code
        self.status_code = status_code
        self.retry_after = retry_after or "unknown"
        super().__init__(message)


class GdeltDocNewsCollector(BaseCollector):
    def __init__(
        self,
        *,
        endpoint: str | None = None,
        timespan: str | None = None,
        max_records: int | None = None,
        timeout_seconds: float | None = None,
        min_relevance_score: float | None = None,
        language: str | None = None,
        requests_get: Callable[..., Any] | None = None,
    ) -> None:
        self.endpoint = endpoint or GDELT_DOC_NEWS_ENDPOINT
        self.timespan = timespan or GDELT_DOC_NEWS_TIMESPAN
        self.max_records = max(1, min(int(max_records or GDELT_DOC_NEWS_MAX_RECORDS), 250))
        self.timeout_seconds = float(timeout_seconds or GDELT_DOC_NEWS_TIMEOUT_SECONDS)
        self.min_relevance_score = float(min_relevance_score or GDELT_DOC_NEWS_MIN_RELEVANCE_SCORE)
        self.language = language if language is not None else GDELT_DOC_NEWS_LANGUAGE
        self._requests_get = requests_get or requests.get
        self.request_count = 0
        self.stats: dict[str, int] = {
            "request_count": 0,
            "article_count": 0,
            "language_excluded_count": 0,
            "relevance_excluded_count": 0,
            "duplicate_excluded_count": 0,
            "returned_count": 0,
        }

    def get_source_type(self) -> str:
        return "news"

    def get_source_name(self) -> str:
        return SOURCE_NAME

    def collect(self) -> list[dict]:
        payload = self._request()
        articles = payload.get("articles")
        if articles is None:
            raise RuntimeError("GDELT DOC API response missing articles array")
        if not isinstance(articles, list):
            raise RuntimeError("GDELT DOC API articles field is not an array")

        self.stats["article_count"] = len(articles)
        collected: list[dict] = []
        seen_urls: set[str] = set()
        seen_title_date_domain: set[tuple[str, str, str]] = set()

        for article in articles:
            if not isinstance(article, dict):
                self.stats["relevance_excluded_count"] += 1
                continue
            if not self._language_allowed(article.get("language")):
                self.stats["language_excluded_count"] += 1
                continue

            raw_item = self._to_raw_item(article)
            if raw_item is None:
                self.stats["relevance_excluded_count"] += 1
                continue

            url_key = str(raw_item.get("url") or "").lower()
            dedup_key = (
                normalize_title(raw_item.get("title")),
                str(raw_item.get("posted_at") or ""),
                str(raw_item.get("organization") or "").lower(),
            )
            if url_key and url_key in seen_urls:
                self.stats["duplicate_excluded_count"] += 1
                continue
            if all(dedup_key) and dedup_key in seen_title_date_domain:
                self.stats["duplicate_excluded_count"] += 1
                continue

            if url_key:
                seen_urls.add(url_key)
            if all(dedup_key):
                seen_title_date_domain.add(dedup_key)
            collected.append(raw_item)

        self.stats["returned_count"] = len(collected)
        return collected

    def _request(self) -> dict[str, Any]:
        params = {
            "query": build_gdelt_doc_query(),
            "mode": "artlist",
            "format": "json",
            "sort": "datedesc",
            "timespan": self.timespan,
            "maxrecords": self.max_records,
        }
        headers = {"User-Agent": "ModularHubGdeltDocNewsCollector/1.0"}
        self.request_count += 1
        self.stats["request_count"] = self.request_count
        try:
            response = self._requests_get(
                self.endpoint,
                params=params,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except requests.Timeout as exc:
            raise RuntimeError("GDELT DOC API timeout") from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"GDELT DOC API request failed: {safe_error(str(exc))}") from exc

        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code == 429:
            retry_after = safe_retry_after(getattr(response, "headers", {}).get("Retry-After"))
            raise GdeltDocNewsError(
                "gdelt_doc_rate_limited",
                f"gdelt_doc_rate_limited: HTTP 429 Retry-After={retry_after}",
                status_code=429,
                retry_after=retry_after,
            )
        if status_code in {401, 403} or status_code >= 500 or status_code >= 400:
            raise GdeltDocNewsError(
                "gdelt_doc_http_error",
                f"gdelt_doc_http_error: HTTP {status_code}",
                status_code=status_code,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            preview = safe_error(str(getattr(response, "text", ""))[:300])
            raise RuntimeError(f"GDELT DOC API JSON parse failed: {preview}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("GDELT DOC API response root is not an object")
        return payload

    def _language_allowed(self, value: Any) -> bool:
        expected = str(self.language or "").strip().lower()
        if not expected:
            return True
        actual = str(value or "").strip().lower()
        return not actual or actual == expected

    def _to_raw_item(self, article: dict[str, Any]) -> dict | None:
        title = clean_text(article.get("title"))
        if not title:
            return None
        url = canonicalize_url(article.get("url") or article.get("url_mobile"))
        if not url:
            return None

        score, matched = calculate_gdelt_doc_relevance(title)
        if score < self.min_relevance_score:
            return None

        domain = clean_domain(article.get("domain") or urlsplit(url).netloc)
        posted_at = parse_gdelt_date(article.get("seendate"))
        summary = build_summary(article, matched)
        source_record_id = hashlib.sha256(url.encode("utf-8")).hexdigest()
        raw_metadata = {key: article.get(key) for key in RAW_ARTICLE_KEYS if key in article}

        return {
            "source_type": self.get_source_type(),
            "source_name": self.get_source_name(),
            "category": "overseas modular",
            "title": title,
            "organization": domain,
            "posted_at": posted_at.isoformat() if posted_at else None,
            "due_at": None,
            "amount": None,
            "region": clean_text(article.get("sourcecountry")) or None,
            "url": url,
            "original_url": url,
            "summary": summary,
            "keywords": matched,
            "relevance_score": score,
            "raw": raw_metadata,
            "source_record_id": source_record_id,
            "source_portal_name": SOURCE_PORTAL_NAME,
            "link_type": "direct",
            "link_status": "unchecked",
            "data_quality": "real",
            "gdelt_language": clean_text(article.get("language")) or None,
            "gdelt_url_mobile": canonicalize_url(article.get("url_mobile")) or None,
        }


def build_gdelt_doc_query() -> str:
    return "(" + " OR ".join(f'"{phrase}"' for phrase in GDELT_DOC_NEWS_STRONG_PHRASES) + ")"


def calculate_gdelt_doc_relevance(title: Any) -> tuple[float, list[str]]:
    text = clean_text(title)
    normalized = normalize_for_match(text)
    if not normalized:
        return 0.0, []
    if any(phrase.lower() in normalized for phrase in GDELT_DOC_NEWS_EXCLUDE_CONTEXT):
        return 0.0, []

    strong_matches = [phrase for phrase in GDELT_DOC_NEWS_STRONG_PHRASES if phrase.lower() in normalized]
    if strong_matches:
        score = 90.0 + min(10.0, float((len(strong_matches) - 1) * 5))
        return min(100.0, score), strong_matches

    weak_matches = [term for term in WEAK_TERMS if term in normalized]
    context_matches = [term for term in GDELT_DOC_NEWS_CONSTRUCTION_CONTEXT if term.lower() in normalized]
    if weak_matches and context_matches:
        return 80.0, sorted(set(weak_matches + context_matches))
    return 0.0, []


def canonicalize_url(value: Any) -> str:
    text = clean_text(value)
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
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS
    ]
    query.sort(key=lambda item: (item[0].lower(), item[1]))
    normalized = urlunsplit((parts.scheme.lower(), netloc, path.rstrip("/") or "/", urlencode(query), ""))
    return normalized


def parse_gdelt_date(value: Any) -> date | None:
    text = clean_text(value)
    if not text:
        return None
    if text.isdigit():
        fmt_by_length = {8: "%Y%m%d", 12: "%Y%m%d%H%M", 14: "%Y%m%d%H%M%S"}
        fmt = fmt_by_length.get(len(text))
        if not fmt:
            return None
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def build_summary(article: dict[str, Any], matched: list[str]) -> str:
    snippet = clean_text(article.get("snippet") or article.get("description"))
    if snippet:
        return snippet[:500]
    parts = [
        f"domain={clean_domain(article.get('domain')) or '-'}",
        f"country={clean_text(article.get('sourcecountry')) or '-'}",
        f"matched={', '.join(matched) if matched else '-'}",
    ]
    return "; ".join(parts)


def clean_domain(value: Any) -> str:
    text = clean_text(value).lower()
    if text.startswith("www."):
        text = text[4:]
    return text


def normalize_title(value: Any) -> str:
    return re.sub(r"\s+", " ", clean_text(value).lower()).strip()


def normalize_for_match(value: Any) -> str:
    text = clean_text(value).lower()
    text = text.replace("off site", "offsite")
    return re.sub(r"\s+", " ", text)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def safe_error(value: str) -> str:
    text = re.sub(r"(?i)(authorization|cookie|token|password|secret|api[_-]?key)=([^&\s]+)", r"\1=[REDACTED]", value)
    return text[:300]


def safe_retry_after(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return "unknown"
    return safe_error(text)[:80]
