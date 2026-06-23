from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.collectors.public_housing_contests.sh import collect_sh_public_housing_contests  # noqa: E402
from src.collectors.public_housing_contests.sh_common import OFFICIAL_HOSTS  # noqa: E402
from src.config import DB_PATH  # noqa: E402


ARTIFACT_DIR = ROOT / "artifacts" / "sh-live-verification"
PUBLIC_DATA_FILES = [
    ROOT / "frontend" / "public" / "data" / "business.json",
    ROOT / "frontend" / "public" / "data" / "news.json",
    ROOT / "frontend" / "public" / "data" / "meta.json",
]
MUTATION_FILES = PUBLIC_DATA_FILES + [Path(DB_PATH), ROOT / ".env"]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_snapshot(paths: list[Path]) -> dict[str, str | None]:
    return {str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path): sha256_file(path) for path in paths}


def load_public_counts() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in ("business", "news", "meta"):
        path = ROOT / "frontend" / "public" / "data" / f"{name}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        items = payload.get("items") if isinstance(payload, dict) else payload if isinstance(payload, list) else []
        result[f"{name}_count"] = len(items) if isinstance(items, list) else 0
        if name == "business" and isinstance(items, list):
            result["lh_public_count"] = sum(
                item.get("source") == "LH" and item.get("source_type") == "public_agency_contest" for item in items
            )
            result["gh_public_count"] = sum(
                item.get("source") == "GH" and item.get("source_type") == "public_agency_contest" for item in items
            )
            result["ih_public_count"] = sum(
                item.get("source") == "iH" and item.get("source_type") == "public_agency_contest" for item in items
            )
            result["sh_public_count"] = sum(
                item.get("source") == "SH" and item.get("source_type") == "public_agency_contest" for item in items
            )
    return result


def official_domain(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    return host in OFFICIAL_HOSTS


def write_outputs(report: dict[str, Any], stdout_lines: list[str]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (ARTIFACT_DIR / "stdout.log").write_text("\n".join(stdout_lines) + "\n", encoding="utf-8")
    markdown = [
        "# SH live verification",
        "",
        f"- checked_at: {report.get('checked_at')}",
        f"- status: {report.get('status')}",
        f"- failure_reason: {report.get('failure_reason') or ''}",
        f"- source_url: {report.get('source_url')}",
        f"- final_url: {report.get('final_url')}",
        f"- collector_mode: {report.get('collector_mode')}",
        f"- scanned_count: {report.get('scanned_count')}",
        f"- sh_notice_count: {report.get('sh_notice_count')}",
        f"- g2b_linked_count: {report.get('g2b_linked_count')}",
        f"- confirmed_count: {report.get('confirmed_count')}",
        f"- review_required_count: {report.get('review_required_count')}",
        f"- result_count: {report.get('result_count')}",
        f"- exact_link_count: {report.get('exact_link_count')}",
        f"- attachment_count: {report.get('attachment_count')}",
        f"- public_json_unchanged: {report.get('public_json_unchanged')}",
        f"- db_unchanged: {report.get('db_unchanged')}",
        f"- env_unchanged: {report.get('env_unchanged')}",
    ]
    if report.get("status") == "success_no_matches":
        markdown.extend(["", "SH 수집 성공, 현재 공개 가능한 민간참여 공공주택 공모 없음"])
    (ARTIFACT_DIR / "report.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")

    summary_path = Path(str(Path.cwd() / "_github_step_summary_placeholder"))
    import os

    if os.getenv("GITHUB_STEP_SUMMARY"):
        summary_path = Path(os.environ["GITHUB_STEP_SUMMARY"])
        with summary_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(markdown) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only live verification for SH public housing contest collector.")
    parser.add_argument("--max-pages", type=int, default=3)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started = time.perf_counter()
    stdout_lines: list[str] = []
    before = file_snapshot(MUTATION_FILES)
    counts_before = load_public_counts()
    checked_at = now_iso()
    report: dict[str, Any] = {
        "checked_at": checked_at,
        "collector_mode": "http_html",
        "status": "failed",
        "failure_reason": "",
        "parser_mismatch": False,
        "source_url": "",
        "final_url": "",
        "http_status": None,
        "scanned_count": 0,
        "sh_notice_count": 0,
        "g2b_linked_count": 0,
        "confirmed_count": 0,
        "review_required_count": 0,
        "result_count": 0,
        "irrelevant_count": 0,
        "exact_link_count": 0,
        "attachment_count": 0,
        "duration_seconds": 0,
        "public_json_unchanged": False,
        "db_unchanged": False,
        "env_unchanged": False,
        "counts_before": counts_before,
        "counts_after": {},
    }

    try:
        stats = collect_sh_public_housing_contests(dry_run=True, max_pages=args.max_pages, verbose=False)
        summary = stats.summary()
        stdout_lines.append(json.dumps(summary, ensure_ascii=False))
        report.update(
            {
                "status": summary.get("status"),
                "failure_reason": summary.get("failure_reason") or "",
                "parser_mismatch": bool(summary.get("parser_mismatch")),
                "source_url": summary.get("source_url") or "",
                "final_url": summary.get("final_url") or "",
                "http_status": summary.get("http_status"),
                "scanned_count": summary.get("scanned") or 0,
                "sh_notice_count": summary.get("sh_notice_count") or 0,
                "g2b_linked_count": summary.get("g2b_linked_count") or 0,
                "confirmed_count": summary.get("confirmed_count") or 0,
                "review_required_count": summary.get("review_required_count") or 0,
                "result_count": summary.get("result_count") or 0,
                "irrelevant_count": summary.get("irrelevant_count") or 0,
                "exact_link_count": summary.get("exact_link_count") or 0,
                "attachment_count": summary.get("attachment_count") or 0,
            }
        )
    except Exception as exc:  # pragma: no cover - live defensive path
        report["status"] = "failed"
        report["failure_reason"] = "unexpected_error"
        stdout_lines.append(f"unexpected_error: {exc}")
        stdout_lines.append(traceback.format_exc())

    after = file_snapshot(MUTATION_FILES)
    counts_after = load_public_counts()
    report["counts_after"] = counts_after
    report["duration_seconds"] = round(time.perf_counter() - started, 3)
    report["public_json_unchanged"] = all(before.get(str(path.relative_to(ROOT))) == after.get(str(path.relative_to(ROOT))) for path in PUBLIC_DATA_FILES)
    db_key = str(Path(DB_PATH).relative_to(ROOT) if Path(DB_PATH).is_relative_to(ROOT) else Path(DB_PATH))
    report["db_unchanged"] = before.get(db_key) == after.get(db_key)
    report["env_unchanged"] = before.get(".env") == after.get(".env")

    failure = ""
    if not report["public_json_unchanged"] or not report["db_unchanged"] or not report["env_unchanged"]:
        failure = "mutation_detected"
    elif not official_domain(str(report.get("final_url") or "")):
        failure = "unexpected_domain"
    elif not report.get("scanned_count"):
        failure = report.get("failure_reason") or "parser_mismatch"
    elif report.get("parser_mismatch"):
        failure = "parser_mismatch"
    elif report.get("status") not in {"success", "success_no_matches"}:
        failure = report.get("failure_reason") or "unexpected_error"

    if failure:
        report["status"] = "failed" if failure != "parser_mismatch" else "parser_mismatch"
        report["failure_reason"] = failure

    write_outputs(report, stdout_lines)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failure else 1


if __name__ == "__main__":
    raise SystemExit(main())
