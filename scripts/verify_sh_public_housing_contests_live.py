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


ARTIFACT_DIR = ROOT / "artifacts" / "sh_live_verification"
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


def record_candidate(record: Any) -> dict[str, Any]:
    publish_eligible = bool(getattr(record, "is_public_opportunity", False))
    return {
        "internal_id": f"sh_contest:{getattr(record, 'source_record_id', '')}",
        "source_name": getattr(record, "source_name", "SH"),
        "source_type": getattr(record, "source_type", "public_agency_contest"),
        "title": getattr(record, "title", ""),
        "posted_date": getattr(record, "posted_at", None),
        "stage": getattr(record, "stage", "unknown"),
        "classification": getattr(record, "classification_status", "unknown"),
        "keyword_matches": list(getattr(record, "modular_evidence", []) or []),
        "seq": getattr(record, "source_record_id", ""),
        "bid_ntce_no": "",
        "bid_ntce_ord": "",
        "list_url": getattr(record, "board_url", ""),
        "detail_url": getattr(record, "source_page_url", ""),
        "official_url": getattr(record, "original_url", None),
        "link_type": "exact_original" if getattr(record, "exact_link_verified", False) else "unverified",
        "exact_link_verified": bool(getattr(record, "exact_link_verified", False)),
        "attachment_count": len(getattr(record, "attachments", []) or []),
        "publish_eligible": publish_eligible,
        "review_reason": "" if publish_eligible else getattr(record, "link_validation_reason", "") or "not_publish_eligible",
    }


def g2b_candidate(discovery: Any) -> dict[str, Any]:
    bid_no = getattr(discovery, "bid_no", "")
    bid_order = getattr(discovery, "bid_order", "")
    return {
        "internal_id": f"g2b:{bid_no}:{bid_order}",
        "source_name": "SH",
        "source_type": "bid",
        "title": getattr(discovery, "title", ""),
        "posted_date": getattr(discovery, "posted_at", None),
        "stage": "linked_bid",
        "classification": "g2b_linked",
        "keyword_matches": [],
        "seq": "",
        "bid_ntce_no": bid_no,
        "bid_ntce_ord": bid_order,
        "list_url": getattr(discovery, "source_page_url", ""),
        "detail_url": getattr(discovery, "detail_url", ""),
        "official_url": getattr(discovery, "detail_url", ""),
        "link_type": "g2b_link",
        "exact_link_verified": False,
        "attachment_count": 0,
        "publish_eligible": False,
        "review_reason": "g2b_linked_shadow_only",
    }


def build_candidates(stats: Any) -> list[dict[str, Any]]:
    candidates = [record_candidate(record) for record in getattr(stats, "records", [])]
    candidates.extend(g2b_candidate(discovery) for discovery in getattr(stats, "g2b_discoveries", []))
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for candidate in candidates:
        key = candidate["internal_id"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def write_outputs(report: dict[str, Any], stdout_lines: list[str], output_dir: Path, candidates: list[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "stdout.log").write_text("\n".join(stdout_lines) + "\n", encoding="utf-8")
    (output_dir / "candidates.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = [
        "# SH live verification",
        "",
        f"- checked_at: {report.get('checked_at')}",
        f"- status: {report.get('status')}",
        f"- failure_reason: {report.get('failure_reason') or ''}",
        f"- source_url: {report.get('source_url')}",
        f"- list_url: {report.get('list_url')}",
        f"- final_url: {report.get('final_url')}",
        f"- collector_mode: {report.get('collector_mode')}",
        f"- detected_page_type: {report.get('detected_page_type')}",
        f"- http_status: {report.get('http_status')}",
        f"- row_count: {report.get('row_count')}",
        f"- rows_with_title: {report.get('rows_with_title')}",
        f"- rows_with_identifier: {report.get('rows_with_identifier')}",
        f"- parse_success_ratio: {report.get('parse_success_ratio')}",
        f"- detail_link_candidate_count: {report.get('detail_link_candidate_count')}",
        f"- unique_detail_candidate_count: {report.get('unique_detail_candidate_count')}",
        f"- detail_fetch_target_count: {report.get('detail_fetch_target_count')}",
        f"- scanned_count: {report.get('scanned_count')}",
        f"- sh_notice_count: {report.get('sh_notice_count')}",
        f"- g2b_linked_count: {report.get('g2b_linked_count')}",
        f"- confirmed_count: {report.get('confirmed_count')}",
        f"- review_required_count: {report.get('review_required_count')}",
        f"- result_count: {report.get('result_count')}",
        f"- exact_link_count: {report.get('exact_link_count')}",
        f"- attachment_count: {report.get('attachment_count')}",
        f"- publish_eligible_count: {report.get('publish_eligible_count')}",
        f"- parser_mismatch: {report.get('parser_mismatch')}",
        f"- parser_mismatch_reasons: {', '.join(report.get('parser_mismatch_reasons') or [])}",
        f"- public_json_unchanged: {report.get('public_json_unchanged')}",
        f"- db_unchanged: {report.get('db_unchanged')}",
        f"- env_unchanged: {report.get('env_unchanged')}",
    ]
    if report.get("status") == "success_no_matches":
        markdown.extend(["", "SH 수집 성공, 현재 공개 가능한 민간참여 공공주택 공모 없음"])
    if report.get("publish_eligible_count"):
        markdown.extend(["", "SH 공개 검토 후보가 발견되었습니다. candidates.json을 검토하십시오."])
    (output_dir / "report.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")

    summary_path = Path(str(Path.cwd() / "_github_step_summary_placeholder"))
    import os

    if os.getenv("GITHUB_STEP_SUMMARY"):
        summary_path = Path(os.environ["GITHUB_STEP_SUMMARY"])
        with summary_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(markdown) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only live verification for SH public housing contest collector.")
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--list-url", default="")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--output-dir", default=str(ARTIFACT_DIR))
    parser.add_argument("--request-delay", type=float, default=None)
    parser.add_argument("--timeout", type=int, default=None)
    return parser.parse_args()


def exit_code_for_status(status: str, failure_reason: str = "") -> int:
    if status in {"success", "success_no_matches"}:
        return 0
    if status in {"parser_mismatch", "wrong_page_type"}:
        return 2
    if status == "network_error":
        return 3
    if status == "blocked":
        return 4
    if status == "http_error":
        return 5
    if failure_reason == "mutation_detected":
        return 1
    return 1


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    started = time.perf_counter()
    stdout_lines: list[str] = []
    candidates: list[dict[str, Any]] = []
    before = file_snapshot(MUTATION_FILES)
    counts_before = load_public_counts()
    checked_at = now_iso()
    report: dict[str, Any] = {
        "checked_at": checked_at,
        "collector_mode": "http_html",
        "status": "failed",
        "failure_reason": "",
        "parser_mismatch": False,
        "parser_mismatch_reasons": [],
        "source_url": "",
        "list_url": "",
        "final_url": "",
        "http_status": None,
        "page_title": "",
        "detected_page_type": "unknown_page",
        "table_found": False,
        "empty_list_message_found": False,
        "row_count": 0,
        "rows_with_title": 0,
        "rows_with_identifier": 0,
        "rows_with_posted_date": 0,
        "rows_with_href": 0,
        "rows_with_onclick": 0,
        "rows_with_seq": 0,
        "rows_with_bid_number": 0,
        "parse_success_ratio": 0.0,
        "detail_link_candidate_count": 0,
        "unique_detail_candidate_count": 0,
        "detail_candidate_count": 0,
        "detail_fetch_target_count": 0,
        "detail_fetch_attempted_count": 0,
        "detail_fetch_success_count": 0,
        "detail_fetch_failed_count": 0,
        "scanned_count": 0,
        "sh_notice_count": 0,
        "g2b_linked_count": 0,
        "confirmed_count": 0,
        "review_required_count": 0,
        "result_count": 0,
        "irrelevant_count": 0,
        "exact_link_count": 0,
        "attachment_count": 0,
        "publish_eligible_count": 0,
        "duration_seconds": 0,
        "public_json_unchanged": False,
        "db_unchanged": False,
        "env_unchanged": False,
        "counts_before": counts_before,
        "counts_after": {},
    }

    try:
        stats = collect_sh_public_housing_contests(
            dry_run=True,
            max_pages=args.max_pages,
            list_url=args.source_url or args.list_url or None,
            request_interval_seconds=args.request_delay,
            timeout_seconds=args.timeout,
            verbose=False,
        )
        candidates = build_candidates(stats)
        summary = stats.summary()
        stdout_lines.append(json.dumps(summary, ensure_ascii=False))
        report.update(
            {
                "status": summary.get("status"),
                "failure_reason": summary.get("failure_reason") or "",
                "parser_mismatch": bool(summary.get("parser_mismatch")),
                "parser_mismatch_reasons": summary.get("parser_mismatch_reasons") or [],
                "source_url": summary.get("source_url") or "",
                "list_url": summary.get("list_url") or "",
                "final_url": summary.get("final_url") or "",
                "http_status": summary.get("http_status"),
                "page_title": summary.get("page_title") or "",
                "detected_page_type": summary.get("detected_page_type") or "unknown_page",
                "table_found": bool(summary.get("table_found")),
                "empty_list_message_found": bool(summary.get("empty_list_message_found")),
                "row_count": summary.get("row_count") or 0,
                "rows_with_title": summary.get("rows_with_title") or 0,
                "rows_with_identifier": summary.get("rows_with_identifier") or 0,
                "rows_with_posted_date": summary.get("rows_with_posted_date") or 0,
                "rows_with_href": summary.get("rows_with_href") or 0,
                "rows_with_onclick": summary.get("rows_with_onclick") or 0,
                "rows_with_seq": summary.get("rows_with_seq") or 0,
                "rows_with_bid_number": summary.get("rows_with_bid_number") or 0,
                "parse_success_ratio": summary.get("parse_success_ratio") or 0.0,
                "detail_candidate_count": summary.get("detail_candidate_count") or 0,
                "detail_link_candidate_count": summary.get("detail_link_candidate_count") or 0,
                "unique_detail_candidate_count": summary.get("unique_detail_candidate_count") or 0,
                "detail_fetch_target_count": summary.get("detail_fetch_target_count") or 0,
                "detail_fetch_attempted_count": summary.get("detail_fetch_attempted_count") or 0,
                "detail_fetch_success_count": summary.get("detail_fetch_success_count") or 0,
                "detail_fetch_failed_count": summary.get("detail_fetch_failed_count") or 0,
                "scanned_count": summary.get("scanned") or 0,
                "sh_notice_count": summary.get("sh_notice_count") or 0,
                "g2b_linked_count": summary.get("g2b_linked_count") or 0,
                "confirmed_count": summary.get("confirmed_count") or 0,
                "review_required_count": summary.get("review_required_count") or 0,
                "result_count": summary.get("result_count") or 0,
                "irrelevant_count": summary.get("irrelevant_count") or 0,
                "exact_link_count": summary.get("exact_link_count") or 0,
                "attachment_count": summary.get("attachment_count") or 0,
                "publish_eligible_count": sum(1 for candidate in candidates if candidate.get("publish_eligible")),
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

    status = str(report.get("status") or "failed")
    failure = ""
    if not report["public_json_unchanged"] or not report["db_unchanged"] or not report["env_unchanged"]:
        failure = "mutation_detected"
        status = "failed"
    elif status in {"parser_mismatch", "wrong_page_type", "network_error", "blocked", "http_error"}:
        failure = report.get("failure_reason") or status
    elif report.get("final_url") and not official_domain(str(report.get("final_url") or "")):
        failure = "unexpected_domain"
        status = "blocked"
    elif status in {"success", "success_no_matches"} and not report.get("scanned_count") and not report.get("empty_list_message_found"):
        failure = "parser_mismatch"
        status = "parser_mismatch"
    elif report.get("parser_mismatch"):
        failure = "parser_mismatch"
    elif report.get("status") not in {"success", "success_no_matches"}:
        failure = report.get("failure_reason") or "unexpected_error"

    if failure:
        if status == "failed" and failure in {"parser_mismatch", "wrong_page_type", "network_error", "blocked", "http_error"}:
            status = failure
        report["status"] = status
        report["failure_reason"] = failure

    write_outputs(report, stdout_lines, output_dir, candidates)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return exit_code_for_status(str(report.get("status") or "failed"), str(report.get("failure_reason") or ""))


if __name__ == "__main__":
    raise SystemExit(main())
