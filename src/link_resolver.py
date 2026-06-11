from __future__ import annotations

from typing import Any

from src.link_validator import validate_candidate_url


G2B_PORTAL_URL = "https://www.g2b.go.kr/"
LH_PORTAL_URL = "https://ebid.lh.or.kr/"
D2B_PORTAL_URL = "https://www.d2b.go.kr/"


def resolve_link(item: dict[str, Any]) -> dict[str, Any]:
    source_name = str(item.get("source_name") or "")
    raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
    record_id = _source_record_id(item, raw)
    record_no = _source_record_no(item, raw)

    if source_name == "네이버뉴스":
        original = _pick(item, "original_link", "originallink")
        naver_link = _pick(item, "naver_link", "link", "url")
        return _result(
            original or None,
            naver_link or None,
            "exact" if original else "unknown",
            "unchecked",
            original or naver_link or None,
            None,
        )

    if item.get("is_mock") or item.get("data_quality") in {"mock", "sample", "test"}:
        return _result(None, None, str(item.get("link_type") or "mock"), "unchecked", record_id, record_no)

    if source_name in {"나라장터", "G2B", "조달청", "나라장터/G2B", "?섎씪?ν꽣"}:
        return _result(None, G2B_PORTAL_URL, "unknown", "unknown", record_id, record_no)

    direct_url = _pick(
        item,
        "detail_url",
        "original_url",
    ) or _pick(
        raw,
        "bidNtceDtlUrl",
        "ntceDtlUrl",
        "dtlUrl",
        "detailUrl",
    )

    if direct_url and not _is_known_portal_url(direct_url):
        return _result(direct_url, None, "exact", "unchecked", record_id, record_no)

    if source_name == "나라장터":
        return _result(None, G2B_PORTAL_URL, "unknown", "unknown", record_id, record_no)
    if source_name == "LH":
        return _result(None, LH_PORTAL_URL, "unknown", "unknown", record_id, record_no)
    if source_name == "D2B":
        return _result(None, D2B_PORTAL_URL, "unknown", "unknown", record_id, record_no)
    return _result(None, None, "unknown", "unknown", record_id, record_no)


def validate_exact_url(url: str, title: str = "", source_record_id: str = "") -> dict[str, Any]:
    return validate_candidate_url(url, title=title, source_record_id=source_record_id, timeout=12)


def _result(
    original_url: str | None,
    source_search_url: str | None,
    link_type: str,
    link_status: str,
    source_record_id: str | None,
    source_record_no: str | None,
) -> dict[str, Any]:
    return {
        "original_url": original_url,
        "source_search_url": source_search_url,
        "link_type": link_type,
        "link_status": link_status,
        "source_record_id": source_record_id,
        "source_record_no": source_record_no,
    }


def _is_known_portal_url(url: str) -> bool:
    normalized = url.rstrip("/") + "/"
    return normalized in {G2B_PORTAL_URL, LH_PORTAL_URL, D2B_PORTAL_URL}


def _source_record_id(item: dict[str, Any], raw: dict[str, Any]) -> str | None:
    return _pick(
        item,
        "source_record_id",
        "bid_no",
        "notice_no",
        "dcs_no",
        "bidNum",
        "bidNtceNo",
    ) or _pick(
        raw,
        "bidNtceNo",
        "bidNo",
        "bidNum",
        "pblancNo",
        "g2bPblancNo",
        "dcsNo",
        "dcsNoNm",
        "bidNum",
    ) or None


def _source_record_no(item: dict[str, Any], raw: dict[str, Any]) -> str | None:
    return _pick(item, "source_record_no", "bid_order") or _pick(
        raw,
        "bidNtceOrd",
        "bidOdr",
        "pblancOdr",
        "g2bPblancNoOdr",
    ) or None


def _pick(source: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = source.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""
