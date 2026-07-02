from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "verify-gdelt-webngrams-live.yml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def production_doc_api_check_targets(workflow_text: str) -> list[str]:
    match = re.search(r"production_files\s*=\s*(\[[^\]]+\])", workflow_text, re.S)
    require(match is not None, "production_files list missing from DOC API preflight check")
    value = ast.literal_eval(match.group(1))
    require(isinstance(value, list) and all(isinstance(item, str) for item in value), "production_files must be a string list")
    return value


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
    require("type: boolean" in text, "acknowledge input must stay boolean")
    require("required: true" in text, "required input contract missing")
    require("default: false" in text, "acknowledge default must be false")
    require("inputs.acknowledge_single_run == true" in text, "boolean approval must use inputs context")
    require("github.event.inputs.acknowledge_single_run" not in text, "github.event.inputs must not drive boolean approval")
    require("ACKNOWLEDGE_SINGLE_RUN_NORMALIZED" in text, "normalized acknowledgement env missing")
    require("timestamp:" in text and "YYYYMMDDHHMMSS" in text, "timestamp input missing")
    require("max_candidates:" in text, "max_candidates input missing")
    require("actions/checkout@v7" in text, "checkout major version mismatch")
    require("actions/setup-python@v6" in text, "setup-python major version mismatch")
    require("actions/upload-artifact@v7" in text, "artifact upload action missing")
    require("Initialize run control artifact" in text, "run control initialization missing")
    require("run_control.json" in text, "run control artifact missing")
    require("failure_report.json" in text and "failure_report.md" in text, "validation failure report missing")
    require("manual_approval_missing" in text, "manual approval failure type missing")
    require("timestamp_invalid" in text, "timestamp failure type missing")
    require("max_candidates_invalid" in text, "max_candidates failure type missing")
    require("preflight_failed" in text, "preflight failure type missing")
    require("preflight_exit_code" in text and "PREFLIGHT_EXIT_CODE" in text, "preflight exit code must be reported")
    require("if: ${{ always() }}" in text, "artifact upload must run always")
    require("retention-days: 7" in text, "artifact retention mismatch")
    require("if-no-files-found: error" in text, "artifact upload must fail when run_control is absent")
    require("gdelt-webngrams-live-review-${{ github.run_id }}-${{ inputs.timestamp }}" in text, "review artifact name mismatch")
    require("probe_exit_code" in text and "Preserve live verification exit code" in text, "live probe exit code is not preserved")
    require("continue-on-error: true" not in text, "live probe should not need continue-on-error after preserving probe_exit_code")
    require("GDELT live probe failed" in text, "live probe failure annotation missing")
    require('exit "$code"' not in text, "live probe step must continue to artifact upload after saving probe_exit_code")
    require("exit 0" in text, "live probe step must exit zero after recording probe_exit_code")
    require("validation_exit_code" in text, "validation exit code is not preserved")
    require("dependency_exit_code" in text, "dependency exit code is not preserved")
    require("preflight_exit_code" in text, "preflight exit code is not preserved")
    require("review_exit_code" in text, "live review exit code is not preserved")
    require("contract_exit_code" in text, "live contract exit code is not preserved")
    require("api.gdeltproject.org/api/v2/doc/doc" not in text, "DOC API endpoint must not appear in workflow")
    production_targets = production_doc_api_check_targets(text)
    require(production_targets == ["scripts/probe_gdelt_webngrams.py"], "DOC API preflight must check only production probe files")
    require("scripts/test_gdelt_webngrams_probe.py" not in production_targets, "DOC API preflight must not scan negative assertion tests")
    endpoint = "api.gdeltproject.org/api/v2/doc/doc"
    for target in production_targets:
        require(endpoint not in (ROOT / target).read_text(encoding="utf-8"), f"DOC API endpoint leaked into production file: {target}")
    require(endpoint in (ROOT / "scripts" / "test_gdelt_webngrams_probe.py").read_text(encoding="utf-8"), "negative assertion test fixture should be allowed to mention DOC API endpoint")
    require("git push" not in lowered and "git commit" not in lowered and "git add" not in lowered, "workflow must not mutate repository")
    require("--timestamp \"${TIMESTAMP}\"" in text, "live probe must use the approved timestamp input")
    require("--max-candidates \"${MAX_CANDIDATES}\"" in text, "live probe must use max_candidates input")
    require("scripts/review_gdelt_webngrams_candidates.py" in text, "live candidate review step missing")
    require("--input-candidates \"${PROBE_DIR}/candidates.json\"" in text, "review must consume probe candidates")
    require("--input-probe-report \"${PROBE_DIR}/report.json\"" in text, "review must consume probe report")
    require("--source-mode live" in text, "review must run in live source mode")
    require("live_review_report.json" in text, "live review report contract missing")
    require("hashFiles('artifacts/global_news_webngrams_probe/report.json') != ''" in text, "review must require probe report")
    require("steps.live_probe.outputs.probe_exit_code == '0'" in text, "review must require successful live probe exit code")
    require("hashFiles('artifacts/global_news_webngrams_probe/candidates.json') != ''" in text, "review must require probe candidates")
    require("transport_acceptance_passed must be true before live candidate review" in text, "review must require transport acceptance")
    require("hashFiles('artifacts/global_news_webngrams_review/live_review_report.json') != ''" in text, "contract must require review report")
    require("steps.live_review.outputs.review_exit_code == '0'" in text, "contract must require successful review exit code")
    require("production_publish_allowed" in text, "production publish guard missing")
    require('re.fullmatch(r"[0-9]{14}", timestamp)' in text, "timestamp regex guard missing")
    require("acknowledge_single_run must be true" in text, "acknowledgement guard missing")
    require("max_candidates must be between 1 and 100" in text, "max_candidates range guard missing")
    require("not_evaluated" in text, "summary must support not_evaluated state")
    require("Failure Type:" in text, "summary must report failure type")
    require("Failed Source:" in text, "summary must report failed source")
    require("Request Attempts:" in text and "HTTP Responses:" in text, "summary must report request attempt and response counts")
    for summary_field in [
        "Transport Scheme:",
        "Transport Security:",
        "Endpoint Contract Valid:",
        "Redirect Received:",
        "Redirect Followed:",
        "Compressed SHA-256:",
        "Compressed Bytes:",
        "Decompressed Bytes:",
        "Source Integrity Checks Passed:",
    ]:
        require(summary_field in text, f"summary field missing: {summary_field}")
    require("Retry count: `0`" in text, "summary must report retry count zero")
    require("Fallback count: `0`" in text, "summary must report fallback count zero")
    require("--retry" not in lowered and "max-attempts" not in lowered, "workflow must not implement request retry")
    require("fallback timestamp" not in lowered and "fallback_timestamp" not in lowered, "workflow must not implement timestamp fallback")
    forbidden_ssl_patterns = [
        "verify=false",
        "session.verify = false",
        "urllib3.disable_warnings",
        "pythonhttpsverify=0",
        "requests_ca_bundle=\"\"",
        "curl_ca_bundle=\"\"",
    ]
    for pattern in forbidden_ssl_patterns:
        require(pattern not in lowered, f"forbidden SSL bypass pattern present: {pattern}")

    print("GDELT WEBNGRAMS WORKFLOW TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
