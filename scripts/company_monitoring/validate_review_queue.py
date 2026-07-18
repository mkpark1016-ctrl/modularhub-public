from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.company_monitoring.common import DATA_DIR, PROJECT_CREDIT_BLOCKED_STATUSES, public_company_ids, read_json  # noqa: E402


REQUIRED = {
    "candidate_id",
    "company_id",
    "candidate_kind",
    "domain",
    "title",
    "summary",
    "source_id",
    "source_type",
    "source_tier",
    "publisher",
    "source_url",
    "fetched_at",
    "evidence_hash",
    "entity_match_score",
    "relevance_score",
    "confidence",
    "review_status",
    "promotion_blockers",
    "duplicate_of",
}
SECRET_PATTERNS = (
    re.compile(r"DART_API_KEY\s*=", re.I),
    re.compile(r"NAVER_API_HUB_CLIENT_SECRET\s*=", re.I),
    re.compile(r"crtfc_key=", re.I),
    re.compile(r"X-Naver-Client-Secret", re.I),
)


def validate_candidate(candidate: dict[str, Any], allowed_companies: set[str]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    missing = sorted(REQUIRED - set(candidate))
    if missing:
        issues.append({"severity": "error", "code": "required_field_missing", "candidate_id": candidate.get("candidate_id"), "fields": missing})
    if candidate.get("company_id") not in allowed_companies:
        issues.append({"severity": "error", "code": "orphan_company_id", "candidate_id": candidate.get("candidate_id"), "company_id": candidate.get("company_id")})
    if candidate.get("review_status") != "pending":
        issues.append({"severity": "error", "code": "review_queue_must_only_contain_pending", "candidate_id": candidate.get("candidate_id"), "review_status": candidate.get("review_status")})
    if candidate.get("project_credit") is True and candidate.get("event_status") in PROJECT_CREDIT_BLOCKED_STATUSES:
        issues.append({"severity": "error", "code": "blocked_status_project_credit_true", "candidate_id": candidate.get("candidate_id")})
    if candidate.get("source_type") == "naver_search" and len(str(candidate.get("summary", ""))) > 500:
        issues.append({"severity": "error", "code": "naver_summary_too_long", "candidate_id": candidate.get("candidate_id")})
    text = json.dumps(candidate, ensure_ascii=False)
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            issues.append({"severity": "error", "code": "secret_literal_exposed", "candidate_id": candidate.get("candidate_id")})
    if "0" == str(candidate.get("proposed_value")) and candidate.get("confidence") == "low":
        issues.append({"severity": "warning", "code": "suspicious_zero_value", "candidate_id": candidate.get("candidate_id")})
    return issues


def validate_queue(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    allowed = public_company_ids()
    candidates = payload.get("review_queue") or []
    issues: list[dict[str, Any]] = []
    ids = [candidate.get("candidate_id") for candidate in candidates]
    duplicates = [candidate_id for candidate_id, count in Counter(ids).items() if candidate_id and count > 1]
    for duplicate in duplicates:
        issues.append({"severity": "error", "code": "duplicate_candidate_id", "candidate_id": duplicate})
    for candidate in candidates:
        issues.extend(validate_candidate(candidate, allowed))
    error_count = sum(1 for issue in issues if issue["severity"] == "error")
    return {
        "valid": error_count == 0,
        "candidate_count": len(candidates),
        "issue_count": len(issues),
        "error_count": error_count,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate company monitoring review queue.")
    parser.add_argument("--queue-path", type=Path, default=DATA_DIR / "review_queue.json")
    args = parser.parse_args()
    result = validate_queue(args.queue_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
