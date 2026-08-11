"""Reconcile exact OpenDART receivable accounts into public audit-financial sources.

This layer is deliberately narrow. It only promotes XBRL accounts whose meaning
matches the existing schema fields exactly. Composite trade-and-other receivable
accounts and generic contract assets remain pending for later note reconciliation.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.general_contractor_working_capital import classify_receivable_row


def amount(value: Any) -> int | None:
    if value in (None, ""):
        return None
    text = str(value).replace(",", "").strip()
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    try:
        parsed = int(float(text))
    except (TypeError, ValueError):
        return None
    return -parsed if negative else parsed


def exact_receivable_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    matches: dict[str, dict[str, Any]] = {}
    for row in rows:
        if str(row.get("sj_div") or "").upper() != "BS":
            continue
        category = classify_receivable_row(row)
        if category not in {"trade_receivables_gross", "construction_receivables_gross"}:
            continue
        value = amount(row.get("thstrm_amount"))
        if value is None:
            continue
        if category in matches:
            raise ValueError(f"ambiguous exact receivable mapping for {category}")
        matches[category] = row
    return matches


def reported_record(value: int, source_ref: str) -> dict[str, Any]:
    return {
        "reported": int(value),
        "disclosure_status": "reported",
        "source_refs": [source_ref],
        "source_locations": [
            {
                "source_ref": source_ref,
                "section": "note.working_capital",
                "verification_status": "pending_manual_page_check",
            }
        ],
        "notes": "OpenDART 연결 전체재무제표의 의미가 정확히 일치하는 XBRL 계정을 사용했다.",
    }


def reconcile_year(record: dict[str, Any], rows: list[dict[str, Any]], source_ref: str) -> tuple[dict[str, Any], dict[str, Any]]:
    output = deepcopy(record)
    matches = exact_receivable_rows(rows)
    applied: dict[str, Any] = {}
    for field, row in matches.items():
        value = amount(row.get("thstrm_amount"))
        if value is None:
            continue
        output["working_capital"][field] = reported_record(value, source_ref)
        applied[field] = {
            "account_id": row.get("account_id"),
            "account_name": row.get("account_nm"),
            "reported": value,
        }
    return output, {"applied": applied}
