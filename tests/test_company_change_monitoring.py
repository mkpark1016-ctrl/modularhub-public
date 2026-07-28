from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.company_change_monitoring import (
    CANDIDATE_STATUSES,
    CONFIDENCE_VALUES,
    NEWS_PATH,
    RISK_LEVELS,
    REVIEW_QUEUE_PATH,
    ROOT,
    audit_proposal_manifest,
    audit_change_run,
    build_proposal_manifest,
    build_change_monitor_run,
    candidate_fingerprint,
    classify_signal,
    dedupe_and_conflict,
    identity_score,
    issue_fingerprint,
    link_research_gaps,
    load_identity_policies,
    load_source_policy,
    repo_relative_posix,
    review_queue_payload,
    source_configured,
    valid_patent_transition,
    valid_project_transition,
)
from src.company_data_quality import load_public_company_universe
import src.company_change_monitoring as change_monitoring


def policy(company_id: str):
    return next(item for item in load_identity_policies() if item.company_id == company_id)


def company_map() -> dict[str, dict]:
    return {item["company_id"]: item for item in load_public_company_universe()}


def workflow_text() -> str:
    return Path(".github/workflows/company-change-monitor.yml").read_text(encoding="utf-8")


def test_identity_policy_covers_current_11_companies() -> None:
    companies = company_map()
    identities = {item.company_id for item in load_identity_policies()}
    assert len(companies) == 11
    assert identities == set(companies)


def test_positive_alias_and_modular_keyword_scores_identity() -> None:
    result = identity_score(policy("kumkang-kind"), "금강공업 모듈러 학교 계약", "스틸 모듈러 수주", "")
    assert result["score"] >= 0.65
    assert result["rejected"] is False


def test_company_name_only_is_not_enough_for_change_evidence() -> None:
    result = identity_score(policy("kumkang-kind"), "금강공업 채용 공고", "일반 채용 안내", "")
    assert result["rejected"] is True


def test_daeseung_same_name_contamination_is_rejected() -> None:
    result = identity_score(
        policy("daeseung-engineering"),
        "김해 대승엔지니어링 최병천 대표 수처리 제진기 설비",
        "자동차 부품과 무관한 수처리 업체",
        "",
    )
    assert result["rejected"] is True
    assert result["reason"] == "excluded_entity"


def test_source_policy_defines_required_groups_and_schedule() -> None:
    payload = load_source_policy()
    source_ids = {row["sourceId"] for row in payload["sources"]}
    assert {"dart", "naver_api_hub", "public_news", "public_procurement", "patent"}.issubset(source_ids)
    assert payload["modes"]["daily_signals"] == ["dart", "naver_api_hub", "public_news"]


def test_company_change_workflow_is_permanently_read_only() -> None:
    text = workflow_text()
    dispatch_block = text.split("concurrency:", 1)[0]
    assert "\n      publish:" not in dispatch_block
    assert "inputs.publish" not in text
    assert 'PUBLISH="false"' in text
    assert "--publish" not in text
    assert "frontend/public/data/company-intelligence" not in text


def test_company_change_workflow_uses_explicit_boolean_guards() -> None:
    text = workflow_text()
    assert 'ACKNOWLEDGE_LIVE="${{ inputs.acknowledge_live }}"' in text
    assert 'CREATE_PROPOSAL="${{ inputs.create_proposal }}"' in text
    assert 'ACKNOWLEDGE_PROPOSAL="${{ inputs.acknowledge_proposal }}"' in text
    assert '"$CREATE_PROPOSAL" == "true"' in text
    assert '"$ACKNOWLEDGE_PROPOSAL" != "true"' in text
    assert '"$ACKNOWLEDGE_LIVE" != "true"' in text
    assert '[ "$ACKNOWLEDGE_LIVE" ]' not in text
    assert '[ "$CREATE_PROPOSAL" ]' not in text
    assert '[ "$ACKNOWLEDGE_PROPOSAL" ]' not in text


def test_company_change_workflow_summary_prints_safe_flags_only() -> None:
    text = workflow_text()
    assert "acknowledge_live:" in text
    assert "publish: $PUBLISH" in text
    assert "create_proposal:" in text
    assert "acknowledge_proposal:" in text
    assert "DART_API_KEY configured:" in text
    assert "NAVER_API_HUB_CLIENT_ID configured:" in text
    assert "NAVER_API_HUB_CLIENT_SECRET configured:" in text
    assert "printenv" not in text
    assert "env |" not in text


def test_company_change_workflow_installs_python_test_dependencies_before_pytest() -> None:
    text = workflow_text()
    assert "cache: pip" in text
    assert "requirements-dev.txt" in text
    assert "Install Python dependencies" in text
    assert "python -m pip install -r requirements-dev.txt" in text
    assert "python -m pip show pytest" in text
    assert "Run company change monitoring tests" in text
    assert text.index("Install Python dependencies") < text.index("Run company change monitoring tests")
    assert text.index("python -m pip show pytest") < text.index("python -m pytest")


def test_company_change_workflow_names_live_collection_step() -> None:
    text = workflow_text()
    assert "Collect live company change sources and build review queue" in text
    assert 'CREATE_PROPOSAL="${{ steps.guard.outputs.create_proposal }}"' in text
    assert 'ACKNOWLEDGE_PROPOSAL="${{ steps.guard.outputs.acknowledge_proposal }}"' in text
    assert "ARGS+=(--create-proposal)" in text
    assert "ARGS+=(--acknowledge-proposal)" in text
    assert "attempted=" in text
    assert "safeErrorCategory" in text
    assert "company-change-classification-diagnostics" in text
    assert "company-change-proposal" in text
    assert "artifacts/company-change-monitor/proposal-manifest.json" in text
    assert "company-source-contribution-history" in text
    assert "company-source-concentration-diagnostics" in text
    assert "Final acceptance gate" in text
    assert "if: always()" in text


def test_dev_requirements_include_runtime_requirements_and_pytest() -> None:
    text = Path("requirements-dev.txt").read_text(encoding="utf-8")
    assert "-r requirements.txt" in text
    assert "pytest" in text


def test_source_configured_never_uses_secret_values(monkeypatch) -> None:
    monkeypatch.setenv("NAVER_API_HUB_CLIENT_ID", "dummy")
    monkeypatch.setenv("NAVER_API_HUB_CLIENT_SECRET", "dummy")
    assert source_configured("naver_api_hub") is True
    monkeypatch.delenv("NAVER_API_HUB_CLIENT_SECRET")
    assert source_configured("naver_api_hub") is False


def test_signal_classification_separates_project_mou_patent_and_news() -> None:
    assert classify_signal("금강공업 모듈러 학교 수주")["signalType"] == "contract_awarded"
    assert classify_signal("유창이앤씨 업무협약 체결")["signalType"] == "partnership"
    assert classify_signal("대승엔지니어링 특허 등록")["signalType"] == "patent_filed"
    assert classify_signal("모듈러 산업 동향")["signalType"] == "modular_strategy"


def test_public_news_run_builds_private_candidates_without_publication() -> None:
    run = build_change_monitor_run(companies=["kumkang-kind", "yuchang-enc", "daeseung-engineering"], sources=["public_news"], lookback_days=30)
    assert run["companies"] == ["yuchang-enc", "kumkang-kind", "daeseung-engineering"]
    assert run["publish"] is False
    assert run["publicDataChanged"] is False
    assert run["candidateCount"] >= 0
    for candidate in run["candidates"]:
        assert candidate["status"] in CANDIDATE_STATUSES
        assert candidate["confidence"] in CONFIDENCE_VALUES
        assert candidate["riskLevel"] in RISK_LEVELS
        assert candidate["requiresHumanReview"] is True
        assert candidate["sourceIds"]


def test_live_configured_sources_are_attempted_instead_of_deferred(monkeypatch) -> None:
    def fake_naver(policies, *, fetched_at=None):
        return {
            "sourceId": "naver_api_hub",
            "configured": True,
            "attempted": True,
            "state": "success_empty",
            "raw": [],
            "normalized": [],
            "rejected": [],
            "latestPublishedAt": None,
            "safeErrorCategory": "none",
            "companyResults": [{"companyId": policy.company_id, "attempted": True, "state": "success_empty"} for policy in policies],
        }

    def fake_dart(policies, *, lookback_days=30, fetched_at=None):
        return {
            "sourceId": "dart",
            "configured": True,
            "attempted": True,
            "state": "success_empty",
            "raw": [],
            "normalized": [],
            "rejected": [],
            "latestPublishedAt": None,
            "safeErrorCategory": "none",
            "companyResults": [{"companyId": policy.company_id, "attempted": True, "state": "success_empty"} for policy in policies],
        }

    monkeypatch.setenv("NAVER_API_HUB_CLIENT_ID", "configured")
    monkeypatch.setenv("NAVER_API_HUB_CLIENT_SECRET", "configured")
    monkeypatch.setenv("DART_API_KEY", "configured")
    monkeypatch.setattr(change_monitoring, "collect_naver_api_hub_signals", fake_naver)
    monkeypatch.setattr(change_monitoring, "collect_dart_signals", fake_dart)

    run = build_change_monitor_run(
        companies=["gs-ec", "yuchang-enc", "daeseung-engineering"],
        sources=["public_news", "naver_api_hub", "dart"],
        lookback_days=30,
        live=True,
        acknowledge_live=True,
    )
    statuses = {source["sourceId"]: source for source in run["sourceStatuses"]}
    assert statuses["naver_api_hub"]["attempted"] is True
    assert statuses["dart"]["attempted"] is True
    assert statuses["naver_api_hub"]["state"] != "configured_deferred_to_source_adapter"
    assert statuses["dart"]["state"] != "configured_deferred_to_source_adapter"
    assert audit_change_run(run)["valid"] is True


def test_audit_rejects_deferred_configured_source_status() -> None:
    run = build_change_monitor_run(companies=["kumkang-kind"], sources=["public_news"], lookback_days=30)
    run["sources"] = ["naver_api_hub"]
    run["sourceStatuses"] = [
        {
            "sourceId": "naver_api_hub",
            "configured": True,
            "attempted": False,
            "state": "configured_deferred_to_source_adapter",
            "rawCount": 0,
            "normalizedCount": 0,
            "identityRejected": 0,
            "latestPublishedAt": None,
            "safeErrorCategory": "none",
        }
    ]
    summary = audit_change_run(run)
    assert summary["deferredSourceStatusCount"] == 1
    assert summary["unattemptedConfiguredSourceCount"] == 1
    assert summary["valid"] is False


def test_review_queue_payload_keeps_candidates_internal() -> None:
    run = build_change_monitor_run(companies=["kumkang-kind"], sources=["public_news"], lookback_days=30)
    queue = review_queue_payload(run)
    assert queue["schemaVersion"] == "company-change-review-queue-v1"
    assert "candidates" in queue
    assert queue["candidateCount"] == len(queue["candidates"])
    assert repo_relative_posix(REVIEW_QUEUE_PATH) == "data/company_change_monitoring/review_queue.json"
    assert "frontend/public" not in repo_relative_posix(REVIEW_QUEUE_PATH)
    for candidate in queue["candidates"]:
        assert "publicOutputPath" not in candidate
        assert "publishPath" not in candidate
        assert "exportPath" not in candidate


def test_public_news_snapshot_provenance_is_allowed() -> None:
    run = build_change_monitor_run(companies=["kumkang-kind"], sources=["public_news"], lookback_days=30)
    public_news = next(source for source in run["sourceStatuses"] if source["sourceId"] == "public_news")
    assert public_news["diagnostics"]["snapshotPath"] == "frontend/public/data/news.json"
    assert public_news["diagnostics"]["snapshotPath"] == repo_relative_posix(NEWS_PATH)


def test_review_queue_is_not_copied_to_public_bundle() -> None:
    public_files = [path.relative_to(ROOT).as_posix() for path in (ROOT / "frontend" / "public").rglob("*") if path.is_file()]
    blocked_names = {"review_queue.json", "company-change-review-queue.json"}
    assert not any(Path(path).name in blocked_names for path in public_files)
    assert not any("company-change-review-queue-v1" in (ROOT / path).read_text(encoding="utf-8", errors="ignore") for path in public_files)


def test_repository_paths_are_serialized_as_posix() -> None:
    run = build_change_monitor_run(companies=["kumkang-kind"], sources=["public_news"], lookback_days=30)
    public_news = next(source for source in run["sourceStatuses"] if source["sourceId"] == "public_news")
    assert public_news["diagnostics"]["snapshotPath"] == "frontend/public/data/news.json"
    assert "\\" not in public_news["diagnostics"]["snapshotPath"]
    assert repo_relative_posix(REVIEW_QUEUE_PATH) == "data/company_change_monitoring/review_queue.json"


def test_proposal_guard_requires_acknowledgement() -> None:
    with pytest.raises(ValueError):
        build_change_monitor_run(create_proposal=True, acknowledge_proposal=False)
    run = build_change_monitor_run(companies=["kumkang-kind"], sources=["public_news"], create_proposal=True, acknowledge_proposal=True)
    assert run["proposal"]["guard"] == "acknowledge_proposal_required"
    assert run["proposal"]["acknowledgeProposal"] is True
    assert run["proposal"]["created"] is False


def proposal_run(candidates: list[dict], *, create: bool = False, acknowledge: bool = False) -> dict:
    return {
        "generatedAt": "2026-07-28T00:00:00Z",
        "runId": "run-proposal-test",
        "mode": "daily_signals",
        "companies": ["kumkang-kind", "yuchang-enc"],
        "sources": ["public_news", "naver_api_hub"],
        "candidates": candidates,
        "proposal": {
            "createProposal": create,
            "acknowledgeProposal": acknowledge,
            "created": False,
        },
    }


def eligible_proposal_candidate(candidate_id: str, **overrides) -> dict:
    candidate = change_candidate(candidate_id)
    candidate.update(
        {
            "confidence": "high",
            "priority": "high",
            "riskLevel": "critical",
            "sourceTiers": ["tier_1"],
            "requiresHumanReview": True,
            "evidenceKey": f"url:https://news.example/{candidate_id}",
        }
    )
    candidate.update(overrides)
    return candidate


def test_proposal_manifest_unrequested_is_empty() -> None:
    manifest = build_proposal_manifest(proposal_run([eligible_proposal_candidate("eligible")]))

    assert manifest["requested"] is False
    assert manifest["acknowledged"] is False
    assert manifest["created"] is False
    assert manifest["reason"] == "not_requested"
    assert manifest["selectedCount"] == 0
    assert manifest["items"] == []
    assert audit_proposal_manifest(manifest) == []


def test_proposal_manifest_requested_and_acknowledged_selects_only_eligible_candidates() -> None:
    candidates = [
        eligible_proposal_candidate("medium-confidence", confidence="medium"),
        eligible_proposal_candidate("duplicate", status="duplicate", duplicateOf="eligible-low"),
        eligible_proposal_candidate("conflict", status="conflict", conflictsWith=["eligible-low"]),
        eligible_proposal_candidate("insufficient", status="insufficient_evidence"),
        eligible_proposal_candidate("no-evidence", proposedValue={"title": "No evidence", "url": ""}, evidenceKey=""),
        eligible_proposal_candidate("eligible-low", priority="low", riskLevel="low", companyId="yuchang-enc"),
        eligible_proposal_candidate("eligible-high", priority="high", riskLevel="high", companyId="kumkang-kind"),
        eligible_proposal_candidate("eligible-critical", priority="high", riskLevel="critical", companyId="kumkang-kind"),
    ]

    manifest = build_proposal_manifest(proposal_run(candidates, create=True, acknowledge=True), max_items=20)

    assert manifest["created"] is True
    assert manifest["reason"] == "proposal_manifest_created"
    assert manifest["eligibleCount"] == 3
    assert [item["candidateId"] for item in manifest["items"]] == ["eligible-critical", "eligible-high", "eligible-low"]
    assert manifest["selectedCount"] == 3
    assert all(set(item) == set(change_monitoring.PROPOSAL_ITEM_FIELDS) for item in manifest["items"])
    assert "fingerprint" not in json.dumps(manifest, ensure_ascii=False)
    assert "review_queue.json" not in json.dumps(manifest, ensure_ascii=False)
    assert audit_proposal_manifest(manifest) == []


def test_proposal_manifest_caps_selected_items_at_twenty() -> None:
    candidates = [eligible_proposal_candidate(f"eligible-{index:02d}") for index in range(25)]

    manifest = build_proposal_manifest(proposal_run(candidates, create=True, acknowledge=True), max_items=20)

    assert manifest["eligibleCount"] == 25
    assert manifest["selectedCount"] == 20
    assert len(manifest["items"]) == 20
    assert audit_proposal_manifest(manifest) == []


def test_proposal_manifest_no_eligible_candidates_is_noop() -> None:
    manifest = build_proposal_manifest(
        proposal_run([eligible_proposal_candidate("low", confidence="low")], create=True, acknowledge=True)
    )

    assert manifest["requested"] is True
    assert manifest["acknowledged"] is True
    assert manifest["created"] is False
    assert manifest["reason"] == "no_eligible_candidates"
    assert manifest["eligibleCount"] == 0
    assert manifest["items"] == []
    assert audit_proposal_manifest(manifest) == []


def test_proposal_manifest_security_scan_blocks_sensitive_strings() -> None:
    manifest = build_proposal_manifest(proposal_run([eligible_proposal_candidate("eligible")], create=True, acknowledge=True))
    serialized = json.dumps(manifest, ensure_ascii=False)
    for blocked in [
        "DART_API_KEY=",
        "NAVER_API_HUB_CLIENT_SECRET=",
        "Authorization:",
        "request_headers",
        "raw_response",
        "review_queue.json",
    ]:
        assert blocked not in serialized

    manifest["items"][0]["evidenceSummary"] = "raw_response"
    assert "proposal_sensitive_content" in audit_proposal_manifest(manifest)


def test_publish_guard_blocks_public_update() -> None:
    with pytest.raises(ValueError):
        build_change_monitor_run(publish=True)


def change_candidate(
    candidate_id: str,
    *,
    company_id: str = "kumkang-kind",
    field_path: str = "recent_signals",
    fingerprint: str | None = None,
    status: str = "pending",
    change_type: str = "freshness_update",
    signal_type: str = "modular_strategy",
    entity_type: str = "news",
    entity_key: str = "entity-a",
    effective_at: str = "2026-07-22",
    proposed_value: dict | None = None,
) -> dict:
    proposed_value = proposed_value or {"title": candidate_id, "url": f"https://news.example/{candidate_id}"}
    fingerprint = fingerprint or candidate_fingerprint(company_id, change_type, field_path, proposed_value, effective_at, "public_news", entity_key=entity_key)
    return {
        "candidateId": candidate_id,
        "companyId": company_id,
        "fieldPath": field_path,
        "changeType": change_type,
        "signalType": signal_type,
        "entityType": entity_type,
        "entityKey": entity_key,
        "effectiveAt": effective_at,
        "proposedValue": proposed_value,
        "comparisonValue": proposed_value,
        "fingerprint": fingerprint,
        "status": status,
        "duplicateOf": None,
        "conflictsWith": [],
        "confidence": "medium",
        "riskLevel": "low",
        "evidenceSummary": proposed_value.get("title"),
        "sourceIds": ["public_news"],
    }


def test_same_canonical_url_is_duplicate_without_candidate_id_collision() -> None:
    proposed = {"title": "First title", "url": "https://news.example/path?utm_source=test"}
    duplicate_proposed = {"title": "Second title", "url": "https://news.example/path"}
    first = change_candidate("c1", proposed_value=proposed)
    second = change_candidate("c2", proposed_value=duplicate_proposed)
    first["fingerprint"] = candidate_fingerprint("kumkang-kind", "freshness_update", "recent_signals", proposed, "2026-07-22", "public_news", entity_key="https://news.example/path")
    second["fingerprint"] = first["fingerprint"]

    result = dedupe_and_conflict([first, second])

    assert result[0]["status"] == "pending"
    assert result[1]["status"] == "duplicate"
    assert result[1]["duplicateOf"] == "c1"
    assert result[0]["candidateId"] != result[1]["candidateId"]


def test_missing_url_same_title_and_date_is_duplicate() -> None:
    proposed = {"title": "Modular school contract", "url": ""}
    first = change_candidate("title-a", proposed_value=proposed, entity_key="modular school contract")
    second = change_candidate("title-b", proposed_value=proposed, entity_key="modular school contract")
    result = dedupe_and_conflict([first, second])
    assert result[0]["status"] == "pending"
    assert result[1]["status"] == "duplicate"
    assert result[1]["duplicateOf"] == "title-a"


def test_distinct_news_same_company_are_not_conflicts() -> None:
    result = dedupe_and_conflict(
        [
            change_candidate("news-a", proposed_value={"title": "A", "url": "https://news.example/a"}, entity_key="https://news.example/a"),
            change_candidate("news-b", proposed_value={"title": "B", "url": "https://news.example/b"}, entity_key="https://news.example/b"),
        ]
    )
    assert [candidate["status"] for candidate in result] == ["pending", "pending"]
    assert all(not candidate["conflictsWith"] for candidate in result)


def test_same_url_different_company_is_not_cross_company_duplicate() -> None:
    proposed = {"title": "Shared article", "url": "https://news.example/shared"}
    result = dedupe_and_conflict(
        [
            change_candidate("a", company_id="kumkang-kind", proposed_value=proposed, entity_key="https://news.example/shared"),
            change_candidate("b", company_id="yuchang-enc", proposed_value=proposed, entity_key="https://news.example/shared"),
        ]
    )
    assert [candidate["status"] for candidate in result] == ["pending", "pending"]


def test_independent_projects_patents_and_facilities_are_not_conflicts() -> None:
    result = dedupe_and_conflict(
        [
            change_candidate("project-a", field_path="project_portfolio", change_type="new_record", signal_type="contract_awarded", entity_type="project", entity_key="project-a"),
            change_candidate("project-b", field_path="project_portfolio", change_type="new_record", signal_type="contract_awarded", entity_type="project", entity_key="project-b"),
            change_candidate("patent-a", field_path="technology", change_type="new_record", signal_type="patent_filed", entity_type="technology", entity_key="patent-a"),
            change_candidate("facility-a", field_path="production", change_type="new_record", signal_type="facility_opened", entity_type="facility", entity_key="facility-a"),
        ]
    )
    assert all(candidate["status"] == "pending" for candidate in result)
    assert all(not candidate["conflictsWith"] for candidate in result)


def test_real_financial_value_conflict_uses_same_scope() -> None:
    first = change_candidate(
        "financial-a",
        field_path="financials",
        change_type="new_value",
        signal_type="financial_filing",
        entity_type="financial",
        entity_key="2025-revenue",
        proposed_value={"year": 2025, "revenue": 100},
    )
    second = change_candidate(
        "financial-b",
        field_path="financials",
        change_type="new_value",
        signal_type="financial_filing",
        entity_type="financial",
        entity_key="2025-revenue",
        proposed_value={"year": 2025, "revenue": 200},
    )
    first["fingerprint"] = "financial-a"
    second["fingerprint"] = "financial-b"

    result = dedupe_and_conflict([first, second])

    assert result[0]["status"] == "pending"
    assert result[1]["status"] == "conflict"
    assert result[1]["conflictsWith"] == ["financial-a"]


def test_repeated_same_base_candidate_id_is_made_unique() -> None:
    first = change_candidate("same-id", fingerprint="same")
    second = change_candidate("same-id", fingerprint="same")
    result = dedupe_and_conflict([first, second])
    assert result[0]["candidateId"] != result[1]["candidateId"]
    assert result[1]["status"] == "duplicate"
    assert result[1]["duplicateOf"] == result[0]["candidateId"]


def test_audit_reference_integrity_and_status_conservation() -> None:
    candidates = dedupe_and_conflict(
        [
            change_candidate("a", fingerprint="same"),
            change_candidate("b", fingerprint="same"),
            change_candidate("c", field_path="financials", change_type="new_value", signal_type="financial_filing", entity_type="financial", entity_key="2025", proposed_value={"value": 1}, fingerprint="financial-1"),
            change_candidate("d", field_path="financials", change_type="new_value", signal_type="financial_filing", entity_type="financial", entity_key="2025", proposed_value={"value": 2}, fingerprint="financial-2"),
        ]
    )
    run = {
        "companies": ["kumkang-kind"],
        "sources": ["public_news"],
        "sourceStatuses": [],
        "candidates": candidates,
        "candidateCount": len(candidates),
        "duplicate": sum(1 for candidate in candidates if candidate["status"] == "duplicate"),
        "publicDataChanged": False,
    }

    summary = audit_change_run(run)

    assert summary["statusConservationPassed"] is True
    assert summary["candidateIdUnique"] is True
    assert summary["orphanDuplicateReferenceCount"] == 0
    assert summary["orphanConflictReferenceCount"] == 0
    assert summary["duplicateOfSelfCount"] == 0
    assert summary["duplicateReferenceCycleCount"] == 0
    assert summary["conflictSelfReferenceCount"] == 0
    assert summary["crossCompanyContaminationCount"] == 0


def test_candidate_fingerprint_is_stable() -> None:
    one = candidate_fingerprint("a", "new_record", "production", {"x": 1}, "2026-07-22", "public_news")
    two = candidate_fingerprint("a", "new_record", "production", {"x": 1}, "2026-07-22", "public_news")
    assert one == two


def test_research_gap_linking_counts_matches() -> None:
    companies = company_map()
    candidate = {
        "candidateId": "gap-candidate",
        "companyId": "daeseung-engineering",
        "fieldPath": "production",
        "status": "pending",
        "researchGapIds": [],
    }
    summary = link_research_gaps(companies, [candidate])
    assert summary["daeseung-engineering"]["existingGapCount"] > 0
    assert isinstance(candidate["researchGapIds"], list)


def test_project_and_patent_transitions_are_guarded() -> None:
    assert valid_project_transition("contracted", "under_construction") is True
    assert valid_project_transition("planned", "completed") is False
    assert valid_patent_transition("filed", "registered") is True
    assert valid_patent_transition("registered", "filed") is False


def test_issue_fingerprint_prevents_duplicate_issue_titles() -> None:
    candidate = {
        "companyId": "kumkang-kind",
        "fingerprint": "abc",
    }
    assert issue_fingerprint(candidate) == issue_fingerprint(candidate)


def test_audit_validates_private_review_queue_and_daeseung_contamination() -> None:
    run = build_change_monitor_run(companies=["daeseung-engineering"], sources=["public_news"], lookback_days=30)
    summary = audit_change_run(run)
    assert summary["companyCount"] == 11
    assert summary["publicReviewQueueExposureCount"] == 0
    assert summary["daeseungContaminationCount"] == 0
    assert summary["secretExposureDetected"] is False
    assert summary["valid"] is True
