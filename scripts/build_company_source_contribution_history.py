from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.company_source_contribution_history import (
    build_history_payload,
    concentration_diagnostics,
    current_run_snapshot,
    load_previous_runs_from_github,
    load_previous_runs_from_json,
    read_json,
    utc_now,
    write_outputs,
)
from src.company_source_coverage import load_source_coverage_policy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build sanitized source contribution history diagnostics.")
    parser.add_argument("--raw-summary", default="artifacts/company-change-monitor/raw-summary.json")
    parser.add_argument("--review-queue", default="data/company_change_monitoring/review_queue.json")
    parser.add_argument("--source-coverage", default="artifacts/company-source-coverage/source-coverage-report.json")
    parser.add_argument("--audit", default="artifacts/company-change-monitor/audit-summary.json")
    parser.add_argument("--history-json")
    parser.add_argument("--run-id")
    parser.add_argument("--run-number")
    parser.add_argument("--run-url")
    parser.add_argument("--run-sha")
    parser.add_argument("--workflow-event")
    parser.add_argument("--run-kind")
    parser.add_argument("--mode")
    parser.add_argument("--created-at")
    parser.add_argument("--completed-at")
    parser.add_argument("--final-gate-passed", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    generated_at = utc_now()
    raw_summary = read_json(ROOT / args.raw_summary)
    queue = read_json(ROOT / args.review_queue)
    source_coverage = read_json(ROOT / args.source_coverage)
    audit = read_json(ROOT / args.audit)
    run_metadata = {
        "runId": args.run_id,
        "runNumber": args.run_number,
        "runUrl": args.run_url,
        "headSha": args.run_sha,
        "workflowEvent": args.workflow_event,
        "runKind": args.run_kind,
        "mode": args.mode or args.run_kind,
        "createdAt": args.created_at,
        "completedAt": args.completed_at or generated_at,
        "finalGatePassed": args.final_gate_passed,
    }
    current_run = current_run_snapshot(
        queue=queue,
        raw_summary=raw_summary,
        source_coverage=source_coverage,
        audit=audit,
        run_metadata=run_metadata,
        generated_at=generated_at,
    )
    history_error = None
    history_source = "github_actions"
    if args.history_json:
        previous_runs = load_previous_runs_from_json(ROOT / args.history_json)
        history_source = "fixture"
    else:
        previous_runs, history_error = load_previous_runs_from_github(
            token=os.environ.get("GITHUB_TOKEN"),
            repository=os.environ.get("GITHUB_REPOSITORY"),
            current_run_id=args.run_id,
        )
    history = build_history_payload(
        current_run=current_run,
        previous_runs=previous_runs,
        history_source=history_source,
        history_error_category=history_error,
        generated_at=generated_at,
    )
    policy = load_source_coverage_policy(ROOT)
    diagnostics = concentration_diagnostics(
        history,
        warning_threshold=float(policy.get("sourceConcentrationWarningThreshold", 0.8)),
        failure_codes=source_coverage.get("failureCodes", []),
        generated_at=generated_at,
    )
    paths = write_outputs(history, diagnostics, root=ROOT)
    print(f"source_contribution_history_state={history.get('historyState')}")
    print(f"source_concentration_state={diagnostics.get('state')}")
    print(f"source_contribution_history_path={paths['sourceContributionHistory']}")
    print(f"source_concentration_diagnostics_path={paths['sourceConcentrationDiagnostics']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
