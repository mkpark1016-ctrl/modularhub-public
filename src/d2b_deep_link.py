from __future__ import annotations

from urllib.parse import urlencode

from src.config import (
    D2B_BID_DEEP_LINK_CANDIDATES,
    D2B_PLAN_DEEP_LINK_CANDIDATES,
    D2B_PORTAL_BASE_URL,
)


D2B_ERROR_MARKERS = [
    "error",
    "exception",
    "session",
    "login",
    "로그인",
    "잘못된 접근",
    "요청하신 서비스를 처리할 수 없습니다",
]


D2B_PLAN_DEFAULT_PATHS = [
    "/internet/ems/prcurePlan/selectPrcurePlanView.do",
    "/internet/ems/prcurePlan/prcurePlanView.do",
    "/internet/ems/prcurePlan/selectPrcurePlanDetail.do",
]
D2B_BID_DEFAULT_PATHS = [
    "/internet/ems/bid/selectBidPblancView.do",
    "/internet/ems/bid/bidPblancView.do",
    "/internet/ems/bid/selectBidPblancDetail.do",
]


def build_d2b_deep_link_candidates(item: dict) -> list[str]:
    source_type = str(item.get("source_type") or "")
    templates = _configured_templates(source_type)
    if templates:
        return _dedupe(_format_template(template, item) for template in templates)

    if source_type == "procurement_plan":
        return _build_default_candidates(item, D2B_PLAN_DEFAULT_PATHS, ("dcsNo", "dcs_no", "dcsnNo"))
    if source_type == "bid":
        return _build_default_candidates(item, D2B_BID_DEFAULT_PATHS, ("bidNo", "pblancNo", "noticeNo"))
    return []


def _build_default_candidates(item: dict, paths: list[str], parameter_names: tuple[str, ...]) -> list[str]:
    record_id = _record_id(item)
    record_no = _record_no(item)
    if not record_id:
        return []

    base = (D2B_PORTAL_BASE_URL or "https://www.d2b.go.kr").rstrip("/")
    candidates = []
    for path in paths:
        for parameter_name in parameter_names:
            params = {parameter_name: record_id}
            candidates.append(f"{base}{path}?{urlencode(params)}")
            if record_no:
                params_with_order = {parameter_name: record_id, "pblancOdr": record_no}
                candidates.append(f"{base}{path}?{urlencode(params_with_order)}")
    return _dedupe(candidates)


def _configured_templates(source_type: str) -> list[str]:
    raw = D2B_PLAN_DEEP_LINK_CANDIDATES if source_type == "procurement_plan" else D2B_BID_DEEP_LINK_CANDIDATES
    return [value.strip() for value in raw.split(";") if value.strip()]


def _format_template(template: str, item: dict) -> str:
    record_id = _record_id(item)
    record_no = _record_no(item)
    base = (D2B_PORTAL_BASE_URL or "https://www.d2b.go.kr").rstrip("/")
    return template.format(
        base=base,
        source_record_id=record_id,
        source_record_no=record_no,
        dcs_no=record_id,
        bid_no=record_id,
        notice_no=record_id,
    )


def _record_id(item: dict) -> str:
    for key in ("source_record_id", "dcs_no", "notice_no", "bid_no"):
        value = item.get(key)
        if value not in (None, ""):
            return str(value).strip()
    raw = item.get("raw")
    if isinstance(raw, dict):
        for key in ("dcsNo", "pblancNo", "bidNo", "bidNum"):
            value = raw.get(key)
            if value not in (None, ""):
                return str(value).strip()
    return ""


def _record_no(item: dict) -> str:
    for key in ("source_record_no", "pblancOdr", "bidOdr"):
        value = item.get(key)
        if value not in (None, ""):
            return str(value).strip()
    raw = item.get("raw")
    if isinstance(raw, dict):
        for key in ("pblancOdr", "bidOdr", "g2bPblancNoOdr", "itemNo", "seq", "sn"):
            value = raw.get(key)
            if value not in (None, ""):
                return str(value).strip()
    return ""


def _dedupe(values) -> list[str]:
    seen = set()
    unique = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique
