from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from src.collectors.public_housing_contests.base import USER_AGENT, create_session, load_sources
from src.collectors.public_housing_contests.sh_common import (
    BID_LIST_URL,
    LANDING_URL,
    OFFICIAL_HOSTS,
    SOURCE_CODE,
    SOURCE_NAME,
    build_g2b_bid_url,
    clean_text,
    find_bid_list_url,
    keyword_flags,
    parse_bid_list_rows,
    parse_down_list,
    parse_landing_notice_links,
)
from src.config import DB_PATH
from src.database import (
    get_connection,
    init_db,
    insert_collect_log,
    upsert_item,
    upsert_source_detail,
)
from src.models import Item
from src.public_housing_contest_classifier import (
    classify_modular_relevance,
    host_allowed,
    normalize_title,
)


SOURCE_TYPE = "public_agency_contest"
BUSINESS_TYPE = "private_participation_public_housing"
ORGANIZATION = "서울주택도시개발공사"
DISPLAY_TYPE = "민간사업자 공모"
OPERATING_SCOPE = "sh_public_housing_contest"
PORTAL_NAME = "SH 사업발주·공지"
BOARD_URL = BID_LIST_URL
COLLECTOR_NAME = "SHPublicHousingContestCollector"
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_REQUEST_INTERVAL_SECONDS = 1.0

RESULT_TERMS = (
    "평가결과",
    "심사결과",
    "선정결과",
    "우선협상대상자",
    "평가위원",
    "계약체결",
    "선정업체",
    "사업자 선정",
)

IRRELEVANT_TERMS = (
    "상가",
    "시설 운영",
    "운영사업",
    "임대 운영",
    "운영자",
    "용역 사업자",
    "주차장",
)


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int | None
    content_type: str
    encoding: str
    text: str
    error: str = ""


@dataclass
class SHContestRecord:
    source_code: str
    source_name: str
    organization: str
    source_type: str
    business_type: str
    display_type: str
    source_record_id: str
    title: str
    normalized_title: str
    posted_at: str | None
    deadline_at: str | None
    application_schedule_text: str | None
    estimated_cost: int | None
    household_count: int | None
    housing_type: str | None
    project_name: str | None
    project_sites: list[str]
    project_blocks: list[str]
    body_summary: str
    original_url: str | None
    board_url: str
    source_page_url: str
    attachments: list[dict[str, str]]
    status: str
    stage: str
    classification_status: str
    modular_relevance: str
    modular_relevance_score: int
    modular_evidence: list[str]
    collected_at: str
    fingerprint: str
    related_group_key: str
    exact_link_verified: bool
    link_validation_reason: str

    @property
    def is_public_opportunity(self) -> bool:
        return (
            self.classification_status == "confirmed"
            and self.stage == "notice"
            and self.exact_link_verified
        )


@dataclass
class SHG2BDiscovery:
    bid_no: str
    bid_order: str
    title: str
    posted_at: str | None
    detail_url: str
    source_page_url: str
    existing_item_id: int | None = None


@dataclass
class SHCollectStats:
    source_code: str = SOURCE_CODE
    collector_name: str = COLLECTOR_NAME
    collector_mode: str = "http_html"
    transport: str = "requests"
    response_format: str = "html"
    status: str = "success_no_matches"
    source_url: str = BOARD_URL
    list_url: str = BOARD_URL
    final_url: str = ""
    http_status: int | None = None
    page_title: str = ""
    detected_page_type: str = "unknown_page"
    table_found: bool = False
    empty_list_message_found: bool = False
    row_count: int = 0
    rows_with_title: int = 0
    rows_with_identifier: int = 0
    rows_with_posted_date: int = 0
    rows_with_href: int = 0
    rows_with_onclick: int = 0
    rows_with_seq: int = 0
    rows_with_bid_number: int = 0
    parse_success_ratio: float = 0.0
    detail_link_candidate_count: int = 0
    unique_detail_candidate_count: int = 0
    detail_candidate_count: int = 0
    detail_fetch_target_count: int = 0
    detail_fetch_attempted_count: int = 0
    detail_fetch_success_count: int = 0
    detail_fetch_failed_count: int = 0
    parser_mismatch: bool = False
    parser_mismatch_reasons: list[str] = field(default_factory=list)
    failure_reason: str = ""
    scanned: int = 0
    sh_notice_count: int = 0
    g2b_linked_count: int = 0
    candidate_count: int = 0
    confirmed_count: int = 0
    review_required_count: int = 0
    result_count: int = 0
    irrelevant_count: int = 0
    exact_link_count: int = 0
    attachment_count: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    duplicate_merged_count: int = 0
    g2b_unmatched_count: int = 0
    skipped: int = 0
    failed: int = 0
    records: list[SHContestRecord] = field(default_factory=list)
    g2b_discoveries: list[SHG2BDiscovery] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def published_count(self) -> int:
        return sum(1 for record in self.records if record.is_public_opportunity)

    def summary(self) -> dict[str, Any]:
        return {
            "source_code": self.source_code,
            "collector_mode": self.collector_mode,
            "transport": self.transport,
            "response_format": self.response_format,
            "status": self.status,
            "source_url": self.source_url,
            "list_url": self.list_url,
            "final_url": self.final_url,
            "http_status": self.http_status,
            "page_title": self.page_title,
            "detected_page_type": self.detected_page_type,
            "table_found": self.table_found,
            "empty_list_message_found": self.empty_list_message_found,
            "row_count": self.row_count,
            "rows_with_title": self.rows_with_title,
            "rows_with_identifier": self.rows_with_identifier,
            "rows_with_posted_date": self.rows_with_posted_date,
            "rows_with_href": self.rows_with_href,
            "rows_with_onclick": self.rows_with_onclick,
            "rows_with_seq": self.rows_with_seq,
            "rows_with_bid_number": self.rows_with_bid_number,
            "parse_success_ratio": self.parse_success_ratio,
            "detail_link_candidate_count": self.detail_link_candidate_count,
            "unique_detail_candidate_count": self.unique_detail_candidate_count,
            "detail_candidate_count": self.detail_candidate_count,
            "detail_fetch_target_count": self.detail_fetch_target_count,
            "detail_fetch_attempted_count": self.detail_fetch_attempted_count,
            "detail_fetch_success_count": self.detail_fetch_success_count,
            "detail_fetch_failed_count": self.detail_fetch_failed_count,
            "parser_mismatch": self.parser_mismatch,
            "parser_mismatch_reasons": self.parser_mismatch_reasons,
            "failure_reason": self.failure_reason,
            "scanned": self.scanned,
            "scanned_count": self.scanned,
            "sh_notice_count": self.sh_notice_count,
            "g2b_linked_count": self.g2b_linked_count,
            "candidate_count": self.candidate_count,
            "keyword_candidate_count": self.candidate_count,
            "confirmed_count": self.confirmed_count,
            "review_required_count": self.review_required_count,
            "result_count": self.result_count,
            "irrelevant_count": self.irrelevant_count,
            "published_count": self.published_count,
            "exact_link_count": self.exact_link_count,
            "attachment_count": self.attachment_count,
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "duplicate_merged_count": self.duplicate_merged_count,
            "g2b_unmatched_count": self.g2b_unmatched_count,
            "skipped": self.skipped,
            "failed": self.failed,
            "record_count": len(self.records),
            "g2b_discovery_count": len(self.g2b_discoveries),
            "errors": self.errors[:10],
        }


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_date(value: str | None) -> date | None:
    text = clean_text(value)
    if not text:
        return None
    match = re.search(r"(20\d{2})[./-]\s*(\d{1,2})[./-]\s*(\d{1,2})", text)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def parse_date_string(value: str | None) -> str | None:
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else None


def compact(value: str) -> str:
    return re.sub(r"\s+", "", clean_text(value))


def html_to_text(page_html: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", page_html or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|tr|h[1-6]|td|dt|dd)>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    lines = [clean_text(line) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def extract_title(page_html: str, fallback: str = "") -> str:
    for pattern in [
        r"<h[1-3][^>]*>(.*?)</h[1-3]>",
        r"<title[^>]*>(.*?)</title>",
    ]:
        match = re.search(pattern, page_html or "", flags=re.IGNORECASE | re.DOTALL)
        if match:
            title = clean_text(re.sub(r"<[^>]+>", " ", match.group(1)))
            if title:
                return title
    lines = [line for line in html_to_text(page_html).splitlines() if line]
    for line in lines:
        if any(token in line for token in ("공모", "공고", "민간사업자")):
            return line
    return clean_text(fallback)


def summarize_body(body: str) -> str:
    lines = [line for line in (clean_text(line) for line in body.splitlines()) if line]
    selected = [
        line
        for line in lines
        if any(token in line for token in ("민간사업자", "공공주택", "공모", "사업", "제출", "접수"))
    ]
    summary = " / ".join(selected[:4]) if selected else "SH 공식 게시판에서 상세 공고문을 확인하세요."
    return summary[:1200]


def extract_schedule_text(body: str) -> str | None:
    lines = [line for line in (clean_text(line) for line in body.splitlines()) if line]
    selected = [
        line
        for line in lines
        if any(token in line for token in ("제출", "접수", "마감", "참가의향서", "사업신청서", "공모일정"))
    ]
    return "\n".join(selected[:5]) if selected else "공모 일정은 첨부 공고문 확인"


def extract_deadline(body: str) -> str | None:
    for line in body.splitlines():
        if any(token in line for token in ("사업신청서", "접수 마감", "제출 마감", "마감일", "신청서 접수")):
            parsed = parse_date_string(line)
            if parsed:
                return parsed
    return None


def extract_sites_and_blocks(title: str, body: str) -> tuple[list[str], list[str]]:
    text = f"{title}\n{body[:5000]}"
    blocks = list(dict.fromkeys(re.findall(r"[A-Za-z0-9-]{1,20}\s*(?:BL|블록)", text, flags=re.IGNORECASE)))
    sites = list(
        dict.fromkeys(
            re.findall(r"[가-힣A-Za-z0-9·().-]{2,40}(?:지구|구역|사업|단지|환승센터)", text)
        )
    )
    return [clean_text(site) for site in sites[:5]], [clean_text(block) for block in blocks[:5]]


def record_fingerprint(source_record_id: str, title: str, posted_at: str | None) -> str:
    return hashlib.sha256(f"{SOURCE_CODE}|{source_record_id}|{title}|{posted_at or ''}".encode("utf-8")).hexdigest()


def unique_hash(source_record_id: str) -> str:
    return hashlib.sha256(f"{SOURCE_CODE}|{source_record_id}".encode("utf-8")).hexdigest()


def classify_sh_candidate(title: str, body: str = "", attachment_names: list[str] | None = None) -> tuple[str, str]:
    text = " ".join([clean_text(title), clean_text(body), " ".join(attachment_names or [])])
    flags = keyword_flags(text)
    if flags["result_keyword"] and flags["general_private_contest_candidate"]:
        return "result", "result"
    if any(term in text for term in RESULT_TERMS) and flags["general_private_contest_candidate"]:
        return "result", "result"
    if any(term in text for term in IRRELEVANT_TERMS) and not flags["housing_context_match"]:
        return "excluded", "unknown"
    if flags["primary_match"] and flags["housing_context_match"]:
        return "confirmed", "notice"
    if flags["primary_match"]:
        return "review_required", "unknown"
    return "excluded", "unknown"


def title_matches(expected: str, actual: str, body: str) -> bool:
    expected_compact = compact(expected)
    if expected_compact and expected_compact in compact(f"{actual} {body}"):
        return True
    terms = [term for term in re.split(r"[\s\[\]\(\),·._-]+", clean_text(expected)) if len(term) >= 4]
    hits = sum(1 for term in terms if term in actual or term in body)
    return hits >= max(1, min(3, len(terms)))


def verify_sh_detail_url(
    *,
    url: str,
    source_record_id: str,
    expected_title: str,
    detail_title: str,
    body: str,
    status_code: int | None,
) -> tuple[bool, str]:
    if not host_allowed(url, OFFICIAL_HOSTS):
        return False, "domain_not_allowed"
    parsed = urlparse(url)
    if not parsed.query or "seq=" not in parsed.query.lower():
        return False, "list_url_not_exact"
    if source_record_id and source_record_id not in url:
        return False, "source_record_id_missing_in_url"
    if status_code != 200:
        return False, f"http_{status_code}"
    lowered = body[:3000].lower()
    if any(token in lowered for token in ("captcha", "access denied", "forbidden", "로그인", "접근 제한")):
        return False, "access_restricted"
    if not title_matches(expected_title, detail_title, body):
        return False, "title_mismatch"
    return True, "verified"


def official_attachments(raw: list[dict[str, Any]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for attachment in raw:
        name = clean_text(attachment.get("name"))
        url = clean_text(attachment.get("url"))
        if not name or not url or not host_allowed(url, OFFICIAL_HOSTS):
            continue
        file_type = clean_text(attachment.get("file_type")) or Path(urlparse(url).path).suffix.lower().lstrip(".") or "other"
        key = (name, url)
        if key in seen:
            continue
        seen.add(key)
        result.append({"name": name, "file_type": file_type, "url": url})
    return result


def extract_page_title(page_html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", page_html or "", flags=re.IGNORECASE | re.DOTALL)
    return clean_text(re.sub(r"<[^>]+>", " ", match.group(1))) if match else ""


def is_blocked_page(page_html: str) -> bool:
    lowered = (page_html or "").lower()
    return any(token in lowered for token in ("captcha", "access denied", "forbidden", "unauthorized"))


def empty_list_message_found(page_html: str) -> bool:
    text = clean_text(re.sub(r"<[^>]+>", " ", page_html or "")).lower()
    tokens = (
        "no data",
        "no results",
        "\uc870\ud68c\ub41c \ub370\uc774\ud130\uac00 \uc5c6",
        "\ub4f1\ub85d\ub41c \uac8c\uc2dc\ubb3c\uc774 \uc5c6",
        "\uac80\uc0c9\uacb0\uacfc\uac00 \uc5c6",
    )
    return any(token in text for token in tokens)


def detect_page_type(page_html: str, final_url: str, status_code: int | None = 200) -> str:
    if status_code and status_code >= 400:
        return "error_page"
    lowered_url = (final_url or "").lower()
    lowered = (page_html or "").lower()
    if is_blocked_page(page_html) or "login" in lowered_url and "i-sh.co.kr" in lowered_url:
        return "blocked_page"
    if "bidblanclist.do" in lowered_url or "openbidblancdetail" in lowered or "bidntcenm" in lowered:
        return "sh_bid_list"
    if "instopenresultcdlist" in lowered_url:
        return "sh_result_list"
    if "submain4.do" in lowered_url:
        return "menu_wrapper"
    if empty_list_message_found(page_html):
        return "empty_list"
    if parse_landing_notice_links(page_html, final_url):
        return "sh_notice_list"
    return "unknown_page"


def bid_list_health(page_html: str, final_url: str, parsed_rows: list[dict[str, Any]]) -> dict[str, Any]:
    row_blocks = re.findall(r"<tr[^>]*>\s*<td[^>]*>\s*\d+.*?</tr>", page_html or "", flags=re.IGNORECASE | re.DOTALL)
    row_candidates = row_blocks or re.findall(r"<tr[^>]*>\s*<td[^>]*>\s*\d+", page_html or "", flags=re.IGNORECASE)
    onclick_candidates: list[tuple[str, str]] = []
    seq_candidates: list[str] = []
    for row_html in row_candidates:
        onclick_candidates.extend(
            re.findall(
                r"openBidblancDetail\('([^']+)'\s*,\s*'([^']+)'\)",
                row_html,
                flags=re.IGNORECASE,
            )
        )
        seq_candidates.extend(re.findall(r"seq=(\d+)", row_html, flags=re.IGNORECASE))
    rows_with_title = sum(1 for row in parsed_rows if clean_text(row.get("title")))
    rows_with_posted_date = sum(1 for row in parsed_rows if parse_date(clean_text(row.get("posted_at"))))
    row_count = max(len(row_candidates), len(parsed_rows))
    detail_candidates = len(onclick_candidates) + len(seq_candidates)
    unique_detail_candidates = {
        f"g2b:{bid_no}:{bid_order}"
        for bid_no, bid_order in onclick_candidates
        if clean_text(bid_no) and clean_text(bid_order)
    }
    unique_detail_candidates.update(f"seq:{seq}" for seq in seq_candidates if clean_text(seq))
    ratio = round(rows_with_title / row_count, 3) if row_count else 0.0
    return {
        "page_title": extract_page_title(page_html),
        "detected_page_type": detect_page_type(page_html, final_url),
        "table_found": bool(re.search(r"<table\b", page_html or "", flags=re.IGNORECASE)),
        "empty_list_message_found": empty_list_message_found(page_html),
        "row_count": row_count,
        "rows_with_title": rows_with_title,
        "rows_with_identifier": sum(1 for row in parsed_rows if clean_text(row.get("source_record_id"))),
        "rows_with_posted_date": rows_with_posted_date,
        "rows_with_href": len(re.findall(r"<a\b[^>]*href=", page_html or "", flags=re.IGNORECASE)),
        "rows_with_onclick": len(onclick_candidates),
        "rows_with_seq": len(seq_candidates),
        "rows_with_bid_number": len(onclick_candidates),
        "parse_success_ratio": ratio,
        "detail_link_candidate_count": detail_candidates,
        "unique_detail_candidate_count": len(unique_detail_candidates),
        "detail_candidate_count": detail_candidates,
        "detail_fetch_target_count": 0,
    }


def load_sh_source() -> dict[str, Any]:
    for source in load_sources():
        if source.get("source_code") == SOURCE_CODE:
            return source
    return {
        "list_url": BID_LIST_URL,
        "request_interval_seconds": DEFAULT_REQUEST_INTERVAL_SECONDS,
        "allowed_domains": sorted(OFFICIAL_HOSTS),
    }


class SHPublicHousingContestCollector:
    def __init__(
        self,
        *,
        max_pages: int | None = None,
        lookback_days: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        request_interval_seconds: float | None = None,
        timeout_seconds: int | None = None,
        list_url: str | None = None,
        verbose: bool = False,
        db_path: Path = DB_PATH,
    ) -> None:
        self.source = load_sh_source()
        self.list_url = (
            list_url
            or os.getenv("SH_CONTEST_LIST_URL")
            or str(self.source.get("list_url") or "")
            or BID_LIST_URL
        )
        self.max_pages = max_pages or int(os.getenv("SH_CONTEST_MAX_PAGES", "3"))
        self.lookback_days = lookback_days or int(os.getenv("SH_CONTEST_LOOKBACK_DAYS", "1825"))
        self.start_date = start_date
        self.end_date = end_date
        self.request_interval_seconds = request_interval_seconds or float(
            os.getenv(
                "SH_CONTEST_REQUEST_INTERVAL_SECONDS",
                str(self.source.get("request_interval_seconds") or DEFAULT_REQUEST_INTERVAL_SECONDS),
            )
        )
        self.timeout_seconds = timeout_seconds or int(os.getenv("SH_CONTEST_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
        self.verbose = verbose
        self.db_path = db_path
        self.allowed_domains = list(self.source.get("allowed_domains") or sorted(OFFICIAL_HOSTS))
        self.session = create_session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def fetch(self, url: str, *, method: str = "GET", data: dict[str, str] | None = None) -> FetchResult:
        retryable_status = {429, 500, 502, 503, 504}
        last_error = ""
        for attempt in range(3):
            time.sleep(max(self.request_interval_seconds, 1.0) * (1.5**attempt))
            try:
                response = self.session.request(
                    method,
                    url,
                    data=data,
                    timeout=(min(self.timeout_seconds, 10), self.timeout_seconds),
                    allow_redirects=True,
                )
                response.encoding = response.encoding or response.apparent_encoding or "utf-8"
                result = FetchResult(
                    url=url,
                    final_url=response.url,
                    status_code=response.status_code,
                    content_type=response.headers.get("content-type", ""),
                    encoding=response.encoding or "",
                    text=response.text,
                )
                if response.status_code in retryable_status:
                    last_error = f"http_{response.status_code}"
                    continue
                return result
            except requests.RequestException as exc:
                last_error = str(exc)
        return FetchResult(url=url, final_url=url, status_code=None, content_type="", encoding="", text="", error=last_error)

    def collect(self) -> SHCollectStats:
        stats = SHCollectStats()
        landing = self.fetch(self.list_url)
        stats.source_url = landing.url
        stats.final_url = landing.final_url
        stats.http_status = landing.status_code
        stats.page_title = extract_page_title(landing.text)
        stats.detected_page_type = detect_page_type(landing.text, landing.final_url, landing.status_code)
        if landing.status_code != 200 or not landing.text:
            stats.status = "http_error" if landing.status_code else "network_error"
            stats.failure_reason = stats.status
            stats.failed += 1
            stats.errors.append(f"landing: status={landing.status_code} error={landing.error}")
            return stats
        if not host_allowed(landing.final_url, self.allowed_domains):
            stats.status = "blocked"
            stats.failure_reason = "unexpected_domain"
            stats.failed += 1
            stats.errors.append(f"landing domain not allowed: {landing.final_url}")
            return stats
        if stats.detected_page_type == "blocked_page":
            stats.status = "blocked"
            stats.failure_reason = "blocked"
            stats.failed += 1
            return stats

        notices = [] if stats.detected_page_type == "sh_bid_list" else parse_landing_notice_links(landing.text, landing.final_url)
        stats.sh_notice_count = len(notices)
        stats.detail_fetch_target_count = len(notices)
        bid_list_url = landing.final_url if stats.detected_page_type == "sh_bid_list" else find_bid_list_url(landing.text, landing.final_url) or BID_LIST_URL
        stats.list_url = bid_list_url
        bid_rows = self._collect_bid_rows(bid_list_url, stats)
        stats.g2b_linked_count = len(bid_rows)
        stats.scanned = stats.sh_notice_count + stats.g2b_linked_count

        cutoff = date.today().toordinal() - self.lookback_days if self.lookback_days else None
        for notice in notices:
            posted = parse_date(clean_text(notice.get("posted_at")))
            if cutoff and posted and posted.toordinal() < cutoff:
                stats.skipped += 1
                continue
            try:
                stats.detail_fetch_attempted_count += 1
                record = self._collect_notice_detail(notice)
                stats.detail_fetch_success_count += 1
            except Exception as exc:  # pragma: no cover - defensive live failure path
                stats.failed += 1
                stats.detail_fetch_failed_count += 1
                stats.errors.append(f"{notice.get('source_record_id')}: {exc}")
                continue
            if record is None:
                stats.irrelevant_count += 1
                continue
            stats.candidate_count += 1
            if record.classification_status == "confirmed":
                stats.confirmed_count += 1
            elif record.classification_status == "review_required":
                stats.review_required_count += 1
            elif record.stage == "result":
                stats.result_count += 1
            if record.exact_link_verified:
                stats.exact_link_count += 1
            stats.attachment_count += len(record.attachments)
            stats.records.append(record)

        for row in bid_rows:
            discovery = SHG2BDiscovery(
                bid_no=clean_text(row.get("bid_no")),
                bid_order=clean_text(row.get("bid_order")),
                title=clean_text(row.get("title")),
                posted_at=parse_date_string(clean_text(row.get("posted_at"))),
                detail_url=clean_text(row.get("detail_url")),
                source_page_url=bid_list_url,
            )
            if discovery.bid_no:
                discovery.existing_item_id = find_g2b_item_id(discovery.bid_no, discovery.bid_order, db_path=self.db_path)
            if discovery.existing_item_id:
                stats.duplicate_merged_count += 1
            else:
                stats.g2b_unmatched_count += 1
            stats.g2b_discoveries.append(discovery)

        if stats.status in {"wrong_page_type", "blocked", "network_error", "http_error"}:
            stats.failure_reason = stats.failure_reason or stats.status
        elif stats.parser_mismatch:
            stats.status = "parser_mismatch"
            stats.failure_reason = stats.failure_reason or "parser_mismatch"
        elif stats.errors and not stats.records and not stats.g2b_discoveries:
            stats.status = "failed"
            stats.failure_reason = stats.failure_reason or "unexpected_error"
        elif stats.confirmed_count == 0:
            stats.status = "success_no_matches"
        else:
            stats.status = "success"
        return stats

    def _collect_bid_rows(self, bid_list_url: str, stats: SHCollectStats) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for page_no in range(1, self.max_pages + 1):
            if page_no == 1:
                fetch = self.fetch(bid_list_url)
            else:
                fetch = self.fetch(
                    bid_list_url,
                    method="POST",
                    data={
                        "reqPage": str(page_no),
                        "bsnsDivNm": "",
                        "inqryDiv": "",
                        "srchFr": self.start_date or "",
                        "srchTo": self.end_date or "",
                        "bidNtceNm": "",
                    },
                )
            if fetch.status_code != 200 or not fetch.text:
                stats.errors.append(f"bid page {page_no}: status={fetch.status_code} error={fetch.error}")
                if page_no == 1:
                    stats.status = "http_error" if fetch.status_code else "network_error"
                    stats.failure_reason = stats.status
                break
            page_rows = parse_bid_list_rows(fetch.text)
            if page_no == 1:
                health = bid_list_health(fetch.text, fetch.final_url, page_rows)
                for key, value in health.items():
                    setattr(stats, key, value)
                stats.final_url = fetch.final_url
                stats.http_status = fetch.status_code
                if health["detected_page_type"] not in {"sh_bid_list", "empty_list"}:
                    stats.status = "wrong_page_type"
                    stats.failure_reason = "wrong_page_type"
                    stats.parser_mismatch = True
                    stats.parser_mismatch_reasons.append(f"detected_page_type={health['detected_page_type']}")
                    break
            if not page_rows:
                if page_no == 1:
                    if stats.empty_list_message_found:
                        break
                    stats.errors.append("bid list parser returned zero rows")
                    stats.parser_mismatch = True
                    stats.failure_reason = "parser_mismatch"
                    stats.parser_mismatch_reasons.append("no_rows_without_empty_list_message")
                break
            if page_no == 1:
                if stats.row_count and stats.rows_with_title / max(stats.row_count, 1) < 0.5:
                    stats.parser_mismatch = True
                    stats.failure_reason = "parser_mismatch"
                    stats.parser_mismatch_reasons.append("low_title_parse_ratio")
                    break
                if stats.row_count and not stats.detail_candidate_count:
                    stats.parser_mismatch = True
                    stats.failure_reason = "parser_mismatch"
                    stats.parser_mismatch_reasons.append("no_detail_candidates")
                    break
            if stats.parser_mismatch:
                break
            for row in page_rows:
                key = (clean_text(row.get("bid_no")), clean_text(row.get("bid_order")))
                if not key[0] or key in seen:
                    continue
                seen.add(key)
                rows.append(row)
            if len(page_rows) < 10:
                break
        return rows

    def _collect_notice_detail(self, notice: dict[str, Any]) -> SHContestRecord | None:
        source_record_id = clean_text(notice.get("source_record_id"))
        detail_url = clean_text(notice.get("detail_url"))
        list_title = clean_text(notice.get("title"))
        if not source_record_id or not detail_url:
            return None
        fetch = self.fetch(detail_url)
        if fetch.status_code != 200 or not fetch.text:
            raise RuntimeError(f"detail status={fetch.status_code} error={fetch.error}")
        body = html_to_text(fetch.text)
        detail_title = extract_title(fetch.text, fallback=list_title)
        title = detail_title or list_title
        attachments = official_attachments(parse_down_list(fetch.text, fetch.final_url))
        attachment_names = [attachment["name"] for attachment in attachments]
        classification_status, stage = classify_sh_candidate(title, body, attachment_names)
        if classification_status == "excluded":
            return None
        exact, validation_reason = verify_sh_detail_url(
            url=fetch.final_url,
            source_record_id=source_record_id,
            expected_title=list_title or title,
            detail_title=detail_title,
            body=body,
            status_code=fetch.status_code,
        )
        modular = classify_modular_relevance(title, body, attachment_names=attachment_names)
        posted_at = parse_date_string(body) or parse_date_string(notice.get("posted_at"))
        sites, blocks = extract_sites_and_blocks(title, body)
        collected_at = now_iso()
        normalized = normalize_title(title)
        related_key = "|".join(part for part in [ORGANIZATION, normalized, (sites or [""])[0], (blocks or [""])[0]] if part)
        return SHContestRecord(
            source_code=SOURCE_CODE,
            source_name=SOURCE_NAME,
            organization=ORGANIZATION,
            source_type=SOURCE_TYPE,
            business_type=BUSINESS_TYPE,
            display_type=DISPLAY_TYPE,
            source_record_id=source_record_id,
            title=title,
            normalized_title=normalized,
            posted_at=posted_at,
            deadline_at=extract_deadline(body),
            application_schedule_text=extract_schedule_text(body),
            estimated_cost=None,
            household_count=None,
            housing_type=None,
            project_name=normalized or None,
            project_sites=sites,
            project_blocks=blocks,
            body_summary=summarize_body(body),
            original_url=fetch.final_url if exact else None,
            board_url=BOARD_URL,
            source_page_url=detail_url,
            attachments=attachments,
            status="ok" if exact else "detail_unverified",
            stage=stage,
            classification_status=classification_status,
            modular_relevance=modular.value,
            modular_relevance_score=modular.score,
            modular_evidence=modular.evidence,
            collected_at=collected_at,
            fingerprint=record_fingerprint(source_record_id, title, posted_at),
            related_group_key=related_key,
            exact_link_verified=exact,
            link_validation_reason=validation_reason,
        )


def item_from_record(record: SHContestRecord) -> Item:
    keywords = [
        "민간사업자 공모",
        "SH",
        record.classification_status,
        record.stage,
    ]
    keywords.extend(record.modular_evidence)
    return Item(
        source_type=record.source_type,
        source_name=record.source_name,
        title=record.title,
        organization=record.organization,
        posted_at=parse_date(record.posted_at),
        due_at=parse_date(record.deadline_at),
        amount=record.estimated_cost,
        region=", ".join(record.project_sites) or None,
        keywords="; ".join(dict.fromkeys(keywords)),
        summary=record.body_summary,
        url=record.original_url or record.board_url,
        relevance_score=70 + record.modular_relevance_score,
        unique_hash=unique_hash(record.source_record_id),
        is_mock=0,
        data_quality="real",
        original_url=record.original_url,
        source_search_url=record.board_url,
        link_type="exact" if record.exact_link_verified else "unknown",
        link_status="ok" if record.exact_link_verified else "unknown",
        link_checked_at=record.collected_at if record.exact_link_verified else None,
        source_record_id=record.source_record_id,
        source_record_no=None,
        bid_no=record.source_record_id,
        bid_order=None,
        notice_status=record.stage,
        business_type=record.business_type,
        business_subtype=record.display_type,
        operating_scope=OPERATING_SCOPE,
        is_operating_scope=1 if record.is_public_opportunity else 0,
        is_known_important=0,
        demand_org=None,
        notice_org=record.organization,
        exact_url_candidate=record.original_url,
        exact_url_verified=1 if record.exact_link_verified else 0,
        exact_url_verified_at=record.collected_at if record.exact_link_verified else None,
        exact_url_validation_reason=record.link_validation_reason,
        source_detail_api_url=record.original_url,
        source_portal_name=PORTAL_NAME,
        api_detail_verified=0,
    )


def source_detail_payload(record: SHContestRecord) -> dict[str, Any]:
    payload = asdict(record)
    payload["manual_check"] = {
        "site_name": PORTAL_NAME,
        "site_url": BOARD_URL,
        "search_text": f"{record.source_record_id} {record.title}",
        "guide_text": "SH 공식 게시판에서 공모명 또는 원문 식별번호(seq)로 상세 공고와 첨부파일을 확인하세요.",
    }
    return payload


def g2b_discovery_payload(discovery: SHG2BDiscovery) -> dict[str, Any]:
    return {
        "source_code": SOURCE_CODE,
        "source_name": SOURCE_NAME,
        "source_type": "bid",
        "discovery_type": "g2b_linked_bid",
        "also_found_on": ["SH"],
        "bid_no": discovery.bid_no,
        "bid_order": discovery.bid_order,
        "title": discovery.title,
        "posted_at": discovery.posted_at,
        "sh_source_page_url": discovery.source_page_url,
        "g2b_detail_url": discovery.detail_url,
        "sh_first_seen_at": now_iso(),
        "sh_last_seen_at": now_iso(),
        "manual_check": {
            "site_name": "SH 사업발주 공고",
            "site_url": discovery.source_page_url,
            "search_text": f"{discovery.bid_no} {discovery.title}",
            "guide_text": "SH 사업발주 목록에서 확인된 나라장터 연계 공고입니다. 동일 나라장터 공고 카드와 중복 공개하지 않습니다.",
        },
    }


def find_item_id_by_hash(unique_hash_value: str, db_path: Path = DB_PATH) -> int | None:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT id FROM items WHERE unique_hash = ?", (unique_hash_value,)).fetchone()
        return int(row["id"]) if row else None


def find_g2b_item_id(bid_no: str, bid_order: str | None, *, db_path: Path = DB_PATH) -> int | None:
    bid_no = clean_text(bid_no)
    bid_order = clean_text(bid_order)
    if not bid_no:
        return None
    if not Path(db_path).exists():
        return None
    try:
        with get_connection(db_path) as conn:
            row = conn.execute(
                """
                SELECT id
                FROM items
                WHERE source_type = 'bid'
                  AND (
                    bid_no = ?
                    OR source_record_id = ?
                  )
                  AND COALESCE(bid_order, source_record_no, '') = COALESCE(?, '')
                ORDER BY id DESC
                LIMIT 1
                """,
                (bid_no, bid_no, bid_order),
            ).fetchone()
            return int(row["id"]) if row else None
    except sqlite3.Error:
        return None


def apply_sh_stats(stats: SHCollectStats, *, db_path: Path = DB_PATH) -> SHCollectStats:
    init_db(db_path)
    started_at = now_iso()
    for record in stats.records:
        item = item_from_record(record)
        status = upsert_item(item, db_path=db_path)
        if status == "inserted":
            stats.inserted += 1
        elif status == "updated":
            stats.updated += 1
        else:
            stats.unchanged += 1
        item_id = find_item_id_by_hash(item.unique_hash, db_path=db_path)
        if item_id is None:
            stats.failed += 1
            stats.errors.append(f"item id not found after upsert: {record.source_record_id}")
            continue
        upsert_source_detail(
            item_id=item_id,
            source_name=record.source_name,
            source_type=record.source_type,
            source_record_id=record.source_record_id,
            source_record_no=None,
            detail_api_url=record.original_url or f"sh_contest:{record.source_record_id}",
            detail_payload_json=json.dumps(source_detail_payload(record), ensure_ascii=False),
            status=record.status,
            error_message=None,
            db_path=db_path,
        )
    for discovery in stats.g2b_discoveries:
        item_id = discovery.existing_item_id or find_g2b_item_id(discovery.bid_no, discovery.bid_order, db_path=db_path)
        if not item_id:
            continue
        upsert_source_detail(
            item_id=item_id,
            source_name=SOURCE_NAME,
            source_type="bid",
            source_record_id=discovery.bid_no,
            source_record_no=discovery.bid_order,
            detail_api_url=f"sh:g2b:{discovery.bid_no}:{discovery.bid_order}",
            detail_payload_json=json.dumps(g2b_discovery_payload(discovery), ensure_ascii=False),
            status="discovered_on_sh",
            error_message=None,
            db_path=db_path,
        )
    log_status = "success" if stats.status in {"success", "success_no_matches"} and not stats.errors else "partial_warning"
    if stats.status in {"failed", "parser_mismatch"}:
        log_status = "failed"
    insert_collect_log(
        collector_name=COLLECTOR_NAME,
        source_type=SOURCE_TYPE,
        started_at=started_at,
        finished_at=now_iso(),
        status=log_status,
        inserted_count=stats.inserted,
        updated_count=stats.updated,
        skipped_count=stats.unchanged + stats.skipped + stats.irrelevant_count + stats.g2b_unmatched_count,
        error_message=json.dumps(stats.summary(), ensure_ascii=False),
        db_path=db_path,
    )
    return stats


def collect_sh_public_housing_contests(
    *,
    dry_run: bool = True,
    max_pages: int | None = None,
    lookback_days: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    list_url: str | None = None,
    request_interval_seconds: float | None = None,
    timeout_seconds: int | None = None,
    verbose: bool = False,
    db_path: Path = DB_PATH,
) -> SHCollectStats:
    collector = SHPublicHousingContestCollector(
        max_pages=max_pages,
        lookback_days=lookback_days,
        start_date=start_date,
        end_date=end_date,
        list_url=list_url,
        request_interval_seconds=request_interval_seconds,
        timeout_seconds=timeout_seconds,
        verbose=verbose,
        db_path=db_path,
    )
    stats = collector.collect()
    if not dry_run:
        stats = apply_sh_stats(stats, db_path=db_path)
    return stats


__all__ = [
    "BID_LIST_URL",
    "BOARD_URL",
    "COLLECTOR_NAME",
    "SHCollectStats",
    "SHContestRecord",
    "SHPublicHousingContestCollector",
    "apply_sh_stats",
    "classify_sh_candidate",
    "collect_sh_public_housing_contests",
    "find_g2b_item_id",
    "html_to_text",
    "item_from_record",
    "parse_bid_list_rows",
    "parse_date",
    "verify_sh_detail_url",
]
