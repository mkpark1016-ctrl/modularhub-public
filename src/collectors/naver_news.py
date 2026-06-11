from __future__ import annotations

import html
import re
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import requests

from src.collectors.base import BaseCollector
from src.config import (
    NAVER_CLIENT_ID,
    NAVER_CLIENT_SECRET,
    NAVER_NEWS_DISPLAY,
    NAVER_NEWS_ENDPOINT,
    NAVER_NEWS_LOOKBACK_DAYS,
    NAVER_NEWS_SORT,
)
from src.keywords import (
    D2B_DIRECT_KEYWORDS,
    NAVER_NEWS_COMPETITOR_KEYWORDS,
    NAVER_NEWS_EXCLUDE_KEYWORDS,
    NAVER_NEWS_KEYWORD_GROUPS,
    NAVER_NEWS_PUBLIC_KEYWORDS,
)


DEFAULT_NAVER_NEWS_ENDPOINT = "https://openapi.naver.com/v1/search/news.json"
MAX_NAVER_NEWS_DISPLAY = 50


class NaverNewsCollector(BaseCollector):
    def __init__(self) -> None:
        self.client_id = NAVER_CLIENT_ID
        self.client_secret = NAVER_CLIENT_SECRET
        self.endpoint = NAVER_NEWS_ENDPOINT or DEFAULT_NAVER_NEWS_ENDPOINT
        self.display = max(1, min(int(NAVER_NEWS_DISPLAY or 50), MAX_NAVER_NEWS_DISPLAY))
        self.sort = NAVER_NEWS_SORT or "date"
        self.lookback_days = int(NAVER_NEWS_LOOKBACK_DAYS or 14)

    def get_source_type(self) -> str:
        return "news"

    def get_source_name(self) -> str:
        return "네이버뉴스"

    def collect(self) -> list[dict]:
        if not self.client_id or not self.client_secret:
            raise RuntimeError(".env에 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET을 설정하세요.")

        collected: list[dict] = []
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()

        for category, queries in NAVER_NEWS_KEYWORD_GROUPS.items():
            for query in queries:
                for item in self._request(query).get("items", []):
                    raw_item = self._to_raw_item(category, query, item)
                    if not self._within_lookback(raw_item):
                        continue
                    if not self._is_relevant(raw_item):
                        continue

                    url = (raw_item.get("url") or "").strip().lower()
                    title_key = (raw_item.get("title") or "").strip().lower()
                    if url and url in seen_urls:
                        continue
                    if not url and title_key in seen_titles:
                        continue

                    if url:
                        seen_urls.add(url)
                    seen_titles.add(title_key)
                    collected.append(raw_item)

        return collected

    def _request(self, query: str) -> dict:
        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
        }
        params = {
            "query": query,
            "display": self.display,
            "start": 1,
            "sort": self.sort,
        }
        response = requests.get(self.endpoint, headers=headers, params=params, timeout=20)
        if response.status_code in (401, 403):
            raise RuntimeError("네이버 뉴스 API 인증 오류입니다. NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET을 확인하세요.")
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"네이버 뉴스 API JSON 파싱 실패: {response.text[:300]}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("네이버 뉴스 API 응답 형식이 올바르지 않습니다.")
        return payload

    def _to_raw_item(self, category: str, query: str, item: dict[str, Any]) -> dict:
        title = clean_html(item.get("title"))
        description = clean_html(item.get("description"))
        original_link = str(item.get("originallink") or "").strip()
        naver_link = str(item.get("link") or "").strip()
        url = original_link or naver_link
        pub_date = parse_naver_pub_date(item.get("pubDate"))
        publisher = infer_publisher(url)

        raw_item = {
            "source_type": self.get_source_type(),
            "source_name": self.get_source_name(),
            "category": category,
            "title": title,
            "organization": publisher,
            "posted_at": pub_date.isoformat() if pub_date else None,
            "due_at": None,
            "amount": None,
            "region": None,
            "url": url,
            "summary": description,
            "raw": item,
            "keyword_query": query,
            "original_link": original_link,
            "naver_link": naver_link,
            "publisher": publisher,
            "pub_date": pub_date.isoformat() if pub_date else None,
        }
        raw_item["keywords"] = matched_news_keywords(raw_item)
        raw_item["relevance_score"] = calculate_naver_news_relevance(raw_item)
        return raw_item

    def _within_lookback(self, raw_item: dict) -> bool:
        posted_at = parse_iso_date(raw_item.get("posted_at"))
        if posted_at is None:
            return True
        return posted_at >= date.today() - timedelta(days=self.lookback_days)

    def _is_relevant(self, raw_item: dict) -> bool:
        title = str(raw_item.get("title") or "")
        summary = str(raw_item.get("summary") or "")
        haystack = f"{title} {summary}".lower()
        if any(keyword.lower() in haystack for keyword in NAVER_NEWS_EXCLUDE_KEYWORDS):
            return False
        return calculate_naver_news_relevance(raw_item) > 0


def clean_html(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_naver_pub_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return parsedate_to_datetime(text).date()
    except (TypeError, ValueError):
        return parse_iso_date(text)


def parse_iso_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def infer_publisher(url: str) -> str | None:
    if not url:
        return None
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def matched_news_keywords(raw_item: dict) -> list[str]:
    haystack = f"{raw_item.get('title') or ''} {raw_item.get('summary') or ''}".lower()
    matched: list[str] = []
    for queries in NAVER_NEWS_KEYWORD_GROUPS.values():
        for keyword in queries:
            if keyword.lower() in haystack and keyword not in matched:
                matched.append(keyword)
    query = str(raw_item.get("keyword_query") or "").strip()
    if query and query not in matched:
        matched.append(query)
    return matched


def calculate_naver_news_relevance(raw_item: dict) -> float:
    title = str(raw_item.get("title") or "")
    summary = str(raw_item.get("summary") or "")
    haystack = f"{title} {summary}".lower()
    if any(keyword.lower() in haystack for keyword in NAVER_NEWS_EXCLUDE_KEYWORDS):
        return 0.0

    score = 0
    if any(keyword.lower() in title.lower() for keyword in D2B_DIRECT_KEYWORDS):
        score += 10
    if any(keyword.lower() in title.lower() for keyword in NAVER_NEWS_PUBLIC_KEYWORDS):
        score += 6
    competitor_names = [keyword.replace(" 모듈러", "") for keyword in NAVER_NEWS_COMPETITOR_KEYWORDS]
    if any(name.lower() in title.lower() for name in competitor_names):
        score += 5
    if any(keyword.lower() in summary.lower() for keyword in D2B_DIRECT_KEYWORDS):
        score += 3

    posted_at = parse_iso_date(raw_item.get("posted_at") or raw_item.get("pub_date"))
    if posted_at:
        age_days = (date.today() - posted_at).days
        if age_days <= 7:
            score += 3
        elif age_days <= 30:
            score += 1

    if not matched_news_keywords(raw_item):
        return 0.0
    return float(min(score, 100))
