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
    D2B_SERVICE_KEY_ENV,
    DEFAULT_LOOKAHEAD_MONTHS,
    DEFAULT_LOOKBACK_DAYS,
    D2BClient,
)
from scripts.integrations.business.d2b_schema_fingerprint import (
    collect_schema_fingerprint,
    verify_schema_fingerprint,
    write_schema_fingerprint,
)


DEFAULT_OUTPUT_DIR = Path("artifacts/d2b-schema-fingerprint")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect key-only fingerprints from the three D2B GW facility operations.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--acknowledge-live", action="store_true")
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    service_key = os.getenv(D2B_SERVICE_KEY_ENV, "").strip()
    configured = bool(service_key)
    print(f"{D2B_SERVICE_KEY_ENV} configured: {str(configured).lower()}")
    if not (args.live and args.acknowledge_live):
        print("D2B schema fingerprint skipped: --live and --acknowledge-live are both required.")
        return 2
    if not configured:
        print(f"D2B schema fingerprint not attempted: {D2B_SERVICE_KEY_ENV} configured: false")
        return 3

    today = date.today()
    plan_from = today.replace(day=1)
    plan_to = _add_months(plan_from, DEFAULT_LOOKAHEAD_MONTHS)
    bid_to = today
    bid_from = bid_to - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    summary = collect_schema_fingerprint(
        client=D2BClient(service_key=service_key),
        plan_from=plan_from,
        plan_to=plan_to,
        bid_from=bid_from,
        bid_to=bid_to,
    )
    verify_schema_fingerprint(summary, service_key=service_key)
    write_schema_fingerprint(summary, args.output_dir)
    print(json.dumps(_console_summary(summary), ensure_ascii=False))
    return 0


def _console_summary(summary: dict[str, Any]) -> dict[str, Any]:
    operations = summary.get("operations") or {}
    return {
        "source": "d2b",
        "fingerprint_health": summary.get("fingerprint_health"),
        "page_limit": 1,
        "operations": {
            name: {
                "http_status": payload.get("http_status"),
                "api_result_code": payload.get("api_result_code"),
                "records_observed": payload.get("records_observed"),
                "key_count": payload.get("key_count"),
                "observed_keys": payload.get("observed_keys"),
                "error_category": payload.get("error_category"),
            }
            for name, payload in operations.items()
        },
    }


def _add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    year = value.year + month // 12
    return date(year, month % 12 + 1, 1)


if __name__ == "__main__":
    raise SystemExit(main())
