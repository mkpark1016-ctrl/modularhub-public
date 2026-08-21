from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(".github/workflows/update-public-data.yml")


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_existing_daily_schedule_and_collectors_are_preserved() -> None:
    workflow = workflow_text()
    assert 'cron: "0 22 * * *"' in workflow
    assert workflow.count("cron:") == 1
    assert "Collect bids and news" in workflow
    assert "Collect G2B procurement plans" in workflow
    assert "Collect LH public housing contests" in workflow
    assert "Collect GH public housing contests" in workflow
    assert "Collect iH public housing contests" in workflow
    assert "Collect known important G2B bids" in workflow


def test_scheduled_unified_collection_is_bounded_and_uses_existing_secrets() -> None:
    workflow = workflow_text()
    assert "LH_SERVICE_KEY: ${{ secrets.LH_SERVICE_KEY }}" in workflow
    assert "DATA_GO_KR_SERVICE_KEY: ${{ secrets.DATA_GO_KR_SERVICE_KEY }}" in workflow
    assert '"LH_SERVICE_KEY=${LH_SERVICE_KEY}"' in workflow
    assert 'echo "${LH_SERVICE_KEY}"' not in workflow
    assert 'echo "${DATA_GO_KR_SERVICE_KEY}"' not in workflow
    assert workflow.count("python -m scripts.integrations.business.run_lh_pilot") == 1
    assert workflow.count("python scripts/integrations/business/run_d2b_pilot.py") == 1
    assert "--lookback-days 30" in workflow
    assert "--page-size 5" in workflow
    assert workflow.count("--max-pages 2") == 2
    assert "--bid-lookback-days 90" in workflow
    assert "--plan-lookahead-months 12" in workflow


def test_source_failures_and_validation_failure_choose_default_exporter() -> None:
    workflow = workflow_text()
    assert '${{ steps.scheduled_lh.outcome }}' in workflow
    assert '${{ steps.scheduled_d2b.outcome }}' in workflow
    assert "failure_category=source_transient" in workflow
    assert "--source-only" in workflow
    assert "failure_category=publication_safety" in workflow
    assert "unified_ready=false" in workflow
    assert 'if [ "${{ steps.scheduled_unified.outputs.unified_ready }}" = "true" ]' in workflow
    assert "else\n            python scripts/export_public_json.py\n          fi" in workflow


def test_success_uses_unified_export_and_publication_safety_remains_blocking() -> None:
    workflow = workflow_text()
    assert "unified_ready=true" in workflow
    assert "--unified-business-records artifacts/scheduled-unified/unified/unified_business_records.json" in workflow
    assert "--unified-business-summary artifacts/scheduled-unified/unified/unified_business_summary.json" in workflow
    assert "--unified-integration-report artifacts/scheduled-unified/public_pipeline_integration_report.json" in workflow
    assert "Enforce scheduled Unified publication safety" in workflow
    assert "steps.scheduled_unified.outputs.failure_category == 'publication_safety'" in workflow
    assert workflow.index("Export public JSON") < workflow.index(
        "Enforce scheduled Unified publication safety"
    )
    assert workflow.index("Enforce scheduled Unified publication safety") < workflow.index(
        "Protect cumulative public JSON"
    )


def test_sanitized_diagnostics_and_artifact_contract() -> None:
    workflow = workflow_text()
    assert "scheduled-unified-${{ github.run_number }}-${{ github.run_attempt }}" in workflow
    assert "artifacts/scheduled-unified/lh/lh_summary.json" in workflow
    assert "artifacts/scheduled-unified/d2b/d2b_summary.json" in workflow
    assert "artifacts/scheduled-unified/unified/unified_business_summary.json" in workflow
    assert "artifacts/scheduled-unified/public_pipeline_integration_report.json" in workflow
    assert "retention-days: 14" in workflow
    assert "Unified attempted:" in workflow
    assert "Unified ready:" in workflow
    assert "Fallback default exporter used:" in workflow
    assert "serviceKey" not in workflow
    assert "request_headers" not in workflow
