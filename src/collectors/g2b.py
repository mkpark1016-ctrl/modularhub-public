from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

import requests

from src.collectors.base import BaseCollector
from src.config import (
    DATA_GO_KR_SERVICE_KEY,
    G2B_CONSTRUCTION_ENDPOINT,
    G2B_GOODS_ENDPOINT,
    G2B_LOOKBACK_DAYS,
    G2B_PAGE_SIZE,
    G2B_SERVICE_ENDPOINT,
    G2B_SERVICE_SUBTYPE,
)
from src.keywords import DEFAULT_KEYWORDS, DIRECT_RELEVANCE_KEYWORDS, IMPORTANT_ORGANIZATION_KEYWORDS
from src.g2b_detail_url import build_g2b_detail_api_url
from src.text_utils import contains_modular_keyword


DEFAULT_G2B_CONSTRUCTION_ENDPOINT = (
    "http://apis.data.go.kr/1230000/ad/BidPublicInfoService/"
    "getBidPblancListInfoCnstwkPPSSrch"
)
DEFAULT_G2B_SERVICE_ENDPOINT = (
    "http://apis.data.go.kr/1230000/ad/BidPublicInfoService/"
    "getBidPblancListInfoServcPPSSrch"
)
DEFAULT_G2B_GOODS_ENDPOINT = (
    "http://apis.data.go.kr/1230000/ad/BidPublicInfoService/"
    "getBidPblancListInfoThngPPSSrch"
)
G2B_SEARCH_URL = "https://www.g2b.go.kr/"
G2B_MAX_QUERY_WINDOW_DAYS = 7
G2B_MAX_PAGES_PER_WINDOW = 3


class G2BCollector(BaseCollector):
    def __init__(
        self,
        *,
        lookback_days: int | None = None,
        debug_keyword: str | None = None,
        debug_bid_no: str | None = None,
        save_raw_debug: bool = False,
        page_size: int | None = None,
        business_types: list[str] | None = None,
        title_keyword: str | None = None,
        operating_scope: str | None = None,
        service_subtype: str | None = None,
    ) -> None:
        self.service_key = DATA_GO_KR_SERVICE_KEY
        self.lookback_days = lookback_days or G2B_LOOKBACK_DAYS
        self.page_size = page_size or G2B_PAGE_SIZE
        self.construction_endpoint = G2B_CONSTRUCTION_ENDPOINT or DEFAULT_G2B_CONSTRUCTION_ENDPOINT
        self.service_endpoint = G2B_SERVICE_ENDPOINT or DEFAULT_G2B_SERVICE_ENDPOINT
        self.goods_endpoint = G2B_GOODS_ENDPOINT or DEFAULT_G2B_GOODS_ENDPOINT
        self.debug_keyword = debug_keyword
        self.debug_bid_no = debug_bid_no
        self.save_raw_debug = save_raw_debug
        self.business_types = set(business_types or ["공사", "용역", "물품"])
        self.title_keyword = title_keyword
        self.operating_scope = operating_scope
        self.service_subtype = service_subtype or G2B_SERVICE_SUBTYPE

    def get_source_type(self) -> str:
        return "bid"

    def get_source_name(self) -> str:
        return "나라장터"

    def collect(self) -> list[dict]:
        if not self.service_key:
            raise RuntimeError(
                "DATA_GO_KR_SERVICE_KEY가 설정되어 있지 않습니다. "
                ".env 파일에 공공데이터포털 서비스키를 추가하세요."
            )

        results: list[dict] = []
        for category, endpoint in (
            ("공사", self.construction_endpoint),
            ("용역", self.service_endpoint),
            ("물품", self.goods_endpoint),
        ):
            if category in self.business_types:
                results.extend(self._collect_endpoint(category, endpoint))
        return results

    def collect_goods_bids(self) -> list[dict]:
        return self._collect_endpoint("물품", self.goods_endpoint)

    def collect_service_bids(self) -> list[dict]:
        return self._collect_endpoint("용역", self.service_endpoint)

    def collect_modular_goods_and_services(self) -> list[dict]:
        previous_business_types = self.business_types
        previous_title_keyword = self.title_keyword
        previous_operating_scope = self.operating_scope
        try:
            self.business_types = {"물품", "용역"}
            self.title_keyword = self.title_keyword or "모듈러"
            self.operating_scope = self.operating_scope or "modular_goods_service"
            return self.collect_goods_bids() + self.collect_service_bids()
        finally:
            self.business_types = previous_business_types
            self.title_keyword = previous_title_keyword
            self.operating_scope = previous_operating_scope

    def _collect_endpoint(self, category: str, endpoint: str) -> list[dict]:
        if self.title_keyword:
            server_matched = self._collect_endpoint_pages(
                category,
                endpoint,
                extra_params={"bidNtceNm": self.title_keyword},
            )
            if server_matched:
                return server_matched
        return self._collect_endpoint_pages(category, endpoint)

    def _collect_endpoint_pages(
        self,
        category: str,
        endpoint: str,
        extra_params: dict | None = None,
    ) -> list[dict]:
        start_dt = datetime.now() - timedelta(days=self.lookback_days)
        end_dt = datetime.now()
        matched: list[dict] = []

        for window_start, window_end in self._date_windows(start_dt, end_dt):
            begin = window_start.strftime("%Y%m%d") + "0000"
            end = window_end.strftime("%Y%m%d") + "2359"
            page_no = 1
            total_pages = 1

            while page_no <= min(total_pages, G2B_MAX_PAGES_PER_WINDOW):
                payload = self._request(endpoint, page_no, begin, end, extra_params=extra_params)
                body = payload.get("response", {}).get("body", {})
                total_count = int(body.get("totalCount") or 0)
                total_pages = max(1, math.ceil(total_count / max(self.page_size, 1)))
                items = self._extract_items(body)

                for item in items:
                    raw_item = self._to_raw_item(category, item)
                    self._debug_sample(raw_item)
                    if self._is_relevant(raw_item):
                        matched.append(raw_item)

                page_no += 1

        return matched

    def _request(self, endpoint: str, page_no: int, begin: str, end: str, extra_params: dict | None = None) -> dict:
        params = {
            "serviceKey": self.service_key,
            "pageNo": page_no,
            "numOfRows": self.page_size,
            "inqryDiv": "1",
            "inqryBgnDt": begin,
            "inqryEndDt": end,
            "type": "json",
        }
        if extra_params:
            params.update(extra_params)
        response = requests.get(endpoint, params=params, timeout=20)
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"나라장터 API JSON 파싱 실패: {response.text[:300]}") from exc

        header = payload.get("response", {}).get("header", {})
        if not header:
            header = payload.get("nkoneps.com.response.ResponseError", {}).get("header", {})
        result_code = str(header.get("resultCode", ""))
        if result_code and result_code not in ("00", "0"):
            result_msg = header.get("resultMsg") or "unknown API error"
            raise RuntimeError(f"나라장터 API 오류: {result_code} {result_msg}")
        return payload

    def _date_windows(self, start_dt: datetime, end_dt: datetime):
        current = start_dt
        while current <= end_dt:
            window_end = min(current + timedelta(days=G2B_MAX_QUERY_WINDOW_DAYS - 1), end_dt)
            yield current, window_end
            current = window_end + timedelta(days=1)

    def _extract_items(self, body: dict) -> list[dict]:
        items = body.get("items") or []
        if isinstance(items, dict):
            item = items.get("item", items)
            return item if isinstance(item, list) else [item]
        if isinstance(items, list):
            return items
        return []

    def _to_raw_item(self, category: str, item: dict[str, Any]) -> dict:
        title = self._pick(item, "bidNtceNm", "ntceNm", "bidNtceName")
        organization = self._pick(item, "ntceInsttNm", "ntceInsttName")
        demand_org = self._pick(item, "dminsttNm", "dmndInsttNm", "demandInsttNm")
        posted_at = self._pick(item, "bidNtceDt", "ntceDt", "bidNtceDate")
        due_at = self._pick(item, "bidClseDt", "bidClseDate", "opengDt")
        amount = self._pick(item, "presmptPrce", "bssamt", "asignBdgtAmt", "bdgtAmt")
        region = self._pick(item, "prtcptPsblRgnNm", "rgstTyNm", "areaNm")
        detail_name = self._pick(item, "indstrytyNm", "cnstrtsiteRgnNm", "prdctClsfcNoNm", "srvceDivNm")
        contract_method = self._pick(item, "cntrctCnclsMthdNm")
        bid_method = self._pick(item, "bidMethdNm")
        bid_no = self._pick(item, "bidNtceNo")
        bid_ord = self._pick(item, "bidNtceOrd")
        bid_clsfc_no = self._pick(item, "bidClsfcNo")
        rbid_no = self._pick(item, "rbidNo")
        business_division = self._pick(item, "bsnsDivNm") or category
        notice_kind = self._pick(item, "ntceKindNm")
        summary = (
            f"공고번호: {bid_no or '-'}; 공고차수: {bid_ord or '-'}; 업무구분: {category}; "
            f"공고상태: {notice_kind or '-'}; 계약방법: {contract_method or '-'}; 입찰방법: {bid_method or '-'}; "
            f"공고기관: {organization or '-'}; 수요기관: {demand_org or '-'}; 마감일: {due_at or '-'}"
        )
        url = self._pick(item, "bidNtceUrl", "ntceUrl") or self._build_notice_url(bid_no, bid_ord)

        raw_item = {
            "source_type": self.get_source_type(),
            "source_name": self.get_source_name(),
            "category": category,
            "bsnsDivNm": business_division,
            "ntceKindNm": notice_kind,
            "title": title,
            "organization": organization or demand_org,
            "demand_org": demand_org,
            "posted_at": posted_at,
            "due_at": due_at,
            "amount": amount,
            "region": region,
            "url": url,
            "summary": summary,
            "description": f"{summary}; 세부: {detail_name or '-'}",
            "bidNtceNo": bid_no,
            "bidNtceOrd": bid_ord,
            "bidClsfcNo": bid_clsfc_no,
            "rbidNo": rbid_no,
            "bid_no": bid_no,
            "bid_order": bid_ord,
            "notice_status": notice_kind,
            "business_type": category,
            "business_subtype": self._business_subtype(category, item),
            "operating_scope": self.operating_scope,
            "is_operating_scope": 1 if self.operating_scope else 0,
            "is_known_important": 0,
            "contract_method": contract_method,
            "bid_method": bid_method,
            "notice_org": organization,
            "source_record_id": bid_no,
            "source_record_no": bid_ord,
            "relevance_score": calculate_g2b_relevance(
                {
                    "title": title,
                    "organization": organization,
                    "demand_org": demand_org,
                    "summary": summary,
                    "description": detail_name,
                }
            ),
            "raw": item,
        }
        raw_item["source_detail_api_url"] = build_g2b_detail_api_url(raw_item)
        if raw_item["source_detail_api_url"]:
            raw_item["exact_url_candidate"] = raw_item["source_detail_api_url"]
        return raw_item

    def _is_relevant(self, raw_item: dict) -> bool:
        if self.title_keyword and not contains_modular_keyword(raw_item.get("title"), self.title_keyword):
            return False
        haystack = " ".join(
            str(raw_item.get(key) or "")
            for key in ("title", "organization", "demand_org", "summary", "description")
        ).lower()
        return any(keyword.lower() in haystack for keyword in DEFAULT_KEYWORDS)

    def _debug_sample(self, raw_item: dict) -> None:
        if self.debug_bid_no and raw_item.get("source_record_id") == self.debug_bid_no:
            print(
                "[G2B debug bid] "
                f"{raw_item.get('source_record_id')} order={raw_item.get('source_record_no')} "
                f"category={raw_item.get('category')} title={raw_item.get('title')}"
            )
        if self.debug_keyword:
            haystack = " ".join(
                str(raw_item.get(key) or "")
                for key in ("title", "organization", "demand_org", "summary", "description")
            )
            if self.debug_keyword.lower() in haystack.lower():
                print(
                    "[G2B debug keyword] "
                    f"{raw_item.get('source_record_id')} order={raw_item.get('source_record_no')} "
                    f"category={raw_item.get('category')} title={raw_item.get('title')}"
                )

    def _build_notice_url(self, bid_no: str, bid_ord: str) -> str:
        if bid_no:
            return f"{G2B_SEARCH_URL}?bidNtceNo={bid_no}&bidNtceOrd={bid_ord or ''}"
        return G2B_SEARCH_URL

    def _pick(self, item: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = item.get(key)
            if value not in (None, ""):
                return str(value).strip()
        return ""

    def _business_subtype(self, category: str, item: dict[str, Any]) -> str:
        explicit = self._pick(item, "srvceDivNm", "bsnsDivNm", "bidNtceDtlTypeNm")
        if explicit:
            return explicit
        if category == "용역":
            return self.service_subtype or "용역"
        return category or "unknown"


def calculate_g2b_relevance(raw_item: dict) -> float:
    title = str(raw_item.get("title") or "")
    organization = " ".join(str(raw_item.get(key) or "") for key in ("organization", "demand_org"))
    summary = " ".join(str(raw_item.get(key) or "") for key in ("summary", "description"))
    score = 0

    for keyword in DEFAULT_KEYWORDS:
        if keyword.lower() in title.lower():
            score += 5
        if keyword.lower() in summary.lower():
            score += 1

    if any(keyword.lower() in organization.lower() for keyword in IMPORTANT_ORGANIZATION_KEYWORDS):
        score += 2

    if any(keyword.lower() in (title + " " + summary).lower() for keyword in DIRECT_RELEVANCE_KEYWORDS):
        score += 5

    return float(min(score, 100))


def _title_contains_keyword(title: object, keyword: str) -> bool:
    normalized_title = _normalize_for_match(title)
    normalized_keyword = _normalize_for_match(keyword)
    if not normalized_keyword:
        return True
    return normalized_keyword in normalized_title


def _normalize_for_match(value: object) -> str:
    return "".join(str(value or "").lower().split())
