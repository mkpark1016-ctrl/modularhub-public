from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.operations_public_data import (
    audit_datasets,
    contains_secret_indicator,
    count_delta_guard,
    issue_fingerprint,
    load_policy,
    normalize_source_health,
    public_company_count,
)


ROOT = Path(__file__).resolve().parents[2]
POLICY = load_policy(ROOT / "config/operations/data_freshness_policy.json")


def news_payload(published_at: str = "2026-07-22T00:00:00+00:00") -> dict:
    return {
        "generated_at": "2026-07-22T01:00:00+00:00",
        "items": [{"id": "n1", "published_at": published_at}],
        "news_source_statuses": [
            {
                "id": "naver_api_hub",
                "name": "NAVER API HUB",
                "source_type": "news",
                "state": "success",
                "fetched_count": 1,
                "accepted_count": 1,
                "latest_item_published_at": published_at,
            }
        ],
    }


def business_payload(generated_at: str = "2026-07-22T00:00:00+00:00", posted_at: str = "2026-07-16T00:00:00+00:00") -> dict:
    return {
        "generated_at": generated_at,
        "items": [{"id": "b1", "posted_at": posted_at}],
        "g2b_order_plan_status": "success",
        "procurement_plan_last_collected_at": generated_at,
        "lh_contest_status": "success",
        "lh_contest_last_attempt": "2026-07-22T01:00:00+00:00",
        "lh_contest_last_success": "2026-07-22T01:00:00+00:00",
    }


def companies_payload(count: int = 11) -> dict:
    return {
        "generated_at": "2026-07-16T00:00:00+00:00",
        "companies": [{"company_id": f"c{i}"} for i in range(count)],
    }


def audit(now: datetime, tmp_path: Path, *, news=None, business=None, companies=None) -> list[dict]:
    return audit_datasets(
        news_payload=news or news_payload(),
        business_payload=business or business_payload(),
        companies_payload=companies or companies_payload(),
        company_v2_payload={"generated_at": "2026-07-16T00:00:00+00:00"},
        meta_payload={},
        policy=POLICY,
        now=now,
    )


def state_for(rows: list[dict], dataset: str) -> str:
    return next(row["state"] for row in rows if row["dataset"] == dataset)


def test_freshness_policy_loads_expected_thresholds() -> None:
    assert POLICY["datasets"]["news"]["warningHours"] == 48
    assert POLICY["datasets"]["business"]["criticalHours"] == 48
    assert POLICY["datasets"]["companies"]["minimumPublicCount"] == 11


def test_news_freshness_healthy_warning_critical(tmp_path: Path) -> None:
    now = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)
    assert state_for(audit(now, tmp_path, news=news_payload("2026-07-22T00:00:00+00:00")), "news") == "healthy"
    assert state_for(audit(now, tmp_path, news=news_payload("2026-07-20T00:00:00+00:00")), "news") == "warning"
    assert state_for(audit(now, tmp_path, news=news_payload("2026-07-18T00:00:00+00:00")), "news") == "critical"


def test_business_freshness_healthy_warning_critical(tmp_path: Path) -> None:
    now = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)
    assert state_for(audit(now, tmp_path, business=business_payload("2026-07-22T00:00:00+00:00")), "business") == "healthy"
    assert state_for(audit(now, tmp_path, business=business_payload("2026-07-21T00:00:00+00:00")), "business") == "warning"
    assert state_for(audit(now, tmp_path, business=business_payload("2026-07-19T00:00:00+00:00")), "business") == "critical"


def test_company_freshness_and_count_guard(tmp_path: Path) -> None:
    now = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)
    rows = audit(now, tmp_path, companies=companies_payload(11))
    company = next(row for row in rows if row["dataset"] == "companies")
    assert company["recordCount"] == 11
    assert company["state"] == "healthy"
    rows = audit(now, tmp_path, companies=companies_payload(10))
    company = next(row for row in rows if row["dataset"] == "companies")
    assert company["recordCount"] == 10
    assert company["state"] == "critical"


def test_missing_invalid_and_empty_timestamps(tmp_path: Path) -> None:
    now = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)
    assert state_for(audit(now, tmp_path, news={"items": [{"id": "n1"}]}), "news") == "unknown"
    assert state_for(audit(now, tmp_path, news=news_payload("not-a-date")), "news") == "unknown"
    assert state_for(audit(now, tmp_path, news={"items": []}), "news") == "empty"


def test_count_drop_protection() -> None:
    assert count_delta_guard(90, 100, {"countDropCriticalPercent": 20}, "news")["state"] == "healthy"
    assert count_delta_guard(70, 100, {"countDropCriticalPercent": 20}, "news")["state"] == "critical"
    assert count_delta_guard(10, 11, {"minimumPublicCount": 11, "countDropCritical": 1}, "companies")["state"] == "critical"


def test_source_health_normalization_and_safe_message() -> None:
    row = normalize_source_health(
        {
            "id": "naver_api_hub",
            "name": "NAVER API HUB",
            "state": "failed",
            "safe_message": "Authorization X-NCP-APIGW-API-KEY failed",
        },
        POLICY,
        "news",
    )
    assert row["state"] == "source_unavailable"
    assert "Authorization" not in row["safeMessage"]
    assert "X-NCP-APIGW-API-KEY" not in row["safeMessage"]


def test_issue_fingerprint_is_deterministic() -> None:
    assert issue_fingerprint("news", "naver_api_hub", "auth_error") == issue_fingerprint("NEWS", "NAVER_API_HUB", "AUTH_ERROR")
    assert issue_fingerprint("news", "naver_api_hub", "auth_error") != issue_fingerprint("news", "overseas_rss", "auth_error")


def test_secret_indicator_scan() -> None:
    assert contains_secret_indicator(json.dumps({"header": "X-NCP-APIGW-API-KEY"}), POLICY)
    assert not contains_secret_indicator(json.dumps({"state": "healthy"}), POLICY)


def test_workflow_concurrency_timeout_and_permissions_contract() -> None:
    workflow = (ROOT / ".github/workflows/update-public-data.yml").read_text(encoding="utf-8")
    assert "concurrency:" in workflow
    assert "group: update-public-data-${{ github.ref }}" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "timeout-minutes: 30" in workflow
    assert "issues: write" in workflow
    assert "actions: read" in workflow
    assert "scripts/audit_public_data_freshness.py" in workflow
    assert "scripts/operations_issue_alert.py" in workflow


def test_public_company_count_uses_canonical_companies_only() -> None:
    assert public_company_count(companies_payload(11)) == 11
    assert public_company_count({"companies": [{"company_id": "c1"}, {"company_id": "c1"}, {"company_id": ""}]}) == 1
