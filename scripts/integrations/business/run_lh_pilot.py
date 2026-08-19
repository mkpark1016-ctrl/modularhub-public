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
from scripts.integrations.business.g2b import (
    G2B_RESOURCES,
    G2B_SERVICE_KEY_ENV,
    G2BClient,
    G2BFallbackRunner,
    build_related_record_candidates,
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
    parser.add_argument("--disable-g2b-fallback", action="store_true")
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    resources = [name.strip() for name in args.resources.split(",") if name.strip()]
    invalid_resources = sorted(set(resources) - set(LH_RESOURCES))
    if invalid_resources:
        raise SystemExit(f"Unsupported LH resources: {', '.join(invalid_resources)}")

    configured = bool(os.getenv(LH_SERVICE_KEY_ENV, "").strip())
    g2b_configured = bool(os.getenv(G2B_SERVICE_KEY_ENV, "").strip())
    print(f"{LH_SERVICE_KEY_ENV} configured: {str(configured).lower()}")
    print(f"{G2B_SERVICE_KEY_ENV} configured: {str(g2b_configured).lower()}")

    if not (args.live and args.acknowledge_live):
        summary = {
            "source": "lh",
            "run_mode": "dry_run",
            "live_opt_in": False,
            "request_attempted": False,
            "configured": configured,
            "g2b_configured": g2b_configured,
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
            "g2b_configured": g2b_configured,
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
    fallback_resource_names = [] if args.disable_g2b_fallback else _fallback_resource_names(summary)
    fallback_records = []
    fallback_summary: dict[str, Any] = {"source": "g2b", "resources": {}, "records_normalized": 0}
    if fallback_resource_names:
        fallback_runner = G2BFallbackRunner(client=G2BClient(page_size=args.page_size))
        fallback_records, fallback_summary = fallback_runner.collect(
            resource_names=fallback_resource_names,
            from_date=from_date,
            to_date=to_date,
            max_pages=args.max_pages,
        )
        records.extend(fallback_records)
        _mark_lh_fallbacks(summary, fallback_resource_names, fallback_summary)
    summary.update(
        {
            "run_mode": "live",
            "live_opt_in": True,
            "request_attempted": True,
            "configured": True,
            "g2b_configured": g2b_configured,
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "g2b_fallback": fallback_summary,
            "fallback_used": bool(fallback_resource_names),
            "overall_health": _overall_health(summary, fallback_summary),
            "related_record_candidates": build_related_record_candidates(records),
            "output_files": {
                "records": str(args.output_dir / "lh_records.json"),
                "summary": str(args.output_dir / "lh_summary.json"),
            },
        }
    )
    write_staging_outputs(records, summary, args.output_dir)
    _print_sanitized_summary(summary)
    return 0 if not _has_blocking_errors(summary) else 4


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
                    f"source_health={payload.get('source_health', '-')}",
                    f"fallback_used={payload.get('fallback_used', False)}",
                ]
                + error_parts
            )
        )
    g2b_resources = (summary.get("g2b_fallback") or {}).get("resources") or {}
    if g2b_resources:
        print("G2B fallback summary:")
        for resource, payload in g2b_resources.items():
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
                        f"source_health={payload.get('source_health', '-')}",
                        f"fallback_used={payload.get('fallback_used', False)}",
                        f"records_agency_matched={payload.get('records_agency_matched', '-')}",
                        f"records_filtered_non_lh={payload.get('records_filtered_non_lh', '-')}",
                        f"agency_filter_mode={payload.get('agency_filter_mode', '-')}",
                        f"agency_code_verified={payload.get('agency_code_verified', '-')}",
                        f"agency_identifier={payload.get('agency_identifier', '-')}",
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
                            f"records_agency_matched={counts.get('records_agency_matched')}",
                            f"records_filtered_non_lh={counts.get('records_filtered_non_lh')}",
                            f"records_normalized={counts.get('records_normalized')}",
                            f"records_invalid={counts.get('records_invalid')}",
                            f"duplicates={counts.get('duplicates')}",
                        ]
                    )
                )


def _has_blocking_errors(summary: dict[str, Any]) -> bool:
    return summary.get("overall_health") in {"failed", "degraded_unresolved"}


def _first_api_error(payload: dict[str, Any]) -> dict[str, Any] | None:
    errors = payload.get("api_errors") or []
    return errors[0] if errors else None


def _fallback_resource_names(summary: dict[str, Any]) -> list[str]:
    mapping = {"procurement_plan": "g2b_procurement_plan", "pre_spec": "g2b_pre_spec"}
    fallback_names = []
    for lh_name, g2b_name in mapping.items():
        resource = (summary.get("resources") or {}).get(lh_name) or {}
        if any(error.get("category") == "service_access_denied" and error.get("result_code") == "20" for error in resource.get("api_errors") or []):
            fallback_names.append(g2b_name)
    return fallback_names


def _mark_lh_fallbacks(summary: dict[str, Any], fallback_resource_names: list[str], fallback_summary: dict[str, Any]) -> None:
    reverse = {"g2b_procurement_plan": "procurement_plan", "g2b_pre_spec": "pre_spec"}
    for g2b_name in fallback_resource_names:
        lh_name = reverse[g2b_name]
        lh_resource = summary["resources"][lh_name]
        lh_resource["fallback_used"] = True
        fallback_resource = (fallback_summary.get("resources") or {}).get(g2b_name) or {}
        if fallback_resource.get("source_health") in {"healthy", "healthy_empty"}:
            lh_resource["source_health"] = "degraded_source"


def _overall_health(summary: dict[str, Any], fallback_summary: dict[str, Any]) -> str:
    lh_resources = summary.get("resources") or {}
    g2b_resources = (fallback_summary.get("resources") or {})
    unresolved = []
    fallback_used = False
    for name, resource in lh_resources.items():
        errors = resource.get("api_errors") or []
        if not errors:
            continue
        if name in {"procurement_plan", "pre_spec"} and resource.get("fallback_used"):
            fallback_used = True
            g2b_name = "g2b_procurement_plan" if name == "procurement_plan" else "g2b_pre_spec"
            if (g2b_resources.get(g2b_name) or {}).get("source_health") in {"healthy", "healthy_empty"}:
                continue
        unresolved.append(name)
    if unresolved:
        return "degraded_unresolved"
    return "success_with_fallback" if fallback_used else "healthy"


if __name__ == "__main__":
    raise SystemExit(main())
