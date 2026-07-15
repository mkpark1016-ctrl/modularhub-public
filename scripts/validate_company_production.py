#!/usr/bin/env python3
"""Validate source-backed production facility records."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"
WAVE1_IDS = ["yuchang-enc", "kumkang-kind", "planm", "daeseung-engineering"]
CONFIRMED_STATUSES = {"confirmed_own_facility", "confirmed_leased_facility", "confirmed_partner_manufacturing"}
EXCLUDED_STATUSES = {"not_publicly_confirmed", "research_in_progress", "historical_facility", "planned_facility", "ceased_operation"}
NUMERIC_FIELDS = {"site_area_m2", "building_area_m2", "site_area", "building_area", "line_count", "reported_capacity", "capacity_value"}
CAPACITY_FIELDS = {"reported_capacity", "capacity_value"}
SUPPORTED_CLAIM_FIELDS = {"facility_name", "location", "ownership_type", "operation_status", "site_area_m2", "building_area_m2", "site_area", "building_area", "production_scope", "production_processes", "reported_capacity", "capacity_value"}
FACILITY_TYPES = {"modular_factory", "steel_fabrication_factory", "pc_factory", "timber_modular_factory", "interior_assembly_factory", "general_material_factory", "research_facility", "unknown"}
MODULAR_SYSTEM_TYPES = {"steel_volumetric", "steel_panelized", "pc_modular", "timber_modular", "hybrid", "multiple", "unknown"}
OWNERSHIP_TYPES = {"owned", "subsidiary_owned", "affiliate_owned", "leased", "partner_owned", "contract_manufacturing", "planned", "unknown"}
OPERATION_STATUSES = {"active", "partially_active", "under_expansion", "under_construction", "planned", "suspended", "closed", "unknown", "current_operation_unconfirmed", "active_on_official_site"}
CAPACITY_STATUSES = {"official_confirmed", "company_claimed", "third_party_reported", "derived", "unavailable", "not_applicable", "unknown"}


def load_payload(path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def wave1_companies(payload: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {company["company_id"]: company for company in payload.get("companies", [])}
    return [by_id[company_id] for company_id in WAVE1_IDS if company_id in by_id]


def source_map(company: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {source["source_id"]: source for source in company.get("sources", []) if source.get("source_id")}


def add_issue(issues: list[dict[str, Any]], code: str, company_id: str, path: str, message: str, severity: str = "error") -> None:
    issues.append({"code": code, "company_id": company_id, "path": path, "message": message, "severity": severity})


def has_sources(record: dict[str, Any]) -> bool:
    return isinstance(record.get("source_ids"), list) and bool(record["source_ids"])


def validate_source_refs(company: dict[str, Any], record: dict[str, Any], path: str, issues: list[dict[str, Any]]) -> None:
    sources = source_map(company)
    if not has_sources(record):
        add_issue(issues, "source_id_missing", company["company_id"], path, "source_ids required")
        return
    for source_id in record["source_ids"]:
        if source_id not in sources:
            add_issue(issues, "unknown_source_reference", company["company_id"], path, f"unknown source_id={source_id}")


def source_claims(company: dict[str, Any], source_ids: list[str]) -> set[str]:
    sources = source_map(company)
    claims: set[str] = set()
    for source_id in source_ids:
        source = sources.get(source_id, {})
        claims.update(source.get("supported_claims") or [])
    return claims


def is_confirmed_facility(facility: dict[str, Any]) -> bool:
    status = facility.get("own_facility_status") or facility.get("verification_status") or facility.get("operation_status")
    if status in EXCLUDED_STATUSES:
        return False
    if status in CONFIRMED_STATUSES:
        return True
    return bool(facility.get("facility_name") and has_sources(facility))


def validate_facility(company: dict[str, Any], facility: dict[str, Any], index: int, issues: list[dict[str, Any]]) -> None:
    path = f"production[{index}]"
    validate_source_refs(company, facility, path, issues)
    if not facility.get("facility_id"):
        add_issue(issues, "missing_facility_id", company["company_id"], path, "facility_id required")
    if is_confirmed_facility(facility) and not facility.get("facility_name"):
        add_issue(issues, "missing_facility_name", company["company_id"], path, "confirmed facility requires facility_name")
    for field in NUMERIC_FIELDS:
        if facility.get(field) is not None and not has_sources(facility):
            add_issue(issues, "number_without_source", company["company_id"], f"{path}.{field}", "numeric production value requires source_ids")
    if any(facility.get(field) is not None for field in CAPACITY_FIELDS):
        if not facility.get("capacity_unit"):
            add_issue(issues, "capacity_unit_missing", company["company_id"], path, "reported capacity requires capacity_unit")
        if not facility.get("capacity_period"):
            add_issue(issues, "capacity_period_missing", company["company_id"], path, "reported capacity requires capacity_period")
        if not facility.get("capacity_scope"):
            add_issue(issues, "capacity_scope_missing", company["company_id"], path, "reported capacity requires capacity_scope")
    if facility.get("capacity_unit") and facility.get("capacity_period") not in {None, "year", "month", "day", "project", "not_publicly_disclosed"}:
        add_issue(issues, "invalid_capacity_period", company["company_id"], path, str(facility.get("capacity_period")))
    if facility.get("site_area_m2") is not None and facility.get("building_area_m2") is not None:
        if float(facility["building_area_m2"]) > float(facility["site_area_m2"]):
            add_issue(issues, "area_inconsistency", company["company_id"], path, "building_area_m2 exceeds site_area_m2")
    if facility.get("site_area") is not None and not facility.get("site_area_unit"):
        add_issue(issues, "site_area_unit_missing", company["company_id"], path, "site_area requires site_area_unit")
    if facility.get("building_area") is not None and not facility.get("building_area_unit"):
        add_issue(issues, "building_area_unit_missing", company["company_id"], path, "building_area requires building_area_unit")
    if facility.get("site_area") is not None and facility.get("building_area") is not None:
        if float(facility["building_area"]) > float(facility["site_area"]):
            add_issue(issues, "area_inconsistency", company["company_id"], path, "building_area exceeds site_area")
    if facility.get("facility_type") and facility["facility_type"] not in FACILITY_TYPES:
        add_issue(issues, "invalid_facility_type", company["company_id"], path, facility["facility_type"])
    if facility.get("modular_system_type") and facility["modular_system_type"] not in MODULAR_SYSTEM_TYPES:
        add_issue(issues, "invalid_modular_system_type", company["company_id"], path, facility["modular_system_type"])
    if facility.get("ownership_type") and facility["ownership_type"] not in OWNERSHIP_TYPES:
        add_issue(issues, "invalid_ownership_type", company["company_id"], path, facility["ownership_type"])
    if facility.get("operation_status") and facility["operation_status"] not in OPERATION_STATUSES:
        add_issue(issues, "invalid_operation_status", company["company_id"], path, facility["operation_status"])
    if facility.get("capacity_status") and facility["capacity_status"] not in CAPACITY_STATUSES:
        add_issue(issues, "invalid_capacity_status", company["company_id"], path, facility["capacity_status"])
    claims = source_claims(company, facility.get("source_ids") or [])
    for field in SUPPORTED_CLAIM_FIELDS:
        value = facility.get(field)
        if value not in (None, "", [], {}):
            equivalent = "location" if field in {"region", "city", "address"} else field
            if equivalent == "site_area" and "site_area_m2" in claims:
                continue
            if equivalent == "building_area" and "building_area_m2" in claims:
                continue
            if equivalent not in claims and field not in {"operation_status"}:
                add_issue(issues, "unsupported_claim", company["company_id"], f"{path}.{field}", f"no source supported_claims entry for {field}", "warning")


def validate_company(company: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    summary = company.get("production_summary") or {}
    validate_source_refs(company, summary, "production_summary", issues)
    facilities = company.get("production") or []
    seen: set[str] = set()
    for index, facility in enumerate(facilities):
        validate_facility(company, facility, index, issues)
        facility_id = facility.get("facility_id")
        if facility_id in seen:
            add_issue(issues, "duplicate_facility_id", company["company_id"], f"production[{index}].facility_id", str(facility_id))
        seen.add(facility_id)
    confirmed_count = sum(1 for facility in facilities if is_confirmed_facility(facility))
    if summary.get("own_facility_status") in EXCLUDED_STATUSES and confirmed_count:
        add_issue(issues, "excluded_status_has_confirmed_facility", company["company_id"], "production_summary", "excluded summary status cannot have confirmed facilities")
    if summary.get("confirmed_facility_count") is not None and int(summary.get("confirmed_facility_count") or 0) != confirmed_count:
        add_issue(issues, "confirmed_count_mismatch", company["company_id"], "production_summary.confirmed_facility_count", f"expected {confirmed_count}")
    if summary.get("reported_capacity_available") is False:
        for index, facility in enumerate(facilities):
            if facility.get("reported_capacity") is not None or facility.get("capacity_value") is not None:
                add_issue(issues, "capacity_flag_mismatch", company["company_id"], f"production[{index}]", "capacity present while summary says unavailable")
    return issues


def validate(payload: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    for company in wave1_companies(payload):
        issues.extend(validate_company(company))
    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue["code"]] = counts.get(issue["code"], 0) + 1
    error_count = sum(1 for issue in issues if issue.get("severity") != "warning")
    return {
        "valid": error_count == 0,
        "wave_1_company_count": len(wave1_companies(payload)),
        "issue_counts": counts,
        "error_count": error_count,
        "warning_count": len(issues) - error_count,
        "issues": issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Wave 1 company production data.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    args = parser.parse_args()
    result = validate(load_payload(Path(args.input)))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
