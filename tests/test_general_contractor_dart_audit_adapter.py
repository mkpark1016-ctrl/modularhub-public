from __future__ import annotations

import json

import pytest

from src.company_dart_audit_adapter import (
    GENERAL_CONTRACTORS,
    TARGET_YEARS,
    build_audit_financial_candidate,
    map_structured_year,
)
from src.opendart_client import OpenDartClient
from scripts.validate_company_audit_financials import validate


def row(account_id: str, account_nm: str, sj_div: str, amount: int) -> dict[str, str]:
    return {
        "account_id": account_id,
        "account_nm": account_nm,
        "sj_div": sj_div,
        "thstrm_amount": str(amount),
        "currency": "KRW",
    }


def synthetic_cfs_rows(multiplier: int = 1) -> list[dict[str, str]]:
    return [
        row("ifrs-full_Revenue", "매출액", "IS", 1_000 * multiplier),
        row("ifrs-full_GrossProfit", "매출총이익", "IS", 200 * multiplier),
        row("dart_OperatingIncomeLoss", "영업이익", "IS", 100 * multiplier),
        row("ifrs-full_ProfitLoss", "당기순이익", "IS", 80 * multiplier),
        row("ifrs-full_Assets", "자산총계", "BS", 1_000 * multiplier),
        row("ifrs-full_Liabilities", "부채총계", "BS", 600 * multiplier),
        row("ifrs-full_Equity", "자본총계", "BS", 400 * multiplier),
        row("ifrs-full_CurrentAssets", "유동자산", "BS", 500 * multiplier),
        row("ifrs-full_CurrentLiabilities", "유동부채", "BS", 300 * multiplier),
        row("ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름", "CF", 90 * multiplier),
        row("ifrs-full_CashFlowsFromUsedInInvestingActivities", "투자활동현금흐름", "CF", -40 * multiplier),
        row("ifrs-full_CashFlowsFromUsedInFinancingActivities", "재무활동현금흐름", "CF", -20 * multiplier),
        row("ifrs-full_CashAndCashEquivalents", "현금및현금성자산", "CF", 120 * multiplier),
        row("ifrs-full_Inventories", "재고자산", "BS", 60 * multiplier),
        row("ifrs-full_ShorttermBorrowings", "단기차입금", "BS", 70 * multiplier),
        row("ifrs-full_CurrentPortionOfLongtermBorrowings", "유동성장기차입금", "BS", 20 * multiplier),
        row("ifrs-full_LongtermBorrowings", "장기차입금", "BS", 110 * multiplier),
    ]


def filing_meta(company_id: str) -> dict[int, dict[str, str]]:
    return {
        year: {
            "receipt_number": f"2026{year}000001",
            "filed_at": f"{year + 1}0315",
            "auditor": "테스트회계법인",
            "audit_opinion": "unmodified",
        }
        for year in TARGET_YEARS
    }


def test_opendart_client_supports_explicit_consolidated_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    client = OpenDartClient(api_key="test")

    def fake_request(endpoint: str, params: dict[str, object], *, require_json_status: bool = True) -> bytes:
        captured.update({"endpoint": endpoint, "params": params, "require_json_status": require_json_status})
        return json.dumps({"status": "000", "list": []}).encode()

    monkeypatch.setattr(client, "_request_bytes", fake_request)
    client.single_account_all(corp_code="00120030", fiscal_year=2025, fs_div="CFS")
    assert captured["endpoint"] == "fnlttSinglAcntAll.json"
    assert captured["params"]["fs_div"] == "CFS"  # type: ignore[index]

    with pytest.raises(ValueError):
        client.single_account_all(corp_code="00120030", fiscal_year=2025, fs_div="INVALID")


def test_existing_opendart_callers_keep_separate_scope_default(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    client = OpenDartClient(api_key="test")

    def fake_request(endpoint: str, params: dict[str, object], *, require_json_status: bool = True) -> bytes:
        captured["params"] = params
        return json.dumps({"status": "000", "list": []}).encode()

    monkeypatch.setattr(client, "_request_bytes", fake_request)
    client.single_account_all(corp_code="00144960", fiscal_year=2025)
    assert captured["params"]["fs_div"] == "OFS"  # type: ignore[index]


def test_adapter_maps_core_cfs_metrics_without_inventing_note_values() -> None:
    record, diagnostics = map_structured_year(synthetic_cfs_rows(), "gs-ec_opendart_2025_test")
    assert record["income_statement"]["revenue"]["reported"] == 1_000
    assert record["balance_sheet"]["total_assets"]["reported"] == 1_000
    assert record["cash_flow"]["operating_cash_flow"]["reported"] == 90
    assert record["borrowings"]["short_term_borrowings"]["reported"] == 70
    assert record["working_capital"]["inventory"]["reported"] == 60

    # The whole-financial-statement API does not prove gross receivable/note detail.
    assert record["working_capital"]["trade_receivables_gross"]["reported"] is None
    assert record["working_capital"]["trade_receivables_gross"]["disclosure_status"] == "verification_pending"
    assert "working_capital.trade_receivables_gross" in diagnostics["pending"]


def test_four_general_contractors_are_locked_to_verified_registry_ids() -> None:
    assert set(GENERAL_CONTRACTORS) == {
        "gs-ec",
        "samsung-ct-construction",
        "hyundai-engineering",
        "dl-enc",
    }
    assert GENERAL_CONTRACTORS["gs-ec"]["corp_code"] == "00120030"
    assert GENERAL_CONTRACTORS["samsung-ct-construction"]["corp_code"] == "00149655"
    assert GENERAL_CONTRACTORS["hyundai-engineering"]["corp_code"] == "00349927"
    assert GENERAL_CONTRACTORS["dl-enc"]["corp_code"] == "01524093"


@pytest.mark.parametrize("company_id", sorted(GENERAL_CONTRACTORS))
def test_schema_shaped_candidate_validates_for_each_contractor(company_id: str) -> None:
    structured = {
        year: {"status": "000", "list": synthetic_cfs_rows(index + 1)}
        for index, year in enumerate(TARGET_YEARS)
    }
    candidate, diagnostics = build_audit_financial_candidate(
        company_id=company_id,
        structured_payloads=structured,
        filing_metadata=filing_meta(company_id),
    )

    assert candidate["entity_attribution"]["financial_scope"] == "consolidated"
    assert candidate["validation_metadata"]["expected_years"] == list(TARGET_YEARS)
    assert diagnostics["blockers"] == []

    result = validate(candidate, expected_year_override=list(TARGET_YEARS), base_ref=None)
    assert result["valid"], result["issues"]
    latest = result["derived_metrics"]["2025"]
    assert latest["operating_margin_pct"] == "10.0"
    assert latest["liabilities_to_equity_pct"] == "150.0"
    assert latest["total_borrowings"] == 600
    assert latest["receivables_total"] is None


def test_candidate_refuses_to_invent_missing_auditor() -> None:
    structured = {year: {"status": "000", "list": synthetic_cfs_rows()} for year in TARGET_YEARS}
    metadata = filing_meta("gs-ec")
    metadata[2025]["auditor"] = ""
    with pytest.raises(ValueError, match="missing_auditor"):
        build_audit_financial_candidate(
            company_id="gs-ec",
            structured_payloads=structured,
            filing_metadata=metadata,
        )
