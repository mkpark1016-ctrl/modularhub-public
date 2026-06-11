from __future__ import annotations

from datetime import datetime
import json
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd

from src.database import (
    add_favorite,
    get_connection,
    init_db,
    load_collect_logs_dataframe,
    load_favorite_item_ids,
    load_items_dataframe,
    remove_favorite,
)
from src.config import DB_PATH


MANUAL_CHECK_SITES = {
    "나라장터": "https://www.g2b.go.kr",
    "G2B": "https://www.g2b.go.kr",
    "조달청": "https://www.g2b.go.kr",
    "LH": "https://ebid.lh.or.kr",
    "D2B": "https://www.d2b.go.kr",
}


COMMON_ITEM_FIELDS = [
    "id",
    "source_type",
    "source_name",
    "title",
    "organization",
    "posted_at",
    "due_at",
    "amount",
    "region",
    "keywords",
    "relevance_score",
    "source_record_id",
    "source_record_no",
    "business_type",
    "business_subtype",
    "notice_status",
    "operating_scope",
    "is_operating_scope",
    "is_known_important",
    "original_url",
    "source_detail_api_url",
    "link_type",
    "link_status",
    "url",
    "summary",
]


def serialize_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def common_item_from_row(row: dict | pd.Series) -> dict[str, Any]:
    data = dict(row)
    item = {field: serialize_value(data.get(field)) for field in COMMON_ITEM_FIELDS}
    item["source_detail_api_url"] = mask_sensitive_url(item.get("source_detail_api_url"))
    source_name = item.get("source_name")
    item["manual_check_site"] = MANUAL_CHECK_SITES.get(str(source_name or ""))
    return item


def safe_text(value: Any, fallback: str = "") -> str:
    value = serialize_value(value)
    if value is None:
        return fallback
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "nat"}:
        return fallback
    return text


def mask_sensitive_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parts = urlsplit(url)
        query = []
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            if key.lower() in {"servicekey", "apikey", "api_key", "key"}:
                query.append((key, "***"))
            else:
                query.append((key, value))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    except Exception:
        return "[masked_url]"


def load_common_items() -> list[dict[str, Any]]:
    df = load_items_dataframe()
    if df.empty:
        return []
    df = df[(df.get("is_mock", 0) != 1) & (~df.get("data_quality", "real").isin(["mock", "sample", "test"]))]
    return [common_item_from_row(row) for _, row in df.iterrows()]


def query_items(
    *,
    source_type: str | None = None,
    source_names: set[str] | None = None,
    operating_scope: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    items = load_common_items()
    if source_type:
        items = [item for item in items if item.get("source_type") == source_type]
    if source_names:
        items = [item for item in items if item.get("source_name") in source_names]
    if operating_scope:
        items = [item for item in items if item.get("operating_scope") == operating_scope]
    return items[:limit]


def get_bids(limit: int = 200) -> list[dict[str, Any]]:
    return query_items(source_type="bid", limit=limit)


def get_news(limit: int = 200) -> list[dict[str, Any]]:
    return query_items(source_type="news", limit=limit)


def get_rnd_announces(limit: int = 200) -> list[dict[str, Any]]:
    items = query_items(source_type="rnd", limit=limit * 2)
    return [item for item in items if "공고" in str(item.get("summary") or item.get("title") or "")][:limit]


def get_rnd_outcomes(limit: int = 200) -> list[dict[str, Any]]:
    announce_ids = {item["id"] for item in get_rnd_announces(limit=limit * 2)}
    return [item for item in query_items(source_type="rnd", limit=limit * 2) if item["id"] not in announce_ids][:limit]


def get_patents(limit: int = 200) -> list[dict[str, Any]]:
    return query_items(source_type="patent", limit=limit)


def get_favorites(limit: int = 500) -> list[dict[str, Any]]:
    favorite_ids = load_favorite_item_ids()
    return [item for item in load_common_items() if int(item["id"]) in favorite_ids][:limit]


def create_favorite(item_id: int) -> dict[str, Any]:
    add_favorite(item_id)
    return {"ok": True, "item_id": item_id}


def get_item_by_id(item_id: int) -> dict[str, Any] | None:
    init_db(DB_PATH)
    with get_connection(DB_PATH) as conn:
        row = conn.execute("SELECT * FROM items WHERE id = ?", (int(item_id),)).fetchone()
        return dict(row) if row else None


def get_source_detail_for_item(item_id: int) -> dict[str, Any] | None:
    item_row = get_item_by_id(item_id)
    if not item_row:
        return None
    init_db(DB_PATH)
    with get_connection(DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM source_details
            WHERE item_id = ?
            ORDER BY fetched_at DESC, id DESC
            LIMIT 1
            """,
            (int(item_id),),
        ).fetchone()
        if row:
            return sanitize_source_detail(dict(row))

        source_record_id = item_row.get("source_record_id") or item_row.get("bid_no")
        source_record_no = item_row.get("source_record_no") or item_row.get("bid_order")
        if source_record_id and source_record_no:
            row = conn.execute(
                """
                SELECT *
                FROM source_details
                WHERE source_record_id = ?
                  AND COALESCE(source_record_no, '') = COALESCE(?, '')
                ORDER BY fetched_at DESC, id DESC
                LIMIT 1
                """,
                (source_record_id, source_record_no),
            ).fetchone()
            if row:
                return sanitize_source_detail(dict(row))

        if source_record_id:
            row = conn.execute(
                """
                SELECT *
                FROM source_details
                WHERE source_record_id = ?
                ORDER BY fetched_at DESC, id DESC
                LIMIT 1
                """,
                (source_record_id,),
            ).fetchone()
            if row:
                return sanitize_source_detail(dict(row))

    return None


def sanitize_source_detail(detail: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(detail)
    sanitized["detail_api_url"] = mask_sensitive_url(sanitized.get("detail_api_url"))
    return {key: serialize_value(value) for key, value in sanitized.items()}


def parse_detail_payload(detail: dict[str, Any] | None) -> dict | str | None:
    if not detail:
        return None
    payload = detail.get("detail_payload_json")
    if not payload:
        return None
    if isinstance(payload, (dict, list)):
        return payload
    try:
        return json.loads(str(payload))
    except json.JSONDecodeError:
        return str(payload)


def build_manual_check_info(item: dict[str, Any]) -> dict[str, Any]:
    source_name = safe_text(item.get("source_name"))
    source_record_id = safe_text(item.get("source_record_id"))
    source_record_no = safe_text(item.get("source_record_no"))
    title = safe_text(item.get("title"))
    organization = safe_text(item.get("organization"))
    region = safe_text(item.get("region"))

    if source_name in {"나라장터", "G2B", "조달청"}:
        return {
            "site_name": "나라장터",
            "site_url": "https://www.g2b.go.kr",
            "search_keys": {
                "공고번호": source_record_id,
                "공고차수": source_record_no,
                "공고명": title,
                "수요기관": organization,
            },
            "guide_text": "나라장터에서 공고번호 또는 공고명으로 검색해 상세 공고를 확인하세요. 이 버튼은 특정 공고 상세 원문이 아니라 공식 확인 사이트를 여는 기능입니다.",
        }
    if source_name == "LH":
        return {
            "site_name": "LH 전자조달",
            "site_url": "https://ebid.lh.or.kr",
            "search_keys": {
                "공고번호": source_record_id,
                "공고명": title,
                "담당지역": region,
            },
            "guide_text": "LH 전자조달 입찰공고 조회에서 공고번호 또는 공고명으로 검색해 확인하세요.",
        }
    if source_name == "D2B":
        return {
            "site_name": "D2B 국방전자조달",
            "site_url": "https://www.d2b.go.kr",
            "search_keys": {
                "판단번호 또는 공고번호": source_record_id,
                "입찰명": title,
                "발주기관": organization,
            },
            "guide_text": "D2B 통합검색 또는 입찰공고/조달계획 메뉴에서 번호로 검색해 확인하세요.",
        }
    return {
        "site_name": source_name or "출처 사이트",
        "site_url": item.get("manual_check_site"),
        "search_keys": {
            "제목": title,
            "기관": organization,
        },
        "guide_text": "출처 사이트에서 제목 또는 기관명으로 확인하세요.",
    }


def get_available_actions(item: dict[str, Any], source_detail: dict[str, Any] | None) -> list[str]:
    actions = ["favorite"]
    if item.get("original_url") and item.get("source_type") == "news":
        actions.insert(0, "original_exact")
    elif item.get("original_url") and item.get("source_name") not in {"나라장터", "G2B", "조달청", "LH", "D2B"}:
        actions.insert(0, "original_exact")
    if source_detail or item.get("source_detail_api_url"):
        actions.append("api_detail")
    if build_manual_check_info(item).get("site_url"):
        actions.append("manual_check")
    return list(dict.fromkeys(actions))


def get_item_detail(item_id: int) -> dict[str, Any]:
    row = get_item_by_id(item_id)
    if not row:
        raise KeyError(f"item not found: {item_id}")
    item = common_item_from_row(row)
    source_detail = get_source_detail_for_item(item_id)
    return {
        "item": item,
        "source_detail": source_detail,
        "detail_payload_json": parse_detail_payload(source_detail),
        "manual_check": build_manual_check_info(item),
        "available_actions": get_available_actions(item, source_detail),
    }


def delete_favorite(item_id: int) -> dict[str, Any]:
    remove_favorite(item_id)
    return {"ok": True, "item_id": item_id}


def get_health() -> dict[str, Any]:
    init_db(DB_PATH)
    logs = load_collect_logs_dataframe(limit=200)
    last_collected_at = None
    if not logs.empty:
        started = pd.to_datetime(logs["started_at"], errors="coerce")
        last_collected_at = serialize_value(started.max())

    def source_status(name_contains: str, pending: bool = False) -> str:
        if pending:
            return "pending"
        if logs.empty:
            return "unknown"
        matched = logs[logs["collector_name"].fillna("").str.contains(name_contains, case=False, regex=False)]
        if matched.empty:
            return "unknown"
        success = matched[matched["status"].eq("success")]
        if success.empty:
            return "error"
        latest = pd.to_datetime(success.iloc[0]["started_at"], errors="coerce")
        return f"last_success:{serialize_value(latest)}"

    return {
        "server": "online",
        "database": "connected" if DB_PATH.exists() else "missing",
        "g2b": source_status("나라장터"),
        "dapa": source_status("D2B"),
        "naver": source_status("네이버뉴스"),
        "kipris": source_status("KIPRIS", pending=True),
        "kci": source_status("KCI", pending=True),
        "last_collected_at": last_collected_at,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }


def get_trends() -> dict[str, Any]:
    df = load_items_dataframe()
    if df.empty:
        return {
            "total_items": 0,
            "source_count": 0,
            "keyword_count": 0,
            "keyword_frequency": {},
            "source_counts": {},
            "daily_counts": {},
        }
    df = df[(df.get("is_mock", 0) != 1) & (~df.get("data_quality", "real").isin(["mock", "sample", "test"]))]
    keyword_frequency: dict[str, int] = {}
    for keywords in df.get("keywords", pd.Series(dtype=str)).dropna():
        for keyword in str(keywords).split(";"):
            clean = keyword.strip()
            if clean:
                keyword_frequency[clean] = keyword_frequency.get(clean, 0) + 1
    posted = pd.to_datetime(df.get("posted_at"), errors="coerce")
    daily_counts = posted.dt.date.astype(str).value_counts().sort_index().tail(30).to_dict()
    source_counts = df.get("source_name", pd.Series(dtype=str)).fillna("unknown").value_counts().to_dict()
    return {
        "total_items": int(len(df)),
        "source_count": int(df.get("source_name", pd.Series(dtype=str)).nunique()),
        "keyword_count": int(len(keyword_frequency)),
        "keyword_frequency": dict(sorted(keyword_frequency.items(), key=lambda item: item[1], reverse=True)[:30]),
        "source_counts": {str(key): int(value) for key, value in source_counts.items()},
        "daily_counts": {str(key): int(value) for key, value in daily_counts.items()},
    }


def get_api_manifest() -> dict[str, Any]:
    return {
        "endpoints": [
            "GET /api/health",
            "GET /api/bids",
            "GET /api/news",
            "GET /api/rnd-announces",
            "GET /api/rnd-outcomes",
            "GET /api/patents",
            "GET /api/trends",
            "GET /api/favorites",
            "POST /api/favorites",
            "DELETE /api/favorites/{id}",
        ],
        "common_item_fields": COMMON_ITEM_FIELDS + ["manual_check_site"],
    }
