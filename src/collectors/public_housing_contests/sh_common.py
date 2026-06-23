from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse


SOURCE_CODE = "SH_CONTEST"
SOURCE_NAME = "SH"
LANDING_URL = "https://www.i-sh.co.kr/main/lay2/program/S1T1C222/subMain4.do?menu=instOpenResultCdList"
BID_LIST_URL = "https://www.i-sh.co.kr/main/lay2/program/S1T316C7212/www/m_2428/BidblancList.do"
G2B_BID_URL = "https://www.g2b.go.kr/link/PNPE027_01/single/"
ATTACHMENT_PREVIEW_URL = "https://www.i-sh.co.kr/main/com/util/htmlConverter.do"
OFFICIAL_HOSTS = {"www.i-sh.co.kr", "i-sh.co.kr"}

PRIMARY_INCLUDE = (
    "민간참여 공공주택건설사업",
    "민간참여 공공주택사업",
    "민간참여 공공주택",
    "민간사업자 공모",
    "민간사업자 재공모",
    "민간사업자 선정 공모",
    "공공주택 민간사업자",
)
HOUSING_CONTEXT = (
    "공공주택",
    "공동주택",
    "주택건설",
    "공공분양",
    "임대주택",
    "주거단지",
    "행복주택",
)
RESULT_KEYWORDS = (
    "평가결과",
    "심사결과",
    "선정결과",
    "우선협상대상자",
    "평가위원",
    "계약체결",
)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", html.unescape(str(value))).strip()


def build_g2b_bid_url(bid_no: str, bid_order: str) -> str:
    return f"{G2B_BID_URL}?{urlencode({'bidPbancNo': bid_no, 'bidPbancOrd': bid_order, 'pbancType': 'pbanc'})}"


def extract_seq(url: str) -> str:
    query = parse_qs(urlparse(url).query)
    return (query.get("seq") or [""])[0]


def keyword_flags(text: str) -> dict[str, bool]:
    normalized = clean_text(text)
    primary = any(token in normalized for token in PRIMARY_INCLUDE)
    context = any(token in normalized for token in HOUSING_CONTEXT)
    result = any(token in normalized for token in RESULT_KEYWORDS)
    return {
        "primary_match": primary,
        "housing_context_match": context,
        "public_housing_candidate": primary and context,
        "general_private_contest_candidate": primary,
        "result_keyword": result,
    }


@dataclass
class LinkInfo:
    text: str
    href: str
    onclick: str = ""


class AnchorParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[LinkInfo] = []
        self._current: dict[str, str] | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = {name.lower(): value or "" for name, value in attrs}
        href = attr_map.get("href", "")
        self._current = {
            "href": urljoin(self.base_url, href) if href and not href.startswith("javascript:") else href,
            "onclick": attr_map.get("onclick", ""),
        }
        self._parts = []

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current is None:
            return
        text = clean_text(" ".join(self._parts))
        self.links.append(LinkInfo(text=text, href=self._current["href"], onclick=self._current["onclick"]))
        self._current = None
        self._parts = []


def extract_links(page_html: str, base_url: str) -> list[LinkInfo]:
    parser = AnchorParser(base_url)
    parser.feed(page_html or "")
    return parser.links


def find_bid_list_url(page_html: str, base_url: str = LANDING_URL) -> str:
    for link in extract_links(page_html, base_url):
        if "BidblancList.do" in link.href:
            return link.href
    return BID_LIST_URL


def parse_landing_notice_links(page_html: str, base_url: str = LANDING_URL) -> list[dict[str, Any]]:
    notices: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in extract_links(page_html, base_url):
        onclick = link.onclick or ""
        match = re.search(r"viewLink\('([^']*?view\.do\?[^']*seq=(\d+)[^']*)'\)", onclick)
        if not match:
            continue
        detail_url = urljoin(base_url, match.group(1))
        source_record_id = match.group(2)
        if source_record_id in seen:
            continue
        seen.add(source_record_id)
        notices.append(
            {
                "source_record_id": source_record_id,
                "title": link.text,
                "detail_url": detail_url,
                "record_id_source": "seq",
                **keyword_flags(link.text),
            }
        )
    return notices


def parse_bid_list_rows(page_html: str) -> list[dict[str, Any]]:
    row_pattern = re.compile(r"<tr[^>]*>\s*<td>(?P<number>\d+)</td>(?P<body>.*?)</tr>", re.IGNORECASE | re.DOTALL)
    rows: list[dict[str, Any]] = []
    for match in row_pattern.finditer(page_html or ""):
        row_html = match.group("body")
        onclick_match = re.search(r"openBidblancDetail\('([^']+)'\s*,\s*'([^']+)'\)", row_html)
        title_match = re.search(r"<a\b[^>]*>(.*?)</a>", row_html, flags=re.IGNORECASE | re.DOTALL)
        cells = [
            clean_text(re.sub(r"<[^>]+>", " ", cell))
            for cell in re.findall(r"<td[^>]*>(.*?)</td>", match.group(0), flags=re.IGNORECASE | re.DOTALL)
        ]
        if not onclick_match or not title_match or len(cells) < 5:
            continue
        title = clean_text(re.sub(r"<[^>]+>", " ", title_match.group(1)))
        bid_no, bid_order = onclick_match.groups()
        rows.append(
            {
                "row_no": int(match.group("number")),
                "title": title,
                "posted_at": cells[2],
                "bid_open_at": cells[3],
                "opening_at": cells[4],
                "bid_no": bid_no,
                "bid_order": bid_order,
                "source_record_id": f"{bid_no}:{bid_order}",
                "record_id_source": "openBidblancDetail(bidNtceNo,bidNtceOrd)",
                "detail_url": build_g2b_bid_url(bid_no, bid_order),
                "detail_url_kind": "g2b_link",
                **keyword_flags(title),
            }
        )
    return rows


def parse_page_count(text: str) -> dict[str, int | None]:
    match = re.search(r"총\s*([\d,]+)\s*건\s*\[(\d+)/(\d+)페이지\]", clean_text(text))
    if not match:
        return {"total_count": None, "current_page": None, "page_count": None}
    return {
        "total_count": int(match.group(1).replace(",", "")),
        "current_page": int(match.group(2)),
        "page_count": int(match.group(3)),
    }


def parse_down_list(page_html: str, detail_url: str) -> list[dict[str, Any]]:
    match = re.search(r"initParam\.downList\s*=\s*(\[[\s\S]*?\]);", page_html or "")
    if not match:
        return []
    try:
        entries = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    attachments: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for entry in entries:
        name = clean_text(entry.get("oriFileNm") or entry.get("fileNm"))
        brd_id = clean_text(entry.get("brdId"))
        seq = clean_text(entry.get("seq") or extract_seq(detail_url))
        file_seq = clean_text(entry.get("fileSeq"))
        file_tp = clean_text(entry.get("fileTp"))
        if not name or not brd_id or not seq or not file_seq:
            continue
        key = (brd_id, seq, file_seq, name)
        if key in seen:
            continue
        seen.add(key)
        preview_query = urlencode({"brd_id": brd_id, "seq": seq, "data_tp": file_tp, "file_seq": file_seq})
        attachments.append(
            {
                "name": name,
                "file_type": Path(name).suffix.lower().lstrip(".") or "other",
                "url": f"{ATTACHMENT_PREVIEW_URL}?{preview_query}",
                "download_handler": "existFile(num) -> POST /main/com/file/existFile.do -> singleDownload(num)",
                "brd_id": brd_id,
                "seq": seq,
                "file_seq": file_seq,
                "file_tp": file_tp,
            }
        )
    return attachments


def parse_notice_detail(page_html: str, detail_url: str, body_text: str = "") -> dict[str, Any]:
    text = body_text or clean_text(re.sub(r"<[^>]+>", "\n", page_html or ""))
    posted_match = re.search(r"등록일\s*:\s*(20\d{2}-\d{2}-\d{2})", text)
    title = ""
    heading = re.search(r"<h[1-3][^>]*>(.*?)</h[1-3]>", page_html or "", flags=re.IGNORECASE | re.DOTALL)
    if heading:
        title = clean_text(re.sub(r"<[^>]+>", " ", heading.group(1)))
    source_record_id = extract_seq(detail_url)
    attachments = parse_down_list(page_html, detail_url)
    parsed_url = urlparse(detail_url)
    query = parse_qs(parsed_url.query)
    if "seq" in query:
        query["seq"] = ["{source_record_id}"]
    detail_pattern = urlunparse(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            parsed_url.params,
            urlencode(query, doseq=True, safe="{}"),
            parsed_url.fragment,
        )
    )
    return {
        "source_record_id": source_record_id,
        "record_id_source": "seq",
        "title": title,
        "posted_at": posted_match.group(1) if posted_match else "",
        "detail_url": detail_url,
        "detail_url_pattern": detail_pattern,
        "attachments": attachments,
        "attachment_count": len(attachments),
        **keyword_flags(f"{title} {text} {' '.join(item['name'] for item in attachments)}"),
    }
