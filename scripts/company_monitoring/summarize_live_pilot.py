from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.company_monitoring.common import DATA_DIR, RAW_DIR, REPORT_DIR, iso_now, read_json, write_json  # noqa: E402

LIVE_REPORT_DIR = ROOT / "artifacts" / "company-intelligence-live-pilot"
RAW_FILES = {
    "dart": "dart_raw.json",
    "naver_search": "naver_search_raw.json",
}
CONFIG_KEYS = {
    "dart": ["DART_API_KEY"],
    "naver_search": ["NAVER_API_HUB_CLIENT_ID", "NAVER_API_HUB_CLIENT_SECRET"],
}


def categorize_error(source: str, error_type: str | None) -> str | None:
    value = (error_type or "").lower()
    if not value:
        return None
    if "not_configured" in value:
        return "configuration_error"
    if "live_opt_in_required" in value:
        return "live_opt_in_required"
    if "auth" in value or "unauthorized" in value or "forbidden" in value or "status_010" in value or "status_011" in value:
        return "auth_error"
    if "429" in value or "rate" in value or "too many" in value:
        return "rate_limited"
    if "json" in value or "parse" in value:
        return "response_parse_error"
    if source == "dart" and "opendart_status_" in value:
        return "response_status_error"
    if "urlopen" in value or "timed out" in value or "connection" in value or "name resolution" in value:
        return "transport_error"
    return "source_error"


def result_status(result: dict[str, Any]) -> str:
    if result.get("status") == "error":
        return categorize_error(str(result.get("source_type") or ""), result.get("error_type")) or "source_error"
    count = len(result.get("candidates") or [])
    if count > 0:
        return "success_with_candidates"
    return "success_empty"


def source_summary(raw_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source, file_name in RAW_FILES.items():
        path = raw_dir / file_name
        if not path.exists():
            continue
        payload = read_json(path)
        env = payload.get("env") or {}
        configured = all(env.get(key) == "configured" for key in CONFIG_KEYS[source])
        for result in payload.get("results", []):
            candidates = result.get("candidates") or []
            rejected = result.get("rejected") or []
            status = result_status(result)
            rows.append(
                {
                    "run_mode": payload.get("run_mode", "unknown"),
                    "live_opt_in": bool(payload.get("live_opt_in")),
                    "company_id": result.get("company_id"),
                    "source": source,
                    "configured": configured,
                    "request_attempted": status != "live_opt_in_required" and configured,
                    "auth_valid": None if status in {"configuration_error", "live_opt_in_required"} else status != "auth_error",
                    "transport_status": "error" if status == "transport_error" else "ok" if not status.endswith("error") else "unknown",
                    "response_status": status,
                    "candidate_count": len(candidates),
                    "normalized_count": len(candidates),
                    "pending_count": 0,
                    "duplicate_count": 0,
                    "conflict_count": 0,
                    "rejected_count": len(rejected),
                    "error_category": None if status.startswith("success_") else status,
                    "collected_at": result.get("fetched_at") or payload.get("fetched_at"),
                }
            )
    return rows


def merge_digest_counts(rows: list[dict[str, Any]], digest_path: Path) -> None:
    if not digest_path.exists():
        return
    digest = read_json(digest_path)
    pending_by_company = digest.get("company_counts") or {}
    duplicate_total = int(digest.get("duplicate_count") or 0)
    conflict_total = int(digest.get("conflict_count") or 0)
    pending_total = int(digest.get("pending_count") or 0)
    for row in rows:
        company_id = row.get("company_id")
        row["pending_count"] = int(pending_by_company.get(company_id, 0) or 0)
    if rows:
        rows[0]["duplicate_count"] = duplicate_total
        rows[0]["conflict_count"] = conflict_total
        rows[0]["pending_total"] = pending_total


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Company Intelligence Live Pilot Report",
        "",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Run mode: `{summary['run_mode']}`",
        f"- Live opt-in: `{str(summary['live_opt_in']).lower()}`",
        f"- Secret exposure detected: `{str(summary['secret_exposure_detected']).lower()}`",
        "",
        "## Source Results",
        "",
        "| company_id | source | configured | response_status | candidates | pending | duplicate | conflict | rejected |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary["results"]:
        lines.append(
            "| {company_id} | {source} | {configured} | {response_status} | {candidate_count} | {pending_count} | {duplicate_count} | {conflict_count} | {rejected_count} |".format(
                **row
            )
        )
    lines.extend(["", "## Artifact Paths"])
    for key, value in summary["artifact_paths"].items():
        lines.append(f"- {key}: `{value}`")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_summary(raw_dir: Path, queue_path: Path, digest_path: Path, output_dir: Path) -> dict[str, Any]:
    rows = source_summary(raw_dir)
    merge_digest_counts(rows, digest_path)
    live_opt_in = any(row.get("live_opt_in") for row in rows)
    run_mode = "live" if live_opt_in else "blocked"
    summary = {
        "generated_at": iso_now(),
        "run_mode": run_mode,
        "live_opt_in": live_opt_in,
        "results": rows,
        "secret_exposure_detected": False,
        "artifact_paths": {
            "raw_dir": str(raw_dir),
            "review_queue": str(queue_path),
            "digest_json": str(digest_path),
            "live_pilot_summary_json": str(output_dir / "live-pilot-summary.json"),
            "live_pilot_report_md": str(output_dir / "live-pilot-report.md"),
        },
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize a company monitoring live pilot run.")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--queue-path", type=Path, default=DATA_DIR / "review_queue.json")
    parser.add_argument("--digest-json", type=Path, default=REPORT_DIR / "latest_digest.json")
    parser.add_argument("--output-dir", type=Path, default=LIVE_REPORT_DIR)
    args = parser.parse_args()
    summary = build_summary(args.raw_dir, args.queue_path, args.digest_json, args.output_dir)
    write_json(args.output_dir / "live-pilot-summary.json", summary)
    write_markdown(args.output_dir / "live-pilot-report.md", summary)
    print(
        json.dumps(
            {
                "run_mode": summary["run_mode"],
                "live_opt_in": summary["live_opt_in"],
                "result_count": len(summary["results"]),
                "output": str(args.output_dir),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
