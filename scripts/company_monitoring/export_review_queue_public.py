from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.company_monitoring.common import DATA_DIR, REPORT_DIR, read_json, write_json


DEFAULT_OUTPUT = ROOT / "frontend" / "public" / "data" / "company-intelligence" / "review-queue.json"
DEFAULT_MANIFEST_OUTPUT = ROOT / "frontend" / "public" / "data" / "company-intelligence" / "manifest.json"
COMPANY_CONFIG = ROOT / "config" / "company_monitoring" / "companies.json"
SECRET_PATTERNS = (
    re.compile(r"crtfc_key\s*=", re.I),
    re.compile(r"DART_API_KEY\s*=", re.I),
    re.compile(r"NAVER_API_HUB_CLIENT_SECRET\s*=", re.I),
    re.compile(r"X-NCP-APIGW-API-KEY-ID\s*[:=]\s*\S+", re.I),
    re.compile(r"X-NCP-APIGW-API-KEY\s*[:=]\s*\S+", re.I),
    re.compile(r"BEGIN (?:RSA|OPENSSH|PRIVATE) KEY", re.I),
)


def company_names(path: Path = COMPANY_CONFIG) -> dict[str, str]:
    payload = read_json(path)
    return {
        row["company_id"]: row.get("canonical_name") or row["company_id"]
        for row in payload.get("companies", [])
        if row.get("company_id")
    }


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def sanitize_item(row: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    company_id = safe_text(row.get("company_id"))
    return {
        "candidateId": safe_text(row.get("candidate_id")),
        "companyId": company_id,
        "companyName": names.get(company_id, company_id),
        "source": safe_text(row.get("source_type")),
        "status": safe_text(row.get("review_status") or "pending"),
        "title": safe_text(row.get("title")),
        "originalUrl": safe_text(row.get("source_url")),
        "publishedAt": safe_text(row.get("published_at")),
        "collectedAt": safe_text(row.get("fetched_at")),
        "matchedKeyword": safe_text(row.get("matched_keyword") or row.get("query")),
        "matchedAlias": safe_text(row.get("matched_alias")),
        "matchReason": "; ".join(safe_text(value) for value in row.get("promotion_blockers", []) if safe_text(value)),
        "duplicateType": safe_text(row.get("duplicate_type")),
        "duplicateOf": safe_text(row.get("duplicate_of")),
        "rejectionReason": safe_text(row.get("rejection_reason")),
    }


def source_counts(items: list[dict[str, Any]], digest: dict[str, Any]) -> dict[str, int]:
    counts = {str(key): int(value) for key, value in (digest.get("source_counts") or {}).items()}
    for item in items:
        source = item.get("source") or "unknown"
        counts[source] = counts.get(source, 0) + 0
    counts.setdefault("dart", 0)
    counts.setdefault("naver_search", 0)
    return counts


def build_manifest(
    *,
    items: list[dict[str, Any]],
    digest: dict[str, Any],
    names: dict[str, str],
    lookback_days: int,
    source_run_commit: str | None,
) -> dict[str, Any]:
    final_status_counts = digest.get("final_status_counts") or {}
    quality_flag_counts = digest.get("quality_flag_counts") or {}
    counts = {
        "rawSourceRecords": int(digest.get("raw_source_record_count") or 0),
        "rawCandidateRecords": int(digest.get("raw_candidate_count") or digest.get("raw_candidate_records") or digest.get("raw_candidate_record_count") or 0),
        "rawRejectedRecords": int(digest.get("raw_rejected_record_count") or digest.get("rejected_raw_count") or 0),
        "nonCandidateControlRecords": int(digest.get("non_candidate_control_record_count") or 0),
        "normalizedUniqueCandidates": int(digest.get("candidate_total") or len(items)),
        "pending": int(final_status_counts.get("pending", digest.get("pending_count") or 0)),
        "duplicate": int(final_status_counts.get("duplicate", digest.get("duplicate_count") or 0)),
        "rejected": int(final_status_counts.get("rejected", 0)),
        "conflict": int(final_status_counts.get("conflict", digest.get("conflict_count") or 0)),
        "accepted": int(final_status_counts.get("accepted", 0)),
        "qualityRejected": int(quality_flag_counts.get("raw_rejected", digest.get("rejected_raw_count") or 0)),
        "sourceCounts": source_counts(items, digest),
    }
    company_ids = sorted({item["companyId"] for item in items if item.get("companyId")})
    return {
        "schemaVersion": "company-intelligence-review-queue.public.v1",
        "generatedAt": digest.get("generated_at") or "",
        "sourceRunCommit": source_run_commit or os.getenv("GITHUB_SHA") or "",
        "lookbackDays": lookback_days,
        "companies": [{"companyId": company_id, "companyName": names.get(company_id, company_id)} for company_id in company_ids],
        "sources": ["dart", "naver_search"],
        "counts": counts,
        "itemCount": len(items),
    }


def assert_no_secret(payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            raise ValueError("secret-like value detected in public review queue export")


def export_public_review_queue(
    *,
    input_path: Path,
    digest_path: Path,
    output_path: Path,
    manifest_output_path: Path,
    lookback_days: int = 30,
    source_run_commit: str | None = None,
) -> dict[str, Any]:
    payload = read_json(input_path)
    if not isinstance(payload.get("review_queue"), list):
        raise ValueError("input review queue must contain a review_queue array")
    digest = read_json(digest_path) if digest_path.exists() else {}
    names = company_names()
    items = [sanitize_item(row, names) for row in payload["review_queue"]]
    items.sort(key=lambda item: (item.get("publishedAt") or "", item.get("candidateId") or ""), reverse=True)
    public_payload = {
        "schemaVersion": "company-intelligence-review-queue.public.v1",
        "generatedAt": digest.get("generated_at") or payload.get("generated_at") or "",
        "items": items,
    }
    manifest = build_manifest(
        items=items,
        digest=digest,
        names=names,
        lookback_days=lookback_days,
        source_run_commit=source_run_commit,
    )
    assert_no_secret(public_payload)
    assert_no_secret(manifest)
    write_json(output_path, public_payload)
    write_json(manifest_output_path, manifest)
    return {"item_count": len(items), "output": str(output_path), "manifest_output": str(manifest_output_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a sanitized public company intelligence review queue JSON.")
    parser.add_argument("--input", type=Path, default=DATA_DIR / "review_queue.json")
    parser.add_argument("--digest", type=Path, default=REPORT_DIR / "latest_digest.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest-output", type=Path, default=DEFAULT_MANIFEST_OUTPUT)
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--source-run-commit", default="")
    args = parser.parse_args()
    result = export_public_review_queue(
        input_path=args.input,
        digest_path=args.digest,
        output_path=args.output,
        manifest_output_path=args.manifest_output,
        lookback_days=args.lookback_days,
        source_run_commit=args.source_run_commit,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
