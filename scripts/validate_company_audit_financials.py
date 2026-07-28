#!/usr/bin/env python3
"""Validate curated company audit financial datasets."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "company_reports" / "yuchang-enc" / "audit_financials_2023_2025.json"
SCHEMA_VERSION = "company_audit_financials_v1"
DEFAULT_BASE_REF = "origin/main"
PROTECTED_PUBLIC_FILES = [
    ROOT / "frontend" / "public" / "data" / "business.json",
    ROOT / "frontend" / "public" / "data" / "news.json",
    ROOT / "frontend" / "public" / "data" / "meta.json",
    ROOT / "frontend" / "public" / "data" / "companies" / "companies.json",
    ROOT / "frontend" / "public" / "data" / "companies" / "company_intelligence_v2.json",
]
REQUIRED_YEAR_SECTIONS = {
    "income_statement",
    "balance_sheet",
    "cash_flow",
    "revenue_breakdown",
    "working_capital",
    "borrowings",
    "investment_signals",
    "source_refs",
}
REQUIRED_INCOME_FIELDS = {"revenue", "gross_profit", "operating_profit", "net_income"}
REQUIRED_BALANCE_FIELDS = {"total_assets", "total_liabilities", "total_equity", "current_assets", "current_liabilities"}
REQUIRED_CASH_FLOW_FIELDS = {"operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "ending_cash"}
REQUIRED_REVENUE_FIELDS = {"goods_revenue", "product_revenue", "construction_revenue", "rental_revenue", "other_revenue"}
REQUIRED_BORROWING_FIELDS = {"short_term_borrowings", "current_portion_long_term_borrowings", "long_term_borrowings"}
REQUIRED_WORKING_CAPITAL_FIELDS = {
    "trade_receivables_gross",
    "construction_receivables_gross",
    "inventory",
    "work_in_progress",
}
REQUIRED_INVESTMENT_FIELDS = {"construction_in_progress", "industrial_property_rights", "research_and_development_expense"}
SOURCE_LOCATION_STATUSES = {"verified", "verified_section_range", "pending_manual_page_check"}
SOURCE_SECTION_CODES = {
    "statement.income_statement",
    "statement.balance_sheet",
    "statement.cash_flow",
    "note.revenue_breakdown",
    "note.working_capital",
    "note.borrowings",
    "note.investment_signals",
}
SOURCE_SECTION_BY_PARENT = {
    "income_statement": "statement.income_statement",
    "balance_sheet": "statement.balance_sheet",
    "cash_flow": "statement.cash_flow",
    "revenue_breakdown": "note.revenue_breakdown",
    "working_capital": "note.working_capital",
    "borrowings": "note.borrowings",
    "investment_signals": "note.investment_signals",
}


@dataclass
class Issue:
    code: str
    path: str
    message: str
    expected: Any = None
    actual: Any = None
    source: str | None = None
    severity: str = "error"

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "path": self.path,
            "message": self.message,
            "expected": self.expected,
            "actual": self.actual,
            "source": self.source,
            "severity": self.severity,
        }


def load_payload(path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def expected_years_for(payload: dict[str, Any], override: list[int] | None = None) -> set[str]:
    if override:
        return {str(year) for year in override}
    metadata_years = (payload.get("validation_metadata") or {}).get("expected_years")
    if isinstance(metadata_years, list) and metadata_years:
        return {str(year) for year in metadata_years}
    return set((payload.get("financial_years") or {}).keys())


def validation_policy_for(payload: dict[str, Any]) -> dict[str, Any]:
    policy = (payload.get("validation_metadata") or {}).get("validation_policy")
    return policy if isinstance(policy, dict) else {}


def issue(issues: list[Issue], code: str, path: str, message: str, expected: Any = None, actual: Any = None, source: str | None = None) -> None:
    issues.append(Issue(code=code, path=path, message=message, expected=expected, actual=actual, source=source))


def amount(record: dict[str, Any], section: str, field: str) -> int:
    return record[section][field]["reported"]


def money_paths(value: Any, path: str = "") -> list[tuple[str, dict[str, Any]]]:
    records: list[tuple[str, dict[str, Any]]] = []
    if isinstance(value, dict):
        if "reported" in value:
            records.append((path, value))
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            records.extend(money_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            records.extend(money_paths(child, f"{path}[{index}]"))
    return records


def contains_key(value: Any, target: str) -> bool:
    if isinstance(value, dict):
        return any(key == target or contains_key(child, target) for key, child in value.items())
    if isinstance(value, list):
        return any(contains_key(child, target) for child in value)
    return False


def pct(numerator: int | None, denominator: int | None) -> Decimal | None:
    if denominator in (None, 0) or numerator is None:
        return None
    return ((Decimal(numerator) / Decimal(denominator)) * Decimal(100)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def ratio(numerator: int | None, denominator: int | None) -> Decimal | None:
    if denominator in (None, 0) or numerator is None:
        return None
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def calculate_derived_metrics(payload: dict[str, Any]) -> dict[str, dict[str, str | int | None]]:
    derived: dict[str, dict[str, str | int | None]] = {}
    previous_revenue: int | None = None
    for year in sorted(payload["financial_years"]):
        record = payload["financial_years"][year]
        revenue = amount(record, "income_statement", "revenue")
        gross_profit = amount(record, "income_statement", "gross_profit")
        operating_profit = amount(record, "income_statement", "operating_profit")
        net_income = amount(record, "income_statement", "net_income")
        liabilities = amount(record, "balance_sheet", "total_liabilities")
        equity = amount(record, "balance_sheet", "total_equity")
        current_assets = amount(record, "balance_sheet", "current_assets")
        current_liabilities = amount(record, "balance_sheet", "current_liabilities")
        borrowings = record["borrowings"]
        total_borrowings = sum(borrowings[field]["reported"] for field in REQUIRED_BORROWING_FIELDS)
        receivables_total = amount(record, "working_capital", "trade_receivables_gross") + amount(record, "working_capital", "construction_receivables_gross")
        inventory = amount(record, "working_capital", "inventory")
        operating_cash_flow = amount(record, "cash_flow", "operating_cash_flow")
        revenue_breakdown = {field: amount(record, "revenue_breakdown", field) for field in REQUIRED_REVENUE_FIELDS}
        derived[year] = {
            "revenue_yoy_pct": str(pct(revenue - previous_revenue, previous_revenue)) if previous_revenue else None,
            "gross_margin_pct": str(pct(gross_profit, revenue)),
            "operating_margin_pct": str(pct(operating_profit, revenue)),
            "net_margin_pct": str(pct(net_income, revenue)),
            "liabilities_to_equity_pct": str(pct(liabilities, equity)),
            "current_ratio_pct": str(pct(current_assets, current_liabilities)),
            "total_borrowings": total_borrowings,
            "borrowings_to_equity_pct": str(pct(total_borrowings, equity)),
            "operating_cash_flow_to_net_income": str(ratio(operating_cash_flow, net_income)),
            "receivables_total": receivables_total,
            "receivables_to_revenue_pct": str(pct(receivables_total, revenue)),
            "inventory_to_revenue_pct": str(pct(inventory, revenue)),
            "goods_revenue_share_pct": str(pct(revenue_breakdown["goods_revenue"], revenue)),
            "product_revenue_share_pct": str(pct(revenue_breakdown["product_revenue"], revenue)),
            "construction_revenue_share_pct": str(pct(revenue_breakdown["construction_revenue"], revenue)),
            "rental_revenue_share_pct": str(pct(revenue_breakdown["rental_revenue"], revenue)),
            "other_revenue_share_pct": str(pct(revenue_breakdown["other_revenue"], revenue)),
        }
        previous_revenue = revenue
    return derived


def validate_required_fields(payload: dict[str, Any], issues: list[Issue]) -> None:
    required_top = {
        "schema_version",
        "company_id",
        "company_name",
        "reporting_entity",
        "accounting_standard",
        "currency",
        "unit",
        "audit_opinions",
        "source_documents",
        "source_priority",
        "financial_years",
        "entity_attribution",
        "disclosure_limitations",
        "validation_metadata",
    }
    for key in sorted(required_top - set(payload)):
        issue(issues, "missing_required_field", key, "required top-level field is missing")
    if payload.get("schema_version") != SCHEMA_VERSION:
        issue(issues, "schema_version_mismatch", "schema_version", "schema_version mismatch", SCHEMA_VERSION, payload.get("schema_version"))
    if payload.get("currency") != "KRW" or payload.get("unit") != "won":
        issue(issues, "currency_unit_mismatch", "currency/unit", "amounts must be KRW integer won", "KRW/won", f"{payload.get('currency')}/{payload.get('unit')}")


def validate_years(payload: dict[str, Any], issues: list[Issue], expected_years: set[str]) -> None:
    years = set((payload.get("financial_years") or {}).keys())
    if years != expected_years:
        issue(issues, "financial_years_mismatch", "financial_years", "financial years do not match validation metadata or CLI override", sorted(expected_years), sorted(years))
        return
    for year, record in payload["financial_years"].items():
        missing_sections = REQUIRED_YEAR_SECTIONS - set(record)
        for section in sorted(missing_sections):
            issue(issues, "missing_year_section", f"financial_years.{year}.{section}", "required year section is missing", source=year)
        field_sets = {
            "income_statement": REQUIRED_INCOME_FIELDS,
            "balance_sheet": REQUIRED_BALANCE_FIELDS,
            "cash_flow": REQUIRED_CASH_FLOW_FIELDS,
            "revenue_breakdown": REQUIRED_REVENUE_FIELDS,
            "borrowings": REQUIRED_BORROWING_FIELDS,
            "working_capital": REQUIRED_WORKING_CAPITAL_FIELDS,
            "investment_signals": REQUIRED_INVESTMENT_FIELDS,
        }
        for section, fields in field_sets.items():
            actual_fields = set(record.get(section, {}))
            for field in sorted(fields - actual_fields):
                issue(issues, "missing_year_metric", f"financial_years.{year}.{section}.{field}", "required metric is missing", source=year)


def validate_amount_shapes(payload: dict[str, Any], issues: list[Issue]) -> None:
    source_ids = set((payload.get("source_documents") or {}).keys())
    for path, record in money_paths(payload):
        reported = record.get("reported")
        if not isinstance(reported, int) or isinstance(reported, bool):
            issue(issues, "reported_amount_not_integer", path, "reported amount must be an integer KRW value", "integer", reported, source="reported")
        refs = record.get("source_refs")
        if not isinstance(refs, list) or not refs:
            issue(issues, "missing_source_refs", f"{path}.source_refs", "reported amount requires source_refs", "non-empty list", refs)
            continue
        for source_ref in refs:
            if source_ref not in source_ids:
                issue(issues, "unknown_source_ref", f"{path}.source_refs", "source_ref is not defined", sorted(source_ids), source_ref)
        locations = record.get("source_locations")
        if locations is not None:
            if not isinstance(locations, list) or not locations:
                issue(issues, "invalid_source_locations", f"{path}.source_locations", "source_locations must be a non-empty list when present")
            else:
                for index, location in enumerate(locations):
                    location_path = f"{path}.source_locations[{index}]"
                    if not isinstance(location, dict):
                        issue(issues, "invalid_source_location", location_path, "source_location must be an object", "object", location)
                        continue
                    allowed = {"source_ref", "page", "page_range", "section", "verification_status"}
                    extra_keys = sorted(set(location) - allowed)
                    if extra_keys:
                        issue(issues, "unknown_source_location_field", location_path, "source_location contains unknown fields", [], extra_keys)
                    if location.get("source_ref") not in source_ids:
                        issue(issues, "unknown_source_location_ref", f"{location_path}.source_ref", "source_location source_ref is not defined", sorted(source_ids), location.get("source_ref"))
                    if location.get("source_ref") not in refs:
                        issue(issues, "source_location_ref_not_in_source_refs", f"{location_path}.source_ref", "source_location source_ref must also be listed in source_refs", refs, location.get("source_ref"))
                    if not location.get("section"):
                        issue(issues, "missing_source_location_section", f"{location_path}.section", "source_location requires section")
                    elif "?" in str(location.get("section")):
                        issue(issues, "corrupted_source_location_section", f"{location_path}.section", "source_location section must not contain question marks", actual=location.get("section"))
                    elif location.get("section") not in SOURCE_SECTION_CODES:
                        issue(issues, "invalid_source_location_section", f"{location_path}.section", "source_location section is not an allowed standard code", sorted(SOURCE_SECTION_CODES), location.get("section"))
                    status = location.get("verification_status")
                    if status not in SOURCE_LOCATION_STATUSES:
                        issue(issues, "invalid_source_location_status", f"{location_path}.verification_status", "invalid source location verification status", sorted(SOURCE_LOCATION_STATUSES), status)
                    if status in {"verified", "verified_section_range"} and not (location.get("page") or location.get("page_range")):
                        issue(issues, "missing_source_location_page", location_path, "verified source locations require page or page_range")
        if "inference" in record:
            issue(issues, "inference_stored_with_reported", path, "inference must not be stored inside a reported amount")


def validate_source_location_parent_sections(payload: dict[str, Any], issues: list[Issue]) -> None:
    for year, year_record in (payload.get("financial_years") or {}).items():
        for parent_section, expected_code in SOURCE_SECTION_BY_PARENT.items():
            for metric_name, metric in (year_record.get(parent_section) or {}).items():
                for index, location in enumerate(metric.get("source_locations") or []):
                    actual_code = location.get("section")
                    if actual_code != expected_code:
                        issue(
                            issues,
                            "source_location_parent_section_mismatch",
                            f"financial_years.{year}.{parent_section}.{metric_name}.source_locations[{index}].section",
                            "source_location section must match its parent financial section",
                            expected_code,
                            actual_code,
                            source=year,
                        )


def validate_accounting(payload: dict[str, Any], issues: list[Issue]) -> None:
    for year, record in (payload.get("financial_years") or {}).items():
        assets = amount(record, "balance_sheet", "total_assets")
        liabilities = amount(record, "balance_sheet", "total_liabilities")
        equity = amount(record, "balance_sheet", "total_equity")
        if assets != liabilities + equity:
            issue(issues, "asset_equation_mismatch", f"financial_years.{year}.balance_sheet", "total_assets must equal liabilities plus equity", liabilities + equity, assets, source=year)
        revenue = amount(record, "income_statement", "revenue")
        revenue_total = sum(amount(record, "revenue_breakdown", field) for field in REQUIRED_REVENUE_FIELDS)
        if revenue != revenue_total:
            issue(issues, "revenue_breakdown_mismatch", f"financial_years.{year}.revenue_breakdown", "revenue breakdown must equal revenue", revenue, revenue_total, source=year)


def validate_source_priority(payload: dict[str, Any], issues: list[Issue], expected_years: set[str]) -> None:
    source_ids = set((payload.get("source_documents") or {}).keys())
    priority = payload.get("source_priority") or {}
    priority_years = set(priority.keys())
    if priority_years != expected_years:
        issue(issues, "source_priority_years_mismatch", "source_priority", "source priority years must match expected years", sorted(expected_years), sorted(priority_years))
    for year in sorted(expected_years):
        actual = priority.get(year) or {}
        source_ref = actual.get("primary_source_ref")
        if not source_ref:
            issue(issues, "source_priority_missing_primary", f"source_priority.{year}.primary_source_ref", "source priority requires primary_source_ref", source=year)
            continue
        if source_ref not in source_ids:
            issue(issues, "source_priority_unknown_source_ref", f"source_priority.{year}.primary_source_ref", "source priority references an unknown source document", sorted(source_ids), source_ref, source=year)
        if actual.get("basis") not in {"current_year_financial_statements", "comparative_financial_statements", "cross_check"}:
            issue(issues, "source_priority_invalid_basis", f"source_priority.{year}.basis", "source priority basis is invalid", actual=actual.get("basis"), source=year)
        primary_refs = []
        for _, record in money_paths((payload.get("financial_years") or {}).get(year, {})):
            primary_refs.extend(record.get("source_refs") or [])
        if source_ref not in set(primary_refs):
            issue(issues, "source_ref_missing_primary", f"financial_years.{year}", "primary source_ref is not used by year values", source_ref, sorted(set(primary_refs)), source=year)
        for cross_ref in actual.get("cross_check_source_refs") or []:
            if cross_ref not in source_ids:
                issue(issues, "source_priority_unknown_cross_check_ref", f"source_priority.{year}.cross_check_source_refs", "cross-check source_ref is not defined", sorted(source_ids), cross_ref, source=year)


def validate_attribution(payload: dict[str, Any], issues: list[Issue]) -> None:
    attribution = payload.get("entity_attribution") or {}
    required_fields = {
        "reporting_entity",
        "financial_scope",
        "related_entity_attribution_required",
        "modular_segment_revenue_disclosed",
        "attribution_warning",
        "special_events",
    }
    for key in sorted(required_fields - set(attribution)):
        issue(issues, "missing_entity_attribution_field", f"entity_attribution.{key}", "entity attribution field is required")
    if attribution.get("financial_scope") not in {"standalone", "consolidated", "standalone_and_consolidated"}:
        issue(issues, "entity_attribution_mismatch", "entity_attribution.financial_scope", "financial_scope is invalid", ["standalone", "consolidated", "standalone_and_consolidated"], attribution.get("financial_scope"))
    if not isinstance(attribution.get("special_events"), list):
        issue(issues, "entity_attribution_mismatch", "entity_attribution.special_events", "special_events must be a list", "list", attribution.get("special_events"))
    warning = attribution.get("attribution_warning", "")
    policy = validation_policy_for(payload)
    for required in policy.get("required_attribution_warning_terms") or []:
        if required not in warning:
            issue(issues, "missing_attribution_warning", "entity_attribution.attribution_warning", f"warning must mention {required!r}")
    disclosure_limitations = payload.get("disclosure_limitations") or []
    for required in policy.get("required_disclosure_limitations") or []:
        if required not in disclosure_limitations:
            issue(issues, "missing_disclosure_limitation", "disclosure_limitations", "required disclosure limitation is missing", required, disclosure_limitations)


def validate_no_forbidden_fields(payload: dict[str, Any], issues: list[Issue]) -> None:
    policy = validation_policy_for(payload)
    for field_name in policy.get("forbidden_field_names") or []:
        if contains_key(payload, field_name):
            issue(issues, "forbidden_field_name", field_name, "validation policy forbids this field name")


def validate_cash_flow_signs(payload: dict[str, Any], issues: list[Issue]) -> None:
    expected_signs = validation_policy_for(payload).get("expected_cash_flow_signs") or {}
    for year, fields in expected_signs.items():
        record = (payload.get("financial_years") or {}).get(year)
        if not record:
            issue(issues, "cash_flow_sign_year_missing", f"financial_years.{year}", "cash-flow sign policy references a missing year", source=year)
            continue
        for field, sign in fields.items():
            if field not in record.get("cash_flow", {}):
                issue(issues, "cash_flow_sign_field_missing", f"financial_years.{year}.cash_flow.{field}", "cash-flow sign policy references a missing field", source=year)
                continue
            value = amount(record, "cash_flow", field)
            sign_matches = {
                "positive": value > 0,
                "negative": value < 0,
                "zero": value == 0,
                "non_negative": value >= 0,
                "non_positive": value <= 0,
            }
            if sign not in sign_matches:
                issue(issues, "cash_flow_sign_policy_invalid", f"validation_metadata.validation_policy.expected_cash_flow_signs.{year}.{field}", "invalid cash-flow sign policy", sorted(sign_matches), sign, source=year)
            elif not sign_matches[sign]:
                issue(issues, "cash_flow_sign_mismatch", f"financial_years.{year}.cash_flow.{field}", "cash-flow sign changed unexpectedly", sign, value, source=year)


def git_ref_exists(ref: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def protected_public_diff_status(base_ref: str | None = DEFAULT_BASE_REF, paths: list[Path] = PROTECTED_PUBLIC_FILES) -> dict[str, Any]:
    existing = [str(path.relative_to(ROOT)) for path in paths if path.exists()]
    if not existing:
        return {"mode": "none", "base_ref": base_ref, "changed_files": [], "warnings": ["no protected files found"]}
    warnings: list[str] = []
    args = ["git", "diff", "--name-only"]
    mode = "worktree"
    if base_ref:
        if git_ref_exists(base_ref):
            args.append(f"{base_ref}...HEAD")
            mode = "branch_vs_base"
        else:
            warnings.append(f"base ref not found: {base_ref}; falling back to worktree diff")
    args.extend(["--", *existing])
    try:
        result = subprocess.run(
            args,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return {"mode": mode, "base_ref": base_ref, "changed_files": [], "warnings": warnings + ["git diff command failed"]}
    return {
        "mode": mode,
        "base_ref": base_ref,
        "changed_files": [line.strip() for line in result.stdout.splitlines() if line.strip()],
        "warnings": warnings,
    }


def protected_public_diffs(paths: list[Path] = PROTECTED_PUBLIC_FILES) -> list[str]:
    return protected_public_diff_status(base_ref=None, paths=paths)["changed_files"]


def validate(payload: dict[str, Any], expected_year_override: list[int] | None = None, base_ref: str | None = DEFAULT_BASE_REF) -> dict[str, Any]:
    issues: list[Issue] = []
    expected_years = expected_years_for(payload, expected_year_override)
    validate_required_fields(payload, issues)
    validate_years(payload, issues, expected_years)
    if set((payload.get("financial_years") or {}).keys()) == expected_years:
        validate_amount_shapes(payload, issues)
        validate_source_location_parent_sections(payload, issues)
        validate_accounting(payload, issues)
        validate_source_priority(payload, issues, expected_years)
        validate_attribution(payload, issues)
        validate_no_forbidden_fields(payload, issues)
        validate_cash_flow_signs(payload, issues)
    protected_status = protected_public_diff_status(base_ref=base_ref)
    if protected_status["changed_files"]:
        issue(issues, "protected_public_file_changed", "frontend/public/data", "protected public data files changed versus protected diff scope", [], protected_status["changed_files"])
    derived_metrics = calculate_derived_metrics(payload) if not any(item.code.startswith("missing") for item in issues) else {}
    return {
        "valid": not any(item.severity == "error" for item in issues),
        "schema_version": payload.get("schema_version"),
        "company_id": payload.get("company_id"),
        "financial_years_loaded": sorted((payload.get("financial_years") or {}).keys()),
        "expected_years": sorted(expected_years),
        "derived_metrics": derived_metrics,
        "issue_count": len(issues),
        "issues": [item.as_dict() for item in issues],
        "protected_public_diff": protected_status,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate company audit financial source data.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--expected-years", nargs="*", type=int, default=None, help="Override expected financial years.")
    parser.add_argument("--base-ref", default=DEFAULT_BASE_REF, help="Base ref used for protected public data diff checks.")
    args = parser.parse_args()
    payload = load_payload(args.input)
    result = validate(payload, expected_year_override=args.expected_years, base_ref=args.base_ref)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
