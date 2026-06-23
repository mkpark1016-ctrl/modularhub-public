from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
READINESS_DIR = ROOT / "artifacts" / "sh-production-readiness"
VERCEL_REPORT = ROOT / "artifacts" / "vercel-json-verification" / "report.json"
DIST_DATA_DIR = ROOT / "frontend" / "dist" / "data"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def validate_local_dist() -> dict[str, Any]:
    result: dict[str, Any] = {"valid": True, "files": {}, "business_count": None, "news_count": None, "errors": []}
    for name in ("business.json", "news.json", "meta.json"):
        path = DIST_DATA_DIR / name
        payload = load_json(path)
        info = {"exists": path.exists(), "json_parse_success": payload is not None}
        if payload is None:
            result["valid"] = False
            result["errors"].append(f"{name}: missing or invalid JSON")
        elif name == "business.json":
            items = payload.get("items") if isinstance(payload, dict) else payload
            result["business_count"] = len(items) if isinstance(items, list) else None
            info["item_count"] = result["business_count"]
        elif name == "news.json":
            items = payload.get("items") if isinstance(payload, dict) else payload
            result["news_count"] = len(items) if isinstance(items, list) else None
            info["item_count"] = result["news_count"]
        elif name == "meta.json" and isinstance(payload, dict):
            info["business_count"] = payload.get("business_count")
            info["news_count"] = payload.get("news_count")
        result["files"][name] = info
    if result["business_count"] != 155:
        result["valid"] = False
        result["errors"].append(f"local business count expected 155, got {result['business_count']}")
    if result["news_count"] != 653:
        result["valid"] = False
        result["errors"].append(f"local news count expected 653, got {result['news_count']}")
    return result


def deployed_status() -> dict[str, Any]:
    report = load_json(VERCEL_REPORT)
    if not isinstance(report, dict):
        return {"loaded": False, "business": "missing", "news": "missing", "meta": "missing", "ready": False}
    path_map = {item.get("path"): item for item in report.get("results", []) if isinstance(item, dict)}
    return {
        "loaded": True,
        "ready": bool(report.get("production_json_ready")),
        "business": (path_map.get("/data/business.json") or {}).get("detected_response_type"),
        "news": (path_map.get("/data/news.json") or {}).get("detected_response_type"),
        "meta": (path_map.get("/data/meta.json") or {}).get("detected_response_type"),
        "raw": report,
    }


def load_sh_workflow_report(path: str | None) -> dict[str, Any]:
    if not path:
        return {"verified": False, "status": "not_verified", "blocking_reason": "SH live workflow report was not provided"}
    payload = load_json(Path(path))
    if not isinstance(payload, dict):
        return {"verified": False, "status": "not_verified", "blocking_reason": "SH live workflow report could not be read"}
    verified = (
        payload.get("status") in {"success", "success_no_matches"}
        and int(payload.get("scanned_count") or 0) > 0
        and not payload.get("parser_mismatch")
        and payload.get("public_json_unchanged") is True
        and payload.get("db_unchanged") is True
    )
    return {
        "verified": verified,
        "status": payload.get("status") or "unknown",
        "scanned_count": payload.get("scanned_count"),
        "parser_mismatch": payload.get("parser_mismatch"),
        "public_json_unchanged": payload.get("public_json_unchanged"),
        "database_unchanged": payload.get("db_unchanged"),
        "blocking_reason": "" if verified else "SH live workflow did not meet production gate criteria",
    }


def write_report(report: dict[str, Any]) -> None:
    READINESS_DIR.mkdir(parents=True, exist_ok=True)
    (READINESS_DIR / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# SH production readiness",
        "",
        f"- checked_at: {report['checked_at']}",
        f"- production_ready: {report['production_ready']}",
        f"- sh_live_workflow_verified: {report['sh_live_workflow_verified']}",
        f"- sh_live_status: {report['sh_live_status']}",
        f"- vercel_business_json_status: {report['vercel_business_json_status']}",
        f"- vercel_news_json_status: {report['vercel_news_json_status']}",
        f"- vercel_meta_json_status: {report['vercel_meta_json_status']}",
        f"- local_dist_json_valid: {report['local_dist_json_valid']}",
        "",
        "## Blocking reasons",
    ]
    if report["blocking_reasons"]:
        lines.extend(f"- {reason}" for reason in report["blocking_reasons"])
    else:
        lines.append("- none")
    (READINESS_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build SH production readiness report.")
    parser.add_argument("--sh-live-report", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    local = validate_local_dist()
    deployed = deployed_status()
    sh = load_sh_workflow_report(args.sh_live_report or None)
    blocking: list[str] = []
    if not local["valid"]:
        blocking.extend(local["errors"])
    if not deployed.get("ready"):
        blocking.append("Vercel deployed public JSON is not ready")
    if not sh["verified"]:
        blocking.append(sh["blocking_reason"])
    report = {
        "checked_at": now_iso(),
        "sh_live_workflow_verified": sh["verified"],
        "sh_live_status": sh["status"],
        "sh_scanned_count": sh.get("scanned_count"),
        "sh_parser_mismatch": sh.get("parser_mismatch"),
        "sh_public_json_unchanged": sh.get("public_json_unchanged"),
        "sh_database_unchanged": sh.get("database_unchanged"),
        "vercel_business_json_status": deployed.get("business"),
        "vercel_news_json_status": deployed.get("news"),
        "vercel_meta_json_status": deployed.get("meta"),
        "local_dist_json_valid": local["valid"],
        "local_dist": local,
        "production_ready": not blocking,
        "blocking_reasons": [reason for reason in blocking if reason],
    }
    write_report(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["production_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
