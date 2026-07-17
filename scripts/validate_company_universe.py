#!/usr/bin/env python3
"""Validate the ModularHub company universe seed dataset."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from company_publication import load_public_company_ids

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"

COMPETITIVE_ROLES = {
    "direct_competitor",
    "substitute_competitor",
    "strategic_benchmark",
    "design_influencer",
    "internal_baseline",
    "watchlist",
}
COMPANY_TYPES = {
    "general_contractor",
    "specialist_manufacturer",
    "modular_integrator",
    "design_firm",
    "engineering_firm",
    "material_supplier",
    "solution_provider",
}
MODULAR_METHODS = {
    "steel_volumetric",
    "steel_panelized",
    "pc_volumetric",
    "pc_ramen",
    "wood_volumetric",
    "wood_panelized",
    "hybrid",
    "bathroom_pod",
    "unknown",
}
TARGET_MARKETS = {
    "public_housing",
    "private_housing",
    "school",
    "dormitory",
    "hotel",
    "senior_housing",
    "office",
    "military",
    "hospital",
    "industrial",
    "data_center",
    "temporary_building",
    "overseas",
    "unknown",
}
REVIEW_STATUSES = {"unresearched", "collecting", "partially_verified", "verified", "update_required"}
DATA_CONFIDENCE = {"high", "medium", "low", "review", "unknown"}
ANALYSIS_TIERS = {"tier_1", "tier_1b", "tier_2", "tier_3", "watchlist"}

REQUIRED_COMPANY_FIELDS = {
    "schema_version",
    "company_id",
    "company_name",
    "company_name_en",
    "aliases",
    "country_code",
    "company_type",
    "competitive_role",
    "analysis_tier",
    "business_status",
    "modular_methods",
    "target_markets",
    "headquarters",
    "website_url",
    "listed_market",
    "ticker",
    "summary",
    "last_verified_at",
    "data_confidence",
    "review_status",
    "company_profile",
    "production",
    "project_portfolio",
    "bidding_performance",
    "technology",
    "financials",
    "recent_signals",
    "sources",
}

EXPECTED_TIER_COUNTS = {
    "tier_1": 5,
    "tier_1b": 1,
    "tier_2": 4,
}
EXPECTED_ROLE_COUNTS = {
    "direct_competitor": 5,
    "substitute_competitor": 1,
    "strategic_benchmark": 3,
    "internal_baseline": 1,
}


def load_universe(path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def companies(payload: dict[str, Any]) -> list[dict[str, Any]]:
    value = payload.get("companies", [])
    return value if isinstance(value, list) else []


def normalized_alias(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def add_error(errors: list[dict[str, Any]], code: str, company_id: str, field: str, message: str) -> None:
    errors.append({"code": code, "company_id": company_id, "field": field, "message": message})


def validate_universe(payload: dict[str, Any]) -> dict[str, Any]:
    rows = companies(payload)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if payload.get("schema_version") != "company-universe-v1":
        add_error(errors, "invalid_schema_version", "", "schema_version", "top-level schema_version must be company-universe-v1")
    public_ids = set(load_public_company_ids())
    if len(rows) != len(public_ids):
        add_error(errors, "invalid_company_count", "", "companies", f"expected {len(public_ids)} companies, got {len(rows)}")

    ids = [str(row.get("company_id", "")) for row in rows]
    if set(ids) != public_ids:
        add_error(errors, "public_allowlist_mismatch", "", "companies", f"public ids differ from allowlist: {sorted(set(ids) ^ public_ids)}")
    id_counts = Counter(ids)
    for company_id, count in id_counts.items():
        if not company_id or count > 1:
            add_error(errors, "duplicate_or_missing_company_id", company_id, "company_id", f"count={count}")
        if company_id and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", company_id):
            add_error(errors, "invalid_company_id_format", company_id, "company_id", "must be lowercase kebab-case")

    alias_owner: dict[str, str] = {}
    alias_collisions: list[dict[str, str]] = []
    for row in rows:
        company_id = str(row.get("company_id", ""))
        missing = sorted(REQUIRED_COMPANY_FIELDS - set(row.keys()))
        for field in missing:
            add_error(errors, "missing_required_field", company_id, field, "required field is missing")

        if row.get("schema_version") != "company-master-v1":
            add_error(errors, "invalid_company_schema_version", company_id, "schema_version", "must be company-master-v1")
        if row.get("company_type") not in COMPANY_TYPES:
            add_error(errors, "invalid_enum", company_id, "company_type", str(row.get("company_type")))
        if row.get("competitive_role") not in COMPETITIVE_ROLES:
            add_error(errors, "invalid_enum", company_id, "competitive_role", str(row.get("competitive_role")))
        if row.get("analysis_tier") not in ANALYSIS_TIERS:
            add_error(errors, "invalid_enum", company_id, "analysis_tier", str(row.get("analysis_tier")))
        if row.get("review_status") not in REVIEW_STATUSES:
            add_error(errors, "invalid_enum", company_id, "review_status", str(row.get("review_status")))
        if row.get("data_confidence") not in DATA_CONFIDENCE:
            add_error(errors, "invalid_enum", company_id, "data_confidence", str(row.get("data_confidence")))
        if not re.fullmatch(r"[A-Z]{2}", str(row.get("country_code", ""))):
            add_error(errors, "invalid_country_code", company_id, "country_code", str(row.get("country_code")))

        aliases = row.get("aliases")
        if not isinstance(aliases, list) or not aliases:
            add_error(errors, "invalid_aliases", company_id, "aliases", "aliases must be a non-empty array")
        else:
            for alias in aliases:
                key = normalized_alias(str(alias))
                if key in alias_owner and alias_owner[key] != company_id:
                    alias_collisions.append({"alias": str(alias), "company_id": company_id, "other_company_id": alias_owner[key]})
                    add_error(errors, "alias_collision", company_id, "aliases", f"{alias} also belongs to {alias_owner[key]}")
                alias_owner[key] = company_id

        for method in row.get("modular_methods", []):
            if method not in MODULAR_METHODS:
                add_error(errors, "invalid_enum", company_id, "modular_methods", str(method))
        for market in row.get("target_markets", []):
            if market not in TARGET_MARKETS:
                add_error(errors, "invalid_enum", company_id, "target_markets", str(market))

        validate_production(row, errors)
        validate_financials(row, errors)
        validate_seed_numbers(row, errors)
        validate_sources(row, errors)
        if row.get("review_status") == "unresearched":
            warnings.append({"code": "research_required", "company_id": company_id, "message": "seed company needs source-backed research"})

    tier_counts = Counter(row.get("analysis_tier") for row in rows)
    role_counts = Counter(row.get("competitive_role") for row in rows)
    for tier, expected in EXPECTED_TIER_COUNTS.items():
        if tier_counts.get(tier, 0) != expected:
            add_error(errors, "tier_count_mismatch", "", "analysis_tier", f"{tier}: expected {expected}, got {tier_counts.get(tier, 0)}")
    for role, expected in EXPECTED_ROLE_COUNTS.items():
        if role_counts.get(role, 0) != expected:
            add_error(errors, "role_count_mismatch", "", "competitive_role", f"{role}: expected {expected}, got {role_counts.get(role, 0)}")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "company_count": len(rows),
        "tier_counts": dict(tier_counts),
        "role_counts": dict(role_counts),
        "company_id_duplicate_count": sum(1 for count in id_counts.values() if count > 1),
        "alias_collision_count": len(alias_collisions),
        "alias_collisions": alias_collisions,
        "required_field_missing_count": sum(1 for error in errors if error["code"] == "missing_required_field"),
        "invalid_enum_count": sum(1 for error in errors if error["code"] == "invalid_enum"),
        "unverified_numeric_count": sum(1 for error in errors if error["code"] == "unverified_seed_number"),
        "production_capacity_without_unit_count": sum(1 for error in errors if error["code"] == "production_capacity_without_unit"),
        "financial_scope_missing_count": sum(1 for error in errors if error["code"] == "financial_scope_missing"),
        "internal_baseline_count": role_counts.get("internal_baseline", 0),
        "direct_competitor_count": role_counts.get("direct_competitor", 0),
    }


def validate_production(row: dict[str, Any], errors: list[dict[str, Any]]) -> None:
    company_id = str(row.get("company_id", ""))
    for index, production in enumerate(row.get("production", []) or []):
        capacity_value = production.get("capacity_value")
        capacity_unit = production.get("capacity_unit")
        if capacity_value is not None and not capacity_unit:
            add_error(errors, "production_capacity_without_unit", company_id, f"production[{index}].capacity_unit", "capacity value requires unit")


def validate_financials(row: dict[str, Any], errors: list[dict[str, Any]]) -> None:
    company_id = str(row.get("company_id", ""))
    for index, financial in enumerate(row.get("financials", []) or []):
        if financial.get("scope") not in {"consolidated", "separate", "modular_segment"}:
            add_error(errors, "financial_scope_missing", company_id, f"financials[{index}].scope", "financial scope is required")


def validate_seed_numbers(row: dict[str, Any], errors: list[dict[str, Any]]) -> None:
    company_id = str(row.get("company_id", ""))
    if row.get("review_status") != "unresearched":
        return
    numeric_paths = [
        ("company_profile.modular_business_started_year", row.get("company_profile", {}).get("modular_business_started_year")),
        ("technology.factory_completion_rate", row.get("technology", {}).get("factory_completion_rate")),
    ]
    for path, value in numeric_paths:
        if isinstance(value, (int, float)):
            add_error(errors, "unverified_seed_number", company_id, path, "unresearched seed must not contain numeric claims")


def validate_sources(row: dict[str, Any], errors: list[dict[str, Any]]) -> None:
    company_id = str(row.get("company_id", ""))
    seen = set()
    for index, source in enumerate(row.get("sources", []) or []):
        source_id = source.get("source_id")
        if not source_id:
            add_error(errors, "missing_source_id", company_id, f"sources[{index}].source_id", "source_id is required")
        if source_id in seen:
            add_error(errors, "duplicate_source_id", company_id, f"sources[{index}].source_id", str(source_id))
        seen.add(source_id)
        if source.get("confidence") not in DATA_CONFIDENCE:
            add_error(errors, "invalid_enum", company_id, f"sources[{index}].confidence", str(source.get("confidence")))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ModularHub company universe.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    payload = load_universe(args.input)
    result = validate_universe(payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
