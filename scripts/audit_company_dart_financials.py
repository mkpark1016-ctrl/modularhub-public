#!/usr/bin/env python3
"""Generate DART financial audit artifacts for Wave 1 companies."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_company_dart_financials import DEFAULT_INPUT, validate, wave1_companies  # noqa: E402

OUTPUT_DIR = ROOT / "artifacts" / "company-research-wave-1-dart"


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
    }


def write_artifacts(result: dict[str, Any], output_dir: Path = OUTPUT_DIR) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_payload = {key: value for key, value in result.items() if not key.endswith("_rows")}
    (output_dir / "company_dart_audit.json").write_text(json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")
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

    write_csv(output_dir / "dart_company_identity.csv", result["identity_rows"], ["company_id", "company_name", "legal_name", "dart_corp_code", "stock_code", "corp_class", "identity_status", "identity_confidence", "searched_at", "not_found_reason"])
    write_csv(output_dir / "dart_filing_inventory.csv", result["filing_rows"], ["company_id", "status", "searched_period", "searched_report_types", "reports_found_count", "selected_report_count", "searched_at", "not_found_reason"])
    write_csv(output_dir / "selected_audit_reports.csv", result["selected_rows"], ["company_id", "fiscal_year", "report_type", "receipt_number", "report_title", "filed_at", "selection_reason", "source_ids"])
    write_csv(output_dir / "audit_opinions.csv", result["audit_rows"], ["company_id", "fiscal_year", "report_type", "receipt_number", "auditor", "audit_opinion", "audit_opinion_raw", "reporting_scope", "unit", "source_ids"])
    write_csv(output_dir / "financial_statement_inventory.csv", result["statement_rows"], ["company_id", "year", "reporting_scope", "accounting_standard", "currency", "source_ids"])
    write_csv(output_dir / "financial_metrics.csv", result["metric_rows"], ["company_id", "year", "metric", "source_value", "source_unit", "normalized_value", "normalized_unit", "normalization_factor", "source_ids"])
    write_csv(output_dir / "account_mapping_results.csv", [], ["company_id", "year", "source_account", "mapped_metric", "status", "note"])
    write_csv(output_dir / "unit_normalization_results.csv", result["metric_rows"], ["company_id", "year", "metric", "source_value", "source_unit", "normalized_value", "normalized_unit", "normalization_factor", "source_ids"])
    write_csv(output_dir / "dart_sources.csv", result["source_rows"], ["company_id", "source_id", "source_type", "source_name", "title", "source_url", "published_at", "accessed_at", "publisher", "primary_source", "confidence", "verification_note"])
    write_csv(output_dir / "ambiguous_companies.csv", [row for row in result["identity_rows"] if row.get("identity_status") == "ambiguous"], ["company_id", "company_name", "legal_name", "identity_status", "identity_confidence", "not_found_reason"])
    write_csv(output_dir / "reports_not_found.csv", result["reports_not_found"], ["company_id", "company_name", "status", "searched_period", "searched_report_types", "reason"])
    write_csv(output_dir / "manual_review_required.csv", result["manual_review_rows"], ["code", "company_id", "path", "message", "severity"])
    write_csv(output_dir / "financial_reconciliation_errors.csv", [issue for issue in result["validation"]["issues"] if issue["code"] in {"value_mismatch", "asset_equation_mismatch", "cashflow_mismatch"}], ["code", "company_id", "path", "message", "severity"])
    write_csv(output_dir / "modular_segment_results.csv", result["modular_rows"], ["company_id", "company_name", "financial_area_status", "modular_segment_available", "modular_segment_name", "modular_segment_revenue", "modular_segment_operating_profit", "modular_segment_basis", "source_ids"])
    write_csv(output_dir / "research_gaps_after_dart.csv", result["gaps_rows"], ["company_id", "company_name", "area", "status", "description", "source_ids", "verified_at"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Wave 1 DART financial enrichment.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    result = collect_artifacts(args.input)
    write_artifacts(result, args.output_dir)
    print(json.dumps({key: value for key, value in result.items() if not key.endswith("_rows")}, ensure_ascii=False, indent=2))
    return 0 if result["validation"]["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
