from __future__ import annotations

from copy import deepcopy

from src.public_data_policy import (
    CONTROLLED_PUBLIC_BUSINESS_PATH,
    CONTROLLED_PUBLIC_META_PATH,
    validate_controlled_business_publication,
)


PUBLIC_PATHS = [CONTROLLED_PUBLIC_BUSINESS_PATH, CONTROLLED_PUBLIC_META_PATH]


def business_item(
    item_id: str,
    *,
    source: str,
    source_type: str,
    status: str,
    external_id: str,
    title: str,
) -> dict:
    item = {
        "id": item_id,
        "source": source,
        "source_name": source,
        "source_type": source_type,
        "source_record_id": external_id,
        "title": title,
        "organization": "테스트 발주기관",
        "opportunity_status": status,
        "posted_at": "2026-08-20",
        "external_original_url": "https://example.test/notice",
    }
    if source_type == "bid":
        item["bid_no"] = external_id
        item["bid_order"] = ""
    if source_type == "procurement_plan":
        item["plan_no"] = external_id
    return item


def baseline_items() -> list[dict]:
    return [
        business_item(
            "bid-1",
            source="G2B",
            source_type="bid",
            status="active",
            external_id="BID-1",
            title="기존 입찰",
        ),
        business_item(
            "plan-1",
            source="G2B",
            source_type="procurement_plan",
            status="closed",
            external_id="PLAN-1",
            title="기존 발주계획",
        ),
        business_item(
            "contest-1",
            source="GH",
            source_type="public_agency_contest",
            status="unknown",
            external_id="CONTEST-1",
            title="기존 공모",
        ),
    ]


def new_d2b_item() -> dict:
    return business_item(
        "d2b-plan-2",
        source="D2B",
        source_type="procurement_plan",
        status="active",
        external_id="D2B-PLAN-2",
        title="모듈러 간부숙소 신축 설계용역",
    )


def count_fields(items: list[dict]) -> dict:
    return {
        "business_total": len(items),
        "business_active": sum(item["opportunity_status"] == "active" for item in items),
        "business_closed": sum(item["opportunity_status"] == "closed" for item in items),
        "business_unknown": sum(item["opportunity_status"] == "unknown" for item in items),
        "bid_total": sum(item["source_type"] == "bid" for item in items),
        "procurement_plan_count": sum(
            item["source_type"] == "procurement_plan" for item in items
        ),
        "procurement_plan_total": sum(
            item["source_type"] == "procurement_plan" for item in items
        ),
        "public_agency_contest_total": sum(
            item["source_type"] == "public_agency_contest" for item in items
        ),
    }


def publication_payloads() -> tuple[dict, dict, dict, dict]:
    before_items = baseline_items()
    after_items = [*deepcopy(before_items), new_d2b_item()]
    before_business = {
        **count_fields(before_items),
        "previous_business_count": len(before_items),
        "merged_business_count": len(before_items),
        "public_data_guard_status": "passed",
        "public_data_guard_message": "Cumulative merge protected public data: business 3 -> 3, news 5 -> 5.",
        "items": before_items,
    }
    before_meta = {
        **{key: value for key, value in before_business.items() if key != "items"},
        "business_count": len(before_items),
    }
    publication_metadata = {
        **count_fields(after_items),
        "previous_business_count": len(before_items),
        "merged_business_count": len(after_items),
        "public_data_guard_status": "passed",
        "public_data_guard_message": "Cumulative merge protected public data: business 3 -> 4, news 5 -> 5.",
        "d2b_status": "success",
        "d2b_legacy_status": "disabled_stopped",
        "d2b_gw_migration_required": False,
        "d2b_unified_status": "success",
        "d2b_unified_public_count": 1,
        "d2b_unified_last_collected_at": "2026-08-20T07:23:09+00:00",
        "procurement_plan_source_status": {"G2B": "success", "D2B": "success"},
    }
    after_business = {**publication_metadata, "items": after_items}
    after_meta = {**publication_metadata, "business_count": len(after_items)}
    return before_business, after_business, before_meta, after_meta


def validate(
    before_business: dict,
    after_business: dict,
    before_meta: dict,
    after_meta: dict,
    changed_paths=PUBLIC_PATHS,
) -> dict:
    return validate_controlled_business_publication(
        before_business,
        after_business,
        before_meta,
        after_meta,
        changed_paths,
    )


def test_no_public_data_change_passes_without_publication_approval() -> None:
    payloads = publication_payloads()
    result = validate(*payloads, changed_paths=["src/example.py"])
    assert result["passed"] is True
    assert result["status"] == "NO_CONTROLLED_PUBLIC_DATA_CHANGE"


def test_existing_business_deletion_is_blocked() -> None:
    before, after, before_meta, after_meta = publication_payloads()
    after["items"] = after["items"][1:]
    result = validate(before, after, before_meta, after_meta)
    assert "existing_business_removed" in result["reason_codes"]


def test_existing_business_payload_mutation_is_blocked() -> None:
    before, after, before_meta, after_meta = publication_payloads()
    after["items"][0]["organization"] = "변경된 발주기관"
    result = validate(before, after, before_meta, after_meta)
    assert "existing_business_modified" in result["reason_codes"]


def test_public_id_collision_is_blocked() -> None:
    before, after, before_meta, after_meta = publication_payloads()
    colliding = deepcopy(after["items"][-1])
    colliding["source_record_id"] = colliding["plan_no"] = "D2B-PLAN-3"
    after["items"].append(colliding)
    result = validate(before, after, before_meta, after_meta)
    assert "public_id_collision" in result["reason_codes"]


def test_duplicate_business_identity_is_blocked() -> None:
    before, after, before_meta, after_meta = publication_payloads()
    duplicate = deepcopy(after["items"][-1])
    duplicate["id"] = "different-public-id"
    after["items"].append(duplicate)
    result = validate(before, after, before_meta, after_meta)
    assert "duplicate_business_identity" in result["reason_codes"]


def test_business_addition_without_meta_count_update_is_blocked() -> None:
    before, after, before_meta, after_meta = publication_payloads()
    after_meta["business_count"] -= 1
    result = validate(before, after, before_meta, after_meta)
    assert "meta_business_count_mismatch" in result["reason_codes"]


def test_business_total_must_equal_item_count() -> None:
    before, after, before_meta, after_meta = publication_payloads()
    after["business_total"] -= 1
    after_meta["business_total"] -= 1
    result = validate(before, after, before_meta, after_meta)
    assert "business_business_total_mismatch" in result["reason_codes"]


def test_lifecycle_status_counts_must_conserve_total() -> None:
    before, after, before_meta, after_meta = publication_payloads()
    after["business_active"] = after_meta["business_active"] = 0
    result = validate(before, after, before_meta, after_meta)
    assert "business_business_active_mismatch" in result["reason_codes"]


def test_record_type_counts_must_conserve_total() -> None:
    before, after, before_meta, after_meta = publication_payloads()
    after["procurement_plan_total"] = after_meta["procurement_plan_total"] = 1
    result = validate(before, after, before_meta, after_meta)
    assert "business_procurement_plan_total_mismatch" in result["reason_codes"]


def test_failed_public_data_guard_is_blocking() -> None:
    before, after, before_meta, after_meta = publication_payloads()
    after["public_data_guard_status"] = after_meta["public_data_guard_status"] = "failed"
    result = validate(before, after, before_meta, after_meta)
    assert "public_data_guard_not_passed" in result["reason_codes"]


def test_credential_bearing_url_is_blocking_without_value_in_result() -> None:
    before, after, before_meta, after_meta = publication_payloads()
    after["items"][-1]["external_original_url"] = "https://example.test/?serviceKey=sensitive-value"
    result = validate(before, after, before_meta, after_meta)
    assert "credential_bearing_url_detected" in result["reason_codes"]
    assert "sensitive-value" not in str(result)


def test_raw_or_secret_payload_field_is_blocking() -> None:
    before, after, before_meta, after_meta = publication_payloads()
    after["items"][-1]["request_headers"] = {"example": "not-published"}
    result = validate(before, after, before_meta, after_meta)
    assert "raw_or_secret_field_detected" in result["reason_codes"]


def test_unrelated_public_news_change_is_blocking() -> None:
    payloads = publication_payloads()
    result = validate(*payloads, changed_paths=[*PUBLIC_PATHS, "frontend/public/data/news.json"])
    assert "changed_file_scope_invalid" in result["reason_codes"]


def test_mixed_code_and_data_change_is_blocking() -> None:
    payloads = publication_payloads()
    result = validate(*payloads, changed_paths=[*PUBLIC_PATHS, "src/example.py"])
    assert "changed_file_scope_invalid" in result["reason_codes"]


def test_semantically_safe_additive_publication_passes() -> None:
    result = validate(*publication_payloads())
    assert result["passed"] is True
    assert result["status"] == "CONTROLLED_PUBLICATION_SAFE"
    assert result["counts"] == {
        "baseline": 3,
        "candidate": 4,
        "net_new": 1,
        "removed": 0,
        "modified": 0,
        "public_id_collisions": 0,
        "duplicate_identities": 0,
    }
    assert result["security"]["passed"] is True


def test_semantic_validation_is_deterministic() -> None:
    payloads = publication_payloads()
    assert validate(*payloads) == validate(*deepcopy(payloads))


def test_d2b_public_source_metadata_must_be_consistent() -> None:
    before, after, before_meta, after_meta = publication_payloads()
    after["d2b_unified_status"] = after_meta["d2b_unified_status"] = "failed"
    result = validate(before, after, before_meta, after_meta)
    assert "d2b_unified_status_inconsistent" in result["reason_codes"]
