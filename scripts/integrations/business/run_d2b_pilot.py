from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.integrations.business.d2b import (
    D2B_RESOURCES,
    D2B_SERVICE_KEY_ENV,
    DEFAULT_LOOKAHEAD_MONTHS,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MAX_PAGES,
    DEFAULT_PAGE_SIZE,
    D2BClient,
    D2BPilotRunner,
    is_d2b_acceptance_failure,
    write_staging_outputs,
)


DEFAULT_OUTPUT_DIR = Path("artifacts/d2b")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the read-only D2B procurement API canonical staging pilot.")
    parser.add_argument("--resources", default="procurement_plan,bid_notice")
    parser.add_argument("--bid-from-date", dest="bid_from_date")
    parser.add_argument("--bid-to-date", dest="bid_to_date")
    parser.add_argument("--plan-from-date", dest="plan_from_date")
    parser.add_argument("--plan-to-date", dest="plan_to_date")
    parser.add_argument("--bid-lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--plan-lookahead-months", type=int, default=DEFAULT_LOOKAHEAD_MONTHS)
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--acknowledge-live", action="store_true")
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    resources = [name.strip() for name in args.resources.split(",") if name.strip()]
    invalid_resources = sorted(set(resources) - set(D2B_RESOURCES))
    if invalid_resources:
        raise SystemExit(f"Unsupported D2B resources: {', '.join(invalid_resources)}")

    configured = bool(os.getenv(D2B_SERVICE_KEY_ENV, "").strip())
    print(f"{D2B_SERVICE_KEY_ENV} configured: {str(configured).lower()}")

    if not (args.live and args.acknowledge_live):
        summary = {
            "source": "d2b",
            "run_mode": "dry_run",
            "live_opt_in": False,
            "request_attempted": False,
            "configured": configured,
            "resources": resources,
            "guard": "requires --live and --acknowledge-live",
        }
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "d2b_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("D2B live request skipped: --live and --acknowledge-live are both required.")
        return 2

    if not configured:
        summary = {
            "source": "d2b",
            "run_mode": "live",
            "live_opt_in": True,
            "request_attempted": False,
            "configured": False,
            "resources": resources,
            "error_category": "missing_secret",
        }
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "d2b_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"D2B live request not attempted: {D2B_SERVICE_KEY_ENV} configured: false")
        return 3

    plan_from, plan_to = _plan_window(args.plan_from_date, args.plan_to_date, args.plan_lookahead_months)
    bid_from, bid_to = _bid_window(args.bid_from_date, args.bid_to_date, args.bid_lookback_days)
    client = D2BClient(page_size=args.page_size)
    runner = D2BPilotRunner(client=client)
    records, summary = runner.collect(
        resource_names=resources,
        plan_from=plan_from,
        plan_to=plan_to,
        bid_from=bid_from,
        bid_to=bid_to,
        max_pages=args.max_pages,
    )
    summary.update(
        {
            "run_mode": "live",
            "live_opt_in": True,
            "request_attempted": True,
            "configured": True,
            "plan_from_date": plan_from.isoformat(),
            "plan_to_date": plan_to.isoformat(),
            "bid_from_date": bid_from.isoformat(),
            "bid_to_date": bid_to.isoformat(),
            "output_files": {
                "records": str(args.output_dir / "d2b_records.json"),
                "summary": str(args.output_dir / "d2b_summary.json"),
            },
        }
    )
    write_staging_outputs(records, summary, args.output_dir)
    _print_sanitized_summary(summary)
    return 4 if is_d2b_acceptance_failure(summary) else 0


def _print_sanitized_summary(summary: dict[str, Any]) -> None:
    print("D2B live pilot summary:")
    for resource, payload in (summary.get("resources") or {}).items():
        first_error = _first_api_error(payload)
        error_parts = []
        if first_error:
            error_parts = [
                f"error_category={first_error.get('category', '-')}",
                f"result_code={first_error.get('result_code', '-')}",
                f"exception_type={first_error.get('exception_type', '-')}",
                f"final_exception_type={first_error.get('final_exception_type', '-')}",
                f"transport_category={first_error.get('transport_category', '-')}",
                f"attempt_count={first_error.get('attempt_count', '-')}",
                f"endpoint_scheme={first_error.get('endpoint_scheme', '-')}",
                f"endpoint_host={first_error.get('endpoint_host', '-')}",
            ]
        print(
            " ".join(
                [
                    f"- {resource}:",
                    f"pages_requested={payload.get('pages_requested')}",
                    f"records_received={payload.get('records_received')}",
                    f"records_matched={payload.get('records_matched')}",
                    f"records_normalized={payload.get('records_normalized')}",
                    f"records_invalid={payload.get('records_invalid')}",
                    f"duplicates={payload.get('duplicates')}",
                    f"api_errors={len(payload.get('api_errors') or [])}",
                    f"source_health={payload.get('source_health', '-')}",
                    f"invalid_reasons={payload.get('invalid_reasons', {})}",
                ]
                + error_parts
            )
        )
        for operation, counts in sorted((payload.get("operation_counts") or {}).items()):
            print(
                " ".join(
                    [
                        f"  - {operation}:",
                        f"pages_requested={counts.get('pages_requested')}",
                        f"records_received={counts.get('records_received')}",
                        f"records_matched={counts.get('records_matched')}",
                        f"records_normalized={counts.get('records_normalized')}",
                        f"records_invalid={counts.get('records_invalid')}",
                        f"duplicates={counts.get('duplicates')}",
                        f"endpoint_scheme={counts.get('endpoint_scheme', '-')}",
                        f"endpoint_host={counts.get('endpoint_host', '-')}",
                    ]
                )
            )


def _first_api_error(payload: dict[str, Any]) -> dict[str, Any] | None:
    errors = payload.get("api_errors") or []
    return errors[0] if errors else None


def _bid_window(from_date: str | None, to_date: str | None, lookback_days: int) -> tuple[date, date]:
    end = date.fromisoformat(to_date) if to_date else date.today()
    start = date.fromisoformat(from_date) if from_date else end - timedelta(days=max(lookback_days, 1))
    if start > end:
        raise SystemExit("--bid-from-date must be earlier than or equal to --bid-to-date")
    return start, end


def _plan_window(from_date: str | None, to_date: str | None, lookahead_months: int) -> tuple[date, date]:
    start = date.fromisoformat(from_date) if from_date else date.today().replace(day=1)
    end = date.fromisoformat(to_date) if to_date else _add_months(start, max(lookahead_months, 1))
    if start > end:
        raise SystemExit("--plan-from-date must be earlier than or equal to --plan-to-date")
    return start, end


def _add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    return date(year, month, 1)


if __name__ == "__main__":
    raise SystemExit(main())
