from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable

import requests

from src.collectors.base import BaseCollector
from src.config import (
    OVERSEAS_RSS_NEWS_FEEDS,
    OVERSEAS_RSS_NEWS_LOOKBACK_DAYS,
    OVERSEAS_RSS_NEWS_MAX_ITEMS_PER_FEED,
    OVERSEAS_RSS_NEWS_MIN_RELEVANCE_SCORE,
    OVERSEAS_RSS_NEWS_TIMEOUT_SECONDS,
)
from src.overseas_news_rules import (
    calculate_overseas_news_relevance,
    canonicalize_url,
    clean_overseas_news_text,
    normalize_title,
)

try:  # feedparser is preferred when installed; stdlib XML parsing is the offline fallback.
    import feedparser  # type: ignore
except Exception:  # pragma: no cover - depends on optional runtime package
    feedparser = None


SOURCE_NAME = "해외 모듈러 RSS"
SOURCE_PORTAL_NAME = "RSS"


@dataclass(frozen=True)
class FeedConfig:
    name: str
    url: str


class OverseasRssNewsCollector(BaseCollector):
    def __init__(
        self,
        *,
        feeds: list[dict[str, str]] | list[FeedConfig] | None = None,
        timeout_seconds: float | None = None,
        lookback_days: int | None = None,
        max_items_per_feed: int | None = None,
        min_relevance_score: float | None = None,
        requests_get: Callable[..., Any] | None = None,
        today: date | None = None,
    ) -> None:
        self.feeds = normalize_feed_configs(feeds if feeds is not None else OVERSEAS_RSS_NEWS_FEEDS)
        self.timeout_seconds = float(timeout_seconds or OVERSEAS_RSS_NEWS_TIMEOUT_SECONDS)
        self.lookback_days = int(lookback_days or OVERSEAS_RSS_NEWS_LOOKBACK_DAYS)
        self.max_items_per_feed = max(1, int(max_items_per_feed or OVERSEAS_RSS_NEWS_MAX_ITEMS_PER_FEED))
        self.min_relevance_score = float(min_relevance_score or OVERSEAS_RSS_NEWS_MIN_RELEVANCE_SCORE)
        self._requests_get = requests_get or requests.get
        self.today = today or date.today()
        self.request_count = 0
        self.stats: dict[str, Any] = {
            "feed_count": len(self.feeds),
            "successful_feed_count": 0,
            "failed_feed_count": 0,
            "fetched_item_count": 0,
            "relevance_excluded_count": 0,
            "date_excluded_count": 0,
            "duplicate_excluded_count": 0,
            "returned_count": 0,
            "feed_errors": [],
        }

    def get_source_type(self) -> str:
        return "news"

    def get_source_name(self) -> str:
        return SOURCE_NAME

    def collect(self) -> list[dict]:
        collected: list[dict] = []
        seen_urls: set[str] = set()
        seen_title_date_org: set[tuple[str, str, str]] = set()

        for feed in self.feeds:
            try:
                entries = self._fetch_feed(feed)
                self.stats["successful_feed_count"] += 1
            except Exception as exc:
                self.stats["failed_feed_count"] += 1
                self.stats["feed_errors"].append({"feed": feed.name, "error": safe_error(str(exc))})
                continue

            self.stats["fetched_item_count"] += len(entries)
            for entry in entries[: self.max_items_per_feed]:
                raw_item = self._entry_to_raw_item(feed, entry)
                if raw_item is None:
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
                if all(dedup_key) and dedup_key in seen_title_date_org:
                    self.stats["duplicate_excluded_count"] += 1
                    continue

                if url_key:
                    seen_urls.add(url_key)
                if all(dedup_key):
                    seen_title_date_org.add(dedup_key)
                collected.append(raw_item)

        if self.feeds and self.stats["successful_feed_count"] == 0:
            raise RuntimeError(f"all RSS feeds failed: {self.stats['feed_errors']}")

        self.stats["returned_count"] = len(collected)
        return collected

    def _fetch_feed(self, feed: FeedConfig) -> list[dict[str, Any]]:
        headers = {
            "User-Agent": "ModularHubOverseasRssNewsCollector/1.0",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        }
        self.request_count += 1
        try:
            response = self._requests_get(feed.url, headers=headers, timeout=self.timeout_seconds)
        except requests.Timeout as exc:
            raise RuntimeError("feed_timeout") from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"feed_request_failed: {safe_error(str(exc))}") from exc

        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code != 200:
            raise RuntimeError(f"feed_http_{status_code}")

        body = bytes(getattr(response, "content", b"") or b"")
        text_preview = body[:200].decode("utf-8", errors="ignore").lstrip().lower()
        content_type = str(getattr(response, "headers", {}).get("Content-Type", "")).lower()
        if "html" in content_type or text_preview.startswith(("<!doctype html", "<html")):
            raise RuntimeError("feed_html_response")
        if not body.strip():
            return []

        return parse_feed_entries(body, source_url=feed.url)

    def _entry_to_raw_item(self, feed: FeedConfig, entry: dict[str, Any]) -> dict | None:
        title = clean_overseas_news_text(entry.get("title"))
        url = canonicalize_url(entry.get("link"))
        if not title or not url:
            self.stats["relevance_excluded_count"] += 1
            return None

        summary = clean_overseas_news_text(entry.get("summary") or entry.get("description"))
        score, matched = calculate_overseas_news_relevance(title, summary)
        if score < self.min_relevance_score:
            self.stats["relevance_excluded_count"] += 1
            return None

        published = parse_feed_date(entry.get("published") or entry.get("updated"))
        if published and published < self.today - timedelta(days=self.lookback_days):
            self.stats["date_excluded_count"] += 1
            return None
        if not published and score < 90:
            self.stats["date_excluded_count"] += 1
            return None

        publisher = clean_overseas_news_text(entry.get("publisher"))
        entry_source = clean_overseas_news_text(entry.get("source"))
        if entry_source.startswith(("http://", "https://")):
            entry_source = ""
        organization = publisher or entry_source or feed.name
        source_record_id = hashlib.sha256(f"{feed.name}|{url}".encode("utf-8")).hexdigest()
        raw = {
            "feed_name": feed.name,
            "feed_url": feed.url,
            "title": title,
            "link": url,
            "published": clean_overseas_news_text(entry.get("published")),
            "updated": clean_overseas_news_text(entry.get("updated")),
            "summary": summary[:500],
            "publisher": organization,
            "author": clean_overseas_news_text(entry.get("author")),
            "image": clean_overseas_news_text(entry.get("image")),
        }

        return {
            "source_type": self.get_source_type(),
            "source_name": self.get_source_name(),
            "category": "overseas modular",
            "title": title,
            "organization": organization,
            "posted_at": published.isoformat() if published else None,
            "due_at": None,
            "amount": None,
            "region": None,
            "url": url,
            "original_url": url,
            "summary": summary or f"feed={feed.name}; matched={', '.join(matched) if matched else '-'}",
            "keywords": matched,
            "relevance_score": score,
            "source_record_id": source_record_id,
            "source_portal_name": feed.name or SOURCE_PORTAL_NAME,
            "link_type": "direct",
            "link_status": "unchecked",
            "data_quality": "real",
            "raw": raw,
        }


def normalize_feed_configs(feeds: list[dict[str, str]] | list[FeedConfig]) -> list[FeedConfig]:
    normalized: list[FeedConfig] = []
    for index, feed in enumerate(feeds, start=1):
        if isinstance(feed, FeedConfig):
            name, url = feed.name, feed.url
        else:
            name = str(feed.get("name") or f"feed-{index}").strip()
            url = str(feed.get("url") or "").strip()
        if name and url:
            normalized.append(FeedConfig(name=name, url=url))
    return normalized


def parse_feed_entries(body: bytes, *, source_url: str = "") -> list[dict[str, Any]]:
    if feedparser is not None:
        parsed = feedparser.parse(body)
        parsed_entries = getattr(parsed, "entries", []) or []
        if getattr(parsed, "bozo", False) and not parsed_entries:
            raise RuntimeError("feed_parse_error")
        entries: list[dict[str, Any]] = []
        for entry in parsed_entries:
            link = entry.get("link") or ""
            image = ""
            thumbnails = entry.get("media_thumbnail") or []
            if thumbnails:
                image = thumbnails[0].get("url", "")
            entries.append(
                {
                    "title": entry.get("title", ""),
                    "link": link,
                    "published": entry.get("published", ""),
                    "updated": entry.get("updated", ""),
                    "summary": entry.get("summary", ""),
                    "description": entry.get("description", ""),
                    "author": entry.get("author", ""),
                    "publisher": (entry.get("source") or {}).get("title", "") if isinstance(entry.get("source"), dict) else "",
                    "source": source_url,
                    "image": image,
                }
            )
        return entries
    return parse_feed_entries_stdlib(body, source_url=source_url)


def parse_feed_entries_stdlib(body: bytes, *, source_url: str = "") -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise RuntimeError("feed_parse_error") from exc

    tag = strip_namespace(root.tag).lower()
    if tag == "rss":
        items = root.findall("./channel/item")
        return [
            {
                "title": find_text(item, "title"),
                "link": find_text(item, "link"),
                "published": find_text(item, "pubDate"),
                "updated": find_text(item, "updated"),
                "summary": find_text(item, "description"),
                "description": find_text(item, "description"),
                "author": find_text(item, "author"),
                "publisher": find_text(item, "source"),
                "source": source_url,
                "image": "",
            }
            for item in items
        ]
    if tag == "feed":
        entries = root.findall("{http://www.w3.org/2005/Atom}entry") or root.findall("entry")
        return [
            {
                "title": find_text(entry, "title"),
                "link": atom_link(entry),
                "published": find_text(entry, "published"),
                "updated": find_text(entry, "updated"),
                "summary": find_text(entry, "summary") or find_text(entry, "content"),
                "description": find_text(entry, "summary") or find_text(entry, "content"),
                "author": find_text(entry, "author/name") or find_text(entry, "name"),
                "publisher": find_text(entry, "source/title"),
                "source": source_url,
                "image": "",
            }
            for entry in entries
        ]
    raise RuntimeError("feed_unknown_root")


def find_text(node: ET.Element, path: str) -> str:
    direct = node.find(path)
    if direct is not None and direct.text:
        return clean_overseas_news_text(direct.text)
    namespaced_path = "/".join(f"{{http://www.w3.org/2005/Atom}}{part}" for part in path.split("/"))
    nested = node.find(namespaced_path)
    if nested is not None and nested.text:
        return clean_overseas_news_text(nested.text)
    return ""


def atom_link(entry: ET.Element) -> str:
    links = list(entry.findall("{http://www.w3.org/2005/Atom}link")) + list(entry.findall("link"))
    for link in links:
        rel = link.attrib.get("rel", "alternate")
        href = link.attrib.get("href", "")
        if href and rel in {"alternate", ""}:
            return href
    return links[0].attrib.get("href", "") if links else ""


def strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def parse_feed_date(value: Any) -> date | None:
    text = clean_overseas_news_text(value)
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.date()
    except (TypeError, ValueError, IndexError, OverflowError):
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def safe_error(value: str) -> str:
    text = re.sub(r"(?i)(authorization|cookie|token|password|secret|api[_-]?key)=([^&\s]+)", r"\1=[REDACTED]", value)
    return text[:300]
