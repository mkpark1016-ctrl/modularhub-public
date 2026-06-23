from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "artifacts" / "vercel-json-verification"
DATA_PATHS = ("data/business.json", "data/news.json", "data/meta.json")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def normalize_base_url(value: str) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError("base URL is required")
    if not text.startswith(("http://", "https://")):
        text = "https://" + text
    return text.rstrip("/") + "/"


def detect_response_type(status: int | None, content_type: str, body_prefix: str, json_ok: bool) -> str:
    lowered = body_prefix.lower()
    if status == 404:
        return "not_found"
    if status in {401, 403} or "vercel" in lowered and any(token in lowered for token in ("authentication", "protection", "login", "deployment")):
        return "vercel_protection_html"
    if json_ok:
        return "json"
    if "text/html" in content_type.lower() or lowered.startswith("<!doctype html") or lowered.startswith("<html"):
        if "id=\"root\"" in lowered or "/assets/" in lowered or "vite" in lowered:
            return "spa_index_html"
        return "generic_html"
    if status is None:
        return "network_error"
    return "generic_html"


def item_count_for_payload(path: str, payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return len(payload) if isinstance(payload, list) else None
    if path.endswith("meta.json"):
        return None
    items = payload.get("items")
    return len(items) if isinstance(items, list) else None


def expected_count_for_payload(path: str, payload: Any) -> int | None:
    if not path.endswith("meta.json") or not isinstance(payload, dict):
        return None
    return None


def verify_one(session: requests.Session, base_url: str, path: str) -> dict[str, Any]:
    requested_url = urljoin(base_url, path)
    started = time.perf_counter()
    try:
        response = session.get(requested_url, timeout=20, allow_redirects=True)
        content_type = response.headers.get("content-type", "")
        text = response.text
        body_prefix = text[:2048]
        payload: Any = None
        json_ok = False
        parse_error = ""
        try:
            payload = response.json()
            json_ok = True
        except ValueError as exc:
            parse_error = str(exc)
        response_type = detect_response_type(response.status_code, content_type, body_prefix, json_ok)
        if "vercel.com/login" in response.url.lower() or "/sso-api" in response.url.lower():
            response_type = "vercel_protection_html"
        failure = ""
        if response_type != "json":
            failure = response_type
        elif response.status_code != 200:
            failure = f"http_{response.status_code}"
        return {
            "path": "/" + path,
            "requested_url": requested_url,
            "final_url": response.url,
            "http_status": response.status_code,
            "content_type": content_type,
            "response_size": len(response.content),
            "redirect_count": len(response.history),
            "detected_response_type": response_type,
            "json_parse_success": json_ok,
            "json_parse_error": parse_error[:200],
            "item_count": item_count_for_payload(path, payload),
            "meta_business_count": payload.get("business_count") if isinstance(payload, dict) and path.endswith("meta.json") else None,
            "meta_news_count": payload.get("news_count") if isinstance(payload, dict) and path.endswith("meta.json") else None,
            "failure_reason": failure,
            "duration_seconds": round(time.perf_counter() - started, 3),
        }
    except requests.RequestException as exc:
        return {
            "path": "/" + path,
            "requested_url": requested_url,
            "final_url": requested_url,
            "http_status": None,
            "content_type": "",
            "response_size": 0,
            "redirect_count": 0,
            "detected_response_type": "network_error",
            "json_parse_success": False,
            "json_parse_error": "",
            "item_count": None,
            "meta_business_count": None,
            "meta_news_count": None,
            "failure_reason": f"network_error: {exc}",
            "duration_seconds": round(time.perf_counter() - started, 3),
        }


def write_report(report: dict[str, Any]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Vercel public JSON verification",
        "",
        f"- checked_at: {report.get('checked_at')}",
        f"- base_url: {report.get('base_url')}",
        f"- overall_status: {report.get('overall_status')}",
        f"- production_json_ready: {report.get('production_json_ready')}",
        "",
        "## Responses",
    ]
    for result in report.get("results", []):
        lines.extend(
            [
                f"- {result['path']}",
                f"  - status: {result['http_status']}",
                f"  - content_type: {result['content_type']}",
                f"  - detected_response_type: {result['detected_response_type']}",
                f"  - json_parse_success: {result['json_parse_success']}",
                f"  - item_count: {result['item_count']}",
                f"  - failure_reason: {result['failure_reason']}",
            ]
        )
    (ARTIFACT_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify deployed ModularHub public JSON endpoints.")
    parser.add_argument("--base-url", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base = normalize_base_url(args.base_url or __import__("os").environ.get("PUBLIC_SITE_URL", ""))
    session = requests.Session()
    session.headers.update({"User-Agent": "ModularHubPublicJsonVerifier/1.0"})
    results = [verify_one(session, base, path) for path in DATA_PATHS]
    failures = [result for result in results if result.get("detected_response_type") != "json" or not result.get("json_parse_success")]
    report = {
        "checked_at": now_iso(),
        "base_url": base.rstrip("/"),
        "overall_status": "success" if not failures else "failed",
        "production_json_ready": not failures,
        "results": results,
        "failure_reasons": [f"{item['path']}: {item['failure_reason']}" for item in failures],
    }
    write_report(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
