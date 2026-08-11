from __future__ import annotations

from src.general_contractor_working_capital import (
    classify_receivable_row,
    current_ratio_pct,
    net_working_capital,
)


def test_exact_receivable_accounts_are_mapped_without_composite_guessing() -> None:
    assert classify_receivable_row({"account_id": "ifrs-full_CurrentTradeReceivables"}) == "trade_receivables_gross"
    assert classify_receivable_row({"account_id": "dart_ShortTermTradeReceivable"}) == "trade_receivables_gross"
    assert classify_receivable_row({"account_id": "dart_ShortTermDueFromCustomersForContractWork"}) == "construction_receivables_gross"
    assert classify_receivable_row({"account_id": "ifrs-full_CurrentContractAssets"}) == "contract_assets"


def test_trade_and_other_receivables_stays_composite_until_note_reconciliation() -> None:
    assert classify_receivable_row({"account_id": "ifrs-full_TradeAndOtherCurrentReceivables"}) == "composite_trade_and_other_receivables"


def test_net_working_capital_and_current_ratio_use_balance_sheet_totals() -> None:
    assert net_working_capital(1_200, 900) == 300
    assert current_ratio_pct(1_200, 900) == 133.3
    assert net_working_capital(None, 900) is None
    assert current_ratio_pct(1_200, 0) is None
