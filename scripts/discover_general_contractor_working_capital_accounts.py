#!/usr/bin/env python3
"""Discover working-capital and borrowing account candidates for general contractors.

This is a read-only diagnostic utility. It calls OpenDART's consolidated all-account
endpoint and emits sanitized account metadata/amounts for review. It never writes
public company-report JSON and never guesses missing values.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from src.company_dart_audit_adapter import GENERAL_CONTRACTORS, TARGET_YEARS
from src.opendart_client import OpenDartClient

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "general-contractor-working-capital-discovery"

KEYWORDS = (
    "매출채권",
    "기타채권",
    "미수금",
    "공사미수",
    "계약자산",
    "미청구",
    "재고",
    "진행공사",
    "재공",
    "단기차입",
    "유동성장기차입",
    "장기차입",
    "사채",
)


def norm(value: Any) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(value or "").lower())


def matches_working_capital_keyword(row: dict[str, Any]) -> bool:
    name = norm(row.get("account_nm"))
    return any(norm(keyword) in name for keyword in KEYWORDS)


def sanitize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rcept_no": row.get("rcept_no"),
        "sj_div": row.get("sj_div"),
        "account_id": row.get("account_id"),
        "account_nm": row.get("account_nm"),
        "thstrm_amount": row.get("thstrm_amount"),
        "frmtrm_amount": row.get("frmtrm_amount"),
        "bfefrmtrm_amount": row.get("bfefrmtrm_amount"),
        "currency": row.get("currency"),
        "ord": row.get("ord"),
    }


def discover_company(client: OpenDartClient, company_id: str) -> dict[str, Any]:
    spec = GENERAL_CONTRACTORS[company_id]
    years: dict[str, Any] = {}
    for year in TARGET_YEARS:
        payload = client.single_account_all(
            corp_code=spec["corp_code"],
            fiscal_year=year,
            fs_div="CFS",
        )
        rows = [sanitize_row(row) for row in (payload.get("list") or []) if matches_working_capital_keyword(row)]
        rows.sort(key=lambda row: (str(row.get("sj_div") or ""), int(str(row.get("ord") or "0") or 0), str(row.get("account_nm") or "")))
        years[str(year)] = {
            "row_count": len(rows),
            "rows": rows,
        }
    return {
        "company_id": company_id,
        "company_name": spec["company_name"],
        "corp_code": spec["corp_code"],
        "financial_scope": "consolidated",
        "years": years,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--companies", nargs="*", choices=sorted(GENERAL_CONTRACTORS), default=sorted(GENERAL_CONTRACTORS))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    client = OpenDartClient()
    output_dir = args.output_dir
    summary: dict[str, Any] = {"schema": "general_contractor_working_capital_discovery_v1", "companies": {}}
    for company_id in args.companies:
        result = discover_company(client, company_id)
        write_json(output_dir / f"{company_id}.json", result)
        summary["companies"][company_id] = {
            "company_name": result["company_name"],
            "year_row_counts": {year: detail["row_count"] for year, detail in result["years"].items()},
        }
    write_json(output_dir / "summary.json", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
