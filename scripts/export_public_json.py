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

from src.config import DB_PATH, D2B_LEGACY_API_ENABLED  # noqa: E402
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
    source_type = clean_text(row.get("source_type"))
    record_no = clean_text(row.get("bid_no") or row.get("source_record_id"))
    return {
        "id": item_id,
        "source": clean_text(row.get("source_name")),
        "source_name": clean_text(row.get("source_name")),
        "source_type": source_type,
        "type": "발주계획" if source_type == "procurement_plan" else "입찰공고",
        "title": clean_text(row.get("title")),
        "organization": clean_text(row.get("organization")),
        "demand_org": clean_text(row.get("demand_org")),
        "business_type": clean_text(row.get("business_type")),
        "business_subtype": clean_text(row.get("business_subtype")),
        "notice_status": clean_text(row.get("notice_status")),
        "plan_no": record_no if source_type == "procurement_plan" else "",
        "bid_no": record_no,
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


def procurement_plan_collection_status(logs: Any) -> tuple[str, dict[str, str], str | None]:
    if logs.empty or "source_type" not in logs.columns:
        return "not_collected", {}, None
    plan_logs = logs[logs["source_type"].eq("procurement_plan")].copy()
    if plan_logs.empty:
        return "not_collected", {}, None

    source_status: dict[str, str] = {}
    latest_at: str | None = None
    for collector_name, group in plan_logs.groupby("collector_name", sort=False):
        latest = group.iloc[0]
        source_status[clean_text(collector_name)] = clean_text(latest.get("status")) or "unknown"
        checked_at = clean_text(latest.get("finished_at") or latest.get("started_at"))
        if checked_at and (latest_at is None or checked_at > latest_at):
            latest_at = checked_at

    statuses = set(source_status.values())
    if statuses == {"success"}:
        return "success", source_status, latest_at
    if "success" in statuses:
        return "partial_warning", source_status, latest_at
    return "failed", source_status, latest_at


def latest_log(logs: Any, collector_name: str, source_type: str | None = None) -> dict[str, Any] | None:
    if logs.empty:
        return None
    matches = logs[logs["collector_name"].eq(collector_name)]
    if source_type:
        matches = matches[matches["source_type"].eq(source_type)]
    if matches.empty:
        return None
    return matches.iloc[0].to_dict()


def collector_public_status(
    logs: Any,
    *,
    collector_name: str,
    source_type: str,
    exported_count: int,
) -> tuple[str, str]:
    log = latest_log(logs, collector_name, source_type)
    if not log:
        return "not_collected", f"{collector_name} {source_type} 수집 실행 기록이 없습니다."
    if clean_text(log.get("status")) != "success":
        error = sanitize_string(clean_text(log.get("error_message")))
        error_lower = error.lower()
        if "auth_error" in error_lower or any(
            token in error_lower for token in ("servicekey", "service key", "data_go_kr_service_key")
        ):
            error = "나라장터 발주계획 인증 또는 활용신청 상태를 확인하세요."
        elif "not_found_operation" in error_lower or "http 404" in error_lower:
            error = (
                "나라장터 발주계획 operation을 찾지 못했습니다. "
                "공식 endpoint OrderPlanSttusService와 업무별 operation path를 확인하세요."
            )
        elif "param_error" in error_lower:
            error = "나라장터 발주계획 필수 파라미터와 날짜 형식을 확인하세요."
        elif "parse_error" in error_lower:
            error = "나라장터 발주계획 응답 형식을 파싱하지 못했습니다. JSON/XML 응답을 확인하세요."
        return "failed", error or f"{collector_name} {source_type} API 호출에 실패했습니다."
    if exported_count == 0:
        return "success_no_match", "정상 호출되었으나 현재 조회기간 내 모듈러 매칭 데이터가 없습니다."
    return "success", f"정상 호출되어 {exported_count}건을 공개 데이터에 반영했습니다."


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
    plan_status, plan_source_status, plan_collected_at = procurement_plan_collection_status(logs)
    last_collected_at = None
    warning_count = 0
    if not logs.empty:
        successful = logs[logs["status"].eq("success")]
        if not successful.empty:
            dates = successful["finished_at"].fillna(successful["started_at"])
            last_collected_at = clean_text(dates.iloc[0]) or None
        warning_count = int((logs["status"] != "success").sum())

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    plan_count = sum(item.get("source_type") == "procurement_plan" for item in business)
    g2b_plan_count = sum(
        item.get("source_type") == "procurement_plan" and item.get("source") in {"나라장터", "G2B", "조달청"}
        for item in business
    )
    g2b_status, g2b_message = collector_public_status(
        logs,
        collector_name="나라장터",
        source_type="procurement_plan",
        exported_count=g2b_plan_count,
    )
    if D2B_LEGACY_API_ENABLED:
        d2b_log = latest_log(logs, "D2B")
        if d2b_log and clean_text(d2b_log.get("status")) == "success":
            d2b_status, d2b_message = "success", "D2B 기존 API 수집이 정상 완료되었습니다."
        else:
            d2b_status = "warning"
            d2b_message = sanitize_string(clean_text((d2b_log or {}).get("error_message"))) or "D2B 기존 API 수집 상태를 확인하세요."
    else:
        d2b_status = "disabled_stopped"
        d2b_message = "방위사업청 기존 군수품조달정보 API가 중지 상태입니다. 추후 GW API 전환이 필요합니다."

    warnings: list[str] = []
    if g2b_status in {"failed", "not_collected"}:
        warnings.append(f"나라장터 발주계획: {g2b_message}")
    if d2b_status != "success":
        warnings.append(f"D2B: {d2b_message}")
    workflow_status = "warning" if warnings else "success"
    common_status = {
        "g2b_order_plan_status": g2b_status,
        "g2b_order_plan_message": g2b_message,
        "d2b_status": d2b_status,
        "d2b_message": d2b_message,
        "workflow_last_run_status": workflow_status,
        "warnings": warnings,
    }
    write_json(
        "business.json",
        {
            "generated_at": generated_at,
            "procurement_plan_count": plan_count,
            "procurement_plan_collection_status": plan_status,
            "procurement_plan_source_status": plan_source_status,
            "procurement_plan_last_collected_at": plan_collected_at,
            **common_status,
            "items": business,
        },
    )
    write_json("news.json", {"generated_at": generated_at, "items": news})
    write_json(
        "meta.json",
        {
            "generated_at": generated_at,
            "business_count": len(business),
            "procurement_plan_count": plan_count,
            "procurement_plan_collection_status": plan_status,
            "procurement_plan_source_status": plan_source_status,
            "procurement_plan_last_collected_at": plan_collected_at,
            "news_count": len(news),
            "sources": sorted({item["source"] for item in business + news}),
            "last_collected_at": last_collected_at,
            "warning_count": len(warnings) if warnings else warning_count,
            **common_status,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
