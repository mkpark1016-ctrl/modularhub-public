from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSIGHTS = ROOT / "frontend" / "public" / "data" / "companies" / "company_report_insights.json"


def companies() -> dict[str, dict]:
    payload = json.loads(INSIGHTS.read_text(encoding="utf-8"))
    return {row["company_id"]: row for row in payload["companies"]}


def test_working_capital_health_uses_current_ratio_not_receivables_ratio() -> None:
    for company in companies().values():
        health = company["financial_health"]
        working = health["working_capital"]
        latest_ratio = company["derived_metrics"][str(company["latest_year"])]["current_ratio_pct"]["value"]
        assert working["rule_id"] == "current_ratio_liquidity_observation"
        assert working["operator"] == "<"
        assert working["threshold"] == 100
        assert working["actual_value"] == latest_ratio
        assert working["metric_ids"] == ["current_assets", "current_liabilities", "current_ratio_pct"]


def test_receivables_burden_remains_a_separate_auxiliary_observation() -> None:
    for company in companies().values():
        burden = company["financial_health"]["receivables_burden"]
        latest_ratio = company["derived_metrics"][str(company["latest_year"])]["receivables_to_revenue_pct"]["value"]
        assert burden["rule_id"] == "receivables_to_revenue_observation"
        assert burden["operator"] == ">"
        assert burden["threshold"] == 30
        assert burden["actual_value"] == latest_ratio
        assert burden["metric_ids"] == ["receivables_total", "receivables_to_revenue_pct"]


def test_gs_working_capital_is_available_even_when_receivables_remain_pending() -> None:
    gs = companies()["gs-ec"]
    assert gs["financial_health"]["working_capital"]["status"] in {"info", "watch"}
    assert gs["financial_health"]["receivables_burden"]["status"] == "additional_confirmation_required"
    assert gs["derived_metrics"]["2025"]["current_ratio_pct"]["value"] is not None
    assert gs["derived_metrics"]["2025"]["receivables_to_revenue_pct"]["value"] is None


def test_hyundai_reconciled_receivables_enable_auxiliary_burden_ratio() -> None:
    hyundai = companies()["hyundai-engineering"]
    burden = hyundai["financial_health"]["receivables_burden"]
    assert burden["status"] == "info"
    assert burden["actual_value"] == 28.7
