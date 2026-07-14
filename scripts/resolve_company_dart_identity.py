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
IDENTITY_OVERRIDES_PATH = ROOT / "config" / "companies" / "dart_identity_overrides.json"
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


def normalize_business_number(value: str | None) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def normalize_corporate_number(value: str | None) -> str:
    return normalize_business_number(value)


def normalize_person_names(value: str | list[str] | None) -> set[str]:
    if isinstance(value, list):
        text = ",".join(value)
    else:
        text = value or ""
    normalized = text.replace("ㆍ", ",").replace("·", ",").replace("/", ",").replace("，", ",")
    return {normalize(part) for part in normalized.split(",") if normalize(part)}


def normalize_address(value: str | None) -> str:
    text = normalize(value)
    for token in ["(", ")", "[", "]", "주식회사", "(주)", "㈜", ",", ".", "-"]:
        text = text.replace(normalize(token), "")
    return text


def normalize_phone(value: str | None) -> str:
    return normalize_business_number(value)


def normalize_url_host(value: str | None) -> str:
    text = (value or "").strip().lower()
    text = text.removeprefix("https://").removeprefix("http://").removeprefix("www.")
    return text.split("/")[0]


def corp_class_label(corp_cls: str | None, stock_code: str | None) -> str:
    if stock_code:
        return "listed"
    return {"Y": "kospi", "K": "kosdaq", "N": "konex", "E": "other"}.get(corp_cls or "", "")


def confirmation_result(company: dict[str, Any], overview: dict[str, Any], match: dict[str, str]) -> tuple[str, str, list[str]]:
    evidence = ["exact_legal_name_match", "opendart_corp_code"]
    if overview.get("status") == "000":
        evidence.append("opendart_company_overview")
    website_match = normalize_url_host(company.get("website_url")) and normalize_url_host(company.get("website_url")) == normalize_url_host(overview.get("hm_url"))
    if website_match:
        evidence.append("homepage_match")
    stock_code = overview.get("stock_code") or match.get("stock_code")
    if stock_code:
        evidence.append("stock_code_present")
    if website_match or stock_code:
        return "confirmed", "high", evidence
    if overview.get("status") == "000":
        return "confirmed", "medium", evidence
    return "probable", "medium", evidence


def manual_filings(path: Path = MANUAL_FILINGS_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = load_json(path)
    return payload.get("filings", []) if isinstance(payload.get("filings"), list) else []


def identity_overrides(path: Path = IDENTITY_OVERRIDES_PATH) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = load_json(path)
    return {item["company_id"]: item for item in payload.get("overrides", []) if item.get("company_id")}


def identity_from_overrides(
    company: dict[str, Any],
    matches: list[dict[str, str]],
    client: OpenDartClient,
    searched_at: str,
    override: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not override:
        return None
    candidates = []
    for match in matches:
        overview = client.company_overview(match.get("corp_code", ""))
        business_match = normalize_business_number(overview.get("bizr_no")) == normalize_business_number(override.get("normalized_business_number"))
        representative_names = normalize_person_names(overview.get("ceo_nm"))
        required_names = normalize_person_names(override.get("representative_required_names", []))
        representative_match = bool(required_names and required_names <= representative_names)
        address_match = normalize_address(override.get("normalized_address_hint")) in normalize_address(overview.get("adres"))
        phone_match = normalize_phone(overview.get("phn_no")) == normalize_phone(override.get("normalized_phone"))
        candidates.append(
            {
                "match": match,
                "overview": overview,
                "business_number_match": business_match,
                "representative_match": representative_match,
                "address_match": address_match,
                "phone_match": phone_match,
            }
        )
    exact_matches = [candidate for candidate in candidates if candidate["business_number_match"]]
    if len(exact_matches) != 1:
        return None
    selected = exact_matches[0]
    match = selected["match"]
    overview = selected["overview"]
    rejected = [candidate["match"].get("corp_code") for candidate in candidates if candidate is not selected]
    matched_fields = ["business_number"]
    if selected["representative_match"]:
        matched_fields.append("representative")
    if selected["address_match"]:
        matched_fields.append("address")
    if selected["phone_match"]:
        matched_fields.append("phone")
    return {
        "company_id": company["company_id"],
        "legal_name": overview.get("corp_name") or override.get("legal_name") or company.get("company_name"),
        "normalized_legal_name": normalize(overview.get("corp_name") or override.get("legal_name") or company.get("company_name")),
        "aliases": company.get("aliases", []),
        "dart_corp_code": match.get("corp_code", ""),
        "stock_code": overview.get("stock_code") or match.get("stock_code", ""),
        "corp_class": corp_class_label(overview.get("corp_cls"), overview.get("stock_code") or match.get("stock_code")),
        "representative": overview.get("ceo_nm", ""),
        "business_number": overview.get("bizr_no", ""),
        "corporate_registration_number": overview.get("jurir_no", ""),
        "headquarters": overview.get("adres") or company.get("headquarters"),
        "phone": overview.get("phn_no", ""),
        "website_url": overview.get("hm_url") or company.get("website_url"),
        "established_at": overview.get("est_dt", ""),
        "accounting_month": overview.get("acc_mt", ""),
        "identity_status": "confirmed",
        "identity_confidence": "high",
        "identity_method": override.get("identity_method", "exact_business_number"),
        "matched_fields": matched_fields,
        "identity_source_ids": ["opendart_corp_code", "opendart_company_overview", "manual_identity_override"],
        "verified_at": searched_at,
        "searched_at": searched_at,
        "not_found_reason": "",
        "candidate_count": len(matches),
        "rejected_candidate_count": len(rejected),
        "rejected_candidate_corp_codes": rejected,
        "identity_evidence": ["exact_legal_name_match", "opendart_corp_code", "opendart_company_overview", "exact_business_number"],
        "verification_reason": override.get("verification_reason", ""),
    }


def resolve_identities(client: OpenDartClient, companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    searched_at = datetime.now(timezone.utc).isoformat()
    overrides = identity_overrides()
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
        override_identity = identity_from_overrides(company, matches, client, searched_at, overrides.get(company["company_id"]))
        if override_identity:
            output.append(override_identity)
            continue
        overview: dict[str, Any] = {}
        evidence: list[str] = []
        if len(matches) == 1:
            match = matches[0]
            try:
                overview = client.company_overview(match.get("corp_code", ""))
            except Exception:
                overview = {}
            status, confidence, evidence = confirmation_result(company, overview, match)
        elif len(matches) > 1:
            match = {}
            status = "ambiguous"
            confidence = "review"
            evidence = [f"candidate:{row.get('corp_code')}" for row in matches]
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
                "stock_code": overview.get("stock_code") or match.get("stock_code", ""),
                "corp_class": corp_class_label(overview.get("corp_cls"), overview.get("stock_code") or match.get("stock_code")),
                "representative": overview.get("ceo_nm", ""),
                "business_number": overview.get("bizr_no", ""),
                "corporate_registration_number": overview.get("jurir_no", ""),
                "headquarters": overview.get("adres") or company.get("headquarters"),
                "website_url": overview.get("hm_url") or company.get("website_url"),
                "identity_status": status,
                "identity_confidence": confidence,
                "identity_source_ids": ["opendart_corp_code", "opendart_company_overview"] if match else [],
                "verified_at": searched_at if match else "",
                "searched_at": searched_at,
                "not_found_reason": "Multiple exact legal-name matches in OpenDART corpCode list." if len(matches) > 1 else ("" if match else "No exact legal-name match in OpenDART corpCode list."),
                "candidate_count": len(matches),
                "identity_evidence": evidence,
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
