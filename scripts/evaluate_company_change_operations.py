#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.company_change_operations import evaluate_operations, load_operations_policy, markdown_evaluation, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Company Change Monitor operational health from existing artifacts.")
    parser.add_argument("--run-kind", default="manual", choices=["daily", "weekly", "manual", "scheduled_unknown"])
    parser.add_argument("--run-url", default="")
    parser.add_argument("--run-number", default="")
    parser.add_argument("--run-sha", default="")
    parser.add_argument("--workflow-event", default="")
    parser.add_argument("--policy", type=Path, default=Path("config/company_change_monitoring/operations_policy.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/company-change-monitor/operations-evaluation.json"))
    parser.add_argument("--report", type=Path, default=Path("reports/company_change_monitoring/latest_operations_evaluation.md"))
    args = parser.parse_args()

    policy = json.loads(args.policy.read_text(encoding="utf-8")) if args.policy.exists() else load_operations_policy()
    evaluation = evaluate_operations(
        root=ROOT,
        policy=policy,
        run_metadata={
            "runKind": args.run_kind,
            "runUrl": args.run_url,
            "runNumber": args.run_number,
            "runSha": args.run_sha,
            "workflowEvent": args.workflow_event,
            "proposalGenerated": False,
            "autoMerge": False,
        },
    )
    write_json(ROOT / args.output, evaluation)
    (ROOT / args.report).parent.mkdir(parents=True, exist_ok=True)
    (ROOT / args.report).write_text(markdown_evaluation(evaluation), encoding="utf-8")
    print(json.dumps({"state": evaluation["state"], "alertRequired": evaluation["alertRequired"], "alertCode": evaluation["alertCode"]}, ensure_ascii=False, indent=2))
    return 0 if evaluation["state"] != "FAILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
