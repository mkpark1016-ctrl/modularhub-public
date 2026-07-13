#!/usr/bin/env python3
"""Audit business collection warning impact without changing collectors.

The audit intentionally works from already-published data, optional local
collect_logs, and git history. It does not call source APIs or mutate public
JSON, so it can be run in CI as a non-blocking diagnostic artifact.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
KST = timezone.utc

PUBLIC_BUSINESS = ROOT / "frontend" / "public" / "data" / "business.json"
OUTPUT_DIR = ROOT / "artifacts" / "business-collection-impact-audit"

SOURCE_HEALTHY_STATES = {"success", "success_no_match", "success_no_public_match", "success_no_matches"}
SOURCE_FAILURE_STATES = {"failed", "not_collected"}
DISABLED_STATES = {"disabled_stopped"}

FIXTURES = [
    {
        "fixture_key": "jeju_medical_modular",
        "title_contains": "제주대학교 의과대학 모듈러 교사",
        "expected_source": "나라장터",
        "expected_type": "bid",
    },
    {
        "fixture_key": "busan_electronic_modular_dorm",
        "title_contains": "부산전자공업고등학교 콘크리트 모듈러 기숙사",
        "expected_source": "나라장터",
        "expected_type": "bid",
    },
    {
        "fixture_key": "icheon_jeil_procurement_plan",
        "title_contains": "이천제일고 공간재구조화",
        "expected_source": "나라장터",
        "expected_type": "procurement_plan",
    },
    {
        "fixture_key": "seongui_known_important_bid",
        "title_contains": "성의여자고등학교 임시교사",
        "expected_source": "나라장터",
        "expected_type": "bid",
    },
]


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def parse_datetime(value: Any) -> datetime | None:
    text = clean(value)
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    for candidate in (normalized, normalized[:19], normalized[:10]):
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            continue
    return None


def hours_between(later: datetime | None, earlier: datetime | None) -> float | None:
    if later is None or earlier is None:
        return None
    return max(0.0, (later - earlier).total_seconds() / 3600)


def staleness_bucket(hours: float | None) -> str:
    if hours is None:
        return "unknown"
    if hours <= 24:
        return "current"
    if hours <= 48:
        return "delayed"
    if hours <= 72:
        return "stale_warning"
    return "stale_source"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def business_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items", [])
    return items if isinstance(items, list) else []


def item_identity(item: dict[str, Any]) -> str:
    for key in ("id", "source_record_id", "bid_no", "plan_no", "title"):
        value = clean(item.get(key))
        if value:
            return value
    return ""


def source_matches(*names: str) -> Callable[[dict[str, Any]], bool]:
    wanted = set(names)
    return lambda item: clean(item.get("source")) in wanted or clean(item.get("source_name")) in wanted


def count_items(items: Iterable[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool]) -> int:
    return sum(1 for item in items if predicate(item))


def latest_posted_at(items: Iterable[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool]) -> datetime | None:
    dates = [
        parse_datetime(item.get("posted_at") or item.get("last_seen_at") or item.get("due_at"))
        for item in items
        if predicate(item)
    ]
    dates = [date for date in dates if date is not None]
    return max(dates) if dates else None


def read_collect_logs(limit: int = 500) -> list[dict[str, Any]]:
    db_path: Path | None = None
    try:
        sys.path.insert(0, str(ROOT))
        from src.config import DB_PATH  # type: ignore

        db_path = Path(DB_PATH)
    except Exception:
        db_path = ROOT / "data" / "modular_info.db"

    if not db_path or not db_path.exists():
        return []

    query = """
        SELECT collector_name, source_type, started_at, finished_at, status,
               inserted_count, updated_count, skipped_count, error_message
        FROM collect_logs
        ORDER BY id DESC
        LIMIT ?
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(query, (limit,)).fetchall()]


def latest_log(
    logs: list[dict[str, Any]],
    *,
    collector_name: str | None = None,
    source_type: str | None = None,
    name_contains: str | None = None,
) -> dict[str, Any] | None:
    for row in logs:
        name = clean(row.get("collector_name"))
        if collector_name and name != collector_name:
            continue
        if name_contains and name_contains not in name:
            continue
        if source_type and clean(row.get("source_type")) != source_type:
            continue
        return row
    return None


def consecutive_failures(
    logs: list[dict[str, Any]],
    *,
    collector_name: str | None = None,
    source_type: str | None = None,
    name_contains: str | None = None,
) -> int:
    count = 0
    for row in logs:
        name = clean(row.get("collector_name"))
        if collector_name and name != collector_name:
            continue
        if name_contains and name_contains not in name:
            continue
        if source_type and clean(row.get("source_type")) != source_type:
            continue
        if clean(row.get("status")) == "success":
            break
        count += 1
    return count


def source_status_from_meta(payload: dict[str, Any], key: str) -> tuple[str, str]:
    status = clean(payload.get(f"{key}_status"))
    message = clean(payload.get(f"{key}_message"))
    return status or "unknown", message


@dataclass
class SourceSpec:
    source_key: str
    source_name: str
    collector_file: str
    workflow_step: str
    output_file: str
    failure_policy: str
    cumulative_export_policy: str
    active_or_disabled: str
    source_type: str
    predicate: Callable[[dict[str, Any]], bool]
    meta_status_key: str | None = None
    collector_name: str | None = None
    name_contains: str | None = None
    alternative_source: str = ""
    expected_effect: str = ""


def source_specs() -> list[SourceSpec]:
    return [
        SourceSpec(
            "g2b_bid",
            "나라장터 입찰공고",
            "scripts/collect_all.py; scripts/collect_g2b_modular_scope.py",
            "Collect bids and news",
            "data/modular_info.db -> frontend/public/data/business.json",
            "warning_only_continue",
            "cumulative_verified_merge",
            "active",
            "bid",
            lambda item: clean(item.get("source_type")) == "bid" and clean(item.get("source")) in {"나라장터", "G2B", "조달청"},
            collector_name="나라장터",
            alternative_source="known important bid fixture may backfill selected G2B notices",
            expected_effect="standard bid failures can delay newly available bid visibility",
        ),
        SourceSpec(
            "known_important_bid",
            "known important G2B bid",
            "scripts/collect_known_g2b_bids.py",
            "Collect known important G2B bids",
            "data/modular_info.db -> frontend/public/data/business.json",
            "warning_only_continue",
            "cumulative_verified_merge",
            "active",
            "bid",
            lambda item: bool(item.get("is_known_important")),
            name_contains="나라장터",
            alternative_source="general G2B modular bid collection",
            expected_effect="may delay targeted important notices if not captured by general G2B",
        ),
        SourceSpec(
            "g2b_procurement_plan",
            "나라장터 발주계획",
            "scripts/collect_g2b_procurement_plans.py",
            "Collect G2B procurement plans",
            "data/modular_info.db -> frontend/public/data/business.json",
            "warning_only_continue",
            "cumulative_verified_merge",
            "active",
            "procurement_plan",
            lambda item: clean(item.get("source_type")) == "procurement_plan" and clean(item.get("source")) in {"나라장터", "G2B", "조달청"},
            meta_status_key="g2b_order_plan",
            collector_name="나라장터",
            alternative_source="future bid notices after plan conversion",
            expected_effect="plan failures can delay early pipeline visibility while later bid notices may still appear",
        ),
        SourceSpec(
            "lh_public_housing_contest",
            "LH 민간참여 공공주택 공모",
            "scripts/collect_lh_public_housing_contests.py",
            "Collect LH public housing contests",
            "data/modular_info.db -> frontend/public/data/business.json",
            "warning_only_continue",
            "cumulative_verified_merge",
            "active",
            "public_agency_contest",
            lambda item: clean(item.get("source_type")) == "public_agency_contest" and clean(item.get("source")) == "LH",
            meta_status_key="lh_contest",
            collector_name="LHPublicHousingContestCollector",
            expected_effect="LH failures can delay new public housing contest visibility",
        ),
        SourceSpec(
            "gh_public_housing_contest",
            "GH 민간참여 공공주택 공모",
            "scripts/collect_gh_public_housing_contests.py",
            "Collect GH public housing contests",
            "data/modular_info.db -> frontend/public/data/business.json",
            "warning_only_continue",
            "cumulative_verified_merge",
            "active",
            "public_agency_contest",
            lambda item: clean(item.get("source_type")) == "public_agency_contest" and clean(item.get("source")) == "GH",
            meta_status_key="gh_contest",
            collector_name="GHPublicHousingContestCollector",
            expected_effect="GH failures can delay new public housing contest visibility",
        ),
        SourceSpec(
            "ih_public_housing_contest",
            "iH 민간참여 공공주택 공모",
            "scripts/collect_ih_public_housing_contests.py",
            "Collect iH public housing contests",
            "data/modular_info.db -> frontend/public/data/business.json",
            "warning_only_continue",
            "cumulative_verified_merge",
            "active",
            "public_agency_contest",
            lambda item: clean(item.get("source_type")) == "public_agency_contest" and clean(item.get("source")) == "iH",
            meta_status_key="ih_contest",
            collector_name="IHPublicHousingContestCollector",
            expected_effect="iH failures can delay new public housing contest visibility",
        ),
        SourceSpec(
            "sh_public_housing_contest",
            "SH 민간참여 공공주택 공모",
            "scripts/collect_sh_public_housing_contests.py",
            "not currently enabled in workflow",
            "data/modular_info.db -> frontend/public/data/business.json",
            "not_collected_reported",
            "cumulative_verified_merge",
            "active_but_not_collected",
            "public_agency_contest",
            lambda item: clean(item.get("source_type")) == "public_agency_contest" and clean(item.get("source")) == "SH",
            meta_status_key="sh_contest",
            collector_name="SHPublicHousingContestCollector",
            expected_effect="SH absence is visible as not_collected, not success_no_match",
        ),
        SourceSpec(
            "d2b_legacy",
            "D2B legacy API",
            "scripts/collect_all.py --skip-d2b; scripts/collect_d2b_procurement_plans.py",
            "Record D2B legacy API status",
            "not published from legacy API while disabled",
            "disabled_known",
            "not_applicable",
            "disabled",
            "bid",
            lambda item: clean(item.get("source")) == "D2B",
            meta_status_key="d2b",
            collector_name="D2B",
            expected_effect="known disabled source; do not treat as active collector failure",
        ),
    ]


def log_counts_for_spec(logs: list[dict[str, Any]], spec: SourceSpec) -> tuple[dict[str, Any] | None, int]:
    log = latest_log(
        logs,
        collector_name=spec.collector_name,
        source_type=None if spec.source_key == "known_important_bid" else spec.source_type,
        name_contains=spec.name_contains if not spec.collector_name else None,
    )
    failures = consecutive_failures(
        logs,
        collector_name=spec.collector_name,
        source_type=None if spec.source_key == "known_important_bid" else spec.source_type,
        name_contains=spec.name_contains if not spec.collector_name else None,
    )
    return log, failures


def classify_source_impact(
    *,
    spec: SourceSpec,
    status: str,
    exported_count: int,
    staleness: str,
    consecutive_failure_count: int,
    fixture_missing_count: int = 0,
) -> str:
    if status in DISABLED_STATES or spec.active_or_disabled == "disabled":
        return "DISABLED_KNOWN"
    if fixture_missing_count:
        return "CRITICAL_GAP"
    if status in SOURCE_HEALTHY_STATES and staleness not in {"stale_source", "unknown"}:
        return "HEALTHY"
    if status in SOURCE_HEALTHY_STATES and exported_count > 0:
        if spec.source_key == "g2b_procurement_plan" and staleness == "stale_source":
            return "STALE_SOURCE"
        return "HEALTHY"
    if status == "not_collected" and exported_count == 0:
        return "UNKNOWN" if spec.source_key != "d2b_legacy" else "DISABLED_KNOWN"
    if status in SOURCE_FAILURE_STATES and exported_count > 0:
        return "DELAYED_VISIBILITY" if consecutive_failure_count <= 2 else "STALE_SOURCE"
    if status in SOURCE_FAILURE_STATES:
        return "CRITICAL_GAP"
    if exported_count > 0:
        return "UNKNOWN" if staleness == "unknown" else "NO_IMPACT_FAILURE"
    return "UNKNOWN"


def recommended_action_for(impact: str, spec: SourceSpec) -> tuple[str, str]:
    if impact == "CRITICAL_GAP":
        return "P0", f"Fix {spec.collector_file}; verify source API and parser before next publish."
    if impact in {"STALE_SOURCE", "PARTIAL_COVERAGE"}:
        return "P1", f"Targeted hotfix for {spec.source_name}; inspect endpoint/schema/pagination/date range."
    if impact in {"DELAYED_VISIBILITY", "UNKNOWN"}:
        return "P2", f"Add diagnostics or targeted fixture check for {spec.source_name} before collector changes."
    if impact == "DISABLED_KNOWN":
        return "P3", "Track as known disabled source; plan separate D2B GW migration if needed."
    return "P3", "No immediate fix; continue monitoring."


def build_source_matrix(payload: dict[str, Any], logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = business_items(payload)
    generated_at = parse_datetime(payload.get("generated_at") or payload.get("last_updated_at"))
    previous_public_count = int(payload.get("previous_business_count") or 0)
    current_public_count = len(items)
    rows: list[dict[str, Any]] = []
    for spec in source_specs():
        exported = [item for item in items if spec.predicate(item)]
        exported_count = len(exported)
        latest_public = latest_posted_at(items, spec.predicate)
        staleness_hours = hours_between(generated_at, latest_public)
        stale_bucket = staleness_bucket(staleness_hours)
        meta_status = ""
        meta_message = ""
        if spec.meta_status_key:
            meta_status, meta_message = source_status_from_meta(payload, spec.meta_status_key)
        log, failures = log_counts_for_spec(logs, spec)
        log_status = clean((log or {}).get("status"))
        status = meta_status or log_status or ("disabled_stopped" if spec.active_or_disabled == "disabled" else "unknown")
        inserted = int((log or {}).get("inserted_count") or 0)
        updated = int((log or {}).get("updated_count") or 0)
        skipped = int((log or {}).get("skipped_count") or 0)
        fetched = inserted + updated + skipped
        attempted = bool(log) or status not in {"unknown", "not_collected"} or spec.source_key == "d2b_legacy"
        succeeded = status in SOURCE_HEALTHY_STATES or log_status == "success"
        disabled = status in DISABLED_STATES or spec.active_or_disabled == "disabled"
        fixture_missing_count = 0
        if spec.source_key == "known_important_bid":
            fixture_missing_count = 0 if exported_count else 1
        impact = classify_source_impact(
            spec=spec,
            status=status,
            exported_count=exported_count,
            staleness=stale_bucket,
            consecutive_failure_count=failures,
            fixture_missing_count=fixture_missing_count,
        )
        priority, action = recommended_action_for(impact, spec)
        failure_reason = meta_message or clean((log or {}).get("error_message"))
        rows.append(
            {
                "source_key": spec.source_key,
                "source_name": spec.source_name,
                "collector_file": spec.collector_file,
                "workflow_step": spec.workflow_step,
                "output_file": spec.output_file,
                "failure_policy": spec.failure_policy,
                "cumulative_export_policy": spec.cumulative_export_policy,
                "active_or_disabled": spec.active_or_disabled,
                "current_warning": failure_reason if status not in SOURCE_HEALTHY_STATES else "",
                "expected_effect": spec.expected_effect,
                "status": impact,
                "collector_status": status,
                "attempted": attempted,
                "succeeded": succeeded,
                "failed": status in SOURCE_FAILURE_STATES,
                "disabled": disabled,
                "records_fetched": fetched if log else exported_count,
                "valid_records": exported_count,
                "invalid_records": 0,
                "new_unique_records": inserted,
                "duplicate_records": skipped,
                "carried_forward_records": max(0, exported_count - inserted - updated),
                "previous_public_count": previous_public_count,
                "current_public_count": current_public_count,
                "count_delta": current_public_count - previous_public_count if previous_public_count else 0,
                "latest_source_published_at": latest_public.isoformat() if latest_public else "",
                "latest_public_published_at": latest_public.isoformat() if latest_public else "",
                "staleness_hours": round(staleness_hours, 2) if staleness_hours is not None else "",
                "staleness_bucket": stale_bucket,
                "consecutive_failure_count": failures,
                "last_success_at": clean((log or {}).get("finished_at") or (log or {}).get("started_at"))
                if succeeded
                else "",
                "last_failure_at": clean((log or {}).get("finished_at") or (log or {}).get("started_at"))
                if status in SOURCE_FAILURE_STATES
                else "",
                "failure_reason": failure_reason,
                "public_data_preserved": current_public_count >= previous_public_count if previous_public_count else True,
                "newly_available_records_may_be_missing": impact in {"DELAYED_VISIBILITY", "PARTIAL_COVERAGE", "STALE_SOURCE", "CRITICAL_GAP", "UNKNOWN"},
                "known_fixture_missing_count": fixture_missing_count,
                "alternative_source": spec.alternative_source,
                "impact_level": priority,
                "recommended_action": action,
            }
        )
    return rows


def find_fixture(items: list[dict[str, Any]], fixture: dict[str, str]) -> dict[str, Any] | None:
    needle = fixture["title_contains"]
    for item in items:
        if needle in clean(item.get("title")):
            return item
    return None


def evaluate_fixtures(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = business_items(payload)
    rows: list[dict[str, Any]] = []
    for fixture in FIXTURES:
        item = find_fixture(items, fixture)
        actual_source = clean((item or {}).get("source"))
        actual_type = clean((item or {}).get("source_type"))
        rows.append(
            {
                "fixture_key": fixture["fixture_key"],
                "expected_source": fixture["expected_source"],
                "expected_type": fixture["expected_type"],
                "actual_source": actual_source,
                "actual_type": actual_type,
                "public_presence": bool(item),
                "current_status": clean((item or {}).get("opportunity_status") or (item or {}).get("notice_status")),
                "original_url": clean((item or {}).get("external_original_url") or (item or {}).get("original_url")),
                "duplicate_path": "general_g2b" if item and bool(item.get("is_known_important")) else "",
                "pass": bool(item) and (not fixture.get("expected_type") or actual_type == fixture["expected_type"]),
                "id": clean((item or {}).get("id")),
                "title": clean((item or {}).get("title")) or fixture["title_contains"],
            }
        )
    return rows


def recent_business_counts(payload: dict[str, Any]) -> dict[str, int]:
    items = business_items(payload)
    generated_at = parse_datetime(payload.get("generated_at") or payload.get("last_updated_at")) or datetime.now(timezone.utc)
    recent7 = 0
    for item in items:
        posted = parse_datetime(item.get("posted_at"))
        if posted and 0 <= (generated_at - posted).total_seconds() <= 7 * 86400:
            recent7 += 1
    return {
        "total": len(items),
        "active": sum(1 for item in items if item.get("opportunity_status") == "active"),
        "closed": sum(1 for item in items if item.get("opportunity_status") == "closed"),
        "unknown": sum(1 for item in items if item.get("opportunity_status") == "unknown"),
        "recent7": recent7,
        "bid": sum(1 for item in items if item.get("source_type") == "bid"),
        "procurement_plan": sum(1 for item in items if item.get("source_type") == "procurement_plan"),
        "public_agency_contest": sum(1 for item in items if item.get("source_type") == "public_agency_contest"),
        "known_important": sum(1 for item in items if item.get("is_known_important")),
    }


def git_business_history(limit: int = 14) -> list[dict[str, Any]]:
    try:
        proc = subprocess.run(
            ["git", "log", f"-n{limit}", "--format=%H%x09%cI", "--", "frontend/public/data/business.json"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
    except Exception:
        return []
    history: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        sha, committed_at = line.split("\t", 1)
        row = {"commit": sha, "committed_at": committed_at, "business_count": "", "generated_at": "", "warnings": ""}
        try:
            show = subprocess.run(
                ["git", "show", f"{sha}:frontend/public/data/business.json"],
                cwd=ROOT,
                check=True,
                text=True,
                capture_output=True,
                encoding="utf-8",
            )
            payload = json.loads(show.stdout)
            row["business_count"] = len(business_items(payload))
            row["generated_at"] = clean(payload.get("generated_at"))
            row["warnings"] = "; ".join(clean(w) for w in payload.get("warnings", []) if clean(w))
        except Exception as exc:
            row["error"] = str(exc)
        history.append(row)
    return history


def workflow_warning_history(payload: dict[str, Any], history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in history:
        warnings = clean(item.get("warnings"))
        rows.append(
            {
                "run_id": "",
                "trigger_type": "git_public_data_history",
                "started_at": item.get("committed_at", ""),
                "head_sha": item.get("commit", ""),
                "overall_status": "warning" if warnings else "success_or_unknown",
                "collector_status": "unknown",
                "known_important_bid_status": "unknown",
                "procurement_plan_status": payload.get("procurement_plan_collection_status", "unknown")
                if item is history[0]
                else "unknown",
                "standard_bid_status": "unknown",
                "export_status": "published" if item.get("business_count") else "unknown",
                "business_count": item.get("business_count", ""),
                "new_business_count": "",
                "carried_forward_count": "",
                "warning_list": warnings,
                "artifact_existence": "unknown",
            }
        )
    if not rows:
        rows.append(
            {
                "run_id": "",
                "trigger_type": "local_current_json",
                "started_at": payload.get("generated_at", ""),
                "head_sha": "",
                "overall_status": payload.get("workflow_last_run_status", "unknown"),
                "collector_status": "unknown",
                "known_important_bid_status": "unknown",
                "procurement_plan_status": payload.get("procurement_plan_collection_status", "unknown"),
                "standard_bid_status": "unknown",
                "export_status": "published",
                "business_count": len(business_items(payload)),
                "new_business_count": payload.get("current_business_count", ""),
                "carried_forward_count": "",
                "warning_list": "; ".join(payload.get("warnings", [])),
                "artifact_existence": "unknown",
            }
        )
    return rows


def impact_decision(source_rows: list[dict[str, Any]], *, live_logs_status: str) -> str:
    statuses = {row["status"] for row in source_rows}
    if "CRITICAL_GAP" in statuses:
        return "HOLD_FOR_CRITICAL_FIX"
    if statuses & {"STALE_SOURCE", "PARTIAL_COVERAGE"}:
        return "HOLD_FOR_TARGETED_FIX"
    if statuses & {"DELAYED_VISIBILITY"}:
        return "PASS_WITH_DELAY_RISK"
    if live_logs_status != "available":
        return "PENDING_LIVE_LOGS"
    return "PASS_NO_IMPACT"


def missing_candidates(fixture_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for fixture in fixture_rows:
        if fixture["public_presence"]:
            continue
        rows.append(
            {
                "candidate_key": fixture["fixture_key"],
                "title": fixture["title"],
                "notice_number": "",
                "expected_source": fixture["expected_source"],
                "expected_published_at": "",
                "found_in_public": False,
                "found_in_alternative_source": False,
                "suspected_missing": True,
                "evidence": "fixture title was not found in current public business.json",
                "confidence": "medium",
            }
        )
    return rows


def recommendation_rows(source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    rows = []
    for row in source_rows:
        rows.append(
            {
                "priority": row["impact_level"],
                "source_key": row["source_key"],
                "source_name": row["source_name"],
                "impact_status": row["status"],
                "target": row["collector_file"],
                "cause": row["failure_reason"] or row["expected_effect"],
                "minimal_files": row["collector_file"],
                "regression_risk": "medium" if row["impact_level"] in {"P0", "P1"} else "low",
                "verification": "rerun collector, export public JSON, and compare source audit artifacts",
                "recommended_hotfix": hotfix_name(row),
                "recommended_action": row["recommended_action"],
            }
        )
    return sorted(rows, key=lambda r: (priority_order.get(r["priority"], 99), r["source_key"]))


def hotfix_name(row: dict[str, Any]) -> str:
    if row["source_key"] == "g2b_procurement_plan":
        return "10.13-B2: 나라장터 발주계획 수집 노후화 Hotfix"
    if row["source_key"] == "known_important_bid":
        return "10.13-B3: known important bid 수집 영향 Hotfix"
    if row["source_key"] == "g2b_bid":
        return "10.13-B4: 나라장터 입찰공고 수집 안정화 Hotfix"
    if row["source_key"].endswith("_public_housing_contest"):
        return "10.13-B5: 공공주택 공모 수집원별 Hotfix"
    return "운영 추적"


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        fieldnames = sorted({key for row in rows for key in row.keys()})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def markdown_report(audit: dict[str, Any]) -> str:
    lines = [
        "# Business Collection Impact Audit",
        "",
        f"- Checked at: {audit['checked_at']}",
        f"- Public generated_at: {audit['public_generated_at']}",
        f"- Business count: {audit['business_counts']['total']}",
        f"- Final impact: **{audit['final_impact']}**",
        f"- Live logs status: {audit['live_logs_status']}",
        "",
        "## Source Matrix",
        "",
        "| Source | Collector status | Impact | Public records | Staleness | Consecutive failures | Priority |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in audit["source_matrix"]:
        lines.append(
            "| {source_name} | {collector_status} | {status} | {valid_records} | {staleness_bucket} | {consecutive_failure_count} | {impact_level} |".format(
                **row
            )
        )
    lines.extend(
        [
            "",
            "## Fixture Results",
            "",
            "| Fixture | Present | Source | Type | Status |",
            "|---|---:|---|---|---|",
        ]
    )
    for row in audit["known_fixture_results"]:
        lines.append(
            f"| {row['fixture_key']} | {row['public_presence']} | {row['actual_source']} | {row['actual_type']} | {row['current_status']} |"
        )
    lines.extend(["", "## Recommended Fix Priority", ""])
    for row in audit["recommended_fix_priority"]:
        lines.append(
            f"- **{row['priority']} {row['source_key']}**: {row['recommended_action']} "
            f"(next: {row['recommended_hotfix']})"
        )
    return "\n".join(lines) + "\n"


def build_audit(business_path: Path) -> dict[str, Any]:
    payload = load_json(business_path)
    logs = read_collect_logs()
    source_matrix = build_source_matrix(payload, logs)
    fixtures = evaluate_fixtures(payload)
    history = git_business_history()
    warning_rows = workflow_warning_history(payload, history)
    live_logs_status = "available" if logs else "local_db_logs_unavailable"
    counts = recent_business_counts(payload)
    final = impact_decision(source_matrix, live_logs_status=live_logs_status)
    audit = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "public_generated_at": clean(payload.get("generated_at")),
        "business_counts": counts,
        "source_matrix": source_matrix,
        "known_fixture_results": fixtures,
        "missing_business_candidates": missing_candidates(fixtures),
        "business_count_history": history,
        "workflow_warning_history": warning_rows,
        "recommended_fix_priority": recommendation_rows(source_matrix),
        "live_logs_status": live_logs_status,
        "final_impact": final,
        "business_news_failure_split": split_business_news_failures(payload, logs),
        "known_important_bid_impact": known_important_impact(source_matrix, fixtures),
        "g2b_procurement_plan_impact": procurement_plan_impact(source_matrix),
        "public_data_preserved": bool(payload.get("public_data_guard_status") == "passed" or counts["total"] > 0),
    }
    return audit


def split_business_news_failures(payload: dict[str, Any], logs: list[dict[str, Any]]) -> dict[str, Any]:
    warnings = [clean(w) for w in payload.get("warnings", []) if clean(w)]
    business_types = {"bid", "procurement_plan", "public_agency_contest"}
    latest_business = next((row for row in logs if clean(row.get("source_type")) in business_types), None)
    latest_news = next((row for row in logs if clean(row.get("source_type")) == "news"), None)
    business_failed = bool(latest_business and clean(latest_business.get("status")) != "success")
    news_failed = bool(latest_news and clean(latest_news.get("status")) != "success")
    if business_failed and news_failed:
        category = "both_failed"
    elif business_failed:
        category = "business_collector_failure"
    elif news_failed:
        category = "news_collector_failure"
    elif any("D2B" in warning for warning in warnings):
        category = "business_disabled_known_only"
    else:
        category = "unknown_subsystem" if warnings else "no_failure_warning"
    return {
        "category": category,
        "business_failure_count": int(business_failed),
        "news_failure_count": int(news_failed),
        "latest_business_status": clean((latest_business or {}).get("status")),
        "latest_business_source_type": clean((latest_business or {}).get("source_type")),
        "latest_news_status": clean((latest_news or {}).get("status")),
        "warnings": warnings,
    }


def known_important_impact(source_matrix: list[dict[str, Any]], fixtures: list[dict[str, Any]]) -> str:
    row = next((item for item in source_matrix if item["source_key"] == "known_important_bid"), None)
    known_fixture = next((item for item in fixtures if item["fixture_key"] == "seongui_known_important_bid"), None)
    if known_fixture and known_fixture["public_presence"]:
        return "NO_DATA_IMPACT"
    if row and row["valid_records"] > 0:
        return "PRIORITY_METADATA_GAP"
    if row and row["status"] in {"DELAYED_VISIBILITY", "STALE_SOURCE", "UNKNOWN"}:
        return "NEW_RECORD_VISIBILITY_DELAY"
    return "RECORD_OMISSION"


def procurement_plan_impact(source_matrix: list[dict[str, Any]]) -> str:
    row = next((item for item in source_matrix if item["source_key"] == "g2b_procurement_plan"), None)
    if not row:
        return "UNKNOWN"
    if row["status"] == "HEALTHY":
        return "HEALTHY"
    if row["status"] == "STALE_SOURCE":
        return "STALE_SOURCE"
    if row["valid_records"] and row["collector_status"] in SOURCE_HEALTHY_STATES:
        return "NO_IMPACT_FAILURE"
    if row["valid_records"]:
        return "DELAYED_VISIBILITY"
    return "CRITICAL_GAP"


def write_outputs(audit: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "business_collection_impact_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md = markdown_report(audit)
    (output_dir / "business_collection_impact_audit.md").write_text(md, encoding="utf-8")
    write_csv(output_dir / "collector_status_matrix.csv", audit["source_matrix"])
    freshness_fields = [
        "source_key",
        "source_name",
        "latest_public_published_at",
        "staleness_hours",
        "staleness_bucket",
        "status",
        "impact_level",
    ]
    write_csv(output_dir / "source_freshness.csv", audit["source_matrix"], freshness_fields)
    write_csv(output_dir / "business_count_history.csv", audit["business_count_history"])
    write_csv(output_dir / "missing_business_candidates.csv", audit["missing_business_candidates"])
    write_csv(output_dir / "known_fixture_results.csv", audit["known_fixture_results"])
    write_csv(output_dir / "workflow_warning_history.csv", audit["workflow_warning_history"])
    write_csv(output_dir / "recommended_fix_priority.csv", audit["recommended_fix_priority"])
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write("\n")
            handle.write(md)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit ModularHub business collection impact.")
    parser.add_argument("--business", type=Path, default=PUBLIC_BUSINESS)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    audit = build_audit(args.business)
    write_outputs(audit, args.output_dir)
    print(f"Business collection impact: {audit['final_impact']}")
    print(f"Artifacts: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
