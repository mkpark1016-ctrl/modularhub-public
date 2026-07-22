from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.company_change_monitoring import (
    CANDIDATE_STATUSES,
    CONFIDENCE_VALUES,
    RISK_LEVELS,
    audit_change_run,
    build_change_monitor_run,
    candidate_fingerprint,
    classify_signal,
    dedupe_and_conflict,
    identity_score,
    issue_fingerprint,
    link_research_gaps,
    load_identity_policies,
    load_source_policy,
    review_queue_payload,
    source_configured,
    valid_patent_transition,
    valid_project_transition,
)
from src.company_data_quality import load_public_company_universe


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


def test_review_queue_payload_keeps_candidates_internal() -> None:
    run = build_change_monitor_run(companies=["kumkang-kind"], sources=["public_news"], lookback_days=30)
    queue = review_queue_payload(run)
    assert queue["schemaVersion"] == "company-change-review-queue-v1"
    assert "candidates" in queue
    assert "frontend/public" not in json.dumps(queue, ensure_ascii=False)


def test_proposal_guard_requires_acknowledgement() -> None:
    with pytest.raises(ValueError):
        build_change_monitor_run(create_proposal=True, acknowledge_proposal=False)
    run = build_change_monitor_run(companies=["kumkang-kind"], sources=["public_news"], create_proposal=True, acknowledge_proposal=True)
    assert run["proposal"]["guard"] == "acknowledge_proposal_required"


def test_publish_guard_blocks_public_update() -> None:
    with pytest.raises(ValueError):
        build_change_monitor_run(publish=True)


def test_duplicate_fingerprint_and_conflict_detection() -> None:
    base = {
        "candidateId": "a",
        "companyId": "kumkang-kind",
        "fieldPath": "project_portfolio",
        "proposedValue": {"title": "A"},
        "fingerprint": "same",
        "status": "pending",
        "duplicateOf": None,
        "conflictsWith": [],
    }
    duplicate = {**base, "candidateId": "b"}
    conflict = {**base, "candidateId": "c", "fingerprint": "different", "proposedValue": {"title": "B"}}
    result = dedupe_and_conflict([base, duplicate, conflict])
    assert result[1]["status"] == "duplicate"
    assert result[1]["duplicateOf"] == "a"
    assert result[2]["status"] == "conflict"
    assert result[2]["conflictsWith"] == ["a"]


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
