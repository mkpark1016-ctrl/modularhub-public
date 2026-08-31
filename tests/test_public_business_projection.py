from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from scripts.integrations.business.base import NormalizedBusinessRecord
from scripts.integrations.business.public_projection import (
    build_public_projection,
    project_record,
    public_id,
    public_relevance_decision,
    write_public_projection_outputs,
)


GENERATED_AT = "2026-08-20T07:23:09+00:00"


def canonical(external_id: str, *, source: str = "d2b", record_type: str = "bid_notice",
              title: str = "모듈러 시설 입찰공고", organization: str | None = "방위사업청",
              source_url: str = "https://www.d2b.go.kr/", published_at: str = "2026-08-20"):
    return NormalizedBusinessRecord(
        source=source, source_record_type=record_type, external_id=external_id, title=title,
        issuing_organization=organization, category="시설공사", estimated_amount=100_000_000,
        published_at=published_at, deadline_at="2026-08-30", status="공고",
        contract_method="일반경쟁", source_url=source_url, collected_at=GENERATED_AT,
    )


def baseline(*items: dict) -> dict:
    return {"generated_at": GENERATED_AT, "business_total": len(items),
            "merged_business_count": len(items), "items": list(items)}


def project(records: list[NormalizedBusinessRecord], payload: dict | None = None):
    return build_public_projection(
        records, payload or baseline(), unified_summary={"generated_at": GENERATED_AT}
    )


def test_canonical_record_projects_to_current_public_contract() -> None:
    projected, candidate, report = project([canonical("D2B-1")])
    assert report["publishable_count"] == report["net_new_count"] == 1
    assert candidate["items"] == projected
    assert {key: projected[0][key] for key in ("source", "source_type", "source_record_id", "organization")} == {
        "source": "D2B", "source_type": "bid", "source_record_id": "D2B-1", "organization": "방위사업청"
    }


def test_public_id_and_projection_are_deterministic() -> None:
    value = canonical("D2B-1")
    assert public_id(value) == "d2b_bid_notice:D2B-1"
    assert project([value]) == project([value])


def test_exact_existing_match_is_not_added_twice() -> None:
    value = canonical("D2B-1")
    existing = project([value])[0][0]
    _, candidate, report = project([value], baseline(existing))
    assert report["exact_existing_matches"] == 1
    assert report["net_new_count"] == 0
    assert candidate["items"] == [existing]


def test_derived_lifecycle_drift_is_not_a_public_id_collision() -> None:
    value = canonical("D2B-1")
    existing = deepcopy(project([value])[0][0])
    existing["days_until_deadline"] -= 1

    _, candidate, report = project([value], baseline(existing))

    assert report["exact_existing_matches"] == 1
    assert report["public_id_collision_count"] == 0
    assert report["net_new_count"] == 0
    assert candidate["items"] == [existing]


def test_authoritative_deadline_refresh_is_not_a_public_id_collision() -> None:
    value = canonical("D2B-1")
    existing = deepcopy(project([value])[0][0])
    existing["due_at"] = "2026-08-29"

    _, candidate, report = project([value], baseline(existing))

    assert report["exact_existing_matches"] == 1
    assert report["public_id_collision_count"] == 0
    assert report["net_new_count"] == 0
    assert candidate["items"] == [existing]


def test_same_public_id_with_different_payload_is_blocking_collision() -> None:
    value = canonical("D2B-1")
    existing = deepcopy(project([value])[0][0])
    existing["title"] = "다른 기존 제목"
    _, candidate, report = project([value], baseline(existing))
    assert report["public_id_collision_count"] == 1
    assert report["net_new_count"] == 0
    assert candidate["items"] == [existing]


def test_cross_source_similar_title_is_not_auto_deduped() -> None:
    records = [canonical("D2B-1"), canonical("G2B-1", source="g2b", organization="방위사업청",
                source_url="https://www.g2b.go.kr/")]
    _, candidate, report = project(records)
    assert report["net_new_count"] == 2
    assert report["possible_overlap_candidate_count"] == 1
    assert len(candidate["items"]) == 2


def test_generic_d2b_base_url_is_never_used_as_identity() -> None:
    _, candidate, report = project([canonical("D2B-1"), canonical("D2B-2")])
    assert report["net_new_count"] == 2
    assert len({item["id"] for item in candidate["items"]}) == 2


def test_existing_public_records_are_fully_preserved() -> None:
    existing = project([canonical("OLD")])[0][0]
    _, candidate, report = project([canonical("NEW")], baseline(existing))
    assert report["existing_records_removed"] == 0
    assert existing in candidate["items"]


def test_required_field_failure_is_reported_without_fake_value() -> None:
    projected, _, report = project([canonical("D2B-1", organization=None)])
    assert projected[0]["organization"] == ""
    assert report["required_field_failures"] == [
        {"id": "d2b_bid_notice:D2B-1", "missing": ["organization"], "issues": []}
    ]


def test_existing_relevance_policy_and_reason_counts_are_reused() -> None:
    relevant = canonical("D2B-1")
    unrelated = canonical("D2B-2", title="시설 정기 보수공사")
    lh_direct = canonical("LH-1", source="lh")
    assert public_relevance_decision(relevant) == (True, None)
    assert public_relevance_decision(unrelated)[1] == "existing_public_relevance_policy_no_match"
    assert public_relevance_decision(lh_direct)[1] == "unsupported_existing_public_source_or_type"
    _, _, report = project([relevant, unrelated, lh_direct])
    assert report["filtered_reasons"] == {
        "existing_public_relevance_policy_no_match": 1,
        "unsupported_existing_public_source_or_type": 1,
    }


def test_utf8_korean_round_trip(tmp_path: Path) -> None:
    projected, candidate, report = project([canonical("한글-1", title="모듈러 간부숙소 신축")])
    write_public_projection_outputs(projected, candidate, report, tmp_path)
    text = (tmp_path / "projected_business_records.json").read_text(encoding="utf-8")
    assert "모듈러 간부숙소 신축" in text
    assert json.loads(text)[0]["title"] == "모듈러 간부숙소 신축"


def test_credential_url_is_blocked_without_leaking_value() -> None:
    _, _, report = project([canonical("D2B-1", source_url="https://example.test/item?serviceKey=secret")])
    assert report["security"]["credential_urls_detected"] == 1
    assert report["security"]["passed"] is False
    assert "secret" not in json.dumps(report, ensure_ascii=False)


def test_candidate_order_is_deterministic_for_reversed_input() -> None:
    records = [canonical("D2B-1", published_at="2026-08-19"), canonical("D2B-2")]
    assert project(records)[1] == project(list(reversed(records)))[1]


def test_publishable_pre_spec_exposes_current_frontend_semantic_gap() -> None:
    value = canonical("G2B-SPEC-1", source="g2b", record_type="pre_spec",
                      source_url="https://www.g2b.go.kr/")
    projected, _, report = project([value])
    assert project_record(value)["type"] == "사전규격"
    assert projected[0]["source_type"] == "bid"
    assert report["frontend_contract_issues"][0]["issue"] == (
        "pre_spec_not_distinguishable_in_current_frontend_source_type_contract"
    )
