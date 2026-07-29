from __future__ import annotations

import json
from pathlib import Path

from scripts.company_change_operations_alert import handle_alert, issue_body
from src.company_change_operations import (
    FAILED,
    HEALTHY,
    WARNING,
    REQUIRED_ARTIFACTS,
    evaluate_operations,
    retention_days_for_run_kind,
    run_kind_from_event,
)


IDS = [
    "daeseung-engineering",
    "dl-enc",
    "geogwang-enterprise",
    "gs-ec",
    "hyundai-engineering",
    "kumkang-kind",
    "nrb",
    "planm",
    "samsung-ct-construction",
    "sungji-steel",
    "yuchang-enc",
]


def policy() -> dict:
    return {
        "version": 1,
        "timezone": "Asia/Seoul",
        "daily": {"cronUtc": "10 23 * * *", "lookbackDays": 2},
        "weekly": {"cronUtc": "40 23 * * 6", "lookbackDays": 30},
        "artifactRetentionDays": {"daily": 14, "weekly": 30, "manual": 30},
        "thresholds": {
            "expectedCompanyCount": 11,
            "pendingWarningCount": 3000,
            "candidateCountWarningIncreasePercent": 50,
            "sourceEmptyConsecutiveWarningRuns": 3,
            "naverOnlyConsecutiveWarningRuns": 3,
            "dartIdentityMappingCoverageWarningPercent": 80,
        },
    }


def source(source_id: str, *, state: str = "success_with_candidates", raw: int = 4, normalized: int = 4, attempted: bool = True) -> dict:
    return {
        "sourceId": source_id,
        "configured": True,
        "attempted": attempted,
        "state": state,
        "rawCount": raw,
        "normalizedCount": normalized,
        "latestPublishedAt": "2026-07-27" if normalized else None,
        "safeErrorCategory": "none",
        "companyResults": [
            {
                "companyId": company_id,
                "attempted": True,
                "state": "success_empty",
                "candidateCount": 0,
                "rawRecordCount": 0,
                "rejectedCount": 0,
                "safeErrorCategory": "none",
            }
            for company_id in IDS
        ],
    }


def queue_payload(**overrides) -> dict:
    payload = {
        "schemaVersion": "company-change-review-queue-v1",
        "runId": "test-run",
        "companies": IDS,
        "sources": ["public_news", "naver_api_hub", "dart"],
        "candidateCount": 12,
        "pending": 6,
        "duplicate": 2,
        "conflict": 1,
        "insufficientEvidence": 3,
        "rejected": 0,
        "highPriority": 1,
        "sourceStatuses": [
            source("public_news", raw=4, normalized=4),
            source("naver_api_hub", raw=4, normalized=4),
            source("dart", raw=4, normalized=4),
        ],
        "classificationDiagnostics": {"bySource": {"public_news": 4, "naver_api_hub": 4, "dart": 4}, "byCompany": {"gs-ec": 2}},
        "candidates": [],
    }
    payload.update(overrides)
    return payload


def audit_payload(**overrides) -> dict:
    payload = {
        "schemaVersion": "company-change-audit-v1",
        "valid": True,
        "companyCount": 11,
        "candidateCount": 12,
        "candidateIdUnique": True,
        "statusConservationPassed": True,
        "multiStatusCandidateCount": 0,
        "orphanDuplicateReferenceCount": 0,
        "orphanConflictReferenceCount": 0,
        "missingDuplicateOfCount": 0,
        "duplicateOfSelfCount": 0,
        "conflictSelfReferenceCount": 0,
        "duplicateReferenceCycleCount": 0,
        "crossCompanyContaminationCount": 0,
        "duplicateFingerprintErrors": 0,
        "invalidCandidateCount": 0,
        "deferredSourceStatusCount": 0,
        "unattemptedConfiguredSourceCount": 0,
        "publicReviewQueueExposureCount": 0,
        "daeseungContaminationCount": 0,
        "publicDataChanged": False,
        "secretExposureDetected": False,
    }
    payload.update(overrides)
    return payload


def make_root(tmp_path: Path, *, queue: dict | None = None, audit: dict | None = None) -> Path:
    root = tmp_path
    identities = root / "config/company_change_monitoring/company_identities.json"
    identities.parent.mkdir(parents=True, exist_ok=True)
    identities.write_text(json.dumps({"companies": [{"companyId": company_id} for company_id in IDS]}), encoding="utf-8")
    payloads = {
        "rawSummary": {"rawSignals": [], "sourceStatuses": (queue or queue_payload())["sourceStatuses"]},
        "normalized": {"normalizedSignals": []},
        "reviewQueue": queue or queue_payload(),
        "digest": {"statusCounts": {}, "publicDataChanged": False, "secretExposureDetected": False},
        "audit": audit or audit_payload(),
        "diagnostics": (queue or queue_payload())["classificationDiagnostics"],
    }
    for name, rel in REQUIRED_ARTIFACTS.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payloads[name]), encoding="utf-8")
    return root


def make_identity_root(tmp_path: Path) -> Path:
    root = tmp_path
    identities = root / "config/company_change_monitoring/company_identities.json"
    identities.parent.mkdir(parents=True, exist_ok=True)
    identities.write_text(json.dumps({"companies": [{"companyId": company_id} for company_id in IDS]}), encoding="utf-8")
    return root


def test_healthy_11_company_run_is_healthy(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    evaluation = evaluate_operations(root=root, policy=policy())
    assert evaluation["state"] == HEALTHY
    assert evaluation["companyScope"]["actualCount"] == 11
    assert evaluation["notes"][0]["code"] == "history_unavailable"


def test_source_attempted_false_fails(tmp_path: Path) -> None:
    queue = queue_payload(sourceStatuses=[source("naver_api_hub", attempted=False)])
    evaluation = evaluate_operations(root=make_root(tmp_path, queue=queue), policy=policy())
    assert evaluation["state"] == FAILED
    assert any(item["code"] == "configured_source_not_attempted" for item in evaluation["failures"])


def test_deferred_adapter_state_fails(tmp_path: Path) -> None:
    queue = queue_payload(sourceStatuses=[source("dart", state="configured_deferred_to_source_adapter", attempted=False)])
    audit = audit_payload(deferredSourceStatusCount=1, unattemptedConfiguredSourceCount=1)
    evaluation = evaluate_operations(root=make_root(tmp_path, queue=queue, audit=audit), policy=policy())
    assert evaluation["state"] == FAILED


def test_single_success_empty_is_not_failure(tmp_path: Path) -> None:
    queue = queue_payload(sourceStatuses=[source("public_news", state="success_empty", raw=0, normalized=0)])
    evaluation = evaluate_operations(root=make_root(tmp_path, queue=queue), policy=policy())
    assert evaluation["state"] == HEALTHY


def test_three_consecutive_source_empty_is_warning(tmp_path: Path) -> None:
    queue = queue_payload(sourceStatuses=[source("dart", state="success_empty", raw=0, normalized=0)])
    history = [
        {"sources": [source("dart", state="success_empty", raw=0, normalized=0)], "classificationDiagnostics": {"bySource": {"public_news": 1}}},
        {"sources": [source("dart", state="success_empty", raw=0, normalized=0)], "classificationDiagnostics": {"bySource": {"public_news": 1}}},
    ]
    evaluation = evaluate_operations(root=make_root(tmp_path, queue=queue), policy=policy(), history=history)
    assert evaluation["state"] == WARNING
    assert any(item["code"] == "source_empty_streak" for item in evaluation["warnings"])
    assert evaluation["alertRequired"] is True


def test_three_consecutive_naver_only_runs_warn(tmp_path: Path) -> None:
    queue = queue_payload(classificationDiagnostics={"bySource": {"naver_api_hub": 12}, "byCompany": {"gs-ec": 2}})
    history = [
        {"sources": [], "classificationDiagnostics": {"bySource": {"naver_api_hub": 8}}, "candidateCount": 8},
        {"sources": [], "classificationDiagnostics": {"bySource": {"naver_api_hub": 6}}, "candidateCount": 6},
    ]
    evaluation = evaluate_operations(root=make_root(tmp_path, queue=queue), policy=policy(), history=history)
    assert evaluation["state"] == WARNING
    assert any(item["code"] == "naver_only_streak" for item in evaluation["warnings"])


def test_company_count_mismatch_fails(tmp_path: Path) -> None:
    queue = queue_payload(companies=IDS[:-1])
    evaluation = evaluate_operations(root=make_root(tmp_path, queue=queue), policy=policy())
    assert evaluation["state"] == FAILED
    assert any(item["code"] == "company_scope_mismatch" for item in evaluation["failures"])


def test_missing_artifact_fails(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    (root / REQUIRED_ARTIFACTS["audit"]).unlink()
    evaluation = evaluate_operations(root=root, policy=policy())
    assert evaluation["state"] == FAILED
    assert any(item["code"] == "artifact_invalid" for item in evaluation["failures"])


def test_artifact_paths_none_uses_default_required_artifacts(tmp_path: Path) -> None:
    root = make_identity_root(tmp_path)
    evaluation = evaluate_operations(
        root=root,
        policy=policy(),
        queue=queue_payload(),
        audit=audit_payload(),
        diagnostics={},
        raw_summary={},
        normalized={},
        digest={},
        artifact_paths=None,
    )
    assert set(evaluation["artifacts"]) == set(REQUIRED_ARTIFACTS)
    assert evaluation["state"] == FAILED
    assert any(item["code"] == "artifact_invalid" for item in evaluation["failures"])


def test_artifact_paths_empty_map_disables_artifact_checking(tmp_path: Path) -> None:
    root = make_identity_root(tmp_path)
    evaluation = evaluate_operations(
        root=root,
        policy=policy(),
        queue=queue_payload(),
        audit=audit_payload(),
        diagnostics={},
        raw_summary={},
        normalized={},
        digest={},
        artifact_paths={},
    )
    assert evaluation["artifacts"] == {}
    assert not any(item["code"] == "artifact_invalid" for item in evaluation["failures"])
    assert evaluation["state"] == HEALTHY


def test_custom_artifact_paths_check_only_custom_map(tmp_path: Path) -> None:
    root = make_identity_root(tmp_path)
    custom_audit = root / "custom/audit.json"
    custom_audit.parent.mkdir(parents=True, exist_ok=True)
    custom_audit.write_text(json.dumps(audit_payload()), encoding="utf-8")
    evaluation = evaluate_operations(
        root=root,
        policy=policy(),
        queue=queue_payload(),
        audit=audit_payload(),
        diagnostics={},
        raw_summary={},
        normalized={},
        digest={},
        artifact_paths={"audit": "custom/audit.json"},
    )
    assert set(evaluation["artifacts"]) == {"audit"}
    assert evaluation["artifacts"]["audit"]["parseable"] is True
    assert not any(item["code"] == "artifact_invalid" for item in evaluation["failures"])

    missing = evaluate_operations(
        root=root,
        policy=policy(),
        queue=queue_payload(),
        audit=audit_payload(),
        diagnostics={},
        raw_summary={},
        normalized={},
        digest={},
        artifact_paths={"audit": "custom/missing-audit.json"},
    )
    assert set(missing["artifacts"]) == {"audit"}
    assert any(item["code"] == "artifact_invalid" and item["artifact"] == "audit" for item in missing["failures"])


def test_status_conservation_failure_fails(tmp_path: Path) -> None:
    queue = queue_payload(candidateCount=99)
    audit = audit_payload(statusConservationPassed=False)
    evaluation = evaluate_operations(root=make_root(tmp_path, queue=queue, audit=audit), policy=policy())
    assert evaluation["state"] == FAILED


def test_audit_integrity_and_protection_failures(tmp_path: Path) -> None:
    audit = audit_payload(candidateIdUnique=False, crossCompanyContaminationCount=1, publicDataChanged=True, secretExposureDetected=True)
    evaluation = evaluate_operations(root=make_root(tmp_path, audit=audit), policy=policy())
    codes = {item["code"] for item in evaluation["failures"]}
    assert {"candidateIdUnique", "crossCompanyContaminationCount", "public_data_changed", "secret_exposure_detected"}.issubset(codes)


def test_proposal_generated_fails(tmp_path: Path) -> None:
    evaluation = evaluate_operations(root=make_root(tmp_path), policy=policy(), run_metadata={"proposalGenerated": True})
    assert evaluation["state"] == FAILED
    assert any(item["code"] == "proposal_generated" for item in evaluation["failures"])


def test_retention_and_schedule_mapping() -> None:
    p = policy()
    assert run_kind_from_event("schedule", "10 23 * * *", p) == "daily"
    assert run_kind_from_event("schedule", "40 23 * * 6", p) == "weekly"
    assert run_kind_from_event("workflow_dispatch", None, p) == "manual"
    assert retention_days_for_run_kind("daily", p) == 14
    assert retention_days_for_run_kind("weekly", p) == 30
    assert retention_days_for_run_kind("manual", p) == 30


class FakeIssueClient:
    def __init__(self, existing: dict | None = None) -> None:
        self.existing = existing
        self.created: list[dict] = []
        self.comments: list[tuple[int, str]] = []
        self.closed: list[int] = []

    def search_open(self, marker: str) -> dict | None:
        return self.existing

    def create(self, title: str, body: str, labels: list[str]) -> dict:
        item = {"number": 7, "html_url": "https://example/issues/7", "title": title, "body": body, "labels": labels}
        self.created.append(item)
        return item

    def comment(self, number: int, body: str) -> None:
        self.comments.append((number, body))

    def close(self, number: int, body: str) -> None:
        self.closed.append(number)

    def ensure_labels(self, labels: list[str]) -> None:
        self.labels = labels


def test_issue_dedupe_updates_existing_issue(tmp_path: Path) -> None:
    evaluation = evaluate_operations(root=make_root(tmp_path, audit=audit_payload(publicDataChanged=True)), policy=policy())
    client = FakeIssueClient(existing={"number": 3, "html_url": "https://example/issues/3"})
    result = handle_alert(evaluation, client)
    assert result["action"] == "issue_updated"
    assert result["duplicatePrevented"] is True
    assert client.comments


def test_recovery_closes_existing_issue(tmp_path: Path) -> None:
    evaluation = evaluate_operations(root=make_root(tmp_path), policy=policy())
    client = FakeIssueClient(existing={"number": 3, "html_url": "https://example/issues/3"})
    result = handle_alert(evaluation, client)
    assert result["action"] == "recovery_closed"
    assert client.closed == [3]


def test_issue_body_does_not_include_secret_terms(tmp_path: Path) -> None:
    evaluation = evaluate_operations(root=make_root(tmp_path, audit=audit_payload(publicDataChanged=True)), policy=policy())
    body = issue_body(evaluation)
    blocked = ["DART_API_KEY", "NAVER_API_HUB_CLIENT_SECRET", "Authorization", "request_headers", "raw_response"]
    assert not any(item in body for item in blocked)


def test_company_change_workflow_contract() -> None:
    text = Path(".github/workflows/company-change-monitor.yml").read_text(encoding="utf-8")
    assert 'cron: "10 23 * * *"' in text
    assert 'cron: "40 23 * * 6"' in text
    assert "publish:" not in text.split("workflow_dispatch:", 1)[1].split("concurrency:", 1)[0]
    assert "PUBLISH=\"false\"" in text
    assert "contents: write" not in text
    assert "pull-requests: write" not in text
    assert "issues: write" in text
    assert "Evaluate operations" in text and "if: always()" in text
    assert "Publish operations alert" in text
    assert "Build source contribution history and concentration diagnostics" in text
    assert text.index("Audit source coverage") < text.index("Build source contribution history and concentration diagnostics")
    assert text.index("Build source contribution history and concentration diagnostics") < text.index("Evaluate operations")
    assert text.index("Evaluate operations") < text.index("Write summary")
    assert text.index("company-change-classification-diagnostics") < text.index("Final acceptance gate")
    for name in [
        "company-change-raw-summary",
        "company-change-normalized",
        "company-change-review-queue",
        "company-change-digest",
        "company-change-audit",
        "company-change-classification-diagnostics",
        "company-source-contribution-history",
        "company-source-concentration-diagnostics",
    ]:
        assert name in text
    assert "source-contribution-history.json" in text
    assert "source-concentration-diagnostics.json" in text
    assert "frontend/public/data/news.json" in text
    assert "git diff --exit-code -- frontend/public/data/news.json" in text
