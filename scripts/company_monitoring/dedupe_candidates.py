from __future__ import annotations

from collections import defaultdict
from typing import Any

from scripts.company_monitoring.common import canonical_url, normalize_title


def duplicate_keys(candidate: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    url = canonical_url(candidate.get("source_url"))
    if url:
        keys.append(f"url:{url}")
    doc = candidate.get("document_id")
    if doc:
        keys.append(f"doc:{candidate.get('source_type')}:{doc}")
    evidence_hash = candidate.get("evidence_hash")
    if evidence_hash:
        keys.append(f"hash:{evidence_hash}")
    title = normalize_title(candidate.get("title"))
    if title:
        keys.append(f"title:{candidate.get('company_id')}:{title}:{candidate.get('published_at') or ''}")
    return keys


def dedupe_candidates(candidates: list[dict[str, Any]], reviewed: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    seen: dict[str, str] = {}
    output: list[dict[str, Any]] = []
    for old in reviewed or []:
        if old.get("review_status") in {"accepted", "rejected", "duplicate", "superseded"}:
            for key in duplicate_keys(old):
                seen[key] = old.get("candidate_id", "")
    for candidate in candidates:
        row = dict(candidate)
        duplicate_of = None
        for key in duplicate_keys(row):
            if key in seen:
                duplicate_of = seen[key]
                break
        if duplicate_of:
            row["review_status"] = "duplicate"
            row["duplicate_of"] = duplicate_of
        else:
            row["review_status"] = row.get("review_status") or "pending"
            row["duplicate_of"] = None
            for key in duplicate_keys(row):
                seen[key] = row["candidate_id"]
        output.append(row)
    return output


def counts_by_status(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for candidate in candidates:
        counts[str(candidate.get("review_status") or "unknown")] += 1
    return dict(sorted(counts.items()))
