from __future__ import annotations

import json
import os
import sys
import time
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
    load_monitor_companies,
    load_query_keywords,
    mask_secret,
    parse_common_args,
    parse_company_arg,
    safe_error_message,
    strip_html,
    write_json,
)
from scripts.company_monitoring.normalize_candidate import make_candidate  # noqa: E402


NAVER_NEWS_ENDPOINT = "https://openapi.naver.com/v1/search/news.json"


def naver_credentials() -> tuple[str | None, str | None]:
    return os.getenv("NAVER_API_HUB_CLIENT_ID") or os.getenv("NAVER_CLIENT_ID"), os.getenv("NAVER_API_HUB_CLIENT_SECRET") or os.getenv("NAVER_CLIENT_SECRET")


def naver_get(query: str, *, display: int = 20, start: int = 1, retries: int = 2) -> dict[str, Any]:
    client_id, client_secret = naver_credentials()
    if not client_id or not client_secret:
        raise RuntimeError("NAVER_API_HUB_CREDENTIALS_NOT_CONFIGURED")
    params = urllib.parse.urlencode({"query": query, "display": display, "start": start, "sort": "date"})
    request = urllib.request.Request(
        f"{NAVER_NEWS_ENDPOINT}?{params}",
        headers={
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
            "User-Agent": "ModularHubCompanyMonitor/1.0",
        },
    )
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - live API retry guard
            last_error = exc
            if attempt < retries:
                time.sleep(2**attempt)
    raise RuntimeError(str(last_error))


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
    args = parser.parse_args()
    selected = parse_company_arg(args.companies)
    companies = load_monitor_companies(selected)
    fetched_at = iso_now()
    client_id, client_secret = naver_credentials()
    output: dict[str, Any] = {
        "source_type": "naver_search",
        "fetched_at": fetched_at,
        "env": {
            "NAVER_API_HUB_CLIENT_ID": mask_secret(client_id),
            "NAVER_API_HUB_CLIENT_SECRET": mask_secret(client_secret),
        },
        "results": [],
    }
    if args.fixture:
        fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
        output["results"] = fixture.get("results", [])
    else:
        for company in companies:
            if "naver_search" not in company.enabled_sources:
                continue
            try:
                output["results"].append(collect_for_company(company, fetched_at))
            except Exception as exc:  # source-level failure isolation
                output["results"].append(fail_source("naver_search", safe_error_message(exc, "naver_error"), company_id=company.company_id))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "naver_search_raw.json"
    write_json(output_path, output)
    candidate_count = sum(len(row.get("candidates", [])) for row in output["results"])
    errors = [row for row in output["results"] if row.get("status") == "error"]
    print(json.dumps({"source_type": "naver_search", "candidate_count": candidate_count, "error_count": len(errors), "output": str(output_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
