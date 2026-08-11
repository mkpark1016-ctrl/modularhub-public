#!/usr/bin/env python3
"""Build read-only audit-financial candidates for the four general contractors.

The script never writes public data. Live runs require OPENDART_API_KEY and emit
candidate/diagnostic artifacts only. Candidates must pass the existing audit
validator before a later guarded onboarding/promotion PR may use them.
"""

from __future__ import annotations

import argparse
import json
import re
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


def audit_report_candidates(
    inventory: list[dict[str, Any]],
    *,
    year: int,
    financial_report: dict[str, Any],
    selected_report: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return deterministic same-year candidates for audit metadata parsing.

    The financial receipt remains authoritative for all amounts. A different
    report may only supply auditor/opinion metadata and is recorded as a
    cross-check source in the candidate contract.
    """

    ordered: list[dict[str, Any]] = [financial_report]
    if selected_report:
        ordered.append(selected_report)
    remainder = [report for report in inventory if int(report.get("fiscal_year") or 0) == year]
    remainder.sort(
        key=lambda report: (
            bool(report.get("correction")),
            not bool(report.get("final_report")),
            getattr(dart_audit, "REPORT_PRIORITY", {}).get(str(report.get("report_type")), 99),
            str(report.get("filed_at") or ""),
        )
    )
    ordered.extend(remainder)

    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for report in ordered:
        receipt = str(report.get("receipt_number") or "").strip()
        if not receipt or receipt in seen:
            continue
        seen.add(receipt)
        deduped.append(report)
    return deduped


def audit_metadata(
    client: OpenDartClient,
    financial_report: dict[str, Any],
    *,
    financial_receipt_number: str,
    candidates: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    best: tuple[int, dict[str, Any], dict[str, Any]] | None = None

    for report in candidates:
        receipt_number = str(report.get("receipt_number") or "").strip()
        try:
            parsed = dart_audit.parse_original_document_audit_info(client, receipt_number)
        except Exception as exc:
            attempts.append(
                {
                    "receipt_number": receipt_number,
                    "report_title": report.get("report_title"),
                    "status": "parse_error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        auditor = str(parsed.get("auditor") or "").strip()
        opinion = str(parsed.get("audit_opinion") or "unknown")
        score = 2 if auditor and opinion != "unknown" else 1 if auditor else 0
        attempts.append(
            {
                "receipt_number": receipt_number,
                "report_title": report.get("report_title"),
                "status": "parsed",
                "auditor": auditor or None,
                "audit_opinion": opinion,
                "score": score,
            }
        )
        if score > 0 and (best is None or score > best[0]):
            best = (score, report, parsed)
        if score == 2:
            break

    if best is None:
        raise ValueError(f"no same-year filing yielded verified auditor metadata for {financial_receipt_number}")

    _, audit_report, parsed = best
    audit_receipt = str(audit_report.get("receipt_number") or "")
    return (
        {
            # The adapter uses this receipt for every numeric source reference.
            "receipt_number": financial_receipt_number,
            "filed_at": financial_report.get("filed_at"),
            "financial_report_title": financial_report.get("report_title"),
            # Audit metadata may come from a same-year cross-check filing.
            "audit_receipt_number": audit_receipt,
            "audit_filed_at": audit_report.get("filed_at"),
            "audit_report_title": audit_report.get("report_title"),
            "auditor": parsed.get("auditor"),
            "audit_opinion": parsed.get("audit_opinion", "unknown"),
            "audit_opinion_raw": parsed.get("audit_opinion_raw"),
            "reporting_scope": parsed.get("reporting_scope"),
            "accounting_standard": parsed.get("accounting_standard"),
            "source_url": financial_report.get("source_url"),
            "audit_source_url": audit_report.get("source_url"),
        },
        attempts,
    )


def _iso_date(value: Any) -> str:
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    if len(digits) != 8:
        raise ValueError(f"invalid filing date: {value!r}")
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"


def attach_audit_cross_check_sources(candidate: dict[str, Any], metadata: dict[int, dict[str, Any]]) -> None:
    company_id = str(candidate["company_id"])
    for year in TARGET_YEARS:
        meta = metadata[year]
        financial_receipt = str(meta["receipt_number"])
        audit_receipt = str(meta.get("audit_receipt_number") or financial_receipt)
        if audit_receipt == financial_receipt:
            continue

        safe_receipt = re.sub(r"[^0-9A-Za-z_-]", "", audit_receipt)
        audit_ref = f"{company_id}_opendart_audit_{year}_{safe_receipt}"
        financial_ref = candidate["source_priority"][str(year)]["primary_source_ref"]
        opinion_record = next(
            row for row in candidate["audit_opinions"] if int(row["covered_years"][0]) == year
        )

        candidate["source_documents"][audit_ref] = {
            "filename": f"OpenDART audit metadata receipt {audit_receipt}",
            "report_date": _iso_date(meta.get("audit_filed_at")),
            "covered_years": [year],
            "auditor": meta["auditor"],
            "auditor_report_date": None,
            "auditor_report_date_verification_status": "pending_manual_page_check",
            "auditor_report_date_note": "OpenDART 원문에서 독립감사인 보고서 작성일은 별도 수동 확인이 필요합니다.",
            "audit_opinion": opinion_record["opinion"],
            "source_role": "cross_check",
            "usage": "재무 API 기준 receipt와 분리된 동일연도 공시에서 감사인·감사의견을 교차검증한 출처",
        }
        candidate["source_documents"][financial_ref]["usage"] = (
            "OpenDART 연결 전체재무제표 API의 금액 기준 공시. "
            f"감사인·감사의견은 {audit_ref}에서 교차검증했다."
        )
        candidate["source_priority"][str(year)]["cross_check_source_refs"] = [audit_ref]
        candidate["financial_years"][str(year)]["source_refs"].append(audit_ref)
        opinion_record["source_ref"] = audit_ref


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
        diagnostics["audit_source_reports"] = {}
        diagnostics["audit_parse_attempts"] = {}

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
            financial_report = report_for_receipt(inventory, selected_report, year, financial_receipt)
            if not financial_report:
                diagnostics["errors"].append(f"{year}: no filing metadata for structured receipt {financial_receipt}")
                continue
            diagnostics["financial_source_reports"][str(year)] = financial_report

            candidates = audit_report_candidates(
                inventory,
                year=year,
                financial_report=financial_report,
                selected_report=selected_report,
            )
            metadata[year], attempts = audit_metadata(
                client,
                financial_report,
                financial_receipt_number=financial_receipt,
                candidates=candidates,
            )
            diagnostics["audit_parse_attempts"][str(year)] = attempts
            audit_receipt = str(metadata[year].get("audit_receipt_number") or "")
            diagnostics["audit_source_reports"][str(year)] = next(
                (row for row in candidates if str(row.get("receipt_number") or "") == audit_receipt),
                None,
            )

        candidate, adapter_diagnostics = build_audit_financial_candidate(
            company_id=company_id,
            structured_payloads=structured,
            filing_metadata=metadata,
        )
        attach_audit_cross_check_sources(candidate, metadata)
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
            "audit_receipts": {
                year: (row or {}).get("receipt_number")
                for year, row in (diagnostics.get("audit_source_reports") or {}).items()
            },
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
