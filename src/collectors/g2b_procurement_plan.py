from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any
from urllib.parse import unquote

import requests

from src.collectors.base import BaseCollector
from src.config import (
    DATA_GO_KR_SERVICE_KEY,
    G2B_PLAN_BASE_ENDPOINT,
    G2B_PLAN_CONSTRUCTION_ENDPOINT,
    G2B_PLAN_FOREIGN_ENDPOINT,
    G2B_PLAN_GOODS_ENDPOINT,
    G2B_PLAN_LOOKAHEAD_MONTHS,
    G2B_PLAN_PAGE_SIZE,
    G2B_PLAN_SERVICE_ENDPOINT,
    G2B_PLAN_TITLE_KEYWORD,
)
from src.text_utils import contains_modular_keyword


DEFAULT_BASE_ENDPOINT = "https://apis.data.go.kr/1230000/ao/OrderPlanStusService"
DEFAULT_GOODS_OPERATIONS = ("getOrderPlanStusListThng", "getOrderPlanSttusListThng")
DEFAULT_SERVICE_OPERATIONS = ("getOrderPlanStusListServc", "getOrderPlanSttusListServc")
DEFAULT_CONSTRUCTION_OPERATIONS = ("getOrderPlanStusListCnstwk", "getOrderPlanSttusListCnstwk")
G2B_PORTAL_URL = "https://www.g2b.go.kr"
MAX_PAGES = 3


class G2BProcurementPlanCollector(BaseCollector):
    def __init__(self) -> None:
        self.service_key = DATA_GO_KR_SERVICE_KEY
        self.lookahead_months = max(1, G2B_PLAN_LOOKAHEAD_MONTHS)
        self.page_size = max(1, G2B_PLAN_PAGE_SIZE)
        self.keyword = G2B_PLAN_TITLE_KEYWORD or "모듈러"
        base = (G2B_PLAN_BASE_ENDPOINT or DEFAULT_BASE_ENDPOINT).rstrip("/")
        self.endpoints: list[tuple[str, list[str]]] = [
            ("물품", [G2B_PLAN_GOODS_ENDPOINT] if G2B_PLAN_GOODS_ENDPOINT else [f"{base}/{op}" for op in DEFAULT_GOODS_OPERATIONS]),
            ("용역", [G2B_PLAN_SERVICE_ENDPOINT] if G2B_PLAN_SERVICE_ENDPOINT else [f"{base}/{op}" for op in DEFAULT_SERVICE_OPERATIONS]),
        ]
        if G2B_PLAN_CONSTRUCTION_ENDPOINT:
            self.endpoints.append(("공사", [G2B_PLAN_CONSTRUCTION_ENDPOINT]))
        else:
            self.endpoints.append(("공사", [f"{base}/{op}" for op in DEFAULT_CONSTRUCTION_OPERATIONS]))
        if G2B_PLAN_FOREIGN_ENDPOINT:
            self.endpoints.append(("외자", [G2B_PLAN_FOREIGN_ENDPOINT]))

    def get_source_type(self) -> str:
        return "procurement_plan"

    def get_source_name(self) -> str:
        return "나라장터"

    def collect(self) -> list[dict]:
        if not self.service_key:
            raise RuntimeError(".env에 DATA_GO_KR_SERVICE_KEY를 설정하세요.")

        start_date, end_date = self._date_range()
        results: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        successful_business_types = 0
        errors: list[str] = []
        for business_type, endpoint_candidates in self.endpoints:
            try:
                items = self._collect_candidates(endpoint_candidates, business_type, start_date, end_date, use_keyword=True)
                if not items:
                    items = self._collect_candidates(endpoint_candidates, business_type, start_date, end_date, use_keyword=False)
                successful_business_types += 1
            except Exception as exc:
                errors.append(f"{business_type}: {exc}")
                print(f"WARNING: 나라장터 {business_type} 발주계획 수집 실패: {exc}")
                continue
            for item in items:
                key = (
                    str(item.get("source_record_id") or ""),
                    str(item.get("source_record_no") or ""),
                    business_type,
                )
                if key in seen:
                    continue
                seen.add(key)
                results.append(item)
        if successful_business_types == 0:
            raise RuntimeError("나라장터 발주계획 API 전체 호출 실패: " + " | ".join(errors))
        return results

    def _collect_candidates(
        self,
        endpoints: list[str],
        business_type: str,
        start_date: str,
        end_date: str,
        *,
        use_keyword: bool,
    ) -> list[dict]:
        errors: list[str] = []
        for endpoint in endpoints:
            try:
                return self._collect_endpoint(endpoint, business_type, start_date, end_date, use_keyword=use_keyword)
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else "unknown"
                errors.append(f"{endpoint} HTTP {status}")
                if status != 404:
                    raise
        raise RuntimeError(
            "나라장터 발주계획 operation 경로를 확인할 수 없습니다: " + "; ".join(errors)
        )

    def _collect_endpoint(
        self,
        endpoint: str,
        business_type: str,
        start_date: str,
        end_date: str,
        *,
        use_keyword: bool,
    ) -> list[dict]:
        matched: list[dict] = []
        total_pages = 1
        page_no = 1
        while page_no <= min(total_pages, MAX_PAGES):
            payload = self._request(endpoint, page_no, start_date, end_date, use_keyword=use_keyword)
            total_count, rows = self._extract_payload(payload)
            total_pages = max(1, math.ceil(total_count / self.page_size))
            for row in rows:
                raw_item = self._to_raw_item(row, business_type)
                if self._is_modular(raw_item):
                    matched.append(raw_item)
            page_no += 1
        return matched

    def _request(
        self,
        endpoint: str,
        page_no: int,
        start_date: str,
        end_date: str,
        *,
        use_keyword: bool,
    ) -> dict:
        params: dict[str, Any] = {
            "serviceKey": self.service_key,
            "pageNo": page_no,
            "numOfRows": self.page_size,
            "inqryDiv": "1",
            "inqryBgnDate": start_date,
            "inqryEndDate": end_date,
            "type": "json",
        }
        if use_keyword:
            params["bizNm"] = self.keyword

        responses: list[requests.Response] = []
        key_values = [self.service_key]
        decoded_key = unquote(self.service_key)
        if decoded_key != self.service_key:
            key_values.append(decoded_key)
        for service_key in key_values:
            response = requests.get(endpoint, params={**params, "serviceKey": service_key}, timeout=30)
            responses.append(response)
            auth_text = response.text.upper()
            if response.status_code != 403 and "SERVICE KEY IS NOT REGISTERED" not in auth_text:
                break
        response = responses[-1]
        if response.status_code == 403 or "SERVICE KEY IS NOT REGISTERED" in response.text.upper():
            raise RuntimeError(
                "나라장터 발주계획 API 인증 실패: 활용신청, DATA_GO_KR_SERVICE_KEY, Encoding/Decoding 키를 확인하세요."
            )
        response.raise_for_status()
        text = response.text.strip()
        if not text:
            raise RuntimeError("나라장터 발주계획 API 빈 응답")
        if text.startswith(("{", "[")):
            try:
                return response.json()
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"나라장터 발주계획 JSON 파싱 실패: {text[:300]}") from exc
        return self._parse_xml(text)

    def _parse_xml(self, content: str) -> dict:
        content = re.sub(r"^\s*<\?xml[^>]*\?>", "", content).strip()
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise RuntimeError(f"나라장터 발주계획 XML 파싱 실패: {content[:300]}") from exc

        result_code = self._find_text(root, "resultCode")
        result_msg = self._find_text(root, "resultMsg")
        if result_code and result_code not in {"00", "0"}:
            raise RuntimeError(f"나라장터 발주계획 API 오류: {result_code} {result_msg}".strip())
        items = []
        for node in self._iter_local(root, "item"):
            item = {self._local_name(child.tag): (child.text or "").strip() for child in list(node)}
            if item:
                items.append(item)
        return {
            "resultCode": result_code,
            "resultMsg": result_msg,
            "totalCount": self._to_int(self._find_text(root, "totalCount")),
            "items": items,
        }

    def _extract_payload(self, payload: dict) -> tuple[int, list[dict]]:
        response = payload.get("response", payload)
        header = response.get("header", {}) if isinstance(response, dict) else {}
        result_code = str(header.get("resultCode") or payload.get("resultCode") or "")
        result_msg = str(header.get("resultMsg") or payload.get("resultMsg") or "")
        if result_code and result_code not in {"00", "0"}:
            raise RuntimeError(f"나라장터 발주계획 API 오류: {result_code} {result_msg}".strip())

        body = response.get("body", {}) if isinstance(response, dict) else {}
        total_count = self._to_int(body.get("totalCount") or payload.get("totalCount"))
        items: Any = body.get("items") or payload.get("items") or []
        if isinstance(items, dict):
            items = items.get("item", items)
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            items = []
        return total_count, [item for item in items if isinstance(item, dict)]

    def _to_raw_item(self, item: dict[str, Any], business_type: str) -> dict:
        title = self._pick(item, "bizNm", "orderPlanNm", "prcrmntObjNm", "prdctNm", "prdctClsfcNoNm", "itemNm")
        procurement_target = self._pick(item, "prcrmntObjNm", "orderObjNm", "prdctNm", "itemNm")
        plan_no = self._pick(item, "orderPlanUntyNo", "orderPlanNo", "prcrmntPlanNo", "planNo", "orderPlanId")
        plan_order = self._pick(item, "orderPlanOrd", "orderPlanSn", "seq", "itemNo")
        organization = self._pick(item, "orderInsttNm", "orderInsttName", "ntceInsttNm", "insttNm")
        demand_org = self._pick(item, "dminsttNm", "dmndInsttNm", "demandInsttNm")
        posted_at = self._pick(item, "rgstDt", "regDt", "orderPlanRegDt", "frstRegDt")
        planned_at = self._pick(item, "orderPrerngeDate", "orderPrearngeDate", "orderPrerngeYm", "orderPrearngeYm", "orderYearMonth")
        if not planned_at:
            year = self._pick(item, "orderYear", "orderPlanYear")
            month = self._pick(item, "orderMonth", "orderPlanMonth")
            planned_at = f"{year}{month.zfill(2)}" if year and month else year
        amount = self._pick(item, "sumOrderAmt", "orderAmt", "bdgtAmt", "budgetAmt", "estmtAmt")
        contract_method = self._pick(item, "cntrctMthdNm", "contractMethodNm", "cntrctMthNm")
        bid_method = self._pick(item, "bidMthdNm", "bidMethodNm", "bidMthNm")
        status = self._pick(item, "orderPlanSttusNm", "planSttusNm", "sttusNm") or "계획등록"
        region = self._pick(item, "rgnNm", "regionNm", "areaNm")
        description = " ".join(str(value or "") for value in item.values())
        summary = (
            f"발주계획번호: {plan_no or '-'}; 발주예정: {planned_at or '-'}; 업무구분: {business_type}; "
            f"계약방법: {contract_method or '-'}; 입찰방법: {bid_method or '-'}; "
            f"발주기관: {organization or '-'}; 수요기관: {demand_org or '-'}; 예산액: {amount or '-'}"
        )
        return {
            "source_type": self.get_source_type(),
            "source_name": self.get_source_name(),
            "category": business_type,
            "business_type": business_type,
            "business_subtype": "발주계획",
            "title": title or procurement_target,
            "organization": organization,
            "demand_org": demand_org,
            "posted_at": posted_at,
            "due_at": planned_at,
            "amount": amount,
            "region": region,
            "url": G2B_PORTAL_URL,
            "source_search_url": G2B_PORTAL_URL,
            "link_type": "portal",
            "link_status": "unchecked",
            "summary": summary,
            "description": description,
            "raw": item,
            "plan_no": plan_no,
            "bid_no": plan_no,
            "source_record_id": plan_no,
            "source_record_no": plan_order,
            "notice_status": status,
            "contract_method": contract_method,
            "bid_method": bid_method,
            "operating_scope": "modular_procurement_plan",
            "is_operating_scope": 1,
            "relevance_score": self._relevance(title, procurement_target, description),
        }

    def _is_modular(self, raw_item: dict) -> bool:
        text = " ".join(str(raw_item.get(key) or "") for key in ("title", "summary", "description", "organization", "demand_org"))
        return contains_modular_keyword(text, self.keyword)

    def _relevance(self, title: str, procurement_target: str, description: str) -> float:
        score = 0
        if contains_modular_keyword(title, self.keyword):
            score += 10
        if contains_modular_keyword(procurement_target, self.keyword):
            score += 6
        if contains_modular_keyword(description, self.keyword):
            score += 2
        return float(score)

    def _date_range(self) -> tuple[str, str]:
        today = date.today()
        end = self._add_months(today, self.lookahead_months)
        return today.strftime("%Y%m%d"), end.strftime("%Y%m%d")

    @staticmethod
    def _add_months(value: date, months: int) -> date:
        month = value.month - 1 + months
        return date(value.year + month // 12, month % 12 + 1, 1)

    @staticmethod
    def _pick(item: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = item.get(key)
            if value not in (None, ""):
                return str(value).strip()
        return ""

    @staticmethod
    def _to_int(value: Any) -> int:
        try:
            return int(str(value or "0").replace(",", ""))
        except ValueError:
            return 0

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.split("}", 1)[-1]

    def _find_text(self, root: ET.Element, tag: str) -> str:
        for node in root.iter():
            if self._local_name(node.tag) == tag:
                return (node.text or "").strip()
        return ""

    def _iter_local(self, root: ET.Element, tag: str):
        for node in root.iter():
            if self._local_name(node.tag) == tag:
                yield node
