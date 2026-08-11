"""Working-capital semantics for general-contractor OpenDART data.

The resolver is intentionally conservative: only accounts whose XBRL meaning is
specific enough are mapped to the existing audit-financial receivable fields.
Composite accounts such as 'trade and other receivables' are surfaced as review
candidates instead of being mislabeled as pure trade receivables.
"""

from __future__ import annotations

import re
from typing import Any


EXACT_TRADE_RECEIVABLE_ACCOUNT_IDS = {
    "ifrs-full_CurrentTradeReceivables",
    "dart_ShortTermTradeReceivable",
}
EXACT_CONSTRUCTION_RECEIVABLE_ACCOUNT_IDS = {
    "dart_ShortTermDueFromCustomersForContractWork",
}
COMPOSITE_RECEIVABLE_ACCOUNT_IDS = {
    "ifrs-full_TradeAndOtherCurrentReceivables",
}
CONTRACT_ASSET_ACCOUNT_IDS = {
    "ifrs-full_CurrentContractAssets",
}


def normalize_account_id(value: Any) -> str:
    return str(value or "").strip()


def normalize_account_name(value: Any) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(value or "").lower())


def classify_receivable_row(row: dict[str, Any]) -> str | None:
    account_id = normalize_account_id(row.get("account_id"))
    if account_id in EXACT_TRADE_RECEIVABLE_ACCOUNT_IDS:
        return "trade_receivables_gross"
    if account_id in EXACT_CONSTRUCTION_RECEIVABLE_ACCOUNT_IDS:
        return "construction_receivables_gross"
    if account_id in COMPOSITE_RECEIVABLE_ACCOUNT_IDS:
        return "composite_trade_and_other_receivables"
    if account_id in CONTRACT_ASSET_ACCOUNT_IDS:
        return "contract_assets"
    return None


def net_working_capital(current_assets: int | None, current_liabilities: int | None) -> int | None:
    if current_assets is None or current_liabilities is None:
        return None
    return int(current_assets) - int(current_liabilities)


def current_ratio_pct(current_assets: int | None, current_liabilities: int | None) -> float | None:
    if current_assets is None or current_liabilities in (None, 0):
        return None
    return round(int(current_assets) / int(current_liabilities) * 100, 1)
