from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import requests


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collectors.lh import DEFAULT_LH_OPENBID_ENDPOINT
from src.config import DATA_GO_KR_SERVICE_KEY, LH_OPENBID_ENDPOINT


HTTPS_ENDPOINT = "https://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
HTTP_ENDPOINT = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
SAMPLE_PARAMS = {
    "numOfRows": "10",
    "pageNo": "1",
    "tndrbidRegDtStart": "20161122",
    "tndrbidRegDtEnd": "20161123",
}


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
    result_msg = find_text(root, "resultMsg")
    total_count = find_text(root, "totalCount")
    item_count = sum(1 for node in root.iter() if local_name(node.tag) == "item")
    return result_code, result_msg, total_count, item_count


def safe_preview(text: str) -> str:
    preview = text[:500]
    if DATA_GO_KR_SERVICE_KEY:
        preview = preview.replace(DATA_GO_KR_SERVICE_KEY, "[MASKED_SERVICE_KEY]")
    return preview


def mask_sensitive_text(text: str) -> str:
    if DATA_GO_KR_SERVICE_KEY:
        text = text.replace(DATA_GO_KR_SERVICE_KEY, "[MASKED_SERVICE_KEY]")
    return text


def call_with_params(endpoint: str) -> requests.Response:
    params = {"serviceKey": DATA_GO_KR_SERVICE_KEY, **SAMPLE_PARAMS}
    return requests.get(endpoint, params=params, timeout=30)


def call_with_manual_url(endpoint: str) -> requests.Response:
    query = "&".join(
        [
            f"serviceKey={DATA_GO_KR_SERVICE_KEY}",
            "numOfRows=10",
            "pageNo=1",
            "tndrbidRegDtStart=20161122",
            "tndrbidRegDtEnd=20161123",
        ]
    )
    return requests.get(f"{endpoint}?{query}", timeout=30)


def run_test(name: str, endpoint: str, mode: str) -> tuple[str, str]:
    print("=" * 72)
    print(f"test name: {name}")
    print(f"endpoint: {endpoint}")
    print(f"call mode: {mode}")

    try:
        response = call_with_params(endpoint) if mode == "params" else call_with_manual_url(endpoint)
    except Exception as exc:
        print(f"request failed: {mask_sensitive_text(str(exc))}")
        return "", ""

    print(f"HTTP status code: {response.status_code}")
    text = response.content.decode(response.encoding or "utf-8", errors="replace")

    try:
        result_code, result_msg, total_count, item_count = parse_response(text)
    except Exception as exc:
        print(f"response parse failed: {exc}")
        print(f"response preview: {safe_preview(text)}")
        return "", ""

    print(f"resultCode: {result_code}")
    print(f"resultMsg: {result_msg}")
    print(f"totalCount: {total_count}")
    print(f"item count: {item_count}")
    print(f"response preview: {safe_preview(text)}")
    return result_code, result_msg


def main() -> int:
    print("auth variable: DATA_GO_KR_SERVICE_KEY")
    print(f"auth key: {mask_key(DATA_GO_KR_SERVICE_KEY)}")
    print(f"configured endpoint: {LH_OPENBID_ENDPOINT or DEFAULT_LH_OPENBID_ENDPOINT}")

    if not DATA_GO_KR_SERVICE_KEY:
        print("ERROR: .env에 DATA_GO_KR_SERVICE_KEY를 설정하세요.")
        return 1

    tests = [
        ("Test A", HTTPS_ENDPOINT, "params"),
        ("Test B", HTTPS_ENDPOINT, "manual_url"),
        ("Test C", HTTP_ENDPOINT, "params"),
        ("Test D", HTTP_ENDPOINT, "manual_url"),
    ]
    results = [(*test, *run_test(*test)) for test in tests]

    for name, endpoint, mode, result_code, result_msg in results:
        if result_code in ("00", "0") or "NORMAL SERVICE" in result_msg.upper():
            print("=" * 72)
            print(f"PASS: {name} succeeded. Use endpoint={endpoint}, mode={mode}.")
            return 0

    if results and all(result_code == "30" for *_, result_code, _ in results):
        print("=" * 72)
        print("All tests returned resultCode=30.")
        print("코드보다 공공데이터포털 키 반영 지연, 인증키 복사 오류, 활용신청 반영 지연, Encoding/Decoding 키 선택 문제를 확인하세요.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
