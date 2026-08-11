from __future__ import annotations

from copy import deepcopy

from scripts.check_general_contractor_dart_audit_updates import compare_payloads, markdown_report


def amount(value: int | None, status: str = "reported") -> dict[str, object]:
    return {"reported": value, "disclosure_status": status}


def payload(company_id: str = "gs-ec") -> dict[str, object]:
    return {
        "company_id": company_id,
        "currency": "KRW",
        "unit": "won",
        "entity_attribution": {"financial_scope": "consolidated"},
        "source_priority": {
            "2023": {"primary_source_ref": "financial-2023", "cross_check_source_refs": ["audit-2023"]},
            "2024": {"primary_source_ref": "financial-2024", "cross_check_source_refs": []},
            "2025": {"primary_source_ref": "financial-2025", "cross_check_source_refs": ["audit-2025"]},
        },
        "audit_opinions": [
            {"covered_years": [2023], "opinion": "unqualified", "auditor": "A", "source_ref": "audit-2023"},
            {"covered_years": [2024], "opinion": "unqualified", "auditor": "A", "source_ref": "financial-2024"},
            {"covered_years": [2025], "opinion": "unqualified", "auditor": "B", "source_ref": "audit-2025"},
        ],
        "financial_years": {
            year: {
                "income_statement": {
                    "revenue": amount(1000 + index),
                    "operating_profit": amount(100 + index),
                },
                "working_capital": {
                    "trade_receivables_gross": amount(None, "verification_pending"),
                },
            }
            for index, year in enumerate(("2023", "2024", "2025"))
        },
    }


def test_identical_candidate_needs_no_review() -> None:
    public = payload()
    candidate = deepcopy(public)
    result = compare_payloads(public, candidate)
    assert result["review_required"] is False
    assert result["regression_detected"] is False
    assert result["change_count"] == 0
    assert "No source" in markdown_report(result)


def test_financial_receipt_change_is_reviewable() -> None:
    public = payload()
    candidate = deepcopy(public)
    candidate["source_priority"]["2025"]["primary_source_ref"] = "financial-2025-corrected"
    result = compare_payloads(public, candidate)
    assert result["review_required"] is True
    assert result["change_counts_by_kind"] == {"primary_source_changed": 1}
    assert result["regression_detected"] is False


def test_value_change_is_reviewable_without_being_coverage_regression() -> None:
    public = payload()
    candidate = deepcopy(public)
    candidate["financial_years"]["2025"]["income_statement"]["revenue"]["reported"] = 1200
    result = compare_payloads(public, candidate)
    assert result["change_counts_by_kind"] == {"metric_value_changed": 1}
    assert result["regression_detected"] is False


def test_reported_metric_becoming_pending_is_regression() -> None:
    public = payload()
    candidate = deepcopy(public)
    candidate["financial_years"]["2025"]["income_statement"]["revenue"] = amount(None, "verification_pending")
    result = compare_payloads(public, candidate)
    assert result["review_required"] is True
    assert result["regression_detected"] is True
    assert result["change_counts_by_kind"] == {"metric_coverage_regression": 1}


def test_pending_metric_becoming_reported_is_newly_available() -> None:
    public = payload()
    candidate = deepcopy(public)
    candidate["financial_years"]["2025"]["working_capital"]["trade_receivables_gross"] = amount(321)
    result = compare_payloads(public, candidate)
    assert result["change_counts_by_kind"] == {"metric_newly_available": 1}
    assert result["regression_detected"] is False


def test_audit_metadata_change_is_separate_from_financial_value_change() -> None:
    public = payload()
    candidate = deepcopy(public)
    candidate["audit_opinions"][2]["auditor"] = "C"
    result = compare_payloads(public, candidate)
    assert result["change_counts_by_kind"] == {"audit_metadata_changed": 1}


def test_company_id_mismatch_is_rejected() -> None:
    public = payload("gs-ec")
    candidate = payload("dl-enc")
    try:
        compare_payloads(public, candidate)
    except ValueError as exc:
        assert "company_id mismatch" in str(exc)
    else:
        raise AssertionError("company_id mismatch must fail")
