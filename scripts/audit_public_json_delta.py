from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LOG_DIR = ROOT / "logs"
BUSINESS_PATH = ROOT / "frontend" / "public" / "data" / "business.json"
NEWS_PATH = ROOT / "frontend" / "public" / "data" / "news.json"
META_PATH = ROOT / "frontend" / "public" / "data" / "meta.json"
ALLOWED_CONTEST_STAGES = {"pre_notice", "main_notice", "re_notice", "correction"}
CONTEST_SOURCE_RULES = {
    "LH": {"host": "lh.or.kr", "path_token": "board.es", "query_token": "list_no="},
    "GH": {"host": "gh.or.kr", "path_token": "bid-announcement.do", "query_token": "articleNo="},
    "iH": {"host": "ih.co.kr", "path_token": "bbsMsgDetail.do", "query_token": "msg_seq="},
}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "none", "nan", "nat"} else text


def payload_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return [item for item in payload["items"] if isinstance(item, dict)]
    return []


def load_json_path(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {"items": payload}
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} must contain a JSON object or array")
    return payload


def load_git_head(path: str) -> dict[str, Any]:
    result = subprocess.run(
        ["git", "show", f"HEAD:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload = json.loads(result.stdout)
    if isinstance(payload, list):
        return {"items": payload}
    return payload


def item_id(item: dict[str, Any]) -> str:
    return clean_text(item.get("id"))


def canonical(item: dict[str, Any]) -> str:
    return json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def by_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        key = item_id(item) or f"missing-id:{index}"
        result[key] = item
    return result


def source_counter(items: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(clean_text(item.get("source_name") or item.get("source")) or "unknown" for item in items))


def type_counter(items: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(clean_text(item.get("source_type")) or "unknown" for item in items))


def summarize_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "source": item.get("source_name") or item.get("source"),
        "source_type": item.get("source_type"),
        "type": item.get("type"),
        "title": item.get("title"),
        "organization": item.get("organization"),
        "source_record_id": item.get("source_record_id"),
        "bid_no": item.get("bid_no"),
        "plan_no": item.get("plan_no"),
        "posted_at": item.get("posted_at"),
        "due_at": item.get("due_at"),
        "external_original_url": item.get("external_original_url"),
    }


def is_contest_exact_url(source: str, url: str, source_record_id: str) -> bool:
    if not url or not source_record_id:
        return False
    rule = CONTEST_SOURCE_RULES.get(source)
    if not rule:
        return False
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    expected_host = rule["host"]
    return (
        parsed.scheme in {"http", "https"}
        and (host == expected_host or host.endswith("." + expected_host))
        and rule["path_token"] in parsed.path
        and f"{rule['query_token']}{source_record_id}" in parsed.query
    )


def find_unexpected(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unexpected: list[dict[str, Any]] = []
    for item in items:
        source = clean_text(item.get("source_name") or item.get("source")).lower()
        source_type = clean_text(item.get("source_type")).lower()
        title = clean_text(item.get("title")).lower()
        urls = json.dumps(item, ensure_ascii=False).lower()
        reasons = []
        if source_type == "mock" or any(token in source for token in ("mock", "sample", "test")):
            reasons.append("mock_or_sample_source")
        if any(token in title for token in ("테스트용", "샘플", "mock", "sample")):
            reasons.append("mock_or_sample_title")
        if any(token in urls for token in ("localhost", "127.0.0.1", "example.com")):
            reasons.append("non_public_url")
        if reasons:
            unexpected.append({**summarize_item(item), "reasons": reasons})
    return unexpected


def validate_public_contest_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for item in items:
        source = clean_text(item.get("source"))
        if source not in CONTEST_SOURCE_RULES or item.get("source_type") != "public_agency_contest":
            continue
        reasons = []
        source_record_id = clean_text(item.get("source_record_id") or item.get("bid_no"))
        original_url = clean_text(item.get("external_original_url"))
        if item.get("business_type") != "private_participation_public_housing":
            reasons.append("business_type_mismatch")
        expected_source_code = {"LH": "LH_CONTEST", "GH": "GH_CONTEST", "iH": "IH_NOTICE"}.get(source)
        if expected_source_code and clean_text(item.get("source_code")) != expected_source_code:
            reasons.append("source_code_mismatch")
        if not source_record_id:
            reasons.append("missing_source_record_id")
        if source == "GH" and clean_text(item.get("id")) != f"gh_contest:{source_record_id}":
            reasons.append("invalid_gh_public_id")
        if source == "iH" and clean_text(item.get("id")) != f"ih_contest:{source_record_id}":
            reasons.append("invalid_ih_public_id")
        if not is_contest_exact_url(source, original_url, source_record_id):
            reasons.append("invalid_public_contest_original_url")
        if not item.get("title"):
            reasons.append("missing_title")
        if not item.get("posted_at"):
            reasons.append("missing_posted_at")
        if item.get("notice_status") not in ALLOWED_CONTEST_STAGES:
            reasons.append("non_opportunity_stage")
        if not item.get("modular_relevance"):
            reasons.append("missing_modular_relevance")
        if not isinstance(item.get("attachments"), list):
            reasons.append("attachments_not_list")
        if reasons:
            violations.append({**summarize_item(item), "reasons": reasons})
    return violations


def load_db_exclusions() -> list[dict[str, Any]]:
    try:
        from src.config import DB_PATH
        import sqlite3
    except Exception:
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, source_record_id, title, notice_status, is_operating_scope, original_url
        FROM items
        WHERE source_name='LH' AND source_type='public_agency_contest'
          AND COALESCE(is_operating_scope, 0) != 1
        ORDER BY source_record_id DESC
        """
    ).fetchall()
    return [
        {
            "db_id": row["id"],
            "source": "LH",
            "source_type": "public_agency_contest",
            "source_record_id": row["source_record_id"],
            "title": row["title"],
            "notice_status": row["notice_status"],
            "reason": "not_public_opportunity_stage",
            "original_url": row["original_url"],
        }
        for row in rows
    ]


def build_report(base_payload: dict[str, Any], current_payload: dict[str, Any]) -> dict[str, Any]:
    base_items = payload_items(base_payload)
    current_items = payload_items(current_payload)
    base_map = by_id(base_items)
    current_map = by_id(current_items)
    added_ids = sorted(set(current_map) - set(base_map), key=str)
    removed_ids = sorted(set(base_map) - set(current_map), key=str)
    changed_ids = sorted(
        item_id
        for item_id in set(base_map) & set(current_map)
        if canonical(base_map[item_id]) != canonical(current_map[item_id])
    )
    added = [summarize_item(current_map[item_id]) for item_id in added_ids]
    removed = [summarize_item(base_map[item_id]) for item_id in removed_ids]
    changed = [
        {
            "id": item_id,
            "before": summarize_item(base_map[item_id]),
            "after": summarize_item(current_map[item_id]),
        }
        for item_id in changed_ids
    ]
    unexpected = find_unexpected(current_items)
    public_contest_violations = validate_public_contest_items(current_items)
    policy_excluded = load_db_exclusions()
    return {
        "base_count": len(base_items),
        "current_count": len(current_items),
        "added_count": len(added),
        "removed_count": len(removed),
        "changed_count": len(changed),
        "added_by_source": source_counter([current_map[item_id] for item_id in added_ids]),
        "removed_by_source": source_counter([base_map[item_id] for item_id in removed_ids]),
        "current_by_source": source_counter(current_items),
        "current_by_type": type_counter(current_items),
        "added": added,
        "removed": removed,
        "changed": changed[:100],
        "unexpected_records": unexpected,
        "public_contest_count_by_source": source_counter(
            [item for item in current_items if item.get("source_type") == "public_agency_contest"]
        ),
        "public_contest_violations": public_contest_violations,
        "lh_public_count": sum(
            1 for item in current_items if item.get("source") == "LH" and item.get("source_type") == "public_agency_contest"
        ),
        "gh_public_count": sum(
            1 for item in current_items if item.get("source") == "GH" and item.get("source_type") == "public_agency_contest"
        ),
        "ih_public_count": sum(
            1 for item in current_items if item.get("source") == "iH" and item.get("source_type") == "public_agency_contest"
        ),
        "policy_excluded_db_items": policy_excluded,
    }


def write_reports(report: dict[str, Any]) -> tuple[Path, Path]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    json_path = LOG_DIR / "public_json_delta_audit.json"
    md_path = LOG_DIR / "public_json_delta_audit.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Public JSON Delta Audit",
        "",
        f"- base_count: {report['base_count']}",
        f"- current_count: {report['current_count']}",
        f"- added_count: {report['added_count']}",
        f"- removed_count: {report['removed_count']}",
        f"- changed_count: {report['changed_count']}",
        f"- added_by_source: {report['added_by_source']}",
        f"- removed_by_source: {report['removed_by_source']}",
        f"- current_by_source: {report['current_by_source']}",
        f"- current_by_type: {report['current_by_type']}",
        f"- lh_public_count: {report['lh_public_count']}",
        f"- gh_public_count: {report['gh_public_count']}",
        f"- ih_public_count: {report['ih_public_count']}",
        f"- public_contest_count_by_source: {report['public_contest_count_by_source']}",
        f"- unexpected_records: {len(report['unexpected_records'])}",
        f"- public_contest_violations: {len(report['public_contest_violations'])}",
        "",
        "## Added",
    ]
    for item in report["added"]:
        lines.append(f"- {item['id']} | {item['source']} | {item['source_type']} | {item['title']}")
    lines.append("")
    lines.append("## Removed")
    for item in report["removed"]:
        lines.append(f"- {item['id']} | {item['source']} | {item['source_type']} | {item['title']}")
    lines.append("")
    lines.append("## Policy Excluded DB Items")
    for item in report["policy_excluded_db_items"]:
        lines.append(f"- {item['source_record_id']} | {item['notice_status']} | {item['title']} | {item['reason']}")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit public business JSON delta.")
    parser.add_argument("--base", default="git-head", choices=["git-head"], help="Baseline source.")
    parser.add_argument("--current", default=str(BUSINESS_PATH), help="Current business JSON path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_payload = load_git_head("frontend/public/data/business.json")
    current_payload = load_json_path((ROOT / args.current).resolve() if not Path(args.current).is_absolute() else Path(args.current))
    report = build_report(base_payload, current_payload)
    json_path, md_path = write_reports(report)
    print(f"base_count={report['base_count']}")
    print(f"current_count={report['current_count']}")
    print(f"added_count={report['added_count']}")
    print(f"removed_count={report['removed_count']}")
    print(f"changed_count={report['changed_count']}")
    print(f"added_by_source={report['added_by_source']}")
    print(f"removed_by_source={report['removed_by_source']}")
    print(f"unexpected_records={len(report['unexpected_records'])}")
    print(f"lh_public_count={report['lh_public_count']}")
    print(f"gh_public_count={report['gh_public_count']}")
    print(f"ih_public_count={report['ih_public_count']}")
    print(f"public_contest_violations={len(report['public_contest_violations'])}")
    print(f"report_path={json_path.relative_to(ROOT)}")
    print(f"report_md_path={md_path.relative_to(ROOT)}")
    if report["unexpected_records"]:
        print("Unexpected public records detected.")
        return 1
    if report["public_contest_violations"]:
        print("Public contest validation failed.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
