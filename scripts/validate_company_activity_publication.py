from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


EXPECTED_SCHEMA_VERSION = "company-activities-v1"
ALLOWED_CONFIDENCE = {"high", "medium"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def company_ids_from_payload(payload: Any) -> list[str]:
    rows = payload.get("companies") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return [str(row.get("company_id") or "") for row in rows if isinstance(row, dict) and row.get("company_id")]


def parse_generated_at(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_http_url(value: Any) -> bool:
    if value in (None, ""):
        return True
    parsed = urlparse(str(value))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_activity_payload(
    candidate: dict[str, Any],
    company_payload: dict[str, Any],
    baseline: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    expected_company_ids = company_ids_from_payload(company_payload)
    expected_company_set = set(expected_company_ids)

    if candidate.get("schemaVersion") != EXPECTED_SCHEMA_VERSION:
        errors.append(f"unexpected schemaVersion: {candidate.get('schemaVersion')!r}")
    if parse_generated_at(candidate.get("generatedAt")) is None:
        errors.append("generatedAt must be a valid ISO datetime")

    rows = candidate.get("companies")
    if not isinstance(rows, list):
        return errors + ["companies must be an array"]

    candidate_company_ids = [str(row.get("companyId") or "") for row in rows if isinstance(row, dict)]
    if len(candidate_company_ids) != len(set(candidate_company_ids)):
        errors.append("duplicate companyId rows detected")
    if set(candidate_company_ids) != expected_company_set:
        missing = sorted(expected_company_set - set(candidate_company_ids))
        extra = sorted(set(candidate_company_ids) - expected_company_set)
        errors.append(f"company universe mismatch: missing={missing} extra={extra}")
    if candidate.get("companyCount") != len(expected_company_ids):
        errors.append(
            f"companyCount mismatch: candidate={candidate.get('companyCount')} expected={len(expected_company_ids)}"
        )
    if len(rows) != len(expected_company_ids):
        errors.append(f"company row count mismatch: candidate={len(rows)} expected={len(expected_company_ids)}")

    seen_activity_ids: set[str] = set()
    total_activities = 0
    for row in rows:
        if not isinstance(row, dict):
            errors.append("company row must be an object")
            continue
        company_id = str(row.get("companyId") or "")
        activities = row.get("activities")
        if not isinstance(activities, list):
            errors.append(f"activities must be an array for {company_id or '<missing>'}")
            continue
        total_activities += len(activities)
        if row.get("activityCount") != len(activities):
            errors.append(
                f"activityCount mismatch for {company_id}: candidate={row.get('activityCount')} actual={len(activities)}"
            )
        for activity in activities:
            if not isinstance(activity, dict):
                errors.append(f"activity must be an object for {company_id}")
                continue
            activity_id = str(activity.get("activityId") or "")
            if not activity_id:
                errors.append(f"missing activityId for {company_id}")
            elif activity_id in seen_activity_ids:
                errors.append(f"duplicate activityId detected: {activity_id}")
            else:
                seen_activity_ids.add(activity_id)
            if activity.get("companyId") != company_id:
                errors.append(f"activity companyId mismatch for {activity_id or company_id}")
            if not activity.get("title"):
                errors.append(f"missing activity title for {activity_id or company_id}")
            if not activity.get("publishedAt"):
                errors.append(f"missing publishedAt for {activity_id or company_id}")
            if activity.get("confidence") not in ALLOWED_CONFIDENCE:
                errors.append(f"invalid confidence for {activity_id or company_id}: {activity.get('confidence')!r}")
            if not is_http_url(activity.get("sourceUrl")):
                errors.append(f"invalid sourceUrl for {activity_id or company_id}")

    if baseline:
        baseline_rows = baseline.get("companies") if isinstance(baseline, dict) else None
        baseline_total = 0
        if isinstance(baseline_rows, list):
            for row in baseline_rows:
                if isinstance(row, dict) and isinstance(row.get("activities"), list):
                    baseline_total += len(row["activities"])
        if baseline_total > 0 and total_activities == 0:
            errors.append(
                f"refusing destructive activity shrink: baseline_total={baseline_total} candidate_total=0"
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate company activity timeline before public publication.")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--companies", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()

    candidate = load_json(args.candidate)
    companies = load_json(args.companies)
    baseline = load_json(args.baseline) if args.baseline and args.baseline.exists() else None
    errors = validate_activity_payload(candidate, companies, baseline)

    rows = candidate.get("companies") if isinstance(candidate, dict) else []
    activity_total = sum(
        len(row.get("activities") or [])
        for row in rows or []
        if isinstance(row, dict) and isinstance(row.get("activities"), list)
    )
    if errors:
        print("COMPANY ACTIVITY PUBLICATION GUARD FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "COMPANY ACTIVITY PUBLICATION GUARD PASSED "
        f"companies={candidate.get('companyCount')} activities={activity_total} generatedAt={candidate.get('generatedAt')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
