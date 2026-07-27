from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.company_source_coverage import audit_source_coverage_from_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit Company Change Monitor source coverage artifacts without external API calls.")
    parser.add_argument("--raw-summary", type=Path, default=ROOT / "artifacts" / "company-change-monitor" / "raw-summary.json")
    parser.add_argument("--review-queue", type=Path, default=ROOT / "data" / "company_change_monitoring" / "review_queue.json")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--head-sha", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = audit_source_coverage_from_files(
        root=ROOT,
        raw_summary_path=args.raw_summary,
        review_queue_path=args.review_queue,
        run_id=args.run_id,
        head_sha=args.head_sha,
        write_outputs=True,
    )
    print(
        json.dumps(
            {
                "state": report["state"],
                "valid": report["valid"],
                "warningCodes": report.get("warningCodes", []),
                "failureCodes": report.get("failureCodes", []),
                "sourceAttempted": report.get("sourceAttempted", []),
                "dartMappingCoverage": report.get("dartMappingCoverage", {}),
                "artifactPaths": report.get("artifactPaths", {}),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if report["state"] == "FAILED" or not report["valid"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
