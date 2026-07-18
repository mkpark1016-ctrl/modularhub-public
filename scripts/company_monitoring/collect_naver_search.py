from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.company_monitoring.classify_candidate import classify_text  # noqa: E402
from scripts.company_monitoring.common import (  # noqa: E402
    fail_source,
    iso_now,
    live_opt_in_enabled,
    live_opt_in_error,
    load_monitoring_environment,
    load_monitor_companies,
    load_query_keywords,
    masked_config_status,
    parse_common_args,
    parse_company_arg,
    safe_error_message,
    strip_html,
    write_json,
)
from scripts.company_monitoring.normalize_candidate import make_candidate  # noqa: E402


DEFAULT_NAVER_API_HUB_NEWS_ENDPOINT = "https://naverapihub.apigw.ntruss.com/search/v1/news"
NAVER_API_HUB_HOST = "naverapihub.apigw.ntruss.com"
NAVER_API_HUB_PATH = "/search/v1/news"
NAVER_API_HUB_ID_HEADER = "X-NCP-APIGW-API-KEY-ID"
NAVER_API_HUB_SECRET_HEADER = "X-NCP-APIGW-API-KEY"
NAVER_TIMEOUT_SECONDS = 20


def naver_credentials() -> tuple[str | None, str | None]:
    load_monitoring_environment()
    return clean_env_value(os.getenv("NAVER_API_HUB_CLIENT_ID")), clean_env_value(os.getenv("NAVER_API_HUB_CLIENT_SECRET"))


def clean_env_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().lstrip("\ufeff")
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1].strip()
    return cleaned or None


def naver_news_endpoint() -> str:
    load_monitoring_environment()
    return clean_env_value(os.getenv("NAVER_API_HUB_NEWS_ENDPOINT")) or DEFAULT_NAVER_API_HUB_NEWS_ENDPOINT


def build_naver_request(query: str, *, display: int = 20, start: int = 1) -> urllib.request.Request:
    client_id, client_secret = naver_credentials()
    if not client_id or not client_secret:
        raise RuntimeError("NAVER_API_HUB_CREDENTIALS_NOT_CONFIGURED")
    params = urllib.parse.urlencode({"query": query, "display": display, "start": start, "sort": "date"})
    return urllib.request.Request(
        f"{naver_news_endpoint()}?{params}",
        headers={
            NAVER_API_HUB_ID_HEADER: client_id,
            NAVER_API_HUB_SECRET_HEADER: client_secret,
            "User-Agent": "ModularHubCompanyMonitor/1.0",
        },
    )


def naver_contract_report() -> dict[str, Any]:
    endpoint = urllib.parse.urlsplit(naver_news_endpoint())
    actual_headers = [NAVER_API_HUB_ID_HEADER, NAVER_API_HUB_SECRET_HEADER, "User-Agent"]
    return {
        "expected_endpoint_host": NAVER_API_HUB_HOST,
        "actual_endpoint_host": endpoint.netloc,
        "expected_api_path": NAVER_API_HUB_PATH,
        "actual_api_path": endpoint.path,
        "expected_client_id_header": NAVER_API_HUB_ID_HEADER,
        "actual_client_id_header": NAVER_API_HUB_ID_HEADER,
        "expected_client_secret_header": NAVER_API_HUB_SECRET_HEADER,
        "actual_client_secret_header": NAVER_API_HUB_SECRET_HEADER,
        "expected_env_names": ["NAVER_API_HUB_CLIENT_ID", "NAVER_API_HUB_CLIENT_SECRET"],
        "actual_env_names": ["NAVER_API_HUB_CLIENT_ID", "NAVER_API_HUB_CLIENT_SECRET"],
        "legacy_env_fallback_enabled": False,
        "legacy_header_names_used": False,
        "http_method": "GET",
        "query_parameter_names": ["query", "display", "start", "sort"],
        "timeout_seconds": NAVER_TIMEOUT_SECONDS,
        "retry_policy": {"default_retries": 2, "auth_errors_retried": False, "preflight_retries": 0},
        "header_names": actual_headers,
        "contract_match": endpoint.netloc == NAVER_API_HUB_HOST and endpoint.path == NAVER_API_HUB_PATH,
    }


def naver_error_category(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 401:
            return "auth_error"
        if exc.code == 403:
            return "forbidden_or_subscription_error"
        if exc.code == 429:
            return "rate_limited"
        if 400 <= exc.code < 500:
            return "invalid_request"
        return "transport_error"
    text = str(exc).lower()
    if "not_configured" in text:
        return "query_configuration_error"
    if "json" in text or "parse" in text:
        return "response_parse_error"
    if "timed out" in text or "urlopen" in text or "connection" in text:
        return "transport_error"
    return "transport_error"


def naver_get(query: str, *, display: int = 20, start: int = 1, retries: int = 2) -> dict[str, Any]:
    request = build_naver_request(query, display=display, start=start)
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=NAVER_TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover - live API guard
            if exc.code in {400, 401, 403, 429}:
                raise
            last_error = exc
        except Exception as exc:  # pragma: no cover - live API retry guard
            last_error = exc
        if attempt < retries:
            time.sleep(2**attempt)
    raise RuntimeError(str(last_error))


def preflight(*, live: bool, acknowledged: bool, output_dir: Path | None = None) -> dict[str, Any]:
    fetched_at = iso_now()
    contract = naver_contract_report()
    client_id, client_secret = naver_credentials()
    configured = bool(client_id and client_secret)
    result: dict[str, Any] = {
        "source_type": "naver_search",
        "run_mode": "live" if live and acknowledged else "blocked",
        "live_opt_in": bool(live and acknowledged),
        "configured": configured,
        "request_attempted": False,
        "endpoint_host": contract["actual_endpoint_host"],
        "endpoint_path": contract["actual_api_path"],
        "header_names": [NAVER_API_HUB_ID_HEADER, NAVER_API_HUB_SECRET_HEADER],
        "http_status": None,
        "safe_error_code": None,
        "safe_error_category": None,
        "success": False,
        "checked_at": fetched_at,
        "contract": contract,
    }
    if output_dir:
        write_json(output_dir / "naver-api-hub-contract-report.json", contract)
    if not live or not acknowledged:
        result["safe_error_code"] = "LIVE_OPT_IN_REQUIRED"
        result["safe_error_category"] = "invalid_request"
        if output_dir:
            write_json(output_dir / "naver-api-hub-preflight.json", result)
        return result
    if not configured:
        result["safe_error_code"] = "NAVER_API_HUB_CREDENTIALS_NOT_CONFIGURED"
        result["safe_error_category"] = "query_configuration_error"
        if output_dir:
            write_json(output_dir / "naver-api-hub-preflight.json", result)
        return result
    try:
        request = build_naver_request("모듈러", display=1, start=1)
        result["request_attempted"] = True
        with urllib.request.urlopen(request, timeout=NAVER_TIMEOUT_SECONDS) as response:
            json.loads(response.read().decode("utf-8"))
            result["http_status"] = response.status
            result["success"] = 200 <= response.status < 300
            result["safe_error_category"] = "success" if result["success"] else "invalid_request"
    except urllib.error.HTTPError as exc:
        result["request_attempted"] = True
        result["http_status"] = exc.code
        result["safe_error_code"] = f"HTTP_{exc.code}"
        result["safe_error_category"] = naver_error_category(exc)
    except json.JSONDecodeError:
        result["request_attempted"] = True
        result["safe_error_code"] = "JSON_DECODE_ERROR"
        result["safe_error_category"] = "response_parse_error"
    except Exception as exc:
        result["request_attempted"] = True
        result["safe_error_code"] = safe_error_message(exc, "NAVER_PREFLIGHT_ERROR")
        result["safe_error_category"] = naver_error_category(exc)
    if output_dir:
        write_json(output_dir / "naver-api-hub-preflight.json", result)
    return result


def should_exclude(company, title: str, summary: str) -> str | None:
    text = f"{title} {summary}".lower()
    if not any(alias.lower() in text for alias in company.search_names if alias):
        return "entity_not_matched"
    if any(word.lower() in text for word in company.negative_keywords):
        return "negative_keyword_context"
    return None


def build_queries(company) -> list[str]:
    suffixes = load_query_keywords().get("query_suffixes", [])
    names = company.search_names[:2]
    queries: list[str] = []
    for name in names:
        for suffix in suffixes:
            query = f"{name} {suffix}"
            if query not in queries:
                queries.append(query)
    return queries


def collect_for_company(company, fetched_at: str) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for query in build_queries(company):
        payload = naver_get(query)
        for item in payload.get("items", []):
            title = strip_html(item.get("title"))
            summary = strip_html(item.get("description"))
            exclusion = should_exclude(company, title, summary)
            record = {
                "title": title,
                "original_link": item.get("originallink") or "",
                "naver_link": item.get("link") or "",
                "description": summary,
                "pub_date": item.get("pubDate"),
                "query": query,
                "fetched_at": fetched_at,
            }
            records.append(record)
            if exclusion:
                rejected.append({**record, "rejection_reason": exclusion})
                continue
            classified = classify_text(title, summary)
            candidates.append(
                make_candidate(
                    company=company,
                    candidate_kind=classified["candidate_kind"],
                    domain=classified["domain"],
                    title=title,
                    summary=summary,
                    source_type="naver_search",
                    source_tier="C",
                    publisher="NAVER Search",
                    source_url=record["original_link"] or record["naver_link"],
                    document_id=None,
                    published_at=record["pub_date"],
                    query=query,
                    event_status=classified.get("event_status"),
                    project_credit=classified.get("project_credit"),
                    promotion_blockers=[*classified.get("promotion_blockers", []), "news_search_candidate_requires_review"],
                    raw_ref=f"naver:{query}",
                    fetched_at=fetched_at,
                )
            )
    return {
        "source_type": "naver_search",
        "company_id": company.company_id,
        "status": "ok",
        "fetched_at": fetched_at,
        "records": records,
        "rejected": rejected,
        "candidates": candidates,
    }


def main() -> int:
    parser = parse_common_args("Collect company monitoring candidates from NAVER API HUB Search API.")
    parser.add_argument("--preflight", action="store_true", help="Run a one-request NAVER API HUB authentication preflight.")
    parser.add_argument("--contract-report", type=Path, default=None, help="Optional path for sanitized API HUB contract report.")
    args = parser.parse_args()
    selected = parse_company_arg(args.companies)
    companies = load_monitor_companies(selected)
    fetched_at = iso_now()
    client_id, client_secret = naver_credentials()
    if args.contract_report:
        write_json(args.contract_report, naver_contract_report())
    if args.preflight:
        output_dir = args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        result = preflight(live=args.live, acknowledged=args.acknowledge_live, output_dir=output_dir)
        print(
            json.dumps(
                {
                    "source_type": "naver_search",
                    "preflight": result["safe_error_category"],
                    "http_status": result["http_status"],
                    "success": result["success"],
                    "output": str(output_dir / "naver-api-hub-preflight.json"),
                },
                ensure_ascii=False,
            )
        )
        return 0 if result["success"] else 1
    output: dict[str, Any] = {
        "source_type": "naver_search",
        "fetched_at": fetched_at,
        "run_mode": "fixture" if args.fixture else "live" if live_opt_in_enabled(args) else "blocked",
        "live_opt_in": live_opt_in_enabled(args),
        "env": {
            "NAVER_API_HUB_CLIENT_ID": masked_config_status(client_id),
            "NAVER_API_HUB_CLIENT_SECRET": masked_config_status(client_secret),
        },
        "results": [],
    }
    if args.fixture:
        fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
        output["results"] = fixture.get("results", [])
    elif not live_opt_in_enabled(args):
        output["results"] = live_opt_in_error("naver_search", companies, fetched_at)
    else:
        for company in companies:
            if "naver_search" not in company.enabled_sources:
                continue
            try:
                output["results"].append(collect_for_company(company, fetched_at))
            except Exception as exc:  # source-level failure isolation
                row = fail_source("naver_search", safe_error_message(exc, "naver_error"), company_id=company.company_id)
                row["error_category"] = naver_error_category(exc)
                output["results"].append(row)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "naver_search_raw.json"
    write_json(output_path, output)
    candidate_count = sum(len(row.get("candidates", [])) for row in output["results"])
    errors = [row for row in output["results"] if row.get("status") == "error"]
    print(json.dumps({"source_type": "naver_search", "candidate_count": candidate_count, "error_count": len(errors), "output": str(output_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
