from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from scripts.audit_public_json_delta import blocking_reasons, build_report
from src.public_data_policy import apply_business_lifecycle, merge_public_items


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
    assert result["changed"][0]["changed_fields"] == [field]
    assert result["changed_field_counts"] == {field: 1}


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


def test_nested_detail_mutation_is_redacted_and_blocking() -> None:
    before = item("1")
    before["detail"] = {"status": "before"}
    after = deepcopy(before)
    after["detail"] = {"status": "after", "private": "must-not-appear"}

    result = report([before], [after])

    assert result["changed"][0]["changed_fields"] == ["detail"]
    assert result["changed"][0]["classification"] == "SCHEMA/PRESENTATION_DRIFT"
    assert result["changed"][0]["field_presence"] == {
        "detail": {"before_present": True, "after_present": True}
    }
    assert "must-not-appear" not in str(result)
    assert "existing_record_modified" in blocking_reasons(result)


def test_verified_attachment_refresh_is_allowed_without_detail_replacement() -> None:
    before = item("1")
    before.update(
        {
            "attachments": [{"name": "old.pdf", "url": "https://official.test/old.pdf"}],
            "detail": {"notice": "stable"},
            "exact_link_verified": True,
        }
    )
    fresh = deepcopy(before)
    fresh.update(
        {
            "attachments": [{"name": "new.pdf", "url": "https://official.test/new.pdf"}],
            "detail": {"notice": "must-not-replace"},
        }
    )

    merged = merge_public_items(
        [before],
        [fresh],
        kind="business",
        now=datetime(2026, 8, 20, tzinfo=timezone.utc),
        removal_allowlist={},
    )[0]
    result = report([before], [merged])

    assert merged["attachments"] == fresh["attachments"]
    assert merged["detail"] == before["detail"]
    assert result["changed_count"] == 0
    assert result["authoritative_refresh_field_counts"] == {"attachments": 1}
    assert blocking_reasons(result) == []


def test_unverified_evidence_refresh_is_preserved_and_direct_mutation_blocks() -> None:
    before = item("1")
    before.update(
        {
            "attachments": [{"name": "old.pdf", "url": "https://official.test/old.pdf"}],
            "exact_link_verified": False,
        }
    )
    fresh = deepcopy(before)
    fresh["attachments"] = [
        {"name": "unverified.pdf", "url": "https://official.test/unverified.pdf"}
    ]

    merged = merge_public_items(
        [before],
        [fresh],
        kind="business",
        now=datetime(2026, 8, 20, tzinfo=timezone.utc),
        removal_allowlist={},
    )[0]
    direct_result = report([before], [fresh])

    assert merged["attachments"] == before["attachments"]
    assert direct_result["changed_count"] == 1
    assert direct_result["changed"][0]["classification"] == "SCHEMA/PRESENTATION_DRIFT"
    assert "existing_record_modified" in blocking_reasons(direct_result)


def test_verified_original_url_correction_is_allowed_and_redacted() -> None:
    before = item("1")
    before.update(
        {
            "exact_link_verified": False,
            "external_original_url": "https://official.test/old",
        }
    )
    after = deepcopy(before)
    after.update(
        {
            "exact_link_verified": True,
            "external_original_url": "https://official.test/corrected",
        }
    )

    result = report([before], [after])

    assert result["changed_count"] == 0
    assert result["authoritative_refresh_field_counts"] == {
        "exact_link_verified": 1,
        "external_original_url": 1,
    }
    assert "official.test" not in str(result["authoritative_refresh_changed"])
    assert blocking_reasons(result) == []


def test_verified_evidence_cannot_be_downgraded() -> None:
    before = item("1")
    before["exact_link_verified"] = True
    after = deepcopy(before)
    after["exact_link_verified"] = False

    result = report([before], [after])

    assert result["changed_count"] == 1
    assert result["changed"][0]["changed_fields"] == ["exact_link_verified"]
    assert "existing_record_modified" in blocking_reasons(result)


def test_changed_field_diagnostics_do_not_serialize_secret_values() -> None:
    before = item("1")
    after = deepcopy(before)
    after["request_headers"] = {"Authorization": "super-secret-value"}

    result = report([before], [after])

    serialized = str(result)
    assert result["changed"][0]["changed_fields"] == ["request_headers"]
    assert "super-secret-value" not in serialized
    assert "Authorization" not in serialized


@pytest.mark.parametrize("field", ["title", "organization", "amount"])
def test_canonical_mutation_is_classified_as_unsafe_overwrite(field: str) -> None:
    before = item("1")
    after = deepcopy(before)
    after[field] = f"changed-{field}" if field != "amount" else 200

    result = report([before], [after])

    assert result["changed"][0]["classification"] == "UNSAFE_EXISTING_VALUE_OVERWRITE"
    assert result["changed"][0]["changed_fields"] == [field]
    assert "existing_record_modified" in blocking_reasons(result)


def test_additive_export_preserves_existing_canonical_facts() -> None:
    now = datetime(2026, 8, 20, tzinfo=timezone.utc)
    before = item("1")
    before["due_at"] = "2026-08-25T00:00:00+09:00"
    fresh_existing = deepcopy(before)
    fresh_existing.update(
        {
            "title": "Changed title",
            "organization": "Changed organization",
            "amount": 999,
            "summary": "Unapproved enrichment",
            "due_at": "2026-09-01T18:00:00+09:00",
            "notice_status": "정정공고",
        }
    )
    fresh_new = item("2")
    fresh_new["source_record_id"] = "record-2"

    merged = merge_public_items(
        [before],
        [fresh_existing, fresh_new],
        kind="business",
        now=now,
        removal_allowlist={},
    )
    candidate = apply_business_lifecycle(merged, now=now)
    result = report([before], candidate)
    existing = next(row for row in candidate if row["id"] == "1")

    assert existing["title"] == before["title"]
    assert existing["organization"] == before["organization"]
    assert existing["amount"] == before["amount"]
    assert "summary" not in existing
    assert existing["due_at"] == fresh_existing["due_at"]
    assert existing["notice_status"] == fresh_existing["notice_status"]
    assert result["added_count"] == 1
    assert result["removed_count"] == 0
    assert result["changed_count"] == 0
    assert result["authoritative_refresh_changed_count"] == 1
    assert result["authoritative_refresh_field_counts"] == {
        "due_at": 1,
        "notice_status": 1,
    }
    assert blocking_reasons(result) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("due_at", "2026-09-15T18:00:00+09:00"),
        ("notice_status", "정정공고"),
        ("notice_stage", "correction"),
    ],
)
def test_authoritative_same_identity_refresh_is_non_blocking(
    field: str, value: object
) -> None:
    before = item("1")
    before[field] = "before"
    after = deepcopy(before)
    after[field] = value

    result = report([before], [after])

    assert result["changed_count"] == 0
    assert result["authoritative_refresh_changed_count"] == 1
    assert result["authoritative_refresh_field_counts"] == {field: 1}
    assert result["authoritative_refresh_changed"][0]["changed_fields"] == [field]
    assert blocking_reasons(result) == []
