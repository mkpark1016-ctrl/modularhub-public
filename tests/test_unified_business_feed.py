from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.integrations.business.base import NormalizedBusinessRecord
from scripts.integrations.business.run_unified_business_feed import main as run_unified_business_feed_main
from scripts.integrations.business.unified import (
    build_unified_business_feed,
    load_canonical_records,
    source_identity,
    write_unified_staging_outputs,
)


def record(
    source: str,
    record_type: str,
    external_id: str,
    title: str,
    *,
    organization: str = "한국토지주택공사",
    published_at: str | None = "2026-08-18",
    deadline_at: str | None = "2026-08-25",
    source_url: str | None = None,
    collected_at: str | None = "2026-08-18T02:00:00+00:00",
    source_updated_at: str | None = None,
    amount: int | None = 100_000_000,
) -> NormalizedBusinessRecord:
    return NormalizedBusinessRecord(
        source=source,
        source_record_type=record_type,
        external_id=external_id,
        title=title,
        issuing_organization=organization,
        estimated_amount=amount,
        published_at=published_at,
        deadline_at=deadline_at,
        source_url=source_url,
        collected_at=collected_at,
        source_updated_at=source_updated_at,
    )


def canonical_fixture() -> list[NormalizedBusinessRecord]:
    return [
        record("lh", "procurement_plan", "LH-PLAN-1", "LH 모듈러 주택 발주계획"),
        record("lh", "bid_notice", "LH-BID-1", "LH 모듈러 주택 입찰공고"),
        record("g2b", "pre_spec", "G2B-SPEC-1", "LH 모듈러 학교 사전규격"),
        record("d2b", "procurement_plan", "D2B-PLAN-1", "군 모듈러 시설 조달계획", organization="방위사업청"),
        record("d2b", "bid_notice", "D2B-BID-1", "군 모듈러 시설 입찰공고", organization="국방시설본부"),
    ]


def test_unique_records_and_source_provenance_are_preserved() -> None:
    unified, summary = build_unified_business_feed(canonical_fixture())

    assert len(unified) == 5
    assert summary["records_input"] == 5
    assert summary["records_output"] == 5
    assert summary["source_counts"] == {"d2b": 2, "g2b": 1, "lh": 2}
    assert summary["record_type_counts"] == {"bid_notice": 2, "pre_spec": 1, "procurement_plan": 2}
    assert summary["sources"]["lh"]["source_role"] == "primary"
    assert summary["sources"]["g2b"]["source_role"] == "lh_fallback"
    assert summary["sources"]["d2b"]["source_role"] == "independent"


def test_exact_same_source_duplicate_is_removed() -> None:
    duplicate = record("lh", "bid_notice", "LH-BID-1", "동일 공고")
    unified, summary = build_unified_business_feed([duplicate, duplicate])

    assert len(unified) == 1
    assert summary["exact_duplicates_removed"] == 1
    assert summary["identity_conflict_count"] == 0


def test_same_external_id_from_different_sources_is_retained() -> None:
    unified, summary = build_unified_business_feed(
        [
            record("lh", "bid_notice", "123", "LH 공고"),
            record("d2b", "bid_notice", "123", "D2B 공고", organization="방위사업청"),
        ]
    )

    assert len(unified) == 2
    assert summary["exact_duplicates_removed"] == 0


def test_cross_source_match_is_candidate_without_collapsing_records() -> None:
    shared = {
        "record_type": "procurement_plan",
        "title": "모듈러 주택 발주 계획",
        "organization": "한국토지주택공사",
        "published_at": "2026-08-18",
    }
    unified, summary = build_unified_business_feed(
        [
            record("lh", external_id="LH-1", **shared),
            record("g2b", external_id="G2B-1", **shared),
        ]
    )

    assert len(unified) == 2
    assert summary["cross_source_candidate_count"] == 1
    candidate = summary["cross_source_candidates"][0]
    assert candidate["match_basis"] == ["normalized_title", "normalized_organization", "published_at", "deadline_at"]
    assert {item["source"] for item in candidate["records"]} == {"lh", "g2b"}


def test_cross_source_candidate_requires_matching_organization_and_date() -> None:
    records = [
        record("lh", "bid_notice", "LH-1", "같은 제목", organization="한국토지주택공사"),
        record("d2b", "bid_notice", "D2B-1", "같은 제목", organization="방위사업청"),
        record(
            "g2b",
            "bid_notice",
            "G2B-1",
            "같은 제목",
            organization="한국토지주택공사",
            published_at="2026-08-19",
            deadline_at="2026-08-26",
        ),
    ]
    _, summary = build_unified_business_feed(records)
    assert summary["cross_source_candidate_count"] == 0


def test_generic_d2b_source_url_is_never_used_as_identity() -> None:
    records = [
        record("d2b", "bid_notice", "D2B-1", "첫 번째", organization="방위사업청", source_url="https://www.d2b.go.kr/"),
        record("d2b", "bid_notice", "D2B-2", "두 번째", organization="방위사업청", source_url="https://www.d2b.go.kr/"),
    ]
    unified, summary = build_unified_business_feed(records)

    assert len(unified) == 2
    assert summary["exact_duplicates_removed"] == 0


def test_identity_conflict_is_reported_and_newest_record_wins() -> None:
    older = record(
        "d2b",
        "procurement_plan",
        "D2B-1",
        "이전 제목",
        organization="방위사업청",
        amount=100,
        source_updated_at="2026-08-18T01:00:00+00:00",
    )
    newer = replace(
        older,
        title="최신 제목",
        estimated_amount=200,
        source_updated_at="2026-08-18T03:00:00+00:00",
    )

    unified, summary = build_unified_business_feed([newer, older])

    assert len(unified) == 1
    assert unified[0].title == "최신 제목"
    assert summary["exact_duplicates_removed"] == 0
    assert summary["identity_conflict_records_removed"] == 1
    assert summary["identity_conflict_count"] == 1
    assert summary["identity_conflicts"][0]["differing_core_fields"] == ["title", "estimated_amount"]


def test_output_and_summary_are_deterministic_for_shuffled_input() -> None:
    records = canonical_fixture()
    first_records, first_summary = build_unified_business_feed(records)
    second_records, second_summary = build_unified_business_feed(list(reversed(records)))

    assert [record.as_dict() for record in first_records] == [record.as_dict() for record in second_records]
    assert first_summary == second_summary


def test_staging_writer_emits_only_deterministic_normalized_artifacts(tmp_path: Path) -> None:
    records, summary = build_unified_business_feed(canonical_fixture())
    write_unified_staging_outputs(records, summary, tmp_path)

    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "unified_business_records.json",
        "unified_business_summary.json",
    ]
    written_records = json.loads((tmp_path / "unified_business_records.json").read_text(encoding="utf-8"))
    written_summary = json.loads((tmp_path / "unified_business_summary.json").read_text(encoding="utf-8"))
    assert len(written_records) == 5
    assert written_summary["security"] == {
        "credential_urls_detected": 0,
        "normalized_records_only": True,
        "passed": True,
        "raw_payload_fields_detected": 0,
    }
    artifact_text = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.iterdir()).lower()
    assert "servicekey=" not in artifact_text
    assert "authorization" not in artifact_text
    assert "raw_response" not in artifact_text


def test_credential_bearing_urls_and_raw_fields_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="credential-bearing source_url"):
        build_unified_business_feed(
            [record("lh", "bid_notice", "LH-1", "공고", source_url="https://example.test/item?serviceKey=secret")]
        )

    raw_path = tmp_path / "records.json"
    payload = record("lh", "bid_notice", "LH-1", "공고").as_dict()
    payload["raw_response"] = {"secret": "value"}
    raw_path.write_text(json.dumps([payload], ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="raw or sensitive fields"):
        load_canonical_records(raw_path)


def test_offline_runner_combines_lh_artifact_with_embedded_g2b_and_d2b(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lh_path = tmp_path / "lh_records.json"
    d2b_path = tmp_path / "d2b_records.json"
    output_dir = tmp_path / "out"
    lh_records = canonical_fixture()[:3]
    d2b_records = canonical_fixture()[3:]
    lh_path.write_text(json.dumps([item.as_dict() for item in lh_records], ensure_ascii=False), encoding="utf-8")
    d2b_path.write_text(json.dumps([item.as_dict() for item in d2b_records], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_unified_business_feed.py",
            "--lh-records",
            str(lh_path),
            "--d2b-records",
            str(d2b_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert run_unified_business_feed_main() == 0
    summary = json.loads((output_dir / "unified_business_summary.json").read_text(encoding="utf-8"))
    assert summary["source_counts"] == {"d2b": 2, "g2b": 1, "lh": 2}
    assert summary["records_output"] == 5


def test_source_identity_never_uses_source_url() -> None:
    value = record("d2b", "bid_notice", "D2B-1", "공고", organization="방위사업청", source_url="https://www.d2b.go.kr/")
    assert source_identity(value) == ("d2b", "bid_notice", "D2B-1")
