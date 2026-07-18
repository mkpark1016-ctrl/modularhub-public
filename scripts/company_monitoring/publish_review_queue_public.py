from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.company_monitoring.common import read_json  # noqa: E402
from scripts.company_monitoring.export_review_queue_public import (  # noqa: E402
    DEFAULT_MANIFEST_OUTPUT,
    DEFAULT_OUTPUT,
    export_public_review_queue,
)


EXPECTED_WORKFLOW_NAME = "Company Intelligence Monitor"
EXPECTED_WORKFLOW_PATH = ".github/workflows/company-intelligence-monitor.yml"
EXPECTED_BRANCH = "main"
EXPECTED_EVENT = "workflow_dispatch"
REQUIRED_ARTIFACTS = {
    "company-intelligence-review-queue": ("review_queue.json",),
    "company-intelligence-digest": ("latest_digest.json",),
    "company-intelligence-audit": ("audit-summary.json",),
}
SECRET_KEY_NAMES = (
    "DART_API_KEY",
    "NAVER_API_HUB_CLIENT_ID",
    "NAVER_API_HUB_CLIENT_SECRET",
    "Authorization",
    "X-NCP-APIGW-API-KEY-ID",
    "X-NCP-APIGW-API-KEY",
    "request_headers",
    "raw_response",
    "traceback",
)


def safe_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_source_run_metadata(payload: dict[str, Any]) -> dict[str, str]:
    workflow_name = safe_text(payload.get("name") or payload.get("workflow_name"))
    workflow_path = safe_text(payload.get("path") or payload.get("workflow_path"))
    conclusion = safe_text(payload.get("conclusion"))
    status = safe_text(payload.get("status"))
    head_branch = safe_text(payload.get("head_branch"))
    event = safe_text(payload.get("event"))
    head_sha = safe_text(payload.get("head_sha"))
    run_id = safe_text(payload.get("id") or payload.get("run_id"))

    errors: list[str] = []
    if workflow_name != EXPECTED_WORKFLOW_NAME:
        errors.append("source workflow name mismatch")
    if workflow_path != EXPECTED_WORKFLOW_PATH:
        errors.append("source workflow path mismatch")
    if status != "completed":
        errors.append("source run is not completed")
    if conclusion != "success":
        errors.append("source run did not succeed")
    if head_branch != EXPECTED_BRANCH:
        errors.append("source run branch is not main")
    if event != EXPECTED_EVENT:
        errors.append("source run event is not workflow_dispatch")
    if not head_sha:
        errors.append("source run head sha missing")
    if not run_id:
        errors.append("source run id missing")
    if errors:
        raise ValueError("; ".join(errors))

    return {
        "source_run_id": run_id,
        "source_commit": head_sha,
        "source_workflow": workflow_name,
        "source_branch": head_branch,
    }


def find_unique_file(root: Path, artifact_name: str, filenames: tuple[str, ...]) -> Path:
    artifact_root = root / artifact_name
    if not artifact_root.exists():
        raise FileNotFoundError(f"required artifact missing: {artifact_name}")
    matches = [path for path in artifact_root.rglob("*") if path.is_file() and path.name in filenames]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {filenames} in {artifact_name}, found {len(matches)}")
    return matches[0]


def artifact_paths(artifact_root: Path) -> dict[str, Path]:
    return {
        name: find_unique_file(artifact_root, name, filenames)
        for name, filenames in REQUIRED_ARTIFACTS.items()
    }


def validate_audit_summary(audit: dict[str, Any]) -> None:
    status_counts = audit.get("final_status_counts") or {}
    final_total = sum(int(status_counts.get(key, 0) or 0) for key in ("pending", "duplicate", "rejected", "conflict", "accepted"))
    normalized = int(audit.get("normalized_unique_count") or 0)
    conservation = audit.get("status_conservation") or {}
    if final_total != normalized or conservation.get("valid") is False:
        raise ValueError("metric conservation failed")

    raw_total = (
        int(audit.get("raw_candidate_record_count") or 0)
        + int(audit.get("raw_rejected_record_count") or 0)
        + int(audit.get("non_candidate_control_record_count") or 0)
    )
    if raw_total != int(audit.get("raw_source_record_count") or raw_total):
        raise ValueError("raw source record conservation failed")

    if int(audit.get("multi_status_candidate_count") or 0) != 0:
        raise ValueError("multi-status candidates detected")
    if int(audit.get("orphan_candidate_count") or 0) != 0:
        raise ValueError("orphan candidate refs detected")
    integrity = audit.get("duplicate_integrity") or {}
    for key in ("missing_duplicate_of_count", "self_duplicate_of_count", "duplicate_cycle_count", "cross_company_duplicate_count"):
        if int(integrity.get(key) or 0) != 0:
            raise ValueError(f"duplicate integrity failed: {key}")
    if audit.get("secret_exposure_detected") is True:
        raise ValueError("secret exposure detected in source audit")


def validate_review_queue_payload(queue: dict[str, Any], audit: dict[str, Any]) -> None:
    rows = queue.get("review_queue")
    if not isinstance(rows, list):
        raise ValueError("review queue artifact must contain review_queue array")
    ids = [safe_text(row.get("candidate_id")) for row in rows]
    if any(not candidate_id for candidate_id in ids):
        raise ValueError("review queue contains a row without candidate_id")
    if len(ids) != len(set(ids)):
        raise ValueError("review queue contains duplicate candidate_id values")
    statuses = {safe_text(row.get("review_status") or "pending") for row in rows}
    if statuses - {"pending"}:
        raise ValueError("public review queue artifact must contain pending candidates only")
    pending = int((audit.get("final_status_counts") or {}).get("pending") or 0)
    if len(rows) != pending:
        raise ValueError(f"review queue pending count mismatch: {len(rows)} != {pending}")


def assert_public_files_safe(paths: list[Path]) -> None:
    pattern = re.compile("|".join(re.escape(name) for name in SECRET_KEY_NAMES), re.I)
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if pattern.search(text):
            raise ValueError(f"sensitive key name detected in public output: {path}")


def publish_from_artifacts(
    *,
    artifact_root: Path,
    source_run_metadata_path: Path,
    output_path: Path,
    manifest_output_path: Path,
    lookback_days: int,
) -> dict[str, Any]:
    metadata = validate_source_run_metadata(load_json(source_run_metadata_path))
    paths = artifact_paths(artifact_root)
    queue = load_json(paths["company-intelligence-review-queue"])
    audit = load_json(paths["company-intelligence-audit"])
    validate_audit_summary(audit)
    validate_review_queue_payload(queue, audit)
    result = export_public_review_queue(
        input_path=paths["company-intelligence-review-queue"],
        digest_path=paths["company-intelligence-digest"],
        output_path=output_path,
        manifest_output_path=manifest_output_path,
        lookback_days=lookback_days,
        source_run_id=metadata["source_run_id"],
        source_run_commit=metadata["source_commit"],
        source_workflow=metadata["source_workflow"],
        source_branch=metadata["source_branch"],
    )
    assert_public_files_safe([output_path, manifest_output_path])
    return {
        **result,
        **metadata,
        "audit_valid": True,
        "public_files_safe": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish sanitized review queue public JSON from downloaded GitHub artifacts.")
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--source-run-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest-output", type=Path, default=DEFAULT_MANIFEST_OUTPUT)
    parser.add_argument("--lookback-days", type=int, default=30)
    args = parser.parse_args()
    result = publish_from_artifacts(
        artifact_root=args.artifact_root,
        source_run_metadata_path=args.source_run_metadata,
        output_path=args.output,
        manifest_output_path=args.manifest_output,
        lookback_days=args.lookback_days,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
