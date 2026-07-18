from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.company_monitoring.export_review_queue_public import export_public_review_queue


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
