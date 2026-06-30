from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "verify-gdelt-webngrams-live.yml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def normalize_for_hash(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: normalize_for_hash(item)
            for key, item in sorted(value.items())
            if key
            not in {
                "checked_at",
                "generated_at",
                "normalized_result_hash",
                "output_file_hashes",
                "source_artifact_hash",
            }
        }
    if isinstance(value, list):
        return [normalize_for_hash(item) for item in value]
    return value


def load_review_artifacts(directory: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for filename in [
        "live_review_report.json",
        "publish_candidates.json",
        "review_required.json",
        "irrelevant.json",
        "malformed.json",
        "duplicate_groups.json",
        "country_resolution.json",
        "processing_manifest.json",
    ]:
        payload[filename] = json.loads((directory / filename).read_text(encoding="utf-8"))
    return normalize_for_hash(payload)


def run_fixture_probe(probe_dir: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "probe_gdelt_webngrams.py"),
            "--fixture",
            "--max-candidates",
            "20",
            "--output-dir",
            str(probe_dir),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def adapt_probe_report_for_live(probe_dir: Path) -> Path:
    report_path = probe_dir / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report.pop("mode", None)
    report["run_id"] = "probe-fixture-live-adapter"
    report["config_fingerprint"] = "fixture-config-fingerprint"
    report["query_fingerprint"] = "fixture-query-fingerprint"
    report["transport_acceptance_passed"] = True
    report["10.10-B1_live_accepted"] = True
    report["http_request_count"] = 2
    report["network_request_count"] = 2
    report["doc_api_request_count"] = 0
    for key in ("checked_at", "started_at", "completed_at"):
        if key in report:
            report[key] = "2026-06-30T00:00:00Z"
    report["duration_seconds"] = 0
    live_report = probe_dir / "live_report.json"
    live_report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return live_report


def run_live_review(probe_dir: Path, review_dir: Path, live_report: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "review_gdelt_webngrams_candidates.py"),
            "--input-candidates",
            str(probe_dir / "candidates.json"),
            "--input-probe-report",
            str(live_report),
            "--source-mode",
            "live",
            "--output-dir",
            str(review_dir),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def metric_conservation_ok(report: dict[str, Any]) -> bool:
    return all(
        [
            report["total_input_count"] == report["valid_input_count"] + report["malformed_input_count"],
            report["unique_valid_candidate_count"] == report["pre_dedup_valid_count"] - report["duplicate_suppressed_count"],
            report["classified_candidate_count"] == report["unique_valid_candidate_count"],
            report["classified_candidate_count"]
            == report["publish_candidate_count"] + report["review_required_count"] + report["irrelevant_count"],
            report["country_confirmed_count"]
            + report["country_inferred_count"]
            + report["country_unresolved_count"]
            + report["country_conflicting_count"]
            == report["country_resolution_eligible_count"],
            report["country_resolution_success_count"] == report["country_confirmed_count"] + report["country_inferred_count"],
        ]
    )


def main() -> int:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    lowered = workflow.lower()
    require("workflow_dispatch:" in workflow, "workflow_dispatch trigger missing")
    require("\n  schedule:" not in workflow and "\n  push:" not in workflow and "\n  pull_request:" not in workflow, "forbidden trigger present")
    require("permissions:\n  contents: read" in workflow, "workflow must use contents read permission")
    require("acknowledge_single_run" in workflow and "must be true" in workflow, "acknowledgement guard missing")
    require("grep -Eq '^[0-9]{14}$'" in workflow, "timestamp guard missing")
    require("max_candidates must be between 1 and 100" in workflow, "max_candidates guard missing")
    require("scripts/review_gdelt_webngrams_candidates.py" in workflow, "live review step missing")
    require("--source-mode live" in workflow, "live review source mode missing")
    require("production_publish_allowed" in workflow, "production publish guard missing")
    require("if: ${{ always() }}" in workflow, "artifact upload must run always")
    require("retention-days: 7" in workflow, "artifact retention mismatch")
    require("api.gdeltproject.org/api/v2/doc/doc" not in workflow, "DOC API endpoint must not appear")
    require("git push" not in lowered and "git commit" not in lowered and "git add" not in lowered, "workflow must not mutate repo")
    require("fallback" not in lowered, "workflow must not contain timestamp fallback")
    require("retry" not in lowered, "workflow must not contain request retry")

    hashes: list[str] = []
    for _ in range(2):
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            probe_dir = tmp / "probe"
            review_dir = tmp / "review"
            run_fixture_probe(probe_dir)
            live_report = adapt_probe_report_for_live(probe_dir)
            report = run_live_review(probe_dir, review_dir, live_report)
            require(report["source_mode"] == "live", "review source mode mismatch")
            require(report["transport_acceptance_passed"] is True, "transport acceptance should pass in adapter test")
            require(report["candidate_schema_valid"] is True, "candidate schema must be valid")
            require(report["metric_conservation_passed"] is True, "metric conservation failed")
            require(report["quality_pipeline_valid"] is True, "quality pipeline invalid")
            require(report["shadow_ready"] is True, "shadow readiness should pass")
            require(report["production_publish_allowed"] is False, "production publication must stay disabled")
            require(report["external_http_request_count"] == 0, "review must not perform HTTP requests")
            require(metric_conservation_ok(report), "metric conservation formulas failed")
            require((review_dir / "manual_review.csv").exists(), "manual review CSV missing")
            artifacts = load_review_artifacts(review_dir)
            payload = json.dumps(artifacts, ensure_ascii=False, sort_keys=True)
            hashes.append(hashlib.sha256(payload.encode("utf-8")).hexdigest())
    require(hashes[0] == hashes[1], "live review fixture adapter output is not deterministic")

    print("GDELT WEBNGRAMS LIVE REVIEW WORKFLOW TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
