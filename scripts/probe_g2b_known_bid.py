from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.collectors.g2b import G2BCollector
from src.config import DATA_GO_KR_SERVICE_KEY, DB_PATH, G2B_DETAIL_BASE_ENDPOINT
from src.database import get_connection, init_db, upsert_item, upsert_source_detail
from src.models import Item
from src.normalizer import normalize_item

OPERATIONS = {
    "물품": "getBidPblancDetailInfoThng",
    "용역": "getBidPblancDetailInfoServc",
    "공사": "getBidPblancDetailInfoCnstwk",
    "외자": "getBidPblancDetailInfoFrgcpt",
}
LIST_OPERATIONS = {
    "물품": "getBidPblancListInfoThngPPSSrch",
    "용역": "getBidPblancListInfoServcPPSSrch",
    "공사": "getBidPblancListInfoCnstwkPPSSrch",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe G2B detail API for a known important bid.")
    parser.add_argument("--bid-no", required=True)
    parser.add_argument("--title-keyword", default="성의여자고등학교")
    parser.add_argument("--title-contains", nargs="*", default=[])
    parser.add_argument("--orders", nargs="*", default=["000", "001"])
    args = parser.parse_args()

    if not args.title_contains and args.title_keyword:
        args.title_contains = [args.title_keyword]

    if not DATA_GO_KR_SERVICE_KEY:
        print(".env에 DATA_GO_KR_SERVICE_KEY를 설정하세요.")
        return 1

    init_db(DB_PATH)
    successes: list[dict] = []
    for category, operation in OPERATIONS.items():
        for order in args.orders:
            result = request_detail(category, operation, args.bid_no, order, args.title_contains)
            print_probe_result(category, operation, order, result, args)
            if result["matched"]:
                successes.append(result)
    if not successes:
        print("\n상세 API 후보가 실패했습니다. 목록 API bidNtceNo 검색 fallback을 시도합니다.")
        for category, operation in LIST_OPERATIONS.items():
            result = request_list_fallback(category, operation, args.bid_no, args.title_contains)
            print_probe_result(category, operation, "list", result, args)
            if result["matched"]:
                successes.append(result)

    if not successes:
        print("G2B detail probe failed for all business types/orders.")
        return 1

    for result in successes:
        item_id = upsert_probe_result(result)
        print(f"stored: item_id={item_id} category={result['category']} order={result['bid_order']}")

    print(f"G2B known bid probe passed: {len(successes)} matching response(s)")
    return 0


def request_detail(category: str, operation: str, bid_no: str, bid_order: str, title_contains: list[str] | None = None) -> dict:
    endpoint = f"{G2B_DETAIL_BASE_ENDPOINT.rstrip('/')}/{operation}"
    params = {
        "serviceKey": DATA_GO_KR_SERVICE_KEY,
        "bidNtceNo": bid_no,
        "bidNtceOrd": bid_order,
        "type": "json",
    }
    try:
        response = requests.get(endpoint, params=params, timeout=30)
        status_code = response.status_code
        text = response.text
        response.raise_for_status()
        payload = response.json() if text.lstrip().startswith("{") else {"raw": text}
    except Exception as exc:
        error_message = mask_key(str(exc))
        return {
            "category": category,
            "operation": operation,
            "bid_no": bid_no,
            "bid_order": bid_order,
            "detail_api_url": mask_key(f"{endpoint}?{urlencode(params)}"),
            "unmasked_detail_api_url": f"{endpoint}?{urlencode(params)}",
            "status_code": getattr(locals().get("response", None), "status_code", None),
            "payload": None,
            "result_code": "",
            "result_msg": error_message,
            "matched": False,
            "error": error_message,
        }

    result_code, result_msg = extract_result(payload)
    body_text = json.dumps(payload, ensure_ascii=False)
    matched = _matches_known_bid(body_text, bid_no, title_contains or [])
    return {
        "category": category,
        "operation": operation,
        "bid_no": bid_no,
        "bid_order": bid_order,
        "detail_api_url": mask_key(f"{endpoint}?{urlencode(params)}"),
        "unmasked_detail_api_url": f"{endpoint}?{urlencode(params)}",
        "status_code": status_code,
        "payload": payload,
        "result_code": result_code,
        "result_msg": result_msg,
        "matched": matched,
        "error": None,
    }


def request_list_fallback(category: str, operation: str, bid_no: str, title_contains: list[str] | None = None) -> dict:
    endpoint = f"{G2B_DETAIL_BASE_ENDPOINT.rstrip('/')}/{operation}"
    base_params = {
        "serviceKey": DATA_GO_KR_SERVICE_KEY,
        "bidNtceNo": bid_no,
        "numOfRows": 999,
        "inqryDiv": "1",
        "inqryBgnDt": "202605110000",
        "inqryEndDt": "202605112359",
        "type": "json",
    }
    last_payload = None
    last_status_code = None
    last_url = ""
    for page_no in range(1, 6):
        params = {**base_params, "pageNo": page_no}
        result = request_list_page(endpoint, params, category, operation, bid_no, title_contains or [])
        last_payload = result.get("payload")
        last_status_code = result.get("status_code")
        last_url = result.get("unmasked_detail_api_url", "")
        if result.get("matched"):
            return result
    return {
        "category": category,
        "operation": operation,
        "bid_no": bid_no,
        "bid_order": "",
        "detail_api_url": mask_key(last_url),
        "unmasked_detail_api_url": last_url,
        "status_code": last_status_code,
        "payload": last_payload,
        "result_code": extract_result(last_payload or {})[0],
        "result_msg": extract_result(last_payload or {})[1],
        "matched": False,
        "error": None,
    }


def request_list_page(endpoint: str, params: dict, category: str, operation: str, bid_no: str, title_contains: list[str] | None = None) -> dict:
    try:
        response = requests.get(endpoint, params=params, timeout=30)
        status_code = response.status_code
        text = response.text
        response.raise_for_status()
        payload = response.json() if text.lstrip().startswith("{") else {"raw": text}
    except Exception as exc:
        error_message = mask_key(str(exc))
        return {
            "category": category,
            "operation": operation,
            "bid_no": bid_no,
            "bid_order": "",
            "detail_api_url": mask_key(f"{endpoint}?{urlencode(params)}"),
            "unmasked_detail_api_url": f"{endpoint}?{urlencode(params)}",
            "status_code": getattr(locals().get("response", None), "status_code", None),
            "payload": None,
            "result_code": "",
            "result_msg": error_message,
            "matched": False,
            "error": error_message,
        }
    result_code, result_msg = extract_result(payload)
    body_text = json.dumps(payload, ensure_ascii=False)
    found = find_candidate_items(payload, bid_no)
    matched = bool(found) and _matches_known_bid(json.dumps(found, ensure_ascii=False), bid_no, title_contains or [])
    bid_order = str(found[0].get("bidNtceOrd") or "") if found else ""
    return {
        "category": category,
        "operation": operation,
        "bid_no": bid_no,
        "bid_order": bid_order,
        "detail_api_url": mask_key(f"{endpoint}?{urlencode(params)}"),
        "unmasked_detail_api_url": f"{endpoint}?{urlencode(params)}",
        "status_code": status_code,
        "payload": payload,
        "result_code": result_code,
        "result_msg": result_msg,
        "matched": matched,
        "error": None,
    }


def print_probe_result(category: str, operation: str, order: str, result: dict, args: argparse.Namespace) -> None:
    print(
        f"[{category}/{order}] operation={operation} http={result['status_code']} "
        f"resultCode={result['result_code'] or '-'} resultMsg={result['result_msg'] or '-'} "
        f"matched={result['matched']}"
    )
    if result.get("payload") is not None:
        text = json.dumps(result["payload"], ensure_ascii=False)
        contains_keyword = bool(args.title_keyword and args.title_keyword in text)
        print(f"  contains_title_keyword={contains_keyword} response_head={text[:300]}")
    elif result.get("error"):
        print(f"  error={result['error']}")


def upsert_probe_result(result: dict) -> int:
    payload = result["payload"]
    items = find_candidate_items(payload, result["bid_no"])
    item_payload = items[0] if items else {
        "bidNtceNo": result["bid_no"],
        "bidNtceOrd": result["bid_order"],
        "bidNtceNm": result["bid_no"],
    }
    collector = G2BCollector()
    raw_item = collector._to_raw_item(result["category"], item_payload)
    raw_item["source_detail_api_url"] = result["unmasked_detail_api_url"]
    raw_item["api_detail_verified"] = 1
    raw_item["is_known_important"] = 1
    normalized = normalize_item(raw_item)
    status = upsert_item(Item(**normalized), DB_PATH)

    with get_connection(DB_PATH) as conn:
        row = conn.execute("SELECT id FROM items WHERE unique_hash = ?", (normalized["unique_hash"],)).fetchone()
        item_id = int(row["id"]) if row else 0

    if item_id:
        upsert_source_detail(
            item_id=item_id,
            source_name="나라장터",
            source_type="bid",
            source_record_id=result["bid_no"],
            source_record_no=result["bid_order"],
            detail_api_url=result["unmasked_detail_api_url"],
            detail_payload_json=json.dumps(payload, ensure_ascii=False, indent=2),
            status=f"probe_{status}",
        )
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                UPDATE items
                SET link_type='exact_api',
                    link_status='ok',
                    api_detail_verified=1,
                    is_known_important=1,
                    source_detail_api_url=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (result["unmasked_detail_api_url"], item_id),
            )
    return item_id


def find_candidate_items(value: object, bid_no: str) -> list[dict]:
    found: list[dict] = []
    if isinstance(value, dict):
        if value.get("bidNtceNo") == bid_no:
            found.append(value)
        for nested in value.values():
            found.extend(find_candidate_items(nested, bid_no))
    elif isinstance(value, list):
        for nested in value:
            found.extend(find_candidate_items(nested, bid_no))
    return found


def extract_result(payload: dict) -> tuple[str, str]:
    header = payload.get("response", {}).get("header", {}) if isinstance(payload.get("response"), dict) else {}
    return str(header.get("resultCode") or ""), str(header.get("resultMsg") or "")


def _matches_known_bid(text: str, bid_no: str, title_contains: list[str]) -> bool:
    if bid_no and bid_no in text:
        return True
    return any(token and token in text for token in title_contains)


def mask_key(text: str) -> str:
    return text.replace(DATA_GO_KR_SERVICE_KEY, "[MASKED_SERVICE_KEY]")


if __name__ == "__main__":
    raise SystemExit(main())
