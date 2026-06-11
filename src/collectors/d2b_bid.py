from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from typing import Any

import requests

from src.collectors.base import BaseCollector
from src.config import (
    D2B_BID_BASE_ENDPOINT,
    D2B_BID_DOMESTIC_ENDPOINT,
    D2B_BID_FOREIGN_ENDPOINT,
    D2B_BID_LOOKBACK_DAYS,
    D2B_BID_PAGE_SIZE,
    D2B_BID_PUBLIC_PRIVATE_ENDPOINT,
    DATA_GO_KR_SERVICE_KEY,
)
from src.keywords import (
    D2B_DEFENSE_ORGANIZATION_KEYWORDS,
    D2B_DIRECT_KEYWORDS,
    D2B_FACILITY_KEYWORDS,
    DEFAULT_KEYWORDS,
)


DEFAULT_D2B_BID_BASE_ENDPOINT = "https://openapi.d2b.go.kr/openapi/service/BidPblancInfoService"
DEFAULT_D2B_BID_DOMESTIC_ENDPOINT = (
    "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList"
)
D2B_BID_DATE_BEGIN_PARAM = "anmtDateBegin"
D2B_BID_DATE_END_PARAM = "anmtDateEnd"
D2B_SEARCH_URL = "https://www.d2b.go.kr/"
MAX_D2B_BID_PAGES = 3


class D2BBidCollector(BaseCollector):
    def __init__(self) -> None:
        self.service_key = DATA_GO_KR_SERVICE_KEY
        self.lookback_days = D2B_BID_LOOKBACK_DAYS
        self.page_size = D2B_BID_PAGE_SIZE
        self.base_endpoint = D2B_BID_BASE_ENDPOINT or DEFAULT_D2B_BID_BASE_ENDPOINT
        self.domestic_endpoint = D2B_BID_DOMESTIC_ENDPOINT or DEFAULT_D2B_BID_DOMESTIC_ENDPOINT
        self.foreign_endpoint = D2B_BID_FOREIGN_ENDPOINT
        self.public_private_endpoint = D2B_BID_PUBLIC_PRIVATE_ENDPOINT

    def get_source_type(self) -> str:
        return "bid"

    def get_source_name(self) -> str:
        return "D2B"

    def collect(self) -> list[dict]:
        if not self.service_key:
            raise RuntimeError(".env에 DATA_GO_KR_SERVICE_KEY를 설정하세요.")
        if not self.domestic_endpoint:
            raise RuntimeError("D2B 입찰공고 endpoint가 필요합니다. scripts/probe_d2b_bid_api.py로 확인하세요.")

        start, end = self._date_range()
        endpoints = [("국내 경쟁입찰공고", self.domestic_endpoint)]
        if self.foreign_endpoint:
            endpoints.append(("국외 경쟁입찰공고", self.foreign_endpoint))
        if self.public_private_endpoint:
            endpoints.append(("공개수의 협상계획", self.public_private_endpoint))

        matched: list[dict] = []
        for category, endpoint in endpoints:
            matched.extend(self._collect_endpoint(category, endpoint, start, end))
        return matched

    def _collect_endpoint(self, category: str, endpoint: str, start: str, end: str) -> list[dict]:
        page_no = 1
        total_pages = 1
        matched: list[dict] = []

        while page_no <= min(total_pages, MAX_D2B_BID_PAGES):
            payload = self._request(endpoint, page_no, start, end)
            total_count, items = self._extract_payload(payload)
            total_pages = max(1, math.ceil(total_count / max(self.page_size, 1)))

            for item in items:
                raw_item = self._to_raw_item(category, item)
                if self._is_relevant(raw_item):
                    matched.append(raw_item)

            page_no += 1
        return matched

    def _request(self, endpoint: str, page_no: int, start: str, end: str) -> dict:
        params = {
            "serviceKey": self.service_key,
            "numOfRows": self.page_size,
            "pageNo": page_no,
            D2B_BID_DATE_BEGIN_PARAM: start,
            D2B_BID_DATE_END_PARAM: end,
        }
        response = requests.get(endpoint, params=params, timeout=20)
        response.raise_for_status()
        text = response.text.strip()
        if not text:
            raise RuntimeError("D2B 입찰공고 API가 빈 응답을 반환했습니다.")
        if text.startswith("{"):
            try:
                return response.json()
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"D2B 입찰공고 API JSON 파싱 실패: {text[:300]}") from exc
        xml_text = response.content.decode(response.encoding or "utf-8", errors="replace")
        return self._parse_xml(xml_text)

    def _parse_xml(self, content: str) -> dict:
        content = re.sub(r"^\s*<\?xml[^>]*\?>", "", content).strip()
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise RuntimeError(f"D2B 입찰공고 API XML 파싱 실패: {content[:300]}") from exc

        result_code = self._find_text(root, "resultCode")
        result_msg = self._find_text(root, "resultMsg") or self._find_text(root, "resultMag")
        if result_code and result_code not in ("00", "0"):
            extra = ""
            if result_code == "30":
                extra = " 활용신청 승인 상태, DATA_GO_KR_SERVICE_KEY 값, 인코딩/디코딩 키 선택을 확인하세요."
            raise RuntimeError(f"D2B 입찰공고 API 오류: {result_code} {result_msg}.{extra}".strip())

        items = []
        for item_node in self._iter_local(root, "item"):
            item = {self._local_name(child.tag): (child.text or "").strip() for child in list(item_node)}
            if item:
                items.append(item)
        return {
            "resultCode": result_code,
            "resultMsg": result_msg,
            "totalCount": self._to_int(self._find_text(root, "totalCount")),
            "items": items,
        }

    def _extract_payload(self, payload: dict) -> tuple[int, list[dict]]:
        if "response" in payload:
            header = payload.get("response", {}).get("header", {})
            result_code = str(header.get("resultCode", ""))
            if result_code and result_code not in ("00", "0"):
                result_msg = header.get("resultMsg") or header.get("resultMag") or ""
                raise RuntimeError(f"D2B 입찰공고 API 오류: {result_code} {result_msg}".strip())
            body = payload.get("response", {}).get("body", {})
            total_count = self._to_int(body.get("totalCount"))
            items = body.get("items", [])
        else:
            total_count = self._to_int(payload.get("totalCount"))
            items = payload.get("items", [])

        if isinstance(items, dict):
            item = items.get("item", items)
            items = item if isinstance(item, list) else [item]
        if not isinstance(items, list):
            items = []
        return total_count, [item for item in items if isinstance(item, dict)]

    def _to_raw_item(self, category: str, item: dict[str, Any]) -> dict:
        title = self._pick(item, "bidNm", "bidName", "bidPblancNm", "pblancNm")
        bid_no = self._pick(item, "bidNo", "bidNum", "pblancNo", "g2bPblancNo")
        notice_no = self._pick(item, "pblancNo", "g2bPblancNo", "bidNo", "bidNum")
        notice_order = self._pick(item, "pblancOdr", "bidOdr", "g2bPblancNoOdr")
        organization = self._pick(item, "ornt", "orntNm", "orntCode", "orderInsttNm")
        posted_at = self._pick(item, "pblancDate", "anmtDate", "bidPblancDate", "bidNtceDate")
        registration_deadline = self._pick(
            item,
            "bidPartcptRegistClosDt",
            "bidPartcptRegistClseDttm",
            "bidRegistClseDttm",
            "rgstClseDttm",
        )
        submission_deadline = self._pick(
            item,
            "biddocPresentnClosDt",
            "bidDcPeoClseDttm",
            "bidSubmitClseDttm",
            "bidClseDttm",
        )
        opening_datetime = self._pick(item, "opengDt", "opengDttm", "opengDate", "openDttm")
        amount = self._pick(item, "bsicExpt", "budgetAmount", "bdgtAmount", "presmptPrce", "bssamt")
        contract_method = self._pick(item, "cntrctMth", "cntrctMthNm", "contractMethod")
        bid_method = self._pick(item, "bidStle", "bidMth", "bidMthNm", "bidMethod")
        business_type = self._pick(item, "busiDivs", "excutTy", "bsnsSe", "jobSe", "workSe", "bidJobGb")
        demand_year = self._pick(item, "demandYear", "dmndYear", "reqYr")
        progress_status = self._pick(item, "pblancSe", "progrsSttus", "progressStatus", "bidProgrsStatus")
        due_at = submission_deadline or registration_deadline
        description = " ".join(str(value or "") for value in item.values())
        summary = (
            f"공고번호: {bid_no or notice_no or '-'}; 요구년도: {demand_year or '-'}; 발주기관: {organization or '-'}; "
            f"계약방법: {contract_method or '-'}; 입찰방법: {bid_method or '-'}; 업무구분: {business_type or category or '-'}; "
            f"등록마감: {registration_deadline or '-'}; 입찰서제출마감: {submission_deadline or '-'}; 개찰일시: {opening_datetime or '-'}"
        )

        return {
            "source_type": self.get_source_type(),
            "source_name": self.get_source_name(),
            "category": category,
            "title": title,
            "organization": organization,
            "posted_at": posted_at,
            "due_at": due_at,
            "amount": amount,
            "region": organization,
            "url": self._build_notice_url(bid_no or notice_no),
            "summary": summary,
            "raw": item,
            "bid_no": bid_no,
            "notice_no": notice_no,
            "source_record_id": notice_no or bid_no,
            "source_record_no": notice_order,
            "bid_name": title,
            "demand_year": demand_year,
            "contract_method": contract_method,
            "bid_method": bid_method,
            "business_type": business_type,
            "registration_deadline": registration_deadline,
            "bid_submission_deadline": submission_deadline,
            "opening_datetime": opening_datetime,
            "progress_status": progress_status,
            "description": description,
            "relevance_score": calculate_d2b_bid_relevance(
                {
                    "title": title,
                    "summary": summary,
                    "description": description,
                    "organization": organization,
                    "business_type": business_type,
                    "registration_deadline": registration_deadline,
                    "bid_submission_deadline": submission_deadline,
                }
            ),
        }

    def _is_relevant(self, raw_item: dict) -> bool:
        haystack = f"{raw_item.get('title') or ''} {raw_item.get('summary') or ''}".lower()
        if not any(keyword.lower() in haystack for keyword in DEFAULT_KEYWORDS):
            return False
        return calculate_d2b_bid_relevance(raw_item) > 0

    def _date_range(self) -> tuple[str, str]:
        today = date.today()
        start = today - timedelta(days=self.lookback_days)
        return start.strftime("%Y%m%d"), today.strftime("%Y%m%d")

    def _build_notice_url(self, bid_no: str) -> str:
        if bid_no:
            return f"{D2B_SEARCH_URL}?bidNo={bid_no}"
        return D2B_SEARCH_URL

    def _find_text(self, root: ET.Element, tag: str) -> str:
        for node in root.iter():
            if self._local_name(node.tag) == tag:
                return (node.text or "").strip()
        return ""

    def _iter_local(self, root: ET.Element, tag: str):
        for node in root.iter():
            if self._local_name(node.tag) == tag:
                yield node

    def _local_name(self, tag: str) -> str:
        return tag.split("}", 1)[-1]

    def _pick(self, item: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = item.get(key)
            if value not in (None, ""):
                return str(value).strip()
        return ""

    def _to_int(self, value: Any) -> int:
        try:
            return int(str(value or "0").replace(",", ""))
        except ValueError:
            return 0


def calculate_d2b_bid_relevance(raw_item: dict) -> float:
    title = str(raw_item.get("title") or "")
    summary = str(raw_item.get("summary") or "")
    business_type = str(raw_item.get("business_type") or raw_item.get("category") or "")
    organization = str(raw_item.get("organization") or "")
    score = 0

    if any(keyword.lower() in title.lower() for keyword in D2B_DIRECT_KEYWORDS):
        score += 10
    if any(keyword.lower() in title.lower() for keyword in D2B_FACILITY_KEYWORDS):
        score += 6
    if any(keyword in business_type for keyword in ("시설", "시설공사")):
        score += 5
    if raw_item.get("bid_submission_deadline") or raw_item.get("registration_deadline"):
        score += 2
    if any(keyword in organization for keyword in D2B_DEFENSE_ORGANIZATION_KEYWORDS):
        score += 2

    keyword_haystack = f"{title} {summary}".lower()
    if not any(keyword.lower() in keyword_haystack for keyword in DEFAULT_KEYWORDS):
        return 0.0
    return float(min(score, 100))
