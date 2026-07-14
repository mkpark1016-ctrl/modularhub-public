#!/usr/bin/env python3
"""Validate DART financial account alias configuration."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALIASES_PATH = ROOT / "config" / "companies" / "dart_account_aliases.json"

REQUIRED_FIELDS = [
    "revenue",
    "cost_of_sales",
    "gross_profit",
    "operating_profit",
    "net_income",
    "operating_cash_flow",
    "total_assets",
    "total_liabilities",
    "total_equity",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    payload = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
    aliases = payload.get("aliases", {})
    require(payload.get("schema_version") == "dart-account-aliases-v2", "unexpected alias schema version")
    require(payload.get("normalized_unit") == "KRW_MILLION", "normalized financial unit must be KRW_MILLION")
    for field in REQUIRED_FIELDS:
        require(field in aliases, f"missing aliases for {field}")
        require(isinstance(aliases[field], list) and aliases[field], f"{field} aliases must be a non-empty list")
    require("매출액" in aliases["revenue"], "revenue aliases must include Korean account name")
    require("영업손실" in aliases["operating_profit"], "operating profit aliases must include operating loss")
    require("당기순손실" in aliases["net_income"], "net income aliases must include net loss")
    require("영업활동으로 인한 현금흐름" in aliases["operating_cash_flow"], "operating cash flow aliases must include full Korean account name")

    duplicate_aliases: dict[str, list[str]] = {}
    for field, values in aliases.items():
        for value in values:
            normalized = "".join(str(value).lower().split())
            duplicate_aliases.setdefault(normalized, []).append(field)
    conflicts = {alias: fields for alias, fields in duplicate_aliases.items() if len(set(fields)) > 1}
    manual = {"".join(str(value).lower().split()) for value in payload.get("manual_review_required_aliases", [])}
    unresolved = {alias: fields for alias, fields in conflicts.items() if alias not in manual}
    require(not unresolved, f"ambiguous aliases must be listed for manual review: {unresolved}")
    print("DART ACCOUNT MAPPING TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
