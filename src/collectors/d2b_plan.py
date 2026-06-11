from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any

import requests

from src.collectors.base import BaseCollector
from src.config import (
    D2B_LOOKAHEAD_MONTHS,
    D2B_PAGE_SIZE,
    D2B_PLAN_BASE_ENDPOINT,
    D2B_PLAN_DOMESTIC_ENDPOINT,
    D2B_PLAN_FACILITY_ENDPOINT,
    DATA_GO_KR_SERVICE_KEY,
)
from src.keywords import D2B_ACTIVE_STATUS_KEYWORDS, D2B_DIRECT_KEYWORDS, D2B_FACILITY_KEYWORDS, DEFAULT_KEYWORDS


DEFAULT_D2B_PLAN_BASE_ENDPOINT = "https://openapi.d2b.go.kr/openapi/service/PrcurePlanInfoService"
DEFAULT_D2B_PLAN_DOMESTIC_ENDPOINT = (
    "http://openapi.d2b.go.kr/openapi/service/PrcurePlanInfoService/getDmstcPrcurePlanList"
)
D2B_SEARCH_URL = "https://www.d2b.go.kr/"
MAX_D2B_PAGES = 3


class D2BPlanCollector(BaseCollector):
    def __init__(self) -> None:
        self.service_key = DATA_GO_KR_SERVICE_KEY
        self.lookahead_months = D2B_LOOKAHEAD_MONTHS
        self.page_size = D2B_PAGE_SIZE
        self.base_endpoint = D2B_PLAN_BASE_ENDPOINT or DEFAULT_D2B_PLAN_BASE_ENDPOINT
        self.domestic_endpoint = D2B_PLAN_DOMESTIC_ENDPOINT or DEFAULT_D2B_PLAN_DOMESTIC_ENDPOINT
        self.facility_endpoint = D2B_PLAN_FACILITY_ENDPOINT

    def get_source_type(self) -> str:
        return "procurement_plan"

    def get_source_name(self) -> str:
        return "D2B"

    def collect(self) -> list[dict]:
        if not self.service_key:
            raise RuntimeError(".env에 DATA_GO_KR_SERVICE_KEY를 설정하세요.")

        begin, end = self._month_range()
        endpoints = [("국내 조달계획", self.domestic_endpoint)]
        if self.facility_endpoint:
            endpoints.append(("시설 조달계획", self.facility_endpoint))

        matched: list[dict] = []
        for category, endpoint in endpoints:
            matched.extend(self._collect_endpoint(category, endpoint, begin, end))
        return matched

    def _collect_endpoint(self, category: str, endpoint: str, begin: str, end: str) -> list[dict]:
        page_no = 1
        total_pages = 1
        matched: list[dict] = []

        while page_no <= min(total_pages, MAX_D2B_PAGES):
            payload = self._request(endpoint, page_no, begin, end)
            total_count, items = self._extract_payload(payload)
            total_pages = max(1, math.ceil(total_count / max(self.page_size, 1)))

            for item in items:
                raw_item = self._to_raw_item(category, item)
                if self._is_relevant(raw_item):
                    matched.append(raw_item)

            page_no += 1

        return matched

    def _request(self, endpoint: str, page_no: int, begin: str, end: str) -> dict:
        params = {
            "serviceKey": self.service_key,
            "orderPrearngeMtBegin": begin,
            "orderPrearngeMtEnd": end,
            "reprsntPrdlstNm": "",
            "dcsNo": "",
            "numOfRows": self.page_size,
            "pageNo": page_no,
        }
        response = requests.get(endpoint, params=params, timeout=30)
        response.raise_for_status()
        text = response.text.strip()
        if not text:
            raise RuntimeError("D2B 조달계획 API 빈 응답")
        if text.startswith("{"):
            try:
                return response.json()
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"D2B 조달계획 API JSON 파싱 실패: {text[:300]}") from exc
        xml_text = response.content.decode(response.encoding or "utf-8", errors="replace")
        return self._parse_xml(xml_text)

    def _parse_xml(self, content: str) -> dict:
        content = re.sub(r"^\s*<\?xml[^>]*\?>", "", content).strip()
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise RuntimeError(f"D2B 조달계획 API XML 파싱 실패: {content[:300]}") from exc

        result_code = self._find_text(root, "resultCode")
        result_msg = self._find_text(root, "resultMsg") or self._find_text(root, "resultMag")
        if result_code and result_code not in ("00", "0"):
            raise RuntimeError(f"D2B 조달계획 API 오류: {result_code} {result_msg}".strip())

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
                raise RuntimeError(f"D2B 조달계획 API 오류: {result_code} {result_msg}".strip())
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
        title = self._pick(item, "reprsntPrdlstNm", "representPrdlstNm", "prdctNm", "itemNm", "prdlstNm")
        dcs_no = self._pick(item, "dcsNo", "judgmntNo", "dcsnNo")
        order_month = self._pick(item, "orderPrearngeMt", "orderPrerngeMt", "orderMonth", "orderPrearngeYm")
        organization = self._pick(item, "ornt", "orntNm", "orntCode", "orderInsttNm", "orderAgency")
        amount = self._pick(item, "bdgtAmount", "budgetAmount", "bdgtAmt", "budgetAmt", "estmtAmount")
        contract_method = self._pick(item, "cntrctMth", "cntrctMthNm", "contractMethod", "contractMthd")
        bid_method = self._pick(item, "bidMth", "bidMthNm", "bidMethod", "tndrMth")
        progress_status = self._pick(item, "progrsSttus", "progressStatus", "prgrsStts", "sttusNm")
        demand_year = self._pick(item, "dmndYear", "demandYear", "rqestYear", "reqYr")
        execution_type = self._pick(item, "excutTy", "excutTyNm", "execType", "bsnsSe")
        summary = (
            f"판단번호: {dcs_no or '-'}; 발주예정월: {order_month or '-'}; 집행유형: {execution_type or '-'}; "
            f"계약방법: {contract_method or '-'}; 입찰방법: {bid_method or '-'}; "
            f"진행상태: {progress_status or '-'}; 예산금액: {amount or '-'}"
        )
        description = " ".join(str(value or "") for value in item.values())
        relevance = calculate_d2b_relevance(
            {
                "title": title,
                "summary": summary,
                "description": description,
                "amount": amount,
                "execution_type": execution_type,
                "progress_status": progress_status,
            }
        )

        return {
            "source_type": self.get_source_type(),
            "source_name": self.get_source_name(),
            "category": category,
            "title": title,
            "organization": organization,
            "posted_at": order_month,
            "due_at": None,
            "amount": amount,
            "region": organization,
            "url": self._build_notice_url(dcs_no),
            "summary": summary,
            "raw": item,
            "dcs_no": dcs_no,
            "source_record_id": dcs_no,
            "source_record_no": self._pick(item, "itemNo", "seq", "sn", "ord"),
            "order_month": order_month,
            "contract_method": contract_method,
            "bid_method": bid_method,
            "progress_status": progress_status,
            "demand_year": demand_year,
            "description": description,
            "relevance_score": relevance,
        }

    def _is_relevant(self, raw_item: dict) -> bool:
        haystack = " ".join(
            str(raw_item.get(key) or "")
            for key in ("title", "summary", "description", "organization", "category")
        ).lower()
        if not any(keyword.lower() in haystack for keyword in DEFAULT_KEYWORDS):
            return False
        return calculate_d2b_relevance(raw_item) > 0

    def _month_range(self) -> tuple[str, str]:
        today = date.today()
        start = today.strftime("%Y%m")
        end_date = self._add_months(today, self.lookahead_months)
        return start, end_date.strftime("%Y%m")

    def _add_months(self, value: date, months: int) -> date:
        month = value.month - 1 + months
        year = value.year + month // 12
        month = month % 12 + 1
        return date(year, month, 1)

    def _build_notice_url(self, dcs_no: str) -> str:
        if dcs_no:
            return f"{D2B_SEARCH_URL}?dcsNo={dcs_no}"
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


def calculate_d2b_relevance(raw_item: dict) -> float:
    title = str(raw_item.get("title") or "")
    summary = str(raw_item.get("summary") or "")
    description = str(raw_item.get("description") or "")
    execution_type = str(raw_item.get("execution_type") or raw_item.get("category") or "")
    progress_status = str(raw_item.get("progress_status") or "")
    score = 0

    if any(keyword.lower() in title.lower() for keyword in D2B_DIRECT_KEYWORDS):
        score += 10
    if any(keyword.lower() in title.lower() for keyword in D2B_FACILITY_KEYWORDS):
        score += 6
    if any(keyword in execution_type for keyword in ("시설", "공사")):
        score += 5
    if raw_item.get("amount"):
        score += 1
    if any(keyword in progress_status for keyword in D2B_ACTIVE_STATUS_KEYWORDS):
        score += 2

    keyword_haystack = f"{title} {summary} {description}".lower()
    if not any(keyword.lower() in keyword_haystack for keyword in DEFAULT_KEYWORDS):
        return 0.0
    return float(min(score, 100))
