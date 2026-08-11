#!/usr/bin/env python3
"""Reconcile exact working-capital accounts for public general-contractor sources.

The command is read-only with respect to repository data: it writes candidate
artifacts to an output directory and requires a later guarded PR for promotion.
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

from scripts.validate_company_audit_financials import validate  # noqa: E402
from src.company_dart_audit_adapter import GENERAL_CONTRACTORS, TARGET_YEARS  # noqa: E402
from src.general_contractor_receivable_reconciliation import reconcile_year  # noqa: E402
from src.opendart_client import OpenDartClient  # noqa: E402

DEFAULT_INPUT_ROOT = ROOT / "data" / "company_reports"
DEFAULT_OUTPUT = ROOT / "artifacts" / "general-contractor-working-capital-reconciliation"


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def dominant_receipt(rows: list[dict[str, Any]]) -> str | None:
    counts = Counter(str(row.get("rcept_no") or "").strip() for row in rows if str(row.get("rcept_no") or "").strip())
    return counts.most_common(1)[0][0] if counts else None


def source_receipt(source_ref: str, company_id: str, year: int) -> str | None:
    prefix = f"{company_id}_opendart_{year}_"
    if not source_ref.startswith(prefix):
        return None
    suffix = source_ref[len(prefix):]
    return re.sub(r"[^0-9A-Za-z_-]", "", suffix) or None


def reconcile_company(client: OpenDartClient, company_id: str, input_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    path = input_root / company_id / "audit_financials_2023_2025.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    diagnostics: dict[str, Any] = {"company_id": company_id, "years": {}, "status": "started"}

    for year in TARGET_YEARS:
        spec = GENERAL_CONTRACTORS[company_id]
        response = client.single_account_all(
            corp_code=spec["corp_code"],
            fiscal_year=year,
            fs_div="CFS",
        )
        rows = list(response.get("list") or [])
        primary_ref = payload["source_priority"][str(year)]["primary_source_ref"]
        expected_receipt = source_receipt(primary_ref, company_id, year)
        live_receipt = dominant_receipt(rows)
        if not expected_receipt or not live_receipt or live_receipt != expected_receipt:
            raise ValueError(
                f"{company_id} {year}: financial receipt drift; public={expected_receipt} live={live_receipt}"
            )
        updated, detail = reconcile_year(payload["financial_years"][str(year)], rows, primary_ref)
        payload["financial_years"][str(year)] = updated
        diagnostics["years"][str(year)] = {
            "financial_receipt": live_receipt,
            **detail,
        }

    result = validate(payload, expected_year_override=list(TARGET_YEARS), base_ref=None)
    if not result["valid"]:
        raise ValueError(f"{company_id}: reconciled candidate failed validation: {result['issues']}")
    diagnostics["status"] = "valid"
    diagnostics["derived_metrics"] = result["derived_metrics"]
    return payload, diagnostics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--companies", nargs="*", choices=sorted(GENERAL_CONTRACTORS), default=sorted(GENERAL_CONTRACTORS))
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    client = OpenDartClient()
    summary: dict[str, Any] = {"schema": "general_contractor_working_capital_reconciliation_v1", "companies": {}}
    for company_id in args.companies:
        candidate, diagnostics = reconcile_company(client, company_id, args.input_root)
        company_dir = args.output_dir / company_id
        save_json(company_dir / "candidate_audit_financials.json", candidate)
        save_json(company_dir / "diagnostics.json", diagnostics)
        summary["companies"][company_id] = {
            "status": diagnostics["status"],
            "applied_by_year": {
                year: sorted(detail.get("applied", {})) for year, detail in diagnostics["years"].items()
            },
        }
    save_json(args.output_dir / "summary.json", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
