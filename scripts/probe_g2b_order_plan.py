from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import DATA_GO_KR_SERVICE_KEY, G2B_PLAN_BASE_ENDPOINT  # noqa: E402
from src.text_utils import contains_modular_keyword  # noqa: E402


DEFAULT_ENDPOINT = "https://apis.data.go.kr/1230000/ao/OrderPlanStusService"
OPERATIONS = {
    "물품": (
        "getOrderPlanStusListThng",
        "getOrderPlanSttusListThng",
        "getOrderPlanStusListGoods",
    ),
    "용역": (
        "getOrderPlanStusListServc",
        "getOrderPlanSttusListServc",
        "getOrderPlanStusListService",
    ),
    "공사": (
        "getOrderPlanStusListCnstwk",
        "getOrderPlanSttusListCnstwk",
        "getOrderPlanStusListConstruction",
    ),
    "통합": ("getOrderPlanStusList", "getOrderPlanSttusList"),
}


def add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    return date(value.year + month // 12, month % 12 + 1, 1)


def key_candidates(value: str) -> list[tuple[str, str]]:
    candidates = [("configured", value)]
    decoded = unquote(value)
    if decoded != value:
        candidates.append(("decoded", decoded))
    return candidates


def parse_response(response: requests.Response) -> dict[str, Any]:
    text = response.text.strip()
    result: dict[str, Any] = {
        "status_code": response.status_code,
        "result_code": "",
        "result_msg": "",
        "total_count": 0,
        "items": [],
        "body_prefix": text[:300].replace("\n", " "),
    }
    if not text:
        return result
    if text.startswith(("{", "[")):
        try:
            payload = response.json()
        except json.JSONDecodeError:
            return result
        envelope = payload.get("response", payload) if isinstance(payload, dict) else {}
        header = envelope.get("header", {}) if isinstance(envelope, dict) else {}
        body = envelope.get("body", {}) if isinstance(envelope, dict) else {}
        result["result_code"] = str(header.get("resultCode") or payload.get("resultCode") or "")
        result["result_msg"] = str(header.get("resultMsg") or payload.get("resultMsg") or "")
        result["total_count"] = int(body.get("totalCount") or payload.get("totalCount") or 0)
        items: Any = body.get("items") or payload.get("items") or []
        if isinstance(items, dict):
            items = items.get("item", items)
        result["items"] = items if isinstance(items, list) else ([items] if isinstance(items, dict) else [])
        return result

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return result
    values = {node.tag.split("}", 1)[-1]: (node.text or "").strip() for node in root.iter()}
    result["result_code"] = values.get("resultCode", "")
    result["result_msg"] = values.get("resultMsg", "") or values.get("resultMag", "")
    try:
        result["total_count"] = int(values.get("totalCount", "0") or 0)
    except ValueError:
        pass
    result["items"] = [
        {child.tag.split("}", 1)[-1]: (child.text or "").strip() for child in list(node)}
        for node in root.iter()
        if node.tag.split("}", 1)[-1] == "item"
    ]
    return result


def is_success(result: dict[str, Any]) -> bool:
    return result["status_code"] in range(200, 400) and result["result_code"] in {"", "00", "0"}


def main() -> int:
    if not DATA_GO_KR_SERVICE_KEY:
        print(".env에 DATA_GO_KR_SERVICE_KEY를 설정하세요.")
        return 1

    base = (G2B_PLAN_BASE_ENDPOINT or DEFAULT_ENDPOINT).rstrip("/")
    today = date.today()
    params_base = {
        "pageNo": 1,
        "numOfRows": 10,
        "inqryDiv": "1",
        "inqryBgnDate": today.strftime("%Y%m%d"),
        "inqryEndDate": add_months(today, 12).strftime("%Y%m%d"),
        "type": "json",
    }
    print(f"endpoint base: {base}")
    print(f"service key: {DATA_GO_KR_SERVICE_KEY[:4]}*** length={len(DATA_GO_KR_SERVICE_KEY)}")
    any_success = False

    for business_type, operations in OPERATIONS.items():
        business_success = False
        for operation in operations:
            endpoint = f"{base}/{operation}"
            for key_mode, service_key in key_candidates(DATA_GO_KR_SERVICE_KEY):
                response = requests.get(endpoint, params={**params_base, "serviceKey": service_key}, timeout=30)
                result = parse_response(response)
                auth_error = result["status_code"] == 403 or result["result_code"] == "30" or "SERVICE KEY" in result["result_msg"].upper()
                modular_count = sum(
                    contains_modular_keyword(" ".join(str(value or "") for value in item.values()))
                    for item in result["items"]
                )
                print(
                    f"[{business_type}] operation={operation} key_mode={key_mode} "
                    f"http={result['status_code']} resultCode={result['result_code'] or '-'} "
                    f"resultMsg={result['result_msg'] or '-'} totalCount={result['total_count']} "
                    f"items={len(result['items'])} modular_matches={modular_count}"
                )
                if auth_error:
                    print("  활용신청 또는 인증키 권한 확인 필요")
                if is_success(result):
                    message = "정상 호출, 모듈러 매칭 0건" if modular_count == 0 else "정상 호출, 모듈러 항목 확인"
                    print(f"  SUCCESS: {message}")
                    any_success = True
                    business_success = True
                    break
            if business_success:
                break

    return 0 if any_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
