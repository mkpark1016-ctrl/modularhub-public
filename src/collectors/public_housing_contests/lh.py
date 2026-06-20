from __future__ import annotations

import hashlib
import html
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from src.collectors.public_housing_contests.base import (
    create_session,
    extract_attachments,
    extract_links,
    extract_record_id_from_url,
    fetch_url,
    format_candidate,
    load_sources,
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
    classify_notice_stage,
    clean_text,
    host_allowed,
    is_business_opportunity_stage,
    normalize_title,
    validate_exact_detail_url,
)


COLLECTOR_NAME = "LHPublicHousingContestCollector"
SOURCE_CODE = "LH_CONTEST"
SOURCE_TYPE = "public_agency_contest"
BUSINESS_TYPE = "private_participation_public_housing"
OPERATING_SCOPE = "lh_public_housing_contest"
BOARD_URL = "https://www.lh.or.kr/board.es?mid=a10601020000&bid=0034"
DEFAULT_KEYWORDS_PATH = Path("config/public_housing_contest_keywords.json")


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if tag.lower() in {"p", "div", "li", "tr", "br", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            text = clean_text(data)
            if text:
                self.parts.append(text)

    def text(self) -> str:
        lines = [clean_text(line) for line in " ".join(self.parts).split("\n")]
        return "\n".join(line for line in lines if line)


@dataclass
class LHContestRecord:
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
    attachments: list[dict[str, str]]
    status: str
    notice_stage: str
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
        return is_business_opportunity_stage(self.notice_stage)


@dataclass
class LHCollectStats:
    scanned: int = 0
    matched: int = 0
    opportunity: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    failed: int = 0
    exact_link_verified: int = 0
    attachment_count: int = 0
    records: list[LHContestRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "matched": self.matched,
            "opportunity": self.opportunity,
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "skipped": self.skipped,
            "failed": self.failed,
            "exact_link_verified": self.exact_link_verified,
            "attachment_count": self.attachment_count,
            "record_count": len(self.records),
            "errors": self.errors[:10],
        }


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_lh_source() -> dict[str, Any]:
    for source in load_sources():
        if source.get("source_code") == SOURCE_CODE:
            return source
    raise RuntimeError("LH_CONTEST source is not configured.")


def load_keywords(path: Path = DEFAULT_KEYWORDS_PATH) -> dict[str, list[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {key: list(value or []) for key, value in payload.items()}


def html_to_text(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html or "")
    return parser.text()


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


def find_dates(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"20\d{2}[./-]\s*\d{1,2}[./-]\s*\d{1,2}", text or "")))


def compact(text: str) -> str:
    return re.sub(r"\s+", "", clean_text(text))


def matches_contest_keywords(title: str, body: str, keywords: dict[str, list[str]]) -> bool:
    haystack = f"{title} {body}"
    primary = keywords.get("primary_include") or []
    context = keywords.get("required_context_any") or []
    return any(term in haystack for term in primary) and any(term in haystack for term in context)


def title_matches(expected: str, detail_title: str, body: str) -> bool:
    expected_compact = compact(expected)
    if expected_compact and expected_compact in compact(f"{detail_title} {body}"):
        return True
    expected_terms = [term for term in re.split(r"[\s\[\]\(\)·ㆍ:,-]+", expected) if len(term) >= 4]
    hits = sum(1 for term in expected_terms if term in body or term in detail_title)
    return hits >= max(1, min(3, len(expected_terms)))


def extract_page_title(html: str, fallback: str = "") -> str:
    patterns = [
        r"<h[1-3][^>]*>(.*?)</h[1-3]>",
        r"<strong[^>]*class=[\"'][^\"']*(?:title|subject|view)[^\"']*[\"'][^>]*>(.*?)</strong>",
        r"<title[^>]*>(.*?)</title>",
    ]
    for pattern in patterns:
        match = re.search(pattern, html or "", flags=re.IGNORECASE | re.DOTALL)
        if match:
            text = clean_text(re.sub(r"<[^>]+>", " ", match.group(1)))
            if text and "한국토지주택공사" not in text:
                return text
    return clean_text(fallback)


def extract_lh_list_items(html: str, base_url: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    view_pattern = re.compile(
        r"<a[^>]+onclick=[\"']goView3\('(?P<id>\d+)','(?P<url>[^']+)'\)[^\"']*[\"'][^>]*>"
        r"(?P<title>.*?)</a>.*?<td[^>]+aria-label=[\"']등록일[\"'][^>]*>(?P<date>.*?)</td>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in view_pattern.finditer(html or ""):
        list_no = clean_text(match.group("id"))
        if not list_no or list_no in seen:
            continue
        seen.add(list_no)
        url = urljoin(base_url, html_unescape(match.group("url")))
        title = clean_text(re.sub(r"<[^>]+>", " ", html_unescape(match.group("title"))))
        posted = clean_text(re.sub(r"<[^>]+>", " ", html_unescape(match.group("date"))))
        items.append(
            {
                "source_record_id": list_no,
                "title": title,
                "href": url,
                "posted_at_candidates": [posted] if posted else [],
                "attachments": extract_lh_download_links(html, base_url, list_no),
            }
        )

    for link in extract_links(html, base_url):
        href = link.get("href", "")
        lowered_href = href.lower()
        if "boarddownload" in lowered_href or "download" in lowered_href or "file" in lowered_href:
            continue
        if "act=view" not in lowered_href or "board.es" not in lowered_href:
            continue
        list_no = extract_record_id_from_url(href, ("list_no",))
        if not list_no or list_no in seen:
            continue
        seen.add(list_no)
        title = clean_text(link.get("text"))
        if len(title) < 5:
            title = f"LH 공모안내 {list_no}"
        idx = html.find(list_no)
        nearby = html[max(0, idx - 800) : idx + 1200] if idx >= 0 else html
        posted_candidates = find_dates(nearby)
        items.append(
            {
                "source_record_id": list_no,
                "title": title,
                "href": href,
                "posted_at_candidates": posted_candidates,
                "attachments": extract_lh_download_links(html, base_url, list_no),
            }
        )
    return items


def html_unescape(value: str) -> str:
    return html.unescape(value or "")


def extract_lh_download_links(html_text: str, base_url: str, source_record_id: str) -> list[dict[str, str]]:
    pattern = re.compile(
        rf"<a[^>]+href=[\"'](?P<href>[^\"']*boardDownload\.es[^\"']*list_no={re.escape(source_record_id)}[^\"']*)[\"'][^>]*"
        rf"(?:title=[\"'](?P<title>[^\"']*)[\"'])?[^>]*>(?P<text>.*?)</a>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    attachments: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in pattern.finditer(html_text or ""):
        url = urljoin(base_url, html_unescape(match.group("href")))
        name = clean_text(html_unescape(match.group("title") or ""))
        if name.endswith(" 다운로드"):
            name = name[: -len(" 다운로드")]
        if not name:
            name = clean_text(re.sub(r"<[^>]+>", " ", html_unescape(match.group("text"))))
        if not name or url in seen:
            continue
        seen.add(url)
        attachments.append({"file_name": name, "url": url})
    return attachments


def build_page_url(list_url: str, page_no: int) -> str:
    if page_no <= 1:
        return list_url
    separator = "&" if "?" in list_url else "?"
    return f"{list_url}{separator}nPage={page_no}"


def canonical_attachments(raw: list[dict[str, str]], detail_url: str, allowed_domains: list[str]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for attachment in raw:
        name = clean_text(attachment.get("file_name") or attachment.get("name"))
        url = urljoin(detail_url, clean_text(attachment.get("url")))
        if not name or not url:
            continue
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not host_allowed(url, allowed_domains):
            continue
        path = parsed.path.lower()
        file_type = ""
        for ext in (".pdf", ".hwpx", ".hwp", ".zip"):
            if path.endswith(ext) or ext[1:] in name.lower():
                file_type = ext[1:]
                break
        key = (name, url)
        if key in seen:
            continue
        seen.add(key)
        result.append({"name": name, "file_type": file_type or "unknown", "url": url})
    return result


def extract_schedule_text(body: str) -> str | None:
    lines = [clean_text(line) for line in body.splitlines()]
    selected = [
        line
        for line in lines
        if any(term in line for term in ["제출", "접수", "마감", "참가의향서", "사업신청서", "공모일정"])
    ]
    selected = [line for line in selected if len(line) >= 8]
    if selected:
        return "\n".join(selected[:5])
    return "공고문 확인 필요"


def extract_deadline(body: str) -> str | None:
    candidates = [
        line
        for line in body.splitlines()
        if any(term in line for term in ["사업신청서", "접수 마감", "제출 마감", "마감일"])
    ]
    for line in candidates:
        dates = find_dates(line)
        if dates:
            return dates[-1]
    return None


def extract_amount(body: str) -> int | None:
    patterns = [
        r"(?:추정\s*사업비|사업비|예산)[^\n]{0,30}?([0-9,]+)\s*억\s*원",
        r"(?:추정\s*사업비|사업비|예산)[^\n]{0,30}?([0-9,]+)\s*원",
    ]
    for pattern in patterns:
        match = re.search(pattern, body)
        if not match:
            continue
        number = int(match.group(1).replace(",", ""))
        return number * 100_000_000 if "억" in match.group(0) else number
    return None


def extract_household_count(body: str) -> int | None:
    match = re.search(r"([0-9,]+)\s*세대", body)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def extract_sites_and_blocks(title: str, body: str) -> tuple[list[str], list[str]]:
    text = f"{title}\n{body[:4000]}"
    sites = list(dict.fromkeys(re.findall(r"[가-힣A-Za-z0-9·ㆍ -]{2,30}(?:지구|신도시)", text)))
    blocks = list(dict.fromkeys(re.findall(r"[A-Z가-힣0-9-]{1,12}\s*(?:BL|블록)", text, flags=re.IGNORECASE)))
    return [clean_text(site) for site in sites[:5]], [clean_text(block) for block in blocks[:5]]


def record_fingerprint(source_record_id: str, title: str, posted_at: str | None) -> str:
    payload = f"{SOURCE_CODE}|{source_record_id}|{title}|{posted_at or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def unique_hash(source_record_id: str) -> str:
    return hashlib.sha256(f"{SOURCE_CODE}|{source_record_id}".encode("utf-8")).hexdigest()


def related_group_key(organization: str, title: str, sites: list[str], blocks: list[str]) -> str:
    base = normalize_title(title)
    site = sites[0] if sites else ""
    block = blocks[0] if blocks else ""
    return "|".join(part for part in [organization, base, site, block] if part)


def summarize_body(body: str) -> str:
    lines = [line for line in (clean_text(line) for line in body.splitlines()) if line]
    useful = [
        line
        for line in lines
        if any(term in line for term in ["민간참여", "공공주택", "공모", "사업", "제출", "접수", "대상"])
    ]
    summary = " / ".join(useful[:4]) if useful else "LH 공모안내 상세 공고문을 확인하세요."
    return summary[:1200]


def verify_lh_detail_url(
    *,
    url: str,
    allowed_domains: list[str],
    source_record_id: str,
    expected_title: str,
    status_code: int | None,
    detail_title: str,
    body: str,
) -> tuple[bool, str]:
    exact_ok, reason = validate_exact_detail_url(url, allowed_domains=allowed_domains, source_record_id=source_record_id)
    if not exact_ok:
        return False, reason
    if status_code != 200:
        return False, f"http_{status_code}"
    lowered = body[:3000].lower()
    if any(token in lowered for token in ["captcha", "access denied", "forbidden"]):
        return False, "access_restricted"
    if not title_matches(expected_title, detail_title, body):
        return False, "title_mismatch"
    return True, "verified"


class LHPublicHousingContestCollector:
    def __init__(
        self,
        *,
        max_pages: int | None = None,
        lookback_days: int | None = None,
        limit: int | None = None,
        request_interval_seconds: float | None = None,
        timeout_seconds: int | None = None,
        known_record_only: bool = False,
    ) -> None:
        self.source = load_lh_source()
        self.keywords = load_keywords()
        self.max_pages = max_pages or int(os.getenv("LH_CONTEST_MAX_PAGES", "10"))
        self.lookback_days = lookback_days or int(os.getenv("LH_CONTEST_LOOKBACK_DAYS", "730"))
        self.limit = limit
        self.request_interval_seconds = request_interval_seconds or float(
            os.getenv("LH_CONTEST_REQUEST_INTERVAL_SECONDS", self.source.get("request_interval_seconds") or 1.5)
        )
        self.timeout_seconds = timeout_seconds or int(os.getenv("LH_CONTEST_TIMEOUT_SECONDS", "20"))
        self.known_record_only = known_record_only
        self.allowed_domains = list(self.source.get("allowed_domains") or ["www.lh.or.kr", "lh.or.kr"])

    def collect(self) -> LHCollectStats:
        stats = LHCollectStats()
        session = create_session()
        candidates = self._known_candidates() if self.known_record_only else self._list_candidates(session, stats)
        cutoff = date.today().toordinal() - self.lookback_days if self.lookback_days else None
        for candidate in candidates:
            if self.limit and len(stats.records) >= self.limit:
                break
            posted_date = parse_date((candidate.get("posted_at_candidates") or [None])[0])
            if cutoff and posted_date and posted_date.toordinal() < cutoff:
                stats.skipped += 1
                continue
            try:
                record = self._collect_detail(session, candidate)
            except Exception as exc:  # pragma: no cover - defensive logging path
                stats.failed += 1
                stats.errors.append(f"{candidate.get('source_record_id')}: {exc}")
                continue
            if not record:
                stats.skipped += 1
                continue
            stats.matched += 1
            if record.is_public_opportunity:
                stats.opportunity += 1
            if record.exact_link_verified:
                stats.exact_link_verified += 1
            stats.attachment_count += len(record.attachments)
            stats.records.append(record)
        return stats

    def _known_candidates(self) -> list[dict[str, Any]]:
        known = self.source.get("known_record") or {}
        patterns = self.source.get("detail_url_candidates") or [self.source.get("detail_url_pattern")]
        candidates = []
        for source_record_id in known.get("source_record_ids") or []:
            url = format_candidate(patterns[0], source_record_id)
            candidates.append(
                {
                    "source_record_id": source_record_id,
                    "title": f"LH 공모안내 {source_record_id}",
                    "href": url,
                    "posted_at_candidates": [],
                }
            )
        return candidates

    def _list_candidates(self, session: Any, stats: LHCollectStats) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for page_no in range(1, self.max_pages + 1):
            page_url = build_page_url(self.source["list_url"], page_no)
            fetch = fetch_url(
                session,
                page_url,
                interval_seconds=self.request_interval_seconds,
                timeout=self.timeout_seconds,
            )
            if fetch.status_code != 200 or not fetch.text:
                stats.errors.append(f"list page {page_no}: status={fetch.status_code} error={fetch.error}")
                if page_no == 1:
                    break
                continue
            page_items = extract_lh_list_items(fetch.text, fetch.final_url)
            if page_no > 1 and not page_items:
                break
            for item in page_items:
                source_record_id = clean_text(item.get("source_record_id"))
                if not source_record_id or source_record_id in seen:
                    continue
                seen.add(source_record_id)
                stats.scanned += 1
                if not matches_contest_keywords(clean_text(item.get("title")), "", self.keywords):
                    continue
                candidates.append(item)
        return candidates

    def _collect_detail(self, session: Any, candidate: dict[str, Any]) -> LHContestRecord | None:
        source_record_id = clean_text(candidate.get("source_record_id"))
        title_from_list = clean_text(candidate.get("title"))
        detail_url = clean_text(candidate.get("href"))
        if not source_record_id:
            return None
        if not detail_url:
            pattern = self.source.get("detail_url_pattern")
            detail_url = format_candidate(pattern, source_record_id)

        fetch = fetch_url(
            session,
            detail_url,
            interval_seconds=self.request_interval_seconds,
            timeout=self.timeout_seconds,
        )
        if not fetch.text:
            raise RuntimeError(f"empty detail response: status={fetch.status_code} error={fetch.error}")

        body = html_to_text(fetch.text)
        detail_title = extract_page_title(fetch.text, fallback=title_from_list)
        title = title_from_list if title_from_list and title_from_list in body else detail_title or title_from_list
        if not matches_contest_keywords(title, body, self.keywords):
            return None

        raw_attachments = list(candidate.get("attachments") or [])
        raw_attachments.extend(extract_attachments(fetch.text, fetch.final_url))
        attachments = canonical_attachments(raw_attachments, fetch.final_url, self.allowed_domains)
        attachment_names = [attachment["name"] for attachment in attachments]
        notice_stage = classify_notice_stage(title)
        modular = classify_modular_relevance(title, body, attachment_names=attachment_names)
        original_ok, validation_reason = verify_lh_detail_url(
            url=fetch.final_url,
            allowed_domains=self.allowed_domains,
            source_record_id=source_record_id,
            expected_title=title,
            status_code=fetch.status_code,
            detail_title=detail_title,
            body=body,
        )
        dates = find_dates(body)
        posted_at = None
        for value in list(candidate.get("posted_at_candidates") or []) + dates:
            parsed = parse_date(value)
            if parsed:
                posted_at = parsed.isoformat()
                break
        deadline_at = extract_deadline(body)
        sites, blocks = extract_sites_and_blocks(title, body)
        organization = "한국토지주택공사"
        collected_at = now_iso()
        normalized = normalize_title(title)
        summary = summarize_body(body)
        return LHContestRecord(
            source_code=SOURCE_CODE,
            source_name="LH",
            organization=organization,
            source_type=SOURCE_TYPE,
            business_type=BUSINESS_TYPE,
            display_type="민간사업자 공모",
            source_record_id=source_record_id,
            title=title,
            normalized_title=normalized,
            posted_at=posted_at,
            deadline_at=deadline_at,
            application_schedule_text=extract_schedule_text(body),
            estimated_cost=extract_amount(body),
            household_count=extract_household_count(body),
            housing_type=None,
            project_name=normalized or None,
            project_sites=sites,
            project_blocks=blocks,
            body_summary=summary,
            original_url=fetch.final_url if original_ok else None,
            board_url=BOARD_URL,
            attachments=attachments,
            status="ok" if original_ok else "detail_unverified",
            notice_stage=notice_stage,
            modular_relevance=modular.value,
            modular_relevance_score=modular.score,
            modular_evidence=modular.evidence,
            collected_at=collected_at,
            fingerprint=record_fingerprint(source_record_id, title, posted_at),
            related_group_key=related_group_key(organization, title, sites, blocks),
            exact_link_verified=original_ok,
            link_validation_reason=validation_reason,
        )


def item_from_record(record: LHContestRecord) -> Item:
    keywords = ["민간참여 공공주택", "민간사업자 공모", "LH"]
    keywords.extend(record.modular_evidence)
    score = 70 + record.modular_relevance_score
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
        relevance_score=score,
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
        notice_status=record.notice_stage,
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
        source_portal_name="LH 공모안내",
        api_detail_verified=0,
    )


def source_detail_payload(record: LHContestRecord) -> dict[str, Any]:
    payload = asdict(record)
    payload["manual_check"] = {
        "site_name": "LH 공모안내",
        "site_url": BOARD_URL,
        "search_text": f"{record.source_record_id} {record.title}",
        "guide_text": "LH 공모안내 게시판에서 공모명 또는 원문 식별번호(list_no)로 상세 공고와 첨부파일을 확인하세요.",
    }
    return payload


def find_item_id_by_hash(unique_hash_value: str, db_path: Path = DB_PATH) -> int | None:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT id FROM items WHERE unique_hash = ?", (unique_hash_value,)).fetchone()
        return int(row["id"]) if row else None


def apply_records(stats: LHCollectStats, *, db_path: Path = DB_PATH) -> LHCollectStats:
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
            detail_api_url=record.original_url or f"lh_contest:{record.source_record_id}",
            detail_payload_json=json.dumps(source_detail_payload(record), ensure_ascii=False),
            status="ok",
            error_message=None,
            db_path=db_path,
        )
    insert_collect_log(
        collector_name=COLLECTOR_NAME,
        source_type=SOURCE_TYPE,
        started_at=started_at,
        finished_at=now_iso(),
        status="success" if not stats.errors else "partial_warning",
        inserted_count=stats.inserted,
        updated_count=stats.updated,
        skipped_count=stats.unchanged + stats.skipped,
        error_message=json.dumps(stats.summary(), ensure_ascii=False),
        db_path=db_path,
    )
    return stats


def collect_lh_public_housing_contests(
    *,
    dry_run: bool = True,
    max_pages: int | None = None,
    lookback_days: int | None = None,
    limit: int | None = None,
    known_record_only: bool = False,
    db_path: Path = DB_PATH,
) -> LHCollectStats:
    collector = LHPublicHousingContestCollector(
        max_pages=max_pages,
        lookback_days=lookback_days,
        limit=limit,
        known_record_only=known_record_only,
    )
    stats = collector.collect()
    if not dry_run:
        stats = apply_records(stats, db_path=db_path)
    return stats
