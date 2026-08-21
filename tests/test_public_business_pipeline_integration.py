from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.export_public_json as export_public_json
from scripts.export_public_json import parse_args
from scripts.integrations.business.base import NormalizedBusinessRecord
from scripts.integrations.business.public_pipeline import (
    UnifiedPublicInputError,
    build_controlled_publication_payloads,
    integrate_optional_unified_business,
    resolve_published_d2b_metadata,
)
from scripts.integrations.business.public_projection import build_public_projection


GENERATED_AT = "2026-08-20T07:23:09+00:00"


class EmptyFrame:
    empty = True
    columns: list[str] = []


def canonical(
    external_id: str,
    *,
    source: str = "d2b",
    record_type: str = "procurement_plan",
    title: str = "모듈러 간부숙소 신축",
    source_url: str = "https://www.d2b.go.kr/",
) -> NormalizedBusinessRecord:
    return NormalizedBusinessRecord(
        source=source,
        source_record_type=record_type,
        external_id=external_id,
        title=title,
        issuing_organization="방위사업청" if source == "d2b" else "한국토지주택공사",
        category="시설공사",
        estimated_amount=100_000_000,
        published_at="2026-08-20",
        deadline_at="2026-08-30",
        status="공고",
        contract_method="일반경쟁",
        source_url=source_url,
        collected_at=GENERATED_AT,
    )


def write_inputs(tmp_path: Path, records: list[NormalizedBusinessRecord]) -> tuple[Path, Path]:
    records_path = tmp_path / "unified_records.json"
    summary_path = tmp_path / "unified_summary.json"
    records_path.write_text(
        json.dumps([record.as_dict() for record in records], ensure_ascii=False),
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps({"records_output": len(records), "generated_at": GENERATED_AT}),
        encoding="utf-8",
    )
    return records_path, summary_path


def integrate(tmp_path: Path, records: list[NormalizedBusinessRecord], existing: list[dict] | None = None):
    records_path, summary_path = write_inputs(tmp_path, records)
    return integrate_optional_unified_business(
        existing or [],
        unified_records_path=records_path,
        unified_summary_path=summary_path,
    )


def test_default_pipeline_without_unified_input_is_semantically_unchanged() -> None:
    existing = [{"id": 1, "title": "기존 사업", "source": "G2B"}]
    result, report = integrate_optional_unified_business(existing)
    assert result == existing
    assert result is not existing
    assert report["integration_enabled"] is False
    assert report["default_pipeline_unchanged"] is True
    assert parse_args([]).unified_business_records is None


def test_explicit_unified_artifact_applies_projection_and_existing_merge(tmp_path: Path) -> None:
    merged, report = integrate(tmp_path, [canonical("D2B-1")])
    assert len(merged) == 1
    assert report["integration_enabled"] is True
    assert report["publishable_count"] == 1
    assert report["net_new_count"] == 1
    assert report["merge_contract"] == "src.public_data_policy.merge_public_items"


def test_95_record_contract_keeps_current_one_publishable_policy_result(tmp_path: Path) -> None:
    records = [canonical("D2B-PASS")]
    records += [canonical(f"D2B-{index}", title="일반 시설 보수") for index in range(64)]
    records += [
        canonical(f"G2B-{index}", source="g2b", title="일반 시설 용역", source_url="https://www.g2b.go.kr/")
        for index in range(20)
    ]
    records += [canonical(f"LH-{index}", source="lh") for index in range(10)]
    merged, report = integrate(tmp_path, records)
    assert report["unified_input_count"] == 95
    assert report["publishable_count"] == 1
    assert report["filtered_count"] == 94
    assert report["net_new_count"] == 1
    assert len(merged) == 1


def test_same_lineage_existing_record_is_not_duplicated(tmp_path: Path) -> None:
    value = canonical("D2B-1")
    existing = build_public_projection(
        [value], {"items": []}, unified_summary={"generated_at": GENERATED_AT}
    )[0][0]
    merged, report = integrate(tmp_path, [value], [existing])
    assert merged == [existing]
    assert report["existing_matches"] == 1
    assert report["net_new_count"] == 0


def test_public_id_collision_is_blocking(tmp_path: Path) -> None:
    value = canonical("D2B-1")
    existing = build_public_projection(
        [value], {"items": []}, unified_summary={"generated_at": GENERATED_AT}
    )[0][0]
    existing["title"] = "충돌하는 기존 제목"
    paths = write_inputs(tmp_path, [value])
    with pytest.raises(UnifiedPublicInputError, match="public_id_collision"):
        integrate_optional_unified_business(
            [existing], unified_records_path=paths[0], unified_summary_path=paths[1]
        )


def test_missing_explicit_artifact_fails_but_default_does_not(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(UnifiedPublicInputError, match="UNIFIED_PUBLIC_INPUT_INCOMPLETE"):
        integrate_optional_unified_business([], unified_records_path=missing)
    with pytest.raises(UnifiedPublicInputError, match="UNIFIED_PUBLIC_INPUT_NOT_FOUND"):
        integrate_optional_unified_business(
            [], unified_records_path=missing, unified_summary_path=missing
        )
    assert integrate_optional_unified_business([])[1]["integration_enabled"] is False


def test_credential_url_is_blocked_before_merge(tmp_path: Path) -> None:
    paths = write_inputs(
        tmp_path,
        [canonical("D2B-1", source_url="https://example.test/item?serviceKey=secret")],
    )
    with pytest.raises(ValueError, match="credential-bearing source_url"):
        integrate_optional_unified_business(
            [], unified_records_path=paths[0], unified_summary_path=paths[1]
        )


def test_existing_payload_preservation_and_deterministic_order(tmp_path: Path) -> None:
    existing = [{"id": 7, "source": "G2B", "source_name": "G2B", "source_type": "bid",
                 "bid_no": "OLD-1", "bid_order": "", "title": "기존 사업",
                 "organization": "기존 기관", "posted_at": "2026-08-01"}]
    records = [canonical("D2B-2"), canonical("D2B-1")]
    first, first_report = integrate(tmp_path, records, existing)
    second, second_report = integrate(tmp_path, list(reversed(records)), existing)
    assert first == second
    assert first_report == second_report
    assert existing[0] in first
    assert first_report["existing_removed_count"] == 0


def test_korean_utf8_round_trip_and_no_network_client_in_integration_module(tmp_path: Path) -> None:
    merged, report = integrate(tmp_path, [canonical("한글-1", title="모듈러 군 숙소 신축")])
    serialized = json.dumps({"items": merged, "report": report}, ensure_ascii=False)
    output = tmp_path / "candidate.json"
    output.write_text(serialized, encoding="utf-8")
    assert json.loads(output.read_text(encoding="utf-8"))["items"][0]["title"] == "모듈러 군 숙소 신축"
    source = Path("scripts/integrations/business/public_pipeline.py").read_text(encoding="utf-8")
    assert "import requests" not in source
    assert "httpx" not in source
    assert "urlopen" not in source


def test_controlled_publication_recalculates_metadata_and_separates_d2b_status(
    tmp_path: Path,
) -> None:
    existing = [{
        "id": "old-1",
        "source": "G2B",
        "source_type": "bid",
        "opportunity_status": "active",
        "title": "기존 사업",
    }]
    merged, report = integrate(tmp_path, [canonical("D2B-1")], existing)
    public = {
        "generated_at": "2026-08-19T00:00:00+09:00",
        "previous_news_count": 10,
        "merged_news_count": 10,
        "d2b_status": "disabled_stopped",
        "d2b_legacy_status": "disabled_stopped",
        "d2b_gw_migration_required": True,
        "procurement_plan_source_status": {"G2B": "success"},
        "items": existing,
    }
    meta = {
        **{key: value for key, value in public.items() if key != "items"},
        "business_count": 1,
        "sources": ["G2B"],
    }
    published_at = datetime(2026, 8, 20, 18, 0, tzinfo=timezone.utc)

    business_candidate, meta_candidate = build_controlled_publication_payloads(
        public,
        meta,
        merged,
        report,
        publication_time=published_at,
    )

    assert business_candidate["business_total"] == 2
    assert business_candidate["business_active"] == 2
    assert business_candidate["business_closed"] == 0
    assert business_candidate["business_unknown"] == 0
    assert business_candidate["bid_total"] == 1
    assert business_candidate["procurement_plan_total"] == 1
    assert business_candidate["public_agency_contest_total"] == 0
    assert business_candidate["public_data_guard_status"] == "passed"
    assert "business 1 -> 2" in business_candidate["public_data_guard_message"]
    assert business_candidate["d2b_status"] == "success"
    assert business_candidate["d2b_legacy_status"] == "disabled_stopped"
    assert business_candidate["d2b_gw_migration_required"] is False
    assert business_candidate["d2b_unified_status"] == "success"
    assert business_candidate["d2b_unified_public_count"] == 1
    assert business_candidate["procurement_plan_last_collected_at"] == GENERATED_AT
    assert business_candidate["procurement_plan_source_status"] == {
        "G2B": "success",
        "D2B": "success",
    }
    assert meta_candidate["business_count"] == 2
    assert meta_candidate["business_total"] == 2
    assert "D2B" in meta_candidate["sources"]
    assert "items" not in meta_candidate


def test_controlled_publication_rejects_non_conserving_candidate(tmp_path: Path) -> None:
    merged, report = integrate(tmp_path, [canonical("D2B-1")])
    with pytest.raises(UnifiedPublicInputError, match="COUNT_MISMATCH"):
        build_controlled_publication_payloads({}, {}, merged + [dict(merged[0])], report)


def test_published_d2b_metadata_requires_previous_success_and_actual_item() -> None:
    legacy = resolve_published_d2b_metadata(
        {},
        [],
        legacy_status="disabled_stopped",
        legacy_message="legacy disabled",
    )
    assert legacy["d2b_status"] == "disabled_stopped"
    assert legacy["d2b_legacy_status"] == "disabled_stopped"
    assert legacy["d2b_gw_migration_required"] is True
    assert "d2b_unified_status" not in legacy

    item_without_metadata = resolve_published_d2b_metadata(
        {},
        [{"source": "D2B", "source_type": "procurement_plan"}],
        legacy_status="disabled_stopped",
        legacy_message="legacy disabled",
    )
    assert item_without_metadata["d2b_status"] == "disabled_stopped"
    assert "d2b_unified_status" not in item_without_metadata

    stale = resolve_published_d2b_metadata(
        {"d2b_unified_status": "success", "d2b_unified_public_count": 9},
        [],
        legacy_status="disabled_stopped",
        legacy_message="legacy disabled",
    )
    assert stale["d2b_status"] == "disabled_stopped"
    assert "d2b_unified_status" not in stale
    assert "d2b_unified_public_count" not in stale


def test_published_d2b_metadata_recalculates_count_and_preserves_source_evidence() -> None:
    item = {
        "id": "d2b-plan-1",
        "source": "D2B",
        "source_type": "procurement_plan",
    }
    result = resolve_published_d2b_metadata(
        {
            "d2b_unified_status": "success",
            "d2b_unified_public_count": 99,
            "d2b_unified_last_collected_at": GENERATED_AT,
        },
        [item],
        legacy_status="disabled_stopped",
        legacy_message="legacy disabled",
        procurement_plan_source_status={"나라장터": "failed"},
    )
    assert result["d2b_status"] == "success"
    assert result["d2b_unified_status"] == "success"
    assert result["d2b_unified_public_count"] == 1
    assert result["d2b_legacy_status"] == "disabled_stopped"
    assert result["d2b_gw_migration_required"] is False
    assert result["d2b_unified_last_collected_at"] == GENERATED_AT
    assert result["procurement_plan_source_status"] == {
        "나라장터": "failed",
        "D2B": "success",
    }


def test_published_d2b_metadata_does_not_copy_sensitive_previous_fields() -> None:
    result = resolve_published_d2b_metadata(
        {
            "d2b_unified_status": "success",
            "request_headers": {"serviceKey": "do-not-copy"},
            "raw_response": "do-not-copy",
        },
        [{"source": "D2B", "source_type": "procurement_plan"}],
        legacy_status="disabled_stopped",
        legacy_message="legacy disabled",
    )
    serialized = json.dumps(result)
    assert "serviceKey" not in serialized
    assert "do-not-copy" not in serialized
    assert "raw_response" not in serialized


def test_default_export_retains_217_item_d2b_publication_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = [
        {
            "id": f"g2b-{index}",
            "source": "G2B",
            "source_type": "bid",
            "bid_no": f"BID-{index}",
            "title": f"기존 사업 {index}",
            "organization": "기존 기관",
            "posted_at": "2026-08-01",
            "due_at": "",
            "opportunity_status": "unknown",
            "is_closed": False,
            "days_until_deadline": None,
            "closed_at": None,
            "last_seen_at": "2026-08-20T00:00:00+09:00",
            "lifecycle_reason": "no_deadline",
        }
        for index in range(216)
    ]
    target_id = "d2b_procurement_plan:d2b:procurement_plan:2026-11890"
    d2b_item = {
        "id": target_id,
        "source": "D2B",
        "source_name": "D2B",
        "source_type": "procurement_plan",
        "plan_no": "2026-11890",
        "source_record_id": "2026-11890",
        "title": "26-J-모듈러형 간부숙소 30실 신축 설계용역",
        "organization": "제9해병여단",
        "posted_at": "2026-08-20",
        "due_at": "",
        "opportunity_status": "unknown",
        "is_closed": False,
        "days_until_deadline": None,
        "closed_at": None,
        "last_seen_at": "2026-08-20T16:23:09+09:00",
        "lifecycle_reason": "no_deadline",
    }
    previous = {
        "d2b_status": "success",
        "d2b_unified_status": "success",
        "d2b_unified_public_count": 1,
        "d2b_unified_last_collected_at": "2026-08-20T16:23:09+09:00",
        "d2b_legacy_status": "disabled_stopped",
        "d2b_gw_migration_required": False,
        "items": baseline + [d2b_item],
    }

    monkeypatch.setattr(
        export_public_json,
        "load_existing_payload",
        lambda name: previous if name == "business.json" else {"items": []},
    )
    monkeypatch.setattr(
        export_public_json,
        "load_git_head_payload",
        lambda name: previous if name == "business.json" else {"items": []},
    )
    monkeypatch.setattr(export_public_json, "load_git_history_payloads", lambda *args, **kwargs: [])
    monkeypatch.setattr(export_public_json, "load_items_dataframe", EmptyFrame)
    monkeypatch.setattr(export_public_json, "load_latest_details", lambda: {})
    monkeypatch.setattr(export_public_json, "load_collect_logs_dataframe", lambda **kwargs: EmptyFrame())
    monkeypatch.setattr(export_public_json, "load_removal_allowlist", lambda: {})

    def write_json(name: str, payload: object) -> None:
        (tmp_path / name).write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    monkeypatch.setattr(export_public_json, "write_json", write_json)

    assert export_public_json.main() == 0
    business = json.loads((tmp_path / "business.json").read_text(encoding="utf-8"))
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    retained = next(item for item in business["items"] if item["id"] == target_id)

    assert len(business["items"]) == 217
    assert retained == d2b_item
    assert business["d2b_status"] == "success"
    assert business["d2b_unified_status"] == "success"
    assert business["d2b_unified_public_count"] == 1
    assert business["d2b_legacy_status"] == "disabled_stopped"
    assert business["d2b_gw_migration_required"] is False
    assert business["d2b_unified_last_collected_at"] == "2026-08-20T16:23:09+09:00"
    assert business["procurement_plan_source_status"] == {"D2B": "success"}
    assert not any(str(warning).startswith("D2B:") for warning in business["warnings"])
    assert meta["business_count"] == len(business["items"])
    assert meta["d2b_unified_public_count"] == 1
