from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "verify-gdelt-webngrams-live.yml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    lowered = text.lower()

    require("name: Verify GDELT Web NGrams live" in text, "workflow name mismatch")
    require("workflow_dispatch:" in text, "workflow_dispatch trigger missing")
    forbidden_triggers = ["\n  schedule:", "\n  push:", "\n  pull_request:"]
    for trigger in forbidden_triggers:
        require(trigger not in text, f"forbidden trigger present: {trigger.strip()}")
    require("permissions:\n  contents: read" in text, "workflow permissions must be contents read")
    require("timeout-minutes: 15" in text, "workflow timeout missing")
    require("concurrency:" in text, "workflow concurrency missing")
    require("acknowledge_single_run" in text, "acknowledgement input missing")
    require("timestamp:" in text and "YYYYMMDDHHMMSS" in text, "timestamp input missing")
    require("max_candidates:" in text, "max_candidates input missing")
    require("actions/checkout@v4" in text, "checkout major version mismatch")
    require("actions/setup-python@v5" in text, "setup-python major version mismatch")
    require("actions/upload-artifact@v4" in text, "artifact upload action missing")
    require("if: ${{ always() }}" in text, "artifact upload must run always")
    require("retention-days: 7" in text, "artifact retention mismatch")
    require("gdelt-webngrams-live-review-${{ github.run_id }}-${{ inputs.timestamp }}" in text, "review artifact name mismatch")
    require("probe_exit_code" in text and "Preserve live probe exit code" in text, "live probe exit code is not preserved")
    require("review_exit_code" in text, "live review exit code is not preserved")
    require("contract_exit_code" in text, "live contract exit code is not preserved")
    require("api.gdeltproject.org/api/v2/doc/doc" not in text, "DOC API endpoint must not appear in workflow")
    require("git push" not in lowered and "git commit" not in lowered and "git add" not in lowered, "workflow must not mutate repository")
    require("--timestamp \"${TIMESTAMP}\"" in text, "live probe must use the approved timestamp input")
    require("--max-candidates \"${MAX_CANDIDATES}\"" in text, "live probe must use max_candidates input")
    require("scripts/review_gdelt_webngrams_candidates.py" in text, "live candidate review step missing")
    require("--input-candidates \"${PROBE_DIR}/candidates.json\"" in text, "review must consume probe candidates")
    require("--input-probe-report \"${PROBE_DIR}/report.json\"" in text, "review must consume probe report")
    require("--source-mode live" in text, "review must run in live source mode")
    require("live_review_report.json" in text, "live review report contract missing")
    require("production_publish_allowed" in text, "production publish guard missing")
    require("grep -Eq '^[0-9]{14}$'" in text, "timestamp regex guard missing")
    require("ACKNOWLEDGE_SINGLE_RUN" in text and "must be true" in text, "acknowledgement guard missing")
    require("max_candidates must be between 1 and 100" in text, "max_candidates range guard missing")
    require("fallback" not in lowered, "workflow must not implement timestamp fallback")
    require("retry" not in lowered, "workflow must not implement retry")

    print("GDELT WEBNGRAMS WORKFLOW TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
