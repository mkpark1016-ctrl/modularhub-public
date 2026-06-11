from __future__ import annotations

import math
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any

import requests
from requests.exceptions import SSLError

from src.collectors.base import BaseCollector
from src.config import DATA_GO_KR_SERVICE_KEY, LH_LOOKBACK_DAYS, LH_OPENBID_ENDPOINT, LH_PAGE_SIZE
from src.keywords import DEFAULT_KEYWORDS


DEFAULT_LH_OPENBID_ENDPOINT = "https://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
LH_SEARCH_URL = "https://ebid.lh.or.kr/"
LH_DIRECT_KEYWORDS = ["모듈러", "OSC", "공업화주택"]
LH_CONTEXT_KEYWORDS = ["기숙사", "학교", "임시교사", "군간부숙소", "병영생활관"]
RESULT_30_HINT = "승인 상태가 아니라면 활용신청 필요, 승인 상태라면 endpoint/인증키 전달 방식 점검 필요"


class LHCollector(BaseCollector):
    def __init__(self) -> None:
        self.service_key = DATA_GO_KR_SERVICE_KEY
        self.lookback_days = LH_LOOKBACK_DAYS
        self.page_size = LH_PAGE_SIZE
        self.endpoint = LH_OPENBID_ENDPOINT or DEFAULT_LH_OPENBID_ENDPOINT

    def get_source_type(self) -> str:
        return "bid"

    def get_source_name(self) -> str:
        return "LH"

    def collect(self) -> list[dict]:
        if not self.service_key:
            raise RuntimeError(".env에 DATA_GO_KR_SERVICE_KEY를 설정하세요.")

        start_dt = datetime.now() - timedelta(days=self.lookback_days)
        end_dt = datetime.now()
        start = start_dt.strftime("%Y%m%d")
        end = end_dt.strftime("%Y%m%d")
        page_no = 1
        total_pages = 1
        matched: list[dict] = []

        while page_no <= total_pages:
            payload = self._request(page_no, start, end)
            total_count, items = self._extract_payload(payload)
            total_pages = max(1, math.ceil(total_count / max(self.page_size, 1)))

            for item in items:
                raw_item = self._to_raw_item(item)
                if self._is_relevant(raw_item):
                    matched.append(raw_item)

            page_no += 1

        return matched

    def _request(self, page_no: int, start: str, end: str) -> dict:
        params = {
            "serviceKey": self.service_key,
            "numOfRows": self.page_size,
            "pageNo": page_no,
            "tndrbidRegDtStart": start,
            "tndrbidRegDtEnd": end,
        }
        response = self._get_with_retries(params)
        response.raise_for_status()

        text = response.text.strip()
        if not text:
            raise RuntimeError("LH API 빈 응답")
        if text.startswith("{"):
            try:
                return response.json()
            except ValueError as exc:
                raise RuntimeError(f"LH API JSON 파싱 실패: {text[:300]}") from exc

        xml_text = response.content.decode(response.encoding or "utf-8", errors="replace")
        return self._parse_xml(xml_text)

    def _response_result_code(self, response: requests.Response) -> str:
        text = response.content.decode(response.encoding or "utf-8", errors="replace")
        match = re.search(r"<resultCode>\s*([^<]+)\s*</resultCode>", text)
        return match.group(1).strip() if match else ""

    def _get_with_retries(self, params: dict) -> requests.Response:
        endpoints = [self.endpoint]
        if self.endpoint.startswith("https://openapi.ebid.lh.or.kr/"):
            endpoints.append(self.endpoint.replace("https://", "http://", 1))

        last_response: requests.Response | None = None
        last_ssl_error: SSLError | None = None
        for endpoint in endpoints:
            for attempt in range(3):
                try:
                    response = requests.get(endpoint, params=params, timeout=30)
                except SSLError as exc:
                    last_ssl_error = exc
                    break

                last_response = response
                if self._response_result_code(response) != "30":
                    return response
                time.sleep(0.5 * (attempt + 1))

        if last_response is not None:
            return last_response
        if last_ssl_error is not None:
            raise last_ssl_error
        raise RuntimeError("LH API 요청 실패")

    def _parse_xml(self, content: str) -> dict:
        content = re.sub(r"^\s*<\?xml[^>]*\?>", "", content).strip()
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise RuntimeError(f"LH API XML 파싱 실패: {content[:300]}") from exc

        result_code = self._find_text(root, "resultCode")
        result_msg = self._find_text(root, "resultMsg").rstrip(".")
        if result_code and result_code not in ("00", "0"):
            hint = f" {RESULT_30_HINT}" if result_code == "30" else ""
            raise RuntimeError(f"LH API 오류: {result_code} {result_msg}.{hint}".strip())

        total_count = self._to_int(self._find_text(root, "totalCount"))
        items = []
        for item_node in self._iter_local(root, "item"):
            item = {self._local_name(child.tag): (child.text or "").strip() for child in list(item_node)}
            if item:
                items.append(item)
        return {"totalCount": total_count, "items": items}

    def _extract_payload(self, payload: dict) -> tuple[int, list[dict]]:
        if "response" in payload:
            header = payload.get("response", {}).get("header", {})
            result_code = str(header.get("resultCode", ""))
            if result_code and result_code not in ("00", "0"):
                result_msg = str(header.get("resultMsg", "")).rstrip(".")
                hint = f" {RESULT_30_HINT}" if result_code == "30" else ""
                raise RuntimeError(f"LH API 오류: {result_code} {result_msg}.{hint}".strip())
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

    def _to_raw_item(self, item: dict[str, Any]) -> dict:
        bid_no = self._pick(item, "bidNum")
        title = self._pick(item, "bidnmKor", "bidnmEng")
        category = self._pick(item, "cstrtnJobGbNm", "bidKind")
        organization = self._pick(item, "zoneHqCd") or "한국토지주택공사"
        posted_at = self._pick(item, "tndrbidRegDt")
        due_at = self._pick(item, "tndrdocAcptEndDtm", "openDtm", "cooperdocAcptEndDtm")
        amount = self._pick(item, "fdmtlAmt", "presmtPrc", "designPrc")
        region = self._join_regions(item)
        base_amount = self._pick(item, "fdmtlAmt")
        estimate_amount = self._pick(item, "presmtPrc")
        contract_method = self._pick(item, "tndrCtrctMedCd")
        status = self._pick(item, "bidProgrsStatus")
        summary = (
            f"공고번호: {bid_no or '-'}; 업무구분: {category or '-'}; 담당지역: {region or organization or '-'}; "
            f"추정가격: {estimate_amount or '-'}; 기초금액: {base_amount or '-'}; "
            f"계약유형: {contract_method or '-'}; 진행상태: {status or '-'}"
        )

        return {
            "source_type": self.get_source_type(),
            "source_name": self.get_source_name(),
            "category": category,
            "bid_no": bid_no,
            "bidNum": bid_no,
            "title": title,
            "organization": organization,
            "posted_at": posted_at,
            "due_at": due_at,
            "amount": amount,
            "region": region or organization,
            "url": self._build_notice_url(bid_no),
            "summary": summary,
            "description": " ".join(str(value or "") for value in item.values()),
            "source_record_id": bid_no,
            "source_record_no": "",
            "relevance_score": calculate_lh_relevance(
                {
                    "title": title,
                    "organization": organization,
                    "region": region,
                    "summary": summary,
                    "description": " ".join(str(value or "") for value in item.values()),
                    "amount": amount,
                }
            ),
            "raw": item,
        }

    def _is_relevant(self, raw_item: dict) -> bool:
        haystack = " ".join(
            str(raw_item.get(key) or "")
            for key in ("title", "organization", "region", "summary", "description")
        ).lower()
        return any(keyword.lower() in haystack for keyword in DEFAULT_KEYWORDS)

    def _join_regions(self, item: dict[str, Any]) -> str:
        regions = [
            self._pick(item, "zoneRstrct1"),
            self._pick(item, "zoneRstrct2"),
            self._pick(item, "zoneRstrct3"),
            self._pick(item, "zoneRstrct4"),
        ]
        return ";".join(region for region in regions if region)

    def _build_notice_url(self, bid_no: str) -> str:
        if bid_no:
            return f"{LH_SEARCH_URL}ebid.et.tp.cmd.BidListCmd.dev?bidNum={bid_no}"
        return LH_SEARCH_URL

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


def calculate_lh_relevance(raw_item: dict) -> float:
    title = str(raw_item.get("title") or "")
    organization_region = " ".join(str(raw_item.get(key) or "") for key in ("organization", "region"))
    details = " ".join(str(raw_item.get(key) or "") for key in ("summary", "description"))
    score = 0

    if any(keyword.lower() in title.lower() for keyword in LH_DIRECT_KEYWORDS):
        score += 10
    if any(keyword.lower() in title.lower() for keyword in LH_CONTEXT_KEYWORDS):
        score += 5
    if any(keyword.lower() in organization_region.lower() for keyword in ("lh", "한국토지주택공사", "본사")):
        score += 2
    for keyword in DEFAULT_KEYWORDS:
        if keyword.lower() in details.lower():
            score += 1
    if raw_item.get("amount"):
        score += 1

    return float(min(score, 100))
