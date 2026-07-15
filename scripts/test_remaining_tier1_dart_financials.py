#!/usr/bin/env python3
"""Tests for remaining Tier 1 DART financial enrichment."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from enrich_remaining_tier1_dart_financials import WAVE1_IDS, metric_value, rows_for_artifacts, select_targets, validate_targets  # noqa: E402

COMPANIES_PATH = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_payload() -> dict:
    return json.loads(COMPANIES_PATH.read_text(encoding="utf-8"))


def main() -> int:
    payload = load_payload()
    companies = {company["company_id"]: company for company in payload.get("companies", [])}
    targets = select_targets(payload)
    target_ids = {company["company_id"] for company in targets}
    require(len(targets) == 4, "remaining Tier 1 target selector should keep the non-Wave1 direct competitors")
    require(target_ids == {"sungji-steel", "geogwang-enterprise", "m3-systems", "jinwoo-inc"}, "unexpected remaining Tier 1 target ids")
    for wave_id in WAVE1_IDS:
        require(wave_id not in target_ids, "existing Wave 1 companies must be excluded")

    confirmed = [companies[company_id] for company_id in ["sungji-steel", "geogwang-enterprise", "m3-systems"]]
    for company in confirmed:
        identity = company.get("dart_identity") or {}
        require(identity.get("identity_status") == "confirmed", f"{company['company_id']} must have confirmed identity")
        require(identity.get("dart_corp_code"), f"{company['company_id']} corp_code missing")
        for financial in company.get("financials") or []:
            require(financial.get("reporting_scope"), f"{company['company_id']} financial scope missing")
            require(financial.get("source_ids"), f"{company['company_id']} financial source missing")
            for metric in ["revenue", "operating_profit", "net_income", "total_assets", "total_liabilities", "total_equity"]:
                value = financial.get(metric)
                if isinstance(value, dict):
                    require(value.get("source_ids"), f"{company['company_id']} {metric} source missing")
                    require(value.get("source_unit") and value.get("normalized_unit"), f"{company['company_id']} {metric} unit missing")
            assets = metric_value(financial, "total_assets")
            liabilities = metric_value(financial, "total_liabilities")
            equity = metric_value(financial, "total_equity")
            if assets is not None and liabilities is not None and equity is not None:
                require(assets == liabilities + equity, f"{company['company_id']} balance equation mismatch")

    require(len(companies["sungji-steel"].get("financials") or []) == 3, "Sungji Steel should have three years")
    require(len(companies["geogwang-enterprise"].get("financials") or []) == 3, "Geogwang should have three years")
    require(len(companies["m3-systems"].get("financials") or []) == 2, "M3 Systems should have standalone 2025 and comparative 2024 years")
    require((companies["m3-systems"].get("financials") or [])[1].get("evidence_type") == "comparative_financial_statement", "M3 2024 must be marked as comparative financial statement")
    require((companies["jinwoo-inc"].get("dart_identity") or {}).get("identity_status") == "manual_review_required", "Jinwoo should require manual legal identity review")
    require(not companies["jinwoo-inc"].get("financials"), "unresolved identity must not receive financials")

    baseline = {company_id: {field: companies[company_id].get(field) for field in ["dart_identity", "financials", "financial_summary", "production"]} for company_id in WAVE1_IDS}
    issues, counts = validate_targets(payload, targets, baseline)
    errors = [issue for issue in issues if issue.get("severity") == "error"]
    require(not errors, f"remaining Tier 1 validation errors: {errors}")
    require(counts.get("source_id_missing", 0) == 0, "source_id missing count must be zero")
    require(counts.get("unit_missing", 0) == 0, "unit missing count must be zero")
    rows = rows_for_artifacts(payload, targets, [], issues)
    require(len(rows["financial_year_summary"]) == 8, "financial year summary should contain the non-Wave1 financial rows")
    print("REMAINING TIER 1 DART FINANCIAL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
