#!/usr/bin/env python3
"""Safe OpenDART configuration and connectivity preflight."""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.env_config import env_status  # noqa: E402
from src.opendart_client import OpenDartClient, OpenDartResponseError  # noqa: E402

OUTPUT_DIR = ROOT / "artifacts" / "company-research-wave-1-dart-live"

STATUS_LABELS = {
    "010": "INVALID_UNREGISTERED_KEY",
    "011": "DISABLED_KEY",
    "012": "IP_ACCESS_BLOCKED",
    "013": "NO_DATA",
    "020": "RATE_LIMIT_EXCEEDED",
    "800": "SYSTEM_MAINTENANCE",
}


def run_preflight(refresh: bool = False) -> dict[str, object]:
    status = env_status("OPENDART_API_KEY", expected_length=40)
    result: dict[str, object] = {
        "env": status,
        "network_status": "not_started",
        "opendart_status": "",
        "opendart_status_label": "",
        "corp_code_zip_downloaded": False,
        "corp_code_xml_parsed": False,
        "corp_code_count": 0,
        "corp_code_length_valid": False,
        "cache_contains_key": False,
    }
    if not status["configured"]:
        result["network_status"] = "blocked_api_key_not_configured"
        return result
    if not status["expected_length_match"]:
        result["network_status"] = "blocked_invalid_api_key_length"
        return result

    client = OpenDartClient()
    try:
        rows = client.list_corp_codes(refresh=refresh)
        result["network_status"] = "ok"
        result["opendart_status"] = "000"
        result["opendart_status_label"] = "OK"
        result["corp_code_count"] = len(rows)
        result["corp_code_xml_parsed"] = bool(rows)
        result["corp_code_length_valid"] = all(len(row.get("corp_code", "")) == 8 for row in rows[:1000])
        zip_path = client.cache_dir / "corp_codes.zip"
        xml_path = client.cache_dir / "corp_codes.xml"
        result["corp_code_zip_downloaded"] = zip_path.exists() and zipfile.is_zipfile(zip_path)
        key = os.getenv("OPENDART_API_KEY", "")
        if xml_path.exists():
            text = xml_path.read_text(encoding="utf-8", errors="ignore")
            result["cache_contains_key"] = bool(key and key in text)
    except OpenDartResponseError as exc:
        result["network_status"] = "opendart_error"
        result["opendart_status"] = exc.status
        result["opendart_status_label"] = STATUS_LABELS.get(exc.status, "UNEXPECTED_API_ERROR")
    except Exception as exc:
        result["network_status"] = "network_or_parse_error"
        result["error_type"] = exc.__class__.__name__
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpenDART preflight without exposing API keys.")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    result = run_preflight(refresh=args.refresh)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "api_preflight.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("network_status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
