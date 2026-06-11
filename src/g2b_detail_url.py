from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

import requests

from src.config import DATA_GO_KR_SERVICE_KEY, G2B_DETAIL_BASE_ENDPOINT


DETAIL_OPERATIONS = {
    "construction": "getBidPblancDetailInfoCnstwk",
    "service": "getBidPblancDetailInfoServc",
    "goods": "getBidPblancDetailInfoThng",
    "foreign": "getBidPblancDetailInfoFrgcpt",
}
LIST_FALLBACK_OPERATIONS = {
    "construction": "getBidPblancListInfoCnstwkPPSSrch",
    "service": "getBidPblancListInfoServcPPSSrch",
    "goods": "getBidPblancListInfoThngPPSSrch",
}


def get_g2b_detail_operation(item: dict) -> str:
    return get_g2b_operation_kind(item)[1]


def get_g2b_operation_kind(item: dict) -> tuple[str, str]:
    category = str(item.get("category") or item.get("bsnsDivNm") or item.get("업무구분") or "")
    summary = str(item.get("summary") or "")
    haystack = f"{category} {summary}".lower()
    if "공사" in haystack or "cnstwk" in haystack or "construction" in haystack:
        return "construction", DETAIL_OPERATIONS["construction"]
    if "용역" in haystack or "서비스" in haystack or "servc" in haystack or "service" in haystack:
        return "service", DETAIL_OPERATIONS["service"]
    if "물품" in haystack or "thng" in haystack or "goods" in haystack:
        return "goods", DETAIL_OPERATIONS["goods"]
    if "외자" in haystack or "frgcpt" in haystack or "foreign" in haystack:
        return "foreign", DETAIL_OPERATIONS["foreign"]
    return "", ""


def build_g2b_detail_api_url(item: dict) -> str:
    return build_g2b_detail_api_request(item).get("url", "")


def build_g2b_detail_api_request(item: dict) -> dict:
    operation_kind, operation = get_g2b_operation_kind(item)
    bid_no = str(item.get("source_record_id") or item.get("bidNtceNo") or item.get("bid_no") or "").strip()
    bid_ord = str(item.get("source_record_no") or item.get("bidNtceOrd") or item.get("bid_ord") or "").strip()
    if not operation or not bid_no or not DATA_GO_KR_SERVICE_KEY:
        return {"operation_kind": operation_kind, "operation": operation, "endpoint": "", "params": {}, "url": ""}

    params = {
        "serviceKey": DATA_GO_KR_SERVICE_KEY,
        "bidNtceNo": bid_no,
        "type": "json",
    }
    if bid_ord:
        params["bidNtceOrd"] = bid_ord
    endpoint = f"{G2B_DETAIL_BASE_ENDPOINT.rstrip('/')}/{operation}"
    return {
        "operation_kind": operation_kind,
        "operation": operation,
        "endpoint": endpoint,
        "params": params,
        "item_posted_at": item.get("posted_at"),
        "url": f"{endpoint}?{urlencode(params)}",
    }


def fetch_g2b_detail(item: dict) -> dict:
    request = build_g2b_detail_api_request(item)
    if not request.get("endpoint"):
        return {
            "ok": False,
            "status": "failed",
            "detail_api_url": "",
            "payload": None,
            "payload_json": None,
            "error_message": "missing operation, bidNtceNo, or DATA_GO_KR_SERVICE_KEY",
        }

    response, request, error = _request_with_fallbacks(request)
    if response is None:
        return {
            "ok": False,
            "status": "failed",
            "detail_api_url": request["url"],
            "payload": None,
            "payload_json": None,
            "error_message": _mask_secret(str(error)),
        }

    payload = _parse_response(response)
    result_code, result_msg = _extract_result(payload)
    if result_code and result_code not in ("00", "0"):
        return {
            "ok": False,
            "status": "failed",
            "detail_api_url": request["url"],
            "payload": payload,
            "payload_json": _to_json(payload),
            "error_message": f"{result_code} {result_msg}".strip(),
        }

    if not _payload_matches_item(payload, item):
        return {
            "ok": False,
            "status": "failed",
            "detail_api_url": request["url"],
            "payload": payload,
            "payload_json": _to_json(payload),
            "error_message": "detail payload does not contain bid notice number or title",
        }

    return {
        "ok": True,
        "status": "success",
        "detail_api_url": request["url"],
        "payload": payload,
        "payload_json": _to_json(payload),
        "error_message": None,
    }


def _parse_response(response: requests.Response) -> dict:
    text = response.text.strip()
    if text.startswith("{"):
        return response.json()
    root = ET.fromstring(response.content.decode(response.encoding or "utf-8", errors="replace"))
    return _xml_to_dict(root)


def _request_with_fallbacks(request: dict) -> tuple[requests.Response | None, dict, requests.RequestException | None]:
    attempts = [request]
    fallback = _build_list_fallback_request(request)
    if fallback.get("endpoint"):
        attempts.append(fallback)

    last_error: requests.RequestException | None = None
    for attempt in attempts:
        endpoints = [attempt["endpoint"]]
        if attempt["endpoint"].startswith("https://apis.data.go.kr/"):
            endpoints.append(attempt["endpoint"].replace("https://", "http://", 1))
        for endpoint in endpoints:
            try:
                response = requests.get(endpoint, params=attempt["params"], timeout=30)
                response.raise_for_status()
                attempt = {**attempt, "endpoint": endpoint, "url": f"{endpoint}?{urlencode(attempt['params'])}"}
                return response, attempt, None
            except requests.RequestException as exc:
                last_error = exc
    return None, request, last_error


def _build_list_fallback_request(request: dict) -> dict:
    operation = LIST_FALLBACK_OPERATIONS.get(request.get("operation_kind"))
    if not operation:
        return {"endpoint": "", "params": {}, "url": ""}
    params = dict(request.get("params") or {})
    params.setdefault("pageNo", 1)
    params["numOfRows"] = 999
    params["inqryDiv"] = "1"
    posted_at = str(request.get("item_posted_at") or "")
    date_digits = "".join(ch for ch in posted_at if ch.isdigit())[:8]
    if date_digits:
        params["inqryBgnDt"] = f"{date_digits}0000"
        params["inqryEndDt"] = f"{date_digits}2359"
    endpoint = f"{G2B_DETAIL_BASE_ENDPOINT.rstrip('/')}/{operation}"
    return {
        "operation_kind": request.get("operation_kind"),
        "operation": operation,
        "endpoint": endpoint,
        "params": params,
        "url": f"{endpoint}?{urlencode(params)}",
    }


def _extract_result(payload: dict) -> tuple[str, str]:
    header = payload.get("response", {}).get("header", {}) if isinstance(payload.get("response"), dict) else {}
    result_code = str(header.get("resultCode") or payload.get("resultCode") or "")
    result_msg = str(header.get("resultMsg") or payload.get("resultMsg") or "")
    return result_code, result_msg


def _payload_matches_item(payload: dict, item: dict) -> bool:
    text = (_to_json(payload) or "").lower()
    record_id = str(item.get("source_record_id") or item.get("bidNtceNo") or "").strip().lower()
    title = str(item.get("title") or "").strip().lower()
    title_tokens = [token for token in title.split() if len(token) >= 4]
    return bool((record_id and record_id in text) or any(token in text for token in title_tokens[:5]))


def _xml_to_dict(node: ET.Element) -> dict:
    children = list(node)
    key = node.tag.split("}", 1)[-1]
    if not children:
        return {key: (node.text or "").strip()}
    result: dict = {}
    for child in children:
        child_dict = _xml_to_dict(child)
        child_key, value = next(iter(child_dict.items()))
        if child_key in result:
            if not isinstance(result[child_key], list):
                result[child_key] = [result[child_key]]
            result[child_key].append(value)
        else:
            result[child_key] = value
    return {key: result}


def _to_json(payload: dict | None) -> str | None:
    if payload is None:
        return None
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _mask_secret(text: str) -> str:
    if DATA_GO_KR_SERVICE_KEY:
        text = text.replace(DATA_GO_KR_SERVICE_KEY, "[MASKED_SERVICE_KEY]")
    return text
