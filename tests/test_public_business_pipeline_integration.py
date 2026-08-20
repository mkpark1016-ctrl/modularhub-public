from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.export_public_json import parse_args
from scripts.integrations.business.base import NormalizedBusinessRecord
from scripts.integrations.business.public_pipeline import (
    UnifiedPublicInputError,
    integrate_optional_unified_business,
)
from scripts.integrations.business.public_projection import build_public_projection


GENERATED_AT = "2026-08-20T07:23:09+00:00"


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
