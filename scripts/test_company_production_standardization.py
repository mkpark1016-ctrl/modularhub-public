#!/usr/bin/env python3
"""Regression checks for Wave 1 production standardization."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from standardize_company_production_wave1 import audit, apply_standardization, load_json  # noqa: E402
from validate_company_production import validate  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def companies_by_id(payload: dict) -> dict:
    return {company["company_id"]: company for company in payload["companies"]}


def main() -> None:
    payload = apply_standardization(load_json(ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"))
    companies = companies_by_id(payload)
    result = audit(payload)
    metrics = result["metrics"]

    require(result["status"] == "PASS_WITH_RESEARCH_GAPS", "standardization should pass with documented research gaps")
    require(metrics["target_company_count"] == 4, "Wave 1 production target count must stay 4")
    require(metrics["facility_count"] == 2, "two source-backed production facility records expected")
    require(metrics["official_source_facility_count"] == 2, "all confirmed facilities must have official sources")
    require(metrics["official_capacity_company_count"] == 0, "no official capacity value should be invented")
    require(metrics["capacity_unavailable_company_count"] == 4, "all Wave 1 companies lack official capacity values")
    require(metrics["facilities_without_source_count"] == 0, "facility facts require source_ids")
    require(metrics["capacities_without_unit_count"] == 0, "capacity values without units must be blocked")
    require(metrics["capacities_without_period_count"] == 0, "capacity values without periods must be blocked")
    require(metrics["null_rendered_as_zero_count"] == 0, "missing values must not be stored as zero")

    yuchang = companies["yuchang-enc"]
    kumkang = companies["kumkang-kind"]
    planm = companies["planm"]
    daeseung = companies["daeseung-engineering"]

    require(yuchang["production_summary"]["verification_status"] == "partially_verified", "YooChang should remain partial")
    require(yuchang["production"][0]["capacity_status"] == "unavailable", "YooChang capacity must remain unavailable")
    require(yuchang["production"][0]["capacity_value"] is None, "YooChang capacity cannot be inferred")
    require(yuchang["production"][0]["site_area_unit"] == "m2", "YooChang site area unit required")
    require(yuchang["production"][0]["building_area_unit"] == "m2", "YooChang building area unit required")

    require(kumkang["production_summary"]["verification_status"] == "verified", "Kumkang production should be verified")
    require(kumkang["production"][0]["modular_system_type"] == "steel_volumetric", "Kumkang modular system type required")
    require("mep_prefabrication" in kumkang["production"][0]["production_processes"], "Kumkang process list should include MEP prefabrication")
    require(kumkang["production"][0]["capacity_value"] is None, "Kumkang capacity cannot be inferred")

    for company in [planm, daeseung]:
        require(company["production"] == [], f"{company['company_id']} should not receive unsupported facility facts")
        require(company["production_summary"]["verification_status"] == "research_exhausted", f"{company['company_id']} should be closed as research gap")
        require(company["production_summary"]["facility_count"] is None, f"{company['company_id']} facility count must not be zero-as-fact")

    broken = copy.deepcopy(payload)
    broken_company = companies_by_id(broken)["kumkang-kind"]
    broken_company["production"][0]["source_ids"] = []
    validation = validate(broken)
    require(not validation["valid"], "facility without source_ids must fail validation")

    broken = copy.deepcopy(payload)
    broken_company = companies_by_id(broken)["kumkang-kind"]
    broken_company["production"][0]["capacity_value"] = 100
    validation = validate(broken)
    require(not validation["valid"], "capacity without unit and period must fail validation")

    print("company production standardization tests passed")


if __name__ == "__main__":
    main()
