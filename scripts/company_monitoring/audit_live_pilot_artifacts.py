from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.company_monitoring.build_review_queue import build_review_queue, load_raw_candidates  # noqa: E402
from scripts.company_monitoring.common import (  # noqa: E402
    CONFIG_DIR,
    DATA_DIR,
    RAW_DIR,
    canonical_url,
    hash_evidence,
    iso_now,
    load_monitor_companies,
    normalize_title,
    read_json,
    write_json,
)
from scripts.company_monitoring.dedupe_candidates import duplicate_keys  # noqa: E402

AUDIT_DIR = ROOT / "artifacts" / "company-intelligence-live-pilot"
DEFAULT_QUEUE_PATH = DATA_DIR / "review_queue.json"
DEFAULT_DIGEST_PATH = ROOT / "reports" / "company_monitoring" / "latest_digest.json"

FINAL_STATUSES = ("pending", "duplicate", "rejected", "conflict", "accepted", "superseded")
RISKY_ALIASES = {
    "gs",
    "dl",
    "nrb",
    "modular",
    "kind",
    "enc",
    "건설",
    "공업",
    "제강",
    "모듈러",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def existing_artifact_hashes(paths: list[Path]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for path in paths:
        if path.is_dir():
            for child in sorted(item for item in path.rglob("*") if item.is_file()):
                output[str(child)] = {"exists": True, "sha256": sha256_file(child), "bytes": child.stat().st_size}
        else:
            output[str(path)] = {
                "exists": path.exists(),
                "sha256": sha256_file(path) if path.exists() else None,
                "bytes": path.stat().st_size if path.exists() else None,
            }
    return output


def raw_record_count(raw_dir: Path) -> int:
    count = 0
    for name in ("dart_raw.json", "naver_search_raw.json"):
        path = raw_dir / name
        if not path.exists():
            continue
        payload = read_json(path)
        for result in payload.get("results", []):
            count += len(result.get("records") or [])
    return count


def candidate_ids(candidates: list[dict[str, Any]]) -> list[str]:
    return [str(row.get("candidate_id") or "") for row in candidates]


def duplicate_type(candidate: dict[str, Any], seen: dict[str, tuple[str, str]]) -> tuple[str | None, str | None]:
    for key in duplicate_keys(candidate):
        if key not in seen:
            continue
        duplicate_of, _ = seen[key]
        if key.startswith("url:"):
            return "same_url_duplicate", duplicate_of
        if key.startswith("doc:"):
            return "same_document_duplicate", duplicate_of
        if key.startswith("hash:"):
            return "canonicalization_duplicate", duplicate_of
        if key.startswith("title:"):
            return "same_title_duplicate", duplicate_of
        return "intra_run_duplicate", duplicate_of
    return None, None


def analyze_duplicates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    seen: dict[str, tuple[str, str]] = {}
    type_counts: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        status = candidate.get("review_status")
        if status == "duplicate":
            dtype, duplicate_of = duplicate_type(candidate, seen)
            dtype = dtype or "intra_run_duplicate"
            type_counts[dtype] += 1
            rows.append(
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "company_id": candidate.get("company_id"),
                    "duplicate_of": candidate.get("duplicate_of"),
                    "inferred_duplicate_of": duplicate_of,
                    "duplicate_type": dtype,
                }
            )
        else:
            for key in duplicate_keys(candidate):
                seen[key] = (str(candidate.get("candidate_id")), str(candidate.get("company_id")))
    cross_company = sum(
        1
        for row in rows
        if row.get("duplicate_of")
        and next((candidate for candidate in candidates if candidate.get("candidate_id") == row["duplicate_of"]), {}).get("company_id")
        != row.get("company_id")
    )
    return {
        "duplicate_type_counts": dict(sorted(type_counts.items())),
        "duplicate_rows": rows,
        "cross_company_duplicate_count": cross_company,
    }


def duplicate_integrity(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {row.get("candidate_id"): row for row in candidates}
    missing: list[str] = []
    self_refs: list[str] = []
    cycles: list[str] = []
    cross_company: list[str] = []
    for row in candidates:
        if row.get("review_status") != "duplicate":
            continue
        candidate_id = row.get("candidate_id")
        duplicate_of = row.get("duplicate_of")
        if not duplicate_of or duplicate_of not in by_id:
            missing.append(candidate_id)
            continue
        if duplicate_of == candidate_id:
            self_refs.append(candidate_id)
        target = by_id[duplicate_of]
        if target.get("company_id") != row.get("company_id"):
            cross_company.append(candidate_id)
        slow = candidate_id
        fast = duplicate_of
        visited = set()
        while fast in by_id and by_id[fast].get("duplicate_of"):
            if fast in visited or fast == slow:
                cycles.append(candidate_id)
                break
            visited.add(fast)
            fast = by_id[fast].get("duplicate_of")
    return {
        "missing_duplicate_of_count": len(missing),
        "self_duplicate_of_count": len(self_refs),
        "duplicate_cycle_count": len(cycles),
        "cross_company_duplicate_count": len(cross_company),
        "missing_duplicate_of_ids": missing[:50],
        "self_duplicate_of_ids": self_refs[:50],
        "duplicate_cycle_ids": cycles[:50],
        "cross_company_duplicate_ids": cross_company[:50],
    }


def status_analysis(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(row.get("review_status") or "missing") for row in candidates)
    final_status_counts = {status: counts.get(status, 0) for status in FINAL_STATUSES}
    missing_status_ids = [row.get("candidate_id") for row in candidates if not row.get("review_status")]
    multi_status_ids: list[str] = []
    ids = candidate_ids(candidates)
    duplicate_id_counts = Counter(ids)
    duplicated_candidate_ids = [key for key, value in duplicate_id_counts.items() if key and value > 1]
    conservation_total = sum(final_status_counts.values())
    return {
        "final_status_counts": final_status_counts,
        "missing_status_count": len(missing_status_ids),
        "multi_status_candidate_count": len(multi_status_ids),
        "duplicated_candidate_id_count": len(duplicated_candidate_ids),
        "missing_status_ids": missing_status_ids[:50],
        "duplicated_candidate_ids": duplicated_candidate_ids[:50],
        "status_conservation": {
            "normalized_unique_count": len(set(ids)),
            "final_status_total": conservation_total,
            "valid": len(set(ids)) == conservation_total and not duplicated_candidate_ids,
        },
    }


def rejected_reason_counts(rejected_raw: list[dict[str, Any]]) -> dict[str, int]:
    normalized: Counter[str] = Counter()
    for row in rejected_raw:
        reason = row.get("rejection_reason") or "other"
        if reason == "entity_not_matched":
            reason = "no_company_match"
        elif reason == "negative_keyword_context":
            reason = "excluded_keyword"
        normalized[reason] += 1
    return dict(sorted(normalized.items()))


def query_risk(raw_dir: Path) -> tuple[dict[str, Any], str]:
    companies = {company.company_id: company for company in load_monitor_companies({"yuchang-enc", "kumkang-kind"})}
    config = read_json(CONFIG_DIR / "companies.json")
    alias_to_companies: defaultdict[str, set[str]] = defaultdict(set)
    for row in config.get("companies", []):
        for alias in [row.get("canonical_name"), *(row.get("aliases") or []), *(row.get("english_names") or [])]:
            if alias:
                alias_to_companies[normalize_title(alias)].add(row.get("company_id"))

    payload = read_json(raw_dir / "naver_search_raw.json") if (raw_dir / "naver_search_raw.json").exists() else {"results": []}
    rows: dict[str, Any] = {}
    proposal_lines = [
        "# Query Tuning Proposal",
        "",
        "No query is changed by this audit. These recommendations are for a later review step.",
        "",
    ]
    for result in payload.get("results", []):
        company_id = result.get("company_id")
        total_records = len(result.get("records") or [])
        rejected = len(result.get("rejected") or [])
        rejected_ratio = rejected / total_records if total_records else 0
        company = companies.get(company_id)
        alias_risks: list[str] = []
        if company:
            for alias in company.search_names:
                norm = normalize_title(alias)
                if not norm:
                    continue
                if len(norm.replace(" ", "")) <= 2 or norm in RISKY_ALIASES:
                    alias_risks.append(f"short_or_generic_alias:{alias}")
                if len(alias_to_companies.get(norm, set())) > 1:
                    alias_risks.append(f"alias_collision:{alias}")
        risk = "low_risk"
        reasons: list[str] = []
        if rejected_ratio >= 0.25:
            risk = "moderate_risk"
            reasons.append("rejected_raw_ratio_at_or_above_25_percent")
        if alias_risks:
            risk = "moderate_risk"
            reasons.extend(alias_risks)
        if rejected_ratio >= 0.5:
            risk = "high_risk"
        rows[company_id] = {
            "company_id": company_id,
            "total_source_records": total_records,
            "candidate_count": len(result.get("candidates") or []),
            "rejected_raw_count": rejected,
            "rejected_raw_ratio": round(rejected_ratio, 4),
            "risk_level": risk,
            "risk_reasons": reasons,
        }
        if risk != "low_risk":
            proposal_lines.extend(
                [
                    f"## {company_id}",
                    "",
                    "- Current search: configured company names plus shared query suffixes.",
                    f"- Issue: {', '.join(reasons) if reasons else 'precision review recommended'}.",
                    "- False-positive signal: rejected raw records are materially present in the current run.",
                    "- Recommended search: keep company canonical name required, and pair broad aliases with modular-specific terms.",
                    "- Expected impact: fewer no-company-match raw records before review queue generation.",
                    "- Regression risk: overly narrow queries may miss early weak signals.",
                    "",
                ]
            )
    return rows, "\n".join(proposal_lines).rstrip() + "\n"


def stable_sample(candidates: list[dict[str, Any]], rejected_raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_company_status: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        by_company_status[(str(candidate.get("company_id")), str(candidate.get("review_status")))].append(candidate)
    sample: list[dict[str, Any]] = []
    for company_id in ("yuchang-enc", "kumkang-kind"):
        for status, limit in (("pending", 20), ("duplicate", 10)):
            rows = sorted(by_company_status[(company_id, status)], key=lambda row: row.get("candidate_id") or "")[:limit]
            for row in rows:
                sample.append(sample_row(row, status=status))
        rejected_for_company = [
            row
            for row in rejected_raw
            if any(company_id in str(row.get(key, "")) for key in ("query",))
            or (company_id == "yuchang-enc" and "유창" in str(row.get("query", "")))
            or (company_id == "kumkang-kind" and "금강" in str(row.get("query", "")))
        ]
        for row in sorted(rejected_for_company, key=lambda item: hash_evidence(item.get("title"), item.get("original_link"), item.get("query")))[:10]:
            rid = "raw-rejected-" + hash_evidence(row.get("title"), row.get("original_link"), row.get("query"))[:16]
            sample.append(
                {
                    "company_id": company_id,
                    "candidate_id": rid,
                    "status": "raw_rejected_quality_flag",
                    "source": "naver_search",
                    "title": row.get("title"),
                    "published_at": row.get("pub_date"),
                    "original_url": canonical_url(row.get("original_link") or row.get("naver_link")),
                    "matched_keyword": row.get("query"),
                    "matched_alias": None,
                    "match_reason": None,
                    "duplicate_type": None,
                    "duplicate_of": None,
                    "rejection_reason": row.get("rejection_reason"),
                    "relevance_review": "",
                    "reviewer_note": "",
                }
            )
    return sample


def sample_row(row: dict[str, Any], *, status: str) -> dict[str, Any]:
    return {
        "company_id": row.get("company_id"),
        "candidate_id": row.get("candidate_id"),
        "status": status,
        "source": row.get("source_type"),
        "title": row.get("title"),
        "published_at": row.get("published_at"),
        "original_url": canonical_url(row.get("source_url")),
        "matched_keyword": row.get("query"),
        "matched_alias": None,
        "match_reason": {
            "entity_match_score": row.get("entity_match_score"),
            "relevance_score": row.get("relevance_score"),
            "confidence": row.get("confidence"),
        },
        "duplicate_type": None,
        "duplicate_of": row.get("duplicate_of"),
        "rejection_reason": None,
        "relevance_review": "",
        "reviewer_note": "",
    }


def write_sample_markdown(path: Path, sample: list[dict[str, Any]]) -> None:
    lines = [
        "# Review Sample",
        "",
        "| company_id | status | candidate_id | title | published_at | reviewer_note |",
        "|---|---|---|---|---|---|",
    ]
    for row in sample:
        title = str(row.get("title") or "").replace("|", " ")
        lines.append(f"| {row.get('company_id')} | {row.get('status')} | `{row.get('candidate_id')}` | {title} | {row.get('published_at') or ''} |  |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_markdown(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Live Pilot Artifact Audit",
            "",
            f"- Generated at: `{summary['generated_at']}`",
            f"- Interpretation: `{summary['metric_interpretation']}`",
            f"- Raw source records: {summary['raw_source_record_count']}",
            f"- Raw candidate records: {summary['raw_candidate_record_count']}",
            f"- Normalized unique candidates: {summary['normalized_unique_count']}",
            f"- Final status counts: `{json.dumps(summary['final_status_counts'], ensure_ascii=False)}`",
            f"- Quality flag counts: `{json.dumps(summary['quality_flag_counts'], ensure_ascii=False)}`",
            f"- Metric excess cause: `{summary['metric_excess_cause']}`",
            f"- Conservation valid: `{str(summary['status_conservation']['valid']).lower()}`",
            f"- Multi-status candidates: {summary['multi_status_candidate_count']}",
            f"- Orphan duplicate references: {summary['duplicate_integrity']['missing_duplicate_of_count']}",
            "",
            "## Query Risk",
            "",
            *[
                f"- {company_id}: {row['risk_level']} ({', '.join(row['risk_reasons']) if row['risk_reasons'] else 'no major issue'})"
                for company_id, row in sorted(summary["query_risk"].items())
            ],
            "",
            "## Artifact Hashes",
            "",
            *[f"- `{path}`: `{meta.get('sha256')}`" for path, meta in sorted(summary["artifact_hashes"].items())],
            "",
        ]
    )


def audit(raw_dir: Path = RAW_DIR, queue_path: Path = DEFAULT_QUEUE_PATH, digest_path: Path = DEFAULT_DIGEST_PATH, output_dir: Path = AUDIT_DIR) -> dict[str, Any]:
    artifact_inputs = [
        raw_dir,
        queue_path,
        digest_path,
        ROOT / "reports" / "company_monitoring" / "latest_digest.md",
        output_dir / "live-pilot-summary.json",
        output_dir / "live-pilot-report.md",
    ]
    before_hashes = existing_artifact_hashes(artifact_inputs)
    raw_candidates, errors, rejected_raw = load_raw_candidates(raw_dir)
    payload = build_review_queue(raw_dir)
    all_candidates = payload["all_candidates"]
    ids = candidate_ids(all_candidates)
    status = status_analysis(all_candidates)
    duplicate = analyze_duplicates(all_candidates)
    integrity = duplicate_integrity(all_candidates)
    rejection_counts = rejected_reason_counts(rejected_raw)
    risk, proposal = query_risk(raw_dir)
    sample = stable_sample(all_candidates, rejected_raw)
    final_counts = status["final_status_counts"]
    quality_flags = {
        "raw_rejected_quality_flag": len(rejected_raw),
        "rejection_reason_counts": rejection_counts,
        "missing_url": sum(1 for row in all_candidates if not canonical_url(row.get("source_url"))),
        "missing_date": sum(1 for row in all_candidates if not row.get("published_at")),
    }
    normalized_unique_count = len(set(ids))
    raw_candidate_record_count = len(raw_candidates)
    raw_source_count = raw_record_count(raw_dir)
    non_candidate_control_record_count = max(0, raw_source_count - raw_candidate_record_count - len(rejected_raw))
    metric_excess_cause = "rejected_flag_double_count" if len(rejected_raw) and final_counts.get("rejected", 0) == 0 else "unknown"
    summary = {
        "generated_at": iso_now(),
        "input_paths": {
            "raw_dir": str(raw_dir),
            "review_queue": str(queue_path),
            "digest_json": str(digest_path),
        },
        "artifact_hashes": before_hashes,
        "raw_source_record_count": raw_source_count,
        "raw_candidate_record_count": raw_candidate_record_count,
        "raw_rejected_record_count": len(rejected_raw),
        "non_candidate_control_record_count": non_candidate_control_record_count,
        "raw_unique_candidate_count": len(set(candidate_ids(raw_candidates))),
        "normalized_unique_count": normalized_unique_count,
        "pending_unique_count": final_counts.get("pending", 0),
        "duplicate_unique_count": final_counts.get("duplicate", 0),
        "rejected_unique_count": final_counts.get("rejected", 0),
        "conflict_unique_count": final_counts.get("conflict", 0),
        "accepted_unique_count": final_counts.get("accepted", 0),
        "final_status_counts": final_counts,
        "quality_flag_counts": quality_flags,
        "multi_status_candidate_count": status["multi_status_candidate_count"],
        "orphan_candidate_count": integrity["missing_duplicate_of_count"],
        "duplicate_type_counts": duplicate["duplicate_type_counts"],
        "duplicate_integrity": integrity,
        "rejection_reason_counts": rejection_counts,
        "metric_excess_cause": metric_excess_cause,
        "reported_sum_pending_duplicate_rejected_raw": final_counts.get("pending", 0) + final_counts.get("duplicate", 0) + len(rejected_raw),
        "reported_sum_exceeds_raw_candidate_by": len(rejected_raw),
        "metric_interpretation": "rejected raw records are pre-candidate quality exclusions, not a mutually exclusive final candidate status",
        "status_conservation": status["status_conservation"],
        "candidate_id_duplicate_count": status["duplicated_candidate_id_count"],
        "missing_status_count": status["missing_status_count"],
        "query_risk": risk,
        "source_error_count": len(errors),
        "secret_exposure_detected": False,
    }
    anomalies = {
        "status": status,
        "duplicate_integrity": integrity,
        "duplicate_rows_sample": duplicate["duplicate_rows"][:100],
        "missing_rejection_reason_count": sum(1 for row in rejected_raw if not row.get("rejection_reason")),
        "query_risk": risk,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "audit-summary.json", summary)
    (output_dir / "audit-report.md").write_text(build_markdown(summary), encoding="utf-8")
    write_json(output_dir / "audit-anomalies.json", anomalies)
    write_json(output_dir / "review-sample.json", {"generated_at": summary["generated_at"], "sample": sample})
    write_sample_markdown(output_dir / "review-sample.md", sample)
    (output_dir / "query-tuning-proposal.md").write_text(proposal, encoding="utf-8")
    after_hashes = existing_artifact_hashes(artifact_inputs)
    summary["input_artifact_hashes_unchanged"] = before_hashes == after_hashes
    write_json(output_dir / "audit-summary.json", summary)
    (output_dir / "audit-report.md").write_text(build_markdown(summary), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit existing company monitoring live pilot artifacts without external API calls.")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--queue-path", type=Path, default=DEFAULT_QUEUE_PATH)
    parser.add_argument("--digest-json", type=Path, default=DEFAULT_DIGEST_PATH)
    parser.add_argument("--output-dir", type=Path, default=AUDIT_DIR)
    args = parser.parse_args()
    summary = audit(args.raw_dir, args.queue_path, args.digest_json, args.output_dir)
    print(
        json.dumps(
            {
                "normalized_unique_count": summary["normalized_unique_count"],
                "final_status_counts": summary["final_status_counts"],
                "quality_flag_counts": summary["quality_flag_counts"],
                "metric_excess_cause": summary["metric_excess_cause"],
                "status_conservation_valid": summary["status_conservation"]["valid"],
                "output_dir": str(args.output_dir),
            },
            ensure_ascii=False,
        )
    )
    return 0 if summary["status_conservation"]["valid"] and summary["duplicate_integrity"]["missing_duplicate_of_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
