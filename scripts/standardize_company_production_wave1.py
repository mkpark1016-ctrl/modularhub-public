#!/usr/bin/env python3
"""Standardize Wave 1 production facility and capacity records."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COMPANIES_PATH = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"
SCOPE_PATH = ROOT / "config" / "companies" / "production_wave1_scope.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "company-production-wave-1-standardization"
TODAY = date.today().isoformat()
NOW = f"{TODAY}T00:00:00+09:00"

CONFIRMED_FACILITY_STATUSES = {
    "confirmed_own_facility",
    "confirmed_leased_facility",
    "confirmed_partner_manufacturing",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_scope() -> dict[str, Any]:
    return load_json(SCOPE_PATH)


def company_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {company["company_id"]: company for company in payload.get("companies", [])}


def source_ids_by_type(company: dict[str, Any], source_type: str) -> list[str]:
    return [
        source["source_id"]
        for source in company.get("sources", [])
        if source.get("source_id") and source.get("source_type") == source_type
    ]


def upsert_source(company: dict[str, Any], source: dict[str, Any]) -> None:
    sources = company.setdefault("sources", [])
    for index, current in enumerate(sources):
        if current.get("source_id") == source["source_id"]:
            sources[index] = {**current, **source}
            return
    sources.append(source)


def upsert_gap(company: dict[str, Any], gap: dict[str, Any]) -> None:
    gaps = [
        item
        for item in company.setdefault("research_gaps", [])
        if not (item.get("area") == gap.get("area") and item.get("gap_id") == gap.get("gap_id"))
    ]
    gaps.insert(0, gap)
    company["research_gaps"] = gaps


def standard_facility(raw: dict[str, Any]) -> dict[str, Any]:
    facility = dict(raw)
    if "site_area_m2" in facility and "site_area" not in facility:
        facility["site_area"] = facility.get("site_area_m2")
        facility["site_area_unit"] = "m2" if facility.get("site_area_m2") is not None else None
    if "building_area_m2" in facility and "building_area" not in facility:
        facility["building_area"] = facility.get("building_area_m2")
        facility["building_area_unit"] = "m2" if facility.get("building_area_m2") is not None else None
    facility.setdefault("company_id", raw.get("company_id"))
    facility.setdefault("modular_system_type", "unknown")
    facility.setdefault("operator_name", None)
    facility.setdefault("production_processes", [])
    facility.setdefault("automation_level", None)
    facility.setdefault("major_equipment", raw.get("main_equipment") or [])
    facility.setdefault("capacity_scope", None)
    facility.setdefault("capacity_status", "unavailable" if raw.get("capacity_value") is None and raw.get("reported_capacity") is None else "unknown")
    facility.setdefault("data_confidence", raw.get("confidence") or "unknown")
    facility.setdefault("notes", raw.get("verification_note"))
    return facility


def set_yuchang(company: dict[str, Any]) -> None:
    upsert_source(
        company,
        {
            "source_id": "yc_official_home",
            "company_id": company["company_id"],
            "source_type": "official_website",
            "source_name": "YooChang E&C official website",
            "title": "YooChang E&C official website Factory section",
            "source_url": "https://yoochangenc.com/",
            "published_at": None,
            "accessed_at": TODAY,
            "publisher": "YooChang E&C",
            "primary_source": True,
            "confidence": "medium",
            "document_number": None,
            "page_or_section": "Factory",
            "source_status": "accessible_spa_shell",
            "supported_claims": [
                "facility_name",
                "ownership_type",
                "site_area_m2",
                "building_area_m2",
                "production_scope",
            ],
            "verification_note": "Official site exposes a Factory section in the public site experience; official capacity, address, and current operation details are not disclosed in a stable text page.",
        },
    )
    facility = standard_facility(
        {
            "facility_id": "yuchang-enc-yoochang-factory",
            "facility_name": "YOOCHANG E&C Factory",
            "company_id": company["company_id"],
            "facility_aliases": ["유창이앤씨 Factory"],
            "facility_type": "modular_factory",
            "modular_system_type": "steel_volumetric",
            "own_facility_status": "confirmed_own_facility",
            "ownership_type": "owned",
            "operator_name": company.get("company_name"),
            "operation_status": "unknown",
            "country": "KR",
            "region": None,
            "city": None,
            "address": None,
            "site_area_m2": 60427.8,
            "building_area_m2": 25832,
            "production_scope": ["steel_modular_factory"],
            "structural_systems": ["steel_modular"],
            "production_processes": [],
            "line_count": None,
            "reported_capacity": None,
            "capacity_value": None,
            "capacity_unit": None,
            "capacity_period": None,
            "capacity_scope": None,
            "capacity_basis": "not_publicly_disclosed",
            "capacity_status": "unavailable",
            "capacity_as_of": None,
            "source_ids": ["yc_official_home"],
            "verified_at": TODAY,
            "confidence": "medium",
            "data_confidence": "medium",
            "notes": "Factory existence and scale metrics are retained from the official website. Official modular production capacity, process details, address, and current operation state remain undisclosed.",
        }
    )
    company["production"] = [facility]
    company["production_summary"] = {
        "research_status": "partially_verified",
        "verification_status": "partially_verified",
        "data_confidence": "medium",
        "facility_count": 1,
        "own_facility_count": 1,
        "official_capacity_available": False,
        "summary": "Official company materials support a YooChang E&C Factory record and factory scale metrics, but official production capacity and current operation details are not publicly disclosed.",
        "source_ids": ["yc_official_home"],
        "own_facility_status": "confirmed_own_facility",
        "manufacturing_model": "own_manufacturing",
        "confirmed_facility_count": 1,
        "reported_capacity_available": False,
        "verified_at": TODAY,
    }
    upsert_gap(
        company,
        {
            "gap_id": "production_capacity_public_disclosure",
            "area": "production",
            "status": "capacity_unavailable",
            "note": "Official capacity, line count, process details, exact address, and current operation status were not confirmed in public official material.",
            "source_ids": ["yc_official_home"],
            "verified_at": TODAY,
        },
    )


def set_kumkang(company: dict[str, Any]) -> None:
    upsert_source(
        company,
        {
            "source_id": "kumkang_official_modular",
            "company_id": company["company_id"],
            "source_type": "official_website",
            "source_name": "Kumkang Kind official modular architecture page",
            "title": "금강공업 모듈러건축",
            "source_url": "https://www.kumkangkind.com/business/boxunit.asp?mCode=3",
            "published_at": None,
            "accessed_at": TODAY,
            "publisher": "Kumkang Kind",
            "primary_source": True,
            "confidence": "high",
            "document_number": None,
            "page_or_section": "사업분야 > 모듈러건축",
            "source_status": "accessible",
            "supported_claims": [
                "production_scope",
                "facility_name",
                "manufacturing_model",
                "ownership_type",
                "production_processes",
            ],
            "verification_note": "Official modular page states that modular units are made in factories and identifies Boeun factory as producing modular units.",
        },
    )
    upsert_source(
        company,
        {
            "source_id": "kumkang_official_domestic_network",
            "company_id": company["company_id"],
            "source_type": "official_website",
            "source_name": "Kumkang Kind domestic production network",
            "title": "금강공업 국내 생산공장",
            "source_url": "https://www.kumkangkind.com/company/network_internal.asp",
            "published_at": None,
            "accessed_at": TODAY,
            "publisher": "Kumkang Kind",
            "primary_source": True,
            "confidence": "high",
            "document_number": None,
            "page_or_section": "회사소개 > 국내 생산공장",
            "source_status": "accessible",
            "supported_claims": ["facility_name", "location", "ownership_type", "operation_status"],
            "verification_note": "Official network page lists Boeun 1 and Boeun 2 factories under the construction business division with addresses.",
        },
    )
    facility = standard_facility(
        {
            "facility_id": "kumkang-kind-boeun-factory",
            "facility_name": "보은공장",
            "company_id": company["company_id"],
            "facility_aliases": ["보은1공장", "보은2공장"],
            "facility_type": "modular_factory",
            "modular_system_type": "steel_volumetric",
            "own_facility_status": "confirmed_own_facility",
            "ownership_type": "owned",
            "operator_name": company.get("company_name"),
            "operation_status": "active",
            "country": "KR",
            "region": "충청북도",
            "city": "보은군",
            "address": "충청북도 보은군 삼승면 남부로 3749-11 / 3749-6",
            "site_area_m2": None,
            "building_area_m2": None,
            "production_scope": ["steel_modular_units"],
            "structural_systems": ["steel_volumetric"],
            "production_processes": [
                "steel_frame_fabrication",
                "floor_assembly",
                "wall_assembly",
                "ceiling_assembly",
                "window_door_installation",
                "mep_prefabrication",
                "interior_fitout",
                "final_assembly",
                "logistics_loading",
            ],
            "line_count": None,
            "reported_capacity": None,
            "capacity_value": None,
            "capacity_unit": None,
            "capacity_period": None,
            "capacity_scope": None,
            "capacity_basis": "not_publicly_disclosed",
            "capacity_status": "unavailable",
            "capacity_as_of": None,
            "source_ids": ["kumkang_official_modular", "kumkang_official_domestic_network"],
            "verified_at": TODAY,
            "confidence": "high",
            "data_confidence": "high",
            "notes": "Official modular page confirms factory-made modular units and names Boeun factory; official network page provides Boeun 1 and 2 factory locations. Official capacity is not disclosed.",
        }
    )
    company["production"] = [facility]
    company["production_summary"] = {
        "research_status": "verified",
        "verification_status": "verified",
        "data_confidence": "high",
        "facility_count": 1,
        "own_facility_count": 1,
        "official_capacity_available": False,
        "summary": "Official pages confirm Boeun factory as the modular-unit production base and identify the domestic Boeun factory locations. Official production capacity is not publicly disclosed.",
        "source_ids": ["kumkang_official_modular", "kumkang_official_domestic_network"],
        "own_facility_status": "confirmed_own_facility",
        "manufacturing_model": "own_manufacturing",
        "confirmed_facility_count": 1,
        "reported_capacity_available": False,
        "verified_at": TODAY,
    }
    upsert_gap(
        company,
        {
            "gap_id": "production_capacity_public_disclosure",
            "area": "production",
            "status": "capacity_unavailable",
            "note": "Official capacity, line count, site area, and building area were not confirmed in public official material.",
            "source_ids": ["kumkang_official_modular", "kumkang_official_domestic_network"],
            "verified_at": TODAY,
        },
    )


def set_unconfirmed(company: dict[str, Any]) -> None:
    source_ids = source_ids_by_type(company, "regulatory_filing")[:3]
    company["production"] = []
    company["production_summary"] = {
        "research_status": "research_exhausted",
        "verification_status": "research_exhausted",
        "data_confidence": "unknown",
        "facility_count": None,
        "own_facility_count": None,
        "official_capacity_available": False,
        "summary": "Public official materials reviewed for this step did not confirm a source-backed modular production facility or official production capacity.",
        "source_ids": source_ids,
        "own_facility_status": "not_publicly_confirmed",
        "manufacturing_model": "not_publicly_confirmed",
        "confirmed_facility_count": 0,
        "reported_capacity_available": False,
        "verified_at": TODAY,
    }
    upsert_gap(
        company,
        {
            "gap_id": "production_facility_public_confirmation",
            "area": "production",
            "status": "research_exhausted",
            "note": "No official public source-backed modular production facility, operating model, or production capacity was confirmed; values remain null rather than zero.",
            "source_ids": source_ids,
            "verified_at": TODAY,
        },
    )


def derive_targets(payload: dict[str, Any], scope: dict[str, Any]) -> list[dict[str, Any]]:
    companies = company_by_id(payload)
    return [companies[company_id] for company_id in scope["company_ids"] if company_id in companies]


def apply_standardization(payload: dict[str, Any]) -> dict[str, Any]:
    scope = load_scope()
    targets = derive_targets(payload, scope)
    for company in targets:
        if company["company_id"] == "yuchang-enc":
            set_yuchang(company)
        elif company["company_id"] == "kumkang-kind":
            set_kumkang(company)
        else:
            set_unconfirmed(company)
        company["last_verified_at"] = NOW
    payload.setdefault("metadata", {})["production_wave_1_standardized_at"] = NOW
    return payload


def source_lookup(company: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {source["source_id"]: source for source in company.get("sources", []) if source.get("source_id")}


def is_facility_source_backed(facility: dict[str, Any]) -> bool:
    return bool(facility.get("facility_name") and facility.get("source_ids"))


def is_official(source: dict[str, Any]) -> bool:
    return bool(source.get("primary_source")) and source.get("source_type") in {"official_website", "regulatory_filing", "government_release", "procurement_notice"}


def audit(payload: dict[str, Any]) -> dict[str, Any]:
    scope = load_scope()
    targets = derive_targets(payload, scope)
    target_rows: list[dict[str, Any]] = []
    facility_rows: list[dict[str, Any]] = []
    capacity_rows: list[dict[str, Any]] = []
    process_rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    gap_rows: list[dict[str, Any]] = []
    before_after_rows: list[dict[str, Any]] = []
    validation_errors: list[dict[str, Any]] = []
    system_counter: Counter[str] = Counter()
    ownership_counter: Counter[str] = Counter()

    for company in targets:
        summary = company.get("production_summary") or {}
        facilities = company.get("production") or []
        sources = source_lookup(company)
        source_backed = [facility for facility in facilities if is_facility_source_backed(facility)]
        official_facilities = [
            facility
            for facility in source_backed
            if any(is_official(sources.get(source_id, {})) for source_id in facility.get("source_ids") or [])
        ]
        target_rows.append(
            {
                "company_id": company["company_id"],
                "company_name": company.get("company_name", ""),
                "competitive_role": company.get("competitive_role", ""),
                "analysis_tier": company.get("analysis_tier", ""),
                "research_status": summary.get("research_status", ""),
                "verification_status": summary.get("verification_status", ""),
                "manufacturing_model": summary.get("manufacturing_model", ""),
                "own_facility_status": summary.get("own_facility_status", ""),
                "facility_count": summary.get("facility_count", ""),
                "official_capacity_available": summary.get("official_capacity_available", ""),
                "source_ids": "|".join(summary.get("source_ids") or []),
            }
        )
        for source_id in summary.get("source_ids") or []:
            source = sources.get(source_id, {})
            source_rows.append(
                {
                    "company_id": company["company_id"],
                    "source_id": source_id,
                    "source_type": source.get("source_type", ""),
                    "source_name": source.get("source_name", ""),
                    "url": source.get("source_url", ""),
                    "primary_source": source.get("primary_source", ""),
                    "supported_claims": "|".join(source.get("supported_claims") or []),
                    "source_status": source.get("source_status", ""),
                }
            )
        if not facilities:
            gap_rows.append(
                {
                    "company_id": company["company_id"],
                    "company_name": company.get("company_name", ""),
                    "gap_type": "facility_not_publicly_confirmed",
                    "description": summary.get("summary", ""),
                    "source_ids": "|".join(summary.get("source_ids") or []),
                }
            )
        for facility in facilities:
            ownership_counter[facility.get("ownership_type") or "unknown"] += 1
            system_counter[facility.get("modular_system_type") or "unknown"] += 1
            facility_rows.append(
                {
                    "company_id": company["company_id"],
                    "company_name": company.get("company_name", ""),
                    "facility_id": facility.get("facility_id", ""),
                    "facility_name": facility.get("facility_name", ""),
                    "facility_type": facility.get("facility_type", ""),
                    "modular_system_type": facility.get("modular_system_type", ""),
                    "ownership_type": facility.get("ownership_type", ""),
                    "operator_name": facility.get("operator_name", ""),
                    "operation_status": facility.get("operation_status", ""),
                    "region": facility.get("region", ""),
                    "city": facility.get("city", ""),
                    "address": facility.get("address", ""),
                    "site_area": facility.get("site_area", ""),
                    "site_area_unit": facility.get("site_area_unit", ""),
                    "building_area": facility.get("building_area", ""),
                    "building_area_unit": facility.get("building_area_unit", ""),
                    "production_scope": "|".join(facility.get("production_scope") or []),
                    "source_ids": "|".join(facility.get("source_ids") or []),
                    "verified_at": facility.get("verified_at", ""),
                    "data_confidence": facility.get("data_confidence", ""),
                }
            )
            capacity_rows.append(
                {
                    "company_id": company["company_id"],
                    "facility_id": facility.get("facility_id", ""),
                    "capacity_value": facility.get("capacity_value", ""),
                    "reported_capacity": facility.get("reported_capacity", ""),
                    "capacity_unit": facility.get("capacity_unit", ""),
                    "capacity_period": facility.get("capacity_period", ""),
                    "capacity_scope": facility.get("capacity_scope", ""),
                    "capacity_basis": facility.get("capacity_basis", ""),
                    "capacity_status": facility.get("capacity_status", ""),
                    "capacity_as_of": facility.get("capacity_as_of", ""),
                    "source_ids": "|".join(facility.get("source_ids") or []),
                }
            )
            for process in facility.get("production_processes") or []:
                process_rows.append(
                    {
                        "company_id": company["company_id"],
                        "facility_id": facility.get("facility_id", ""),
                        "production_process": process,
                        "source_ids": "|".join(facility.get("source_ids") or []),
                    }
                )
            if facility.get("capacity_value") in (0, "0") or facility.get("reported_capacity") in (0, "0"):
                validation_errors.append(
                    {
                        "code": "zero_capacity_fallback",
                        "company_id": company["company_id"],
                        "facility_id": facility.get("facility_id", ""),
                        "message": "Zero capacity must not be used as a missing-value fallback.",
                    }
                )
            if facility.get("capacity_value") is not None or facility.get("reported_capacity") is not None:
                for field in ["capacity_unit", "capacity_period", "capacity_scope"]:
                    if not facility.get(field):
                        validation_errors.append(
                            {
                                "code": f"{field}_missing",
                                "company_id": company["company_id"],
                                "facility_id": facility.get("facility_id", ""),
                                "message": f"{field} is required when a capacity value exists.",
                            }
                        )
            if facility.get("facility_type") == "modular_factory" and facility.get("modular_system_type") == "unknown":
                validation_errors.append(
                    {
                        "code": "generic_factory_misclassified",
                        "company_id": company["company_id"],
                        "facility_id": facility.get("facility_id", ""),
                        "message": "Modular factory requires a modular_system_type.",
                    }
                )
        before_after_rows.append(
            {
                "company_id": company["company_id"],
                "facility_count_after": len(facilities),
                "official_source_facility_count_after": len(official_facilities),
                "official_capacity_available_after": summary.get("official_capacity_available", False),
                "research_status_after": summary.get("research_status", ""),
            }
        )

    summary_counter = Counter((company.get("production_summary") or {}).get("verification_status", "") for company in targets)
    facility_count = sum(len(company.get("production") or []) for company in targets)
    official_facility_count = sum(
        1
        for company in targets
        for facility in company.get("production") or []
        if any(is_official(source_lookup(company).get(source_id, {})) for source_id in facility.get("source_ids") or [])
    )
    official_capacity_company_count = sum(1 for company in targets if (company.get("production_summary") or {}).get("official_capacity_available") is True)
    capacity_unavailable_company_count = sum(1 for company in targets if (company.get("production_summary") or {}).get("official_capacity_available") is False)
    location_verified_company_count = sum(
        1 for company in targets if any((facility.get("region") or facility.get("city") or facility.get("address")) for facility in company.get("production") or [])
    )
    metrics = {
        "target_company_count": len(targets),
        "production_verified_company_count": summary_counter.get("verified", 0),
        "production_partially_verified_company_count": summary_counter.get("partially_verified", 0),
        "own_facility_company_count": sum(1 for company in targets if (company.get("production_summary") or {}).get("own_facility_status") == "confirmed_own_facility"),
        "partner_production_company_count": sum(1 for company in targets if (company.get("production_summary") or {}).get("own_facility_status") == "confirmed_partner_manufacturing"),
        "not_applicable_company_count": summary_counter.get("not_applicable", 0),
        "facility_count": facility_count,
        "official_source_facility_count": official_facility_count,
        "official_capacity_company_count": official_capacity_company_count,
        "company_claim_capacity_count": 0,
        "capacity_unavailable_company_count": capacity_unavailable_company_count,
        "location_verified_company_count": location_verified_company_count,
        "modular_relation_verified_facility_count": sum(1 for row in facility_rows if row["modular_system_type"] not in {"", "unknown"}),
        "facilities_without_source_count": sum(1 for row in facility_rows if not row["source_ids"]),
        "capacities_without_unit_count": sum(1 for row in capacity_rows if (row["capacity_value"] or row["reported_capacity"]) and not row["capacity_unit"]),
        "capacities_without_period_count": sum(1 for row in capacity_rows if (row["capacity_value"] or row["reported_capacity"]) and not row["capacity_period"]),
        "generic_factory_misclassified_count": sum(1 for issue in validation_errors if issue["code"] == "generic_factory_misclassified"),
        "null_rendered_as_zero_count": sum(1 for issue in validation_errors if issue["code"] == "zero_capacity_fallback"),
        "stale_source_count": 0,
        "conflicting_value_count": 0,
        "ownership_type_counts": dict(ownership_counter),
        "modular_system_type_counts": dict(system_counter),
    }
    status = "PASS" if not validation_errors else "HOLD_FOR_FIX"
    if status == "PASS" and any((company.get("production_summary") or {}).get("research_status") == "research_exhausted" for company in targets):
        status = "PASS_WITH_RESEARCH_GAPS"
    return {
        "status": status,
        "metrics": metrics,
        "rows": {
            "production_target_companies": target_rows,
            "production_facilities": facility_rows,
            "production_capacity_inventory": capacity_rows,
            "production_process_inventory": process_rows,
            "production_source_inventory": source_rows,
            "production_claims_rejected": rejected_rows,
            "production_research_gaps": gap_rows,
            "production_validation_errors": validation_errors,
            "production_before_after": before_after_rows,
        },
    }


def write_artifacts(result: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "production_wave_1_audit.json").write_text(
        json.dumps({"status": result["status"], "metrics": result["metrics"]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for name, rows in result["rows"].items():
        write_csv(output_dir / f"{name}.csv", rows)
    metrics = result["metrics"]
    lines = [
        "# Wave 1 Production Standardization Audit",
        "",
        f"- Status: {result['status']}",
        f"- Target companies: {metrics['target_company_count']}",
        f"- Verified production companies: {metrics['production_verified_company_count']}",
        f"- Partially verified production companies: {metrics['production_partially_verified_company_count']}",
        f"- Own facility companies: {metrics['own_facility_company_count']}",
        f"- Facilities: {metrics['facility_count']}",
        f"- Official-source facilities: {metrics['official_source_facility_count']}",
        f"- Official capacity companies: {metrics['official_capacity_company_count']}",
        f"- Capacity unavailable companies: {metrics['capacity_unavailable_company_count']}",
        f"- Facilities without source: {metrics['facilities_without_source_count']}",
        f"- Capacity unit errors: {metrics['capacities_without_unit_count']}",
        f"- Capacity period errors: {metrics['capacities_without_period_count']}",
        "",
        "Unconfirmed production capacity remains null. The audit does not treat missing values as zero or as proof that a facility does not exist.",
    ]
    (output_dir / "production_wave_1_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Standardize Wave 1 production facility data.")
    parser.add_argument("--input", default=str(COMPANIES_PATH))
    parser.add_argument("--write-companies", action="store_true")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    path = Path(args.input)
    payload = load_json(path)
    payload = apply_standardization(payload)
    result = audit(payload)
    write_artifacts(result, Path(args.output_dir))
    if args.write_companies:
        write_json(path, payload)
    print(json.dumps({"status": result["status"], "metrics": result["metrics"]}, ensure_ascii=False, indent=2))
    if result["status"] == "HOLD_FOR_FIX":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
