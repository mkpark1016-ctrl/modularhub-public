from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from scripts.integrations.business.lh import (
    DEFAULT_PAGE_SIZE,
    LH_RESOURCES,
    LH_SERVICE_KEY_ENV,
    LHClient,
    LHPilotRunner,
    write_staging_outputs,
)


DEFAULT_OUTPUT_DIR = Path("artifacts/lh")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the read-only LH procurement API staging pilot.")
    parser.add_argument("--resources", default="procurement_plan,pre_spec,bid_notice")
    parser.add_argument("--from-date", dest="from_date")
    parser.add_argument("--to-date", dest="to_date")
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--acknowledge-live", action="store_true")
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    resources = [name.strip() for name in args.resources.split(",") if name.strip()]
    invalid_resources = sorted(set(resources) - set(LH_RESOURCES))
    if invalid_resources:
        raise SystemExit(f"Unsupported LH resources: {', '.join(invalid_resources)}")

    configured = bool(os.getenv(LH_SERVICE_KEY_ENV, "").strip())
    print(f"{LH_SERVICE_KEY_ENV} configured: {str(configured).lower()}")

    if not (args.live and args.acknowledge_live):
        summary = {
            "source": "lh",
            "run_mode": "dry_run",
            "live_opt_in": False,
            "request_attempted": False,
            "configured": configured,
            "resources": resources,
            "guard": "requires --live and --acknowledge-live",
        }
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "lh_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("LH live request skipped: --live and --acknowledge-live are both required.")
        return 2

    if not configured:
        summary = {
            "source": "lh",
            "run_mode": "live",
            "live_opt_in": True,
            "request_attempted": False,
            "configured": False,
            "resources": resources,
            "error_category": "missing_secret",
        }
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "lh_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("LH live request not attempted: LH_SERVICE_KEY configured: false")
        return 3

    from_date, to_date = _date_window(args.from_date, args.to_date, args.lookback_days)
    client = LHClient(page_size=args.page_size)
    runner = LHPilotRunner(client=client)
    records, summary = runner.collect(
        resource_names=resources,
        from_date=from_date,
        to_date=to_date,
        max_pages=args.max_pages,
    )
    summary.update(
        {
            "run_mode": "live",
            "live_opt_in": True,
            "request_attempted": True,
            "configured": True,
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "output_files": {
                "records": str(args.output_dir / "lh_records.json"),
                "summary": str(args.output_dir / "lh_summary.json"),
            },
        }
    )
    write_staging_outputs(records, summary, args.output_dir)
    _print_sanitized_summary(summary)
    return 0 if not _has_api_errors(summary) else 4


def _date_window(from_date: str | None, to_date: str | None, lookback_days: int) -> tuple[date, date]:
    end = date.fromisoformat(to_date) if to_date else date.today()
    start = date.fromisoformat(from_date) if from_date else end - timedelta(days=max(lookback_days, 1))
    if start > end:
        raise SystemExit("--from-date must be earlier than or equal to --to-date")
    return start, end


def _print_sanitized_summary(summary: dict[str, Any]) -> None:
    print("LH live pilot summary:")
    for resource, payload in summary.get("resources", {}).items():
        first_error = _first_api_error(payload)
        error_parts = []
        if first_error:
            error_parts = [
                f"error_category={first_error.get('category', '-')}",
                f"result_code={first_error.get('result_code', '-')}",
                f"exception_type={first_error.get('exception_type', '-')}",
                f"endpoint_scheme={first_error.get('endpoint_scheme', '-')}",
                f"endpoint_host={first_error.get('endpoint_host', '-')}",
            ]
        print(
            " ".join(
                [
                    f"- {resource}:",
                    f"pages_requested={payload.get('pages_requested')}",
                    f"records_received={payload.get('records_received')}",
                    f"records_normalized={payload.get('records_normalized')}",
                    f"records_invalid={payload.get('records_invalid')}",
                    f"duplicates={payload.get('duplicates')}",
                    f"api_errors={len(payload.get('api_errors') or [])}",
                ]
                + error_parts
            )
        )


def _has_api_errors(summary: dict[str, Any]) -> bool:
    return any(bool(payload.get("api_errors")) for payload in summary.get("resources", {}).values())


def _first_api_error(payload: dict[str, Any]) -> dict[str, Any] | None:
    errors = payload.get("api_errors") or []
    return errors[0] if errors else None


if __name__ == "__main__":
    raise SystemExit(main())
