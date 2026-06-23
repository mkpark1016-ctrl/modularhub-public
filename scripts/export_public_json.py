from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import DB_PATH, D2B_LEGACY_API_ENABLED  # noqa: E402
from src.database import init_db, load_collect_logs_dataframe, load_items_dataframe  # noqa: E402
from src.public_data_policy import guard_result, merge_public_items, payload_items  # noqa: E402


OUTPUT_DIR = ROOT / "frontend" / "public" / "data"
BUSINESS_SOURCES = {"나라장터", "G2B", "조달청", "D2B", "국방조달", "방위사업청"}
BUSINESS_TYPES = {"bid", "procurement_plan", "public_agency_contest"}
PUBLIC_AGENCY_CONTEST_SOURCES = {"LH", "GH", "iH", "SH"}
PUBLIC_AGENCY_CONTEST_COLLECTORS = {
    "LH": ("LHPublicHousingContestCollector", "LH 공모안내"),
    "GH": ("GHPublicHousingContestCollector", "GH 공모 관련사항"),
    "iH": ("IHPublicHousingContestCollector", "iH 공지사항"),
    "SH": ("SHPublicHousingContestCollector", "SH 사업발주·공지"),
}
PUBLIC_AGENCY_BOARD_URLS = {
    "LH": "https://www.lh.or.kr/board.es?mid=a10601020000&bid=0034",
    "GH": "https://www.gh.or.kr/gh/bid-announcement.do",
    "iH": "https://www.ih.co.kr/main/customer/notification/notice.jsp",
    "SH": "https://www.i-sh.co.kr/main/lay2/program/S1T1C222/subMain4.do?menu=instOpenResultCdList",
}
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
    source_type = clean_text(row.get("source_type"))
    bid_no = clean_text(row.get("source_record_id") or row.get("bid_no"))
    bid_order = clean_text(row.get("source_record_no") or row.get("bid_order"))
    title = clean_text(row.get("title"))
    organization = clean_text(row.get("organization"))
    if source_type == "public_agency_contest" and source in PUBLIC_AGENCY_CONTEST_SOURCES:
        site_name = PUBLIC_AGENCY_CONTEST_COLLECTORS.get(source, ("", f"{source} 공식 게시판"))[1]
        site_url = PUBLIC_AGENCY_BOARD_URLS.get(source, "")
        guide = f"{site_name}에서 공모명 또는 원문 식별번호로 상세 공고와 첨부파일을 확인하세요."
    elif source in {"나라장터", "G2B", "조달청"}:
        site_name, site_url = "나라장터", "https://www.g2b.go.kr"
        guide = "나라장터에서 공고번호 또는 공고명으로 검색해 상세 공고를 확인하세요."
    else:
        site_name, site_url = "D2B 국방전자조달", "https://www.d2b.go.kr"
        guide = "D2B 통합검색 또는 입찰공고·조달계획 메뉴에서 번호나 사업명으로 확인하세요."
    search_text = " ".join(part for part in (bid_no, bid_order, title, organization) if part)
    return {"site_name": site_name, "site_url": site_url, "search_text": search_text, "guide_text": guide}


def exact_original_url(row: dict[str, Any]) -> str | None:
    url = clean_text(row.get("original_url"))
    if not url or clean_text(row.get("link_type")) not in {"exact", "exact_original"}:
        return None
    if int(row.get("exact_url_verified") or 0) != 1 or clean_text(row.get("link_status")) != "ok":
        return None
    return sanitize_url(url) or None


def business_item(row: dict[str, Any], details: dict[int, dict[str, Any]]) -> dict[str, Any]:
    item_id = int(row["id"])
    detail_row = details.get(item_id)
    source_type = clean_text(row.get("source_type"))
    source_name = clean_text(row.get("source_name"))
    record_no = clean_text(row.get("bid_no") or row.get("source_record_id"))
    detail_payload = parse_payload(detail_row.get("detail_payload_json")) if detail_row else None
    detail = detail_payload if isinstance(detail_payload, dict) else {}
    source_record_id = clean_text(row.get("source_record_id"))
    source_code = clean_text(detail.get("source_code"))
    if not source_code and source_type == "public_agency_contest":
        source_code = {"LH": "LH_CONTEST", "GH": "GH_CONTEST", "iH": "IH_NOTICE", "SH": "SH_CONTEST"}.get(source_name, "")
    public_id: int | str = item_id
    if source_type == "public_agency_contest" and source_name in {"GH", "iH", "SH"} and source_record_id:
        public_id = f"{source_name.lower()}_contest:{source_record_id}"
    item_type = "민간사업자 공모" if source_type == "public_agency_contest" else (
        "발주계획" if source_type == "procurement_plan" else "입찰공고"
    )
    original_url = exact_original_url(row)
    item = {
        "id": public_id,
        "source": source_name,
        "source_name": source_name,
        "source_type": source_type,
        "type": item_type,
        "title": clean_text(row.get("title")),
        "organization": clean_text(row.get("organization")),
        "demand_org": clean_text(row.get("demand_org")),
        "business_type": clean_text(row.get("business_type")),
        "business_subtype": clean_text(row.get("business_subtype")),
        "notice_status": clean_text(row.get("notice_status")),
        "notice_stage": clean_text(row.get("notice_status") or detail.get("notice_stage")),
        "source_record_id": source_record_id,
        "source_record_no": clean_text(row.get("source_record_no")),
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
        "is_operating_scope": bool(row.get("is_operating_scope")),
        "display_type": clean_text(detail.get("display_type")) or item_type,
        "modular_relevance": clean_text(detail.get("modular_relevance")),
        "modular_evidence": detail.get("modular_evidence") or [],
        "project_name": clean_text(detail.get("project_name")),
        "project_sites": detail.get("project_sites") or [],
        "project_blocks": detail.get("project_blocks") or [],
        "application_schedule_text": clean_text(detail.get("application_schedule_text")),
        "household_count": scalar(detail.get("household_count")),
        "housing_type": clean_text(detail.get("housing_type")),
        "attachments": detail.get("attachments") or [],
        "related_group_key": clean_text(detail.get("related_group_key")),
        "exact_link_verified": bool(row.get("exact_url_verified")),
        "external_original_url": original_url,
        "manual_check": manual_check(row),
        "detail": detail_payload,
    }
    if source_type == "public_agency_contest":
        item["source_code"] = source_code
        item["link_verified"] = bool(row.get("exact_url_verified"))
        item["original_url"] = original_url
    return item


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


def load_existing_payload(name: str) -> dict[str, Any]:
    path = OUTPUT_DIR / name
    if not path.exists():
        return {"items": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"WARNING: 기존 {name}을 읽지 못해 빈 기준으로 병합합니다: {exc}")
        return {"items": []}
    if isinstance(payload, list):
        return {"items": payload}
    return payload if isinstance(payload, dict) else {"items": []}


def load_git_head_payload(name: str) -> dict[str, Any] | None:
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:frontend/public/data/{name}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        payload = json.loads(result.stdout)
    except Exception:
        return None
    if isinstance(payload, list):
        return {"items": payload}
    return payload if isinstance(payload, dict) else {"items": []}


def normalize_existing_public_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    contest_only_fields = {"source_code", "link_verified", "original_url"}
    for item in items:
        copied = dict(item)
        if clean_text(copied.get("source_type")) != "public_agency_contest":
            for field in contest_only_fields:
                copied.pop(field, None)
        normalized.append(copied)
    return normalized


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


def public_agency_contest_public_meta(
    logs: Any,
    business: list[dict[str, Any]],
    *,
    source: str,
) -> dict[str, Any]:
    collector_name, label = PUBLIC_AGENCY_CONTEST_COLLECTORS[source]
    items = [
        item
        for item in business
        if item.get("source") == source and item.get("source_type") == "public_agency_contest"
    ]
    count = len(items)
    exact_link_count = sum(1 for item in items if item.get("external_original_url"))
    log = latest_log(logs, collector_name, "public_agency_contest")
    stats: dict[str, Any] = {}
    if log and clean_text(log.get("error_message")):
        try:
            parsed_stats = json.loads(clean_text(log.get("error_message")))
            if isinstance(parsed_stats, dict):
                stats = sanitize_payload(parsed_stats)
        except json.JSONDecodeError:
            stats = {"message": sanitize_string(clean_text(log.get("error_message")))}

    if not log:
        status = "not_collected" if count == 0 else "previous_data_retained"
        message = f"{label} 수집 기록이 아직 없습니다."
    elif clean_text(log.get("status")) in {"success", "partial_warning"}:
        status = "success" if count > 0 else "success_no_public_match"
        message = f"{label} {count}건을 공개 사업정보에 반영했습니다."
    else:
        status = "failed"
        message = sanitize_string(clean_text(log.get("error_message"))) or f"{label} 수집에 실패했습니다."

    prefix = source.lower().replace("ih", "ih")
    return {
        f"{prefix}_contest_status": status,
        f"{prefix}_contest_message": message,
        f"{prefix}_contest_last_attempt": clean_text((log or {}).get("started_at")),
        f"{prefix}_contest_last_success": clean_text((log or {}).get("finished_at"))
        if log and clean_text(log.get("status")) in {"success", "partial_warning"}
        else "",
        f"{prefix}_contest_scanned_count": scalar(stats.get("scanned")),
        f"{prefix}_contest_matched_count": scalar(stats.get("matched")),
        f"{prefix}_contest_opportunity_count": scalar(stats.get("opportunity")),
        f"{prefix}_contest_inserted_count": scalar(stats.get("inserted")),
        f"{prefix}_contest_updated_count": scalar(stats.get("updated")),
        f"{prefix}_contest_public_count": count,
        f"{prefix}_contest_exact_link_count": exact_link_count,
        f"{prefix}_contest_attachment_count": scalar(stats.get("attachment_count")),
        f"{prefix}_contest_failure_reason": "; ".join(stats.get("errors") or []),
    }


def include_business_row(row: dict[str, Any]) -> bool:
    source_name = clean_text(row.get("source_name"))
    source_type = clean_text(row.get("source_type"))
    if source_type == "public_agency_contest":
        return (
            source_name in PUBLIC_AGENCY_CONTEST_SOURCES
            and clean_text(row.get("business_type")) == "private_participation_public_housing"
            and int(row.get("is_operating_scope") or 0) == 1
        )
    if source_name not in BUSINESS_SOURCES or source_type not in BUSINESS_TYPES:
        return False
    if bool(row.get("is_known_important")):
        return True
    if contains_modular(row.get("title"), row.get("summary"), row.get("keywords")):
        return True
    return False


def main() -> int:
    previous_business_payload = load_existing_payload("business.json")
    previous_news_payload = load_existing_payload("news.json")
    previous_business = payload_items(previous_business_payload)
    previous_news = payload_items(previous_news_payload)
    baseline_business_payload = load_git_head_payload("business.json") or previous_business_payload
    baseline_news_payload = load_git_head_payload("news.json") or previous_news_payload
    baseline_business = payload_items(baseline_business_payload)
    baseline_news = payload_items(baseline_news_payload)
    previous_business = normalize_existing_public_items(previous_business)
    baseline_business = normalize_existing_public_items(baseline_business)

    df = load_items_dataframe()
    if df.empty:
        rows: list[dict[str, Any]] = []
    else:
        df = df[(df["is_mock"].fillna(0) != 1) & (~df["data_quality"].fillna("real").isin(["mock", "sample", "test"]))]
        rows = df.to_dict(orient="records")
    details = load_latest_details()

    business_rows = [
        row for row in rows
        if include_business_row(row)
    ]
    news_rows = [
        row for row in rows
        if clean_text(row.get("source_type")) == "news"
        and contains_modular(row.get("title"), row.get("summary"), row.get("keywords"))
        and clean_text(row.get("original_url"))
    ]

    current_business = [business_item(row, details) for row in business_rows]
    current_news = [news_item(row) for row in news_rows]
    merge_time = datetime.now(timezone.utc)
    business = merge_public_items(previous_business, current_business, kind="business", now=merge_time)
    news = merge_public_items(previous_news, current_news, kind="news", now=merge_time)

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
    lh_contest_items = [
        item
        for item in business
        if item.get("source") == "LH" and item.get("source_type") == "public_agency_contest"
    ]
    lh_contest_count = len(lh_contest_items)
    lh_exact_link_count = sum(1 for item in lh_contest_items if item.get("external_original_url"))
    lh_log = latest_log(logs, "LHPublicHousingContestCollector", "public_agency_contest")
    lh_stats: dict[str, Any] = {}
    if lh_log and clean_text(lh_log.get("error_message")):
        try:
            parsed_lh_stats = json.loads(clean_text(lh_log.get("error_message")))
            if isinstance(parsed_lh_stats, dict):
                lh_stats = sanitize_payload(parsed_lh_stats)
        except json.JSONDecodeError:
            lh_stats = {"message": sanitize_string(clean_text(lh_log.get("error_message")))}
    if not lh_log:
        lh_status = "not_collected" if lh_contest_count == 0 else "previous_data_retained"
        lh_message = "LH 민간참여 공공주택 공모 수집 기록이 아직 없습니다."
    elif clean_text(lh_log.get("status")) in {"success", "partial_warning"}:
        lh_status = "success" if lh_contest_count > 0 else "success_no_public_match"
        lh_message = f"LH 민간참여 공공주택 공모 {lh_contest_count}건을 공개 사업정보에 반영했습니다."
    else:
        lh_status = "failed"
        lh_message = sanitize_string(clean_text(lh_log.get("error_message"))) or "LH 공모 수집에 실패했습니다."
    gh_contest_meta = public_agency_contest_public_meta(logs, business, source="GH")
    ih_contest_meta = public_agency_contest_public_meta(logs, business, source="iH")
    sh_contest_meta = public_agency_contest_public_meta(logs, business, source="SH")
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

    guard_status, guard_message = guard_result(
        previous_business=len(baseline_business),
        merged_business=len(business),
        previous_news=len(baseline_news),
        merged_news=len(news),
        allow_shrink=os.getenv("ALLOW_PUBLIC_DATA_SHRINK", "false").lower() in {"1", "true", "yes", "y"},
    )

    warnings: list[str] = []
    if g2b_status in {"failed", "not_collected"}:
        warnings.append(f"나라장터 발주계획: {g2b_message}")
    if d2b_status != "success":
        warnings.append(f"D2B: {d2b_message}")
    if lh_status == "failed":
        warnings.append(f"LH 민간사업자 공모: {lh_message}")
    if gh_contest_meta.get("gh_contest_status") == "failed":
        warnings.append(f"GH 민간사업자 공모: {gh_contest_meta.get('gh_contest_message')}")
    if ih_contest_meta.get("ih_contest_status") == "failed":
        warnings.append(f"iH 민간사업자 공모: {ih_contest_meta.get('ih_contest_message')}")
    if sh_contest_meta.get("sh_contest_status") == "failed":
        warnings.append(f"SH 민간사업자 공모: {sh_contest_meta.get('sh_contest_message')}")
    if guard_status in {"blocked", "warning", "override"}:
        warnings.append(f"공개 데이터 보호: {guard_message}")
    workflow_status = "warning" if warnings else "success"
    common_status = {
        "g2b_order_plan_status": g2b_status,
        "g2b_order_plan_message": g2b_message,
        "d2b_status": d2b_status,
        "d2b_message": d2b_message,
        "d2b_legacy_status": d2b_status,
        "d2b_gw_migration_required": True,
        "lh_contest_status": lh_status,
        "lh_contest_message": lh_message,
        "lh_contest_last_attempt": clean_text((lh_log or {}).get("started_at")),
        "lh_contest_last_success": clean_text((lh_log or {}).get("finished_at"))
        if lh_log and clean_text(lh_log.get("status")) in {"success", "partial_warning"}
        else "",
        "lh_contest_scanned_count": scalar(lh_stats.get("scanned")),
        "lh_contest_matched_count": scalar(lh_stats.get("matched")),
        "lh_contest_inserted_count": scalar(lh_stats.get("inserted")),
        "lh_contest_updated_count": scalar(lh_stats.get("updated")),
        "lh_contest_public_count": lh_contest_count,
        "lh_contest_exact_link_count": lh_exact_link_count,
        "lh_contest_failure_reason": "; ".join(lh_stats.get("errors") or []),
        **gh_contest_meta,
        **ih_contest_meta,
        **sh_contest_meta,
        "workflow_last_run_status": workflow_status,
        "warnings": warnings,
        "previous_business_count": len(baseline_business),
        "current_business_count": len(current_business),
        "merged_business_count": len(business),
        "previous_news_count": len(baseline_news),
        "current_news_count": len(current_news),
        "merged_news_count": len(news),
        "public_data_guard_status": guard_status,
        "public_data_guard_message": guard_message,
        "data_policy": "cumulative_verified",
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
    write_json(
        "news.json",
        {
            "generated_at": generated_at,
            "data_policy": "cumulative_verified",
            "previous_news_count": len(baseline_news),
            "current_news_count": len(current_news),
            "merged_news_count": len(news),
            "items": news,
        },
    )
    write_json(
        "meta.json",
        {
            "generated_at": generated_at,
            "last_updated": generated_at,
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
