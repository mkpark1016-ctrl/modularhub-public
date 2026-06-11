from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

import requests


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import (
    D2B_BID_BASE_ENDPOINT,
    D2B_BID_DOMESTIC_ENDPOINT,
    D2B_BID_FOREIGN_ENDPOINT,
    D2B_BID_PUBLIC_PRIVATE_ENDPOINT,
    DATA_GO_KR_SERVICE_KEY,
)


DEFAULT_BASE = "https://openapi.d2b.go.kr/openapi/service/BidPblancInfoService"
DEFAULT_DOMESTIC = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList"
REQUEST_TIMEOUT_SECONDS = 8
CANDIDATE_PATHS = [
    "getDmstcCmpetBidPblancList",
    "getOutnatnCmpetBidPblancList",
    "getFcltyCmpetBidPblancList",
    "getDmstcOthbcVltrnNtatPlanList",
    "getFcltyOthbcVltrnNtatPlanList",
]
DATE_PARAM_SETS = [
    ("announcement_date", "anmtDateBegin", "anmtDateEnd"),
    ("opening_date", "opengDateBegin", "opengDateEnd"),
]


def mask_key(value: str) -> str:
    if not value:
        return "missing"
    return f"{value[:4]}*** (length={len(value)})"


def safe_text(text: str) -> str:
    if DATA_GO_KR_SERVICE_KEY:
        return text.replace(DATA_GO_KR_SERVICE_KEY, "[MASKED_SERVICE_KEY]")
    return text


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


def params(begin_param: str, end_param: str) -> dict:
    end = date.today()
    start = end - timedelta(days=30)
    return {
        "serviceKey": DATA_GO_KR_SERVICE_KEY,
        "numOfRows": 10,
        "pageNo": 1,
        begin_param: start.strftime("%Y%m%d"),
        end_param: end.strftime("%Y%m%d"),
    }


def endpoint_candidates() -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    if D2B_BID_DOMESTIC_ENDPOINT:
        candidates.append(("env domestic", D2B_BID_DOMESTIC_ENDPOINT))
    if D2B_BID_FOREIGN_ENDPOINT:
        candidates.append(("env foreign", D2B_BID_FOREIGN_ENDPOINT))
    if D2B_BID_PUBLIC_PRIVATE_ENDPOINT:
        candidates.append(("env public/private", D2B_BID_PUBLIC_PRIVATE_ENDPOINT))

    candidates.append(("default domestic", DEFAULT_DOMESTIC))
    base = D2B_BID_BASE_ENDPOINT or DEFAULT_BASE
    candidates.append(("base", base))
    for path in CANDIDATE_PATHS:
        candidates.append((f"candidate {path}", f"{base.rstrip('/')}/{path}"))

    seen = set()
    unique = []
    for name, endpoint in candidates:
        if endpoint not in seen:
            seen.add(endpoint)
            unique.append((name, endpoint))
    return unique


def call(endpoint: str, mode: str, request_params: dict) -> requests.Response:
    if mode == "params":
        return requests.get(endpoint, params=request_params, timeout=REQUEST_TIMEOUT_SECONDS)
    query = "&".join(f"{key}={value}" for key, value in request_params.items())
    return requests.get(f"{endpoint}?{query}", timeout=REQUEST_TIMEOUT_SECONDS)


def run_test(name: str, endpoint: str, mode: str, date_mode: str, request_params: dict) -> tuple[str, str, str, str, str]:
    print("=" * 72, flush=True)
    print(f"test name: {name}", flush=True)
    print(f"endpoint: {endpoint}", flush=True)
    print(f"call mode: {mode}", flush=True)
    print(f"date params: {date_mode}", flush=True)
    try:
        response = call(endpoint, mode, request_params)
    except Exception as exc:
        message = safe_text(str(exc))
        print(f"request failed: {message}", flush=True)
        return name, mode, date_mode, "", message

    print(f"HTTP status code: {response.status_code}", flush=True)
    text = response.content.decode(response.encoding or "utf-8", errors="replace")
    try:
        result_code, result_msg, total_count, item_count = parse_response(text)
    except Exception as exc:
        print(f"response parse failed: {exc}", flush=True)
        print(f"response preview: {safe_text(text[:500])}", flush=True)
        return name, mode, date_mode, "", str(exc)

    print(f"resultCode: {result_code}", flush=True)
    print(f"resultMsg/resultMag: {result_msg}", flush=True)
    print(f"totalCount: {total_count}", flush=True)
    print(f"item count: {item_count}", flush=True)
    print(f"response preview: {safe_text(text[:500])}", flush=True)
    return name, mode, date_mode, result_code, result_msg


def main() -> int:
    print(f"DATA_GO_KR_SERVICE_KEY: {mask_key(DATA_GO_KR_SERVICE_KEY)}", flush=True)
    if not DATA_GO_KR_SERVICE_KEY:
        print("ERROR: .env에 DATA_GO_KR_SERVICE_KEY를 설정하세요.", flush=True)
        return 1

    failures = []
    for name, endpoint in endpoint_candidates():
        for date_mode, begin_param, end_param in DATE_PARAM_SETS:
            request_params = params(begin_param, end_param)
            for mode in ("params", "manual_url"):
                test_name, test_mode, test_date_mode, result_code, result_msg = run_test(
                    name,
                    endpoint,
                    mode,
                    date_mode,
                    request_params,
                )
                if result_code in ("00", "0") or "NORMAL SERVICE" in result_msg.upper():
                    print("=" * 72, flush=True)
                    print(
                        f"SUCCESS: endpoint={endpoint}, mode={mode}, "
                        f"date_params={begin_param}/{end_param}",
                        flush=True,
                    )
                    return 0
                failures.append((test_name, test_mode, test_date_mode, result_code, result_msg))

    print("=" * 72, flush=True)
    print("All D2B bid endpoint candidates failed.", flush=True)
    print("summary:", flush=True)
    for failure in failures:
        print(failure, flush=True)
    print(
        "SERVICE KEY 오류가 있으면 활용신청 승인 여부, DATA_GO_KR_SERVICE_KEY 값, "
        "인코딩/디코딩 키 선택을 확인하세요.",
        flush=True,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
