#!/usr/bin/env python3
"""Tests for Wave 1 DART identity resolution."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from resolve_company_dart_identity import resolve_identities, wave1_companies  # noqa: E402
from src.opendart_client import OpenDartClient  # noqa: E402


class FakeClient:
    has_api_key = True

    def list_corp_codes(self) -> list[dict[str, str]]:
        return [
            {"corp_code": "00126380", "corp_name": "금강공업", "stock_code": "014280"},
            {"corp_code": "00999999", "corp_name": "테스트회사", "stock_code": ""},
        ]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    old_key = os.environ.pop("OPENDART_API_KEY", None)
    try:
        companies = wave1_companies()
        rows = resolve_identities(OpenDartClient(api_key=None), companies)
        require(len(rows) == 4, "Wave 1 identity rows must be 4")
        require({row["identity_status"] for row in rows} == {"api_key_required"}, "missing API key must be explicit")
        require(all(not row["dart_corp_code"] for row in rows), "corp codes must not be fabricated without an API key")

        fake_rows = resolve_identities(FakeClient(), companies)  # type: ignore[arg-type]
        by_id = {row["company_id"]: row for row in fake_rows}
        require(by_id["kumkang-kind"]["identity_status"] == "probable", "exact fake DART match should be probable")
        require(by_id["kumkang-kind"]["dart_corp_code"] == "00126380", "fake corp_code should be preserved")
        require(by_id["planm"]["identity_status"] == "not_found", "unmatched companies should remain not_found")
    finally:
        if old_key is not None:
            os.environ["OPENDART_API_KEY"] = old_key

    print("COMPANY DART IDENTITY TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
