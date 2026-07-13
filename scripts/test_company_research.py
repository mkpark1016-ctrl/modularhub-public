#!/usr/bin/env python3
"""Regression tests for Wave 1 company research records."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_company_research_quality import audit  # noqa: E402
from validate_company_research import WAVE1_IDS, load_companies, validate_research, wave1_companies  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    companies = wave1_companies(load_companies())
    by_id = {company["company_id"]: company for company in companies}
    validation = validate_research()
    result = audit()

    require(len(companies) == 4, "Wave 1 must contain 4 companies")
    require([company["company_id"] for company in companies] == WAVE1_IDS, "Wave 1 order or membership changed")
    require(validation["valid"], f"research validation failed: {validation['issues']}")
    require(validation["issue_counts"]["fact_without_source"] == 0, "facts without sources must be zero")
    require(validation["issue_counts"]["number_without_source"] == 0, "numbers without sources must be zero")
    require(validation["issue_counts"]["production_capacity_without_unit"] == 0, "capacity values without units must be zero")
    require(validation["issue_counts"]["project_role_missing"] == 0, "project role missing must be zero")
    require(validation["issue_counts"]["project_status_missing"] == 0, "project status missing must be zero")
    require(validation["issue_counts"]["financial_reporting_scope_missing"] == 0, "financial scope missing must be zero")
    require(validation["issue_counts"]["technology_status_missing"] == 0, "technology status missing must be zero")
    require(validation["issue_counts"]["duplicate_source_url"] == 0, "duplicate source URLs must be zero")
    require(result["audit_status"] == "passed", "Wave 1 audit must pass")

    kumkang = by_id["kumkang-kind"]
    require(kumkang["data_confidence"] == "medium", "Kumkang confidence should reflect official-source partial verification")
    require(len(kumkang["project_portfolio"]) == 3, "Kumkang should have 3 official project records")
    require(result["total_project_count"] == 3, "total project count mismatch")
    require(result["total_technology_record_count"] == 1, "technology record count mismatch")
    require(result["total_financial_year_count"] == 0, "financials must remain empty without filing source")
    require(result["total_bidding_record_count"] == 0, "bidding data must remain empty without verified dataset")

    for company_id in ["planm", "daeseung-engineering"]:
        company = by_id[company_id]
        require(company["review_status"] == "collecting", f"{company_id} should remain collecting")
        require(company["data_confidence"] == "unknown", f"{company_id} confidence should remain unknown")
        require(len(company.get("sources", [])) == 0, f"{company_id} should not have unverified sources")
        require(company["project_portfolio"] == [], f"{company_id} project portfolio must remain empty")

    print("COMPANY RESEARCH TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
