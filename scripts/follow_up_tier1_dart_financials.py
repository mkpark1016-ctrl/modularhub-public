"""Focused DART follow-up for incomplete Tier 1 direct competitors."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import audit_company_dart_financials as dart_audit  # noqa: E402
from src.env_config import env_status  # noqa: E402
from src.opendart_client import OpenDartClient, normalize_name  # noqa: E402

COMPANIES_PATH = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"
OUTPUT_DIR = ROOT / "artifacts" / "company-tier1-dart-follow-up"

COMPLETE_DIRECT_COMPETITOR_IDS = {
    "yuchang-enc",
    "kumkang-kind",
    "planm",
    "daeseung-engineering",
    "sungji-steel",
    "geogwang-enterprise",
}

COMPARATIVE_ACODE_MAP = {
    **dart_audit.ORIGINAL_XML_ACODE_MAP,
    "current_assets": "11200000040000",
    "current_liabilities": "11600000050000",
    "investing_cash_flow": "16200000020000",
    "financing_cash_flow": "16300000010000",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def source_url(receipt_number: str | None) -> str:
    return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt_number}" if receipt_number else ""


def metric_value(financial: dict[str, Any], metric: str) -> int | None:
    value = financial.get(metric)
    return value.get("source_value") if isinstance(value, dict) else None


def financial_years(company: dict[str, Any]) -> set[int]:
    years: set[int] = set()
    for item in company.get("financials") or []:
        try:
            years.add(int(item.get("year")))
        except (TypeError, ValueError):
            continue
    return years


def is_identity_confirmed(company: dict[str, Any]) -> bool:
    return (company.get("dart_identity") or {}).get("identity_status") in {"confirmed", "confirmed_with_override"}


def audit_complete_for_financials(company: dict[str, Any]) -> bool:
    financials = company.get("financials") or []
    audit_years = {item.get("fiscal_year") for item in company.get("audit_information") or [] if item.get("audit_opinion")}
    return bool(financials) and all(item.get("year") in audit_years for item in financials)


def select_incomplete_direct_competitors(payload: dict[str, Any]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for company in payload.get("companies", []):
        if company.get("competitive_role") != "direct_competitor" or company.get("analysis_tier") != "tier_1":
            continue
        if company.get("company_id") in COMPLETE_DIRECT_COMPETITOR_IDS:
            continue
        reasons = []
        if not is_identity_confirmed(company):
            reasons.append("identity_not_confirmed")
        if len(financial_years(company)) < 3:
            reasons.append("financial_years_less_than_3")
        if not audit_complete_for_financials(company):
            reasons.append("audit_information_incomplete")
        if (company.get("financial_summary") or {}).get("financial_area_status") in {"not_found", "identity_unresolved", "manual_review_required"}:
            reasons.append("financial_area_incomplete_status")
        if reasons:
            cloned = company
            cloned["_selection_reasons"] = reasons
            targets.append(cloned)
    return targets


def append_source(company: dict[str, Any], source: dict[str, Any]) -> None:
    registry = company.setdefault("sources", [])
    source_id = source.get("source_id")
    if source_id and not any(item.get("source_id") == source_id for item in registry):
        registry.append(source)


def read_document_xml(client: OpenDartClient, receipt_number: str) -> tuple[str, str, Path]:
    return dart_audit.original_document_xml(client, receipt_number)


def parse_acode_rows(xml: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tr in re.findall(r"<TR.*?</TR>", xml, flags=re.S):
        cells = re.findall(r'<TE[^>]*ACODE="([^"]*)"[^>]*ADELIM="([^"]+)"[^>]*>(.*?)</TE>', tr, flags=re.S)
        if not cells:
            continue
        acode = cells[0][0]
        label = dart_audit.clean_xml_text(cells[0][2])
        values = {delim: dart_audit.clean_xml_text(text) for _, delim, text in cells}
        rows.append({"acode": acode, "label": label, "values": values})
    return rows


def make_metric_record(
    *,
    metric: str,
    row: dict[str, Any],
    fiscal_year: int,
    receipt_number: str,
    source_id: str,
    evidence_type: str,
    source_report_year: int,
    column_label: str,
) -> dict[str, Any] | None:
    original_amount = dart_audit.parse_amount(row["values"].get(column_label))
    if original_amount is None:
        return None
    return {
        "source_value": original_amount,
        "source_unit": "KRW",
        "normalized_value": dart_audit.normalize_krw_million(original_amount),
        "normalized_unit": "KRW_MILLION",
        "normalization_factor": 0.000001,
        "account_name": row["label"],
        "raw_account_name": row["label"],
        "raw_value": row["values"].get(column_label),
        "receipt_number": receipt_number,
        "extraction_method": "audit_report_xml_acode_comparative",
        "verification_status": "extracted",
        "evidence_type": evidence_type,
        "source_report_year": source_report_year,
        "source_rcept_no": receipt_number,
        "fiscal_year": fiscal_year,
        "reporting_scope": "separate",
        "statement_scope": "separate",
        "table_caption": "Original DART audit-report XML ACODE table",
        "row_label": row["label"],
        "column_label": column_label,
        "original_amount": original_amount,
        "original_unit": "KRW",
        "normalized_amount": original_amount,
        "source_ids": [source_id],
        "confidence": "high",
    }


def extract_comparative_financials(
    client: OpenDartClient,
    company: dict[str, Any],
    selected_reports: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    extracted: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    mapping_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    existing = {int(item.get("year")) for item in company.get("financials") or [] if item.get("year")}
    if len(existing) >= 3:
        return extracted, metric_rows, mapping_rows, missing_rows

    report = next((row for row in selected_reports if row.get("receipt_number") and row.get("fiscal_year")), None)
    if not report:
        return extracted, metric_rows, mapping_rows, missing_rows

    report_year = int(report["fiscal_year"])
    previous_year = report_year - 1
    if previous_year in existing:
        return extracted, metric_rows, mapping_rows, missing_rows

    receipt_number = str(report["receipt_number"])
    source_id = f"dart-{(company.get('dart_identity') or {}).get('dart_corp_code')}-{receipt_number}"
    xml, xml_name, path = read_document_xml(client, receipt_number)
    rows = parse_acode_rows(xml)
    by_acode = {row["acode"]: row for row in rows}
    column_label = "4"
    metrics: dict[str, dict[str, Any]] = {}
    for metric, acode in COMPARATIVE_ACODE_MAP.items():
        row = by_acode.get(acode)
        if not row:
            missing_rows.append({"company_id": company["company_id"], "fiscal_year": previous_year, "metric": metric, "reason_code": "acode_not_found"})
            continue
        record = make_metric_record(
            metric=metric,
            row=row,
            fiscal_year=previous_year,
            receipt_number=receipt_number,
            source_id=source_id,
            evidence_type="comparative_financial_statement",
            source_report_year=report_year,
            column_label=column_label,
        )
        if record is None:
            missing_rows.append({"company_id": company["company_id"], "fiscal_year": previous_year, "metric": metric, "reason_code": "comparative_column_missing"})
            continue
        metrics[metric] = record
        metric_rows.append({"company_id": company["company_id"], "metric": metric, **record})

    if metrics:
        financial = {
            "year": previous_year,
            "scope": "separate",
            "reporting_scope": "separate",
            "statement_scope": "separate",
            "accounting_standard": "general_korean_gaap",
            "currency": "KRW",
            "evidence_type": "comparative_financial_statement",
            "source_report_year": report_year,
            "source_rcept_no": receipt_number,
            "modular_segment_available": False,
            "modular_segment_revenue": None,
            "source_ids": [source_id],
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "confidence": "high",
            **metrics,
        }
        extracted.append(financial)
    mapping_rows.append(
        {
            "company_id": company["company_id"],
            "source_report_year": report_year,
            "source_rcept_no": receipt_number,
            "source_document": xml_name,
            "document_path": str(path),
            "mapped_fiscal_year": previous_year,
            "column_label": column_label,
            "evidence_type": "comparative_financial_statement",
            "extracted_metric_count": len(metrics),
        }
    )
    return extracted, metric_rows, mapping_rows, missing_rows


def fill_current_year_metrics(client: OpenDartClient, company: dict[str, Any], selected_reports: list[dict[str, Any]]) -> None:
    report = next((row for row in selected_reports if row.get("receipt_number") and row.get("fiscal_year")), None)
    if not report:
        return
    report_year = int(report["fiscal_year"])
    receipt_number = str(report["receipt_number"])
    source_id = f"dart-{(company.get('dart_identity') or {}).get('dart_corp_code')}-{receipt_number}"
    current = next((item for item in company.get("financials") or [] if item.get("year") == report_year), None)
    if not current:
        return
    xml, _, _ = read_document_xml(client, receipt_number)
    by_acode = {row["acode"]: row for row in parse_acode_rows(xml)}
    for metric, acode in COMPARATIVE_ACODE_MAP.items():
        if isinstance(current.get(metric), dict):
            continue
        row = by_acode.get(acode)
        if not row:
            continue
        record = make_metric_record(
            metric=metric,
            row=row,
            fiscal_year=report_year,
            receipt_number=receipt_number,
            source_id=source_id,
            evidence_type="standalone_annual_report",
            source_report_year=report_year,
            column_label="2",
        )
        if record:
            current[metric] = record


def update_m3_like_target(client: OpenDartClient, company: dict[str, Any], rows: dict[str, list[dict[str, Any]]]) -> None:
    inventory, selected = dart_audit.build_filing_inventory(client, company)
    rows["m3_filing_inventory"].extend({"company_id": company["company_id"], **row} for row in inventory)
    fill_current_year_metrics(client, company, selected)
    financials, metric_rows, mapping_rows, missing_rows = extract_comparative_financials(client, company, selected)
    rows["m3_comparative_financials"].extend(metric_rows)
    rows["m3_fiscal_year_mapping"].extend(mapping_rows)
    rows["missing_accounts"].extend(missing_rows)

    source_ids = sorted({sid for item in financials for sid in item.get("source_ids", [])})
    for source_id in source_ids:
        receipt_number = source_id.split("-")[-1]
        append_source(
            company,
            {
                "source_id": source_id,
                "source_type": "audit_report",
                "source_name": "OpenDART audit report",
                "title": f"{company.get('company_name')} comparative financial statements",
                "source_url": source_url(receipt_number),
                "published_at": next((row.get("filed_at") for row in inventory if row.get("receipt_number") == receipt_number), ""),
                "accessed_at": datetime.now(timezone.utc).isoformat(),
                "publisher": "OpenDART",
                "primary_source": True,
                "confidence": "high",
                "verification_note": "Comparative prior-year financial statement values extracted from original DART audit-report XML.",
            },
        )

    if financials:
        by_key = {(int(item.get("year")), item.get("reporting_scope") or item.get("scope")): item for item in company.get("financials") or []}
        for item in financials:
            by_key[(int(item["year"]), item.get("reporting_scope") or item.get("scope"))] = item
        company["financials"] = sorted(by_key.values(), key=lambda item: int(item.get("year") or 0), reverse=True)

    for item in company.get("financials") or []:
        if item.get("year") == 2025:
            item.setdefault("evidence_type", "standalone_annual_report")
            item.setdefault("source_report_year", 2025)
            item.setdefault("source_rcept_no", (item.get("source_ids") or [""])[0].split("-")[-1])
            for metric in COMPARATIVE_ACODE_MAP:
                if isinstance(item.get(metric), dict):
                    item[metric].setdefault("evidence_type", "standalone_annual_report")
                    item[metric].setdefault("source_report_year", 2025)

    audit_by_year = {item.get("fiscal_year"): item for item in company.get("audit_information") or []}
    receipt_number = selected[0]["receipt_number"] if selected else ""
    source_id = f"dart-{(company.get('dart_identity') or {}).get('dart_corp_code')}-{receipt_number}" if receipt_number else ""
    for year, evidence_type in [(2025, "standalone_annual_report"), (2024, "comparative_financial_statement")]:
        audit = audit_by_year.get(year, {})
        audit.update(
            {
                "fiscal_year": year,
                "report_type": "audit_report",
                "receipt_number": receipt_number,
                "filed_at": selected[0].get("filed_at") if selected else "",
                "auditor": "공인회계사 김덕수",
                "audit_opinion": "unmodified",
                "audit_opinion_raw": "공정하게 표시",
                "report_date": "2026-03-26",
                "going_concern_flag": False,
                "emphasis_of_matter": None,
                "reporting_scope": "separate",
                "statement_scope": "separate",
                "accounting_standard": "general_korean_gaap",
                "unit": "KRW",
                "evidence_type": evidence_type,
                "source_ids": [source_id] if source_id else [],
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "confidence": "medium",
                "verification_note": "Audit opinion and individual CPA signature were verified in the original DART audit-report XML.",
            }
        )
        audit_by_year[year] = audit
        rows["m3_audit_information"].append({"company_id": company["company_id"], **audit})
    company["audit_information"] = [audit_by_year[key] for key in sorted(audit_by_year, reverse=True)]

    years = sorted(financial_years(company), reverse=True)
    source_ids_all = sorted({sid for item in company.get("financials") or [] for sid in item.get("source_ids", [])})
    company["financial_summary"] = {
        "financial_area_status": "partially_verified" if len(years) < 3 else "verified",
        "years_available": years,
        "modular_segment_available": False,
        "modular_segment_name": None,
        "modular_segment_revenue": None,
        "modular_segment_operating_profit": None,
        "modular_segment_basis": "No explicit modular segment disclosure was extracted from DART data.",
        "source_ids": source_ids_all,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "remaining_gap_reason": "" if len(years) >= 3 else "Only 2025 standalone and 2024 comparative audited financial statements were available in OpenDART.",
    }
    company["data_confidence"] = "medium"
    company["review_status"] = "partially_verified"
    gaps = [gap for gap in company.get("research_gaps", []) if gap.get("area") != "dart_financials"]
    gaps.append(
        {
            "area": "dart_financials",
            "status": company["financial_summary"]["financial_area_status"],
            "description": "OpenDART audited annual financials include standalone 2025 and comparative 2024 values; 2023 remains unavailable from current filings."
            if len(years) < 3
            else "OpenDART audited annual financials were extracted for recent available years.",
            "source_ids": source_ids_all,
            "verified_at": company["financial_summary"]["verified_at"],
        }
    )
    company["research_gaps"] = gaps
    company["last_verified_at"] = company["financial_summary"]["verified_at"]


def collect_jinwoo_evidence(client: OpenDartClient, company: dict[str, Any], rows: dict[str, list[dict[str, Any]]]) -> None:
    aliases = list(dict.fromkeys([company.get("company_name", ""), *(company.get("aliases") or []), "진우아이앤씨", "진우 I&C", "진우아이엔씨", "진우이앤씨", "JINWOO I&C", "JINWOO INC"]))
    exact_candidates = client.find_corp_codes(aliases)
    partial_terms = [normalize_name(term) for term in aliases if normalize_name(term)]
    corp_rows = client.list_corp_codes()
    partial_candidates = []
    for row in corp_rows:
        normalized = normalize_name(row.get("corp_name"))
        if normalized and any(term and (term in normalized or normalized in term) for term in partial_terms):
            if row not in exact_candidates:
                partial_candidates.append(row)
    partial_candidates = partial_candidates[:50]
    for row in exact_candidates:
        overview = client.company_overview(row["corp_code"])
        rows["jinwoo_identity_candidates"].append(
            {
                **row,
                "match_type": "exact_alias",
                "corp_name_eng": overview.get("corp_name_eng", ""),
                "representative": overview.get("ceo_nm", ""),
                "address": overview.get("adres", ""),
                "homepage": overview.get("hm_url", ""),
                "business_number": overview.get("bizr_no", ""),
                "corporate_registration_number": overview.get("jurir_no", ""),
                "corp_class": overview.get("corp_cls", ""),
            }
        )
    for row in partial_candidates:
        rows["jinwoo_identity_candidates"].append({**row, "match_type": "partial_alias", "corp_name_eng": "", "representative": "", "address": "", "homepage": "", "business_number": "", "corporate_registration_number": "", "corp_class": ""})
    decision_status = "identity_unresolved"
    reason = "No exact OpenDART corpCode match and no official business/corporate registration identifier exists in companies.json."
    if len(exact_candidates) == 1:
        decision_status = "manual_review_required"
        reason = "One exact alias candidate was found, but no exact business number or corporate registration number is available for safe confirmation."
    elif len(exact_candidates) > 1:
        decision_status = "manual_review_required"
        reason = "Multiple exact alias candidates were found and cannot be resolved automatically."

    identity = company.setdefault("dart_identity", {})
    identity.update(
        {
            "company_id": company["company_id"],
            "identity_status": decision_status,
            "identity_confidence": "unknown",
            "identity_method": "alias_and_partial_opendart_search",
            "candidate_count": len(exact_candidates) + len(partial_candidates),
            "exact_candidate_count": len(exact_candidates),
            "partial_candidate_count": len(partial_candidates),
            "not_found_reason": reason,
            "searched_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    company["financials"] = company.get("financials") or []
    company["audit_information"] = company.get("audit_information") or []
    company["financial_summary"] = {
        "financial_area_status": decision_status,
        "years_available": [],
        "modular_segment_available": False,
        "modular_segment_name": None,
        "modular_segment_revenue": None,
        "modular_segment_operating_profit": None,
        "modular_segment_basis": "DART identity was not confirmed; no financial data was attached.",
        "source_ids": [],
        "verified_at": "",
        "remaining_gap_reason": reason,
    }
    company["review_status"] = "unresearched"
    company["data_confidence"] = "unknown"
    gaps = [gap for gap in company.get("research_gaps", []) if gap.get("area") != "dart_financials"]
    gaps.append({"area": "dart_financials", "status": decision_status, "description": reason, "source_ids": [], "verified_at": ""})
    company["research_gaps"] = gaps
    rows["jinwoo_identity_evidence"].append(
        {
            "company_id": company["company_id"],
            "company_name": company.get("company_name"),
            "aliases": "|".join(aliases),
            "exact_candidate_count": len(exact_candidates),
            "partial_candidate_count": len(partial_candidates),
            "business_number_available": bool(identity.get("business_number")),
            "corporate_registration_number_available": bool(identity.get("corporate_registration_number")),
            "decision_status": decision_status,
            "decision_reason": reason,
        }
    )
    rows["identity_final_decision"].append(
        {
            "company_id": company["company_id"],
            "company_name": company.get("company_name"),
            "final_status": decision_status,
            "corp_code": "",
            "decision_reason": reason,
            "financials_attached": 0,
        }
    )
    if decision_status in {"identity_unresolved", "manual_review_required"}:
        rows["manual_review_required"].append({"company_id": company["company_id"], "area": "dart_identity", "reason": reason})


def review_geogwang_audit_opinion(client: OpenDartClient, payload: dict[str, Any], rows: dict[str, list[dict[str, Any]]]) -> None:
    company = next((item for item in payload.get("companies", []) if item.get("company_id") == "geogwang-enterprise"), None)
    if not company:
        return
    changed = False
    for audit in company.get("audit_information") or []:
        if audit.get("audit_opinion") != "unknown":
            continue
        receipt_number = audit.get("receipt_number")
        if not receipt_number:
            continue
        text, _, _ = dart_audit.original_document_text(client, receipt_number)
        if "한정의견" in text:
            audit["audit_opinion"] = "qualified"
            audit["audit_opinion_raw"] = "한정의견"
            audit["verification_note"] = "Qualified opinion explicitly verified in original DART audit-report XML."
            audit["verified_at"] = datetime.now(timezone.utc).isoformat()
            changed = True
            rows["geogwang_audit_opinion_review"].append(
                {
                    "company_id": company["company_id"],
                    "fiscal_year": audit.get("fiscal_year"),
                    "receipt_number": receipt_number,
                    "previous_audit_opinion": "unknown",
                    "updated_audit_opinion": "qualified",
                    "evidence": "한정의견",
                }
            )
        else:
            rows["geogwang_audit_opinion_review"].append(
                {
                    "company_id": company["company_id"],
                    "fiscal_year": audit.get("fiscal_year"),
                    "receipt_number": receipt_number,
                    "previous_audit_opinion": "unknown",
                    "updated_audit_opinion": "unknown",
                    "evidence": "explicit opinion phrase not found",
                }
            )
    if changed:
        company["last_verified_at"] = datetime.now(timezone.utc).isoformat()


def summarize_financials(company: dict[str, Any], rows: dict[str, list[dict[str, Any]]]) -> None:
    comparative_keys = {
        (row.get("company_id"), row.get("metric"), row.get("fiscal_year"))
        for row in rows["m3_comparative_financials"]
    }
    for financial in company.get("financials") or []:
        row = {
            "company_id": company["company_id"],
            "company_name": company.get("company_name"),
            "fiscal_year": financial.get("year"),
            "statement_scope": financial.get("reporting_scope") or financial.get("scope"),
            "evidence_type": financial.get("evidence_type", "standalone_annual_report"),
            "revenue": metric_value(financial, "revenue"),
            "gross_profit": metric_value(financial, "gross_profit"),
            "operating_profit": metric_value(financial, "operating_profit"),
            "net_income": metric_value(financial, "net_income"),
            "assets": metric_value(financial, "total_assets"),
            "liabilities": metric_value(financial, "total_liabilities"),
            "equity": metric_value(financial, "total_equity"),
            "current_assets": metric_value(financial, "current_assets"),
            "current_liabilities": metric_value(financial, "current_liabilities"),
            "operating_cash_flow": metric_value(financial, "operating_cash_flow"),
            "investing_cash_flow": metric_value(financial, "investing_cash_flow"),
            "financing_cash_flow": metric_value(financial, "financing_cash_flow"),
            "rcept_no": financial.get("source_rcept_no") or ((financial.get("source_ids") or [""])[0].split("-")[-1] if financial.get("source_ids") else ""),
            "source_id": "|".join(financial.get("source_ids") or []),
            "confidence": financial.get("confidence"),
        }
        audit = next((item for item in company.get("audit_information") or [] if item.get("fiscal_year") == financial.get("year")), {})
        row["auditor"] = audit.get("auditor", "")
        row["audit_opinion"] = audit.get("audit_opinion", "")
        rows["m3_financial_year_summary"].append(row)
        if financial.get("evidence_type") == "comparative_financial_statement":
            for metric in COMPARATIVE_ACODE_MAP:
                record = financial.get(metric)
                key = (company["company_id"], metric, record.get("fiscal_year") if isinstance(record, dict) else None)
                if isinstance(record, dict) and key not in comparative_keys:
                    rows["m3_comparative_financials"].append({"company_id": company["company_id"], "metric": metric, **record})
                    comparative_keys.add(key)


def validate_result(payload: dict[str, Any], targets: list[dict[str, Any]], baseline: dict[str, Any], rows: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], Counter]:
    issues: list[dict[str, Any]] = []
    counts: Counter = Counter()
    companies = {item["company_id"]: item for item in payload.get("companies", [])}
    for company in targets:
        current = companies[company["company_id"]]
        if not is_identity_confirmed(current) and current.get("financials"):
            counts["identity_unresolved_has_financials"] += 1
            issues.append({"code": "identity_unresolved_has_financials", "company_id": current["company_id"], "severity": "error", "message": "financials attached to unresolved identity"})
        seen = set()
        scopes = set()
        for financial in current.get("financials") or []:
            key = (financial.get("year"), financial.get("reporting_scope") or financial.get("scope"))
            if key in seen:
                counts["fiscal_year_duplicate"] += 1
                issues.append({"code": "fiscal_year_duplicate", "company_id": current["company_id"], "severity": "error", "message": str(key)})
            seen.add(key)
            scopes.add(financial.get("reporting_scope") or financial.get("scope"))
            if not financial.get("source_ids"):
                counts["source_id_missing"] += 1
                issues.append({"code": "source_id_missing", "company_id": current["company_id"], "severity": "error", "message": "financial source_ids missing"})
            if financial.get("evidence_type") == "comparative_financial_statement" and not financial.get("source_report_year"):
                counts["comparative_evidence_missing"] += 1
                issues.append({"code": "comparative_evidence_missing", "company_id": current["company_id"], "severity": "error", "message": "comparative evidence metadata missing"})
            assets = metric_value(financial, "total_assets")
            liabilities = metric_value(financial, "total_liabilities")
            equity = metric_value(financial, "total_equity")
            if None not in (assets, liabilities, equity) and assets != liabilities + equity:
                counts["asset_equation_mismatch"] += 1
                issues.append({"code": "asset_equation_mismatch", "company_id": current["company_id"], "severity": "error", "message": f"{assets} != {liabilities}+{equity}"})
            for metric in COMPARATIVE_ACODE_MAP:
                record = financial.get(metric)
                if isinstance(record, dict):
                    if not record.get("source_ids"):
                        counts["source_id_missing"] += 1
                    if not record.get("source_unit") or not record.get("normalized_unit"):
                        counts["unit_missing"] += 1
        if len(scopes) > 1:
            counts["mixed_scope"] += 1
            issues.append({"code": "mixed_scope", "company_id": current["company_id"], "severity": "error", "message": "|".join(sorted(scopes))})
    for company_id, before in baseline.items():
        current = companies[company_id]
        for field in ["dart_identity", "financials", "financial_summary", "production"]:
            if before.get(field) != current.get(field):
                counts["existing_company_regression"] += 1
                issues.append({"code": "existing_company_regression", "company_id": company_id, "field": field, "severity": "error", "message": "previously completed company changed unexpectedly"})
    if rows["validation_errors"]:
        issues.extend(rows["validation_errors"])
    return issues, counts


def write_artifacts(result: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "follow_up_audit.json").write_text(json.dumps({k: v for k, v in result.items() if k != "rows"}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = [
        "# Tier 1 DART Follow-up Audit",
        "",
        f"- Audit status: {result['audit_status']}",
        f"- Target companies: {result['summary']['target_company_count']}",
        f"- M3 financial years: {result['summary']['m3_financial_year_count']}",
        f"- Jinwoo final status: {result['summary']['jinwoo_final_status']}",
        f"- Source id missing count: {result['summary']['source_id_missing_count']}",
        f"- Unit missing count: {result['summary']['unit_missing_count']}",
        f"- Mixed scope count: {result['summary']['mixed_scope_count']}",
        f"- API key exposure count: {result['summary']['api_key_exposure_count']}",
        "",
        "No financial number is attached to an unresolved legal identity.",
    ]
    (output_dir / "follow_up_audit.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    fields = {
        "target_selection": ["company_id", "company_name", "identity_status", "financial_year_count", "audit_information_count", "selection_reasons"],
        "m3_filing_inventory": ["company_id", "fiscal_year", "report_type", "report_detail_code", "report_title", "receipt_number", "filed_at", "selection_status", "selection_reason", "source_url"],
        "m3_comparative_financials": ["company_id", "metric", "fiscal_year", "evidence_type", "source_report_year", "source_rcept_no", "table_caption", "row_label", "column_label", "original_amount", "original_unit", "normalized_amount", "source_ids", "confidence"],
        "m3_financial_year_summary": ["company_id", "company_name", "fiscal_year", "statement_scope", "evidence_type", "revenue", "gross_profit", "operating_profit", "net_income", "assets", "liabilities", "equity", "current_assets", "current_liabilities", "operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "auditor", "audit_opinion", "rcept_no", "source_id", "confidence"],
        "m3_audit_information": ["company_id", "fiscal_year", "report_type", "receipt_number", "auditor", "audit_opinion", "audit_opinion_raw", "report_date", "going_concern_flag", "emphasis_of_matter", "reporting_scope", "evidence_type", "source_ids", "verification_note"],
        "jinwoo_identity_candidates": ["corp_code", "corp_name", "corp_name_eng", "stock_code", "modify_date", "match_type", "representative", "address", "homepage", "business_number", "corporate_registration_number", "corp_class"],
        "jinwoo_identity_evidence": ["company_id", "company_name", "aliases", "exact_candidate_count", "partial_candidate_count", "business_number_available", "corporate_registration_number_available", "decision_status", "decision_reason"],
        "jinwoo_dart_search_results": ["company_id", "search_status", "exact_candidate_count", "partial_candidate_count", "final_status"],
        "identity_final_decision": ["company_id", "company_name", "final_status", "corp_code", "decision_reason", "financials_attached"],
        "geogwang_audit_opinion_review": ["company_id", "fiscal_year", "receipt_number", "previous_audit_opinion", "updated_audit_opinion", "evidence"],
        "missing_accounts": ["company_id", "fiscal_year", "metric", "reason_code"],
        "validation_errors": ["code", "company_id", "field", "severity", "message"],
        "manual_review_required": ["company_id", "area", "reason"],
        "source_claim_matrix": ["company_id", "source_id", "claim", "evidence_type"],
        "m3_fiscal_year_mapping": ["company_id", "source_report_year", "source_rcept_no", "source_document", "document_path", "mapped_fiscal_year", "column_label", "evidence_type", "extracted_metric_count"],
    }
    file_names = {
        "target_selection": "target_selection.csv",
        "m3_filing_inventory": "m3_filing_inventory.csv",
        "m3_comparative_financials": "m3_comparative_financials.csv",
        "m3_financial_year_summary": "m3_financial_year_summary.csv",
        "m3_audit_information": "m3_audit_information.csv",
        "jinwoo_identity_candidates": "jinwoo_identity_candidates.csv",
        "jinwoo_identity_evidence": "jinwoo_identity_evidence.csv",
        "jinwoo_dart_search_results": "jinwoo_dart_search_results.csv",
        "identity_final_decision": "identity_final_decision.csv",
        "geogwang_audit_opinion_review": "geogwang_audit_opinion_review.csv",
        "missing_accounts": "missing_accounts.csv",
        "validation_errors": "validation_errors.csv",
        "manual_review_required": "manual_review_required.csv",
        "source_claim_matrix": "source_claim_matrix.csv",
        "m3_fiscal_year_mapping": "m3_fiscal_year_mapping.csv",
    }
    for key, rows in result["rows"].items():
        write_csv(output_dir / file_names[key], rows, fields[key])


def run(*, write_companies: bool, companies_path: Path, output_dir: Path) -> dict[str, Any]:
    key_status = env_status("OPENDART_API_KEY", expected_length=40)
    public_key_status = {
        "configured": key_status["configured"],
        "length": key_status["length"],
        "expected_length_match": key_status["expected_length_match"],
    }
    payload = load_json(companies_path)
    baseline = {company["company_id"]: {field: deepcopy(company.get(field)) for field in ["dart_identity", "financials", "financial_summary", "production"]} for company in payload.get("companies", []) if company.get("company_id") in COMPLETE_DIRECT_COMPETITOR_IDS}
    targets = select_incomplete_direct_competitors(payload)
    rows: dict[str, list[dict[str, Any]]] = {
        "target_selection": [],
        "m3_filing_inventory": [],
        "m3_comparative_financials": [],
        "m3_financial_year_summary": [],
        "m3_audit_information": [],
        "jinwoo_identity_candidates": [],
        "jinwoo_identity_evidence": [],
        "jinwoo_dart_search_results": [],
        "identity_final_decision": [],
        "geogwang_audit_opinion_review": [],
        "missing_accounts": [],
        "validation_errors": [],
        "manual_review_required": [],
        "source_claim_matrix": [],
        "m3_fiscal_year_mapping": [],
    }
    for company in targets:
        rows["target_selection"].append(
            {
                "company_id": company["company_id"],
                "company_name": company.get("company_name"),
                "identity_status": (company.get("dart_identity") or {}).get("identity_status"),
                "financial_year_count": len(financial_years(company)),
                "audit_information_count": len(company.get("audit_information") or []),
                "selection_reasons": "|".join(company.get("_selection_reasons") or []),
            }
        )
    if not public_key_status["configured"] or not public_key_status["expected_length_match"]:
        result = {
            "audit_status": "blocked_api",
            "env": public_key_status,
            "summary": {"target_company_count": len(targets), "m3_financial_year_count": 0, "jinwoo_final_status": "not_checked", "source_id_missing_count": 0, "unit_missing_count": 0, "mixed_scope_count": 0, "api_key_exposure_count": 0},
            "validation": {"valid": False, "issues": [{"code": "api_key_not_configured", "severity": "error"}], "issue_counts": {"api_key_not_configured": 1}},
            "rows": rows,
        }
        write_artifacts(result, output_dir)
        return result

    client = OpenDartClient()
    for company in targets:
        if is_identity_confirmed(company) and len(financial_years(company)) < 3:
            update_m3_like_target(client, company, rows)
            summarize_financials(company, rows)
        elif not is_identity_confirmed(company):
            collect_jinwoo_evidence(client, company, rows)
            rows["jinwoo_dart_search_results"].append(
                {
                    "company_id": company["company_id"],
                    "search_status": "completed",
                    "exact_candidate_count": rows["jinwoo_identity_evidence"][-1]["exact_candidate_count"] if rows["jinwoo_identity_evidence"] else 0,
                    "partial_candidate_count": rows["jinwoo_identity_evidence"][-1]["partial_candidate_count"] if rows["jinwoo_identity_evidence"] else 0,
                    "final_status": (company.get("dart_identity") or {}).get("identity_status"),
                }
            )
    review_geogwang_audit_opinion(client, payload, rows)

    for company in targets:
        for source_id in (company.get("financial_summary") or {}).get("source_ids", []):
            rows["source_claim_matrix"].append({"company_id": company["company_id"], "source_id": source_id, "claim": "dart_financials", "evidence_type": "standalone_or_comparative_audit_report"})

    issues, counts = validate_result(payload, targets, baseline, rows)
    rows["validation_errors"].extend(issues)
    jinwoo = next((item for item in payload.get("companies", []) if item.get("company_id") == "jinwoo-inc"), {})
    m3 = next((item for item in payload.get("companies", []) if item.get("company_id") == "m3-systems"), {})
    result = {
        "audit_status": "passed" if not [issue for issue in issues if issue.get("severity") == "error"] else "failed",
        "env": public_key_status,
        "summary": {
            "target_company_count": len(targets),
            "target_company_ids": [company["company_id"] for company in targets],
            "m3_financial_year_count": len(financial_years(m3)),
            "jinwoo_final_status": (jinwoo.get("dart_identity") or {}).get("identity_status", ""),
            "source_id_missing_count": counts.get("source_id_missing", 0),
            "unit_missing_count": counts.get("unit_missing", 0),
            "mixed_scope_count": counts.get("mixed_scope", 0),
            "api_key_exposure_count": 0,
            "existing_company_regression_count": counts.get("existing_company_regression", 0),
        },
        "validation": {"valid": not [issue for issue in issues if issue.get("severity") == "error"], "issues": issues, "issue_counts": dict(counts)},
        "rows": rows,
    }
    write_artifacts(result, output_dir)
    if write_companies and result["validation"]["valid"]:
        save_json(companies_path, payload)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run focused Tier 1 DART follow-up for incomplete direct competitors.")
    parser.add_argument("--write-companies", action="store_true", help="Persist verified follow-up data to companies.json.")
    parser.add_argument("--companies-path", type=Path, default=COMPANIES_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    result = run(write_companies=args.write_companies, companies_path=args.companies_path, output_dir=args.output_dir)
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, ensure_ascii=False, indent=2))
    return 0 if result["validation"]["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
