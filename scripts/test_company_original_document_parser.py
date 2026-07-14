#!/usr/bin/env python3
"""Regression tests for original DART audit-report parser outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from audit_company_dart_financials import fiscal_year_from_filing  # noqa: E402


COMPANIES_PATH = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def company_by_id(payload: dict, company_id: str) -> dict:
    return next(company for company in payload["companies"] if company["company_id"] == company_id)


def financial_by_year(company: dict, year: int) -> dict:
    return next(item for item in company.get("financials", []) if item.get("year") == year)


def metric_value(company: dict, year: int, metric: str) -> int:
    value = financial_by_year(company, year).get(metric)
    require(isinstance(value, dict), f"{company['company_id']} {year} {metric} must be structured")
    require(value.get("receipt_number"), f"{company['company_id']} {year} {metric} requires receipt number")
    require(value.get("source_ids"), f"{company['company_id']} {year} {metric} requires source_ids")
    require(value.get("source_unit") == "KRW", f"{company['company_id']} {year} {metric} source unit must be KRW")
    return int(value["source_value"])


def assert_balance_equation(company: dict) -> None:
    for financial in company.get("financials", []):
        assets = financial.get("total_assets", {}).get("source_value")
        liabilities = financial.get("total_liabilities", {}).get("source_value")
        equity = financial.get("total_equity", {}).get("source_value")
        if assets is not None and liabilities is not None and equity is not None:
            require(assets == liabilities + equity, f"{company['company_id']} {financial.get('year')} balance equation mismatch")


def main() -> int:
    payload = json.loads(COMPANIES_PATH.read_text(encoding="utf-8"))

    require(fiscal_year_from_filing({"report_nm": "감사보고서 (2025.06)", "rcept_dt": "20250917"}) == 2025, "June fiscal report must map to stated report year")
    require(fiscal_year_from_filing({"report_nm": "감사보고서 (2024.12)", "rcept_dt": "20250424"}) == 2024, "December fiscal report must map to stated report year")

    yuchang = company_by_id(payload, "yuchang-enc")
    require(metric_value(yuchang, 2025, "revenue") == 307_684_467_052, "YooChang 2025 revenue regression")
    require(metric_value(yuchang, 2025, "operating_profit") == 14_867_615_594, "YooChang 2025 operating profit regression")
    require(metric_value(yuchang, 2025, "net_income") == 5_662_989_075, "YooChang 2025 net income regression")
    require(metric_value(yuchang, 2025, "operating_cash_flow") == -30_830_315_410, "YooChang 2025 OCF regression")
    require(metric_value(yuchang, 2024, "revenue") == 364_024_587_969, "YooChang 2024 revenue regression")
    require(metric_value(yuchang, 2024, "operating_profit") == 9_124_197_103, "YooChang 2024 operating profit regression")
    require(metric_value(yuchang, 2024, "net_income") == 10_850_960_336, "YooChang 2024 net income regression")
    require(metric_value(yuchang, 2024, "operating_cash_flow") == -32_263_069_529, "YooChang 2024 OCF regression")

    planm = company_by_id(payload, "planm")
    daeseung = company_by_id(payload, "daeseung-engineering")
    for company in [planm, daeseung]:
        years = [item["year"] for item in company.get("financials", [])]
        require(years[:3] == [2025, 2024, 2023], f"{company['company_id']} must have recent available 3 financial years")
        require(company.get("financial_summary", {}).get("modular_segment_available") is False, f"{company['company_id']} modular segment must not be inferred")
        for audit in company.get("audit_information", [])[:3]:
            require(audit.get("auditor"), f"{company['company_id']} {audit.get('fiscal_year')} auditor must be extracted")
            require(audit.get("audit_opinion") == "unmodified", f"{company['company_id']} {audit.get('fiscal_year')} opinion must be unmodified")
            require(audit.get("accounting_standard") == "general_korean_gaap", f"{company['company_id']} accounting standard must be extracted")
        assert_balance_equation(company)

    require(metric_value(planm, 2025, "revenue") == 59_222_859_418, "PlanM 2025 revenue regression")
    require(metric_value(daeseung, 2025, "revenue") == 61_659_861_549, "Daeseung 2025 revenue regression")
    print("COMPANY ORIGINAL DOCUMENT PARSER TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
