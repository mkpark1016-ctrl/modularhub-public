from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.aggregate_gdelt_shadow_samples import aggregate  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def candidate(
    item_id: str,
    title: str,
    classification: str,
    *,
    url: str,
    published_at: str,
    description: str,
    matched_strength: str = "excluded",
    exclusion: str = "",
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "title": title,
        "normalized_title": title.lower(),
        "description": description,
        "canonical_url": url,
        "normalized_url": url,
        "domain": url.split("/")[2],
        "published_at": published_at,
        "language": "en",
        "classification": classification,
        "relevance_score": 0 if classification == "irrelevant" else 90 if classification == "publish_candidate" else 60,
        "matched_strength": matched_strength,
        "classification_reason": "score_0" if classification == "irrelevant" else "score_90" if classification == "publish_candidate" else "score_60",
        "positive_reason_codes": [] if classification == "irrelevant" else ["strong_positive:modular construction"],
        "exclusion_reason_codes": [exclusion] if exclusion else [],
        "construction_context_terms": [] if classification == "irrelevant" else ["construction", "housing"],
        "non_construction_context_terms": [exclusion] if exclusion else [],
        "country_resolution_status": "not_applicable" if classification == "irrelevant" else "unresolved",
        "duplicate_group_id": "",
        "duplicate_reason": "",
        "representative_item_id": item_id,
    }


def write_sample(
    base: Path,
    *,
    sample_id: str,
    timestamp: str,
    status: str,
    items: list[dict[str, Any]],
    duplicate_suppressed: int = 0,
    transport: bool = True,
    quality: bool = True,
) -> None:
    base.mkdir(parents=True, exist_ok=True)
    publish = [item for item in items if item["classification"] == "publish_candidate"]
    review = [item for item in items if item["classification"] == "review_required"]
    irrelevant = [item for item in items if item["classification"] == "irrelevant"]
    malformed: list[dict[str, Any]] = []
    write_json(
        base / "run_control.json",
        {
            "schema_version": 1,
            "run_id": f"run-{sample_id}",
            "commit_sha": "abc123",
            "timestamp": timestamp,
            "validation_status": "passed",
        },
    )
    write_json(
        base / "report.json",
        {
            "schema_version": 1,
            "timestamp": timestamp,
            "status": status,
            "transport_acceptance_passed": transport,
            "source_integrity_checks_passed": transport,
            "request_attempt_count": 2 if transport else 1,
            "network_request_count": 2 if transport else 1,
            "http_response_count": 2 if transport else 0,
            "webngrams_request_count": 1,
            "gal_request_count": 1 if transport else 0,
            "doc_api_request_count": 0,
            "retry_count": 0,
            "fallback_count": 0,
            "public_json_unchanged": True,
            "db_unchanged": True,
            "env_unchanged": True,
            "checkpoint_unchanged": True,
            "production_publish_allowed": False,
        },
    )
    write_json(base / "download_manifest.json", {"schema_version": 1, "timestamp": timestamp})
    write_json(base / "candidates.json", {"items": items})
    (base / "manual_review.csv").write_text("item_id,title\n", encoding="utf-8")
    total = len(items)
    unique = total - duplicate_suppressed
    write_json(
        base / "live_review_report.json",
        {
            "schema_version": 1,
            "timestamp": timestamp,
            "source_mode": "live",
            "quality_pipeline_valid": quality,
            "pipeline_shadow_ready": transport and quality,
            "shadow_ready": transport and quality,
            "content_sample_usable": bool(publish or review),
            "production_publish_allowed": False,
            "public_json_unchanged": True,
            "db_unchanged": True,
            "env_unchanged": True,
            "total_input_count": total + duplicate_suppressed,
            "valid_input_count": total + duplicate_suppressed,
            "duplicate_group_count": 1 if duplicate_suppressed else 0,
            "duplicate_suppressed_count": duplicate_suppressed,
            "unique_valid_candidate_count": unique,
            "publish_candidate_count": len(publish),
            "review_required_count": len(review),
            "irrelevant_input_count": len(irrelevant) + duplicate_suppressed,
            "irrelevant_unique_count": len(irrelevant),
            "strong_match_count": len(publish) + len(review),
            "weak_match_count": 0,
            "excluded_context_count": len(irrelevant),
            "country_resolution_eligible_count": len(publish) + len(review),
            "country_resolution_success_count": 0,
            "country_resolution_success_ratio": "not_applicable" if not publish and not review else 0.0,
        },
    )
    (base / "live_review_report.md").write_text("# live review\n", encoding="utf-8")
    write_json(base / "publish_candidates.json", {"schema_version": 1, "items": publish})
    write_json(base / "review_required.json", {"schema_version": 1, "items": review})
    write_json(base / "irrelevant.json", {"schema_version": 1, "items": irrelevant})
    write_json(base / "malformed.json", {"schema_version": 1, "items": malformed})


def write_manifest(path: Path, samples_root: Path) -> None:
    write_json(
        path,
        {
            "schema_version": "1.0",
            "sample_set_id": "test-shadow-set",
            "description": "offline test manifest",
            "samples": [
                {
                    "sample_id": "sample-a",
                    "timestamp": "20211215000100",
                    "artifact_dir": str(samples_root / "sample-a"),
                    "expected_status": "success",
                    "enabled": True,
                },
                {
                    "sample_id": "sample-b",
                    "timestamp": "20211216000100",
                    "artifact_dir": str(samples_root / "sample-b"),
                    "expected_status": "success",
                    "enabled": True,
                },
                {
                    "sample_id": "sample-c",
                    "timestamp": "20211217000100",
                    "artifact_dir": str(samples_root / "sample-c"),
                    "expected_status": "failed",
                    "enabled": True,
                },
            ],
        },
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp_text:
        tmp = Path(tmp_text)
        samples_root = tmp / "samples"
        manifest = tmp / "manifest.json"
        output = tmp / "out"
        shared = candidate(
            "a-log4j",
            "Companies scramble to defend against newly discovered Log4j digital flaw",
            "irrelevant",
            url="https://alpha.test/log4j",
            published_at="2021-12-14T13:22:10.000Z",
            description="Security teams patch a software vulnerability in Log4j, a modular component used by digital systems.",
            exclusion="software_component",
        )
        shared_b = dict(shared, item_id="b-log4j", canonical_url="https://beta.test/log4j", normalized_url="https://beta.test/log4j", domain="beta.test")
        write_sample(samples_root / "sample-a", sample_id="sample-a", timestamp="20211215000100", status="success", items=[shared])
        write_sample(
            samples_root / "sample-b",
            sample_id="sample-b",
            timestamp="20211216000100",
            status="success",
            items=[
                shared_b,
                candidate(
                    "b-publish",
                    "Modular construction housing project opens",
                    "publish_candidate",
                    url="https://builder.test/modular-housing",
                    published_at="2021-12-15T10:00:00.000Z",
                    description="A modular construction housing project opens with factory built apartments.",
                    matched_strength="strong",
                ),
                candidate(
                    "b-review",
                    "Prefab developer expands factory project",
                    "review_required",
                    url="https://builder.test/prefab-factory",
                    published_at="2021-12-15T11:00:00.000Z",
                    description="A prefab developer expands a factory project for building modules.",
                    matched_strength="weak",
                ),
            ],
        )
        (samples_root / "sample-c").mkdir(parents=True)
        write_manifest(manifest, samples_root)

        summary = aggregate(manifest, output)
        require(summary["total_sample_count"] == 3, "sample count mismatch")
        require(summary["successful_sample_count"] == 2, "successful sample count mismatch")
        require(summary["incomplete_sample_count"] == 1, "incomplete sample count mismatch")
        require(summary["failed_sample_count"] == 0, "failed sample count mismatch")
        require(summary["content_sample_usable_count"] == 1, "content usable count mismatch")
        require(summary["cross_sample_duplicate_group_count"] == 1, "cross-sample duplicate group mismatch")
        require(summary["unique_candidates_before_cross_sample_dedup"] == 4, "pre cross-dedup count mismatch")
        require(summary["unique_candidates_after_cross_sample_dedup"] == 3, "post cross-dedup count mismatch")
        require(summary["classifier_precision_for_relevant"] == "not_applicable", "unlabeled precision must be not_applicable")
        require(summary["source_level_recall_status"] == "not_measurable_from_candidate_only_artifacts", "source recall warning missing")
        require(summary["evaluation_status"] == "insufficient_sample", "small sample should be insufficient")
        require(summary["production_publish_allowed"] is False, "production publish must stay false")
        for filename in [
            "shadow_evaluation_summary.json",
            "shadow_evaluation_summary.md",
            "run_matrix.csv",
            "candidate_pool.csv",
            "cross_sample_duplicate_groups.json",
            "reason_code_distribution.csv",
            "exclusion_reason_distribution.csv",
            "duplicate_reason_distribution.csv",
            "domain_distribution.csv",
            "timestamp_distribution.csv",
            "manual_labels_template.csv",
            "validation_errors.json",
        ]:
            require((output / filename).exists(), f"{filename} missing")
        duplicate_groups = json.loads((output / "cross_sample_duplicate_groups.json").read_text(encoding="utf-8"))
        require(len(duplicate_groups["items"]) == 1, "duplicate artifact mismatch")
        errors = json.loads((output / "validation_errors.json").read_text(encoding="utf-8"))["items"]
        require(any(error["sample_id"] == "sample-c" for error in errors), "missing sample error not recorded")

        labels = output / "manual_labels.csv"
        with labels.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "sample_id",
                    "timestamp",
                    "candidate_id",
                    "title",
                    "canonical_url",
                    "observed_classification",
                    "observed_reason",
                    "ground_truth_label",
                    "ground_truth_reason",
                    "reviewer",
                    "reviewed_at",
                    "notes",
                ],
            )
            writer.writeheader()
            writer.writerow({"sample_id": "sample-a", "candidate_id": "a-log4j", "ground_truth_label": "irrelevant"})
            writer.writerow({"sample_id": "sample-b", "candidate_id": "b-publish", "ground_truth_label": "relevant_building_modular"})
            writer.writerow({"sample_id": "sample-b", "candidate_id": "b-review", "ground_truth_label": "relevant_building_modular"})
            writer.writerow({"sample_id": "sample-b", "candidate_id": "b-log4j", "ground_truth_label": "irrelevant"})
        labeled_summary = aggregate(manifest, output / "labeled", labels)
        require(labeled_summary["labeled_candidate_count"] == 4, "labeled count mismatch")
        require(labeled_summary["unlabeled_candidate_count"] == 0, "unlabeled count mismatch")
        require(labeled_summary["classifier_precision_for_relevant"] == 1.0, "relevant precision mismatch")
        require(labeled_summary["classifier_precision_for_irrelevant"] == 1.0, "irrelevant precision mismatch")
        require(labeled_summary["classification_recall_within_candidate_pool"] == 1.0, "candidate-pool recall mismatch")
        require(labeled_summary["label_coverage_rate"] == 1.0, "label coverage mismatch")

        cli_output = tmp / "cli"
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "aggregate_gdelt_shadow_samples.py"),
                "--manifest",
                str(manifest),
                "--output-dir",
                str(cli_output),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        parsed = json.loads(result.stdout)
        require(parsed["external_http_request_count"] == 0, "aggregator must not report HTTP requests")
        require((cli_output / "shadow_evaluation_summary.json").exists(), "CLI summary missing")

    print("GDELT SHADOW SAMPLE AGGREGATOR TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
