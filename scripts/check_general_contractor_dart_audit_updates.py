#!/usr/bin/env python3
"""Compare a fresh OpenDART audit candidate with the committed public source.

This script is read-only with respect to repository data. It emits a sanitized
review artifact and can return exit code 2 when human review is required.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

YEARS = ("2023", "2024", "2025")
FINANCIAL_SECTIONS = (
    "income_statement",
    "balance_sheet",
    "cash_flow",
    "revenue_breakdown",
    "working_capital",
    "borrowings",
    "investment_signals",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def audit_by_year(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in payload.get("audit_opinions") or []:
        for year in row.get("covered_years") or []:
            result[str(year)] = {
                "opinion": row.get("opinion"),
                "auditor": row.get("auditor"),
                "source_ref": row.get("source_ref"),
            }
    return result


def metric_snapshot(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for year in YEARS:
        financial_year = (payload.get("financial_years") or {}).get(year) or {}
        for section in FINANCIAL_SECTIONS:
            for field, row in (financial_year.get(section) or {}).items():
                if not isinstance(row, dict) or "disclosure_status" not in row:
                    continue
                result[f"{year}.{section}.{field}"] = {
                    "reported": row.get("reported"),
                    "disclosure_status": row.get("disclosure_status"),
                }
    return result


def source_priority_snapshot(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for year in YEARS:
        row = (payload.get("source_priority") or {}).get(year) or {}
        result[year] = {
            "primary_source_ref": row.get("primary_source_ref"),
            "cross_check_source_refs": sorted(row.get("cross_check_source_refs") or []),
        }
    return result


def add_change(changes: list[dict[str, Any]], kind: str, path: str, before: Any, after: Any) -> None:
    changes.append({"kind": kind, "path": path, "before": before, "after": after})


def compare_payloads(public: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    public_id = public.get("company_id")
    candidate_id = candidate.get("company_id")
    if not public_id or public_id != candidate_id:
        raise ValueError(f"company_id mismatch: public={public_id!r}, candidate={candidate_id!r}")

    changes: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []

    for key in ("currency", "unit"):
        if public.get(key) != candidate.get(key):
            add_change(changes, "contract_changed", key, public.get(key), candidate.get(key))
    public_scope = (public.get("entity_attribution") or {}).get("financial_scope")
    candidate_scope = (candidate.get("entity_attribution") or {}).get("financial_scope")
    if public_scope != candidate_scope:
        add_change(changes, "contract_changed", "entity_attribution.financial_scope", public_scope, candidate_scope)

    old_priority = source_priority_snapshot(public)
    new_priority = source_priority_snapshot(candidate)
    for year in YEARS:
        if old_priority[year]["primary_source_ref"] != new_priority[year]["primary_source_ref"]:
            add_change(
                changes,
                "primary_source_changed",
                f"source_priority.{year}.primary_source_ref",
                old_priority[year]["primary_source_ref"],
                new_priority[year]["primary_source_ref"],
            )
        if old_priority[year]["cross_check_source_refs"] != new_priority[year]["cross_check_source_refs"]:
            add_change(
                changes,
                "cross_check_sources_changed",
                f"source_priority.{year}.cross_check_source_refs",
                old_priority[year]["cross_check_source_refs"],
                new_priority[year]["cross_check_source_refs"],
            )

    old_audit = audit_by_year(public)
    new_audit = audit_by_year(candidate)
    for year in YEARS:
        if old_audit.get(year) != new_audit.get(year):
            add_change(changes, "audit_metadata_changed", f"audit_opinions.{year}", old_audit.get(year), new_audit.get(year))

    old_metrics = metric_snapshot(public)
    new_metrics = metric_snapshot(candidate)
    for path in sorted(set(old_metrics) | set(new_metrics)):
        before = old_metrics.get(path)
        after = new_metrics.get(path)
        if before == after:
            continue
        if before is None:
            add_change(changes, "metric_added", path, None, after)
            continue
        if after is None:
            change = {"kind": "metric_removed", "path": path, "before": before, "after": None}
            changes.append(change)
            regressions.append(change)
            continue
        if before.get("disclosure_status") == "reported" and after.get("disclosure_status") != "reported":
            change = {"kind": "metric_coverage_regression", "path": path, "before": before, "after": after}
            changes.append(change)
            regressions.append(change)
            continue
        if before.get("disclosure_status") != "reported" and after.get("disclosure_status") == "reported":
            add_change(changes, "metric_newly_available", path, before, after)
            continue
        if before.get("disclosure_status") != after.get("disclosure_status"):
            add_change(changes, "metric_disclosure_changed", path, before, after)
            continue
        if before.get("reported") != after.get("reported"):
            add_change(changes, "metric_value_changed", path, before, after)

    kinds: dict[str, int] = {}
    for change in changes:
        kinds[change["kind"]] = kinds.get(change["kind"], 0) + 1

    return {
        "schema_version": "general_contractor_dart_audit_update_check_v1",
        "company_id": public_id,
        "review_required": bool(changes),
        "regression_detected": bool(regressions),
        "change_count": len(changes),
        "change_counts_by_kind": dict(sorted(kinds.items())),
        "changes": changes,
        "regressions": regressions,
    }


def markdown_report(result: dict[str, Any]) -> str:
    lines = [
        f"# OpenDART audit-financial update check: {result['company_id']}",
        "",
        f"- review_required: `{str(result['review_required']).lower()}`",
        f"- regression_detected: `{str(result['regression_detected']).lower()}`",
        f"- change_count: `{result['change_count']}`",
    ]
    if not result["changes"]:
        lines.extend(["", "No source, audit metadata, disclosure-status, or financial-value drift detected."])
        return "\n".join(lines) + "\n"
    lines.extend(["", "## Changes", ""])
    for change in result["changes"]:
        lines.append(f"- `{change['kind']}` · `{change['path']}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--fail-on-change", action="store_true")
    args = parser.parse_args()

    result = compare_payloads(load_json(args.public), load_json(args.candidate))
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_md.write_text(markdown_report(result), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.fail_on_change and result["review_required"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
