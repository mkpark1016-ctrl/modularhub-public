from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

from scripts.company_monitoring.build_review_queue import build_review_queue
from scripts.company_monitoring.classify_candidate import classify_text
from scripts.company_monitoring.collect_naver_search import (
    NAVER_API_HUB_HOST,
    NAVER_API_HUB_ID_HEADER,
    NAVER_API_HUB_PATH,
    NAVER_API_HUB_SECRET_HEADER,
    build_naver_request,
    naver_contract_report,
)
from scripts.company_monitoring.audit_live_pilot_artifacts import audit
from scripts.company_monitoring.common import canonical_url, live_opt_in_enabled, load_monitor_companies, masked_config_status, read_json, write_json
from scripts.company_monitoring.dedupe_candidates import dedupe_candidates
from scripts.company_monitoring.normalize_candidate import entity_match_score, make_candidate, parse_date, relevance_score
from scripts.company_monitoring.validate_review_queue import validate_queue


def company(company_id: str = "kumkang-kind"):
    return next(item for item in load_monitor_companies({company_id}) if item.company_id == company_id)


def test_alias_mapping_scores_exact_company_match() -> None:
    c = company("kumkang-kind")
    assert entity_match_score(c, "금강공업 모듈러 학교 수주", "Kumkang Kind confirmed", "") >= 0.8
    assert entity_match_score(c, "다른 회사 모듈러 수주", "", "") == 0


def test_url_normalization_removes_tracking() -> None:
    url = canonical_url("HTTPS://Example.COM/news/123/?utm_source=x&b=2#g")
    assert url == "https://example.com/news/123?b=2"


def test_secret_status_does_not_include_length() -> None:
    assert masked_config_status("not-a-real-secret") == "configured"
    assert masked_config_status("") == "missing"


def test_live_opt_in_requires_both_flags() -> None:
    class Args:
        live = True
        acknowledge_live = False

    assert live_opt_in_enabled(Args()) is False
    Args.acknowledge_live = True
    assert live_opt_in_enabled(Args()) is True


def test_naver_api_hub_contract_uses_official_endpoint_and_headers(monkeypatch) -> None:
    monkeypatch.setenv("NAVER_API_HUB_CLIENT_ID", "dummy-client-id")
    monkeypatch.setenv("NAVER_API_HUB_CLIENT_SECRET", "dummy-client-secret")
    monkeypatch.delenv("NAVER_API_HUB_NEWS_ENDPOINT", raising=False)
    request = build_naver_request("모듈러", display=1, start=1)
    parsed = urllib.parse.urlsplit(request.full_url)
    assert parsed.netloc == NAVER_API_HUB_HOST
    assert parsed.path == NAVER_API_HUB_PATH
    headers = {key.lower() for key, _ in request.header_items()}
    assert NAVER_API_HUB_ID_HEADER.lower() in headers
    assert NAVER_API_HUB_SECRET_HEADER.lower() in headers
    assert "x-naver-client-id" not in headers
    assert "x-naver-client-secret" not in headers
    assert "openapi.naver.com" not in request.full_url


def test_naver_contract_report_is_sanitized(monkeypatch) -> None:
    monkeypatch.setenv("NAVER_API_HUB_CLIENT_ID", "dummy-client-id")
    monkeypatch.setenv("NAVER_API_HUB_CLIENT_SECRET", "dummy-client-secret")
    report = naver_contract_report()
    assert report["contract_match"] is True
    assert report["legacy_env_fallback_enabled"] is False
    assert report["legacy_header_names_used"] is False
    serialized = json.dumps(report, ensure_ascii=False)
    assert "dummy-client-id" not in serialized
    assert "dummy-client-secret" not in serialized


def test_date_conversion_handles_naver_and_dart_formats() -> None:
    assert parse_date("20260718") == "2026-07-18"
    assert parse_date("Sat, 18 Jul 2026 09:00:00 +0900") == "2026-07-18"


def test_classification_keeps_mou_and_planned_out_of_project_credit() -> None:
    mou = classify_text("금강공업 모듈러 MOU 체결", "업무협약")
    assert mou["event_status"] == "mou_signed"
    assert mou["project_credit"] is False
    planned = classify_text("유창이앤씨 학교 모듈러 추진 계획", "검토 단계")
    assert planned["project_credit"] is False
    assert "planned_or_unconfirmed_not_project_credit" in planned["promotion_blockers"]


def test_classification_marks_project_candidates_for_review_not_credit() -> None:
    result = classify_text("금강공업 모듈러 학교 수주", "계약 기사")
    assert result["domain"] == "project"
    assert result["event_status"] == "contracted"
    assert result["project_credit"] is False
    assert "official_role_review_required" in result["promotion_blockers"]


def test_relevance_score_uses_modular_keywords() -> None:
    c = company("yuchang-enc")
    high = relevance_score(c, "유창이앤씨 스틸 모듈러 학교", "군숙소 모듈러", "")
    low = relevance_score(c, "유창이앤씨 채용 공고", "구인", "")
    assert high > low


def test_dedupe_marks_same_url_duplicate() -> None:
    c = company()
    first = make_candidate(
        company=c,
        candidate_kind="event",
        domain="project",
        title="금강공업 모듈러 수주",
        summary="계약 후보",
        source_type="naver_search",
        source_tier="C",
        publisher="NAVER Search",
        source_url="https://news.example.com/a?utm_source=x",
    )
    second = {**first, "candidate_id": "cand-other", "source_url": "https://news.example.com/a"}
    deduped = dedupe_candidates([first, second])
    assert deduped[0]["review_status"] == "pending"
    assert deduped[1]["review_status"] == "duplicate"
    assert deduped[1]["duplicate_of"] == deduped[0]["candidate_id"]
    assert deduped[1]["candidate_id"] != deduped[0]["candidate_id"]


def test_dedupe_does_not_link_same_url_across_companies() -> None:
    first_company = company("kumkang-kind")
    second_company = company("yuchang-enc")
    first = make_candidate(
        company=first_company,
        candidate_kind="event",
        domain="project",
        title="모듈러 공동 기사",
        summary="금강공업과 유창이앤씨가 언급된 기사",
        source_type="naver_search",
        source_tier="C",
        publisher="NAVER Search",
        source_url="https://news.example.com/shared",
    )
    second = make_candidate(
        company=second_company,
        candidate_kind="event",
        domain="project",
        title="모듈러 공동 기사",
        summary="금강공업과 유창이앤씨가 언급된 기사",
        source_type="naver_search",
        source_tier="C",
        publisher="NAVER Search",
        source_url="https://news.example.com/shared",
    )
    deduped = dedupe_candidates([first, second])
    assert [row["review_status"] for row in deduped] == ["pending", "pending"]
    assert deduped[1]["duplicate_of"] is None


def test_build_review_queue_outputs_only_pending(tmp_path: Path) -> None:
    c = company()
    raw = {
        "source_type": "naver_search",
        "results": [
            {
                "source_type": "naver_search",
                "company_id": c.company_id,
                "status": "ok",
                "candidates": [
                    make_candidate(
                        company=c,
                        candidate_kind="event",
                        domain="project",
                        title="금강공업 모듈러 학교 수주",
                        summary="공식 확인 전 후보",
                        source_type="naver_search",
                        source_tier="C",
                        publisher="NAVER Search",
                        source_url="https://news.example.com/project",
                        event_status="contracted",
                        project_credit=False,
                    )
                ],
            }
        ],
    }
    write_json(tmp_path / "naver_search_raw.json", raw)
    payload = build_review_queue(tmp_path)
    assert payload["digest"]["pending_count"] == 1
    assert payload["review_queue"][0]["review_status"] == "pending"
    assert payload["review_queue"][0]["project_credit"] is False
    assert payload["digest"]["final_status_counts"]["pending"] == 1
    assert payload["digest"]["quality_flag_counts"]["raw_rejected"] == 0


def test_live_artifact_audit_preserves_status_counts_and_rejected_flags(tmp_path: Path) -> None:
    c = company()
    first = make_candidate(
        company=c,
        candidate_kind="event",
        domain="project",
        title="금강공업 모듈러 수주",
        summary="공식 확인 전 후보",
        source_type="naver_search",
        source_tier="C",
        publisher="NAVER Search",
        source_url="https://news.example.com/project?utm_source=x",
        event_status="contracted",
        project_credit=False,
    )
    second = {**first, "candidate_id": "candidate-second", "source_url": "https://news.example.com/project"}
    raw = {
        "source_type": "naver_search",
        "results": [
            {
                "source_type": "naver_search",
                "company_id": c.company_id,
                "status": "ok",
                "records": [
                    {"title": first["title"], "original_link": first["source_url"], "query": "금강공업 모듈러"},
                    {"title": second["title"], "original_link": second["source_url"], "query": "금강공업 모듈러"},
                    {"title": "다른 회사", "original_link": "https://news.example.com/other", "query": "금강공업 모듈러"},
                ],
                "rejected": [
                    {
                        "title": "다른 회사",
                        "original_link": "https://news.example.com/other",
                        "query": "금강공업 모듈러",
                        "rejection_reason": "entity_not_matched",
                    }
                ],
                "candidates": [first, second],
            }
        ],
    }
    write_json(tmp_path / "naver_search_raw.json", raw)
    write_json(tmp_path / "dart_raw.json", {"source_type": "dart", "results": []})
    output_dir = tmp_path / "audit"
    summary = audit(raw_dir=tmp_path, queue_path=tmp_path / "review_queue.json", digest_path=tmp_path / "digest.json", output_dir=output_dir)
    assert summary["normalized_unique_count"] == 2
    assert summary["final_status_counts"]["pending"] == 1
    assert summary["final_status_counts"]["duplicate"] == 1
    assert summary["quality_flag_counts"]["raw_rejected_quality_flag"] == 1
    assert summary["final_status_counts"]["rejected"] == 0
    assert summary["status_conservation"]["valid"] is True
    assert summary["duplicate_integrity"]["missing_duplicate_of_count"] == 0
    assert summary["metric_excess_cause"] == "rejected_flag_double_count"
    assert (output_dir / "audit-summary.json").exists()
    assert (output_dir / "review-sample.json").exists()


def test_validate_queue_rejects_secret_literal(tmp_path: Path) -> None:
    c = company()
    candidate = make_candidate(
        company=c,
        candidate_kind="evidence",
        domain="market",
        title="금강공업 모듈러",
        summary="crtfc_key=SHOULD_NOT_APPEAR",
        source_type="naver_search",
        source_tier="C",
        publisher="NAVER Search",
        source_url="https://news.example.com/secret",
    )
    path = tmp_path / "review_queue.json"
    write_json(path, {"schema_version": "test", "generated_at": "2026-07-18T00:00:00Z", "review_queue": [candidate]})
    result = validate_queue(path)
    assert not result["valid"]
    assert any(issue["code"] == "secret_literal_exposed" for issue in result["issues"])


def test_public_baseline_company_count_matches_canonical_universe() -> None:
    companies = read_json(Path("frontend/public/data/companies/companies.json"))
    assert len(companies["companies"]) == 11
    assert sum(1 for company in companies["companies"] if company.get("company_id") == "daeseung-engineering") == 1
