from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from scripts.integrations.business.base import NormalizedBusinessRecord
from scripts.integrations.business.unified import build_unified_business_feed
from scripts.integrations.business.validate_unified_live_staging import (
    UnifiedLiveAcceptanceError,
    validate_source_acceptance,
    validate_unified_acceptance,
)


WORKFLOW = Path(".github/workflows/unified-business-live-staging.yml")


def canonical(source: str, external_id: str, record_type: str = "bid_notice") -> dict:
    return NormalizedBusinessRecord(
        source=source,
        source_record_type=record_type,
        external_id=external_id,
        title=f"{source} modular procurement {external_id}",
        issuing_organization="한국토지주택공사" if source in {"lh", "g2b"} else "방위사업청",
        published_at="2026-08-20",
        deadline_at="2026-08-30",
        source_url="https://www.d2b.go.kr/" if source == "d2b" else "https://example.test/item",
        collected_at="2026-08-20T00:00:00+00:00",
    ).as_dict()


def accepted_payloads() -> tuple[dict, list[dict], dict, list[dict], dict, list[dict]]:
    lh_records = [canonical("lh", "LH-1"), canonical("g2b", "G2B-1", "pre_spec")]
    d2b_records = [canonical("d2b", "D2B-1"), canonical("d2b", "D2B-2", "procurement_plan")]
    lh_summary = {
        "request_attempted": True,
        "overall_health": "success_with_fallback",
        "fallback_used": True,
        "records_normalized": 1,
        "g2b_fallback": {"records_normalized": 1},
    }
    d2b_summary = {"request_attempted": True, "overall_health": "healthy", "records_normalized": 2}
    unified_records, unified_summary = build_unified_business_feed(
        [NormalizedBusinessRecord(**item) for item in [*lh_records, *d2b_records]]
    )
    return lh_summary, lh_records, d2b_summary, d2b_records, unified_summary, [item.as_dict() for item in unified_records]


def test_source_acceptance_allows_lh_fallback_and_healthy_d2b() -> None:
    lh_summary, lh_records, d2b_summary, d2b_records, _, _ = accepted_payloads()
    result = validate_source_acceptance(lh_summary, lh_records, d2b_summary, d2b_records)
    assert result["lh_overall_health"] == "success_with_fallback"
    assert result["d2b_records_normalized"] == 2


@pytest.mark.parametrize("health", ["failed", "degraded_unresolved", None])
def test_source_acceptance_rejects_blocking_lh_health(health: str | None) -> None:
    lh_summary, lh_records, d2b_summary, d2b_records, _, _ = accepted_payloads()
    lh_summary["overall_health"] = health
    with pytest.raises(UnifiedLiveAcceptanceError, match="LH source acceptance failed") as exc:
        validate_source_acceptance(lh_summary, lh_records, d2b_summary, d2b_records)
    assert exc.value.category == "lh_source"


@pytest.mark.parametrize("health", ["failed", "schema_mismatch", "healthy_empty"])
def test_source_acceptance_rejects_nonhealthy_d2b(health: str) -> None:
    lh_summary, lh_records, d2b_summary, d2b_records, _, _ = accepted_payloads()
    d2b_summary["overall_health"] = health
    with pytest.raises(UnifiedLiveAcceptanceError, match="D2B source acceptance failed") as exc:
        validate_source_acceptance(lh_summary, lh_records, d2b_summary, d2b_records)
    assert exc.value.category == "d2b_source"


def test_unified_acceptance_passes_identity_source_and_security_gates() -> None:
    result = validate_unified_acceptance(*accepted_payloads())
    assert result["records_output"] == 4
    assert result["source_counts"] == {"d2b": 2, "g2b": 1, "lh": 1}
    assert result["duplicate_identity_count"] == 0
    assert result["credential_url_count"] == 0
    assert result["security_passed"] is True


def test_unified_acceptance_holds_for_identity_conflict() -> None:
    payloads = list(accepted_payloads())
    payloads[4] = deepcopy(payloads[4])
    payloads[4]["identity_conflict_count"] = 1
    with pytest.raises(UnifiedLiveAcceptanceError, match="identity conflict review") as exc:
        validate_unified_acceptance(*payloads)
    assert exc.value.category == "identity_conflict"


def test_unified_acceptance_rejects_duplicate_identity() -> None:
    payloads = list(accepted_payloads())
    payloads[5] = [*payloads[5], deepcopy(payloads[5][0])]
    payloads[4] = deepcopy(payloads[4])
    payloads[4]["records_output"] += 1
    payloads[4]["source_counts"][payloads[5][0]["source"]] += 1
    payloads[4]["record_type_counts"][payloads[5][0]["source_record_type"]] += 1
    with pytest.raises(UnifiedLiveAcceptanceError, match="duplicate source identities"):
        validate_unified_acceptance(*payloads)


def test_unified_acceptance_rejects_credential_url() -> None:
    payloads = list(accepted_payloads())
    payloads[5] = deepcopy(payloads[5])
    payloads[5][0]["source_url"] = "https://example.test/item?serviceKey=secret"
    with pytest.raises(UnifiedLiveAcceptanceError, match="security acceptance failed") as exc:
        validate_unified_acceptance(*payloads)
    assert exc.value.category == "security"


def test_unified_acceptance_rejects_record_type_count_mismatch() -> None:
    payloads = list(accepted_payloads())
    payloads[4] = deepcopy(payloads[4])
    payloads[4]["record_type_counts"]["bid_notice"] += 1
    with pytest.raises(UnifiedLiveAcceptanceError, match="record type counts"):
        validate_unified_acceptance(*payloads)


def test_workflow_is_manual_read_only_and_bounded() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    trigger_block = workflow.split("permissions:", 1)[0]
    assert "workflow_dispatch:" in trigger_block
    assert "schedule:" not in trigger_block
    assert "pull_request:" not in trigger_block
    assert "push:" not in trigger_block
    assert "contents: read" in workflow
    assert "actions: read" in workflow
    assert "ACKNOWLEDGE_LIVE" in workflow
    assert 'bounded_integer lh_max_pages "$LH_MAX_PAGES" 1 3' in workflow
    assert 'bounded_integer d2b_max_pages "$D2B_MAX_PAGES" 1 3' in workflow
    assert 'bounded_integer lh_page_size "$LH_PAGE_SIZE" 1 20' in workflow


def test_workflow_uses_both_secrets_without_echoing_values() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "LH_SERVICE_KEY: ${{ secrets.LH_SERVICE_KEY }}" in workflow
    assert "DATA_GO_KR_SERVICE_KEY: ${{ secrets.DATA_GO_KR_SERVICE_KEY }}" in workflow
    assert "LH_SERVICE_KEY configured:" in workflow
    assert "DATA_GO_KR_SERVICE_KEY configured:" in workflow
    assert 'echo "$LH_SERVICE_KEY"' not in workflow
    assert 'echo "$DATA_GO_KR_SERVICE_KEY"' not in workflow


def test_workflow_runs_each_source_and_unified_runner_once() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert workflow.count("python -m scripts.integrations.business.run_lh_pilot") == 1
    assert workflow.count("python scripts/integrations/business/run_d2b_pilot.py") == 1
    assert workflow.count("python scripts/integrations/business/run_unified_business_feed.py") == 1
    assert "G2BFallbackRunner" not in workflow
    assert "run_g2b" not in workflow


def test_workflow_preserves_artifacts_and_protected_public_data() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "actions/upload-artifact@v4" in workflow
    assert "unified-business-live-staging-${{ github.run_number }}-${{ github.run_attempt }}" in workflow
    assert "if-no-files-found: warn" in workflow
    assert "git diff --exit-code" in workflow
    assert "frontend/public/data/business.json" in workflow
    assert "frontend/public/data/news.json" in workflow
    assert "git add" not in workflow
    assert "git commit" not in workflow
    assert "git push" not in workflow
    assert "scripts/export_public_json.py" not in workflow
