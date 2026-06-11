from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import DB_PATH  # noqa: E402
from src.database import init_db, load_collect_logs_dataframe, load_items_dataframe  # noqa: E402


OUTPUT_DIR = ROOT / "frontend" / "public" / "data"
BUSINESS_SOURCES = {"나라장터", "G2B", "조달청", "D2B", "국방조달", "방위사업청"}
BUSINESS_TYPES = {"bid", "procurement_plan"}
MODULAR_TERMS = ("모듈러", "osc", "공업화주택", "프리패브", "프리팹")
SENSITIVE_KEY_PARTS = (
    "servicekey",
    "service_key",
    "data_go_kr_service_key",
    "naver_client_secret",
    "naver_client_id",
    "api_key",
    "apikey",
    "database_path",
    "db_path",
)
SENSITIVE_QUERY_KEYS = {"servicekey", "apikey", "api_key", "key", "client_secret", "client_id"}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "none", "nan", "nat"} else text


def scalar(value: Any) -> Any:
    if value is None:
        return None
    try:
        if value != value:
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def contains_modular(*values: Any) -> bool:
    text = " ".join(clean_text(value) for value in values).lower()
    compact = re.sub(r"[\s·ㆍ\-_()\[\]]+", "", text)
    return any(term.replace(" ", "") in compact for term in MODULAR_TERMS)


def sanitize_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"}:
            return ""
        query = [
            (key, val)
            for key, val in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in SENSITIVE_QUERY_KEYS
        ]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    except Exception:
        return ""


def sanitize_string(value: str) -> str:
    text = value
    for name in SENSITIVE_KEY_PARTS:
        text = re.sub(
            rf"(?i)({re.escape(name)})(\s*[=:]\s*|%3[dD])([^&\s\"'<>]+)",
            r"\1\2[REDACTED]",
            text,
        )
    text = re.sub(r"(?i)(serviceKey|client_secret|client_id|api_key)=([^&\s\"'<>]+)", r"\1=[REDACTED]", text)
    return text


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, nested in value.items():
            normalized = str(key).lower().replace("-", "_")
            if any(part in normalized for part in SENSITIVE_KEY_PARTS):
                continue
            if normalized in {"detail_api_url", "source_detail_api_url", "raw_url", "request_url"}:
                continue
            result[str(key)] = sanitize_payload(nested)
        return result
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, str):
        cleaned = sanitize_string(value)
        if cleaned.startswith(("http://", "https://")):
            return sanitize_url(cleaned)
        return cleaned
    return scalar(value)


def parse_payload(raw: Any) -> Any:
    text = clean_text(raw)
    if not text:
        return None
    try:
        return sanitize_payload(json.loads(text))
    except json.JSONDecodeError:
        return sanitize_payload(text)


def load_latest_details() -> dict[int, dict[str, Any]]:
    init_db(DB_PATH)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT sd.*
            FROM source_details sd
            INNER JOIN (
                SELECT item_id, MAX(id) AS latest_id
                FROM source_details
                GROUP BY item_id
            ) latest ON latest.latest_id = sd.id
            """
        ).fetchall()
    return {int(row["item_id"]): dict(row) for row in rows}


def manual_check(row: dict[str, Any]) -> dict[str, str]:
    source = clean_text(row.get("source_name"))
    bid_no = clean_text(row.get("source_record_id") or row.get("bid_no"))
    bid_order = clean_text(row.get("source_record_no") or row.get("bid_order"))
    title = clean_text(row.get("title"))
    organization = clean_text(row.get("organization"))
    if source in {"나라장터", "G2B", "조달청"}:
        site_name, site_url = "나라장터", "https://www.g2b.go.kr"
        guide = "나라장터에서 공고번호 또는 공고명으로 검색해 상세 공고를 확인하세요."
    else:
        site_name, site_url = "D2B 국방전자조달", "https://www.d2b.go.kr"
        guide = "D2B 통합검색 또는 입찰공고·조달계획 메뉴에서 번호나 사업명으로 확인하세요."
    search_text = " ".join(part for part in (bid_no, bid_order, title, organization) if part)
    return {"site_name": site_name, "site_url": site_url, "search_text": search_text, "guide_text": guide}


def exact_original_url(row: dict[str, Any]) -> str | None:
    url = clean_text(row.get("original_url"))
    if not url or clean_text(row.get("link_type")) != "exact":
        return None
    if int(row.get("exact_url_verified") or 0) != 1 or clean_text(row.get("link_status")) != "ok":
        return None
    return sanitize_url(url) or None


def business_item(row: dict[str, Any], details: dict[int, dict[str, Any]]) -> dict[str, Any]:
    item_id = int(row["id"])
    detail_row = details.get(item_id)
    return {
        "id": item_id,
        "source": clean_text(row.get("source_name")),
        "source_type": clean_text(row.get("source_type")),
        "title": clean_text(row.get("title")),
        "organization": clean_text(row.get("organization")),
        "demand_org": clean_text(row.get("demand_org")),
        "business_type": clean_text(row.get("business_type")),
        "business_subtype": clean_text(row.get("business_subtype")),
        "notice_status": clean_text(row.get("notice_status")),
        "bid_no": clean_text(row.get("bid_no") or row.get("source_record_id")),
        "bid_order": clean_text(row.get("bid_order") or row.get("source_record_no")),
        "posted_at": scalar(row.get("posted_at")),
        "due_at": scalar(row.get("due_at")),
        "amount": scalar(row.get("amount")),
        "region": clean_text(row.get("region")),
        "summary": clean_text(row.get("summary")),
        "keywords": clean_text(row.get("keywords")),
        "relevance_score": scalar(row.get("relevance_score")) or 0,
        "is_known_important": bool(row.get("is_known_important")),
        "external_original_url": exact_original_url(row),
        "manual_check": manual_check(row),
        "detail": parse_payload(detail_row.get("detail_payload_json")) if detail_row else None,
    }


def news_item(row: dict[str, Any]) -> dict[str, Any]:
    original_url = sanitize_url(clean_text(row.get("original_url")))
    naver_url = sanitize_url(clean_text(row.get("source_search_url") or row.get("url")))
    return {
        "id": int(row["id"]),
        "source": clean_text(row.get("source_name")),
        "media": clean_text(row.get("organization")),
        "title": clean_text(row.get("title")),
        "summary": clean_text(row.get("summary")),
        "published_at": scalar(row.get("posted_at")),
        "original_url": original_url or None,
        "naver_url": naver_url or None,
        "keywords": clean_text(row.get("keywords")),
        "relevance_score": scalar(row.get("relevance_score")) or 0,
    }


def write_json(name: str, payload: object) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


def main() -> int:
    df = load_items_dataframe()
    if df.empty:
        rows: list[dict[str, Any]] = []
    else:
        df = df[(df["is_mock"].fillna(0) != 1) & (~df["data_quality"].fillna("real").isin(["mock", "sample", "test"]))]
        rows = df.to_dict(orient="records")
    details = load_latest_details()

    business_rows = [
        row for row in rows
        if clean_text(row.get("source_name")) in BUSINESS_SOURCES
        and clean_text(row.get("source_type")) in BUSINESS_TYPES
        and (contains_modular(row.get("title"), row.get("summary"), row.get("keywords")) or bool(row.get("is_known_important")))
    ]
    news_rows = [
        row for row in rows
        if clean_text(row.get("source_type")) == "news"
        and contains_modular(row.get("title"), row.get("summary"), row.get("keywords"))
        and clean_text(row.get("original_url"))
    ]

    business = [business_item(row, details) for row in business_rows]
    news = [news_item(row) for row in news_rows]
    business.sort(key=lambda item: (clean_text(item.get("posted_at")), item["id"]), reverse=True)
    news.sort(key=lambda item: (clean_text(item.get("published_at")), item["id"]), reverse=True)

    logs = load_collect_logs_dataframe(limit=500)
    last_collected_at = None
    warning_count = 0
    if not logs.empty:
        successful = logs[logs["status"].eq("success")]
        if not successful.empty:
            dates = successful["finished_at"].fillna(successful["started_at"])
            last_collected_at = clean_text(dates.iloc[0]) or None
        warning_count = int((logs["status"] != "success").sum())

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    write_json("business.json", {"generated_at": generated_at, "items": business})
    write_json("news.json", {"generated_at": generated_at, "items": news})
    write_json(
        "meta.json",
        {
            "generated_at": generated_at,
            "business_count": len(business),
            "news_count": len(news),
            "sources": sorted({item["source"] for item in business + news}),
            "last_collected_at": last_collected_at,
            "warning_count": warning_count,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
