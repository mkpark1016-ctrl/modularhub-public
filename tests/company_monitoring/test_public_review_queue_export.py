from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.company_monitoring.export_review_queue_public import export_public_review_queue
from scripts.company_monitoring.publish_review_queue_public import (
    publish_from_artifacts,
    validate_source_run_metadata,
)


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sample_queue() -> dict[str, object]:
    return {
        "schema_version": "test",
        "generated_at": "2026-07-18T09:00:00Z",
        "review_queue": [
            {
                "candidate_id": "cand-a",
                "company_id": "kumkang-kind",
                "source_type": "naver_search",
                "review_status": "pending",
                "title": "금강공업 모듈러 후보",
                "source_url": "https://news.example.com/a",
                "published_at": "2026-07-18",
                "fetched_at": "2026-07-18T08:00:00Z",
                "query": "금강공업 모듈러",
                "matched_alias": "금강공업",
                "promotion_blockers": ["news_search_candidate_requires_review"],
                "duplicate_of": None,
                "raw_ref": "internal-path-should-not-export",
                "summary": "본문 요약은 이번 공개 계약에 포함하지 않는다.",
            }
        ],
    }


def sample_digest() -> dict[str, object]:
    return {
        "generated_at": "2026-07-18T09:00:00Z",
        "candidate_total": 1,
        "raw_candidate_count": 1,
        "raw_rejected_record_count": 0,
        "final_status_counts": {"pending": 1, "duplicate": 0, "rejected": 0, "conflict": 0, "accepted": 0},
        "quality_flag_counts": {"raw_rejected": 0},
        "source_counts": {"naver_search": 1},
    }


def test_export_sanitizes_internal_fields_and_counts(tmp_path: Path) -> None:
    input_path = tmp_path / "review_queue.json"
    digest_path = tmp_path / "digest.json"
    output_path = tmp_path / "public.json"
    manifest_path = tmp_path / "manifest.json"
    write_json(input_path, sample_queue())
    write_json(digest_path, sample_digest())

    first = export_public_review_queue(
        input_path=input_path,
        digest_path=digest_path,
        output_path=output_path,
        manifest_output_path=manifest_path,
        source_run_commit="abc123",
    )
    public_payload = json.loads(output_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    second = export_public_review_queue(
        input_path=input_path,
        digest_path=digest_path,
        output_path=output_path,
        manifest_output_path=manifest_path,
        source_run_commit="abc123",
    )

    assert first == second
    assert first["item_count"] == 1
    assert public_payload["items"][0]["candidateId"] == "cand-a"
    assert public_payload["items"][0]["companyName"] == "금강공업"
    serialized = json.dumps(public_payload, ensure_ascii=False)
    assert "raw_ref" not in serialized
    assert "summary" not in serialized
    assert "internal-path" not in serialized
    assert manifest["counts"]["pending"] == 1
    assert manifest["counts"]["sourceCounts"]["dart"] == 0
    assert manifest["counts"]["sourceCounts"]["naver_search"] == 1
    assert manifest["configuredSources"] == ["dart", "naver"]
    assert manifest["sourceCounts"]["dart"] == 0
    assert manifest["sourceCounts"]["naver"] == 1


def test_export_writes_source_run_metadata(tmp_path: Path) -> None:
    input_path = tmp_path / "review_queue.json"
    digest_path = tmp_path / "digest.json"
    output_path = tmp_path / "public.json"
    manifest_path = tmp_path / "manifest.json"
    write_json(input_path, sample_queue())
    write_json(digest_path, sample_digest())

    export_public_review_queue(
        input_path=input_path,
        digest_path=digest_path,
        output_path=output_path,
        manifest_output_path=manifest_path,
        source_run_id="12345",
        source_run_commit="abc123",
        source_workflow="Company Intelligence Monitor",
        source_branch="main",
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["sourceRunId"] == "12345"
    assert manifest["sourceCommit"] == "abc123"
    assert manifest["sourceWorkflow"] == "Company Intelligence Monitor"
    assert manifest["sourceBranch"] == "main"


def test_validate_source_run_metadata_rejects_wrong_workflow() -> None:
    with pytest.raises(ValueError, match="workflow"):
        validate_source_run_metadata(
            {
                "id": 1,
                "name": "Other Workflow",
                "path": ".github/workflows/company-intelligence-monitor.yml",
                "status": "completed",
                "conclusion": "success",
                "head_branch": "main",
                "head_sha": "abc",
                "event": "workflow_dispatch",
            }
        )


def test_publish_from_artifacts_validates_and_exports(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    queue_dir = artifact_root / "company-intelligence-review-queue"
    digest_dir = artifact_root / "company-intelligence-digest"
    audit_dir = artifact_root / "company-intelligence-audit"
    queue_dir.mkdir(parents=True)
    digest_dir.mkdir(parents=True)
    audit_dir.mkdir(parents=True)
    write_json(queue_dir / "review_queue.json", sample_queue())
    write_json(digest_dir / "latest_digest.json", sample_digest())
    write_json(
        audit_dir / "audit-summary.json",
        {
            "raw_source_record_count": 1,
            "raw_candidate_record_count": 1,
            "raw_rejected_record_count": 0,
            "non_candidate_control_record_count": 0,
            "normalized_unique_count": 1,
            "final_status_counts": {"pending": 1, "duplicate": 0, "rejected": 0, "conflict": 0, "accepted": 0},
            "status_conservation": {"valid": True},
            "multi_status_candidate_count": 0,
            "orphan_candidate_count": 0,
            "duplicate_integrity": {
                "missing_duplicate_of_count": 0,
                "self_duplicate_of_count": 0,
                "duplicate_cycle_count": 0,
                "cross_company_duplicate_count": 0,
            },
            "secret_exposure_detected": False,
        },
    )
    metadata_path = tmp_path / "source-run.json"
    write_json(
        metadata_path,
        {
            "id": 12345,
            "name": "Company Intelligence Monitor",
            "path": ".github/workflows/company-intelligence-monitor.yml",
            "status": "completed",
            "conclusion": "success",
            "head_branch": "main",
            "head_sha": "abc123",
            "event": "workflow_dispatch",
        },
    )

    result = publish_from_artifacts(
        artifact_root=artifact_root,
        source_run_metadata_path=metadata_path,
        output_path=tmp_path / "public.json",
        manifest_output_path=tmp_path / "manifest.json",
        lookback_days=30,
    )

    assert result["item_count"] == 1
    assert result["source_run_id"] == "12345"
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["sourceRunId"] == "12345"
    assert manifest["sourceCounts"]["dart"] == 0
    assert manifest["sourceCounts"]["naver"] == 1


def test_export_rejects_missing_review_queue(tmp_path: Path) -> None:
    input_path = tmp_path / "bad.json"
    digest_path = tmp_path / "digest.json"
    write_json(input_path, {"items": []})
    write_json(digest_path, sample_digest())
    with pytest.raises(ValueError, match="review_queue"):
        export_public_review_queue(
            input_path=input_path,
            digest_path=digest_path,
            output_path=tmp_path / "out.json",
            manifest_output_path=tmp_path / "manifest.json",
        )


def test_export_rejects_secret_like_payload(tmp_path: Path) -> None:
    payload = sample_queue()
    payload["review_queue"][0]["title"] = "crtfc_key=SHOULD_NOT_EXPORT"
    input_path = tmp_path / "review_queue.json"
    digest_path = tmp_path / "digest.json"
    write_json(input_path, payload)
    write_json(digest_path, sample_digest())
    with pytest.raises(ValueError, match="secret-like"):
        export_public_review_queue(
            input_path=input_path,
            digest_path=digest_path,
            output_path=tmp_path / "out.json",
            manifest_output_path=tmp_path / "manifest.json",
        )
