#!/usr/bin/env python3
"""Verify general-contractor financial coverage in local or production View Model JSON.

The verifier intentionally uses only the Python standard library so it can run as a
lightweight post-deploy/scheduled smoke check. It validates semantic contracts and,
when an expected local file is supplied, compares only the four general-contractor
company blocks so unrelated company updates do not cause false positives.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REQUIRED_COMPANIES = {
    "gs-ec": "GS건설",
    "samsung-ct-construction": "삼성물산 건설부문",
    "dl-enc": "DL이앤씨",
    "hyundai-engineering": "현대엔지니어링",
}
REQUIRED_YEARS = {2023, 2024, 2025}
REQUIRED_HEALTH_KEYS = {
    "cash_generation",
    "profitability",
    "leverage",
    "working_capital",
    "receivables_burden",
}
WORKING_CAPITAL_RULE_ID = "current_ratio_liquidity_observation"
WORKING_CAPITAL_THRESHOLD = 100
RECEIVABLES_RULE_ID = "receivables_to_revenue_observation"
RECEIVABLES_THRESHOLD = 30
DEFAULT_PRODUCTION_URL = (
    "https://modularhub-public.vercel.app/data/companies/company_report_insights.json"
)


def _companies(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = payload.get("companies")
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("company_id")): row
        for row in rows
        if isinstance(row, dict) and row.get("company_id")
    }


def validate_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    companies = _companies(payload)

    for company_id, company_name in REQUIRED_COMPANIES.items():
        company = companies.get(company_id)
        if not company:
            errors.append(f"{company_id}: company View Model missing")
            continue

        if company.get("company_name") != company_name:
            errors.append(
                f"{company_id}: company_name mismatch: {company.get('company_name')!r}"
            )

        years = {int(year) for year in company.get("available_years", []) if str(year).isdigit()}
        missing_years = sorted(REQUIRED_YEARS - years)
        if missing_years:
            errors.append(f"{company_id}: missing years {missing_years}")

        if company.get("source_schema_version") != "company_audit_financials_v1":
            errors.append(
                f"{company_id}: source_schema_version is not company_audit_financials_v1"
            )

        comparison = company.get("comparison_context") or {}
        if comparison.get("company_type") != "general_contractor":
            errors.append(f"{company_id}: company_type is not general_contractor")

        health = company.get("financial_health") or {}
        missing_health = sorted(REQUIRED_HEALTH_KEYS - set(health))
        if missing_health:
            errors.append(f"{company_id}: missing financial_health keys {missing_health}")
            continue

        working_capital = health.get("working_capital") or {}
        if working_capital.get("rule_id") != WORKING_CAPITAL_RULE_ID:
            errors.append(
                f"{company_id}: working_capital rule_id={working_capital.get('rule_id')!r}"
            )
        if working_capital.get("threshold") != WORKING_CAPITAL_THRESHOLD:
            errors.append(
                f"{company_id}: working_capital threshold={working_capital.get('threshold')!r}"
            )
        working_metric_ids = set(working_capital.get("metric_ids") or [])
        if not {"current_assets", "current_liabilities", "current_ratio_pct"}.issubset(
            working_metric_ids
        ):
            errors.append(
                f"{company_id}: working_capital does not use current assets/liabilities/current ratio"
            )

        receivables = health.get("receivables_burden") or {}
        if receivables.get("rule_id") != RECEIVABLES_RULE_ID:
            errors.append(
                f"{company_id}: receivables_burden rule_id={receivables.get('rule_id')!r}"
            )
        if receivables.get("threshold") != RECEIVABLES_THRESHOLD:
            errors.append(
                f"{company_id}: receivables_burden threshold={receivables.get('threshold')!r}"
            )

        latest_year = str(company.get("latest_year") or max(years or {0}))
        latest_derived = (company.get("derived_metrics") or {}).get(latest_year) or {}
        current_ratio = latest_derived.get("current_ratio_pct") or {}
        if current_ratio.get("value") is None:
            errors.append(f"{company_id}: latest current_ratio_pct is unavailable")

    return errors


def contractor_subset(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    companies = _companies(payload)
    return {
        company_id: companies[company_id]
        for company_id in REQUIRED_COMPANIES
        if company_id in companies
    }


def compare_contractor_blocks(
    actual: dict[str, Any], expected: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    actual_subset = contractor_subset(actual)
    expected_subset = contractor_subset(expected)

    for company_id in REQUIRED_COMPANIES:
        if company_id not in expected_subset:
            errors.append(f"expected file missing {company_id}")
            continue
        if company_id not in actual_subset:
            errors.append(f"production missing {company_id}")
            continue
        if actual_subset[company_id] != expected_subset[company_id]:
            errors.append(f"production drift detected for {company_id}")

    return errors


def load_json_file(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def fetch_json(url: str, timeout: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "modularhub-production-coverage/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} from {url}")
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {url}")
    return payload


def verify_once(
    payload: dict[str, Any], expected: dict[str, Any] | None = None
) -> list[str]:
    errors = validate_payload(payload)
    if expected is not None:
        errors.extend(compare_contractor_blocks(payload, expected))
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", help="Local company_report_insights.json path")
    source.add_argument("--url", help="Production company_report_insights.json URL")
    parser.add_argument(
        "--expected-file",
        help="Optional local JSON whose four contractor blocks must match production",
    )
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--retry-delay", type=int, default=15)
    parser.add_argument("--timeout", type=int, default=30)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    expected = load_json_file(args.expected_file) if args.expected_file else None
    attempts = max(1, args.retries)

    for attempt in range(1, attempts + 1):
        try:
            payload = (
                load_json_file(args.file)
                if args.file
                else fetch_json(args.url or DEFAULT_PRODUCTION_URL, timeout=args.timeout)
            )
            errors = verify_once(payload, expected)
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError, urllib.error.URLError) as exc:
            errors = [f"fetch/parse failure: {exc}"]

        if not errors:
            source_label = args.file or args.url
            print(f"PASS: general-contractor financial coverage verified: {source_label}")
            for company_id in REQUIRED_COMPANIES:
                print(f"  - {company_id}: PASS")
            return 0

        print(f"Attempt {attempt}/{attempts} failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)

        if attempt < attempts:
            time.sleep(max(0, args.retry_delay))

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
