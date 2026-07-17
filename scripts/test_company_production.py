#!/usr/bin/env python3
"""Unit tests for source-backed production facility contracts."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from validate_company_production import validate

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"


def assert_issue(payload: dict, code: str) -> None:
    result = validate(payload)
    assert any(issue["code"] == code for issue in result["issues"]), f"expected issue {code}"


def main() -> None:
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    result = validate(payload)
    assert result["valid"], result
    companies = {company["company_id"]: company for company in payload["companies"]}
    assert len(companies["yuchang-enc"]["production"]) == 4
    assert len(companies["kumkang-kind"]["production"]) == 3
    assert len(companies["planm"]["production"]) == 1
    assert len(companies["sungji-steel"]["production"]) == 3
    assert companies["dl-enc"]["production_summary"]["own_facility_status"] == "not_publicly_confirmed"
    assert companies["dl-enc"]["production"] == []
    assert companies["yuchang-enc"]["production"][0]["site_area_m2"] != 0
    assert companies["yuchang-enc"]["production"][0]["reported_capacity"] == 30
    assert companies["kumkang-kind"]["production"][0]["capacity_basis"] == "target_manual_verified"

    broken = copy.deepcopy(payload)
    broken_company = next(company for company in broken["companies"] if company["company_id"] == "yuchang-enc")
    broken_company["production"][0]["source_ids"] = []
    assert_issue(broken, "source_id_missing")

    broken = copy.deepcopy(payload)
    broken_company = next(company for company in broken["companies"] if company["company_id"] == "yuchang-enc")
    broken_company["production"][0]["facility_id"] = "duplicate"
    broken_company["production"].append({**broken_company["production"][0], "facility_name": "Duplicate"})
    assert_issue(broken, "duplicate_facility_id")

    broken = copy.deepcopy(payload)
    broken_company = next(company for company in broken["companies"] if company["company_id"] == "kumkang-kind")
    broken_company["production"][0]["reported_capacity"] = 100
    broken_company["production"][0]["capacity_unit"] = None
    assert_issue(broken, "capacity_unit_missing")

    broken = copy.deepcopy(payload)
    broken_company = next(company for company in broken["companies"] if company["company_id"] == "dl-enc")
    broken_company["production_summary"]["own_facility_status"] = "not_publicly_confirmed"
    broken_company["production_summary"]["confirmed_facility_count"] = 0
    broken_company["production"].append({
        "facility_id": "planm-planned",
        "facility_name": "Planned",
        "own_facility_status": "planned_facility",
        "source_ids": broken_company["production_summary"]["source_ids"],
    })
    assert validate(broken)["valid"], "planned facility must not be counted as active"

    print("COMPANY PRODUCTION TESTS PASSED")


if __name__ == "__main__":
    main()
