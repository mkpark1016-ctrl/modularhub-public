#!/usr/bin/env python3
"""Generate DART financial audit artifacts for Wave 1 companies."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from validate_company_dart_financials import DEFAULT_INPUT, validate, wave1_companies  # noqa: E402
from src.env_config import env_status  # noqa: E402
from src.opendart_client import OpenDartClient, OpenDartResponseError  # noqa: E402

OUTPUT_DIR = ROOT / "artifacts" / "company-research-wave-1-dart-live"
ALIASES_PATH = ROOT / "config" / "companies" / "dart_account_aliases.json"
VERIFIED_OVERRIDES_PATH = ROOT / "config" / "companies" / "dart_verified_overrides.json"
REPORT_DETAILS = {"F001": "audit_report", "F002": "consolidated_audit_report", "A001": "business_report"}
SEARCH_START = "20210101"
SEARCH_END = "20260714"
TARGET_FINANCIAL_YEARS = [2025, 2024, 2023]
FINANCIAL_METRICS = [
    "revenue",
    "gross_profit",
    "operating_profit",
    "net_income",
    "operating_cash_flow",
    "total_assets",
    "total_liabilities",
    "total_equity",
]
ACCOUNT_ID_METRIC_MAP = {
    "ifrs-full_revenue": "revenue",
    "ifrs-full_grossprofit": "gross_profit",
    "dart_operatingincomeloss": "operating_profit",
    "ifrs-full_profitloss": "net_income",
}
ORIGINAL_XML_ACODE_MAP = {
    "total_assets": "11500000010000",
    "total_liabilities": "11800000010000",
    "total_equity": "11890000010000",
    "revenue": "12100000010000",
    "cost_of_sales": "12200000010000",
    "gross_profit": "12300000010000",
    "operating_profit": "12500000010000",
    "net_income": "12900000010000",
    "operating_cash_flow": "16100000010000",
}
OPINION_MAP = {
    "의견거절": "disclaimer",
    "부적정": "adverse",
    "한정": "qualified",
    "적정": "unmodified",
}


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def join_list(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return "" if value is None else str(value)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_account(value: str | None) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value or "").lower()


def load_account_aliases() -> dict[str, list[str]]:
    payload = load_json(ALIASES_PATH)
    return {metric: [normalize_account(alias) for alias in aliases] for metric, aliases in payload.get("aliases", {}).items()}


def verified_overrides() -> dict[str, Any]:
    if not VERIFIED_OVERRIDES_PATH.exists():
        return {}
    return load_json(VERIFIED_OVERRIDES_PATH).get("companies", {})


def parse_amount(value: Any) -> int | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace(",", "")
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    try:
        amount = int(float(text))
    except ValueError:
        return None
    return -amount if negative else amount


def clean_xml_text(value: str) -> str:
    return re.sub(r"<.*?>", "", value or "").strip()


def normalize_krw_million(value: int | None) -> float | None:
    if value is None:
        return None
    return round(value / 1_000_000, 3)


def source_url(receipt_number: str | None) -> str:
    return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt_number}" if receipt_number else "https://dart.fss.or.kr/"


def append_source(company: dict[str, Any], source: dict[str, Any]) -> None:
    sources = company.setdefault("sources", [])
    existing_urls = {str(item.get("source_url", "")).lower(): item for item in sources}
    url = str(source.get("source_url", "")).lower()
    if url in existing_urls:
        return
    sources.append(source)


def fetch_all_filings(client: OpenDartClient, corp_code: str, detail: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page_no = 1
    while True:
        try:
            payload = client.list_filings(
                corp_code=corp_code,
                start_date=SEARCH_START,
                end_date=SEARCH_END,
                pblntf_detail_ty=detail,
                page_no=page_no,
                page_count=100,
            )
        except OpenDartResponseError as exc:
            if exc.status == "013":
                return rows
            raise
        batch = payload.get("list", []) or []
        rows.extend(batch)
        total = int(payload.get("total_count") or len(rows))
        if len(rows) >= total or not batch:
            return rows
        page_no += 1


def fiscal_year_from_filing(row: dict[str, Any]) -> int | None:
    report = row.get("report_nm", "")
    match = re.search(r"\((20\d{2})(?:[.\-\s/](\d{1,2}))?\)", report)
    if match:
        return int(match.group(1))
    match = re.search(r"(20\d{2})(?:[.\-\s/](\d{1,2}))", report)
    if match:
        return int(match.group(1))
    filed = str(row.get("rcept_dt", ""))
    if len(filed) >= 4:
        return int(filed[:4]) - 1
    return None


def build_filing_inventory(client: OpenDartClient, company: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    identity = company.get("dart_identity", {}) or {}
    corp_code = identity.get("dart_corp_code")
    if identity.get("identity_status") != "confirmed" or not corp_code:
        return [], []
    inventory: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    for detail, report_type in REPORT_DETAILS.items():
        for row in fetch_all_filings(client, corp_code, detail):
            fiscal_year = fiscal_year_from_filing(row)
            receipt_number = row.get("rcept_no", "")
            source_id = f"dart-{corp_code}-{receipt_number}"
            record = {
                "fiscal_year": fiscal_year,
                "report_type": report_type,
                "report_detail_code": detail,
                "report_title": row.get("report_nm", "").strip(),
                "receipt_number": receipt_number,
                "filed_at": row.get("rcept_dt", ""),
                "source_url": source_url(receipt_number),
                "final_report": "정정" not in row.get("report_nm", ""),
                "correction": "정정" in row.get("report_nm", ""),
                "consolidated": detail == "F002",
                "selection_status": "candidate",
                "selection_reason": "",
                "source_ids": [source_id],
            }
            inventory.append(record)
            append_source(
                company,
                {
                    "source_id": source_id,
                    "source_type": "regulatory_filing",
                    "source_name": "DART",
                    "title": record["report_title"],
                    "source_url": record["source_url"],
                    "published_at": record["filed_at"],
                    "accessed_at": datetime.now(timezone.utc).isoformat(),
                    "publisher": "DART",
                    "primary_source": True,
                    "confidence": "high",
                    "verification_note": "OpenDART filing inventory result.",
                },
            )
    by_year: dict[int, list[dict[str, Any]]] = {}
    for record in inventory:
        if record.get("fiscal_year"):
            by_year.setdefault(int(record["fiscal_year"]), []).append(record)
    priority = {"consolidated_audit_report": 0, "audit_report": 1, "business_report": 2}
    for year, records in by_year.items():
        chosen = sorted(records, key=lambda item: (priority.get(item["report_type"], 9), item.get("filed_at", "")), reverse=False)[0]
        chosen["selection_status"] = "selected"
        chosen["selection_reason"] = "selected by report-type priority and filing date"
        selected.append(chosen)
    return inventory, selected


def extract_structured_financials(client: OpenDartClient, company: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    identity = company.get("dart_identity", {}) or {}
    corp_code = identity.get("dart_corp_code")
    if identity.get("identity_status") != "confirmed" or not corp_code:
        return [], [], []
    aliases = load_account_aliases()
    financials: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    manual_review: list[dict[str, Any]] = []
    for year in TARGET_FINANCIAL_YEARS:
        try:
            payload = client.single_account_all(corp_code=corp_code, fiscal_year=year)
        except OpenDartResponseError as exc:
            if exc.status == "013":
                manual_review.append({"code": "structured_api_no_data", "company_id": company["company_id"], "path": f"financials.{year}", "message": "OpenDART structured financial API returned no data", "severity": "warning"})
                continue
            raise
        rows = payload.get("list", []) or []
        mapped: dict[str, dict[str, Any]] = {}
        for row in rows:
            account = normalize_account(row.get("account_nm"))
            account_id = str(row.get("account_id") or "").lower()
            mapped_metric = ACCOUNT_ID_METRIC_MAP.get(account_id)
            candidate_metrics = [mapped_metric] if mapped_metric else list(aliases)
            for metric in candidate_metrics:
                metric_aliases = aliases.get(metric, [])
                if metric in mapped or account not in metric_aliases:
                    if mapped_metric != metric:
                        continue
                if metric == "net_income" and str(row.get("sj_div", "")).upper() not in {"IS", "CIS"}:
                    continue
                amount = parse_amount(row.get("thstrm_amount"))
                if amount is None:
                    continue
                receipt_number = row.get("rcept_no", "")
                source_id = f"dart-{corp_code}-{receipt_number}" if receipt_number else f"dart-{corp_code}-{year}-structured-api"
                metric_record = {
                    "source_value": amount,
                    "source_unit": row.get("currency") or "KRW",
                    "normalized_value": normalize_krw_million(amount),
                    "normalized_unit": "KRW_MILLION",
                    "normalization_factor": 0.000001,
                    "fiscal_year": year,
                    "reporting_scope": "separate",
                    "account_name": row.get("account_nm", ""),
                    "receipt_number": receipt_number,
                    "source_ids": [source_id],
                    "confidence": "high",
                }
                mapped[metric] = metric_record
                metric_rows.append({"company_id": company["company_id"], "year": year, "metric": metric, **metric_record})
        if mapped:
            financial_source_ids = sorted({sid for item in mapped.values() for sid in item.get("source_ids", [])})
            source_id = f"dart-{corp_code}-{year}-structured-api"
            if not financial_source_ids:
                append_source(
                    company,
                    {
                        "source_id": source_id,
                        "source_type": "regulatory_filing",
                        "source_name": "OpenDART structured financial API",
                        "title": f"{company.get('company_name')} {year} structured financial statements",
                        "source_url": source_url(next((value.get("receipt_number") for value in mapped.values() if value.get("receipt_number")), "")),
                        "published_at": "",
                        "accessed_at": datetime.now(timezone.utc).isoformat(),
                        "publisher": "OpenDART",
                        "primary_source": True,
                        "confidence": "high",
                        "verification_note": "Structured single-account financial statement API result.",
                    },
                )
                financial_source_ids = [source_id]
            financial = {
                "year": year,
                "scope": "separate",
                "reporting_scope": "separate",
                "accounting_standard": "K-IFRS",
                "currency": "KRW",
                "modular_segment_available": False,
                "modular_segment_revenue": None,
                "source_ids": financial_source_ids,
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "confidence": "high",
            }
            for metric in FINANCIAL_METRICS:
                if metric in mapped:
                    financial[metric] = mapped[metric]
            financials.append(financial)
    return financials, metric_rows, manual_review


def original_document_xml(client: OpenDartClient, receipt_number: str) -> tuple[str, str, Path]:
    import zipfile

    path = client.download_document(receipt_number)
    with zipfile.ZipFile(path) as archive:
        xml_name = next(name for name in archive.namelist() if name.lower().endswith(".xml"))
        data = archive.read(xml_name).decode("utf-8", "replace")
    return data, xml_name, path


def original_document_text(client: OpenDartClient, receipt_number: str) -> tuple[str, str, Path]:
    data, xml_name, path = original_document_xml(client, receipt_number)
    text = re.sub(r"<[^>]+>", " ", data)
    text = re.sub(r"\s+", " ", text).strip()
    return text, xml_name, path


def parse_original_document_metrics(client: OpenDartClient, receipt_number: str) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    data, xml_name, path = original_document_xml(client, receipt_number)
    rows: dict[str, dict[str, Any]] = {}
    revenue_mix: list[dict[str, Any]] = []
    parsed_table_rows = 0
    for tr in re.findall(r"<TR.*?</TR>", data, flags=re.S):
        cells = re.findall(r'<TE[^>]*ACODE="([^"]+)"[^>]*ADELIM="([^"]+)"[^>]*>(.*?)</TE>', tr, flags=re.S)
        if not cells:
            continue
        parsed_table_rows += 1
        acode = cells[0][0]
        label = clean_xml_text(cells[0][2])
        values = {delim: clean_xml_text(text) for _, delim, text in cells}
        current_value = parse_amount(values.get("2"))
        for metric, target_acode in ORIGINAL_XML_ACODE_MAP.items():
            if acode == target_acode and current_value is not None:
                rows[metric] = {
                    "source_value": current_value,
                    "source_unit": "KRW",
                    "normalized_value": normalize_krw_million(current_value),
                    "normalized_unit": "KRW_MILLION",
                    "normalization_factor": 0.000001,
                    "account_name": label,
                    "receipt_number": receipt_number,
                    "extraction_method": "audit_report_xml_acode",
                    "verification_status": "extracted",
                }
        if acode.startswith("121") and acode != ORIGINAL_XML_ACODE_MAP["revenue"] and current_value is not None:
            revenue_mix.append(
                {
                    "account_code": acode,
                    "account_name": label,
                    "source_value": current_value,
                    "source_unit": "KRW",
                    "normalized_value": normalize_krw_million(current_value),
                    "normalized_unit": "KRW_MILLION",
                    "receipt_number": receipt_number,
                    "financial_scope": "company_total",
                }
            )
    document_info = {
        "document_path": str(path),
        "document_name": xml_name,
        "document_format": "xml",
        "parser": "audit_report_xml_acode",
        "statement_type": "separate",
        "source_unit": "KRW",
        "normalized_unit": "KRW_MILLION",
        "conversion_multiplier": 1,
        "parsed_table_rows": parsed_table_rows,
        "extracted_metric_count": len(rows),
    }
    return rows, revenue_mix, document_info


def normalize_auditor_name(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"\s+", "", value)
    normalized = re.sub(r"^[^가-힣A-Za-z0-9]*", "", normalized)
    match = re.search(r"([가-힣A-Za-z0-9·]{2,12}회계법인)", normalized)
    if match:
        return match.group(1)
    match = re.search(r"회계법인([가-힣A-Za-z0-9·]{2,12})", normalized)
    return f"{match.group(1)}회계법인" if match else None


def parse_original_document_audit_info(client: OpenDartClient, receipt_number: str) -> dict[str, Any]:
    text, xml_name, path = original_document_text(client, receipt_number)
    info: dict[str, Any] = {
        "auditor": None,
        "audit_opinion": "unknown",
        "audit_opinion_raw": None,
        "accounting_standard": "unknown",
        "reporting_scope": "separate",
        "source_document_name": xml_name,
        "source_document_path": str(path),
        "extraction_method": "audit_report_xml_text",
        "confidence": "medium",
        "verification_note": "Auditor and opinion extracted from original DART audit-report XML text.",
    }
    for candidate in re.findall(r"([가-힣A-Za-z0-9·]{2,12}회계법인)", text):
        auditor = normalize_auditor_name(candidate)
        if auditor and auditor != "회계법인":
            info["auditor"] = auditor
            break
    if not info["auditor"]:
        for candidate in re.findall(r"(회계법인\s*[가-힣A-Za-z0-9·]{2,12})", text):
            auditor = normalize_auditor_name(candidate)
            if auditor and auditor != "회계법인":
                info["auditor"] = auditor
                break

    opinion_start = text.find("감사의견")
    if opinion_start == -1:
        opinion_start = text.find("우리의 의견으로는")
    opinion_segment = text[opinion_start : opinion_start + 900] if opinion_start != -1 else text[:900]
    for raw, normalized in OPINION_MAP.items():
        if raw in opinion_segment:
            info["audit_opinion"] = normalized
            info["audit_opinion_raw"] = raw
            break
    if info["audit_opinion"] == "unknown" and "공정하게 표시" in opinion_segment:
        info["audit_opinion"] = "unmodified"
        info["audit_opinion_raw"] = "공정하게 표시"
    if "일반기업회계기준" in opinion_segment or "일반기업회계기준" in text[:2000]:
        info["accounting_standard"] = "general_korean_gaap"
    if "연결재무제표" in opinion_segment[:350] or "연결 재무제표" in opinion_segment[:350]:
        info["reporting_scope"] = "consolidated"
    return info


def extract_original_document_financials(
    client: OpenDartClient,
    company: dict[str, Any],
    selected_reports: list[dict[str, Any]],
    existing_years: set[int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    financials: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    revenue_mix_rows: list[dict[str, Any]] = []
    fallback_rows: list[dict[str, Any]] = []
    document_rows: list[dict[str, Any]] = []
    for report in selected_reports:
        year = report.get("fiscal_year")
        receipt_number = report.get("receipt_number")
        if year not in TARGET_FINANCIAL_YEARS or year in existing_years or not receipt_number:
            continue
        metrics, revenue_mix, document_info = parse_original_document_metrics(client, receipt_number)
        document_rows.append({"company_id": company["company_id"], "fiscal_year": year, "receipt_number": receipt_number, **document_info})
        if not metrics:
            fallback_rows.append({"company_id": company["company_id"], "fiscal_year": year, "receipt_number": receipt_number, "fallback_type": "audit_report_xml", "status": "no_metrics_extracted", "note": ""})
            continue
        source_id = f"dart-{(company.get('dart_identity') or {}).get('dart_corp_code')}-{receipt_number}"
        financial = {
            "year": year,
            "scope": "separate",
            "reporting_scope": "separate",
            "accounting_standard": "general_korean_gaap",
            "currency": "KRW",
            "modular_segment_available": False,
            "modular_segment_revenue": None,
            "source_ids": [source_id],
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "confidence": "high",
        }
        for metric, value in metrics.items():
            record = {**value, "fiscal_year": year, "reporting_scope": "separate", "source_ids": [source_id], "confidence": "high"}
            financial[metric] = record
            metric_rows.append({"company_id": company["company_id"], "year": year, "metric": metric, **record})
        financials.append(financial)
        for row in revenue_mix:
            revenue_mix_rows.append({"company_id": company["company_id"], "fiscal_year": year, **row})
        fallback_rows.append({"company_id": company["company_id"], "fiscal_year": year, "receipt_number": receipt_number, "fallback_type": "audit_report_xml", "status": "metrics_extracted", "note": f"{len(metrics)} metrics extracted"})
    return financials, metric_rows, revenue_mix_rows, fallback_rows, document_rows


def validate_against_overrides(company: dict[str, Any], financials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    overrides = verified_overrides().get(company["company_id"], {}).get("financial_validation", {})
    rows: list[dict[str, Any]] = []
    by_year = {str(item.get("year")): item for item in financials}
    for year, metrics in overrides.items():
        financial = by_year.get(str(year), {})
        for metric, expected in metrics.items():
            actual_record = financial.get(metric)
            actual = actual_record.get("source_value") if isinstance(actual_record, dict) else None
            rows.append(
                {
                    "company_id": company["company_id"],
                    "fiscal_year": year,
                    "metric": metric,
                    "expected_value": expected,
                    "actual_value": actual,
                    "match": actual == expected,
                    "difference": None if actual is None else actual - expected,
                    "receipt_number": actual_record.get("receipt_number", "") if isinstance(actual_record, dict) else "",
                }
            )
    return rows


def enrich_live_data(path: Path = DEFAULT_INPUT) -> None:
    status = env_status("OPENDART_API_KEY", expected_length=40)
    if not (status["configured"] and status["expected_length_match"]):
        return
    payload = load_json(path)
    client = OpenDartClient()
    by_id = {company["company_id"]: company for company in payload.get("companies", [])}
    for company in [by_id[company_id] for company_id in ["yuchang-enc", "kumkang-kind", "planm", "daeseung-engineering"] if company_id in by_id]:
        inventory, selected = build_filing_inventory(client, company)
        financials, _, manual_review = extract_structured_financials(client, company)
        filing_status = "searched"
        if (company.get("dart_identity", {}) or {}).get("identity_status") == "ambiguous":
            filing_status = "identity_ambiguous"
        company["filings"] = inventory
        company["filing_availability"] = {
            "status": filing_status,
            "searched_period": [2025, 2024, 2023, 2022, 2021],
            "searched_report_types": list(REPORT_DETAILS.values()),
            "reports_found_count": len(inventory),
            "selected_reports": selected,
            "not_found_reason": "" if inventory else ("identity ambiguous; filing extraction skipped" if filing_status == "identity_ambiguous" else "No F001/F002/A001 filing found in searched period."),
            "searched_at": datetime.now(timezone.utc).isoformat(),
        }
        audit_information = []
        for report in selected:
            receipt_number = report.get("receipt_number")
            parsed_audit: dict[str, Any] = {}
            if receipt_number:
                try:
                    parsed_audit = parse_original_document_audit_info(client, receipt_number)
                except Exception as exc:  # pragma: no cover - live document format guard
                    parsed_audit = {
                        "auditor": None,
                        "audit_opinion": "unknown",
                        "audit_opinion_raw": None,
                        "accounting_standard": "unknown",
                        "reporting_scope": "consolidated" if report.get("consolidated") else "separate",
                        "confidence": "low",
                        "verification_note": f"Original audit text parse failed: {type(exc).__name__}",
                    }
            audit_information.append(
                {
                    "fiscal_year": report.get("fiscal_year"),
                    "report_type": report.get("report_type"),
                    "receipt_number": receipt_number,
                    "filed_at": report.get("filed_at"),
                    "auditor": parsed_audit.get("auditor"),
                    "audit_opinion": parsed_audit.get("audit_opinion", "unknown"),
                    "audit_opinion_raw": parsed_audit.get("audit_opinion_raw"),
                    "reporting_scope": parsed_audit.get("reporting_scope") or ("consolidated" if report.get("consolidated") else "separate"),
                    "accounting_standard": parsed_audit.get("accounting_standard", "unknown"),
                    "unit": "KRW",
                    "source_ids": report.get("source_ids", []),
                    "verified_at": datetime.now(timezone.utc).isoformat(),
                    "confidence": parsed_audit.get("confidence", "medium"),
                    "verification_note": parsed_audit.get("verification_note", "Filing identified; auditor and opinion require original report text review."),
                }
            )
        company["audit_information"] = audit_information
        existing_years = {int(item.get("year")) for item in financials if item.get("year")}
        fallback_financials, _, revenue_mix_rows, fallback_rows, document_rows = extract_original_document_financials(client, company, selected, existing_years)
        financials = sorted([*financials, *fallback_financials], key=lambda item: int(item.get("year") or 0), reverse=True)
        fulfilled_years = {int(item.get("year")) for item in financials if item.get("year")}
        unresolved_manual_review = []
        for issue in manual_review:
            match = re.search(r"financials\.(\d{4})", str(issue.get("path", "")))
            if match and int(match.group(1)) in fulfilled_years:
                continue
            unresolved_manual_review.append(issue)
        if financials:
            company["financials"] = financials
        if revenue_mix_rows:
            company["revenue_mix"] = revenue_mix_rows
        company["dart_original_document_fallback_results"] = fallback_rows
        company["dart_original_document_inventory"] = document_rows
        validation_rows = validate_against_overrides(company, financials)
        if validation_rows:
            company["dart_financial_validation_results"] = validation_rows
        overrides = verified_overrides().get(company["company_id"], {})
        audit_override = overrides.get("audit", {})
        if audit_override:
            for audit in company["audit_information"]:
                if audit.get("receipt_number") == audit_override.get("receipt_number"):
                    audit.update(
                        {
                            "auditor": audit_override.get("auditor"),
                            "audit_opinion": audit_override.get("audit_opinion"),
                            "audit_opinion_raw": audit_override.get("audit_opinion_raw"),
                            "reporting_scope": audit_override.get("reporting_scope"),
                            "accounting_standard": audit_override.get("accounting_standard"),
                            "confidence": "high",
                            "verification_note": audit_override.get("verification_status"),
                        }
                    )
        summary_status = "partially_verified" if financials else ("identity_ambiguous" if filing_status == "identity_ambiguous" else "filing_found_extraction_pending")
        company["financial_summary"] = {
            "financial_area_status": summary_status,
            "years_available": [item["year"] for item in financials],
            "modular_segment_available": False,
            "modular_segment_name": None,
            "modular_segment_revenue": None,
            "modular_segment_operating_profit": None,
            "modular_segment_basis": "No explicit modular segment disclosure was extracted from DART data.",
            "source_ids": sorted({sid for item in financials for sid in item.get("source_ids", [])}),
            "verified_at": datetime.now(timezone.utc).isoformat() if financials else "",
        }
        gaps = [gap for gap in company.get("research_gaps", []) if gap.get("area") != "dart_financials"]
        if unresolved_manual_review:
            gaps.append({"area": "dart_financials", "status": "manual_review_required", "description": "Some OpenDART structured financial data was unavailable and requires original-report review.", "source_ids": [], "verified_at": ""})
        elif financials:
            gaps.append({"area": "dart_financials", "status": "partially_verified", "description": "OpenDART structured data or original audit-report XML data extracted for available years.", "source_ids": company["financial_summary"]["source_ids"], "verified_at": company["financial_summary"]["verified_at"]})
        else:
            gaps.append({"area": "dart_financials", "status": summary_status, "description": company["filing_availability"]["not_found_reason"], "source_ids": [], "verified_at": ""})
        company["research_gaps"] = gaps
    save_json(path, payload)


def collect_artifacts(input_path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    companies = wave1_companies(input_path)
    validation = validate(input_path)

    identity_rows = []
    filing_rows = []
    selected_rows = []
    audit_rows = []
    statement_rows = []
    metric_rows = []
    source_rows = []
    reports_not_found = []
    manual_review_rows = []
    modular_rows = []
    gaps_rows = []
    revenue_mix_rows = []
    fallback_rows = []
    validation_rows = []
    identity_candidate_rows = []
    document_rows = []
    balance_rows = []
    fiscal_year_mapping_rows = []

    for company in companies:
        identity = company.get("dart_identity", {}) or {}
        filing = company.get("filing_availability", {}) or {}
        summary = company.get("financial_summary", {}) or {}
        identity_rows.append(
            {
                "company_id": company["company_id"],
                "company_name": company.get("company_name"),
                "legal_name": identity.get("legal_name"),
                "dart_corp_code": identity.get("dart_corp_code"),
                "stock_code": identity.get("stock_code"),
                "corp_class": identity.get("corp_class"),
                "identity_status": identity.get("identity_status"),
                "identity_confidence": identity.get("identity_confidence"),
                "searched_at": identity.get("searched_at"),
                "not_found_reason": identity.get("not_found_reason"),
            }
        )
        if company["company_id"] == "yuchang-enc":
            for code in identity.get("rejected_candidate_corp_codes", []) or []:
                identity_candidate_rows.append({"company_id": company["company_id"], "corp_code": code, "decision": "rejected_identity_candidate", "reason": "business number did not match verified reference"})
            if identity.get("dart_corp_code"):
                identity_candidate_rows.append({"company_id": company["company_id"], "corp_code": identity.get("dart_corp_code"), "decision": "confirmed", "reason": identity.get("verification_reason")})
        filing_rows.append(
            {
                "company_id": company["company_id"],
                "status": filing.get("status"),
                "searched_period": join_list(filing.get("searched_period")),
                "searched_report_types": join_list(filing.get("searched_report_types")),
                "reports_found_count": filing.get("reports_found_count", 0),
                "selected_report_count": len(filing.get("selected_reports", []) or []),
                "searched_at": filing.get("searched_at"),
                "not_found_reason": filing.get("not_found_reason"),
            }
        )
        if not filing.get("reports_found_count"):
            reports_not_found.append(
                {
                    "company_id": company["company_id"],
                    "company_name": company.get("company_name"),
                    "status": filing.get("status"),
                    "searched_period": join_list(filing.get("searched_period")),
                    "searched_report_types": join_list(filing.get("searched_report_types")),
                    "reason": filing.get("not_found_reason"),
                }
            )
        for report in filing.get("selected_reports", []) or []:
            selected_rows.append({"company_id": company["company_id"], **report})
            fiscal_year_mapping_rows.append(
                {
                    "company_id": company["company_id"],
                    "receipt_number": report.get("receipt_number"),
                    "report_title": report.get("report_title"),
                    "filed_at": report.get("filed_at"),
                    "mapped_fiscal_year": report.get("fiscal_year"),
                    "mapping_method": "report_title_parenthesized_period" if report.get("report_title") else "filing_date_minus_one",
                }
            )
        for audit in company.get("audit_information", []) or []:
            audit_rows.append({"company_id": company["company_id"], **audit})
        for financial in company.get("financials", []) or []:
            statement_rows.append(
                {
                    "company_id": company["company_id"],
                    "year": financial.get("year"),
                    "reporting_scope": financial.get("reporting_scope"),
                    "accounting_standard": financial.get("accounting_standard"),
                    "currency": financial.get("currency"),
                    "source_ids": join_list(financial.get("source_ids")),
                }
            )
            for metric in ["revenue", "operating_profit", "net_income", "operating_cash_flow", "total_assets", "total_liabilities", "total_equity"]:
                value = financial.get(metric)
                if isinstance(value, dict):
                    metric_rows.append({"company_id": company["company_id"], "year": financial.get("year"), "metric": metric, **value})
        for source in company.get("sources", []) or []:
            if str(source.get("source_type", "")).startswith(("audit", "regulatory")) or "dart" in str(source.get("source_url", "")).lower():
                source_rows.append({"company_id": company["company_id"], **source})
        for issue in validation["issues"]:
            if issue.get("severity") == "warning":
                manual_review_rows.append(issue)
        revenue_mix_rows.extend(company.get("revenue_mix", []) or [])
        fallback_rows.extend(company.get("dart_original_document_fallback_results", []) or [])
        document_rows.extend(company.get("dart_original_document_inventory", []) or [])
        validation_rows.extend(company.get("dart_financial_validation_results", []) or [])
        for financial in company.get("financials", []) or []:
            assets = financial.get("total_assets", {}).get("source_value") if isinstance(financial.get("total_assets"), dict) else None
            liabilities = financial.get("total_liabilities", {}).get("source_value") if isinstance(financial.get("total_liabilities"), dict) else None
            equity = financial.get("total_equity", {}).get("source_value") if isinstance(financial.get("total_equity"), dict) else None
            if assets is not None and liabilities is not None and equity is not None:
                balance_rows.append(
                    {
                        "company_id": company["company_id"],
                        "fiscal_year": financial.get("year"),
                        "assets": assets,
                        "liabilities": liabilities,
                        "equity": equity,
                        "difference": assets - liabilities - equity,
                        "pass": assets == liabilities + equity,
                        "source_ids": join_list(financial.get("source_ids")),
                    }
                )
        modular_rows.append(
            {
                "company_id": company["company_id"],
                "company_name": company.get("company_name"),
                "financial_area_status": summary.get("financial_area_status"),
                "modular_segment_available": summary.get("modular_segment_available"),
                "modular_segment_name": summary.get("modular_segment_name"),
                "modular_segment_revenue": summary.get("modular_segment_revenue"),
                "modular_segment_operating_profit": summary.get("modular_segment_operating_profit"),
                "modular_segment_basis": summary.get("modular_segment_basis"),
                "source_ids": join_list(summary.get("source_ids")),
            }
        )
        for gap in company.get("research_gaps", []) or []:
            gaps_rows.append({"company_id": company["company_id"], "company_name": company.get("company_name"), **gap})

    status = "passed" if validation["valid"] else "failed"
    if status == "passed" and validation["issue_counts"].get("api_key_required"):
        status = "passed_with_api_key_required"

    return {
        "audit_status": status,
        "validation": validation,
        "target_company_count": len(companies),
        "identity_rows": identity_rows,
        "filing_rows": filing_rows,
        "selected_rows": selected_rows,
        "audit_rows": audit_rows,
        "statement_rows": statement_rows,
        "metric_rows": metric_rows,
        "source_rows": source_rows,
        "reports_not_found": reports_not_found,
        "manual_review_rows": manual_review_rows,
        "modular_rows": modular_rows,
        "gaps_rows": gaps_rows,
        "revenue_mix_rows": revenue_mix_rows,
        "fallback_rows": fallback_rows,
        "financial_validation_rows": validation_rows,
        "identity_candidate_rows": identity_candidate_rows,
        "document_rows": document_rows,
        "balance_rows": balance_rows,
        "fiscal_year_mapping_rows": fiscal_year_mapping_rows,
    }


def write_artifacts(result: dict[str, Any], output_dir: Path = OUTPUT_DIR) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_payload = {key: value for key, value in result.items() if not key.endswith("_rows")}
    (output_dir / "company_dart_audit.json").write_text(json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "live_acceptance.json").write_text(json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "company_research_wave_1_dart_r2_audit.json").write_text(json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Wave 1 DART Audit",
        "",
        f"- Audit status: {result['audit_status']}",
        f"- Target companies: {result['target_company_count']}",
        f"- Identity status counts: {result['validation']['identity_status_counts']}",
        f"- Reports found: {result['validation']['issue_counts']['reports_found']}",
        f"- Financial years extracted: {result['validation']['issue_counts']['financial_years']}",
        f"- API key required companies: {result['validation']['issue_counts']['api_key_required']}",
        f"- Error count: {len(result['validation']['issues'])}",
        "",
        "No audited financial number is stored unless a report source, scope, and unit are available.",
    ]
    (output_dir / "company_dart_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output_dir / "live_acceptance.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output_dir / "company_research_wave_1_dart_r2_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    write_csv(output_dir / "dart_company_identity.csv", result["identity_rows"], ["company_id", "company_name", "legal_name", "dart_corp_code", "stock_code", "corp_class", "identity_status", "identity_confidence", "searched_at", "not_found_reason"])
    write_csv(output_dir / "company_identity_candidates.csv", result["identity_candidate_rows"], ["company_id", "corp_code", "decision", "reason"])
    decision = {
        "yuchang_identity": next((row for row in result["identity_rows"] if row.get("company_id") == "yuchang-enc"), {}),
        "candidate_rows": result["identity_candidate_rows"],
    }
    (output_dir / "company_identity_decision.json").write_text(json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "company_identity_decision.md").write_text("# YooChang E&C Identity Decision\n\n" + json.dumps(decision, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(output_dir / "dart_filing_inventory.csv", result["filing_rows"], ["company_id", "status", "searched_period", "searched_report_types", "reports_found_count", "selected_report_count", "searched_at", "not_found_reason"])
    write_csv(output_dir / "selected_audit_reports.csv", result["selected_rows"], ["company_id", "fiscal_year", "report_type", "receipt_number", "report_title", "filed_at", "selection_reason", "source_ids"])
    write_csv(output_dir / "selected_filings.csv", result["selected_rows"], ["company_id", "fiscal_year", "report_type", "receipt_number", "report_title", "filed_at", "selection_reason", "source_ids"])
    write_csv(output_dir / "downloaded_document_inventory.csv", result["document_rows"], ["company_id", "fiscal_year", "receipt_number", "document_name", "document_format", "parser", "statement_type", "source_unit", "normalized_unit", "conversion_multiplier", "parsed_table_rows", "extracted_metric_count"])
    write_csv(output_dir / "statement_section_inventory.csv", result["document_rows"], ["company_id", "fiscal_year", "receipt_number", "document_name", "statement_type", "parser", "parsed_table_rows", "extracted_metric_count"])
    write_csv(output_dir / "parsed_financial_tables.csv", result["metric_rows"], ["company_id", "year", "metric", "account_name", "source_value", "source_unit", "normalized_value", "normalized_unit", "receipt_number", "extraction_method", "verification_status", "source_ids"])
    write_csv(output_dir / "audit_opinions.csv", result["audit_rows"], ["company_id", "fiscal_year", "report_type", "receipt_number", "auditor", "audit_opinion", "audit_opinion_raw", "reporting_scope", "unit", "source_ids"])
    write_csv(output_dir / "financial_statement_inventory.csv", result["statement_rows"], ["company_id", "year", "reporting_scope", "accounting_standard", "currency", "source_ids"])
    write_csv(output_dir / "financial_metrics.csv", result["metric_rows"], ["company_id", "year", "metric", "source_value", "source_unit", "normalized_value", "normalized_unit", "normalization_factor", "source_ids"])
    write_csv(output_dir / "extracted_financials.csv", result["metric_rows"], ["company_id", "year", "metric", "source_value", "source_unit", "normalized_value", "normalized_unit", "normalization_factor", "receipt_number", "source_ids"])
    write_csv(output_dir / "financial_validation_results.csv", result["financial_validation_rows"], ["company_id", "fiscal_year", "metric", "expected_value", "actual_value", "match", "difference", "receipt_number"])
    write_csv(output_dir / "structured_api_results.csv", result["metric_rows"], ["company_id", "year", "metric", "source_value", "source_unit", "normalized_value", "normalized_unit", "normalization_factor", "source_ids"])
    write_csv(output_dir / "original_document_fallback_results.csv", result["fallback_rows"], ["company_id", "fiscal_year", "receipt_number", "fallback_type", "status", "note"])
    write_csv(output_dir / "account_mapping_results.csv", [], ["company_id", "year", "source_account", "mapped_metric", "status", "note"])
    write_csv(output_dir / "unit_normalization_results.csv", result["metric_rows"], ["company_id", "year", "metric", "source_value", "source_unit", "normalized_value", "normalized_unit", "normalization_factor", "source_ids"])
    write_csv(output_dir / "unit_detection_results.csv", result["document_rows"], ["company_id", "fiscal_year", "receipt_number", "source_unit", "normalized_unit", "conversion_multiplier", "parser"])
    write_csv(output_dir / "fiscal_year_mapping.csv", result["fiscal_year_mapping_rows"], ["company_id", "receipt_number", "report_title", "filed_at", "mapped_fiscal_year", "mapping_method"])
    write_csv(output_dir / "dart_sources.csv", result["source_rows"], ["company_id", "source_id", "source_type", "source_name", "title", "source_url", "published_at", "accessed_at", "publisher", "primary_source", "confidence", "verification_note"])
    write_csv(output_dir / "source_registry.csv", result["source_rows"], ["company_id", "source_id", "source_type", "source_name", "title", "source_url", "published_at", "accessed_at", "publisher", "primary_source", "confidence", "verification_note"])
    write_csv(output_dir / "ambiguous_companies.csv", [row for row in result["identity_rows"] if row.get("identity_status") == "ambiguous"], ["company_id", "company_name", "legal_name", "identity_status", "identity_confidence", "not_found_reason"])
    write_csv(output_dir / "reports_not_found.csv", result["reports_not_found"], ["company_id", "company_name", "status", "searched_period", "searched_report_types", "reason"])
    write_csv(output_dir / "manual_review_required.csv", result["manual_review_rows"], ["code", "company_id", "path", "message", "severity"])
    write_csv(output_dir / "financial_reconciliation_errors.csv", [issue for issue in result["validation"]["issues"] if issue["code"] in {"value_mismatch", "asset_equation_mismatch", "cashflow_mismatch"}], ["code", "company_id", "path", "message", "severity"])
    write_csv(output_dir / "balance_equation_results.csv", result["balance_rows"], ["company_id", "fiscal_year", "assets", "liabilities", "equity", "difference", "pass", "source_ids"])
    write_csv(output_dir / "parser_failures.csv", [row for row in result["fallback_rows"] if row.get("status") != "metrics_extracted"], ["company_id", "fiscal_year", "receipt_number", "fallback_type", "status", "note"])
    write_csv(output_dir / "modular_segment_results.csv", result["modular_rows"], ["company_id", "company_name", "financial_area_status", "modular_segment_available", "modular_segment_name", "modular_segment_revenue", "modular_segment_operating_profit", "modular_segment_basis", "source_ids"])
    write_csv(output_dir / "company_revenue_mix.csv", result["revenue_mix_rows"], ["company_id", "fiscal_year", "account_code", "account_name", "source_value", "source_unit", "normalized_value", "normalized_unit", "receipt_number", "financial_scope"])
    write_csv(output_dir / "unresolved_fields.csv", [], ["company_id", "field", "reason", "next_action"])
    write_csv(output_dir / "api_key_exposure_audit.csv", [], ["scope", "checked", "hits"])
    write_csv(output_dir / "research_gaps_after_dart.csv", result["gaps_rows"], ["company_id", "company_name", "area", "status", "description", "source_ids", "verified_at"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Wave 1 DART financial enrichment.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--no-live-enrich", action="store_true", help="Skip live OpenDART enrichment before auditing.")
    args = parser.parse_args()
    if not args.no_live_enrich:
        enrich_live_data(args.input)
    result = collect_artifacts(args.input)
    write_artifacts(result, args.output_dir)
    print(json.dumps({key: value for key, value in result.items() if not key.endswith("_rows")}, ensure_ascii=False, indent=2))
    return 0 if result["validation"]["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
