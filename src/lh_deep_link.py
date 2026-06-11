from __future__ import annotations

from urllib.parse import urlencode

from src.config import LH_BID_LIST_URL, LH_PORTAL_BASE_URL


LH_ERROR_MARKERS = [
    "프로그램에 오류가 발생",
    "요청하신 서비스를 처리할 수 없습니다",
    "담당자에게 문의",
    "session",
    "exception",
    "error",
]


# Probe-only candidates. These are not shown in the dashboard until a request
# proves that the response body contains the LH bid number or title.
LH_DETAIL_CANDIDATE_PATHS = [
    "/ebid.et.tp.cmd.BidMasterDetailCmd.dev",
    "/ebid.et.tp.cmd.BidDetailCmd.dev",
    "/ebid.et.tp.cmd.BidInfoDetailCmd.dev",
    "/ebid.et.tp.cmd.BidMasterInfoCmd.dev",
    "/ebid.et.tp.cmd.BidMasterDtlCmd.dev",
]


def build_lh_deep_link_candidates(item: dict) -> list[str]:
    bid_num = _bid_num(item)
    if not bid_num:
        return []

    base = (LH_PORTAL_BASE_URL or "https://ebid.lh.or.kr").rstrip("/")
    param_sets = [
        {"bidNum": bid_num},
        {"bidNo": bid_num},
        {"bidNum": bid_num, "bidNo": bid_num},
    ]

    candidates: list[str] = []
    for path in LH_DETAIL_CANDIDATE_PATHS:
        for params in param_sets:
            candidates.append(f"{base}{path}?{urlencode(params)}")
    return _dedupe(candidates)


def build_lh_list_url(item: dict) -> str:
    bid_num = _bid_num(item)
    if not bid_num:
        return LH_BID_LIST_URL
    return f"{LH_BID_LIST_URL}?{urlencode({'bidNum': bid_num})}"


def _bid_num(item: dict) -> str:
    for key in ("source_record_id", "bidNum", "bid_no"):
        value = item.get(key)
        if value not in (None, ""):
            return str(value).strip()
    raw = item.get("raw")
    if isinstance(raw, dict):
        value = raw.get("bidNum")
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    unique = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique
