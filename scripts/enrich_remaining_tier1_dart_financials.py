#!/usr/bin/env python3
"""Enrich remaining Tier 1 direct competitors with source-backed DART financials."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import audit_company_dart_financials as dart_audit  # noqa: E402
from resolve_company_dart_identity import (  # noqa: E402
    confirmation_result,
    normalize,
)
from src.env_config import env_status  # noqa: E402
from src.opendart_client import OpenDartClient, OpenDartResponseError  # noqa: E402

COMPANIES_PATH = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"
OUTPUT_DIR = ROOT / "artifacts" / "company-tier1-remaining-dart-enrichment"
WAVE1_IDS = {"yuchang-enc", "kumkang-kind", "planm", "daeseung-engineering"}
SEARCH_YEARS = [2025, 2024, 2023, 2022, 2021]
REPORT_TYPES = ["F001", "A001", "F002"]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def metric_value(financial: dict[str, Any], metric: str) -> int | None:
    value = financial.get(metric)
    return value.get("source_value") if isinstance(value, dict) else None


def financial_years(company: dict[str, Any]) -> set[int]:
    years = set()
    for record in company.get("financials") or []:
        year = record.get("year") or record.get("fiscal_year")
        if year:
            years.add(int(year))
    return years


def is_dart_verified(company: dict[str, Any]) -> bool:
    identity = company.get("dart_identity") or {}
    return identity.get("identity_status") == "confirmed" and len(financial_years(company)) >= 3


def select_targets(payload: dict[str, Any]) -> list[dict[str, Any]]:
    targets = []
    for company in payload.get("companies", []):
        if company.get("competitive_role") != "direct_competitor":
            continue
        if company.get("analysis_tier") != "tier_1":
            continue
        if company.get("company_id") in WAVE1_IDS:
            continue
        targets.append(company)
    return targets


def source_url(receipt_number: str | None) -> str:
    return dart_audit.source_url(receipt_number)


def append_source(company: dict[str, Any], source: dict[str, Any]) -> None:
    sources = company.setdefault("sources", [])
    existing_ids = {source.get("source_id") for source in sources}
    existing_urls = {str(source.get("source_url", "")).lower() for source in sources}
    if source.get("source_id") in existing_ids:
        return
    if source.get("source_url") and str(source.get("source_url")).lower() in existing_urls:
        return
    sources.append(source)


def resolve_identity(client: OpenDartClient, company: dict[str, Any], corp_rows: list[dict[str, str]], now: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    names = [company.get("company_name", ""), *(company.get("aliases", []) or [])]
    normalized_names = {normalize(name) for name in names if normalize(name)}
    matches = [row for row in corp_rows if normalize(row.get("corp_name")) in normalized_names]
    candidate_rows: list[dict[str, Any]] = []
    overviews: dict[str, dict[str, Any]] = {}
    for match in matches:
        overview: dict[str, Any] = {}
        try:
            overview = client.company_overview(match.get("corp_code", ""))
        except Exception as exc:  # pragma: no cover - live API guard
            overview = {"status": "api_error", "message": type(exc).__name__}
        overviews[match.get("corp_code", "")] = overview
        candidate_rows.append(
            {
                "company_id": company["company_id"],
                "company_name": company.get("company_name"),
                "candidate_corp_code": match.get("corp_code", ""),
                "corp_name": match.get("corp_name", ""),
                "stock_code": overview.get("stock_code") or match.get("stock_code", ""),
                "representative": overview.get("ceo_nm", ""),
                "address": overview.get("adres", ""),
                "website_url": overview.get("hm_url", ""),
                "business_number_present": bool(overview.get("bizr_no")),
                "corporate_registration_number_present": bool(overview.get("jurir_no")),
                "identity_decision": "candidate",
                "decision_reason": "exact normalized company or alias name match",
            }
        )
    if len(matches) == 1:
        match = matches[0]
        overview = overviews.get(match.get("corp_code", ""), {})
        status, confidence, evidence = confirmation_result(company, overview, match)
        if status == "probable":
            status = "confirmed"
        identity = {
            "company_id": company["company_id"],
            "legal_name": overview.get("corp_name") or match.get("corp_name") or company.get("company_name"),
            "normalized_legal_name": normalize(overview.get("corp_name") or match.get("corp_name") or company.get("company_name")),
            "aliases": company.get("aliases", []),
            "dart_corp_code": match.get("corp_code", ""),
            "stock_code": overview.get("stock_code") or match.get("stock_code", ""),
            "corp_class": "listed" if overview.get("stock_code") or match.get("stock_code") else {"Y": "kospi", "K": "kosdaq", "N": "konex", "E": "other"}.get(overview.get("corp_cls") or "", ""),
            "representative": overview.get("ceo_nm", ""),
            "business_number": overview.get("bizr_no", ""),
            "corporate_registration_number": overview.get("jurir_no", ""),
            "headquarters": overview.get("adres") or company.get("headquarters"),
            "website_url": overview.get("hm_url") or company.get("website_url"),
            "identity_status": status,
            "identity_confidence": confidence,
            "identity_method": "single_exact_normalized_name_match",
            "identity_source_ids": ["opendart_corp_code", "opendart_company_overview"],
            "identity_evidence": evidence,
            "verified_at": now,
            "searched_at": now,
            "candidate_count": len(matches),
            "not_found_reason": "",
        }
        for candidate in candidate_rows:
            candidate["identity_decision"] = "confirmed" if candidate["candidate_corp_code"] == identity["dart_corp_code"] else "rejected"
            candidate["decision_reason"] = "single exact normalized OpenDART corpCode match"
        return identity, candidate_rows
    if len(matches) > 1:
        return (
            {
                "company_id": company["company_id"],
                "legal_name": company.get("company_name"),
                "normalized_legal_name": normalize(company.get("company_name")),
                "aliases": company.get("aliases", []),
                "dart_corp_code": "",
                "stock_code": "",
                "corp_class": "",
                "identity_status": "ambiguous",
                "identity_confidence": "review",
                "identity_method": "multiple_exact_normalized_name_matches",
                "identity_source_ids": [],
                "identity_evidence": [f"candidate:{row.get('corp_code')}" for row in matches],
                "verified_at": "",
                "searched_at": now,
                "candidate_count": len(matches),
                "not_found_reason": "Multiple exact normalized OpenDART corpCode matches; manual review required.",
            },
            candidate_rows,
        )
    return (
        {
            "company_id": company["company_id"],
            "legal_name": company.get("company_name"),
            "normalized_legal_name": normalize(company.get("company_name")),
            "aliases": company.get("aliases", []),
            "dart_corp_code": "",
            "stock_code": "",
            "corp_class": "",
            "identity_status": "not_found",
            "identity_confidence": "unknown",
            "identity_method": "exact_normalized_name_search",
            "identity_source_ids": [],
            "identity_evidence": [],
            "verified_at": "",
            "searched_at": now,
            "candidate_count": 0,
            "not_found_reason": "No exact normalized OpenDART corpCode match for company name or aliases.",
        },
        candidate_rows,
    )


def enrich_company(client: OpenDartClient, company: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
    company["dart_identity"] = identity
    if identity.get("identity_status") not in {"confirmed", "confirmed_with_override"}:
        company["filing_availability"] = {
            "status": identity.get("identity_status"),
            "searched_period": SEARCH_YEARS,
            "searched_report_types": ["audit_report", "business_report", "consolidated_audit_report"],
            "reports_found_count": 0,
            "selected_reports": [],
            "not_found_reason": identity.get("not_found_reason", ""),
            "searched_at": identity.get("searched_at", ""),
        }
        company.setdefault("financials", [])
        company.setdefault("audit_information", [])
        company["financial_summary"] = {
            "financial_area_status": identity.get("identity_status"),
            "years_available": [],
            "modular_segment_available": False,
            "modular_segment_name": None,
            "modular_segment_revenue": None,
            "modular_segment_operating_profit": None,
            "modular_segment_basis": "DART identity was not confirmed; no financial data was attached.",
            "source_ids": [],
            "verified_at": "",
        }
        return company

    dart_audit.TARGET_FINANCIAL_YEARS = SEARCH_YEARS
    inventory, selected = dart_audit.build_filing_inventory(client, company)
    selected = sorted(selected, key=lambda item: int(item.get("fiscal_year") or 0), reverse=True)
    financials, _, manual_review = dart_audit.extract_structured_financials(client, company)
    existing_years = {int(record.get("year")) for record in financials if record.get("year")}
    fallback_financials, _, revenue_mix_rows, fallback_rows, document_rows = dart_audit.extract_original_document_financials(client, company, selected, existing_years)
    all_financials = sorted([*financials, *fallback_financials], key=lambda item: int(item.get("year") or 0), reverse=True)
    all_financials = all_financials[:3]
    selected_years = {int(item.get("year")) for item in all_financials if item.get("year")}
    selected_reports = [report for report in selected if int(report.get("fiscal_year") or 0) in selected_years]
    audit_information = []
    for report in selected_reports:
        receipt_number = report.get("receipt_number")
        parsed_audit: dict[str, Any] = {}
        if receipt_number:
            try:
                parsed_audit = dart_audit.parse_original_document_audit_info(client, receipt_number)
            except Exception as exc:  # pragma: no cover - live document guard
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
                "verification_note": parsed_audit.get("verification_note", "Filing identified from OpenDART; auditor and opinion extracted when available."),
            }
        )
    company["filings"] = inventory
    company["filing_availability"] = {
        "status": "searched",
        "searched_period": SEARCH_YEARS,
        "searched_report_types": ["audit_report", "business_report", "consolidated_audit_report"],
        "reports_found_count": len(inventory),
        "selected_reports": selected_reports,
        "not_found_reason": "" if inventory else "No F001/F002/A001 annual filing found in searched period.",
        "searched_at": datetime.now(timezone.utc).isoformat(),
    }
    if all_financials:
        company["financials"] = all_financials
    company["audit_information"] = audit_information
    if revenue_mix_rows:
        company["revenue_mix"] = revenue_mix_rows
    company["dart_original_document_fallback_results"] = fallback_rows
    company["dart_original_document_inventory"] = document_rows
    source_ids = sorted({sid for item in all_financials for sid in item.get("source_ids", [])})
    years = [item["year"] for item in all_financials]
    status = "verified" if len(years) >= 3 else ("partially_verified" if years else "filing_found_extraction_pending")
    company["financial_summary"] = {
        "financial_area_status": status,
        "years_available": years,
        "modular_segment_available": False,
        "modular_segment_name": None,
        "modular_segment_revenue": None,
        "modular_segment_operating_profit": None,
        "modular_segment_basis": "No explicit modular segment disclosure was extracted from DART data.",
        "source_ids": source_ids,
        "verified_at": datetime.now(timezone.utc).isoformat() if years else "",
    }
    gaps = [gap for gap in company.get("research_gaps", []) if gap.get("area") != "dart_financials"]
    unresolved = []
    for issue in manual_review:
        year = "".join(ch for ch in str(issue.get("path", "")) if ch.isdigit())
        if year and int(year[:4]) in selected_years:
            continue
        unresolved.append(issue)
    if len(years) >= 3:
        gaps.append({"area": "dart_financials", "status": "verified", "description": "OpenDART audited annual financials were extracted for recent available years.", "source_ids": source_ids, "verified_at": company["financial_summary"]["verified_at"]})
    elif years:
        gaps.append({"area": "dart_financials", "status": "partially_verified", "description": "Some OpenDART audited annual financials were extracted; remaining years require review.", "source_ids": source_ids, "verified_at": company["financial_summary"]["verified_at"]})
    elif unresolved:
        gaps.append({"area": "dart_financials", "status": "manual_review_required", "description": "OpenDART filings were found but financial extraction was incomplete.", "source_ids": [], "verified_at": ""})
    else:
        gaps.append({"area": "dart_financials", "status": status, "description": company["filing_availability"]["not_found_reason"], "source_ids": [], "verified_at": ""})
    company["research_gaps"] = gaps
    if len(years) >= 3:
        company["review_status"] = "partially_verified"
        company["data_confidence"] = "medium"
        company["last_verified_at"] = company["financial_summary"]["verified_at"]
    elif years:
        company["review_status"] = "partially_verified"
        company["data_confidence"] = "medium"
        company["last_verified_at"] = company["financial_summary"]["verified_at"]
    return company


def validate_targets(payload: dict[str, Any], targets: list[dict[str, Any]], baseline: dict[str, Any]) -> tuple[list[dict[str, Any]], Counter]:
    issues: list[dict[str, Any]] = []
    counts: Counter = Counter()
    corp_codes: dict[str, str] = {}
    for company in payload.get("companies", []):
        identity = company.get("dart_identity") or {}
        corp_code = identity.get("dart_corp_code")
        if corp_code:
            if corp_code in corp_codes and corp_codes[corp_code] != company["company_id"]:
                counts["duplicate_corp_code"] += 1
                issues.append({"code": "duplicate_corp_code", "company_id": company["company_id"], "message": f"corp_code duplicates {corp_codes[corp_code]}", "severity": "error"})
            corp_codes[corp_code] = company["company_id"]
    target_ids = {company["company_id"] for company in targets}
    for company in payload.get("companies", []):
        if company["company_id"] not in target_ids:
            continue
        identity = company.get("dart_identity") or {}
        if identity.get("identity_status") not in {"confirmed", "confirmed_with_override"}:
            continue
        financials = company.get("financials") or []
        if len(financials) < 3:
            counts["financial_years_less_than_3"] += 1
            issues.append({"code": "financial_years_less_than_3", "company_id": company["company_id"], "message": "less than three financial years extracted", "severity": "warning"})
        seen_years: set[tuple[int, str]] = set()
        for idx, record in enumerate(financials):
            year = int(record.get("year") or 0)
            scope = record.get("reporting_scope") or record.get("scope")
            if not scope:
                counts["scope_missing"] += 1
                issues.append({"code": "scope_missing", "company_id": company["company_id"], "path": f"financials.{idx}", "message": "statement scope is missing", "severity": "error"})
            key = (year, str(scope))
            if key in seen_years:
                counts["fiscal_year_duplicate"] += 1
                issues.append({"code": "fiscal_year_duplicate", "company_id": company["company_id"], "path": f"financials.{idx}", "message": "duplicate fiscal year/scope", "severity": "error"})
            seen_years.add(key)
            if not record.get("source_ids"):
                counts["source_id_missing"] += 1
                issues.append({"code": "source_id_missing", "company_id": company["company_id"], "path": f"financials.{idx}", "message": "financial record source_ids missing", "severity": "error"})
            for metric in ["revenue", "gross_profit", "operating_profit", "net_income", "operating_cash_flow", "total_assets", "total_liabilities", "total_equity"]:
                value = record.get(metric)
                if not isinstance(value, dict):
                    continue
                if value.get("source_value") is None:
                    continue
                if not value.get("source_ids"):
                    counts["source_id_missing"] += 1
                    issues.append({"code": "source_id_missing", "company_id": company["company_id"], "path": f"financials.{idx}.{metric}", "message": "metric source_ids missing", "severity": "error"})
                if not value.get("source_unit") or not value.get("normalized_unit"):
                    counts["unit_missing"] += 1
                    issues.append({"code": "unit_missing", "company_id": company["company_id"], "path": f"financials.{idx}.{metric}", "message": "metric unit missing", "severity": "error"})
            assets = metric_value(record, "total_assets")
            liabilities = metric_value(record, "total_liabilities")
            equity = metric_value(record, "total_equity")
            if assets is not None and liabilities is not None and equity is not None and assets != liabilities + equity:
                counts["asset_equation_mismatch"] += 1
                issues.append({"code": "asset_equation_mismatch", "company_id": company["company_id"], "path": f"financials.{idx}", "message": f"assets-liabilities-equity={assets - liabilities - equity}", "severity": "error"})
        summary = company.get("financial_summary") or {}
        if summary.get("modular_segment_available") is not False:
            counts["modular_segment_misclassification"] += 1
            issues.append({"code": "modular_segment_misclassification", "company_id": company["company_id"], "message": "modular segment should remain false unless explicitly disclosed", "severity": "error"})
    for wave_id in WAVE1_IDS:
        before = baseline.get(wave_id, {})
        after = next((company for company in payload.get("companies", []) if company.get("company_id") == wave_id), {})
        for field in ["dart_identity", "financials", "financial_summary", "production"]:
            if before.get(field) != after.get(field):
                counts["existing_wave1_regression"] += 1
                issues.append({"code": "existing_wave1_regression", "company_id": wave_id, "path": field, "message": "existing Wave 1 field changed", "severity": "error"})
    return issues, counts


def rows_for_artifacts(payload: dict[str, Any], targets: list[dict[str, Any]], candidate_rows: list[dict[str, Any]], issues: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    target_ids = {company["company_id"] for company in targets}
    by_id = {company["company_id"]: company for company in payload.get("companies", [])}
    target_rows = []
    identity_rows = []
    filing_rows = []
    selected_rows = []
    financial_rows = []
    account_rows = []
    audit_rows = []
    scope_rows = []
    fallback_rows = []
    document_rows = []
    missing_rows = []
    report_not_found_rows = []
    manual_rows = []
    source_rows = []
    ambiguous_rows = []
    for company_id in target_ids:
        company = by_id[company_id]
        identity = company.get("dart_identity") or {}
        target_rows.append({
            "company_id": company_id,
            "company_name": company.get("company_name"),
            "analysis_tier": company.get("analysis_tier"),
            "competitive_role": company.get("competitive_role"),
            "identity_status": identity.get("identity_status", ""),
            "financial_year_count": len(company.get("financials") or []),
            "selection_reason": "remaining tier_1 direct competitor without three verified DART financial years",
        })
        identity_rows.append({
            "company_id": company_id,
            "company_name": company.get("company_name"),
            "legal_name": identity.get("legal_name"),
            "corp_code": identity.get("dart_corp_code"),
            "stock_code": identity.get("stock_code"),
            "identity_status": identity.get("identity_status"),
            "identity_confidence": identity.get("identity_confidence"),
            "identity_method": identity.get("identity_method"),
            "candidate_count": identity.get("candidate_count"),
            "verified_at": identity.get("verified_at"),
            "not_found_reason": identity.get("not_found_reason"),
        })
        if identity.get("identity_status") == "ambiguous":
            ambiguous_rows.append(identity_rows[-1])
        filing = company.get("filing_availability") or {}
        filing_rows.append({
            "company_id": company_id,
            "status": filing.get("status"),
            "searched_period": "|".join(str(year) for year in filing.get("searched_period") or []),
            "searched_report_types": "|".join(filing.get("searched_report_types") or []),
            "reports_found_count": filing.get("reports_found_count", 0),
            "selected_report_count": len(filing.get("selected_reports") or []),
            "searched_at": filing.get("searched_at"),
            "not_found_reason": filing.get("not_found_reason"),
        })
        if not filing.get("reports_found_count"):
            report_not_found_rows.append({"company_id": company_id, "company_name": company.get("company_name"), "reason": filing.get("not_found_reason")})
        for report in filing.get("selected_reports") or []:
            selected_rows.append({"company_id": company_id, **report})
        for audit in company.get("audit_information") or []:
            audit_rows.append({"company_id": company_id, **audit})
        for fallback in company.get("dart_original_document_fallback_results") or []:
            fallback_rows.append({"company_id": company_id, **fallback})
        for document in company.get("dart_original_document_inventory") or []:
            document_rows.append({"company_id": company_id, **document})
        for source in company.get("sources") or []:
            if any(source.get("source_id") in item.get("source_ids", []) for item in company.get("financials") or []):
                source_rows.append({"company_id": company_id, **source})
        for financial in company.get("financials") or []:
            row = {
                "company_id": company_id,
                "company_name": company.get("company_name"),
                "corp_code": identity.get("dart_corp_code"),
                "fiscal_year": financial.get("year"),
                "statement_scope": financial.get("reporting_scope") or financial.get("scope"),
                "revenue": metric_value(financial, "revenue"),
                "gross_profit": metric_value(financial, "gross_profit"),
                "operating_profit": metric_value(financial, "operating_profit"),
                "net_income": metric_value(financial, "net_income"),
                "assets": metric_value(financial, "total_assets"),
                "liabilities": metric_value(financial, "total_liabilities"),
                "equity": metric_value(financial, "total_equity"),
                "operating_cash_flow": metric_value(financial, "operating_cash_flow"),
                "auditor": "",
                "audit_opinion": "",
                "rcept_no": "",
                "source_id": "|".join(financial.get("source_ids") or []),
                "confidence": financial.get("confidence"),
            }
            audit = next((item for item in company.get("audit_information") or [] if item.get("fiscal_year") == financial.get("year")), {})
            row["auditor"] = audit.get("auditor", "")
            row["audit_opinion"] = audit.get("audit_opinion", "")
            row["rcept_no"] = (financial.get("source_ids") or [""])[0].split("-")[-1] if financial.get("source_ids") else audit.get("receipt_number", "")
            financial_rows.append(row)
            scope_rows.append({"company_id": company_id, "fiscal_year": financial.get("year"), "statement_scope": row["statement_scope"], "source_ids": row["source_id"]})
            for metric in ["revenue", "gross_profit", "operating_profit", "net_income", "total_assets", "total_liabilities", "total_equity", "operating_cash_flow"]:
                value = financial.get(metric)
                if isinstance(value, dict):
                    account_rows.append({"company_id": company_id, "fiscal_year": financial.get("year"), "metric": metric, **value})
                else:
                    missing_rows.append({"company_id": company_id, "fiscal_year": financial.get("year"), "metric": metric, "reason": "not_extracted"})
        for gap in company.get("research_gaps") or []:
            if gap.get("area") == "dart_financials" and gap.get("status") in {"manual_review_required", "ambiguous", "not_found"}:
                manual_rows.append({"company_id": company_id, **gap})
    return {
        "target_company_selection": target_rows,
        "dart_identity_results": identity_rows,
        "dart_identity_candidates": candidate_rows,
        "dart_filing_inventory": filing_rows,
        "selected_annual_reports": selected_rows,
        "financial_year_summary": financial_rows,
        "financial_account_inventory": account_rows,
        "audit_information": audit_rows,
        "statement_scope_results": scope_rows,
        "account_alias_results": [],
        "original_document_extractions": fallback_rows + document_rows,
        "ambiguous_identities": ambiguous_rows,
        "reports_not_found": report_not_found_rows,
        "missing_accounts": missing_rows,
        "validation_errors": issues,
        "manual_review_required": manual_rows,
        "source_claim_matrix": source_rows,
    }


def write_artifacts(result: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = result.pop("rows")
    (output_dir / "dart_enrichment_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Remaining Tier 1 DART Enrichment Audit",
        "",
        f"- Audit status: {result['audit_status']}",
        f"- Target companies: {result['summary']['target_company_count']}",
        f"- Confirmed identities: {result['summary']['confirmed_identity_count']}",
        f"- Ambiguous identities: {result['summary']['ambiguous_identity_count']}",
        f"- Report not found: {result['summary']['report_not_found_count']}",
        f"- Financial years extracted: {result['summary']['financial_year_count']}",
        f"- Source ID missing: {result['summary']['source_id_missing_count']}",
        f"- Unit missing: {result['summary']['unit_missing_count']}",
        f"- Mixed scope errors: {result['summary']['mixed_scope_count']}",
        f"- Existing Wave 1 regressions: {result['summary']['existing_wave1_regression_count']}",
    ]
    (output_dir / "dart_enrichment_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    field_map = {
        "target_company_selection": ["company_id", "company_name", "analysis_tier", "competitive_role", "identity_status", "financial_year_count", "selection_reason"],
        "dart_identity_results": ["company_id", "company_name", "legal_name", "corp_code", "stock_code", "identity_status", "identity_confidence", "identity_method", "candidate_count", "verified_at", "not_found_reason"],
        "dart_identity_candidates": ["company_id", "company_name", "candidate_corp_code", "corp_name", "stock_code", "representative", "address", "website_url", "business_number_present", "corporate_registration_number_present", "identity_decision", "decision_reason"],
        "dart_filing_inventory": ["company_id", "status", "searched_period", "searched_report_types", "reports_found_count", "selected_report_count", "searched_at", "not_found_reason"],
        "selected_annual_reports": ["company_id", "fiscal_year", "report_type", "receipt_number", "report_title", "filed_at", "selection_reason", "source_ids"],
        "financial_year_summary": ["company_id", "company_name", "corp_code", "fiscal_year", "statement_scope", "revenue", "gross_profit", "operating_profit", "net_income", "assets", "liabilities", "equity", "operating_cash_flow", "auditor", "audit_opinion", "rcept_no", "source_id", "confidence"],
        "financial_account_inventory": ["company_id", "fiscal_year", "metric", "account_name", "source_value", "source_unit", "normalized_value", "normalized_unit", "receipt_number", "source_ids"],
        "audit_information": ["company_id", "fiscal_year", "report_type", "receipt_number", "auditor", "audit_opinion", "audit_opinion_raw", "reporting_scope", "accounting_standard", "unit", "source_ids", "verified_at", "confidence"],
        "statement_scope_results": ["company_id", "fiscal_year", "statement_scope", "source_ids"],
        "account_alias_results": ["company_id", "fiscal_year", "source_account", "mapped_metric", "status", "note"],
        "original_document_extractions": ["company_id", "fiscal_year", "receipt_number", "fallback_type", "status", "note", "document_name", "document_format", "parser", "statement_type", "parsed_table_rows", "extracted_metric_count"],
        "ambiguous_identities": ["company_id", "company_name", "legal_name", "identity_status", "identity_confidence", "not_found_reason"],
        "reports_not_found": ["company_id", "company_name", "reason"],
        "missing_accounts": ["company_id", "fiscal_year", "metric", "reason"],
        "validation_errors": ["code", "company_id", "path", "message", "severity"],
        "manual_review_required": ["company_id", "area", "status", "description", "source_ids", "verified_at"],
        "source_claim_matrix": ["company_id", "source_id", "source_type", "source_name", "title", "source_url", "published_at", "accessed_at", "publisher", "primary_source", "confidence", "verification_note"],
    }
    for name, fields in field_map.items():
        write_csv(output_dir / f"{name}.csv", rows.get(name, []), fields)


def run(write_companies: bool, companies_path: Path, output_dir: Path) -> dict[str, Any]:
    key_status = env_status("OPENDART_API_KEY", expected_length=40)
    public_key_status = {
        "configured": key_status["configured"],
        "length": key_status["length"],
        "expected_length_match": key_status["expected_length_match"],
    }
    payload = load_json(companies_path)
    baseline = {company["company_id"]: {field: company.get(field) for field in ["dart_identity", "financials", "financial_summary", "production"]} for company in payload.get("companies", []) if company.get("company_id") in WAVE1_IDS}
    targets = select_targets(payload)
    if not (key_status["configured"] and key_status["expected_length_match"]):
        rows = rows_for_artifacts(payload, targets, [], [{"code": "api_key_not_configured", "company_id": "", "path": "", "message": "OPENDART_API_KEY is not configured or length mismatch", "severity": "error"}])
        result = {
            "audit_status": "blocked_api",
            "env": public_key_status,
            "summary": {"target_company_count": len(targets), "confirmed_identity_count": 0, "ambiguous_identity_count": 0, "report_not_found_count": 0, "financial_year_count": 0, "source_id_missing_count": 0, "unit_missing_count": 0, "mixed_scope_count": 0, "existing_wave1_regression_count": 0},
            "validation": {"valid": False, "issues": rows["validation_errors"], "issue_counts": {"api_key_not_configured": 1}},
            "rows": rows,
        }
        write_artifacts(result, output_dir)
        return result
    client = OpenDartClient()
    corp_rows = client.list_corp_codes()
    now = datetime.now(timezone.utc).isoformat()
    all_candidate_rows: list[dict[str, Any]] = []
    by_id = {company["company_id"]: company for company in payload.get("companies", [])}
    for target in targets:
        company = by_id[target["company_id"]]
        identity, candidates = resolve_identity(client, company, corp_rows, now)
        all_candidate_rows.extend(candidates)
        enrich_company(client, company, identity)
    issues, counts = validate_targets(payload, targets, baseline)
    rows = rows_for_artifacts(payload, targets, all_candidate_rows, issues)
    confirmed_count = sum(1 for row in rows["dart_identity_results"] if row.get("identity_status") in {"confirmed", "confirmed_with_override"})
    result = {
        "audit_status": "passed" if not [issue for issue in issues if issue.get("severity") == "error"] else "failed",
        "env": public_key_status,
        "summary": {
            "target_company_count": len(targets),
            "confirmed_identity_count": confirmed_count,
            "ambiguous_identity_count": sum(1 for row in rows["dart_identity_results"] if row.get("identity_status") == "ambiguous"),
            "report_not_found_count": len(rows["reports_not_found"]),
            "financial_year_count": len(rows["financial_year_summary"]),
            "source_id_missing_count": counts.get("source_id_missing", 0),
            "unit_missing_count": counts.get("unit_missing", 0),
            "mixed_scope_count": counts.get("mixed_reporting_scope", 0),
            "existing_wave1_regression_count": counts.get("existing_wave1_regression", 0),
        },
        "validation": {"valid": not [issue for issue in issues if issue.get("severity") == "error"], "issues": issues, "issue_counts": dict(counts)},
        "rows": rows,
    }
    write_artifacts(result, output_dir)
    if write_companies:
        save_json(companies_path, payload)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich remaining Tier 1 direct competitors with OpenDART financials.")
    parser.add_argument("--companies", type=Path, default=COMPANIES_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--write-companies", action="store_true")
    args = parser.parse_args()
    result = run(args.write_companies, args.companies, args.output_dir)
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, ensure_ascii=False, indent=2))
    return 0 if result["audit_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
