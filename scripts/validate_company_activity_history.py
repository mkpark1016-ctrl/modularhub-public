from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


EXPECTED_HISTORY_SCHEMA = "company-activity-history-v1"
EXPECTED_INDEX_SCHEMA = "company-activity-history-index-v1"
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


def load_history_dir(history_dir: Path | None) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    if history_dir is None or not history_dir.exists():
        return payloads
    for path in sorted(history_dir.glob("*.json")):
        try:
            payload = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            company_id = str(payload.get("companyId") or path.stem).strip()
            if company_id:
                payloads[company_id] = payload
    return payloads


def snapshot_ids_by_company(snapshot: dict[str, Any] | None) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    if not snapshot:
        return result
    for row in snapshot.get("companies") or []:
        if not isinstance(row, dict):
            continue
        company_id = str(row.get("companyId") or "").strip()
        if not company_id:
            continue
        result[company_id] = {
            str(activity.get("activityId"))
            for activity in row.get("activities") or []
            if isinstance(activity, dict) and activity.get("activityId")
        }
    return result


def history_ids(payload: dict[str, Any] | None) -> set[str]:
    if not payload:
        return set()
    return {
        str(activity.get("activityId"))
        for activity in payload.get("activities") or []
        if isinstance(activity, dict) and activity.get("activityId")
    }


def validate_activity_history(
    history_index: dict[str, Any],
    histories: dict[str, dict[str, Any]],
    company_payload: dict[str, Any],
    *,
    snapshot: dict[str, Any] | None = None,
    baseline_histories: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    errors: list[str] = []
    expected_company_ids = company_ids_from_payload(company_payload)
    expected_company_set = set(expected_company_ids)

    if history_index.get("schemaVersion") != EXPECTED_INDEX_SCHEMA:
        errors.append(f"unexpected history index schemaVersion: {history_index.get('schemaVersion')!r}")
    if parse_generated_at(history_index.get("generatedAt")) is None:
        errors.append("history index generatedAt must be a valid ISO datetime")

    rows = history_index.get("companies")
    if not isinstance(rows, list):
        return errors + ["history index companies must be an array"]

    index_company_ids = [str(row.get("companyId") or "") for row in rows if isinstance(row, dict)]
    if len(index_company_ids) != len(set(index_company_ids)):
        errors.append("duplicate companyId rows detected in history index")
    if set(index_company_ids) != expected_company_set:
        missing = sorted(expected_company_set - set(index_company_ids))
        extra = sorted(set(index_company_ids) - expected_company_set)
        errors.append(f"history company universe mismatch: missing={missing} extra={extra}")
    if history_index.get("companyCount") != len(expected_company_ids):
        errors.append(
            f"history companyCount mismatch: candidate={history_index.get('companyCount')} expected={len(expected_company_ids)}"
        )

    snapshot_ids = snapshot_ids_by_company(snapshot)
    baseline_histories = baseline_histories or {}
    seen_activity_ids: set[str] = set()
    total_activities = 0

    row_by_company = {
        str(row.get("companyId") or ""): row
        for row in rows
        if isinstance(row, dict) and row.get("companyId")
    }

    for company_id in expected_company_ids:
        row = row_by_company.get(company_id)
        if row is None:
            continue
        expected_path = f"company-activity-history/{company_id}.json"
        if row.get("path") != expected_path:
            errors.append(f"unexpected history path for {company_id}: {row.get('path')!r}")

        payload = histories.get(company_id)
        if payload is None:
            errors.append(f"missing history file for {company_id}")
            continue
        if payload.get("schemaVersion") != EXPECTED_HISTORY_SCHEMA:
            errors.append(f"unexpected history schemaVersion for {company_id}: {payload.get('schemaVersion')!r}")
        if parse_generated_at(payload.get("generatedAt")) is None:
            errors.append(f"invalid history generatedAt for {company_id}")
        if payload.get("companyId") != company_id:
            errors.append(f"history companyId mismatch for {company_id}: {payload.get('companyId')!r}")

        activities = payload.get("activities")
        if not isinstance(activities, list):
            errors.append(f"history activities must be an array for {company_id}")
            continue
        total_activities += len(activities)
        if payload.get("activityCount") != len(activities):
            errors.append(
                f"history activityCount mismatch for {company_id}: candidate={payload.get('activityCount')} actual={len(activities)}"
            )
        if row.get("activityCount") != len(activities):
            errors.append(
                f"history index activityCount mismatch for {company_id}: index={row.get('activityCount')} actual={len(activities)}"
            )

        published_dates: list[str] = []
        candidate_ids: set[str] = set()
        for activity in activities:
            if not isinstance(activity, dict):
                errors.append(f"history activity must be an object for {company_id}")
                continue
            activity_id = str(activity.get("activityId") or "")
            if not activity_id:
                errors.append(f"missing history activityId for {company_id}")
            else:
                candidate_ids.add(activity_id)
                if activity_id in seen_activity_ids:
                    errors.append(f"duplicate history activityId detected: {activity_id}")
                seen_activity_ids.add(activity_id)
            if activity.get("companyId") != company_id:
                errors.append(f"history activity companyId mismatch for {activity_id or company_id}")
            if not activity.get("title"):
                errors.append(f"missing history activity title for {activity_id or company_id}")
            published_at = str(activity.get("publishedAt") or "")
            if not published_at:
                errors.append(f"missing history publishedAt for {activity_id or company_id}")
            else:
                published_dates.append(published_at)
            if activity.get("confidence") not in ALLOWED_CONFIDENCE:
                errors.append(f"invalid history confidence for {activity_id or company_id}: {activity.get('confidence')!r}")
            if not is_http_url(activity.get("sourceUrl")):
                errors.append(f"invalid history sourceUrl for {activity_id or company_id}")

        if published_dates != sorted(published_dates, reverse=True):
            errors.append(f"history activities are not newest-first for {company_id}")

        missing_snapshot_ids = snapshot_ids.get(company_id, set()) - candidate_ids
        if missing_snapshot_ids:
            errors.append(
                f"history missing snapshot activities for {company_id}: {sorted(missing_snapshot_ids)}"
            )

        missing_baseline_ids = history_ids(baseline_histories.get(company_id)) - candidate_ids
        if missing_baseline_ids:
            errors.append(
                f"refusing destructive history shrink for {company_id}: missing={sorted(missing_baseline_ids)}"
            )

        latest = activities[0].get("publishedAt") if activities else None
        earliest = activities[-1].get("publishedAt") if activities else None
        if row.get("latestPublishedAt") != latest:
            errors.append(f"history latestPublishedAt mismatch for {company_id}")
        if row.get("earliestPublishedAt") != earliest:
            errors.append(f"history earliestPublishedAt mismatch for {company_id}")

    if history_index.get("totalActivityCount") != total_activities:
        errors.append(
            f"history totalActivityCount mismatch: index={history_index.get('totalActivityCount')} actual={total_activities}"
        )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate per-company activity history publication.")
    parser.add_argument("--history-index", type=Path, required=True)
    parser.add_argument("--history-dir", type=Path, required=True)
    parser.add_argument("--companies", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--baseline-history-dir", type=Path)
    args = parser.parse_args()

    history_index = load_json(args.history_index)
    histories = load_history_dir(args.history_dir)
    companies = load_json(args.companies)
    snapshot = load_json(args.snapshot) if args.snapshot and args.snapshot.exists() else None
    baseline_histories = load_history_dir(args.baseline_history_dir)
    errors = validate_activity_history(
        history_index,
        histories,
        companies,
        snapshot=snapshot,
        baseline_histories=baseline_histories,
    )

    if errors:
        print("COMPANY ACTIVITY HISTORY GUARD FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "COMPANY ACTIVITY HISTORY GUARD PASSED "
        f"companies={history_index.get('companyCount')} "
        f"activities={history_index.get('totalActivityCount')} "
        f"generatedAt={history_index.get('generatedAt')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
