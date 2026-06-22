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


SOURCE_TYPE = "public_agency_contest"
BUSINESS_TYPE = "private_participation_public_housing"
DEFAULT_KEYWORDS_PATH = Path("config/public_housing_contest_keywords.json")

SOURCE_CONFIGS: dict[str, dict[str, Any]] = {
    "GH_CONTEST": {
        "collector_name": "GHPublicHousingContestCollector",
        "source_name": "GH",
        "organization": "경기주택도시공사",
        "display_type": "민간사업자 공모",
        "operating_scope": "gh_public_housing_contest",
        "board_url": "https://www.gh.or.kr/gh/bid-announcement.do",
        "record_keys": ("articleNo",),
        "record_label": "articleNo",
        "portal_name": "GH 공모 관련사항",
        "env_prefix": "GH_CONTEST",
        "default_max_pages": 10,
        "default_lookback_days": 730,
    },
    "IH_NOTICE": {
        "collector_name": "IHPublicHousingContestCollector",
        "source_name": "iH",
        "organization": "인천도시공사",
        "display_type": "민간사업자 공모",
        "operating_scope": "ih_public_housing_contest",
        "board_url": "https://www.ih.co.kr/main/customer/notification/notice.jsp",
        "record_keys": ("msg_seq",),
        "record_label": "msg_seq",
        "portal_name": "iH 공지사항",
        "env_prefix": "IH_CONTEST",
        "default_max_pages": 10,
        "default_lookback_days": 730,
    },
}


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
        if tag.lower() in {"p", "div", "li", "tr", "br", "h1", "h2", "h3", "td"}:
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
class AgencyContestRecord:
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
class AgencyCollectStats:
    source_code: str
    collector_name: str
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
    records: list[AgencyContestRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "source_code": self.source_code,
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


def load_source(source_code: str) -> dict[str, Any]:
    for source in load_sources():
        if source.get("source_code") == source_code:
            return source
    raise RuntimeError(f"{source_code} source is not configured.")


def load_keywords(path: Path = DEFAULT_KEYWORDS_PATH) -> dict[str, list[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {key: list(value or []) for key, value in payload.items()}


def html_to_text(html_text: str) -> str:
    parser = TextExtractor()
    parser.feed(html_text or "")
    return parser.text()


def html_unescape(value: str) -> str:
    return html.unescape(value or "")


def parse_date(value: str | None) -> date | None:
    text = clean_text(value)
    if not text:
        return None
    patterns = [
        r"(20\d{2})[./-]\s*(\d{1,2})[./-]\s*(\d{1,2})",
        r"(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    return None


def find_dates(text: str) -> list[str]:
    patterns = [
        r"20\d{2}[./-]\s*\d{1,2}[./-]\s*\d{1,2}",
        r"20\d{2}년\s*\d{1,2}월\s*\d{1,2}일",
    ]
    found: list[str] = []
    for pattern in patterns:
        found.extend(clean_text(match) for match in re.findall(pattern, text or ""))
    return list(dict.fromkeys(found))


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


def clean_detail_title(value: str) -> str:
    text = clean_text(value)
    if "|" in text:
        text = clean_text(text.split("|", 1)[0])
    text = re.sub(r"^공지사항[-\s]*", "", text)
    text = re.sub(r"\s*내용$", "", text)
    return clean_text(text)


def extract_page_title(html_text: str, fallback: str = "") -> str:
    patterns = [
        r"<title[^>]*>(.*?)</title>",
        r"<h[1-3][^>]*>(.*?)</h[1-3]>",
        r"<strong[^>]*class=[\"'][^\"']*(?:title|subject|view)[^\"']*[\"'][^>]*>(.*?)</strong>",
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text or "", flags=re.IGNORECASE | re.DOTALL)
        if match:
            text = clean_detail_title(re.sub(r"<[^>]+>", " ", html_unescape(match.group(1))))
            if text and not any(token in text for token in ["경기주택도시공사", "인천도시공사"]):
                return text
            if text:
                return text
    return clean_text(fallback)


def is_detail_link(source_code: str, href: str) -> bool:
    lowered = href.lower()
    if "download" in lowered or "attachno=" in lowered or "boarddownload" in lowered:
        return False
    if source_code == "GH_CONTEST":
        return "articleno=" in lowered and "mode=view" in lowered
    if source_code == "IH_NOTICE":
        return "msg_seq=" in lowered and "bbsmsgdetail" in lowered and "bcd=notice" in lowered
    return False


def extract_list_items(
    html_text: str,
    base_url: str,
    *,
    source_code: str,
    record_keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in extract_links(html_text, base_url):
        href = link.get("href", "")
        if not is_detail_link(source_code, href):
            continue
        source_record_id = extract_record_id_from_url(href, record_keys)
        title = clean_text(link.get("text"))
        if not source_record_id or source_record_id in seen or len(title) < 5:
            continue
        seen.add(source_record_id)
        idx = html_text.find(source_record_id)
        nearby = html_text[max(0, idx - 900) : idx + 1400] if idx >= 0 else html_text[:1800]
        items.append(
            {
                "source_record_id": source_record_id,
                "title": title,
                "href": href,
                "posted_at_candidates": find_dates(nearby),
            }
        )
    return items


def build_page_url(list_url: str, page_no: int, pagination_mode: str) -> str:
    from src.collectors.public_housing_contests.base import build_page_url as base_build_page_url

    return base_build_page_url(list_url, page_no, pagination_mode)


def build_source_page_url(source_code: str, list_url: str, page_no: int, pagination_mode: str) -> str:
    if source_code == "IH_NOTICE" and page_no > 1:
        return f"https://www.ih.co.kr/main/bbs/bbsMsgList.do?bcd=notice&pgno={page_no}"
    return build_page_url(list_url, page_no, pagination_mode)


def canonical_attachments(raw: list[dict[str, str]], detail_url: str, allowed_domains: list[str]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for attachment in raw:
        name = clean_text(attachment.get("file_name") or attachment.get("name") or attachment.get("text"))
        url = urljoin(detail_url, clean_text(attachment.get("url")))
        if name.endswith(" 다운로드"):
            name = clean_text(name[: -len(" 다운로드")])
        if not name or not url:
            continue
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not host_allowed(url, allowed_domains):
            continue
        lowered = f"{parsed.path.lower()} {name.lower()}"
        file_type = "other"
        for ext in (".pdf", ".hwpx", ".hwp", ".zip", ".xlsx", ".xls"):
            if ext in lowered:
                file_type = ext[1:]
                break
        key = (name, url)
        if key in seen:
            continue
        seen.add(key)
        result.append({"name": name, "file_type": file_type, "url": url})
    return result


def extract_detail_attachments(html_text: str, detail_url: str, allowed_domains: list[str]) -> list[dict[str, str]]:
    raw = list(extract_attachments(html_text, detail_url))
    for link in extract_links(html_text, detail_url):
        href = clean_text(link.get("href"))
        text = clean_text(link.get("text") or link.get("title"))
        lowered = href.lower()
        if not href or not text:
            continue
        if any(token in lowered for token in ["download", "attach", "file"]) or re.search(
            r"\.(pdf|hwp|hwpx|zip|xlsx|xls)\b",
            text.lower(),
        ):
            raw.append({"file_name": text, "url": href})
    return canonical_attachments(raw, detail_url, allowed_domains)


def extract_schedule_text(body: str) -> str | None:
    lines = [clean_text(line) for line in body.splitlines()]
    selected = [
        line
        for line in lines
        if any(term in line for term in ["제출", "접수", "마감", "참가의향서", "사업신청서", "공모일정"])
    ]
    selected = [line for line in selected if len(line) >= 8]
    return "\n".join(selected[:5]) if selected else "공고문 확인 필요"


def extract_deadline(body: str) -> str | None:
    candidates = [
        line
        for line in body.splitlines()
        if any(term in line for term in ["사업신청서", "접수 마감", "제출 마감", "마감일", "신청서 접수"])
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
    text = f"{title}\n{body[:5000]}"
    sites = list(dict.fromkeys(re.findall(r"[가-힣A-Za-z0-9·ㆍ -]{2,40}(?:지구|신도시|구역)", text)))
    blocks = list(dict.fromkeys(re.findall(r"[A-Z가-힣0-9-]{1,16}\s*(?:BL|블록)", text, flags=re.IGNORECASE)))
    return [clean_text(site) for site in sites[:5]], [clean_text(block) for block in blocks[:5]]


def record_fingerprint(source_code: str, source_record_id: str, title: str, posted_at: str | None) -> str:
    payload = f"{source_code}|{source_record_id}|{title}|{posted_at or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def unique_hash(source_code: str, source_record_id: str) -> str:
    return hashlib.sha256(f"{source_code}|{source_record_id}".encode("utf-8")).hexdigest()


def related_group_key(organization: str, title: str, sites: list[str], blocks: list[str]) -> str:
    base = normalize_title(title)
    site = sites[0] if sites else ""
    block = blocks[0] if blocks else ""
    return "|".join(part for part in [organization, base, site, block] if part)


def summarize_body(source_name: str, body: str) -> str:
    lines = [line for line in (clean_text(line) for line in body.splitlines()) if line]
    useful = [
        line
        for line in lines
        if any(term in line for term in ["민간참여", "공공주택", "공모", "사업", "제출", "접수", "대상"])
    ]
    summary = " / ".join(useful[:4]) if useful else f"{source_name} 공식 게시판 상세 공고문을 확인하세요."
    return summary[:1200]


def verify_detail_url(
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
    if any(token in lowered for token in ["captcha", "access denied", "forbidden", "접근 제한", "잘못된 접근"]):
        return False, "access_restricted"
    if not title_matches(expected_title, detail_title, body):
        return False, "title_mismatch"
    return True, "verified"


class AgencyPublicHousingContestCollector:
    def __init__(
        self,
        source_code: str,
        *,
        max_pages: int | None = None,
        lookback_days: int | None = None,
        limit: int | None = None,
        request_interval_seconds: float | None = None,
        timeout_seconds: int | None = None,
        known_record_only: bool = False,
    ) -> None:
        if source_code not in SOURCE_CONFIGS:
            raise ValueError(f"unsupported public housing contest source: {source_code}")
        self.config = SOURCE_CONFIGS[source_code]
        self.source_code = source_code
        self.source = load_source(source_code)
        self.keywords = load_keywords()
        prefix = self.config["env_prefix"]
        self.max_pages = max_pages or int(os.getenv(f"{prefix}_MAX_PAGES", str(self.config["default_max_pages"])))
        self.lookback_days = lookback_days or int(
            os.getenv(f"{prefix}_LOOKBACK_DAYS", str(self.config["default_lookback_days"]))
        )
        self.limit = limit
        self.request_interval_seconds = request_interval_seconds or float(
            os.getenv(f"{prefix}_REQUEST_INTERVAL_SECONDS", self.source.get("request_interval_seconds") or 1.5)
        )
        self.timeout_seconds = timeout_seconds or int(os.getenv(f"{prefix}_TIMEOUT_SECONDS", "20"))
        self.known_record_only = known_record_only
        self.allowed_domains = list(self.source.get("allowed_domains") or [])

    def collect(self) -> AgencyCollectStats:
        stats = AgencyCollectStats(
            source_code=self.source_code,
            collector_name=self.config["collector_name"],
        )
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
                    "title": f"{self.config['source_name']} 공모 {source_record_id}",
                    "href": url,
                    "posted_at_candidates": [],
                }
            )
        return candidates

    def _list_candidates(self, session: Any, stats: AgencyCollectStats) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for page_no in range(1, self.max_pages + 1):
            page_url = build_source_page_url(
                self.source_code,
                self.source["list_url"],
                page_no,
                self.source.get("pagination_mode", "unknown"),
            )
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
            page_items = extract_list_items(
                fetch.text,
                fetch.final_url,
                source_code=self.source_code,
                record_keys=tuple(self.config["record_keys"]),
            )
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
        for item in self._known_candidates():
            source_record_id = clean_text(item.get("source_record_id"))
            if source_record_id and source_record_id not in seen:
                seen.add(source_record_id)
                candidates.append(item)
        return candidates

    def _collect_detail(self, session: Any, candidate: dict[str, Any]) -> AgencyContestRecord | None:
        source_record_id = clean_text(candidate.get("source_record_id"))
        title_from_list = clean_text(candidate.get("title"))
        detail_url = clean_text(candidate.get("href"))
        if not source_record_id:
            return None
        if not detail_url:
            detail_url = format_candidate(self.source.get("detail_url_pattern"), source_record_id)

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
        title = title_from_list if title_from_list and compact(title_from_list) in compact(body) else detail_title
        title = clean_text(title or title_from_list)
        if not matches_contest_keywords(title, body, self.keywords):
            return None

        attachments = extract_detail_attachments(fetch.text, fetch.final_url, self.allowed_domains)
        attachment_names = [attachment["name"] for attachment in attachments]
        notice_stage = classify_notice_stage(title)
        modular = classify_modular_relevance(title, body, attachment_names=attachment_names)
        original_ok, validation_reason = verify_detail_url(
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
        organization = self.config["organization"]
        collected_at = now_iso()
        normalized = normalize_title(title)
        summary = summarize_body(self.config["source_name"], body)
        return AgencyContestRecord(
            source_code=self.source_code,
            source_name=self.config["source_name"],
            organization=organization,
            source_type=SOURCE_TYPE,
            business_type=BUSINESS_TYPE,
            display_type=self.config["display_type"],
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
            board_url=self.config["board_url"],
            attachments=attachments,
            status="ok" if original_ok else "detail_unverified",
            notice_stage=notice_stage,
            modular_relevance=modular.value,
            modular_relevance_score=modular.score,
            modular_evidence=modular.evidence,
            collected_at=collected_at,
            fingerprint=record_fingerprint(self.source_code, source_record_id, title, posted_at),
            related_group_key=related_group_key(organization, title, sites, blocks),
            exact_link_verified=original_ok,
            link_validation_reason=validation_reason,
        )


def item_from_record(record: AgencyContestRecord) -> Item:
    config = SOURCE_CONFIGS[record.source_code]
    keywords = ["민간참여 공공주택", "민간사업자 공모", record.source_name]
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
        unique_hash=unique_hash(record.source_code, record.source_record_id),
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
        operating_scope=config["operating_scope"],
        is_operating_scope=1 if record.is_public_opportunity else 0,
        is_known_important=0,
        demand_org=None,
        notice_org=record.organization,
        exact_url_candidate=record.original_url,
        exact_url_verified=1 if record.exact_link_verified else 0,
        exact_url_verified_at=record.collected_at if record.exact_link_verified else None,
        exact_url_validation_reason=record.link_validation_reason,
        source_detail_api_url=record.original_url,
        source_portal_name=config["portal_name"],
        api_detail_verified=0,
    )


def source_detail_payload(record: AgencyContestRecord) -> dict[str, Any]:
    config = SOURCE_CONFIGS[record.source_code]
    payload = asdict(record)
    payload["manual_check"] = {
        "site_name": config["portal_name"],
        "site_url": config["board_url"],
        "search_text": f"{record.source_record_id} {record.title}",
        "guide_text": (
            f"{config['portal_name']} 게시판에서 공모명 또는 원문 식별번호"
            f"({config['record_label']})로 상세 공고와 첨부파일을 확인하세요."
        ),
    }
    return payload


def find_item_id_by_hash(unique_hash_value: str, db_path: Path = DB_PATH) -> int | None:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT id FROM items WHERE unique_hash = ?", (unique_hash_value,)).fetchone()
        return int(row["id"]) if row else None


def apply_records(stats: AgencyCollectStats, *, db_path: Path = DB_PATH) -> AgencyCollectStats:
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
            detail_api_url=record.original_url or f"{record.source_code.lower()}:{record.source_record_id}",
            detail_payload_json=json.dumps(source_detail_payload(record), ensure_ascii=False),
            status="ok",
            error_message=None,
            db_path=db_path,
        )
    insert_collect_log(
        collector_name=stats.collector_name,
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


def collect_agency_public_housing_contests(
    source_code: str,
    *,
    dry_run: bool = True,
    max_pages: int | None = None,
    lookback_days: int | None = None,
    limit: int | None = None,
    known_record_only: bool = False,
    db_path: Path = DB_PATH,
) -> AgencyCollectStats:
    collector = AgencyPublicHousingContestCollector(
        source_code,
        max_pages=max_pages,
        lookback_days=lookback_days,
        limit=limit,
        known_record_only=known_record_only,
    )
    stats = collector.collect()
    if not dry_run:
        stats = apply_records(stats, db_path=db_path)
    return stats
