#!/usr/bin/env python3
"""Build public company audit financial insight view models."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

try:
    from validate_company_audit_financials import calculate_derived_metrics, load_payload, validate
except ModuleNotFoundError:
    from scripts.validate_company_audit_financials import calculate_derived_metrics, load_payload, validate

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_ROOT = ROOT / "data" / "company_reports"
DEFAULT_OUTPUT = ROOT / "frontend" / "public" / "data" / "companies" / "company_report_insights.json"
SCHEMA_VERSION = "company_report_insights_v1"
SOURCE_SCHEMA_VERSION = "company_audit_financials_v1"
LATEST_METRIC_FIELDS = [
    "revenue",
    "gross_profit",
    "operating_profit",
    "net_income",
    "operating_cash_flow",
    "total_assets",
    "total_liabilities",
    "total_equity",
    "total_borrowings",
    "receivables_total",
    "inventory",
    "work_in_progress",
]
SERIES_METRIC_FIELDS = [
    "revenue",
    "gross_profit",
    "operating_profit",
    "net_income",
    "operating_cash_flow",
    "total_borrowings",
    "receivables_total",
    "inventory",
    "current_assets",
    "current_liabilities",
    "total_assets",
    "total_liabilities",
    "total_equity",
]
DERIVED_METRIC_FIELDS = [
    "revenue_yoy_pct",
    "gross_margin_pct",
    "operating_margin_pct",
    "net_margin_pct",
    "current_ratio_pct",
    "liabilities_to_equity_pct",
    "borrowings_to_equity_pct",
    "receivables_to_revenue_pct",
    "inventory_to_revenue_pct",
    "operating_cash_flow_to_net_income",
    "goods_revenue_share_pct",
    "product_revenue_share_pct",
    "construction_revenue_share_pct",
    "rental_revenue_share_pct",
    "other_revenue_share_pct",
]


def stable_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def discover_source_files(input_root: Path = DEFAULT_INPUT_ROOT) -> list[Path]:
    files = sorted(input_root.glob("*/*.json"))
    return [path for path in files if (json.loads(path.read_text(encoding="utf-8")).get("schema_version") == SOURCE_SCHEMA_VERSION)]


def reported(record: dict[str, Any], section: str, field: str) -> dict[str, Any]:
    return record[section][field]


def raw_value(record: dict[str, Any], section: str, field: str) -> int | None:
    value = reported(record, section, field)["reported"]
    return None if value is None else int(value)


def display_eok(raw_krw: int) -> Decimal:
    return (Decimal(raw_krw) / Decimal(100000000)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def money_metric(raw_krw: int | None, source_refs: list[str], source_locations: list[dict[str, Any]], basis: str = "reported", disclosure_status: str | None = None) -> dict[str, Any]:
    if raw_krw is None:
        if disclosure_status == "not_applicable":
            display_text = "해당 없음"
            calculation_basis = "not_applicable"
        elif disclosure_status == "not_disclosed":
            display_text = "공시되지 않음"
            calculation_basis = "not_disclosed"
        else:
            raise ValueError("raw_krw=None requires disclosure_status not_disclosed or not_applicable")
        metric = {
            "raw_krw": None,
            "display_eok": None,
            "display_text": display_text,
            "source_refs": sorted(set(source_refs)),
            "source_locations": source_locations,
            "calculation_basis": calculation_basis,
            "disclosure_status": disclosure_status,
        }
        return metric
    eok = display_eok(raw_krw)
    metric = {
        "raw_krw": raw_krw,
        "display_eok": float(eok),
        "display_text": f"{eok:,.1f}억원",
        "source_refs": sorted(set(source_refs)),
        "source_locations": source_locations,
        "calculation_basis": basis,
    }
    if disclosure_status:
        metric["disclosure_status"] = disclosure_status
    return metric


def metric_from_reported(record: dict[str, Any], section: str, field: str) -> dict[str, Any]:
    source = reported(record, section, field)
    return money_metric(
        raw_krw=None if source["reported"] is None else int(source["reported"]),
        source_refs=list(source["source_refs"]),
        source_locations=list(source.get("source_locations") or []),
        disclosure_status=source.get("disclosure_status"),
    )


def combined_metric(raw_krw: int | None, parts: list[dict[str, Any]]) -> dict[str, Any]:
    refs: list[str] = []
    locations: list[dict[str, Any]] = []
    for part in parts:
        refs.extend(part.get("source_refs") or [])
        locations.extend(part.get("source_locations") or [])
    aggregate_status = aggregate_reported(parts)["disclosure_status"] if raw_krw is None else None
    return money_metric(raw_krw=raw_krw, source_refs=refs, source_locations=locations, basis="derived_from_reported", disclosure_status=aggregate_status)


def aggregate_reported(parts: list[dict[str, Any]]) -> dict[str, int | str | None]:
    total = 0
    included_count = 0
    has_not_disclosed = False
    for part in parts:
        value = part.get("reported")
        status = part.get("disclosure_status")
        if value is None:
            if status == "not_applicable":
                continue
            has_not_disclosed = True
            continue
        total += int(value)
        included_count += 1

    if has_not_disclosed:
        return {"reported": None, "disclosure_status": "not_disclosed"}
    if included_count == 0:
        return {"reported": None, "disclosure_status": "not_applicable"}
    return {"reported": total, "disclosure_status": "reported"}


def combined_raw(parts: list[dict[str, Any]]) -> int | None:
    aggregate = aggregate_reported(parts)
    return aggregate["reported"] if isinstance(aggregate["reported"], int) else None


def metric_map(record: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    borrowings = [
        record["borrowings"]["short_term_borrowings"],
        record["borrowings"]["current_portion_long_term_borrowings"],
        record["borrowings"]["long_term_borrowings"],
    ]
    receivables = [
        record["working_capital"]["trade_receivables_gross"],
        record["working_capital"]["construction_receivables_gross"],
    ]
    mapping = {
        "revenue": metric_from_reported(record, "income_statement", "revenue"),
        "gross_profit": metric_from_reported(record, "income_statement", "gross_profit"),
        "operating_profit": metric_from_reported(record, "income_statement", "operating_profit"),
        "net_income": metric_from_reported(record, "income_statement", "net_income"),
        "operating_cash_flow": metric_from_reported(record, "cash_flow", "operating_cash_flow"),
        "total_assets": metric_from_reported(record, "balance_sheet", "total_assets"),
        "total_liabilities": metric_from_reported(record, "balance_sheet", "total_liabilities"),
        "total_equity": metric_from_reported(record, "balance_sheet", "total_equity"),
        "current_assets": metric_from_reported(record, "balance_sheet", "current_assets"),
        "current_liabilities": metric_from_reported(record, "balance_sheet", "current_liabilities"),
        "inventory": metric_from_reported(record, "working_capital", "inventory"),
        "work_in_progress": metric_from_reported(record, "working_capital", "work_in_progress"),
        "total_borrowings": combined_metric(combined_raw(borrowings), borrowings),
        "receivables_total": combined_metric(combined_raw(receivables), receivables),
    }
    return {field: mapping[field] for field in fields}


def derived_metric(value: str | int | None, suffix: str = "%") -> dict[str, Any]:
    if value is None:
        return {"value": None, "display_text": "확인되지 않음", "calculation_basis": "derived_from_reported"}
    numeric = float(value)
    return {"value": numeric, "display_text": f"{numeric:,.1f}{suffix}", "calculation_basis": "derived_from_reported"}


def build_derived_metrics(source_payload: dict[str, Any]) -> dict[str, Any]:
    calculated = calculate_derived_metrics(source_payload)
    output: dict[str, Any] = {}
    for year in sorted(calculated):
        output[year] = {field: derived_metric(calculated[year].get(field), "" if field == "operating_cash_flow_to_net_income" else "%") for field in DERIVED_METRIC_FIELDS}
    return output


def direction_code(current: int, previous: int, metric: str) -> str:
    if current > previous:
        return f"{metric}_increased"
    if current < previous:
        return f"{metric}_decreased"
    return f"{metric}_flat"


def trend_signal(code: str, title: str, description: str, years: list[int], metric_values: dict[str, Any], level: str = "info") -> dict[str, Any]:
    return {
        "code": code,
        "level": level,
        "title": title,
        "description": description,
        "based_on_years": years,
        "metric_values": metric_values,
        "interpretation_type": "rule_based",
    }


def build_trend_signals(source_payload: dict[str, Any], series: list[dict[str, Any]], derived: dict[str, Any]) -> list[dict[str, Any]]:
    years = [item["year"] for item in series]
    first = series[0]["metrics"]
    previous = series[-2]["metrics"] if len(series) > 1 else series[0]["metrics"]
    latest = series[-1]["metrics"]
    latest_year = years[-1]
    previous_year = years[-2] if len(years) > 1 else years[0]
    latest_derived = derived[str(latest_year)]
    previous_derived = derived[str(previous_year)]
    revenue_code = direction_code(latest["revenue"]["raw_krw"], first["revenue"]["raw_krw"], "revenue")
    borrowing_code = direction_code(latest["total_borrowings"]["raw_krw"], previous["total_borrowings"]["raw_krw"], "borrowings")
    receivables_code = direction_code(latest["receivables_total"]["raw_krw"], previous["receivables_total"]["raw_krw"], "receivables")
    inventory_code = direction_code(latest["inventory"]["raw_krw"], previous["inventory"]["raw_krw"], "inventory")
    latest_ocf = latest["operating_cash_flow"]["raw_krw"]
    current_ratio = latest_derived["current_ratio_pct"]["value"]
    margin_delta = (latest_derived["operating_margin_pct"]["value"] or 0) - (previous_derived["operating_margin_pct"]["value"] or 0)
    return [
        trend_signal(
            revenue_code,
            "매출 방향",
            f"{years[0]}년 대비 {latest_year}년 매출액이 {'증가' if revenue_code.endswith('increased') else '감소' if revenue_code.endswith('decreased') else '유지'}했다.",
            [years[0], latest_year],
            {"start_raw_krw": first["revenue"]["raw_krw"], "latest_raw_krw": latest["revenue"]["raw_krw"]},
        ),
        trend_signal(
            "operating_margin_improved" if margin_delta > 0 else "operating_margin_declined" if margin_delta < 0 else "operating_margin_flat",
            "영업이익률 방향",
            f"{previous_year}년 대비 {latest_year}년 영업이익률이 {'개선' if margin_delta > 0 else '하락' if margin_delta < 0 else '유지'}됐다.",
            [previous_year, latest_year],
            {"previous_pct": previous_derived["operating_margin_pct"]["value"], "latest_pct": latest_derived["operating_margin_pct"]["value"]},
        ),
        trend_signal(
            "operating_cash_flow_positive" if latest_ocf > 0 else "operating_cash_flow_negative" if latest_ocf < 0 else "operating_cash_flow_zero",
            "영업현금흐름 상태",
            f"{latest_year}년 영업현금흐름은 {'양수' if latest_ocf > 0 else '음수' if latest_ocf < 0 else '0'}다.",
            [latest_year],
            {"latest_raw_krw": latest_ocf},
            "watch" if latest_ocf < 0 else "info",
        ),
        trend_signal(
            borrowing_code,
            "차입금 방향",
            f"{previous_year}년 대비 {latest_year}년 총차입금이 {'증가' if borrowing_code.endswith('increased') else '감소' if borrowing_code.endswith('decreased') else '유지'}했다.",
            [previous_year, latest_year],
            {"previous_raw_krw": previous["total_borrowings"]["raw_krw"], "latest_raw_krw": latest["total_borrowings"]["raw_krw"]},
        ),
        trend_signal(
            receivables_code,
            "매출채권 방향",
            f"{previous_year}년 대비 {latest_year}년 매출채권 합계가 {'증가' if receivables_code.endswith('increased') else '감소' if receivables_code.endswith('decreased') else '유지'}했다.",
            [previous_year, latest_year],
            {"previous_raw_krw": previous["receivables_total"]["raw_krw"], "latest_raw_krw": latest["receivables_total"]["raw_krw"]},
        ),
        trend_signal(
            inventory_code,
            "재고 방향",
            f"{previous_year}년 대비 {latest_year}년 재고자산이 {'증가' if inventory_code.endswith('increased') else '감소' if inventory_code.endswith('decreased') else '유지'}했다.",
            [previous_year, latest_year],
            {"previous_raw_krw": previous["inventory"]["raw_krw"], "latest_raw_krw": latest["inventory"]["raw_krw"]},
        ),
        trend_signal(
            "current_ratio_above_100" if (current_ratio or 0) >= 100 else "current_ratio_below_100",
            "유동비율 상태",
            f"{latest_year}년 유동비율은 {current_ratio:.1f}%다." if current_ratio is not None else "유동비율을 계산할 수 없다.",
            [latest_year],
            {"latest_pct": current_ratio},
            "watch" if current_ratio is not None and current_ratio < 100 else "info",
        ),
    ]


def all_source_locations(source_payload: dict[str, Any]) -> list[dict[str, Any]]:
    locations: list[dict[str, Any]] = []
    for record in source_payload["financial_years"].values():
        for section in ["income_statement", "balance_sheet", "cash_flow", "revenue_breakdown", "working_capital", "borrowings", "investment_signals"]:
            for value in record[section].values():
                locations.extend(value.get("source_locations") or [])
    return locations


def build_disclosure_warnings(source_payload: dict[str, Any], pending_location_count: int) -> list[dict[str, str]]:
    warnings = []
    if source_payload["entity_attribution"].get("modular_segment_revenue_disclosed") is False:
        warnings.append({"code": "modular_segment_revenue_not_disclosed", "message": "감사보고서에 모듈러 사업부문 별도 매출이 공시되지 않았다.", "level": "warning"})
    warnings.extend([
        {"code": "product_revenue_not_modular_revenue", "message": "제품매출을 모듈러 매출로 간주할 수 없다.", "level": "warning"},
        {"code": "construction_revenue_not_modular_revenue", "message": "공사매출을 모듈러 매출로 간주할 수 없다.", "level": "warning"},
        {"code": "related_entity_results_not_combined", "message": source_payload["entity_attribution"]["attribution_warning"], "level": "warning"},
    ])
    if pending_location_count:
        warnings.append({"code": "pending_manual_page_check", "message": f"주석 기반 수치 {pending_location_count}건은 정확한 페이지 수동 확인이 남아 있다.", "level": "info"})
    return warnings


def build_source_summary(source_payload: dict[str, Any], locations: list[dict[str, Any]]) -> dict[str, Any]:
    source_documents = source_payload["source_documents"]
    primary_refs = sorted({priority["primary_source_ref"] for priority in source_payload["source_priority"].values()})
    primary_documents = [
        {
            "source_ref": ref,
            "filename": source_documents[ref]["filename"],
            "report_date": source_documents[ref]["report_date"],
            "source_role": source_documents[ref]["source_role"],
        }
        for ref in primary_refs
    ]
    return {
        "primary_documents": primary_documents,
        "source_priority_by_year": source_payload["source_priority"],
        "audit_opinions": source_payload["audit_opinions"],
        "auditors": sorted({doc["auditor"] for doc in source_documents.values()}),
        "verified_location_count": sum(1 for item in locations if item["verification_status"] in {"verified", "verified_section_range"}),
        "pending_location_count": sum(1 for item in locations if item["verification_status"] == "pending_manual_page_check"),
        "latest_report_date": max(doc["report_date"] for doc in source_documents.values()),
    }


def build_company_insight(source_payload: dict[str, Any]) -> dict[str, Any]:
    years = sorted(int(year) for year in source_payload["financial_years"])
    financial_series = [
        {"year": year, "metrics": metric_map(source_payload["financial_years"][str(year)], SERIES_METRIC_FIELDS)}
        for year in years
    ]
    latest_year = years[-1]
    latest_metrics = metric_map(source_payload["financial_years"][str(latest_year)], LATEST_METRIC_FIELDS)
    derived = build_derived_metrics(source_payload)
    locations = all_source_locations(source_payload)
    source_summary = build_source_summary(source_payload, locations)
    return {
        "company_id": source_payload["company_id"],
        "company_name": source_payload["company_name"],
        "reporting_entity": source_payload["reporting_entity"],
        "financial_scope": source_payload["entity_attribution"]["financial_scope"],
        "currency": source_payload["currency"],
        "source_schema_version": source_payload["schema_version"],
        "available_years": years,
        "latest_year": latest_year,
        "latest_metrics": latest_metrics,
        "financial_series": financial_series,
        "derived_metrics": derived,
        "trend_signals": build_trend_signals(source_payload, financial_series, derived),
        "disclosure_warnings": build_disclosure_warnings(source_payload, source_summary["pending_location_count"]),
        "attribution": source_payload["entity_attribution"],
        "source_summary": source_summary,
        "data_quality": {
            "source_validator_status": "passed",
            "source_location_count": len(locations),
            "pending_manual_page_check_count": source_summary["pending_location_count"],
            "manual_page_check_required": source_summary["pending_location_count"] > 0,
            "modular_segment_revenue_disclosed": source_payload["entity_attribution"]["modular_segment_revenue_disclosed"],
        },
    }


def build_view_model(input_root: Path = DEFAULT_INPUT_ROOT, base_ref: str | None = "origin/main") -> dict[str, Any]:
    companies = []
    for path in discover_source_files(input_root):
        payload = load_payload(path)
        validation = validate(payload, base_ref=base_ref)
        if not validation["valid"]:
            raise ValueError(f"source validation failed for {path}: {validation['issues']}")
        companies.append(build_company_insight(payload))
    companies.sort(key=lambda item: item["company_id"])
    return {"schema_version": SCHEMA_VERSION, "companies": companies}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build public company report insight view models.")
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--check", action="store_true", help="Fail if the stored output differs from generated output.")
    args = parser.parse_args()

    payload = build_view_model(args.input_root, base_ref=args.base_ref)
    rendered = stable_json(payload)
    if args.check:
        existing = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if existing != rendered:
            raise SystemExit(f"{args.output} is not up to date")
        print(f"{args.output} is up to date")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"wrote {args.output} with {len(payload['companies'])} companies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
