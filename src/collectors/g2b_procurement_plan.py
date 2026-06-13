from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
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


OFFICIAL_BASE_ENDPOINT = "https://apis.data.go.kr/1230000/ao/OrderPlanSttusService"
LEGACY_TYPO_BASE_ENDPOINT = "https://apis.data.go.kr/1230000/ao/OrderPlanStusService"
OFFICIAL_OPERATIONS = {
    "물품": ("getOrderPlanSttusListThngPPSSrch", "getOrderPlanSttusListThng"),
    "용역": ("getOrderPlanSttusListServcPPSSrch", "getOrderPlanSttusListServc"),
    "공사": ("getOrderPlanSttusListCnstwkPPSSrch", "getOrderPlanSttusListCnstwk"),
    "외자": ("getOrderPlanSttusListFrgcptPPSSrch", "getOrderPlanSttusListFrgcpt"),
}
G2B_PORTAL_URL = "https://www.g2b.go.kr"
MAX_PAGES = 3


class G2BProcurementPlanCollector(BaseCollector):
    def __init__(self) -> None:
        self.service_key = DATA_GO_KR_SERVICE_KEY
        self.lookahead_months = max(1, G2B_PLAN_LOOKAHEAD_MONTHS)
        self.page_size = max(1, G2B_PLAN_PAGE_SIZE)
        self.keyword = G2B_PLAN_TITLE_KEYWORD or "모듈러"
        self.base_endpoint = self._official_base_endpoint(G2B_PLAN_BASE_ENDPOINT)
        self.endpoints = self._build_endpoints()

    def get_source_type(self) -> str:
        return "procurement_plan"

    def get_source_name(self) -> str:
        return "나라장터"

    def collect(self) -> list[dict]:
        if not self.service_key:
            raise RuntimeError(".env에 DATA_GO_KR_SERVICE_KEY를 설정하세요.")

        date_range = self._date_range()
        results: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        successful_business_types = 0
        errors: list[str] = []

        for business_type, endpoint_candidates in self.endpoints:
            try:
                items = self._collect_candidates(endpoint_candidates, business_type, date_range)
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
        if not results:
            print("나라장터 발주계획 API 정상 호출, 조회기간 내 모듈러 매칭 0건")
        return results

    def _build_endpoints(self) -> list[tuple[str, list[str]]]:
        configured = {
            "물품": G2B_PLAN_GOODS_ENDPOINT,
            "용역": G2B_PLAN_SERVICE_ENDPOINT,
            "공사": G2B_PLAN_CONSTRUCTION_ENDPOINT,
            "외자": G2B_PLAN_FOREIGN_ENDPOINT,
        }
        endpoints: list[tuple[str, list[str]]] = []
        for business_type in ("물품", "용역", "공사"):
            override = configured[business_type].strip()
            if override:
                endpoints.append((business_type, [override]))
                continue
            operations = OFFICIAL_OPERATIONS[business_type]
            endpoints.append((business_type, [f"{self.base_endpoint}/{operation}" for operation in operations]))
        if configured["외자"].strip():
            endpoints.append(("외자", [configured["외자"].strip()]))
        return endpoints

    def _collect_candidates(
        self,
        endpoints: list[str],
        business_type: str,
        date_range: dict[str, str],
    ) -> list[dict]:
        errors: list[str] = []
        had_successful_call = False
        for endpoint in endpoints:
            try:
                matched = self._collect_endpoint(endpoint, business_type, date_range)
                had_successful_call = True
                if matched:
                    return matched
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else "unknown"
                errors.append(f"{self._operation_name(endpoint)} HTTP {status}")
                continue
            except RuntimeError as exc:
                errors.append(f"{self._operation_name(endpoint)} {exc}")
                continue
        if had_successful_call:
            return []
        raise RuntimeError("공식 operation 호출 실패: " + "; ".join(errors))

    def _collect_endpoint(
        self,
        endpoint: str,
        business_type: str,
        date_range: dict[str, str],
    ) -> list[dict]:
        matched: list[dict] = []
        total_pages = 1
        page_no = 1
        while page_no <= min(total_pages, MAX_PAGES):
            payload = self._request(endpoint, page_no, date_range)
            total_count, rows = self._extract_payload(payload)
            total_pages = max(1, math.ceil(total_count / self.page_size))
            operation = self._operation_name(endpoint)
            for row in rows:
                raw_item = self._to_raw_item(row, business_type, operation)
                if self._is_modular(raw_item):
                    matched.append(raw_item)
            page_no += 1
        return matched

    def _request(self, endpoint: str, page_no: int, date_range: dict[str, str]) -> dict:
        params: dict[str, Any] = {
            "serviceKey": self.service_key,
            "pageNo": page_no,
            "numOfRows": self.page_size,
            "type": "json",
        }
        if endpoint.endswith("PPSSrch"):
            params.update(
                {
                    "orderBgnYm": date_range["order_begin_month"],
                    "orderEndYm": date_range["order_end_month"],
                    "inqryBgnDt": date_range["inquiry_begin_datetime"],
                    "inqryEndDt": date_range["inquiry_end_datetime"],
                    "bizNm": self.keyword,
                }
            )
        else:
            params.update(
                {
                    "inqryDiv": "1",
                    "orderBgnYm": date_range["order_begin_month"],
                    "orderEndYm": date_range["order_end_month"],
                }
            )

        response: requests.Response | None = None
        for service_key in self._key_values():
            response = requests.get(endpoint, params={**params, "serviceKey": service_key}, timeout=30)
            upper = response.text.upper()
            if response.status_code not in {401, 403} and "SERVICE KEY IS NOT REGISTERED" not in upper:
                break
        assert response is not None

        if response.status_code in {401, 403} or "SERVICE KEY IS NOT REGISTERED" in response.text.upper():
            raise RuntimeError(
                "AUTH_ERROR: 활용신청, DATA_GO_KR_SERVICE_KEY, Encoding/Decoding 키를 확인하세요."
            )
        if response.status_code == 404:
            raise requests.HTTPError("NOT_FOUND_OPERATION", response=response)
        response.raise_for_status()

        text = response.text.strip()
        if not text:
            raise RuntimeError("PARSE_ERROR: 빈 응답")
        if text.startswith(("{", "[")):
            try:
                return response.json()
            except (json.JSONDecodeError, ValueError) as exc:
                raise RuntimeError(f"PARSE_ERROR: JSON 파싱 실패: {text[:300]}") from exc
        return self._parse_xml(text)

    def _parse_xml(self, content: str) -> dict:
        content = re.sub(r"^\s*<\?xml[^>]*\?>", "", content).strip()
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise RuntimeError(f"PARSE_ERROR: XML 파싱 실패: {content[:300]}") from exc

        result_code = self._find_text(root, "resultCode")
        result_msg = self._find_text(root, "resultMsg") or self._find_text(root, "resultMag")
        self._raise_api_error(result_code, result_msg)
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
        result_msg = str(
            header.get("resultMsg")
            or header.get("resultMag")
            or payload.get("resultMsg")
            or payload.get("resultMag")
            or ""
        )
        self._raise_api_error(result_code, result_msg)

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

    def _raise_api_error(self, result_code: str, result_msg: str) -> None:
        code = str(result_code or "").strip()
        message = str(result_msg or "").strip()
        if not code or code in {"0", "00"} or "NORMAL SERVICE" in message.upper():
            return
        upper = f"{code} {message}".upper()
        if code in {"10", "20", "30", "31", "32"} or "SERVICE KEY" in upper:
            raise RuntimeError(f"AUTH_ERROR: {code} {message}".strip())
        if code in {"11", "12", "22"} or "PARAMETER" in upper or "필수" in message:
            raise RuntimeError(f"PARAM_ERROR: {code} {message}".strip())
        raise RuntimeError(f"API_ERROR: {code} {message}".strip())

    def _to_raw_item(self, item: dict[str, Any], business_type: str, operation: str) -> dict:
        title = self._pick(
            item,
            "bizNm",
            "orderPlanNm",
            "prcrmntObjNm",
            "prdctNm",
            "prdctClsfcNoNm",
            "itemNm",
            "cnstwkNm",
            "servcNm",
        )
        procurement_target = self._pick(
            item,
            "prcrmntObjNm",
            "orderObjNm",
            "prdctNm",
            "itemNm",
            "prdctClsfcNoNm",
        )
        plan_no = self._pick(item, "orderPlanUntyNo", "orderPlanNo", "prcrmntPlanNo", "planNo", "orderPlanId")
        plan_order = self._pick(item, "orderPlanSno", "orderPlanOrd", "orderPlanSn", "seq", "itemNo")
        organization = self._pick(item, "orderInsttNm", "orderInsttName", "ntceInsttNm", "insttNm")
        demand_org = self._pick(
            item,
            "dminsttNm",
            "dmndInsttNm",
            "demandInsttNm",
            "totlmngInsttNm",
            "jrsdctnDivNm",
        )
        posted_at = self._pick(item, "nticeDt", "rgstDt", "regDt", "orderPlanRegDt", "frstRegDt", "pubDt")
        planned_at = self._pick(
            item,
            "orderPrerngeDate",
            "orderPrearngeDate",
            "orderPrerngeYm",
            "orderPrearngeYm",
            "orderPlanDt",
            "orderPlanYm",
            "orderYearMonth",
        )
        if not planned_at:
            year = self._pick(item, "orderYear", "orderPlanYear")
            month = self._pick(item, "orderMnth", "orderMonth", "orderPlanMonth")
            planned_at = f"{year}{month.zfill(2)}" if year and month else year
        amount = self._pick(item, "sumOrderAmt", "totOrderAmt", "orderAmt", "bdgtAmt", "budgetAmt", "estmtAmt")
        contract_method = self._pick(item, "cntrctMthdNm", "contractMethodNm", "cntrctMthNm")
        bid_method = self._pick(item, "bidMthdNm", "bidMethodNm", "bidMthNm", "prcrmntMethd")
        status = self._pick(item, "orderPlanSttusNm", "planSttusNm", "sttusNm")
        if not status:
            status = "입찰공고연계" if self._pick(item, "ntceNticeYn").upper() == "Y" else "발주계획"
        region = self._pick(item, "cnstwkRgnNm", "insttLctNm", "rgnNm", "regionNm", "areaNm")
        business_subtype = self._pick(item, "bsnsTyNm") or "발주계획"
        description = " ".join(str(value or "") for value in item.values())
        display_title = title or procurement_target
        summary = (
            f"발주계획번호: {plan_no or '-'}; 발주예정: {planned_at or '-'}; 업무구분: {business_type}; "
            f"계약방법: {contract_method or '-'}; 입찰방법: {bid_method or '-'}; "
            f"발주기관: {organization or '-'}; 수요기관: {demand_org or '-'}; 예산액: {amount or '-'}"
        )
        return {
            "source_type": self.get_source_type(),
            "source_name": self.get_source_name(),
            "type": "발주계획",
            "category": business_type,
            "business_type": business_type,
            "business_subtype": business_subtype,
            "title": display_title,
            "organization": organization,
            "demand_org": demand_org,
            "posted_at": posted_at,
            "due_at": planned_at,
            "amount": amount,
            "region": region,
            "url": None,
            "source_search_url": G2B_PORTAL_URL,
            "link_type": "unknown",
            "link_status": "unknown",
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
            "operation": operation,
            "operating_scope": "modular_procurement_plan",
            "is_operating_scope": 1,
            "data_quality": "real",
            "relevance_score": self._relevance(display_title, procurement_target, description),
        }

    def _is_modular(self, raw_item: dict) -> bool:
        text = " ".join(
            str(raw_item.get(key) or "")
            for key in ("title", "summary", "description", "organization", "demand_org")
        )
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

    def _date_range(self) -> dict[str, str]:
        today = date.today()
        end = self._add_months(today, self.lookahead_months)
        return {
            "order_begin_month": today.strftime("%Y%m"),
            "order_end_month": end.strftime("%Y%m"),
            "inquiry_begin_datetime": (today - timedelta(days=365)).strftime("%Y%m%d0000"),
            "inquiry_end_datetime": datetime.now().strftime("%Y%m%d2359"),
        }

    def _key_values(self) -> list[str]:
        values = [self.service_key]
        decoded = unquote(self.service_key)
        if decoded != self.service_key:
            values.append(decoded)
        return values

    @staticmethod
    def _official_base_endpoint(configured: str) -> str:
        base = (configured or OFFICIAL_BASE_ENDPOINT).rstrip("/")
        if base == LEGACY_TYPO_BASE_ENDPOINT or base.endswith("/OrderPlanStusService"):
            print(
                "WARNING: G2B_PLAN_BASE_ENDPOINT의 StusService 오타를 공식 SttusService endpoint로 교정합니다."
            )
            return base[: -len("OrderPlanStusService")] + "OrderPlanSttusService"
        return base

    @staticmethod
    def _operation_name(endpoint: str) -> str:
        return endpoint.rstrip("/").rsplit("/", 1)[-1]

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
