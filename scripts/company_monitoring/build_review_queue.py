from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.company_monitoring.classify_candidate import classify_candidate  # noqa: E402
from scripts.company_monitoring.common import DATA_DIR, RAW_DIR, REPORT_DIR, iso_now, read_json, write_json  # noqa: E402
from scripts.company_monitoring.dedupe_candidates import counts_by_status, dedupe_candidates  # noqa: E402


RAW_FILES = ("dart_raw.json", "naver_search_raw.json")


def load_raw_candidates(raw_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for name in RAW_FILES:
        path = raw_dir / name
        if not path.exists():
            continue
        payload = read_json(path)
        for result in payload.get("results", []):
            if result.get("status") == "error":
                errors.append(result)
            rejected.extend(result.get("rejected") or [])
            candidates.extend(result.get("candidates") or [])
    return candidates, errors, rejected


def detect_conflicts(candidate: dict[str, Any]) -> dict[str, Any]:
    row = dict(candidate)
    blockers = list(row.get("promotion_blockers") or [])
    if row.get("domain") in {"identity", "financial", "production", "project", "technology"}:
        if row.get("current_value") not in (None, "", {}, []):
            blockers.append("baseline_conflict_requires_human_review")
    row["promotion_blockers"] = list(dict.fromkeys(blockers))
    return row


def build_review_queue(raw_dir: Path = RAW_DIR) -> dict[str, Any]:
    raw_candidates, errors, rejected = load_raw_candidates(raw_dir)
    classified = [detect_conflicts(classify_candidate(candidate)) for candidate in raw_candidates]
    deduped = dedupe_candidates(classified)
    pending = [candidate for candidate in deduped if candidate.get("review_status") == "pending"]
    fetched_at = iso_now()
    status_counts = counts_by_status(deduped)
    source_counts = Counter(candidate.get("source_type", "unknown") for candidate in deduped)
    domain_counts = Counter(candidate.get("domain", "unknown") for candidate in deduped)
    company_counts = Counter(candidate.get("company_id", "unknown") for candidate in deduped)
    conflict_count = sum(1 for candidate in deduped if any("conflict" in blocker for blocker in candidate.get("promotion_blockers", [])))
    digest = {
        "generated_at": fetched_at,
        "candidate_total": len(deduped),
        "pending_count": len(pending),
        "duplicate_count": status_counts.get("duplicate", 0),
        "conflict_count": conflict_count,
        "rejected_raw_count": len(rejected),
        "source_counts": dict(sorted(source_counts.items())),
        "domain_counts": dict(sorted(domain_counts.items())),
        "company_counts": dict(sorted(company_counts.items())),
        "source_errors": errors,
        "high_confidence_candidates": [
            {
                "candidate_id": candidate["candidate_id"],
                "company_id": candidate["company_id"],
                "title": candidate["title"],
                "source_type": candidate["source_type"],
                "domain": candidate["domain"],
            }
            for candidate in deduped
            if candidate.get("confidence") == "high" and candidate.get("review_status") == "pending"
        ][:20],
    }
    return {
        "schema_version": "2026-07-18",
        "generated_at": fetched_at,
        "review_queue": pending,
        "all_candidates": deduped,
        "rejected_raw": rejected,
        "digest": digest,
    }


def write_digest_markdown(path: Path, digest: dict[str, Any]) -> None:
    lines = [
        "# Company Intelligence Monitoring Digest",
        "",
        f"- Generated at: `{digest['generated_at']}`",
        f"- Pending candidates: {digest['pending_count']}",
        f"- Duplicate candidates: {digest['duplicate_count']}",
        f"- Conflict candidates: {digest['conflict_count']}",
        f"- Rejected raw records: {digest['rejected_raw_count']}",
        "",
        "## Source Counts",
    ]
    for key, value in digest.get("source_counts", {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Domain Counts"])
    for key, value in digest.get("domain_counts", {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Source Errors"])
    if digest.get("source_errors"):
        for error in digest["source_errors"]:
            lines.append(f"- {error.get('source_type')} / {error.get('company_id')}: {error.get('error_type')}")
    else:
        lines.append("- none")
    lines.extend(["", "## High Confidence Candidates"])
    if digest.get("high_confidence_candidates"):
        for candidate in digest["high_confidence_candidates"]:
            lines.append(f"- {candidate['company_id']} · {candidate['domain']} · {candidate['title']}")
    else:
        lines.append("- none")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build pending review queue from raw company monitoring candidates.")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--queue-path", type=Path, default=DATA_DIR / "review_queue.json")
    parser.add_argument("--digest-json", type=Path, default=REPORT_DIR / "latest_digest.json")
    parser.add_argument("--digest-md", type=Path, default=REPORT_DIR / "latest_digest.md")
    args = parser.parse_args()
    payload = build_review_queue(args.raw_dir)
    write_json(args.queue_path, {"schema_version": payload["schema_version"], "generated_at": payload["generated_at"], "review_queue": payload["review_queue"]})
    write_json(args.digest_json, payload["digest"])
    write_digest_markdown(args.digest_md, payload["digest"])
    print(json.dumps({"pending_count": payload["digest"]["pending_count"], "duplicate_count": payload["digest"]["duplicate_count"], "conflict_count": payload["digest"]["conflict_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
