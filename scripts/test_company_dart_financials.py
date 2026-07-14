#!/usr/bin/env python3
"""Regression tests for Wave 1 DART financial audit outputs."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from audit_company_dart_financials import collect_artifacts  # noqa: E402
from src.env_config import env_status  # noqa: E402
from validate_company_dart_financials import validate  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    result = validate()
    audit = collect_artifacts()
    counts = result["issue_counts"]
    key_status = env_status("OPENDART_API_KEY", expected_length=40)
    require(result["valid"], f"DART financial validation failed: {result['issues']}")
    require(result["wave_1_company_count"] == 4, "Wave 1 DART validation must cover 4 companies")
    require(counts["missing_dart_identity"] == 0, "DART identity field must exist for each Wave 1 company")
    require(counts["corp_code_duplicate"] == 0, "DART corp_code duplicates must be zero")
    if key_status["configured"] and key_status["expected_length_match"]:
        require(counts["api_key_required"] == 0, "api_key_required should be cleared after live DART lookup")
    else:
        require(counts["ambiguous_identity"] == 0, "ambiguous identity count must be zero in the no-key baseline")
        require(counts["api_key_required"] == 4, "all Wave 1 companies should be marked api_key_required without OPENDART_API_KEY")
        require(counts["reports_found"] == 0, "reports must not be fabricated without live DART lookup")
        require(counts["financial_years"] == 0, "financial years must remain empty without filing sources")
    require(counts["reporting_scope_missing"] == 0, "reporting scope missing count must be zero")
    require(counts["source_id_missing"] == 0, "source ID missing count must be zero")
    require(counts["unit_missing"] == 0, "unit missing count must be zero")
    require(counts["number_without_source"] == 0, "numbers without source must be zero")
    require(counts["modular_segment_misclassification"] == 0, "modular segment misclassification must be zero")
    require(audit["audit_status"] in {"passed", "passed_with_api_key_required"}, "audit status must be passing")
    print("COMPANY DART FINANCIAL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
