from __future__ import annotations

from src.general_contractor_receivable_reconciliation import (
    exact_receivable_rows,
    reconcile_year,
)


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
