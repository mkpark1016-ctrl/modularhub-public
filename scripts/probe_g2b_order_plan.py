from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import DATA_GO_KR_SERVICE_KEY, G2B_PLAN_BASE_ENDPOINT  # noqa: E402


OFFICIAL_BASE_ENDPOINT = "https://apis.data.go.kr/1230000/ao/OrderPlanSttusService"
OPERATIONS = (
    ("물품 일반조회", "getOrderPlanSttusListThng", "standard"),
    ("용역 일반조회", "getOrderPlanSttusListServc", "standard"),
    ("공사 일반조회", "getOrderPlanSttusListCnstwk", "standard"),
    ("외자 일반조회", "getOrderPlanSttusListFrgcpt", "standard"),
    ("물품 검색조회", "getOrderPlanSttusListThngPPSSrch", "search"),
    ("용역 검색조회", "getOrderPlanSttusListServcPPSSrch", "search"),
    ("공사 검색조회", "getOrderPlanSttusListCnstwkPPSSrch", "search"),
    ("외자 검색조회", "getOrderPlanSttusListFrgcptPPSSrch", "search"),
)
AUTH_CODES = {"10", "20", "30", "31", "32"}
PARAM_CODES = {"11", "12", "22"}


def add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    return date(value.year + month // 12, month % 12 + 1, 1)


def key_candidates(value: str) -> list[tuple[str, str]]:
    candidates = [("configured", value)]
    decoded = unquote(value)
    if decoded != value:
        candidates.append(("decoded", decoded))
    return candidates


def request_params(operation_kind: str, service_key: str) -> dict[str, Any]:
    today = date.today()
    end_date = add_months(today, 12)
    common: dict[str, Any] = {
        "serviceKey": service_key,
        "pageNo": 1,
        "numOfRows": 10,
        "type": "json",
    }
    if operation_kind == "search":
        return {
            **common,
            "orderBgnYm": today.strftime("%Y%m"),
            "orderEndYm": end_date.strftime("%Y%m"),
            "inqryBgnDt": (today - timedelta(days=365)).strftime("%Y%m%d0000"),
            "inqryEndDt": datetime.now().strftime("%Y%m%d2359"),
            "bizNm": "모듈러",
        }
    return {
        **common,
        "inqryDiv": "1",
        "orderBgnYm": today.strftime("%Y%m"),
        "orderEndYm": end_date.strftime("%Y%m"),
    }


def masked_url(url: str) -> str:
    parts = urlsplit(url)
    query = []
    for name, value in parse_qsl(parts.query, keep_blank_values=True):
        query.append((name, "****" if name.lower() == "servicekey" else value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def response_format(text: str) -> str:
    stripped = text.lstrip()
    if stripped.startswith(("{", "[")):
        return "JSON"
    if stripped.startswith("<"):
        return "XML" if "<html" not in stripped[:200].lower() else "HTML"
    return "EMPTY" if not stripped else "TEXT"


def parse_response(response: requests.Response) -> dict[str, Any]:
    text = response.text.strip()
    result: dict[str, Any] = {
        "status_code": response.status_code,
        "format": response_format(text),
        "result_code": "",
        "result_msg": "",
        "total_count": 0,
        "items": [],
        "parsed": False,
        "body_prefix": text[:500].replace("\n", " "),
    }
    if not text:
        return result

    if result["format"] == "JSON":
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError):
            return result
        if not isinstance(payload, dict):
            return result
        envelope = payload.get("response", payload)
        header = envelope.get("header", {}) if isinstance(envelope, dict) else {}
        body = envelope.get("body", {}) if isinstance(envelope, dict) else {}
        result["result_code"] = str(header.get("resultCode") or payload.get("resultCode") or "")
        result["result_msg"] = str(
            header.get("resultMsg") or header.get("resultMag") or payload.get("resultMsg") or payload.get("resultMag") or ""
        )
        result["total_count"] = to_int(body.get("totalCount") or payload.get("totalCount"))
        items: Any = body.get("items") or payload.get("items") or []
        if isinstance(items, dict):
            items = items.get("item", items)
        result["items"] = items if isinstance(items, list) else ([items] if isinstance(items, dict) else [])
        result["parsed"] = True
        return result

    if result["format"] not in {"XML", "HTML"}:
        return result
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return result
    values = {local_name(node.tag): (node.text or "").strip() for node in root.iter()}
    result["result_code"] = values.get("resultCode", "")
    result["result_msg"] = values.get("resultMsg", "") or values.get("resultMag", "")
    result["total_count"] = to_int(values.get("totalCount"))
    result["items"] = [
        {local_name(child.tag): (child.text or "").strip() for child in list(node)}
        for node in root.iter()
        if local_name(node.tag) == "item"
    ]
    result["parsed"] = result["format"] == "XML"
    return result


def classify_result(result: dict[str, Any]) -> tuple[str, str]:
    status = result["status_code"]
    code = str(result["result_code"] or "").strip()
    message = str(result["result_msg"] or "").strip()
    upper = f"{code} {message} {result['body_prefix']}".upper()

    if status == 404:
        return "NOT_FOUND_OPERATION", "operation path가 존재하지 않습니다."
    if status in {401, 403} or code in AUTH_CODES or any(
        token in upper for token in ("SERVICE KEY", "UNREGISTERED", "ACCESS DENIED", "인증키", "활용신청")
    ):
        return "AUTH_ERROR", "활용신청 승인 상태와 인증키 Encoding/Decoding 값을 확인하세요."
    if status == 400 or code in PARAM_CODES or any(
        token in upper for token in ("REQUIRED PARAMETER", "INVALID REQUEST PARAMETER", "필수 파라미터", "PARAMETER ERROR")
    ):
        return "PARAM_ERROR", "공식 문서의 필수 파라미터와 날짜 형식을 확인하세요."
    if status < 200 or status >= 400:
        return "PARSE_ERROR", f"예상하지 못한 HTTP 상태 {status}입니다."
    if not result["parsed"]:
        return "PARSE_ERROR", f"{result['format']} 응답을 API 데이터로 파싱하지 못했습니다."
    if code and code not in {"0", "00"} and "NORMAL SERVICE" not in message.upper():
        return "PARAM_ERROR", f"API 오류 코드 {code}: {message or '메시지 없음'}"
    if result["items"]:
        return "SUCCESS", "정상 호출되어 항목을 수신했습니다."
    if result["total_count"] > 0:
        return "PARSE_ERROR", "totalCount는 있으나 item을 파싱하지 못했습니다."
    return "EMPTY_RESULT", "정상 호출되었지만 조회 결과가 0건입니다."


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def to_int(value: Any) -> int:
    try:
        return int(str(value or "0").replace(",", ""))
    except ValueError:
        return 0


def main() -> int:
    if not DATA_GO_KR_SERVICE_KEY:
        print(".env에 DATA_GO_KR_SERVICE_KEY를 설정하세요.")
        return 1

    configured_base = (G2B_PLAN_BASE_ENDPOINT or "").rstrip("/")
    bases = []
    for label, endpoint in (("configured", configured_base), ("official", OFFICIAL_BASE_ENDPOINT)):
        if endpoint and endpoint not in {value for _, value in bases}:
            bases.append((label, endpoint))

    print("공식 문서: https://www.data.go.kr/data/15129462/openapi.do")
    print(f"공식 endpoint: {OFFICIAL_BASE_ENDPOINT}")
    print(f"service key: {DATA_GO_KR_SERVICE_KEY[:4]}*** length={len(DATA_GO_KR_SERVICE_KEY)}")
    classifications: dict[str, int] = {}

    for base_label, base in bases:
        print(f"\n=== base={base_label}: {base} ===")
        for operation_label, operation, operation_kind in OPERATIONS:
            endpoint = f"{base}/{operation}"
            final_result: dict[str, Any] | None = None
            final_classification = "PARSE_ERROR"
            final_reason = "응답 없음"
            final_key_mode = "configured"
            for key_mode, service_key in key_candidates(DATA_GO_KR_SERVICE_KEY):
                params = request_params(operation_kind, service_key)
                prepared = requests.Request("GET", endpoint, params=params).prepare()
                print(f"[{operation_label}] operation={operation} key_mode={key_mode}")
                print(f"  request={masked_url(prepared.url or endpoint)}")
                try:
                    response = requests.get(endpoint, params=params, timeout=30)
                except requests.RequestException as exc:
                    final_result = {
                        "status_code": 0,
                        "format": "NETWORK",
                        "result_code": "",
                        "result_msg": str(exc),
                        "total_count": 0,
                        "items": [],
                        "parsed": False,
                        "body_prefix": str(exc),
                    }
                    final_classification, final_reason = "PARSE_ERROR", f"네트워크 요청 실패: {exc}"
                    break
                final_result = parse_response(response)
                final_classification, final_reason = classify_result(final_result)
                final_key_mode = key_mode
                if final_classification != "AUTH_ERROR" or key_mode == key_candidates(DATA_GO_KR_SERVICE_KEY)[-1][0]:
                    break

            assert final_result is not None
            classifications[final_classification] = classifications.get(final_classification, 0) + 1
            print(
                f"  http={final_result['status_code']} format={final_result['format']} "
                f"resultCode={final_result['result_code'] or '-'} resultMsg={final_result['result_msg'] or '-'}"
            )
            print(
                f"  totalCount={final_result['total_count']} items={len(final_result['items'])} "
                f"classification={final_classification} key_mode={final_key_mode}"
            )
            print(f"  reason={final_reason}")
            print(f"  response={final_result['body_prefix'] or '-'}")

    print("\n=== classification summary ===")
    for name in ("SUCCESS", "EMPTY_RESULT", "AUTH_ERROR", "NOT_FOUND_OPERATION", "PARAM_ERROR", "PARSE_ERROR"):
        print(f"{name}={classifications.get(name, 0)}")
    return 0 if classifications.get("SUCCESS", 0) or classifications.get("EMPTY_RESULT", 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
