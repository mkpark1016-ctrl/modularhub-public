from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_company_activity_timeline import (  # noqa: E402
    FILTER_CONFIDENCES,
    build_alias_registry,
    business_activity,
    dedupe_key,
    find_company_matches,
    items_from_payload,
    load_companies,
    load_json,
    news_activity,
    parse_datetime,
    sort_key,
)


DEFAULT_COMPANIES = ROOT / "frontend/public/data/companies/companies.json"
DEFAULT_NEWS = ROOT / "frontend/public/data/news.json"
DEFAULT_BUSINESS = ROOT / "frontend/public/data/business.json"
DEFAULT_SNAPSHOT = ROOT / "frontend/public/data/companies/company-activities.json"
DEFAULT_HISTORY_DIR = ROOT / "frontend/public/data/companies/company-activity-history"
DEFAULT_HISTORY_INDEX = ROOT / "frontend/public/data/companies/company-activity-history-index.json"
DEFAULT_AUDIT_DIR = ROOT / "artifacts/company_activity_timeline"

HISTORY_SCHEMA_VERSION = "company-activity-history-v1"
HISTORY_INDEX_SCHEMA_VERSION = "company-activity-history-index-v1"


def load_existing_histories(history_dir: Path) -> dict[str, dict[str, Any]]:
    histories: dict[str, dict[str, Any]] = {}
    if not history_dir.exists():
        return histories
    for path in sorted(history_dir.glob("*.json")):
        try:
            payload = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("activities"), list):
            continue
        company_id = str(payload.get("companyId") or path.stem).strip()
        if company_id:
            histories[company_id] = payload
    return histories


def _seed_snapshot(by_company: dict[str, list[dict[str, Any]]], snapshot: dict[str, Any] | None) -> int:
    count = 0
    if not snapshot:
        return count
    for row in snapshot.get("companies") or []:
        if not isinstance(row, dict):
            continue
        company_id = str(row.get("companyId") or "").strip()
        if not company_id:
            continue
        for activity in row.get("activities") or []:
            if isinstance(activity, dict):
                by_company[company_id].append(activity)
                count += 1
    return count


def _seed_histories(
    by_company: dict[str, list[dict[str, Any]]],
    existing_histories: dict[str, dict[str, Any]],
) -> int:
    count = 0
    for company_id, payload in existing_histories.items():
        for activity in payload.get("activities") or []:
            if isinstance(activity, dict):
                by_company[company_id].append(activity)
                count += 1
    return count


def build_company_activity_history(
    *,
    companies: list[dict[str, Any]],
    news_items: list[dict[str, Any]],
    business_items: list[dict[str, Any]],
    snapshot_payload: dict[str, Any] | None,
    existing_histories: dict[str, dict[str, Any]] | None,
    now: datetime,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any], dict[str, Any]]:
    aliases, collisions = build_alias_registry(companies)
    stats: Counter[str] = Counter()
    by_company: dict[str, list[dict[str, Any]]] = defaultdict(list)

    stats["existing_history_count"] = _seed_histories(by_company, existing_histories or {})
    stats["snapshot_seed_count"] = _seed_snapshot(by_company, snapshot_payload)

    for record in news_items:
        matches, match_stats = find_company_matches(record, aliases, source_kind="news")
        stats.update(match_stats)
        for match in matches:
            activity = news_activity(record, match)
            if activity.get("confidence") in FILTER_CONFIDENCES and parse_datetime(activity.get("publishedAt")):
                by_company[activity["companyId"]].append(activity)
                stats["news_history_candidate_count"] += 1

    for record in business_items:
        matches, match_stats = find_company_matches(record, aliases, source_kind="business")
        stats.update(match_stats)
        for match in matches:
            activity = business_activity(record, match)
            if activity.get("confidence") in FILTER_CONFIDENCES and parse_datetime(activity.get("publishedAt")):
                by_company[activity["companyId"]].append(activity)
                stats["business_history_candidate_count"] += 1

    company_ids = [str(company.get("company_id")) for company in companies if company.get("company_id")]
    history_payloads: dict[str, dict[str, Any]] = {}
    index_rows: list[dict[str, Any]] = []
    duplicate_excluded = 0

    for company_id in company_ids:
        deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
        for activity in sorted(by_company.get(company_id, []), key=sort_key):
            if not isinstance(activity, dict):
                continue
            if activity.get("confidence") not in FILTER_CONFIDENCES:
                continue
            if not parse_datetime(activity.get("publishedAt")):
                continue
            if str(activity.get("companyId") or "") != company_id:
                continue
            key = dedupe_key(activity)
            if key in deduped:
                duplicate_excluded += 1
            deduped[key] = activity

        activities = sorted(deduped.values(), key=sort_key, reverse=True)
        payload = {
            "schemaVersion": HISTORY_SCHEMA_VERSION,
            "generatedAt": now.isoformat(),
            "companyId": company_id,
            "activityCount": len(activities),
            "activities": activities,
        }
        history_payloads[company_id] = payload
        index_rows.append(
            {
                "companyId": company_id,
                "activityCount": len(activities),
                "latestPublishedAt": activities[0].get("publishedAt") if activities else None,
                "earliestPublishedAt": activities[-1].get("publishedAt") if activities else None,
                "path": f"company-activity-history/{company_id}.json",
            }
        )

    history_index = {
        "schemaVersion": HISTORY_INDEX_SCHEMA_VERSION,
        "generatedAt": now.isoformat(),
        "companyCount": len(company_ids),
        "totalActivityCount": sum(row["activityCount"] for row in index_rows),
        "companies": index_rows,
    }
    audit = {
        "schemaVersion": "company-activity-history-audit-v1",
        "generatedAt": now.isoformat(),
        "companyCount": len(company_ids),
        "totalActivityCount": history_index["totalActivityCount"],
        "companyActivityCounts": {row["companyId"]: row["activityCount"] for row in index_rows},
        "existingHistoryCount": stats["existing_history_count"],
        "snapshotSeedCount": stats["snapshot_seed_count"],
        "newsHistoryCandidateCount": stats["news_history_candidate_count"],
        "businessHistoryCandidateCount": stats["business_history_candidate_count"],
        "duplicateExcludedCount": duplicate_excluded,
        "ambiguousExcludedCount": stats["ambiguous_excluded"],
        "identityGuardExcludedCount": stats["identity_guard_excluded"],
        "orderingOrgOnlyExcludedCount": stats["ordering_org_only_excluded"],
        "aliasCollisionCount": len(collisions),
    }
    return history_payloads, history_index, audit


def render_history_audit_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# Company Activity History Audit",
        "",
        f"- Company count: {audit['companyCount']}",
        f"- Total retained history activities: {audit['totalActivityCount']}",
        f"- Existing history seed: {audit['existingHistoryCount']}",
        f"- Snapshot migration seed: {audit['snapshotSeedCount']}",
        f"- News candidates: {audit['newsHistoryCandidateCount']}",
        f"- Business candidates: {audit['businessHistoryCandidateCount']}",
        f"- Duplicate excluded: {audit['duplicateExcludedCount']}",
        "",
        "## Company History Counts",
        "",
    ]
    for company_id, count in sorted(audit["companyActivityCounts"].items()):
        lines.append(f"- {company_id}: {count}")
    return "\n".join(lines) + "\n"


def write_history_outputs(
    history_payloads: dict[str, dict[str, Any]],
    history_index: dict[str, Any],
    audit: dict[str, Any],
    *,
    history_dir: Path,
    history_index_path: Path,
    audit_dir: Path,
) -> None:
    history_dir.mkdir(parents=True, exist_ok=True)
    for company_id, payload in history_payloads.items():
        path = history_dir / f"{company_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    history_index_path.parent.mkdir(parents=True, exist_ok=True)
    history_index_path.write_text(json.dumps(history_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "company-activity-history-audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (audit_dir / "company-activity-history-audit.md").write_text(
        render_history_audit_markdown(audit),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build non-destructive per-company activity history files.")
    parser.add_argument("--companies", type=Path, default=DEFAULT_COMPANIES)
    parser.add_argument("--news", type=Path, default=DEFAULT_NEWS)
    parser.add_argument("--business", type=Path, default=DEFAULT_BUSINESS)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--history-dir", type=Path, default=DEFAULT_HISTORY_DIR)
    parser.add_argument("--history-index", type=Path, default=DEFAULT_HISTORY_INDEX)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT_DIR)
    parser.add_argument("--now", default="")
    args = parser.parse_args()

    now = parse_datetime(args.now) if args.now else datetime.now(timezone.utc)
    if now is None:
        raise SystemExit("--now must be an ISO datetime")

    companies = load_companies(args.companies)
    news_items = items_from_payload(load_json(args.news))
    business_items = items_from_payload(load_json(args.business))
    snapshot_payload = load_json(args.snapshot) if args.snapshot.exists() else None
    existing_histories = load_existing_histories(args.history_dir)

    history_payloads, history_index, audit = build_company_activity_history(
        companies=companies,
        news_items=news_items,
        business_items=business_items,
        snapshot_payload=snapshot_payload,
        existing_histories=existing_histories,
        now=now,
    )
    write_history_outputs(
        history_payloads,
        history_index,
        audit,
        history_dir=args.history_dir,
        history_index_path=args.history_index,
        audit_dir=args.audit_dir,
    )
    print(
        "company_activity_history "
        f"companies={audit['companyCount']} "
        f"activities={audit['totalActivityCount']} "
        f"existing={audit['existingHistoryCount']} "
        f"snapshot_seed={audit['snapshotSeedCount']} "
        f"duplicates={audit['duplicateExcludedCount']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
