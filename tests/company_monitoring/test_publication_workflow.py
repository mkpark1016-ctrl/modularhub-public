from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "company-intelligence-publish.yml"


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_publish_workflow_is_manual_only() -> None:
    text = workflow_text()
    assert "workflow_dispatch:" in text
    for forbidden in ["schedule:", "pull_request:", "workflow_run:", "push:"]:
        assert forbidden not in text


def test_publish_workflow_has_required_inputs_and_permissions() -> None:
    text = workflow_text()
    for required in ["source_run_id:", "acknowledge_publish:", "target_branch:"]:
        assert required in text
    assert "contents: write" in text
    assert "pull-requests: write" in text
    assert "actions: read" in text
    assert "target_branch must be main" in text
    assert "acknowledge_publish must be true" in text


def test_publish_workflow_downloads_only_publication_artifacts() -> None:
    text = workflow_text()
    for required in [
        "company-intelligence-review-queue",
        "company-intelligence-digest",
        "company-intelligence-live-pilot",
        "company-intelligence-audit",
    ]:
        assert required in text
    assert "name: company-intelligence-raw" not in text


def test_publish_workflow_creates_data_branch_pr_not_main_push() -> None:
    text = workflow_text()
    assert "data/company-intelligence-run-${{ inputs.source_run_id }}" in text
    assert "git push --set-upstream origin \"$DATA_BRANCH\"" in text
    assert "\"draft\": True" in text
    assert "Update company intelligence public data from run #" in text
