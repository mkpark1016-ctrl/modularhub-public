#!/usr/bin/env python3
"""Resolve DART identity candidates for Wave 1 companies."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.opendart_client import OpenDartClient  # noqa: E402

COMPANIES_PATH = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"
MANUAL_FILINGS_PATH = ROOT / "config" / "companies" / "dart_manual_filings.json"
OUTPUT_DIR = ROOT / "artifacts" / "company-research-wave-1-dart"
WAVE1_IDS = ["yuchang-enc", "kumkang-kind", "planm", "daeseung-engineering"]
SEARCHED_YEARS = [2025, 2024, 2023, 2022, 2021]
SEARCHED_REPORT_TYPES = [
    "audit_report",
    "consolidated_audit_report",
    "business_report",
    "corrected_audit_report",
    "corrected_business_report",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def wave1_companies(path: Path = COMPANIES_PATH) -> list[dict[str, Any]]:
    payload = load_json(path)
    by_id = {company["company_id"]: company for company in payload.get("companies", [])}
    return [by_id[company_id] for company_id in WAVE1_IDS if company_id in by_id]


def normalize(value: str | None) -> str:
    return "".join((value or "").lower().split())


def manual_filings(path: Path = MANUAL_FILINGS_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = load_json(path)
    return payload.get("filings", []) if isinstance(payload.get("filings"), list) else []


def resolve_identities(client: OpenDartClient, companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    searched_at = datetime.now(timezone.utc).isoformat()
    if not client.has_api_key:
        return [
            {
                "company_id": company["company_id"],
                "legal_name": company["company_name"],
                "normalized_legal_name": normalize(company["company_name"]),
                "aliases": company.get("aliases", []),
                "dart_corp_code": "",
                "stock_code": "",
                "corp_class": "",
                "business_number": "",
                "corporate_registration_number": "",
                "headquarters": company.get("headquarters"),
                "website_url": company.get("website_url"),
                "identity_status": "api_key_required",
                "identity_confidence": "unknown",
                "identity_source_ids": [],
                "verified_at": "",
                "searched_at": searched_at,
                "not_found_reason": "OPENDART_API_KEY is not set; no live DART lookup was performed.",
            }
            for company in companies
        ]

    corp_rows = client.list_corp_codes()

    output = []
    for company in companies:
        names = [company.get("company_name", ""), *(company.get("aliases", []) or [])]
        normalized_names = {normalize(name) for name in names if normalize(name)}
        matches = [row for row in corp_rows if normalize(row.get("corp_name")) in normalized_names]
        if len(matches) == 1:
            match = matches[0]
            status = "probable"
            confidence = "medium"
        elif len(matches) > 1:
            match = {}
            status = "ambiguous"
            confidence = "review"
        else:
            match = {}
            status = "not_found"
            confidence = "unknown"
        output.append(
            {
                "company_id": company["company_id"],
                "legal_name": match.get("corp_name") or company.get("company_name"),
                "normalized_legal_name": normalize(match.get("corp_name") or company.get("company_name")),
                "aliases": company.get("aliases", []),
                "dart_corp_code": match.get("corp_code", ""),
                "stock_code": match.get("stock_code", ""),
                "corp_class": "listed" if match.get("stock_code") else "",
                "business_number": "",
                "corporate_registration_number": "",
                "headquarters": company.get("headquarters"),
                "website_url": company.get("website_url"),
                "identity_status": status,
                "identity_confidence": confidence,
                "identity_source_ids": ["opendart_corp_code"] if match else [],
                "verified_at": searched_at if match else "",
                "searched_at": searched_at,
                "not_found_reason": "" if match else "No exact legal-name match in OpenDART corpCode list.",
                "candidate_count": len(matches),
            }
        )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve Wave 1 OpenDART company identities.")
    parser.add_argument("--companies", type=Path, default=COMPANIES_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--write-companies", action="store_true", help="Write DART identity and filing availability fields back to companies.json.")
    args = parser.parse_args()
    payload = load_json(args.companies)
    by_id = {company["company_id"]: company for company in payload.get("companies", [])}
    rows = resolve_identities(OpenDartClient(), [by_id[company_id] for company_id in WAVE1_IDS if company_id in by_id])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "dart_company_identity.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.write_companies:
        updated = apply_identities_to_companies(payload, rows)
        args.companies.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"identity_count": len(rows), "statuses": count_statuses(rows)}, ensure_ascii=False, indent=2))
    return 0


def count_statuses(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = row.get("identity_status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def dart_financial_gap(identity: dict[str, Any]) -> dict[str, Any]:
    status = identity.get("identity_status") or "unknown"
    if status == "api_key_required":
        description = "OPENDART_API_KEY is required before DART identity, filing, and audit financial lookup can be completed."
    elif status == "ambiguous":
        description = "DART identity is ambiguous; manual legal-entity verification is required before filing extraction."
    elif status == "not_found":
        description = "No exact OpenDART legal-name match was found in the searched corpus."
    else:
        description = "DART filing extraction has not yet produced audited financial records."
    return {
        "area": "dart_financials",
        "status": status,
        "description": description,
        "source_ids": identity.get("identity_source_ids", []),
        "verified_at": identity.get("verified_at") or "",
    }


def apply_identities_to_companies(payload: dict[str, Any], identities: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {identity["company_id"]: identity for identity in identities}
    for company in payload.get("companies", []):
        identity = by_id.get(company.get("company_id"))
        if not identity:
            continue
        company["dart_identity"] = identity
        company["filing_availability"] = {
            "status": identity.get("identity_status"),
            "searched_period": SEARCHED_YEARS,
            "searched_report_types": SEARCHED_REPORT_TYPES,
            "reports_found_count": 0,
            "selected_reports": [],
            "not_found_reason": identity.get("not_found_reason", ""),
            "searched_at": identity.get("searched_at", ""),
        }
        company.setdefault("dart_filings", [])
        company.setdefault("audit_information", [])
        company.setdefault("financials", [])
        company["financial_summary"] = {
            "financial_area_status": identity.get("identity_status"),
            "years_available": [],
            "modular_segment_available": False,
            "modular_segment_name": None,
            "modular_segment_revenue": None,
            "modular_segment_operating_profit": None,
            "modular_segment_basis": "No audited DART report was fetched or parsed for modular segment disclosure.",
            "source_ids": identity.get("identity_source_ids", []),
            "verified_at": identity.get("verified_at", ""),
        }
        gaps = [gap for gap in company.get("research_gaps", []) if gap.get("area") != "dart_financials"]
        gaps.append(dart_financial_gap(identity))
        company["research_gaps"] = gaps
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
