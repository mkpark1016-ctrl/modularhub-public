#!/usr/bin/env python3
"""Build read-only audit-financial candidates for the four general contractors.

The script never writes public data. Live runs require OPENDART_API_KEY and emit
candidate/diagnostic artifacts only. Candidates must pass the existing audit
validator before a later guarded onboarding/promotion PR may use them.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import audit_company_dart_financials as dart_audit  # noqa: E402
from src.company_dart_audit_adapter import (  # noqa: E402
    GENERAL_CONTRACTORS,
    TARGET_YEARS,
    build_audit_financial_candidate,
)
from src.opendart_client import OpenDartClient  # noqa: E402
from validate_company_audit_financials import validate  # noqa: E402

DEFAULT_OUTPUT = ROOT / "artifacts" / "general-contractor-dart-audit"


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def filing_inventory(client: OpenDartClient, company_id: str) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    spec = GENERAL_CONTRACTORS[company_id]
    company = {
        "company_id": company_id,
        "company_name": spec["company_name"],
        "dart_identity": {
            "identity_status": "confirmed",
            "dart_corp_code": spec["corp_code"],
        },
        "sources": [],
    }
    inventory, selected = dart_audit.build_filing_inventory(client, company)
    selected_by_year = {
        int(report["fiscal_year"]): report
        for report in selected
        if report.get("fiscal_year") in TARGET_YEARS
    }
    return inventory, selected_by_year


def structured_receipts(payload: dict[str, Any]) -> list[str]:
    counts = Counter(
        str(row.get("rcept_no") or "").strip()
        for row in (payload.get("list") or [])
        if str(row.get("rcept_no") or "").strip()
    )
    return [receipt for receipt, _ in counts.most_common()]


def report_for_receipt(
    inventory: list[dict[str, Any]],
    selected_report: dict[str, Any] | None,
    year: int,
    receipt_number: str | None,
) -> dict[str, Any] | None:
    if receipt_number:
        for report in inventory:
            if int(report.get("fiscal_year") or 0) == year and str(report.get("receipt_number") or "") == receipt_number:
                return report
    return selected_report


def audit_metadata(client: OpenDartClient, report: dict[str, Any], *, financial_receipt_number: str) -> dict[str, Any]:
    receipt_number = str(report.get("receipt_number") or "")
    if receipt_number != financial_receipt_number:
        raise ValueError(
            "structured financial receipt and audit metadata receipt differ: "
            f"financial={financial_receipt_number} audit={receipt_number}"
        )
    parsed = dart_audit.parse_original_document_audit_info(client, receipt_number)
    return {
        "receipt_number": receipt_number,
        "filed_at": report.get("filed_at"),
        "auditor": parsed.get("auditor"),
        "audit_opinion": parsed.get("audit_opinion", "unknown"),
        "audit_opinion_raw": parsed.get("audit_opinion_raw"),
        "reporting_scope": parsed.get("reporting_scope"),
        "accounting_standard": parsed.get("accounting_standard"),
        "report_type": report.get("report_type"),
        "report_title": report.get("report_title"),
        "source_url": report.get("source_url"),
    }


def build_one(client: OpenDartClient, company_id: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    spec = GENERAL_CONTRACTORS[company_id]
    diagnostics: dict[str, Any] = {
        "company_id": company_id,
        "company_name": spec["company_name"],
        "corp_code": spec["corp_code"],
        "requested_scope": "CFS",
        "requested_years": list(TARGET_YEARS),
        "status": "started",
        "errors": [],
    }
    try:
        inventory, selected_reports = filing_inventory(client, company_id)
        diagnostics["filing_inventory_count"] = len(inventory)
        diagnostics["selected_reports"] = selected_reports
        metadata: dict[int, dict[str, Any]] = {}
        structured: dict[int, dict[str, Any]] = {}
        diagnostics["structured_receipts"] = {}
        diagnostics["financial_source_reports"] = {}

        for year in TARGET_YEARS:
            # Fetch CFS rows first. Their rcept_no is the authoritative filing
            # lineage for the financial amounts and must not be replaced by a
            # separately selected correction/attachment filing.
            structured[year] = client.single_account_all(
                corp_code=spec["corp_code"],
                fiscal_year=year,
                report_code="11011",
                fs_div="CFS",
            )
            rows = structured[year].get("list") or []
            diagnostics.setdefault("structured_row_counts", {})[str(year)] = len(rows)
            receipts = structured_receipts(structured[year])
            diagnostics["structured_receipts"][str(year)] = receipts

            selected_report = selected_reports.get(year)
            financial_receipt = receipts[0] if receipts else str((selected_report or {}).get("receipt_number") or "")
            if not financial_receipt:
                diagnostics["errors"].append(f"{year}: no structured or selected filing receipt")
                continue
            report = report_for_receipt(inventory, selected_report, year, financial_receipt)
            if not report:
                diagnostics["errors"].append(f"{year}: no filing metadata for structured receipt {financial_receipt}")
                continue
            diagnostics["financial_source_reports"][str(year)] = report
            metadata[year] = audit_metadata(client, report, financial_receipt_number=financial_receipt)

        candidate, adapter_diagnostics = build_audit_financial_candidate(
            company_id=company_id,
            structured_payloads=structured,
            filing_metadata=metadata,
        )
        validation = validate(candidate, expected_year_override=list(TARGET_YEARS), base_ref="origin/main")
        diagnostics["adapter"] = adapter_diagnostics
        diagnostics["validation"] = validation
        diagnostics["status"] = "validated" if validation["valid"] else "validation_failed"
        return candidate, diagnostics
    except Exception as exc:  # live-source isolation: one company must not hide the others
        diagnostics["status"] = "blocked"
        diagnostics["errors"].append(f"{type(exc).__name__}: {exc}")
        return None, diagnostics


def parse_company_ids(raw: str) -> list[str]:
    if not raw.strip():
        return list(GENERAL_CONTRACTORS)
    values = [value.strip() for value in raw.split(",") if value.strip()]
    unknown = [value for value in values if value not in GENERAL_CONTRACTORS]
    if unknown:
        raise ValueError(f"unknown company ids: {', '.join(unknown)}")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--companies", default="", help="Comma-separated company IDs; blank means all four contractors")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--require-all-valid", action="store_true", help="Exit non-zero unless every requested candidate validates")
    args = parser.parse_args()

    company_ids = parse_company_ids(args.companies)
    client = OpenDartClient()
    client.require_api_key()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "schema_version": "general-contractor-dart-audit-candidate-run-v1",
        "requested_companies": company_ids,
        "requested_scope": "CFS",
        "requested_years": list(TARGET_YEARS),
        "companies": {},
    }
    valid_count = 0
    for company_id in company_ids:
        candidate, diagnostics = build_one(client, company_id)
        company_dir = args.output_dir / company_id
        save_json(company_dir / "diagnostics.json", diagnostics)
        if candidate is not None:
            save_json(company_dir / "candidate_audit_financials.json", candidate)
        is_valid = bool((diagnostics.get("validation") or {}).get("valid"))
        valid_count += int(is_valid)
        summary["companies"][company_id] = {
            "status": diagnostics.get("status"),
            "valid": is_valid,
            "structured_row_counts": diagnostics.get("structured_row_counts", {}),
            "structured_receipts": diagnostics.get("structured_receipts", {}),
            "errors": diagnostics.get("errors", []),
            "pending_metrics": {
                year: len((row or {}).get("pending", []))
                for year, row in ((diagnostics.get("adapter") or {}).get("years") or {}).items()
            },
        }

    summary["valid_count"] = valid_count
    summary["requested_count"] = len(company_ids)
    summary["all_valid"] = valid_count == len(company_ids)
    save_json(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if args.require_all_valid and not summary["all_valid"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
