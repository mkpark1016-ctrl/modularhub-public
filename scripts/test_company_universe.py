#!/usr/bin/env python3
"""Tests for the ModularHub company universe seed dataset."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_company_universe import audit, research_required  # noqa: E402
from validate_company_universe import load_universe, validate_universe  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    payload = load_universe()
    companies = payload["companies"]
    validation = validate_universe(payload)
    result = audit(payload)
    by_id = {company["company_id"]: company for company in companies}

    require(validation["valid"], f"company universe validation failed: {validation['errors']}")
    require(len(companies) == 17, "company universe must contain 17 companies")
    require(result["tier_counts"].get("tier_1") == 8, "Tier 1 direct competitor count mismatch")
    require(result["tier_counts"].get("tier_1b") == 1, "Tier 1-B benchmark count mismatch")
    require(result["tier_counts"].get("tier_2") == 5, "Tier 2 strategic contractor count mismatch")
    require(result["tier_counts"].get("tier_3") == 3, "Tier 3 design influencer count mismatch")
    require(result["role_counts"].get("direct_competitor") == 8, "direct competitor role count mismatch")
    require(result["role_counts"].get("substitute_competitor") == 1, "substitute competitor role count mismatch")
    require(result["role_counts"].get("internal_baseline") == 1, "internal baseline count mismatch")
    require(by_id["gs-ec"]["competitive_role"] == "internal_baseline", "GS E&C must be internal baseline")
    require(by_id["nrb"]["analysis_tier"] == "tier_1b", "NRB must be Tier 1-B")
    require(by_id["nrb"]["competitive_role"] == "substitute_competitor", "NRB must be substitute competitor")
    require(validation["company_id_duplicate_count"] == 0, "company_id duplicates must be zero")
    require(validation["alias_collision_count"] == 0, "alias collisions must be zero")
    require(validation["required_field_missing_count"] == 0, "required field missing count must be zero")
    require(validation["invalid_enum_count"] == 0, "invalid enum count must be zero")
    require(validation["unverified_numeric_count"] == 0, "unverified numeric count must be zero")
    require(validation["production_capacity_without_unit_count"] == 0, "production capacity without unit count must be zero")
    require(validation["financial_scope_missing_count"] == 0, "financial scope missing count must be zero")
    wave1_ids = {"yuchang-enc", "kumkang-kind", "planm", "daeseung-engineering"}
    require(
        all(company["review_status"] in {"unresearched", "collecting", "partially_verified"} for company in companies),
        "company review statuses must follow the research lifecycle",
    )
    require(
        all(company["review_status"] == "unresearched" for company in companies if company["company_id"] not in wave1_ids),
        "non-Wave 1 companies should remain unresearched",
    )
    require(all(not company["production"] for company in companies), "production data must remain empty until facility facts are verified")
    require(
        all(not company["financials"] or all(record.get("source_ids") and record.get("scope") for record in company["financials"]) for company in companies),
        "financial data must be empty or source-backed with scope",
    )
    research = research_required(companies)
    require(sum(1 for row in research if row["analysis_tier"] == "tier_1" and row["research_priority"] == "P0") == 8, "Tier 1 research priority mismatch")
    print("COMPANY UNIVERSE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
