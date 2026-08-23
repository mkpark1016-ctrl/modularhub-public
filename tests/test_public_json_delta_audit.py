from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.audit_public_json_delta import blocking_reasons, build_report


@pytest.fixture(autouse=True)
def isolate_repository_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.audit_public_json_delta.load_db_exclusions", lambda: []
    )


def item(item_id: str) -> dict:
    return {
        "id": item_id,
        "source": "D2B",
        "source_name": "D2B",
        "source_type": "procurement_plan",
        "source_record_id": f"record-{item_id}",
        "title": f"Plan {item_id}",
        "organization": "Test organization",
        "amount": 100,
        "days_until_deadline": 3,
        "is_closed": False,
        "opportunity_status": "active",
        "closed_at": None,
        "last_seen_at": "2026-08-20T00:00:00Z",
        "lifecycle_reason": "deadline_today_or_future",
    }


def report(before_items: list[dict], after_items: list[dict]) -> dict:
    return build_report({"items": before_items}, {"items": after_items})


def test_lifecycle_only_change_is_non_blocking() -> None:
    before = item("1")
    after = deepcopy(before)
    after["last_seen_at"] = "2026-08-21T00:00:00Z"

    result = report([before], [after])

    assert result["changed_count"] == 0
    assert result["lifecycle_only_changed_count"] == 1
    assert blocking_reasons(result) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("closed_at", "2026-08-21T00:00:00Z"),
        ("days_until_deadline", -1),
        ("is_closed", True),
        ("last_seen_at", "2026-08-21T00:00:00Z"),
        ("lifecycle_reason", "deadline_passed"),
        ("opportunity_status", "closed"),
    ],
)
def test_each_lifecycle_field_is_non_blocking(field: str, value: object) -> None:
    before = item("1")
    after = deepcopy(before)
    after[field] = value

    result = report([before], [after])

    assert result["changed_count"] == 0
    assert result["lifecycle_only_changed_count"] == 1
    assert blocking_reasons(result) == []


def test_multiple_lifecycle_fields_are_non_blocking() -> None:
    before = item("1")
    after = deepcopy(before)
    after["days_until_deadline"] = -1
    after["is_closed"] = True

    result = report([before], [after])

    assert result["changed_count"] == 0
    assert result["lifecycle_only_changed_count"] == 1
    assert blocking_reasons(result) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", "Changed title"),
        ("organization", "Changed organization"),
        ("amount", 200),
        ("source", "G2B"),
        ("source_type", "bid"),
        ("source_record_id", "changed-record-id"),
        ("request_headers", {"Authorization": "redacted"}),
    ],
)
def test_substantive_or_sensitive_change_is_blocking(field: str, value: object) -> None:
    before = item("1")
    after = deepcopy(before)
    after[field] = value

    result = report([before], [after])

    assert result["changed_count"] == 1
    assert result["lifecycle_only_changed_count"] == 0
    assert "existing_record_modified" in blocking_reasons(result)


def test_existing_id_removal_is_blocking() -> None:
    result = report([item("1")], [])

    assert "existing_record_removed" in blocking_reasons(result)


def test_many_lifecycle_only_changes_are_non_blocking() -> None:
    before = [item(str(index)) for index in range(43)]
    after = deepcopy(before)
    for row in after:
        row["days_until_deadline"] -= 1
        row["last_seen_at"] = "2026-08-21T00:00:00Z"

    result = report(before, after)

    assert result["changed_count"] == 0
    assert result["lifecycle_only_changed_count"] == 43
    assert blocking_reasons(result) == []


def test_mixed_lifecycle_and_substantive_change_is_blocking() -> None:
    before = item("1")
    after = deepcopy(before)
    after["days_until_deadline"] = 2
    after["title"] = "Changed title"

    result = report([before], [after])

    assert result["changed_count"] == 1
    assert result["lifecycle_only_changed_count"] == 0
    assert "existing_record_modified" in blocking_reasons(result)


def test_duplicate_public_id_is_blocking() -> None:
    duplicate = item("1")
    result = report([], [duplicate, deepcopy(duplicate)])

    assert result["duplicate_id_count"] == 1
    assert "public_id_collision" in blocking_reasons(result)
