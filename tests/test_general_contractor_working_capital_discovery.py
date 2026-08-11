from __future__ import annotations

from scripts.discover_general_contractor_working_capital_accounts import (
    KEYWORDS,
    matches_working_capital_keyword,
    sanitize_row,
)


def test_keywords_cover_contractor_receivables_contract_assets_and_borrowings() -> None:
    required = {"매출채권", "기타채권", "계약자산", "미청구", "단기차입", "장기차입"}
    assert required.issubset(set(KEYWORDS))


def test_discovery_matches_relevant_account_names_only() -> None:
    positives = [
        "매출채권및기타채권",
        "계약자산",
        "미청구공사채권",
        "단기차입금",
        "장기차입금",
        "재고자산",
    ]
    for account_name in positives:
        assert matches_working_capital_keyword({"account_nm": account_name})

    assert not matches_working_capital_keyword({"account_nm": "현금및현금성자산"})
    assert not matches_working_capital_keyword({"account_nm": "영업이익"})


def test_sanitized_discovery_rows_exclude_unrelated_payload_fields() -> None:
    raw = {
        "rcept_no": "20260316000001",
        "sj_div": "BS",
        "account_id": "dart_Test",
        "account_nm": "매출채권",
        "thstrm_amount": "100",
        "frmtrm_amount": "90",
        "bfefrmtrm_amount": "80",
        "currency": "KRW",
        "ord": "10",
        "secretish": "must-not-be-propagated",
    }
    sanitized = sanitize_row(raw)
    assert sanitized["account_nm"] == "매출채권"
    assert "secretish" not in sanitized
