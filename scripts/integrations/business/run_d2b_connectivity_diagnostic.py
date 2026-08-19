from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.integrations.business.d2b import D2B_SERVICE_KEY_ENV
from scripts.integrations.business.d2b_connectivity import (
    run_connectivity_diagnostic,
    write_diagnostic_outputs,
)


DEFAULT_OUTPUT_DIR = Path("artifacts/d2b-connectivity")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a read-only data.go.kr and D2B GW connectivity diagnostic."
    )
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
        summary = {
            "schema_version": "1.0",
            "request_attempted": False,
            "configured": configured,
            "guard": "requires --live and --acknowledge-live",
        }
        write_diagnostic_outputs(summary, args.output_dir)
        print("Connectivity requests skipped: explicit live acknowledgement is required.")
        return 2

    if not configured:
        summary = {
            "schema_version": "1.0",
            "request_attempted": False,
            "configured": False,
            "error_category": "missing_secret",
        }
        write_diagnostic_outputs(summary, args.output_dir)
        print(f"Connectivity requests skipped: {D2B_SERVICE_KEY_ENV} configured: false")
        return 3

    summary = run_connectivity_diagnostic(service_key=service_key)
    summary["configured"] = True
    write_diagnostic_outputs(summary, args.output_dir)

    for name, probe in summary["probes"].items():
        print(
            " ".join(
                [
                    f"probe={name}",
                    f"host={probe.get('host', '-')}",
                    f"http_reached={_display(probe.get('http_reached'))}",
                    f"http_status={_display(probe.get('http_status'))}",
                    f"api_result_code={probe.get('api_result_code') or '-'}",
                    f"transport_category={probe.get('transport_category') or '-'}",
                    f"exception_type={probe.get('exception_type') or '-'}",
                    f"elapsed_ms={probe.get('elapsed_ms', 0)}",
                ]
            )
        )
    print(f"classification={summary['classification']['case']}")
    return 4 if summary["classification"]["case"] == "diagnostic_implementation_failure" else 0


def _display(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
