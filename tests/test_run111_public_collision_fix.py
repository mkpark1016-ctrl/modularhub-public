from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.integrations.business.base import NormalizedBusinessRecord
from scripts.integrations.business.public_pipeline import (
    UnifiedPublicInputError,
    integrate_optional_unified_business,
)
from scripts.integrations.business.public_projection import (
    build_public_projection,
    projection_blockers,
)
from src.public_data_policy import (
    business_items_safely_refreshable,
    merge_public_items,
    safe_business_refresh_fields,
)


TARGET_EXTERNAL_ID = "d2b:procurement_plan:2026-14303"
GENERATED_AT = "2026-09-07T23:57:51+00:00"


def canonical(*, status: str, amount: int | None, title: str = "26-M-모듈러형 간부숙소 신축") -> NormalizedBusinessRecord:
    return NormalizedBusinessRecord(
        source="d2b",
        source_record_type="procurement_plan",
        external_id=TARGET_EXTERNAL_ID,
        title=title,
        issuing_organization="국군재정관리단",
        category="시설공사",
        estimated_amount=amount,
        currency="KRW",
        published_at="2026-09-01",
        deadline_at="2026-09-01",
        status=status,
        contract_method="일반경쟁",
        source_url="https://www.d2b.go.kr/",
        collected_at=GENERATED_AT,
    )


def public_item(record: NormalizedBusinessRecord) -> dict:
    return build_public_projection(
        [record], {"items": []}, unified_summary={"generated_at": GENERATED_AT}
    )[0][0]


def test_run111_transition_is_one_safe_existing_refresh() -> None:
    existing = public_item(canonical(status="집행계획", amount=0))
    fresh = public_item(canonical(status="공고확정", amount=2_943_080_000))

    assert business_items_safely_refreshable(existing, fresh)
    assert safe_business_refresh_fields(existing, fresh) == [
        "amount",
        "notice_stage",
        "notice_status",
    ]

    _, candidate, report = build_public_projection(
        [canonical(status="공고확정", amount=2_943_080_000)],
        {"items": [existing]},
        unified_summary={"generated_at": GENERATED_AT},
    )
    assert report["public_id_collision_count"] == 0
    assert report["exact_existing_matches"] == 1
    assert projection_blockers(report) == []
    assert candidate["items"] == [existing]


@pytest.mark.parametrize(
    ("before_amount", "before_status", "after_amount", "after_status", "allowed"),
    [
        (None, "공고확정", 100, "공고확정", True),
        (0, "집행계획", 100, "공고확정", True),
        (0, "집행계획", 100, "집행계획", False),
        (100, "공고확정", 200, "공고확정", False),
        (100, "공고확정", 0, "공고확정", False),
    ],
)
def test_d2b_amount_enrichment_contract(
    before_amount: int | None,
    before_status: str,
    after_amount: int,
    after_status: str,
    allowed: bool,
) -> None:
    before = public_item(canonical(status=before_status, amount=before_amount))
    after = public_item(canonical(status=after_status, amount=after_amount))
    assert business_items_safely_refreshable(before, after) is allowed


@pytest.mark.parametrize("field", ["title", "organization", "posted_at"])
def test_canonical_identity_fields_remain_blocked(field: str) -> None:
    before = public_item(canonical(status="공고확정", amount=100))
    after = deepcopy(before)
    after[field] = "changed"
    assert not business_items_safely_refreshable(before, after)


def test_empty_amount_enrichment_is_not_allowed_for_non_d2b_sources() -> None:
    before = public_item(canonical(status="공고확정", amount=None))
    after = public_item(canonical(status="공고확정", amount=100))
    before.update({"source": "G2B", "source_name": "G2B"})
    after.update({"source": "G2B", "source_name": "G2B"})
    assert not business_items_safely_refreshable(before, after)


def test_status_refresh_and_lifecycle_refresh_remain_allowed() -> None:
    before = public_item(canonical(status="집행계획", amount=0))
    after = public_item(canonical(status="공고확정", amount=0))
    after["days_until_deadline"] = before["days_until_deadline"] - 1
    assert business_items_safely_refreshable(before, after)
    merged = merge_public_items([before], [after], kind="business", removal_allowlist={})[0]
    assert merged["notice_status"] == "공고확정"
    assert merged["amount"] == 0


def test_blocked_projection_writes_redacted_diagnostics(tmp_path: Path) -> None:
    existing = public_item(canonical(status="집행계획", amount=0))
    existing["title"] = "tampered existing title"
    records_path = tmp_path / "unified_records.json"
    summary_path = tmp_path / "unified_summary.json"
    diagnostics_path = tmp_path / "public_projection_failure_diagnostics.json"
    records_path.write_text(
        json.dumps([canonical(status="공고확정", amount=2_943_080_000).as_dict()]),
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps({"records_output": 1, "generated_at": GENERATED_AT}),
        encoding="utf-8",
    )

    with pytest.raises(UnifiedPublicInputError, match="public_id_collision"):
        integrate_optional_unified_business(
            [existing],
            unified_records_path=records_path,
            unified_summary_path=summary_path,
            projection_diagnostics_path=diagnostics_path,
        )

    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    assert diagnostics["decision"] == "blocked"
    assert diagnostics["public_id_collision_count"] == 1
    collision = diagnostics["public_id_collisions"][0]
    assert collision["public_id"] == "d2b_procurement_plan:d2b:procurement_plan:2026-14303"
    assert collision["changed_fields"] == ["amount", "notice_stage", "notice_status", "title"]
    serialized = json.dumps(diagnostics, ensure_ascii=False)
    assert "tampered existing title" not in serialized
    assert "2943080000" not in serialized
    assert "Authorization" not in serialized
