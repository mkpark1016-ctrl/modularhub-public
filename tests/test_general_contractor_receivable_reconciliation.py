from __future__ import annotations

import json
from pathlib import Path

from src.general_contractor_receivable_reconciliation import (
    exact_receivable_rows,
    reconcile_year,
)

ROOT = Path(__file__).resolve().parents[1]


def row(account_id: str, account_nm: str, amount: int, sj_div: str = "BS") -> dict[str, str]:
    return {
        "account_id": account_id,
        "account_nm": account_nm,
        "sj_div": sj_div,
        "thstrm_amount": str(amount),
    }


def pending() -> dict[str, object]:
    return {
        "reported": None,
        "disclosure_status": "verification_pending",
        "source_refs": ["source"],
        "source_locations": [
            {"source_ref": "source", "section": "note.working_capital", "verification_status": "pending_manual_page_check"}
        ],
        "notes": "pending",
    }


def load_public(company_id: str) -> dict[str, object]:
    path = ROOT / "data" / "company_reports" / company_id / "audit_financials_2023_2025.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_exact_rows_include_samsung_and_hyundai_semantics_only() -> None:
    rows = [
        row("ifrs-full_CurrentTradeReceivables", "매출채권", 100),
        row("dart_ShortTermDueFromCustomersForContractWork", "미청구공사채권", 40),
        row("ifrs-full_TradeAndOtherCurrentReceivables", "매출채권및기타채권", 300),
        row("ifrs-full_CurrentContractAssets", "계약자산", 50),
    ]
    matches = exact_receivable_rows(rows)
    assert matches["trade_receivables_gross"]["thstrm_amount"] == "100"
    assert matches["construction_receivables_gross"]["thstrm_amount"] == "40"
    assert len(matches) == 2


def test_reconcile_year_updates_only_exact_receivable_fields_without_mutation() -> None:
    record = {
        "working_capital": {
            "trade_receivables_gross": pending(),
            "construction_receivables_gross": pending(),
            "inventory": pending(),
            "work_in_progress": pending(),
        }
    }
    rows = [
        row("dart_ShortTermTradeReceivable", "매출채권", 120),
        row("dart_ShortTermDueFromCustomersForContractWork", "미청구공사채권", 80),
    ]
    updated, diagnostics = reconcile_year(record, rows, "hyundai-engineering_opendart_2025_TEST")
    assert record["working_capital"]["trade_receivables_gross"]["reported"] is None
    assert updated["working_capital"]["trade_receivables_gross"]["reported"] == 120
    assert updated["working_capital"]["construction_receivables_gross"]["reported"] == 80
    assert sorted(diagnostics["applied"]) == ["construction_receivables_gross", "trade_receivables_gross"]


def test_composite_gs_dl_receivable_account_is_not_promoted() -> None:
    rows = [row("ifrs-full_TradeAndOtherCurrentReceivables", "매출채권및기타채권", 999)]
    assert exact_receivable_rows(rows) == {}


def test_public_samsung_trade_receivables_are_reported_for_all_three_years() -> None:
    payload = load_public("samsung-ct-construction")
    expected = {
        "2023": 6_409_308_979_443,
        "2024": 7_325_254_673_959,
        "2025": 7_382_578_167_968,
    }
    for year, value in expected.items():
        record = payload["financial_years"][year]["working_capital"]
        assert record["trade_receivables_gross"]["reported"] == value
        assert record["trade_receivables_gross"]["disclosure_status"] == "reported"
        assert record["construction_receivables_gross"]["reported"] is None


def test_public_hyundai_receivables_support_reported_receivables_to_revenue() -> None:
    payload = load_public("hyundai-engineering")
    expected = {
        "2023": (1_829_102_000_000, 1_432_812_000_000),
        "2024": (2_408_453_000_000, 1_108_409_000_000),
        "2025": (2_856_228_000_000, 1_138_369_000_000),
    }
    for year, (trade, construction) in expected.items():
        record = payload["financial_years"][year]["working_capital"]
        assert record["trade_receivables_gross"]["reported"] == trade
        assert record["construction_receivables_gross"]["reported"] == construction


def test_public_gs_and_dl_composite_receivables_remain_pending() -> None:
    for company_id in ("gs-ec", "dl-enc"):
        payload = load_public(company_id)
        for year in ("2023", "2024", "2025"):
            record = payload["financial_years"][year]["working_capital"]
            assert record["trade_receivables_gross"]["reported"] is None
            assert record["trade_receivables_gross"]["disclosure_status"] == "verification_pending"
