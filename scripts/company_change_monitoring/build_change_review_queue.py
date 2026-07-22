#!/usr/bin/env python3
"""Build an internal company-change review queue without publishing company data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.company_change_monitoring import (  # noqa: E402
    audit_change_run,
    build_change_monitor_run,
    write_audit_outputs,
    write_run_outputs,
)


def csv_list(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--companies", default="", help="Comma-separated company IDs. Defaults to all 11 companies.")
    parser.add_argument("--sources", default="public_news", help="Comma-separated source IDs.")
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--mode", choices=["daily_signals", "weekly_research", "full_audit"], default="daily_signals")
    parser.add_argument("--publish", action="store_true", help="Forbidden guard; public data publication is not allowed here.")
    parser.add_argument("--create-proposal", action="store_true", help="Create patch proposal metadata only when acknowledged.")
    parser.add_argument("--acknowledge-proposal", action="store_true")
    parser.add_argument("--live", action="store_true", help="Accepted for workflow parity; external adapters remain source-isolated.")
    parser.add_argument("--acknowledge-live", action="store_true")
    parser.add_argument("--skip-internal-queue", action="store_true", help="Write reports/artifacts but skip data/company_change_monitoring output.")
    args = parser.parse_args()

    if args.live and not args.acknowledge_live:
        print("ERROR: --live requires --acknowledge-live before any external source can run", file=sys.stderr)
        return 2

    try:
        run = build_change_monitor_run(
            companies=csv_list(args.companies),
            sources=csv_list(args.sources),
            lookback_days=args.lookback_days,
            mode=args.mode,
            publish=args.publish,
            create_proposal=args.create_proposal,
            acknowledge_proposal=args.acknowledge_proposal,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    paths = write_run_outputs(run, write_internal_queue=not args.skip_internal_queue)
    audit = audit_change_run(run)
    paths.update(write_audit_outputs(audit))
    print(
        json.dumps(
            {
                "runId": run["runId"],
                "candidateCount": run["candidateCount"],
                "pending": run["pending"],
                "duplicate": run["duplicate"],
                "conflict": run["conflict"],
                "insufficientEvidence": run["insufficientEvidence"],
                "highPriority": run["highPriority"],
                "auditValid": audit["valid"],
                "paths": paths,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if audit["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
