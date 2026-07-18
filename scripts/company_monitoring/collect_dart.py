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

from scripts.company_monitoring.common import (  # noqa: E402
    fail_source,
    iso_now,
    live_opt_in_enabled,
    live_opt_in_error,
    load_monitoring_environment,
    load_monitor_companies,
    masked_config_status,
    parse_common_args,
    parse_company_arg,
    write_json,
    yyyymmdd_days_ago,
    yyyymmdd_today,
    safe_error_message,
)
from scripts.company_monitoring.normalize_candidate import make_candidate  # noqa: E402


DART_BASE_URL = "https://opendart.fss.or.kr/api"
REPORT_DETAIL_TYPES = {
    "A001": "business_report",
    "A002": "semiannual_report",
    "A003": "quarterly_report",
    "A005": "audit_report",
    "B001": "major_event_report",
}
IMPORTANT_TITLE_TERMS = ("사업보고서", "감사보고서", "반기보고서", "분기보고서", "신규시설", "영업양수", "출자", "합병", "분할", "대표이사", "본점")


def dart_api_key() -> str | None:
    load_monitoring_environment()
    return os.getenv("DART_API_KEY") or os.getenv("OPENDART_API_KEY")


def dart_get(endpoint: str, params: dict[str, Any], *, retries: int = 2) -> dict[str, Any]:
    key = dart_api_key()
    if not key:
        raise RuntimeError("DART_API_KEY_NOT_CONFIGURED")
    query = dict(params)
    query["crtfc_key"] = key
    url = f"{DART_BASE_URL}/{endpoint}?{urllib.parse.urlencode(query)}"
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "ModularHubCompanyMonitor/1.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            status = str(payload.get("status", ""))
            if status not in {"", "000", "013"}:
                raise RuntimeError(f"OPENDART_STATUS_{status}")
            return payload
        except Exception as exc:  # pragma: no cover - live API retry guard
            last_error = exc
            if attempt < retries:
                time.sleep(2**attempt)
    raise RuntimeError(str(last_error))


def viewer_url(receipt_number: str) -> str:
    return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt_number}"


def classify_report_name(name: str) -> str:
    if "사업보고서" in name:
        return "business_report"
    if "감사보고서" in name:
        return "audit_report"
    if "반기보고서" in name:
        return "semiannual_report"
    if "분기보고서" in name:
        return "quarterly_report"
    if any(term in name for term in ("신규시설", "영업양수", "출자", "합병", "분할", "대표이사", "본점")):
        return "major_event_report"
    return "other_disclosure"


def filing_domain(report_name: str) -> str:
    if any(term in report_name for term in ("대표이사", "본점")):
        return "identity"
    if any(term in report_name for term in ("신규시설", "공장", "생산")):
        return "production"
    if any(term in report_name for term in ("영업양수", "출자", "합병", "분할")):
        return "strategy"
    if any(term in report_name for term in ("사업보고서", "감사보고서", "반기보고서", "분기보고서")):
        return "financial"
    return "organization"


def collect_for_company(company, days: int, fetched_at: str) -> dict[str, Any]:
    if not company.dart_corp_code:
        return {
            "source_type": "dart",
            "company_id": company.company_id,
            "status": "skipped",
            "reason": "dart_corp_code_missing",
            "fetched_at": fetched_at,
            "records": [],
            "candidates": [],
        }
    payload = dart_get(
        "list.json",
        {
            "corp_code": company.dart_corp_code,
            "bgn_de": yyyymmdd_days_ago(days),
            "end_de": yyyymmdd_today(),
            "page_no": 1,
            "page_count": 100,
        },
    )
    records = payload.get("list") or []
    candidates = []
    for record in records:
        report_name = str(record.get("report_nm") or "")
        if not any(term in report_name for term in IMPORTANT_TITLE_TERMS):
            continue
        receipt = str(record.get("rcept_no") or "")
        domain = filing_domain(report_name)
        report_type = classify_report_name(report_name)
        candidates.append(
            make_candidate(
                company=company,
                candidate_kind="evidence" if domain == "financial" else "event",
                domain=domain,
                title=report_name,
                summary=f"OpenDART disclosure {receipt} filed on {record.get('rcept_dt') or ''}.",
                source_type="dart",
                source_tier="A",
                publisher="OpenDART",
                source_url=viewer_url(receipt),
                document_id=receipt,
                published_at=record.get("rcept_dt"),
                proposed_value={"report_type": report_type, "receipt_number": receipt, "corp_code": company.dart_corp_code},
                current_value=None,
                event_status="unconfirmed",
                project_credit=False,
                promotion_blockers=["manual_review_required", "automatic_dart_candidate_not_baseline"],
                fetched_at=fetched_at,
            )
        )
    return {
        "source_type": "dart",
        "company_id": company.company_id,
        "status": "ok",
        "fetched_at": fetched_at,
        "records": records,
        "candidates": candidates,
    }


def main() -> int:
    parser = parse_common_args("Collect company monitoring candidates from OpenDART.")
    args = parser.parse_args()
    selected = parse_company_arg(args.companies)
    companies = load_monitor_companies(selected)
    fetched_at = iso_now()
    output: dict[str, Any] = {
        "source_type": "dart",
        "fetched_at": fetched_at,
        "run_mode": "fixture" if args.fixture else "live" if live_opt_in_enabled(args) else "blocked",
        "live_opt_in": live_opt_in_enabled(args),
        "env": {"DART_API_KEY": masked_config_status(dart_api_key())},
        "results": [],
    }
    if args.fixture:
        fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
        output["results"] = fixture.get("results", [])
    elif not live_opt_in_enabled(args):
        output["results"] = live_opt_in_error("dart", companies, fetched_at)
    else:
        for company in companies:
            if "dart" not in company.enabled_sources:
                continue
            try:
                output["results"].append(collect_for_company(company, args.days, fetched_at))
            except Exception as exc:  # source-level failure isolation
                output["results"].append(fail_source("dart", safe_error_message(exc, "dart_error"), company_id=company.company_id))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "dart_raw.json"
    write_json(output_path, output)
    candidate_count = sum(len(row.get("candidates", [])) for row in output["results"])
    errors = [row for row in output["results"] if row.get("status") == "error"]
    print(json.dumps({"source_type": "dart", "candidate_count": candidate_count, "error_count": len(errors), "output": str(output_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
