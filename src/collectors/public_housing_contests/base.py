from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests

from src.public_housing_contest_classifier import (
    classify_modular_relevance,
    classify_notice_stage,
    clean_text,
    normalize_title,
    validate_exact_detail_url,
)


USER_AGENT = "ModularHubProbe/1.0 (+https://github.com/mkpark1016-ctrl/modularhub-public)"
ATTACHMENT_EXTENSIONS = (".pdf", ".hwp", ".hwpx", ".zip")
ERROR_HINTS = ("captcha", "access denied", "forbidden", "로그인", "접근", "차단")


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int | None
    content_type: str
    encoding: str
    text: str
    error: str = ""


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = {name.lower(): value or "" for name, value in attrs}
        href = attr_map.get("href", "")
        self._current = {"href": href, "title": attr_map.get("title", "")}
        self._parts = []

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._current is not None:
            text = clean_text(" ".join(self._parts))
            self.links.append({**self._current, "text": text})
            self._current = None
            self._parts = []


def load_sources(path: str | Path = "config/public_housing_contest_sources.json") -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [source for source in payload.get("sources", []) if source.get("enabled", True)]


def fetch_url(
    session: requests.Session,
    url: str,
    *,
    interval_seconds: float = 1.0,
    timeout: int = 20,
    retries: int = 1,
) -> FetchResult:
    last_error = ""
    for attempt in range(max(retries, 0) + 1):
        time.sleep(max(interval_seconds, 1.0) * (1.5**attempt))
        try:
            response = session.get(url, timeout=timeout, allow_redirects=True)
            response.encoding = response.encoding or response.apparent_encoding
            return FetchResult(
                url=url,
                final_url=response.url,
                status_code=response.status_code,
                content_type=response.headers.get("content-type", ""),
                encoding=response.encoding or "",
                text=response.text,
            )
        except requests.RequestException as exc:
            last_error = str(exc)
    return FetchResult(url=url, final_url=url, status_code=None, content_type="", encoding="", text="", error=last_error)


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.6",
        }
    )
    return session


def extract_links(html: str, base_url: str) -> list[dict[str, str]]:
    parser = LinkParser()
    parser.feed(html or "")
    links = []
    for link in parser.links:
        href = clean_text(link.get("href"))
        text = clean_text(link.get("text") or link.get("title"))
        if not href or href.startswith("#") or href.lower().startswith("javascript:void"):
            continue
        links.append({"text": text, "href": urljoin(base_url, href)})
    return links


def extract_attachments(html: str, base_url: str) -> list[dict[str, str]]:
    attachments = []
    for link in extract_links(html, base_url):
        href_lower = link["href"].split("?", 1)[0].lower()
        text_lower = link["text"].lower()
        if href_lower.endswith(ATTACHMENT_EXTENSIONS) or any(ext[1:] in text_lower for ext in ATTACHMENT_EXTENSIONS):
            attachments.append({"file_name": link["text"] or Path(urlparse(link["href"]).path).name, "url": link["href"]})
    return attachments


def extract_dates(text: str) -> list[str]:
    patterns = [
        r"20\d{2}[./-]\d{1,2}[./-]\d{1,2}",
        r"20\d{2}\.\s*\d{1,2}\.\s*\d{1,2}",
        r"20\d{2}년\s*\d{1,2}월\s*\d{1,2}일",
    ]
    found: list[str] = []
    for pattern in patterns:
        found.extend(clean_text(match) for match in re.findall(pattern, text))
    return list(dict.fromkeys(found))


def is_title_candidate(text: str) -> bool:
    text = clean_text(text)
    if len(text) < 8:
        return False
    blocked = ("로그인", "회원가입", "사이트맵", "이전", "다음", "목록", "검색", "첨부")
    return not any(token == text or token in text[:5] for token in blocked)


def is_notice_like_link(title: str, href: str) -> bool:
    lowered_href = href.lower()
    if any(token.lower() in lowered_href for token in ["list_no=", "articleno=", "msg_seq=", "bbsmsgdetail", "mode=view"]):
        return True
    return any(token in title for token in ["공모", "공고", "민간참여", "사업자", "주택건설"])


def extract_list_items(html: str, base_url: str, *, limit: int = 80) -> list[dict[str, Any]]:
    items = []
    for link in extract_links(html, base_url):
        title = clean_text(link["text"])
        if not is_title_candidate(title):
            continue
        href = link["href"]
        if not is_notice_like_link(title, href):
            continue
        idx = html.find(link.get("href", ""))
        nearby = html[max(0, idx - 600) : idx + 900] if idx >= 0 else html[:1200]
        dates = extract_dates(nearby)
        items.append({"title": title, "href": href, "posted_at_candidates": dates})
        if len(items) >= limit:
            break
    return items


def detect_pagination(html: str) -> dict[str, Any]:
    lowered = html.lower()
    return {
        "detected": any(token in lowered for token in ["npage", "article.offset", "pageindex", "page=", "paging", "pagination"]),
        "mode_hint": next(
            (token for token in ["nPage", "article.offset", "pageIndex", "page", "paging"] if token.lower() in lowered),
            "",
        ),
    }


def detect_search(html: str, url: str) -> dict[str, Any]:
    lowered = html.lower()
    query_keys = set(parse_qs(urlparse(url).query).keys())
    supported = any(token in lowered for token in ["keyword", "search", "srch", "검색"]) or bool(
        query_keys & {"keyword", "searchKeyword", "searchWrd", "srchWord"}
    )
    return {"supported": supported, "query_keys": sorted(query_keys)}


def detect_rss(html: str) -> bool:
    lowered = html.lower()
    return "application/rss+xml" in lowered or "rss" in lowered


def extract_record_id_from_url(url: str, keys: tuple[str, ...]) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in keys:
        if query.get(key):
            return query[key][0]
    for key in keys:
        match = re.search(rf"{re.escape(key)}[=/](\d+)", url)
        if match:
            return match.group(1)
    return ""


def format_candidate(pattern: str, source_record_id: str) -> str:
    return pattern.replace("{source_record_id}", source_record_id)


def classify_failure(fetch: FetchResult) -> str:
    if fetch.error:
        return "request_failed"
    if fetch.status_code in {401, 403}:
        return "access_restricted"
    if fetch.status_code == 404:
        return "not_found"
    if fetch.status_code and fetch.status_code >= 500:
        return "server_error"
    lowered = fetch.text[:5000].lower()
    if any(hint in lowered for hint in ERROR_HINTS):
        return "playwright_required"
    return ""


def title_similarity_ok(expected_parts: list[str], title: str, body: str) -> bool:
    haystack = f"{title} {body}"
    compact = re.sub(r"\s+", "", haystack)
    for part in expected_parts:
        if re.sub(r"\s+", "", part) in compact:
            return True
    return False


def probe_known_records(source: dict[str, Any], session: requests.Session) -> dict[str, Any]:
    known = source.get("known_record") or {}
    ids = known.get("source_record_ids") or []
    title_contains = known.get("title_contains") or []
    candidates = source.get("detail_url_candidates") or []
    allowed = source.get("allowed_domains") or []
    interval = float(source.get("request_interval_seconds") or 1.0)
    attempts = []
    success_count = 0
    for source_record_id in ids:
        for pattern in candidates:
            url = format_candidate(pattern, source_record_id)
            exact_ok, exact_reason = validate_exact_detail_url(url, allowed_domains=allowed, source_record_id=source_record_id)
            fetch = fetch_url(session, url, interval_seconds=interval)
            page_title = extract_page_title(fetch.text)
            detail_ok = bool(
                exact_ok
                and fetch.status_code == 200
                and (source_record_id in fetch.final_url or source_record_id in url)
                and title_similarity_ok(title_contains, page_title, fetch.text[:12000])
            )
            attachments = extract_attachments(fetch.text, fetch.final_url) if fetch.text else []
            attempts.append(
                {
                    "source_record_id": source_record_id,
                    "url": url,
                    "final_url": fetch.final_url,
                    "status_code": fetch.status_code,
                    "exact_candidate": exact_ok,
                    "exact_reason": exact_reason,
                    "page_title": page_title,
                    "title_similarity_ok": title_similarity_ok(title_contains, page_title, fetch.text[:12000]),
                    "attachment_count": len(attachments),
                    "failure_reason": "" if detail_ok else classify_failure(fetch) or exact_reason,
                    "verified": detail_ok,
                }
            )
            if detail_ok:
                success_count += 1
                break
    return {"success_count": success_count, "attempts": attempts}


def extract_page_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html or "", flags=re.IGNORECASE | re.DOTALL)
    if match:
        return clean_text(re.sub(r"<[^>]+>", " ", match.group(1)))
    heading = re.search(r"<h[1-3][^>]*>(.*?)</h[1-3]>", html or "", flags=re.IGNORECASE | re.DOTALL)
    if heading:
        return clean_text(re.sub(r"<[^>]+>", " ", heading.group(1)))
    return ""


def build_page_url(list_url: str, page_no: int, mode: str) -> str:
    if page_no <= 1:
        return list_url
    parsed = urlparse(list_url)
    query = parse_qs(parsed.query)
    if mode == "query_nPage":
        query["nPage"] = [str(page_no)]
    elif mode == "article_offset":
        query["article.offset"] = [str((page_no - 1) * 10)]
    elif mode == "jsp_query":
        query["page"] = [str(page_no)]
    else:
        query["page"] = [str(page_no)]
    encoded = urlencode(query, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, encoded, parsed.fragment))


def probe_source(source: dict[str, Any], *, max_pages: int = 3) -> dict[str, Any]:
    session = create_session()
    interval = float(source.get("request_interval_seconds") or 1.0)
    page_results = []
    all_items = []
    first_fetch: FetchResult | None = None
    for page_no in range(1, max_pages + 1):
        page_url = build_page_url(source["list_url"], page_no, source.get("pagination_mode", "unknown"))
        fetch = fetch_url(session, page_url, interval_seconds=interval)
        if first_fetch is None:
            first_fetch = fetch
        if fetch.status_code != 200 or not fetch.text:
            page_results.append({"page_no": page_no, "status_code": fetch.status_code, "failure_reason": classify_failure(fetch)})
            if page_no == 1:
                break
            continue
        items = extract_list_items(fetch.text, fetch.final_url)
        all_items.extend(items)
        page_results.append({"page_no": page_no, "status_code": fetch.status_code, "item_count": len(items), "url": fetch.final_url})
        if page_no > 1 and not items:
            break

    html = first_fetch.text if first_fetch else ""
    known = probe_known_records(source, session)
    sample = all_items[:10]
    attachment_detected = False
    detail_detected = any("href" in item and item["href"] != source["list_url"] for item in sample)
    posted_detected = any(item.get("posted_at_candidates") for item in all_items)
    for item in sample[:3]:
        if item.get("href"):
            detail_fetch = fetch_url(session, item["href"], interval_seconds=interval)
            if detail_fetch.status_code == 200 and extract_attachments(detail_fetch.text, detail_fetch.final_url):
                attachment_detected = True
                break
    failure_reason = ""
    if first_fetch:
        failure_reason = classify_failure(first_fetch)
    recommended_mode = source.get("parser_mode", "html")
    if failure_reason == "playwright_required":
        recommended_mode = "playwright"
    elif first_fetch and first_fetch.status_code in {401, 403}:
        recommended_mode = "manual_only"

    if recommended_mode in {"playwright", "manual_only"} and not posted_detected:
        all_items = []
        sample = []
        detail_detected = False
        attachment_detected = False

    return {
        "source_code": source["source_code"],
        "source_name": source["source_name"],
        "list_url": source["list_url"],
        "list_status": first_fetch.status_code if first_fetch else None,
        "final_url": first_fetch.final_url if first_fetch else source["list_url"],
        "charset": first_fetch.encoding if first_fetch else "",
        "content_type": first_fetch.content_type if first_fetch else "",
        "parser_mode_recommended": recommended_mode,
        "list_item_count": len(all_items),
        "page_results": page_results,
        "sample_items": sample,
        "title_detected": any(item.get("title") for item in all_items),
        "posted_at_detected": posted_detected,
        "detail_link_detected": detail_detected,
        "attachment_detected": attachment_detected,
        "pagination_detected": detect_pagination(html),
        "search_supported": detect_search(html, first_fetch.final_url if first_fetch else source["list_url"]),
        "rss_supported": detect_rss(html),
        "known_record_status": known,
        "failure_reason": failure_reason,
        "recommended_next_action": recommend_next_action(source, known, failure_reason, recommended_mode),
    }


def recommend_next_action(source: dict[str, Any], known: dict[str, Any], failure_reason: str, parser_mode: str) -> str:
    if parser_mode == "manual_only":
        return "접근 제한 또는 수동 확인 필요"
    if parser_mode == "playwright":
        return "requests 렌더링 한계로 Playwright 후보 검토"
    if source["source_code"] == "SH_CONTEST" and not known.get("attempts"):
        return "최신 목록에서 상세 링크 파라미터를 확정한 뒤 known record 추가"
    if known.get("success_count", 0) > 0:
        return "상세 URL 검증 성공, 수집기 구현 가능"
    return "목록 파싱 결과와 상세 URL 후보를 추가 검증"


def summarize_probe(results: list[dict[str, Any]]) -> str:
    lines = ["# Public Housing Contest Probe", ""]
    for result in results:
        known = result.get("known_record_status") or {}
        lines.extend(
            [
                f"## {result['source_code']} - {result['source_name']}",
                "",
                f"- list_status: {result.get('list_status')}",
                f"- parser_mode_recommended: {result.get('parser_mode_recommended')}",
                f"- list_item_count: {result.get('list_item_count')}",
                f"- pagination_detected: {result.get('pagination_detected', {}).get('detected')}",
                f"- search_supported: {result.get('search_supported', {}).get('supported')}",
                f"- rss_supported: {result.get('rss_supported')}",
                f"- detail_link_detected: {result.get('detail_link_detected')}",
                f"- attachment_detected: {result.get('attachment_detected')}",
                f"- known_record_success_count: {known.get('success_count', 0)}",
                f"- failure_reason: {result.get('failure_reason')}",
                f"- recommended_next_action: {result.get('recommended_next_action')}",
                "",
            ]
        )
    return "\n".join(lines)
