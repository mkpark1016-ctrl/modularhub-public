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
EXPECTED_YEARS = {"2023", "2024", "2025"}
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


def validate_years(payload: dict[str, Any], issues: list[Issue]) -> None:
    years = set((payload.get("financial_years") or {}).keys())
    if years != EXPECTED_YEARS:
        issue(issues, "financial_years_mismatch", "financial_years", "expected exactly 2023, 2024, and 2025", sorted(EXPECTED_YEARS), sorted(years))
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
        if "inference" in record:
            issue(issues, "inference_stored_with_reported", path, "inference must not be stored inside a reported amount")


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


def validate_source_priority(payload: dict[str, Any], issues: list[Issue]) -> None:
    expected = {
        "2025": ("yuchang_audit_report_2026_04_08", "current_year_financial_statements"),
        "2024": ("yuchang_audit_report_2026_04_08", "comparative_financial_statements"),
        "2023": ("yuchang_audit_report_2025_04_04", "comparative_financial_statements"),
    }
    priority = payload.get("source_priority") or {}
    for year, (source_ref, basis) in expected.items():
        actual = priority.get(year) or {}
        if actual.get("primary_source_ref") != source_ref or actual.get("basis") != basis:
            issue(issues, "source_priority_mismatch", f"source_priority.{year}", "source priority does not match the audit-report policy", {"primary_source_ref": source_ref, "basis": basis}, actual, source=year)
        primary_refs = []
        for _, record in money_paths((payload.get("financial_years") or {}).get(year, {})):
            primary_refs.extend(record.get("source_refs") or [])
        if source_ref not in set(primary_refs):
            issue(issues, "source_ref_missing_primary", f"financial_years.{year}", "primary source_ref is not used by year values", source_ref, sorted(set(primary_refs)), source=year)
    cross_checks = priority.get("2023", {}).get("cross_check_source_refs") or []
    if "yuchang_audit_report_2024_04_05" not in cross_checks:
        issue(issues, "missing_2023_cross_check", "source_priority.2023.cross_check_source_refs", "2024.04.05 report must be marked as 2023 cross-check only")


def validate_attribution(payload: dict[str, Any], issues: list[Issue]) -> None:
    attribution = payload.get("entity_attribution") or {}
    expected_true = [
        "standalone_financials",
        "school_modular_business_spin_off_disclosed",
        "product_revenue_is_not_modular_revenue",
        "construction_revenue_is_not_modular_revenue",
        "related_entity_attribution_required",
    ]
    for key in expected_true:
        if attribution.get(key) is not True:
            issue(issues, "entity_attribution_mismatch", f"entity_attribution.{key}", "entity attribution flag must be true", True, attribution.get(key))
    if attribution.get("group_consolidated_financials") is not False:
        issue(issues, "entity_attribution_mismatch", "entity_attribution.group_consolidated_financials", "dataset must be standalone, not group consolidated", False, attribution.get("group_consolidated_financials"))
    if attribution.get("modular_segment_revenue_disclosed") is not False:
        issue(issues, "modular_segment_misclassification", "entity_attribution.modular_segment_revenue_disclosed", "modular segment revenue must remain undisclosed", False, attribution.get("modular_segment_revenue_disclosed"))
    warning = attribution.get("attribution_warning", "")
    for required in ["별도 재무제표", "유창엠앤씨", "자동 합산하지 않는다"]:
        if required not in warning:
            issue(issues, "missing_attribution_warning", "entity_attribution.attribution_warning", f"warning must mention {required!r}")


def validate_no_forbidden_fields(payload: dict[str, Any], issues: list[Issue]) -> None:
    if contains_key(payload, "modular_revenue"):
        issue(issues, "forbidden_modular_revenue", "modular_revenue", "modular_revenue must not be stored because the audit reports do not disclose segment revenue")
    if contains_key(payload, "derived"):
        issue(issues, "derived_stored_in_source_json", "derived", "derived values must be calculated by validator/public transform code, not manually stored in source JSON")
    if contains_key(payload, "inference"):
        issue(issues, "inference_stored_in_source_json", "inference", "inference must not be stored as reported source data")


def validate_cash_flow_signs(payload: dict[str, Any], issues: list[Issue]) -> None:
    expected_signs = {
        "2023": {"operating_cash_flow": 1, "investing_cash_flow": -1, "financing_cash_flow": 1},
        "2024": {"operating_cash_flow": -1, "investing_cash_flow": -1, "financing_cash_flow": 1},
        "2025": {"operating_cash_flow": -1, "investing_cash_flow": -1, "financing_cash_flow": 1},
    }
    for year, fields in expected_signs.items():
        record = payload["financial_years"][year]
        for field, sign in fields.items():
            value = amount(record, "cash_flow", field)
            if sign > 0 and value < 0:
                issue(issues, "cash_flow_sign_mismatch", f"financial_years.{year}.cash_flow.{field}", "cash-flow sign changed unexpectedly", "positive", value, source=year)
            if sign < 0 and value > 0:
                issue(issues, "cash_flow_sign_mismatch", f"financial_years.{year}.cash_flow.{field}", "cash-flow sign changed unexpectedly", "negative", value, source=year)


def protected_public_diffs(paths: list[Path] = PROTECTED_PUBLIC_FILES) -> list[str]:
    existing = [str(path.relative_to(ROOT)) for path in paths if path.exists()]
    if not existing:
        return []
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--", *existing],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def validate(payload: dict[str, Any]) -> dict[str, Any]:
    issues: list[Issue] = []
    validate_required_fields(payload, issues)
    validate_years(payload, issues)
    if set((payload.get("financial_years") or {}).keys()) == EXPECTED_YEARS:
        validate_amount_shapes(payload, issues)
        validate_accounting(payload, issues)
        validate_source_priority(payload, issues)
        validate_attribution(payload, issues)
        validate_no_forbidden_fields(payload, issues)
        validate_cash_flow_signs(payload, issues)
    protected_diffs = protected_public_diffs()
    if protected_diffs:
        issue(issues, "protected_public_file_changed", "frontend/public/data", "protected public data files have local diffs", [], protected_diffs)
    derived_metrics = calculate_derived_metrics(payload) if not any(item.code.startswith("missing") for item in issues) else {}
    return {
        "valid": not any(item.severity == "error" for item in issues),
        "schema_version": payload.get("schema_version"),
        "company_id": payload.get("company_id"),
        "financial_years_loaded": sorted((payload.get("financial_years") or {}).keys()),
        "derived_metrics": derived_metrics,
        "issue_count": len(issues),
        "issues": [item.as_dict() for item in issues],
        "protected_public_files_changed": protected_diffs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate company audit financial source data.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    payload = load_payload(args.input)
    result = validate(payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
