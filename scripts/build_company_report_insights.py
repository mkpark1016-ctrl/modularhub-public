#!/usr/bin/env python3
"""Build public company audit financial insight view models."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal, ROUND_HALF_UP
from statistics import median
from pathlib import Path
from typing import Any

try:
    from validate_company_audit_financials import calculate_derived_metrics, load_payload, validate
except ModuleNotFoundError:
    from scripts.validate_company_audit_financials import calculate_derived_metrics, load_payload, validate

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_ROOT = ROOT / "data" / "company_reports"
DEFAULT_OUTPUT = ROOT / "frontend" / "public" / "data" / "companies" / "company_report_insights.json"
DEFAULT_COMPANY_MASTER = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"
SCHEMA_VERSION = "company_report_insights_v1"
SOURCE_SCHEMA_VERSION = "company_audit_financials_v1"
COMPARISON_GROUPS = {
    "general_contractor": {
        "group_id": "general_contractor",
        "label": "건설사",
        "company_types": ["general_contractor"],
    },
    "modular_specialist": {
        "group_id": "modular_specialist",
        "label": "모듈러 제작 전문 업체",
        "company_types": ["specialist_manufacturer", "modular_integrator", "modular_specialist", "producer_group"],
    },
}
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
REVENUE_BREAKDOWN_METRIC_FIELDS = [
    "goods_revenue",
    "product_revenue",
    "rental_revenue",
    "service_revenue",
    "construction_revenue",
    "other_revenue",
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
OPTIONAL_DERIVED_METRIC_FIELDS = [
    "service_revenue_share_pct",
]
LATEST_SNAPSHOT_FIELDS = [
    "revenue",
    "operating_profit",
    "net_income",
    "operating_cash_flow",
    "total_borrowings",
    "receivables_total",
    "total_assets",
    "total_liabilities",
    "total_equity",
]
PEER_BENCHMARK_METRICS = [
    {"metric_id": "revenue", "source": "latest_metrics", "comparison_direction": "higher_is_larger"},
    {"metric_id": "operating_margin_pct", "source": "derived_metrics", "comparison_direction": "higher_is_larger"},
    {"metric_id": "operating_cash_flow", "source": "latest_metrics", "comparison_direction": "higher_is_larger"},
    {"metric_id": "total_borrowings", "source": "latest_metrics", "comparison_direction": "lower_is_lower_burden"},
    {"metric_id": "liabilities_to_equity_pct", "source": "derived_metrics", "comparison_direction": "lower_is_lower_burden"},
    {"metric_id": "receivables_to_revenue_pct", "source": "derived_metrics", "comparison_direction": "lower_is_lower_burden"},
]


def stable_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def comparison_group_for_company_type(company_type: str | None) -> dict[str, Any] | None:
    for group in COMPARISON_GROUPS.values():
        if company_type in group["company_types"]:
            return group
    return None


def load_company_comparison_groups(path: Path = DEFAULT_COMPANY_MASTER) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("companies") if isinstance(payload, dict) else payload
    mapping: dict[str, dict[str, Any]] = {}
    for company in rows:
        company_id = company.get("company_id")
        if not company_id:
            continue
        group = comparison_group_for_company_type(company.get("company_type"))
        mapping[company_id] = {
            "company_type": company.get("company_type"),
            "group_id": group["group_id"] if group else None,
            "group_label": group["label"] if group else None,
        }
    return mapping


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
        elif disclosure_status == "verification_pending":
            display_text = "검증 보류"
            calculation_basis = "verification_pending"
        else:
            raise ValueError("raw_krw=None requires disclosure_status not_disclosed, not_applicable, or verification_pending")
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
    has_verification_pending = False
    has_not_disclosed = False
    for part in parts:
        value = part.get("reported")
        status = part.get("disclosure_status")
        if value is None:
            if status == "not_applicable":
                continue
            if status == "verification_pending":
                has_verification_pending = True
                continue
            has_not_disclosed = True
            continue
        total += int(value)
        included_count += 1

    if has_verification_pending:
        return {"reported": None, "disclosure_status": "verification_pending"}
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
    for field in REVENUE_BREAKDOWN_METRIC_FIELDS:
        if field in record.get("revenue_breakdown", {}):
            mapping[field] = metric_from_reported(record, "revenue_breakdown", field)
    return {field: mapping[field] for field in fields if field in mapping}


def derived_metric(value: str | int | None, suffix: str = "%") -> dict[str, Any]:
    if value is None:
        return {"value": None, "display_text": "확인되지 않음", "calculation_basis": "derived_from_reported"}
    numeric = float(value)
    return {"value": numeric, "display_text": f"{numeric:,.1f}{suffix}", "calculation_basis": "derived_from_reported"}


def build_derived_metrics(source_payload: dict[str, Any]) -> dict[str, Any]:
    calculated = calculate_derived_metrics(source_payload)
    derived_fields = list(DERIVED_METRIC_FIELDS)
    if any(calculated[year].get(field) is not None for year in calculated for field in OPTIONAL_DERIVED_METRIC_FIELDS):
        derived_fields.extend(OPTIONAL_DERIVED_METRIC_FIELDS)
    output: dict[str, Any] = {}
    for year in sorted(calculated):
        output[year] = {field: derived_metric(calculated[year].get(field), "" if field == "operating_cash_flow_to_net_income" else "%") for field in derived_fields}
    return output


def direction_code(current: int | None, previous: int | None, metric: str) -> str:
    if current is None or previous is None:
        return f"{metric}_unknown"
    if current > previous:
        return f"{metric}_increased"
    if current < previous:
        return f"{metric}_decreased"
    return f"{metric}_flat"


def direction_phrase_ko(code: str) -> str:
    if code.endswith("increased"):
        return "증가했다"
    if code.endswith("decreased"):
        return "감소했다"
    if code.endswith("flat"):
        return "유지했다"
    return "확인되지 않았다"


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
            f"{years[0]}년 대비 {latest_year}년 매출액이 {direction_phrase_ko(revenue_code)}.",
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
            f"{previous_year}년 대비 {latest_year}년 총차입금이 {direction_phrase_ko(borrowing_code)}.",
            [previous_year, latest_year],
            {"previous_raw_krw": previous["total_borrowings"]["raw_krw"], "latest_raw_krw": latest["total_borrowings"]["raw_krw"]},
        ),
        trend_signal(
            receivables_code,
            "매출채권 방향",
            f"{previous_year}년 대비 {latest_year}년 매출채권 합계가 {direction_phrase_ko(receivables_code)}.",
            [previous_year, latest_year],
            {"previous_raw_krw": previous["receivables_total"]["raw_krw"], "latest_raw_krw": latest["receivables_total"]["raw_krw"]},
        ),
        trend_signal(
            inventory_code,
            "재고 방향",
            f"{previous_year}년 대비 {latest_year}년 재고자산이 {direction_phrase_ko(inventory_code)}.",
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
    for year, record in sorted(source_payload["financial_years"].items()):
        total_equity = record.get("balance_sheet", {}).get("total_equity", {})
        if total_equity.get("disclosure_status") == "verification_pending":
            warnings.append({
                "code": "verification_pending_total_equity",
                "message": f"{year}년 자본총계 검증 보류: 해당 자본 관련 비율은 계산에서 제외됩니다.",
                "level": "info",
            })
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
        **({"disclosure_limitations": list(source_payload.get("disclosure_limitations") or [])} if any(opinion.get("opinion") != "unqualified" for opinion in source_payload.get("audit_opinions") or []) else {}),
        "auditors": sorted({doc["auditor"] for doc in source_documents.values()}),
        "verified_location_count": sum(1 for item in locations if item["verification_status"] in {"verified", "verified_section_range"}),
        "pending_location_count": sum(1 for item in locations if item["verification_status"] == "pending_manual_page_check"),
        "latest_report_date": max(doc["report_date"] for doc in source_documents.values()),
    }


def metric_raw(metric: dict[str, Any] | None) -> int | float | None:
    if not metric:
        return None
    if metric.get("raw_krw") is not None:
        return int(metric["raw_krw"])
    if metric.get("value") is not None:
        return float(metric["value"])
    return None


def metric_source_refs(metric: dict[str, Any] | None) -> list[str]:
    return sorted(set(metric.get("source_refs") or [])) if metric else []


def metric_status(metric: dict[str, Any] | None) -> str:
    if not metric:
        return "unavailable"
    if metric.get("raw_krw") is not None or metric.get("value") is not None:
        return "reported"
    return metric.get("disclosure_status") or "unavailable"


def percent_change(current: int | float | None, previous: int | float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return float(((Decimal(str(current)) - Decimal(str(previous))) / abs(Decimal(str(previous))) * Decimal(100)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def value_change(current: int | float | None, previous: int | float | None) -> int | float | None:
    if current is None or previous is None:
        return None
    return current - previous


def direction(current: int | float | None, previous: int | float | None) -> str:
    if current is None or previous is None:
        return "unknown"
    if current > previous:
        return "increased"
    if current < previous:
        return "decreased"
    return "flat"


def change_pct_unavailable_reason(current: int | float | None, previous: int | float | None) -> str | None:
    if current is None or previous is None:
        return "최신 연도 또는 직전 연도 값이 없어 변화율을 계산하지 않습니다."
    if previous == 0:
        return "직전 연도 값이 0이라 변화율을 계산하지 않습니다."
    return None


def metric_display(metric: dict[str, Any] | None) -> str:
    return metric.get("display_text", "확인되지 않음") if metric else "확인되지 않음"


def change_display(metric_id: str, change: int | float | None) -> str:
    if change is None:
        return "계산되지 않음"
    if metric_id.endswith("_pct"):
        return f"{float(change):+.1f}%p"
    eok = Decimal(str(change)) / Decimal(100_000_000)
    rounded = eok.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{rounded:+,.1f}억원"


def trend_item(
    key: str,
    label: str,
    latest_year: int,
    previous_year: int,
    current: dict[str, Any] | None,
    previous: dict[str, Any] | None,
    explanation: str,
) -> dict[str, Any]:
    current_value = metric_raw(current)
    previous_value = metric_raw(previous)
    change = value_change(current_value, previous_value)
    return {
        "status": "additional_confirmation_required" if current_value is None or previous_value is None else direction(current_value, previous_value),
        "headline": label,
        "explanation": explanation,
        "latest_year": latest_year,
        "previous_year": previous_year,
        "latest_display": metric_display(current),
        "previous_display": metric_display(previous),
        "change_value": change,
        "change_display": change_display(key, change),
        "change_pct": percent_change(current_value, previous_value),
        "change_pct_unavailable_reason": change_pct_unavailable_reason(current_value, previous_value),
        "metric_ids": [key],
        "source_ids": sorted(set(metric_source_refs(current) + metric_source_refs(previous))),
        "calculation_basis": "latest_year_vs_previous_year",
    }


def build_latest_snapshot(latest_year: int, latest_metrics: dict[str, Any], derived: dict[str, Any]) -> dict[str, Any]:
    snapshot = {"latest_year": latest_year}
    for key in LATEST_SNAPSHOT_FIELDS:
        target_key = "trade_receivables" if key == "receivables_total" else key
        if key in latest_metrics:
            snapshot[target_key] = latest_metrics[key]
    if "operating_margin_pct" in derived[str(latest_year)]:
        snapshot["operating_margin_pct"] = derived[str(latest_year)]["operating_margin_pct"]
    return snapshot


def build_decision_trends(years: list[int], series: list[dict[str, Any]], derived: dict[str, Any]) -> dict[str, Any]:
    latest_year = years[-1]
    previous_year = years[-2] if len(years) > 1 else years[-1]
    latest = series[-1]["metrics"]
    previous = series[-2]["metrics"] if len(series) > 1 else {}
    latest_derived = derived[str(latest_year)]
    previous_derived = derived[str(previous_year)] if previous_year != latest_year else {}
    return {
        "revenue": trend_item("revenue", "매출 변화", latest_year, previous_year, latest.get("revenue"), previous.get("revenue"), "최근 연도 매출을 직전 연도와 비교합니다."),
        "operating_profit": trend_item("operating_profit", "영업이익 변화", latest_year, previous_year, latest.get("operating_profit"), previous.get("operating_profit"), "영업이익의 금액 변화만 표시하며 수익성 판단은 영업이익률과 함께 봅니다."),
        "operating_margin": trend_item("operating_margin_pct", "영업이익률 변화", latest_year, previous_year, latest_derived.get("operating_margin_pct"), previous_derived.get("operating_margin_pct"), "영업이익률의 전년 대비 변화폭을 확인합니다."),
        "operating_cash_flow": trend_item("operating_cash_flow", "영업현금흐름 변화", latest_year, previous_year, latest.get("operating_cash_flow"), previous.get("operating_cash_flow"), "회계상 이익이 현금창출로 이어지는지 확인합니다."),
        "total_borrowings": trend_item("total_borrowings", "총차입금 변화", latest_year, previous_year, latest.get("total_borrowings"), previous.get("total_borrowings"), "차입금 부담의 방향만 표시하며 부실 판단은 하지 않습니다."),
        "trade_receivables": trend_item("receivables_total", "채권 변화", latest_year, previous_year, latest.get("receivables_total"), previous.get("receivables_total"), "채권 증가 속도를 매출 변화와 함께 관찰합니다."),
        "liabilities_to_equity": trend_item("liabilities_to_equity_pct", "부채비율 변화", latest_year, previous_year, latest_derived.get("liabilities_to_equity_pct"), previous_derived.get("liabilities_to_equity_pct"), "총부채와 자본의 비율 변화를 확인합니다."),
    }


def health_item(
    status: str,
    headline: str,
    explanation: str,
    metric_ids: list[str],
    source_ids: list[str],
    *,
    rule_id: str,
    operator: str,
    threshold: int | float | None,
    actual_value: int | float | None,
    interpretation_scope: str,
    limitation: str | None = None,
) -> dict[str, Any]:
    item = {
        "status": status,
        "headline": headline,
        "explanation": explanation,
        "metric_ids": metric_ids,
        "source_ids": sorted(set(source_ids)),
        "calculation_basis": "rule_based_from_reported_metrics",
        "rule_id": rule_id,
        "operator": operator,
        "threshold": threshold,
        "actual_value": actual_value,
        "interpretation_scope": interpretation_scope,
    }
    if limitation:
        item["limitation"] = limitation
    return item


def build_financial_health(latest_year: int, latest_metrics: dict[str, Any], derived: dict[str, Any], source_summary: dict[str, Any], attribution: dict[str, Any]) -> dict[str, Any]:
    latest_derived = derived[str(latest_year)]
    revenue = latest_metrics.get("revenue")
    operating_profit = latest_metrics.get("operating_profit")
    operating_margin = latest_derived.get("operating_margin_pct")
    operating_cash_flow = latest_metrics.get("operating_cash_flow")
    borrowings = latest_metrics.get("total_borrowings")
    receivables = latest_metrics.get("receivables_total")
    receivables_ratio = latest_derived.get("receivables_to_revenue_pct")
    liabilities_ratio = latest_derived.get("liabilities_to_equity_pct")
    source_ids = metric_source_refs(revenue) + metric_source_refs(operating_profit)
    profitability_status = "additional_confirmation_required" if metric_raw(operating_margin) is None else "watch" if metric_raw(operating_margin) < 0 else "info"
    cash_status = "additional_confirmation_required" if metric_raw(operating_cash_flow) is None else "watch" if metric_raw(operating_cash_flow) < 0 and metric_raw(operating_profit) and metric_raw(operating_profit) > 0 else "info"
    leverage_status = "additional_confirmation_required" if metric_raw(liabilities_ratio) is None else "watch" if metric_raw(liabilities_ratio) > 200 else "info"
    working_capital_status = "additional_confirmation_required" if metric_raw(receivables_ratio) is None else "watch" if metric_raw(receivables_ratio) > 30 else "info"
    coverage_status = "watch" if source_summary.get("pending_location_count") else "info"
    return {
        "profitability": health_item(
            profitability_status,
            "수익성",
            f"{latest_year}년 영업이익률은 {operating_margin.get('display_text') if operating_margin else '확인되지 않음'}입니다.",
            ["revenue", "operating_profit", "operating_margin_pct"],
            source_ids,
            rule_id="profitability_negative_margin",
            operator="<",
            threshold=0,
            actual_value=metric_raw(operating_margin),
            interpretation_scope="영업이익률이 0% 미만인지 확인하는 관찰 규칙이며 신용등급이나 투자 판단이 아닙니다.",
        ),
        "cash_generation": health_item(
            cash_status,
            "현금창출력",
            f"{latest_year}년 영업현금흐름은 {operating_cash_flow.get('display_text') if operating_cash_flow else '확인되지 않음'}입니다.",
            ["operating_profit", "operating_cash_flow"],
            metric_source_refs(operating_cash_flow) + metric_source_refs(operating_profit),
            rule_id="positive_profit_negative_operating_cash_flow",
            operator="operating_profit > 0 and operating_cash_flow <",
            threshold=0,
            actual_value=metric_raw(operating_cash_flow),
            interpretation_scope="이익과 영업현금흐름 방향이 엇갈리는지 확인하는 관찰 규칙입니다.",
        ),
        "leverage": health_item(
            leverage_status,
            "재무안정성",
            f"{latest_year}년 총차입금은 {borrowings.get('display_text') if borrowings else '확인되지 않음'}이고 부채비율은 {liabilities_ratio.get('display_text') if liabilities_ratio else '확인되지 않음'}입니다.",
            ["total_borrowings", "liabilities_to_equity_pct"],
            metric_source_refs(borrowings),
            rule_id="liabilities_to_equity_observation",
            operator=">",
            threshold=200,
            actual_value=metric_raw(liabilities_ratio),
            interpretation_scope="부채비율이 관찰 기준을 넘는지 표시하며 부실 판단을 의미하지 않습니다.",
        ),
        "working_capital": health_item(
            working_capital_status,
            "운전자본",
            f"{latest_year}년 채권/매출 비율은 {receivables_ratio.get('display_text') if receivables_ratio else '확인되지 않음'}입니다.",
            ["receivables_total", "receivables_to_revenue_pct"],
            metric_source_refs(receivables),
            rule_id="receivables_to_revenue_observation",
            operator=">",
            threshold=30,
            actual_value=metric_raw(receivables_ratio),
            interpretation_scope="채권/매출 비율이 관찰 기준을 넘는지 표시하며 회수 위험을 단정하지 않습니다.",
            limitation="채권은 감사보고서 주석의 매출채권과 공사미수금 등 공개 항목 합계입니다.",
        ),
        "disclosure_coverage": health_item(
            coverage_status,
            "공시 범위",
            f"검증된 출처 위치 {source_summary.get('verified_location_count', 0)}건, 수동 확인 필요 {source_summary.get('pending_location_count', 0)}건입니다.",
            ["source_locations"],
            [],
            rule_id="source_location_coverage_observation",
            operator="pending_location_count >",
            threshold=0,
            actual_value=source_summary.get("pending_location_count", 0),
            interpretation_scope="수동 출처 위치 확인이 남아 있는지 표시하는 공시 범위 관찰 규칙입니다.",
            limitation=None if attribution.get("modular_segment_revenue_disclosed") else "모듈러 부문 별도 매출은 공시되지 않았습니다.",
        ),
    }


def financial_metric_status_counts(source_payload: dict[str, Any]) -> dict[str, int]:
    counts = {
        "not_disclosed": 0,
        "not_applicable": 0,
        "verification_pending": 0,
    }
    for record in source_payload["financial_years"].values():
        for section in ["metrics", "revenue_breakdown"]:
            for metric in record.get(section, {}).values():
                status = metric.get("disclosure_status")
                if metric.get("reported") is None and status in counts:
                    counts[status] += 1
    return counts


def location_verification_counts(locations: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "verified": 0,
        "verified_section_range": 0,
        "pending_manual_page_check": 0,
    }
    for location in locations:
        status = location.get("verification_status")
        if status in counts:
            counts[status] += 1
    return counts


def build_evidence_health(source_payload: dict[str, Any], source_summary: dict[str, Any], locations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    financial_source_refs = sorted({location["source_ref"] for location in locations if location.get("source_ref")})
    latest_verified_at = source_summary.get("latest_report_date")
    location_counts = location_verification_counts(locations)
    metric_counts = financial_metric_status_counts(source_payload)
    pending_count = int(location_counts["pending_manual_page_check"])
    verified_count = int(location_counts["verified"] + location_counts["verified_section_range"])
    modular_disclosed = source_payload["entity_attribution"].get("modular_segment_revenue_disclosed")
    return [
        {
            "domain": "financial",
            "distinct_source_count": len(financial_source_refs),
            "verified_item_count": verified_count,
            "pending_item_count": pending_count,
            "not_disclosed_item_count": metric_counts["not_disclosed"],
            "not_applicable_item_count": metric_counts["not_applicable"],
            "verification_pending_item_count": metric_counts["verification_pending"],
            "unavailable_item_count": metric_counts["not_disclosed"] + metric_counts["not_applicable"] + metric_counts["verification_pending"],
            "source_count": len(financial_source_refs),
            "latest_verified_at": latest_verified_at,
            "verification_status": "pending_manual_page_check" if pending_count else "verified",
            "source_ids": financial_source_refs,
            "source_type_counts": {"audit_report": len(financial_source_refs)},
        },
        {
            "domain": "disclosure_scope",
            "distinct_source_count": len(financial_source_refs),
            "verified_item_count": 1 if modular_disclosed else 0,
            "pending_item_count": 0,
            "not_disclosed_item_count": 0 if modular_disclosed else 1,
            "not_applicable_item_count": 0,
            "verification_pending_item_count": 0,
            "unavailable_item_count": 0 if modular_disclosed else 1,
            "source_count": len(financial_source_refs),
            "latest_verified_at": latest_verified_at,
            "verification_status": "verified" if modular_disclosed else "not_disclosed",
            "source_ids": financial_source_refs,
            "source_type_counts": {"audit_report": len(financial_source_refs)},
        },
    ]


def comparable_metric_value(company: dict[str, Any], metric_id: str, source: str) -> float | None:
    if source == "latest_metrics":
        return metric_raw(company.get("latest_metrics", {}).get(metric_id))
    if source == "derived_metrics":
        latest_year = company.get("latest_year")
        return metric_raw(company.get("derived_metrics", {}).get(str(latest_year), {}).get(metric_id))
    return None


def comparable_metric(company: dict[str, Any], metric_id: str, source: str) -> dict[str, Any] | None:
    if source == "latest_metrics":
        return company.get("latest_metrics", {}).get(metric_id)
    if source == "derived_metrics":
        latest_year = company.get("latest_year")
        return company.get("derived_metrics", {}).get(str(latest_year), {}).get(metric_id)
    return None


def metric_display_for_peer(company: dict[str, Any], metric_id: str, source: str) -> str:
    if source == "latest_metrics":
        return company.get("latest_metrics", {}).get(metric_id, {}).get("display_text", "확인되지 않음")
    latest_year = company.get("latest_year")
    return company.get("derived_metrics", {}).get(str(latest_year), {}).get(metric_id, {}).get("display_text", "확인되지 않음")


def peer_value_display(value: int | float | None, source: str) -> str:
    if value is None:
        return "확인되지 않음"
    if source == "derived_metrics":
        return f"{float(value):,.1f}%"
    eok = Decimal(str(value)) / Decimal(100_000_000)
    return f"{eok.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):,.1f}억원"


def benchmark_difference_display(company_value: int | float | None, median_value: int | float | None, source: str) -> str | None:
    if company_value is None or median_value is None:
        return None
    difference = float(company_value) - float(median_value)
    if difference == 0:
        return "중앙값과 같음"
    direction = "높음" if difference > 0 else "낮음"
    if source == "derived_metrics":
        return f"중앙값보다 {abs(difference):,.1f}%p {direction}"
    eok = Decimal(str(abs(difference))) / Decimal(100_000_000)
    return f"중앙값보다 {eok.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):,.1f}억원 {direction}"


def build_peer_benchmarks(companies: list[dict[str, Any]]) -> None:
    for company in companies:
        benchmarks = []
        company_context = company.get("comparison_context", {})
        comparison_group_id = company_context.get("group_id")
        for config in PEER_BENCHMARK_METRICS:
            metric_id = config["metric_id"]
            source = config["source"]
            scoped_peers = [
                peer for peer in companies
                if comparison_group_id is not None
                and peer.get("comparison_context", {}).get("group_id") == comparison_group_id
                and peer.get("latest_year") == company.get("latest_year")
                and peer.get("currency") == company.get("currency")
                and peer.get("financial_scope") == company.get("financial_scope")
                and comparable_metric_value(peer, metric_id, source) is not None
            ]
            value = comparable_metric_value(company, metric_id, source)
            comparable = value is not None and len(scoped_peers) >= 3
            if comparable:
                reverse = config["comparison_direction"] == "higher_is_larger"
                ordered = sorted(scoped_peers, key=lambda item: comparable_metric_value(item, metric_id, source), reverse=reverse)
                rank = [peer["company_id"] for peer in ordered].index(company["company_id"]) + 1
                values = [comparable_metric_value(peer, metric_id, source) for peer in scoped_peers]
                best_value = comparable_metric_value(ordered[0], metric_id, source)
                median_value = float(median(values))
                comparison_label = f"{len(scoped_peers)}개 중 {rank}위"
                reason = None
            else:
                rank = None
                best_value = None
                median_value = None
                comparison_label = "동일 유형 재무 비교 준비 중"
                if value is None:
                    reason = "현재 기업의 해당 지표값이 확인되지 않았습니다."
                elif comparison_group_id is None:
                    reason = "canonical 기업유형이 자동 재무 비교 그룹에 포함되지 않습니다."
                else:
                    reason = "같은 기업유형의 비교 가능한 감사재무가 3개 미만이라 상대 위치를 표시하지 않습니다."
            benchmarks.append({
                "metric_id": metric_id,
                "comparison_group_id": comparison_group_id,
                "comparison_group_label": company_context.get("group_label"),
                "comparison_year": company.get("latest_year"),
                "comparison_currency": company.get("currency"),
                "comparison_financial_scope": company.get("financial_scope"),
                "company_value": value,
                "company_display": metric_display_for_peer(company, metric_id, source),
                "peer_count": len(scoped_peers),
                "comparison_universe_count": len(scoped_peers),
                "other_peer_count": max(len(scoped_peers) - (1 if value is not None else 0), 0),
                "current_company_included": value is not None and any(peer["company_id"] == company["company_id"] for peer in scoped_peers),
                "rank": rank,
                "median": median_value,
                "median_display": peer_value_display(median_value, source),
                "median_difference_display": benchmark_difference_display(value, median_value, source),
                "best_value": best_value,
                "reference_value": best_value,
                "reference_value_display": peer_value_display(best_value, source),
                "reference_value_label": "비교 범위 최대값" if config["comparison_direction"] == "higher_is_larger" else "비교 범위 최소값",
                "comparison_direction": config["comparison_direction"],
                "comparison_label": comparison_label,
                "comparable": comparable,
                "not_comparable_reason": reason,
                "source_ids": metric_source_refs(comparable_metric(company, metric_id, source)),
                "calculation_basis": "same_company_group_latest_year_currency_financial_scope_minimum_three_values",
            })
        company["peer_benchmarks"] = benchmarks


def public_attribution(source_payload: dict[str, Any]) -> dict[str, Any]:
    attribution = dict(source_payload["entity_attribution"])
    attribution["special_events"] = [
        event
        for event in attribution.get("special_events", [])
        if event.get("event_type") != "unresolved_requested_amount_not_found"
    ]
    return attribution


def has_service_revenue(source_payload: dict[str, Any]) -> bool:
    return any("service_revenue" in record.get("revenue_breakdown", {}) for record in source_payload["financial_years"].values())


def build_company_insight(source_payload: dict[str, Any]) -> dict[str, Any]:
    years = sorted(int(year) for year in source_payload["financial_years"])
    series_fields = SERIES_METRIC_FIELDS + (REVENUE_BREAKDOWN_METRIC_FIELDS if has_service_revenue(source_payload) else [])
    financial_series = [
        {"year": year, "metrics": metric_map(source_payload["financial_years"][str(year)], series_fields)}
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
        "latest_snapshot": build_latest_snapshot(latest_year, latest_metrics, derived),
        "financial_series": financial_series,
        "derived_metrics": derived,
        "trends": build_decision_trends(years, financial_series, derived),
        "financial_health": build_financial_health(
            latest_year,
            latest_metrics,
            derived,
            source_summary,
            source_payload["entity_attribution"],
        ),
        "evidence_health": build_evidence_health(source_payload, source_summary, locations),
        "trend_signals": build_trend_signals(source_payload, financial_series, derived),
        "disclosure_warnings": build_disclosure_warnings(source_payload, source_summary["pending_location_count"]),
        "attribution": public_attribution(source_payload),
        "source_summary": source_summary,
        "data_quality": {
            "source_validator_status": "passed",
            "source_location_count": len(locations),
            "pending_manual_page_check_count": source_summary["pending_location_count"],
            "manual_page_check_required": source_summary["pending_location_count"] > 0,
            "modular_segment_revenue_disclosed": source_payload["entity_attribution"]["modular_segment_revenue_disclosed"],
        },
    }


def apply_comparison_context(company: dict[str, Any], group_map: dict[str, dict[str, Any]]) -> None:
    group = group_map.get(company["company_id"], {})
    company["comparison_context"] = {
        "company_type": group.get("company_type", "unknown"),
        "group_id": group.get("group_id"),
        "group_label": group.get("group_label"),
        "minimum_peer_count": 3,
        "calculation_basis": "canonical_company_type_same_latest_year_currency_financial_scope",
    }


def build_view_model(input_root: Path = DEFAULT_INPUT_ROOT, base_ref: str | None = "origin/main", company_master: Path = DEFAULT_COMPANY_MASTER) -> dict[str, Any]:
    group_map = load_company_comparison_groups(company_master)
    companies = []
    for path in discover_source_files(input_root):
        payload = load_payload(path)
        validation = validate(payload, base_ref=base_ref)
        if not validation["valid"]:
            raise ValueError(f"source validation failed for {path}: {validation['issues']}")
        insight = build_company_insight(payload)
        apply_comparison_context(insight, group_map)
        companies.append(insight)
    companies.sort(key=lambda item: item["company_id"])
    build_peer_benchmarks(companies)
    return {"schema_version": SCHEMA_VERSION, "companies": companies}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build public company report insight view models.")
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--company-master", type=Path, default=DEFAULT_COMPANY_MASTER)
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--check", action="store_true", help="Fail if the stored output differs from generated output.")
    args = parser.parse_args()

    payload = build_view_model(args.input_root, base_ref=args.base_ref, company_master=args.company_master)
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
