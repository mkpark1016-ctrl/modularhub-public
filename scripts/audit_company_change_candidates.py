#!/usr/bin/env python3
"""Audit company change-monitoring candidates and protection rules."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.company_change_monitoring import audit_change_run, write_audit_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-json", type=Path, default=ROOT / "data" / "company_change_monitoring" / "review_queue.json")
    args = parser.parse_args()
    payload = json.loads(args.run_json.read_text(encoding="utf-8"))
    run = {
        "generatedAt": payload.get("generatedAt"),
        "runId": payload.get("runId"),
        "companies": payload.get("companies", []),
        "sourceStatuses": payload.get("sourceStatuses", []),
        "candidates": payload.get("candidates", []),
        "candidateCount": payload.get("candidateCount", 0),
        "duplicate": payload.get("duplicate", 0),
        "publicDataChanged": False,
    }
    summary = audit_change_run(run)
    write_audit_outputs(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
