from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import requests


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import D2B_LOOKAHEAD_MONTHS, D2B_PLAN_DOMESTIC_ENDPOINT, DATA_GO_KR_SERVICE_KEY


def add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    return date(year, month, 1)


def mask_key(value: str) -> str:
    if not value:
        return "missing"
    return f"{value[:4]}*** (length={len(value)})"


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def find_text(root: ET.Element, tag: str) -> str:
    for node in root.iter():
        if local_name(node.tag) == tag:
            return (node.text or "").strip()
    return ""


def parse_response(text: str) -> tuple[str, str, str, int]:
    stripped = re.sub(r"^\s*<\?xml[^>]*\?>", "", text).strip()
    root = ET.fromstring(stripped)
    result_code = find_text(root, "resultCode")
    result_msg = find_text(root, "resultMsg") or find_text(root, "resultMag")
    total_count = find_text(root, "totalCount")
    item_count = sum(1 for node in root.iter() if local_name(node.tag) == "item")
    return result_code, result_msg, total_count, item_count


def safe_preview(text: str) -> str:
    preview = text[:500]
    if DATA_GO_KR_SERVICE_KEY:
        preview = preview.replace(DATA_GO_KR_SERVICE_KEY, "[MASKED_SERVICE_KEY]")
    return preview


def build_params() -> dict:
    today = date.today()
    return {
        "serviceKey": DATA_GO_KR_SERVICE_KEY,
        "orderPrearngeMtBegin": today.strftime("%Y%m"),
        "orderPrearngeMtEnd": add_months(today, D2B_LOOKAHEAD_MONTHS).strftime("%Y%m"),
        "reprsntPrdlstNm": "",
        "dcsNo": "",
        "numOfRows": 10,
        "pageNo": 1,
    }


def request_params(endpoint: str) -> requests.Response:
    return requests.get(endpoint, params=build_params(), timeout=30)


def request_manual(endpoint: str) -> requests.Response:
    params = build_params()
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return requests.get(f"{endpoint}?{query}", timeout=30)


def run_once(endpoint: str, mode: str) -> bool:
    print("=" * 72)
    print(f"endpoint: {endpoint}")
    print(f"mode: {mode}")
    try:
        response = request_params(endpoint) if mode == "params" else request_manual(endpoint)
    except Exception as exc:
        message = str(exc).replace(DATA_GO_KR_SERVICE_KEY, "[MASKED_SERVICE_KEY]")
        print(f"request failed: {message}")
        return False

    print(f"HTTP status code: {response.status_code}")
    text = response.content.decode(response.encoding or "utf-8", errors="replace")
    try:
        result_code, result_msg, total_count, item_count = parse_response(text)
    except Exception as exc:
        print(f"response parse failed: {exc}")
        print(f"response preview: {safe_preview(text)}")
        return False

    print(f"resultCode: {result_code}")
    print(f"resultMsg/resultMag: {result_msg}")
    print(f"totalCount: {total_count}")
    print(f"item count: {item_count}")
    print(f"response preview: {safe_preview(text)}")
    return result_code in ("00", "0")


def main() -> int:
    print(f"DATA_GO_KR_SERVICE_KEY: {mask_key(DATA_GO_KR_SERVICE_KEY)}")
    if not DATA_GO_KR_SERVICE_KEY:
        print("ERROR: .env에 DATA_GO_KR_SERVICE_KEY를 설정하세요.")
        return 1

    endpoint = D2B_PLAN_DOMESTIC_ENDPOINT
    if run_once(endpoint, "params"):
        print("D2B probe passed with params mode.")
        return 0
    if run_once(endpoint, "manual_url"):
        print("D2B probe passed with manual_url mode.")
        return 0
    print("D2B probe failed. Check API approval, endpoint, key type, and traffic limits.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
