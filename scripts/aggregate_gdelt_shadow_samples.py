from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.review_gdelt_webngrams_candidates import normalize_text, parse_date  # noqa: E402


SCHEMA_VERSION = "1.0"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "gdelt_shadow_evaluation"
RELEVANT_PRECISION_THRESHOLD = 0.90
IRRELEVANT_PRECISION_THRESHOLD = 0.95
REPORT_FILES = {
    "probe_report": "report.json",
    "run_control": "run_control.json",
    "download_manifest": "download_manifest.json",
    "candidates": "candidates.json",
    "manual_review": "manual_review.csv",
    "review_report": "live_review_report.json",
    "review_markdown": "live_review_report.md",
}
BUCKET_FILES = ["publish_candidates.json", "review_required.json", "irrelevant.json", "malformed.json"]
LABEL_COLUMNS = [
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
]
RUN_MATRIX_COLUMNS = [
    "sample_id",
    "timestamp",
    "artifact_dir_configured",
    "artifact_dir_resolved",
    "workflow_run_id",
    "commit_sha",
    "workflow_status",
    "validation_status",
    "sample_status",
    "transport_acceptance",
    "source_integrity_checks_passed",
    "quality_pipeline_valid",
    "pipeline_shadow_ready",
    "content_sample_usable",
    "production_publish_allowed",
    "request_attempt_count",
    "http_response_count",
    "webngrams_request_count",
    "gal_request_count",
    "doc_api_request_count",
    "retry_count",
    "fallback_count",
    "total_input_count",
    "valid_candidate_count",
    "duplicate_group_count",
    "duplicate_suppressed_count",
    "unique_candidate_count",
    "publish_candidate_count",
    "review_required_count",
    "irrelevant_input_count",
    "irrelevant_unique_count",
    "strong_match_count",
    "weak_match_count",
    "excluded_context_count",
    "country_resolution_eligible_count",
    "country_resolution_success_count",
    "country_resolution_success_ratio",
    "public_json_unchanged",
    "db_unchanged",
    "env_unchanged",
    "checkpoint_unchanged",
]
CANDIDATE_POOL_COLUMNS = [
    "sample_id",
    "timestamp",
    "candidate_id",
    "title",
    "canonical_url",
    "domain",
    "published_at",
    "language",
    "classification",
    "relevance_score",
    "matched_strength",
    "classification_reason",
    "positive_reason_codes",
    "exclusion_reason_codes",
    "construction_context_terms",
    "non_construction_context_terms",
    "country_resolution_status",
    "duplicate_group_id",
    "duplicate_reason",
    "representative_item_id",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def stable_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def ratio(numerator: int, denominator: int) -> float | str:
    if denominator == 0:
        return "not_applicable"
    return round(numerator / denominator, 4)


def resolve_artifact_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path.resolve()
    return (ROOT / path).resolve()


def find_artifact_file(base: Path, filename: str) -> Path | None:
    direct = base / filename
    if direct.exists():
        return direct
    matches = sorted(path for path in base.rglob(filename) if path.is_file())
    return matches[0] if matches else None


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = read_json(path)
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")
    if clean_text(manifest.get("schema_version")) != SCHEMA_VERSION:
        raise ValueError(f"manifest schema_version must be {SCHEMA_VERSION}")
    samples = manifest.get("samples")
    if not isinstance(samples, list):
        raise ValueError("manifest samples must be a list")
    for sample in samples:
        if not isinstance(sample, dict):
            raise ValueError("manifest samples must contain objects")
        for field in ("sample_id", "timestamp", "artifact_dir"):
            if not clean_text(sample.get(field)):
                raise ValueError(f"manifest sample missing field: {field}")
    return manifest


def listify(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def csv_value(value: Any) -> str:
    if isinstance(value, list):
        return ";".join(json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, dict) else clean_text(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return clean_text(value)


def candidate_id(item: dict[str, Any]) -> str:
    return clean_text(item.get("item_id") or item.get("id") or item.get("candidate_id") or stable_hash(item)[:16])


def description_prefix(item: dict[str, Any], length: int = 140) -> str:
    description = normalize_text(item.get("description") or item.get("desc") or item.get("raw_candidate", {}).get("description"))
    return description[:length].strip()


def date_bucket(value: Any) -> str:
    parsed = parse_date(value)
    return parsed.strftime("%Y%m%d") if parsed else ""


def cross_sample_keys(item: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    canonical = clean_text(item.get("canonical_url") or item.get("normalized_url"))
    if canonical:
        keys.append(f"url:{canonical}")
    title = clean_text(item.get("normalized_title") or normalize_text(item.get("title")))
    bucket = date_bucket(item.get("published_at"))
    description = description_prefix(item)
    language = clean_text(item.get("language") or "unknown").lower()
    if title and bucket and len(description) >= 40:
        keys.append(f"syndicated:{title}|{bucket}|{description}|{language}")
    return keys


def load_bucket_items(base: Path) -> tuple[list[dict[str, Any]], list[str]]:
    items: list[dict[str, Any]] = []
    missing: list[str] = []
    for filename in BUCKET_FILES:
        path = find_artifact_file(base, filename)
        if path is None:
            missing.append(filename)
            continue
        payload = read_json(path)
        bucket_items = payload.get("items") if isinstance(payload, dict) else []
        if not isinstance(bucket_items, list):
            raise ValueError(f"{filename} items must be a list")
        for item in bucket_items:
            if isinstance(item, dict):
                items.append(item)
    return items, missing


def classify_sample_status(run: dict[str, Any], errors: list[str]) -> str:
    if errors:
        return "incomplete"
    if run["transport_acceptance"] and run["quality_pipeline_valid"] and run["source_integrity_checks_passed"]:
        return "success"
    return "failed"


def summarize_sample(sample: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    sample_id = clean_text(sample.get("sample_id"))
    timestamp = clean_text(sample.get("timestamp"))
    artifact_dir_configured = clean_text(sample.get("artifact_dir"))
    artifact_dir = resolve_artifact_path(artifact_dir_configured)
    errors: list[str] = []
    loaded: dict[str, Any] = {}
    paths: dict[str, Path] = {}
    if not artifact_dir.exists():
        errors.append("artifact_dir_missing")
    else:
        for key, filename in REPORT_FILES.items():
            path = find_artifact_file(artifact_dir, filename)
            if path is not None:
                paths[key] = path
        for key in ("probe_report", "run_control", "download_manifest", "candidates", "review_report"):
            if key not in paths:
                errors.append(f"{REPORT_FILES[key]}_missing")
        for key, path in paths.items():
            if path.suffix.lower() == ".json":
                try:
                    loaded[key] = read_json(path)
                except json.JSONDecodeError:
                    errors.append(f"{path.name}_json_invalid")
    probe = loaded.get("probe_report") if isinstance(loaded.get("probe_report"), dict) else {}
    run_control = loaded.get("run_control") if isinstance(loaded.get("run_control"), dict) else {}
    review = loaded.get("review_report") if isinstance(loaded.get("review_report"), dict) else {}
    reported_timestamp = clean_text(probe.get("timestamp") or review.get("timestamp") or run_control.get("timestamp"))
    if reported_timestamp and reported_timestamp != timestamp:
        errors.append("timestamp_mismatch")
    bucket_items: list[dict[str, Any]] = []
    if artifact_dir.exists():
        try:
            bucket_items, missing_buckets = load_bucket_items(artifact_dir)
            if missing_buckets:
                errors.extend(f"{name}_missing" for name in missing_buckets)
        except (json.JSONDecodeError, ValueError) as exc:
            errors.append(f"bucket_read_failed:{exc}")
    run = {
        "sample_id": sample_id,
        "timestamp": timestamp,
        "artifact_dir": artifact_dir_configured,
        "artifact_dir_configured": artifact_dir_configured,
        "artifact_dir_resolved": str(artifact_dir),
        "workflow_run_id": clean_text(run_control.get("run_id") or probe.get("workflow_run_id") or review.get("probe_run_id")),
        "commit_sha": clean_text(run_control.get("commit_sha") or probe.get("commit_sha")),
        "workflow_status": clean_text(probe.get("status") or run_control.get("validation_status") or sample.get("expected_status")),
        "validation_status": clean_text(run_control.get("validation_status") or "not_evaluated"),
        "transport_acceptance": as_bool(probe.get("transport_acceptance_passed")),
        "source_integrity_checks_passed": as_bool(probe.get("source_integrity_checks_passed")),
        "quality_pipeline_valid": as_bool(review.get("quality_pipeline_valid")),
        "pipeline_shadow_ready": as_bool(review.get("pipeline_shadow_ready", review.get("shadow_ready"))),
        "content_sample_usable": as_bool(review.get("content_sample_usable")),
        "production_publish_allowed": as_bool(review.get("production_publish_allowed")),
        "request_attempt_count": int(probe.get("request_attempt_count") or probe.get("network_request_count") or 0),
        "http_response_count": int(probe.get("http_response_count") or 0),
        "webngrams_request_count": int(probe.get("webngrams_request_count") or 0),
        "gal_request_count": int(probe.get("gal_request_count") or 0),
        "doc_api_request_count": int(probe.get("doc_api_request_count") or 0),
        "retry_count": int(probe.get("retry_count") or 0),
        "fallback_count": int(probe.get("fallback_count") or 0),
        "total_input_count": int(review.get("total_input_count") or 0),
        "valid_candidate_count": int(review.get("valid_input_count") or 0),
        "duplicate_group_count": int(review.get("duplicate_group_count") or 0),
        "duplicate_suppressed_count": int(review.get("duplicate_suppressed_count") or 0),
        "unique_candidate_count": int(review.get("unique_valid_candidate_count") or 0),
        "publish_candidate_count": int(review.get("publish_candidate_count") or 0),
        "review_required_count": int(review.get("review_required_count") or 0),
        "irrelevant_input_count": int(review.get("irrelevant_input_count") or 0),
        "irrelevant_unique_count": int(review.get("irrelevant_unique_count") or 0),
        "strong_match_count": int(review.get("strong_match_count") or 0),
        "weak_match_count": int(review.get("weak_match_count") or 0),
        "excluded_context_count": int(review.get("excluded_context_count") or 0),
        "country_resolution_eligible_count": int(review.get("country_resolution_eligible_count") or 0),
        "country_resolution_success_count": int(review.get("country_resolution_success_count") or 0),
        "country_resolution_success_ratio": review.get("country_resolution_success_ratio", "not_applicable"),
        "public_json_unchanged": probe.get("public_json_unchanged") is True and review.get("public_json_unchanged") is True,
        "db_unchanged": probe.get("db_unchanged") is True and review.get("db_unchanged") is True,
        "env_unchanged": probe.get("env_unchanged") is True and review.get("env_unchanged") is True,
        "checkpoint_unchanged": probe.get("checkpoint_unchanged") is True,
        "validation_errors": errors,
    }
    run["sample_status"] = classify_sample_status(run, errors)
    candidate_rows: list[dict[str, Any]] = []
    for item in bucket_items:
        row = {
            "sample_id": sample_id,
            "timestamp": timestamp,
            "candidate_id": candidate_id(item),
            "title": clean_text(item.get("title")),
            "canonical_url": clean_text(item.get("canonical_url") or item.get("normalized_url")),
            "domain": clean_text(item.get("domain")),
            "published_at": clean_text(item.get("published_at")),
            "language": clean_text(item.get("language")),
            "classification": clean_text(item.get("classification")),
            "relevance_score": item.get("relevance_score", ""),
            "matched_strength": clean_text(item.get("matched_strength")),
            "classification_reason": clean_text(item.get("classification_reason")),
            "positive_reason_codes": listify(item.get("positive_reason_codes")),
            "exclusion_reason_codes": listify(item.get("exclusion_reason_codes")),
            "construction_context_terms": listify(item.get("construction_context_terms")),
            "non_construction_context_terms": listify(item.get("non_construction_context_terms")),
            "country_resolution_status": clean_text(item.get("country_resolution_status")),
            "duplicate_group_id": clean_text(item.get("duplicate_group_id")),
            "duplicate_reason": clean_text(item.get("duplicate_reason")),
            "representative_item_id": clean_text(item.get("representative_item_id")),
            "_raw": item,
        }
        row["cross_sample_keys"] = cross_sample_keys({**item, **row})
        row["cross_sample_key"] = row["cross_sample_keys"][0] if row["cross_sample_keys"] else ""
        candidate_rows.append(row)
    validation_errors = [
        {
            "sample_id": sample_id,
            "timestamp": timestamp,
            "artifact_dir": artifact_dir_configured,
            "artifact_dir_configured": artifact_dir_configured,
            "artifact_dir_resolved": str(artifact_dir),
            "error": error,
        }
        for error in errors
    ]
    return run, candidate_rows, validation_errors


def cross_sample_duplicates(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], set[tuple[str, str]]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in candidates:
        for key in item.get("cross_sample_keys") or [item.get("cross_sample_key")]:
            key = clean_text(key)
            if not key:
                continue
            buckets[key].append(item)
    groups: list[dict[str, Any]] = []
    duplicate_members: set[tuple[str, str]] = set()
    for key, members in sorted(buckets.items()):
        sample_ids = sorted({item["sample_id"] for item in members})
        if len(sample_ids) < 2:
            continue
        sorted_members = sorted(members, key=lambda item: (item["sample_id"], item["candidate_id"]))
        member_refs = [{"sample_id": item["sample_id"], "candidate_id": item["candidate_id"]} for item in sorted_members]
        for item in sorted_members:
            duplicate_members.add((item["sample_id"], item["candidate_id"]))
        group_id = f"xdup-{stable_hash(member_refs)[:12]}"
        groups.append(
            {
                "schema_version": SCHEMA_VERSION,
                "duplicate_group_id": group_id,
                "duplicate_reason": "cross_sample_fingerprint",
                "fingerprint": key,
                "representative": member_refs[0],
                "members": member_refs,
                "sample_ids": sample_ids,
            }
        )
    return groups, duplicate_members


def load_labels(path: Path | None, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    source_level_recall_status = "not_measurable_from_candidate_only_artifacts"
    if path is None:
        return {
            "labels_present": False,
            "labeled_candidate_count": 0,
            "unlabeled_candidate_count": len(candidates),
            "label_coverage_rate": "not_applicable" if not candidates else 0.0,
            "classifier_precision_for_relevant": "not_applicable",
            "classifier_precision_for_irrelevant": "not_applicable",
            "classification_recall_within_candidate_pool": "not_applicable",
            "false_positive_count": 0,
            "false_negative_within_candidate_pool_count": 0,
            "uncertain_count": 0,
            "source_level_recall_status": source_level_recall_status,
            "positive_fixture_recall_benchmark": "not_evaluated_by_shadow_aggregator",
        }
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        rows = [dict(row) for row in reader]
    label_by_key = {(clean_text(row.get("sample_id")), clean_text(row.get("candidate_id"))): clean_text(row.get("ground_truth_label")) for row in rows}
    labeled = 0
    predicted_relevant_labeled = 0
    predicted_relevant_correct = 0
    predicted_irrelevant_labeled = 0
    predicted_irrelevant_correct = 0
    actual_relevant_labeled = 0
    actual_relevant_found = 0
    false_positive_count = 0
    false_negative_count = 0
    uncertain_count = 0
    for item in candidates:
        label = label_by_key.get((item["sample_id"], item["candidate_id"]), "")
        if not label:
            continue
        labeled += 1
        observed_relevant = item["classification"] in {"publish_candidate", "review_required"}
        actual_relevant = label == "relevant_building_modular"
        if label == "uncertain":
            uncertain_count += 1
        if observed_relevant:
            predicted_relevant_labeled += 1
            if actual_relevant:
                predicted_relevant_correct += 1
            elif label not in {"uncertain"}:
                false_positive_count += 1
        elif item["classification"] == "irrelevant":
            predicted_irrelevant_labeled += 1
            if label in {"irrelevant", "duplicate", "inaccessible"}:
                predicted_irrelevant_correct += 1
        if actual_relevant:
            actual_relevant_labeled += 1
            if observed_relevant:
                actual_relevant_found += 1
            else:
                false_negative_count += 1
    return {
        "labels_present": True,
        "labeled_candidate_count": labeled,
        "unlabeled_candidate_count": max(0, len(candidates) - labeled),
        "label_coverage_rate": ratio(labeled, len(candidates)),
        "classifier_precision_for_relevant": ratio(predicted_relevant_correct, predicted_relevant_labeled),
        "classifier_precision_for_irrelevant": ratio(predicted_irrelevant_correct, predicted_irrelevant_labeled),
        "classification_recall_within_candidate_pool": ratio(actual_relevant_found, actual_relevant_labeled),
        "false_positive_count": false_positive_count,
        "false_negative_within_candidate_pool_count": false_negative_count,
        "uncertain_count": uncertain_count,
        "source_level_recall_status": source_level_recall_status,
        "positive_fixture_recall_benchmark": "not_evaluated_by_shadow_aggregator",
    }


def distribution_rows(counter: Counter[str], key_name: str) -> list[dict[str, Any]]:
    return [{key_name: key or "unknown", "count": count} for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field, "")) for field in fieldnames})


def label_template_rows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in sorted(candidates, key=lambda value: (value["sample_id"], value["timestamp"], value["candidate_id"])):
        observed_reason = clean_text(item.get("duplicate_reason")) or clean_text(item.get("classification_reason"))
        rows.append(
            {
                "sample_id": item["sample_id"],
                "timestamp": item["timestamp"],
                "candidate_id": item["candidate_id"],
                "title": item["title"],
                "canonical_url": item["canonical_url"],
                "observed_classification": item["classification"],
                "observed_reason": observed_reason,
                "ground_truth_label": "",
                "ground_truth_reason": "",
                "reviewer": "",
                "reviewed_at": "",
                "notes": "",
            }
        )
    return rows


def decide_evaluation_status(summary: dict[str, Any], label_metrics: dict[str, Any]) -> str:
    if summary["successful_sample_count"] < 6 or int(label_metrics["labeled_candidate_count"]) < 20:
        return "insufficient_sample"
    if not summary["technical_contract_passed"]:
        return "candidate_rules_hold"
    relevant_precision = label_metrics["classifier_precision_for_relevant"]
    irrelevant_precision = label_metrics["classifier_precision_for_irrelevant"]
    if relevant_precision == "not_applicable" or irrelevant_precision == "not_applicable":
        return "technical_shadow_pass"
    precision_failed = (
        isinstance(relevant_precision, float)
        and relevant_precision < RELEVANT_PRECISION_THRESHOLD
        or isinstance(irrelevant_precision, float)
        and irrelevant_precision < IRRELEVANT_PRECISION_THRESHOLD
    )
    if precision_failed or label_metrics["false_positive_count"] or label_metrics["false_negative_within_candidate_pool_count"]:
        return "quality_review_required"
    return "shadow_evaluation_pass"


def aggregate(manifest_path: Path, output_dir: Path, labels_path: Path | None = None) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    enabled_samples = [sample for sample in manifest["samples"] if sample.get("enabled", True)]
    run_rows: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    validation_errors: list[dict[str, Any]] = []
    for sample in enabled_samples:
        run, sample_candidates, errors = summarize_sample(sample)
        run_rows.append(run)
        candidates.extend(sample_candidates)
        validation_errors.extend(errors)
    cross_groups, cross_duplicate_members = cross_sample_duplicates(candidates)
    successful = [row for row in run_rows if row["sample_status"] == "success"]
    failed = [row for row in run_rows if row["sample_status"] == "failed"]
    incomplete = [row for row in run_rows if row["sample_status"] == "incomplete"]
    relevant_candidates = [item for item in candidates if item["classification"] in {"publish_candidate", "review_required"}]
    labels = load_labels(labels_path, candidates)
    domain_counter = Counter(item["domain"] or "unknown" for item in candidates)
    country_counter = Counter(item["country_resolution_status"] or "unknown" for item in candidates)
    technical_contract_passed = bool(
        successful
        and not failed
        and not incomplete
        and all(
            row["transport_acceptance"]
            and row["source_integrity_checks_passed"]
            and row["quality_pipeline_valid"]
            and row["public_json_unchanged"]
            and row["db_unchanged"]
            and row["env_unchanged"]
            and row["checkpoint_unchanged"]
            and not row["production_publish_allowed"]
            for row in successful
        )
    )
    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "sample_set_id": clean_text(manifest.get("sample_set_id")),
        "description": clean_text(manifest.get("description")),
        "manifest": str(manifest_path),
        "production_publish_allowed": False,
        "total_sample_count": len(enabled_samples),
        "successful_sample_count": len(successful),
        "failed_sample_count": len(failed),
        "incomplete_sample_count": len(incomplete),
        "pipeline_success_rate": ratio(len(successful), len(enabled_samples)),
        "transport_acceptance_rate": ratio(sum(1 for row in run_rows if row["transport_acceptance"]), len(enabled_samples)),
        "source_integrity_pass_rate": ratio(sum(1 for row in run_rows if row["source_integrity_checks_passed"]), len(enabled_samples)),
        "quality_pipeline_pass_rate": ratio(sum(1 for row in run_rows if row["quality_pipeline_valid"]), len(enabled_samples)),
        "pipeline_shadow_ready_rate": ratio(sum(1 for row in run_rows if row["pipeline_shadow_ready"]), len(enabled_samples)),
        "content_sample_usable_count": sum(1 for row in run_rows if row["content_sample_usable"]),
        "content_sample_usable_rate": ratio(sum(1 for row in run_rows if row["content_sample_usable"]), len(enabled_samples)),
        "total_input_candidate_count": sum(row["total_input_count"] for row in run_rows),
        "total_unique_candidate_count": sum(row["unique_candidate_count"] for row in run_rows),
        "total_duplicate_suppressed_count": sum(row["duplicate_suppressed_count"] for row in run_rows),
        "total_publish_candidate_count": sum(row["publish_candidate_count"] for row in run_rows),
        "total_review_required_count": sum(row["review_required_count"] for row in run_rows),
        "total_irrelevant_input_count": sum(row["irrelevant_input_count"] for row in run_rows),
        "total_irrelevant_unique_count": sum(row["irrelevant_unique_count"] for row in run_rows),
        "total_strong_match_count": sum(row["strong_match_count"] for row in run_rows),
        "total_weak_match_count": sum(row["weak_match_count"] for row in run_rows),
        "total_excluded_context_count": sum(row["excluded_context_count"] for row in run_rows),
        "total_country_resolution_eligible_count": sum(row["country_resolution_eligible_count"] for row in run_rows),
        "total_country_resolution_success_count": sum(row["country_resolution_success_count"] for row in run_rows),
        "within_sample_duplicate_count": sum(row["duplicate_suppressed_count"] for row in run_rows),
        "cross_sample_duplicate_count": len(cross_duplicate_members),
        "cross_sample_duplicate_group_count": len(cross_groups),
        "unique_candidates_before_cross_sample_dedup": len(candidates),
        "unique_candidates_after_cross_sample_dedup": max(0, len(candidates) - sum(max(0, len(group["members"]) - 1) for group in cross_groups)),
        "unique_domain_count": len(domain_counter),
        "unique_country_count": len([country for country in country_counter if country not in {"unknown", "not_applicable"}]),
        "samples_with_relevant_candidates": len({item["sample_id"] for item in relevant_candidates}),
        "relevant_candidate_yield_per_sample": ratio(len(relevant_candidates), len(enabled_samples)),
        "technical_contract_passed": technical_contract_passed,
        "external_http_request_count": 0,
        **labels,
    }
    summary["evaluation_status"] = decide_evaluation_status(summary, labels)
    write_outputs(output_dir, summary, run_rows, candidates, cross_groups, validation_errors)
    return summary


def write_outputs(
    output_dir: Path,
    summary: dict[str, Any],
    run_rows: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    cross_groups: list[dict[str, Any]],
    validation_errors: list[dict[str, Any]],
) -> None:
    (output_dir / "shadow_evaluation_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# GDELT Multi-Timestamp Shadow Evaluation",
        "",
        f"- sample_set_id: `{summary['sample_set_id']}`",
        f"- total_sample_count: `{summary['total_sample_count']}`",
        f"- successful_sample_count: `{summary['successful_sample_count']}`",
        f"- failed_sample_count: `{summary['failed_sample_count']}`",
        f"- incomplete_sample_count: `{summary['incomplete_sample_count']}`",
        f"- pipeline_success_rate: `{summary['pipeline_success_rate']}`",
        f"- transport_acceptance_rate: `{summary['transport_acceptance_rate']}`",
        f"- total_input_candidate_count: `{summary['total_input_candidate_count']}`",
        f"- total_unique_candidate_count: `{summary['total_unique_candidate_count']}`",
        f"- relevant_candidate_yield_per_sample: `{summary['relevant_candidate_yield_per_sample']}`",
        f"- cross_sample_duplicate_group_count: `{summary['cross_sample_duplicate_group_count']}`",
        f"- label_coverage_rate: `{summary['label_coverage_rate']}`",
        f"- classifier_precision_for_relevant: `{summary['classifier_precision_for_relevant']}`",
        f"- classifier_precision_for_irrelevant: `{summary['classifier_precision_for_irrelevant']}`",
        f"- source_level_recall_status: `{summary['source_level_recall_status']}`",
        f"- evaluation_status: `{summary['evaluation_status']}`",
        "- production_publish_allowed: `false`",
    ]
    (output_dir / "shadow_evaluation_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_csv(output_dir / "run_matrix.csv", run_rows, RUN_MATRIX_COLUMNS)
    write_csv(output_dir / "candidate_pool.csv", candidates, CANDIDATE_POOL_COLUMNS)
    (output_dir / "cross_sample_duplicate_groups.json").write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "items": cross_groups}, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "validation_errors.json").write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "items": validation_errors}, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    write_csv(output_dir / "manual_labels_template.csv", label_template_rows(candidates), LABEL_COLUMNS)
    reason_counter: Counter[str] = Counter()
    exclusion_counter: Counter[str] = Counter()
    duplicate_counter: Counter[str] = Counter()
    domain_counter: Counter[str] = Counter()
    timestamp_counter: Counter[str] = Counter()
    for item in candidates:
        reason_counter[item["classification_reason"] or "unknown"] += 1
        reason_counter[f"matched_strength:{item['matched_strength'] or 'unknown'}"] += 1
        reason_counter.update(f"positive:{value}" for value in item["positive_reason_codes"])
        reason_counter.update(f"construction_context:{value}" for value in item["construction_context_terms"])
        reason_counter.update(f"non_construction_context:{value}" for value in item["non_construction_context_terms"])
        reason_counter[f"country_resolution_status:{item['country_resolution_status'] or 'unknown'}"] += 1
        exclusion_counter.update(item["exclusion_reason_codes"])
        if item["duplicate_reason"]:
            duplicate_counter[item["duplicate_reason"]] += 1
        domain_counter[item["domain"] or "unknown"] += 1
        timestamp_counter[item["timestamp"] or "unknown"] += 1
    write_csv(output_dir / "reason_code_distribution.csv", distribution_rows(reason_counter, "reason_code"), ["reason_code", "count"])
    write_csv(output_dir / "exclusion_reason_distribution.csv", distribution_rows(exclusion_counter, "exclusion_reason"), ["exclusion_reason", "count"])
    write_csv(output_dir / "duplicate_reason_distribution.csv", distribution_rows(duplicate_counter, "duplicate_reason"), ["duplicate_reason", "count"])
    write_csv(output_dir / "domain_distribution.csv", distribution_rows(domain_counter, "domain"), ["domain", "count"])
    write_csv(output_dir / "timestamp_distribution.csv", distribution_rows(timestamp_counter, "timestamp"), ["timestamp", "count"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate downloaded GDELT Web NGrams shadow artifacts without network access.")
    parser.add_argument("--manifest", type=Path, required=True, help="Path to shadow sample manifest JSON")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output artifact directory")
    parser.add_argument("--labels", type=Path, default=None, help="Optional manual labels CSV")
    args = parser.parse_args()
    try:
        result = aggregate(args.manifest, args.output_dir, args.labels)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
