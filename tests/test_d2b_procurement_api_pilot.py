from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import requests

from scripts.integrations.business.d2b import (
    D2B_RESOURCES,
    D2B_SERVICE_KEY_ENV,
    D2B_GW_BID_BASE_ENDPOINT,
    D2B_GW_PLAN_BASE_ENDPOINT,
    D2BClient,
    D2BPilotRunner,
    D2BProcurementAdapter,
    write_staging_outputs,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, payload: str, *, status_code: int = 200, encoding: str = "utf-8") -> None:
        self.text = payload
        self.content = payload.encode(encoding)
        self.status_code = status_code
        self.encoding = encoding

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            error = requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error

    def json(self) -> Any:
        return json.loads(self.text)


def d2b_payload(items: list[dict[str, Any]], *, total_count: int | None = None, result_code: str = "00") -> str:
    return json.dumps(
        {
            "response": {
                "header": {"resultCode": result_code, "resultMsg": "NORMAL SERVICE."},
                "body": {
                    "totalCount": len(items) if total_count is None else total_count,
                    "items": {"item": items},
                },
            }
        },
        ensure_ascii=False,
    )


D2B_PLAN_ITEM = {
    "dcsNo": "D2B-PLAN-001",
    "reprsntPrdlstNm": "모듈러 군 숙소 조달계획",
    "orntNm": "방위사업청",
    "orderPrearngeMt": "202609",
    "bdgtAmount": "980000000",
    "cntrctMthNm": "제한경쟁",
    "bidMthNm": "전자입찰",
    "progrsSttus": "계획",
    "excutTyNm": "시설",
}


D2B_BID_ITEM = {
    "bidNo": "D2B-BID-001",
    "pblancNo": "D2B-BID-001",
    "bidNm": "모듈러 작전시설 제작 설치",
    "orntNm": "국방시설본부",
    "pblancDate": "20260801",
    "bidSubmitClseDttm": "202608301800",
    "bsicExpt": "1250000000",
    "cntrctMthNm": "제한경쟁",
    "bidStle": "총액",
    "busiDivs": "시설공사",
    "pblancSe": "공고",
}


D2B_PRIVATE_BID_ITEM = {
    "bidNo": "D2B-PRIVATE-001",
    "pblancNo": "D2B-PRIVATE-001",
    "bidNm": "모듈러 정비시설 공개수의 협상계획",
    "orntNm": "국방시설본부",
    "pblancDate": "20260802",
    "ntatClosDttm": "202608311800",
    "bsicExpt": "900000000",
    "cntrctMthNm": "공개수의",
    "bidStle": "협상",
    "busiDivs": "시설공사",
    "pblancSe": "협상계획",
}


def test_d2b_procurement_plan_canonical_mapping() -> None:
    adapter = D2BProcurementAdapter(D2B_RESOURCES["procurement_plan"], collected_at="2026-08-19T00:00:00+00:00")
    raw = {
        "source_record_id": "D2B-PLAN-001",
        "dcs_no": "D2B-PLAN-001",
        "title": "모듈러 군 숙소 조달계획",
        "organization": "방위사업청",
        "business_type": "시설",
        "region": "방위사업청",
        "amount": "980,000,000",
        "posted_at": "202609",
        "due_at": "202609",
        "progress_status": "계획",
        "contract_method": "제한경쟁",
        "url": "https://www.d2b.go.kr/?dcsNo=D2B-PLAN-001",
    }

    normalized = adapter.normalize_raw_record(raw)

    assert normalized.source == "d2b"
    assert normalized.source_record_type == "procurement_plan"
    assert normalized.external_id == "d2b:procurement_plan:D2B-PLAN-001"
    assert normalized.title == "모듈러 군 숙소 조달계획"
    assert normalized.estimated_amount == 980_000_000
    assert normalized.published_at == "2026-09-01"
    assert normalized.deadline_at == "2026-09-01"
    assert normalized.currency == "KRW"
    assert "serviceKey" not in json.dumps(normalized.as_dict(), ensure_ascii=False)


def test_d2b_bid_notice_canonical_mapping() -> None:
    adapter = D2BProcurementAdapter(D2B_RESOURCES["bid_notice"], collected_at="2026-08-19T00:00:00+00:00")
    raw = {
        "source_record_id": "D2B-BID-001",
        "notice_no": "D2B-BID-001",
        "bid_no": "D2B-BID-001",
        "title": "모듈러 작전시설 제작 설치",
        "organization": "국방시설본부",
        "business_type": "시설공사",
        "amount": "1250000000",
        "posted_at": "20260801",
        "due_at": "202608301800",
        "progress_status": "공고",
        "contract_method": "제한경쟁",
        "url": "https://www.d2b.go.kr/?bidNo=D2B-BID-001",
    }

    normalized = adapter.normalize_raw_record(raw)

    assert normalized.source_record_type == "bid_notice"
    assert normalized.external_id == "d2b:bid_notice:D2B-BID-001"
    assert normalized.published_at == "2026-08-01"
    assert normalized.deadline_at == "2026-08-30"
    assert normalized.status == "공고"


def test_d2b_runner_reuses_existing_collectors_for_pagination_and_dedupe() -> None:
    calls: list[tuple[str, int]] = []

    def fake_get(endpoint: str, *, params: dict[str, Any], timeout: int) -> FakeResponse:
        page_no = int(params["pageNo"])
        calls.append((endpoint, page_no))
        if "PrcurePlanInfoService" in endpoint:
            return FakeResponse(d2b_payload([D2B_PLAN_ITEM], total_count=2))
        if "getFcltyOthbcVltrnNtatPlanList" in endpoint:
            return FakeResponse(d2b_payload([D2B_PRIVATE_BID_ITEM], total_count=2))
        return FakeResponse(d2b_payload([D2B_BID_ITEM], total_count=2))

    runner = D2BPilotRunner(client=D2BClient(service_key="test-secret", request_get=fake_get, page_size=1))
    records, summary = runner.collect(
        resource_names=["procurement_plan", "bid_notice"],
        plan_from=date(2026, 8, 1),
        plan_to=date(2026, 12, 1),
        bid_from=date(2026, 8, 1),
        bid_to=date(2026, 8, 31),
        max_pages=2,
    )

    assert [record.external_id for record in records] == [
        "d2b:procurement_plan:D2B-PLAN-001",
        "d2b:bid_notice:D2B-BID-001",
        "d2b:bid_notice:D2B-PRIVATE-001",
    ]
    assert summary["records_normalized"] == 3
    assert summary["overall_health"] == "healthy"
    assert summary["resources"]["procurement_plan"]["pages_requested"] == 2
    assert summary["resources"]["procurement_plan"]["records_received"] == 2
    assert summary["resources"]["procurement_plan"]["records_matched"] == 2
    assert summary["resources"]["procurement_plan"]["records_normalized"] == 1
    assert summary["resources"]["procurement_plan"]["duplicates"] == 1
    assert summary["resources"]["procurement_plan"]["operation_counts"]["getFcltyPrcurePlanList"]["pages_requested"] == 2
    assert summary["resources"]["bid_notice"]["pages_requested"] == 4
    assert summary["resources"]["bid_notice"]["records_normalized"] == 2
    assert summary["resources"]["bid_notice"]["duplicates"] == 2
    assert summary["resources"]["bid_notice"]["operation_counts"]["getFcltyCmpetBidPblancList"]["pages_requested"] == 2
    assert summary["resources"]["bid_notice"]["operation_counts"]["getFcltyOthbcVltrnNtatPlanList"]["pages_requested"] == 2
    assert len(calls) == 6
    assert all("openapi.d2b.go.kr" not in endpoint for endpoint, _page in calls)
    assert any(endpoint == f"{D2B_GW_PLAN_BASE_ENDPOINT}/getFcltyPrcurePlanList" for endpoint, _page in calls)
    assert any(endpoint == f"{D2B_GW_BID_BASE_ENDPOINT}/getFcltyCmpetBidPblancList" for endpoint, _page in calls)
    assert any(endpoint == f"{D2B_GW_BID_BASE_ENDPOINT}/getFcltyOthbcVltrnNtatPlanList" for endpoint, _page in calls)


def test_d2b_connect_timeout_retries_then_success() -> None:
    calls: list[tuple[str, Any]] = []
    sleep_calls: list[int] = []

    def fake_get(endpoint: str, *, params: dict[str, Any], timeout: Any) -> FakeResponse:
        calls.append((endpoint, timeout))
        if len(calls) < 3:
            raise requests.exceptions.ConnectTimeout("simulated connect timeout")
        return FakeResponse(d2b_payload([D2B_PLAN_ITEM], total_count=1))

    runner = D2BPilotRunner(
        client=D2BClient(
            service_key="test-secret",
            request_get=fake_get,
            max_attempts=3,
            sleep_func=sleep_calls.append,
        )
    )
    records, summary = runner.collect(
        resource_names=["procurement_plan"],
        plan_from=date(2026, 8, 1),
        plan_to=date(2026, 12, 1),
        bid_from=date(2026, 8, 1),
        bid_to=date(2026, 8, 31),
        max_pages=1,
    )

    assert len(calls) == 3
    assert [timeout for _endpoint, timeout in calls] == [(10, 30), (10, 30), (10, 30)]
    assert sleep_calls == [0, 1]
    assert [record.external_id for record in records] == ["d2b:procurement_plan:D2B-PLAN-001"]
    assert summary["resources"]["procurement_plan"]["api_errors"] == []
    assert summary["overall_health"] == "healthy"


def test_d2b_connect_timeout_all_attempts_fails_with_sanitized_diagnostic() -> None:
    calls = 0
    sleep_calls: list[int] = []

    def fake_get(_endpoint: str, *, params: dict[str, Any], timeout: Any) -> FakeResponse:
        nonlocal calls
        calls += 1
        raise requests.exceptions.ConnectTimeout("simulated connect timeout")

    runner = D2BPilotRunner(
        client=D2BClient(
            service_key="secret-not-for-output",
            request_get=fake_get,
            max_attempts=3,
            sleep_func=sleep_calls.append,
        )
    )
    _records, summary = runner.collect(
        resource_names=["procurement_plan"],
        plan_from=date(2026, 8, 1),
        plan_to=date(2026, 12, 1),
        bid_from=date(2026, 8, 1),
        bid_to=date(2026, 8, 31),
        max_pages=1,
    )

    error = summary["resources"]["procurement_plan"]["api_errors"][0]
    assert calls == 3
    assert sleep_calls == [0, 1]
    assert error["category"] == "transport_error"
    assert error["attempt_count"] == "3"
    assert error["transport_category"] == "connect_timeout"
    assert error["final_exception_type"] == "ConnectTimeout"
    assert error["endpoint_host"] == "apis.data.go.kr"
    assert "serviceKey" not in json.dumps(summary, ensure_ascii=False)
    assert "secret-not-for-output" not in json.dumps(summary, ensure_ascii=False)


def test_d2b_connection_error_retries_then_success() -> None:
    calls = 0

    def fake_get(_endpoint: str, *, params: dict[str, Any], timeout: Any) -> FakeResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise requests.exceptions.ConnectionError("simulated connection reset")
        return FakeResponse(d2b_payload([D2B_PLAN_ITEM], total_count=1))

    runner = D2BPilotRunner(
        client=D2BClient(
            service_key="test-secret",
            request_get=fake_get,
            max_attempts=2,
            sleep_func=lambda _attempt: None,
        )
    )
    records, summary = runner.collect(
        resource_names=["procurement_plan"],
        plan_from=date(2026, 8, 1),
        plan_to=date(2026, 12, 1),
        bid_from=date(2026, 8, 1),
        bid_to=date(2026, 8, 31),
        max_pages=1,
    )

    assert calls == 2
    assert len(records) == 1
    assert summary["resources"]["procurement_plan"]["source_health"] == "healthy"


def test_d2b_http_5xx_retries_then_success() -> None:
    calls = 0

    def fake_get(_endpoint: str, *, params: dict[str, Any], timeout: Any) -> FakeResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            return FakeResponse("temporary outage", status_code=503)
        return FakeResponse(d2b_payload([D2B_PLAN_ITEM], total_count=1))

    runner = D2BPilotRunner(
        client=D2BClient(
            service_key="test-secret",
            request_get=fake_get,
            max_attempts=2,
            sleep_func=lambda _attempt: None,
        )
    )
    records, summary = runner.collect(
        resource_names=["procurement_plan"],
        plan_from=date(2026, 8, 1),
        plan_to=date(2026, 12, 1),
        bid_from=date(2026, 8, 1),
        bid_to=date(2026, 8, 31),
        max_pages=1,
    )

    assert calls == 2
    assert len(records) == 1
    assert summary["overall_health"] == "healthy"


def test_d2b_empty_response_is_healthy_empty() -> None:
    def fake_get(_endpoint: str, *, params: dict[str, Any], timeout: int) -> FakeResponse:
        return FakeResponse(d2b_payload([], total_count=0))

    runner = D2BPilotRunner(client=D2BClient(service_key="test-secret", request_get=fake_get))
    records, summary = runner.collect(
        resource_names=["procurement_plan"],
        plan_from=date(2026, 8, 1),
        plan_to=date(2026, 12, 1),
        bid_from=date(2026, 8, 1),
        bid_to=date(2026, 8, 31),
        max_pages=1,
    )

    assert records == []
    assert summary["resources"]["procurement_plan"]["source_health"] == "healthy_empty"
    assert summary["overall_health"] == "healthy_empty"


def test_d2b_api_error_is_sanitized() -> None:
    def fake_get(_endpoint: str, *, params: dict[str, Any], timeout: int) -> FakeResponse:
        return FakeResponse(d2b_payload([], result_code="99"))

    runner = D2BPilotRunner(client=D2BClient(service_key="secret-not-for-output", request_get=fake_get))
    _records, summary = runner.collect(
        resource_names=["bid_notice"],
        plan_from=date(2026, 8, 1),
        plan_to=date(2026, 12, 1),
        bid_from=date(2026, 8, 1),
        bid_to=date(2026, 8, 31),
        max_pages=1,
    )

    resource = summary["resources"]["bid_notice"]
    assert resource["source_health"] == "failed"
    assert resource["api_errors"][0]["category"] == "api_error"
    assert resource["api_errors"][0]["result_code"] == "99"
    payload = json.dumps(summary, ensure_ascii=False)
    assert "secret-not-for-output" not in payload
    assert "serviceKey=" not in payload


def test_d2b_result_code_20_is_service_access_denied() -> None:
    calls = 0

    def fake_get(_endpoint: str, *, params: dict[str, Any], timeout: int) -> FakeResponse:
        nonlocal calls
        calls += 1
        return FakeResponse(d2b_payload([], result_code="20"))

    runner = D2BPilotRunner(
        client=D2BClient(
            service_key="secret-not-for-output",
            request_get=fake_get,
            max_attempts=3,
            sleep_func=lambda _attempt: None,
        )
    )
    _records, summary = runner.collect(
        resource_names=["procurement_plan"],
        plan_from=date(2026, 8, 1),
        plan_to=date(2026, 12, 1),
        bid_from=date(2026, 8, 1),
        bid_to=date(2026, 8, 31),
        max_pages=1,
    )

    error = summary["resources"]["procurement_plan"]["api_errors"][0]
    assert calls == 1
    assert error["category"] == "service_access_denied"
    assert error["result_code"] == "20"


def test_d2b_result_code_30_is_auth_error() -> None:
    calls = 0

    def fake_get(_endpoint: str, *, params: dict[str, Any], timeout: int) -> FakeResponse:
        nonlocal calls
        calls += 1
        return FakeResponse(d2b_payload([], result_code="30"))

    runner = D2BPilotRunner(
        client=D2BClient(
            service_key="secret-not-for-output",
            request_get=fake_get,
            max_attempts=3,
            sleep_func=lambda _attempt: None,
        )
    )
    _records, summary = runner.collect(
        resource_names=["procurement_plan"],
        plan_from=date(2026, 8, 1),
        plan_to=date(2026, 12, 1),
        bid_from=date(2026, 8, 1),
        bid_to=date(2026, 8, 31),
        max_pages=1,
    )

    error = summary["resources"]["procurement_plan"]["api_errors"][0]
    assert calls == 1
    assert error["category"] == "auth_error"
    assert error["result_code"] == "30"


def test_d2b_malformed_response_is_parse_error() -> None:
    def fake_get(_endpoint: str, *, params: dict[str, Any], timeout: int) -> FakeResponse:
        return FakeResponse("<not-xml")

    runner = D2BPilotRunner(client=D2BClient(service_key="test-secret", request_get=fake_get))
    _records, summary = runner.collect(
        resource_names=["procurement_plan"],
        plan_from=date(2026, 8, 1),
        plan_to=date(2026, 12, 1),
        bid_from=date(2026, 8, 1),
        bid_to=date(2026, 8, 31),
        max_pages=1,
    )

    error = summary["resources"]["procurement_plan"]["api_errors"][0]
    assert error["category"] == "response_parse_error"
    assert error["endpoint_host"] == "apis.data.go.kr"


def test_d2b_invalid_records_count_missing_external_id_and_title() -> None:
    adapter = D2BProcurementAdapter(D2B_RESOURCES["procurement_plan"])

    with pytest.raises(ValueError, match="external_id"):
        adapter.normalize_raw_record({"title": "모듈러 계획"})
    with pytest.raises(ValueError, match="title"):
        adapter.normalize_raw_record({"source_record_id": "D2B-PLAN-001"})


def test_d2b_live_guard_skips_without_dual_opt_in(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/integrations/business/run_d2b_pilot.py",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    summary = json.loads((tmp_path / "d2b_summary.json").read_text(encoding="utf-8"))
    assert summary["request_attempted"] is False
    assert summary["guard"] == "requires --live and --acknowledge-live"


def test_d2b_missing_secret_does_not_attempt_request(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop(D2B_SERVICE_KEY_ENV, None)
    result = subprocess.run(
        [
            sys.executable,
            "scripts/integrations/business/run_d2b_pilot.py",
            "--output-dir",
            str(tmp_path),
            "--live",
            "--acknowledge-live",
        ],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 3
    summary = json.loads((tmp_path / "d2b_summary.json").read_text(encoding="utf-8"))
    assert summary["request_attempted"] is False
    assert summary["error_category"] == "missing_secret"


def test_d2b_staging_output_contract(tmp_path: Path) -> None:
    adapter = D2BProcurementAdapter(D2B_RESOURCES["bid_notice"], collected_at="2026-08-19T00:00:00+00:00")
    record = adapter.normalize_raw_record(
        {
            "source_record_id": "D2B-BID-001",
            "title": "모듈러 작전시설 제작 설치",
            "organization": "국방시설본부",
        }
    )
    summary = {"source": "d2b", "records_normalized": 1, "resources": {}}

    write_staging_outputs([record], summary, tmp_path)

    records_payload = json.loads((tmp_path / "d2b_records.json").read_text(encoding="utf-8"))
    summary_payload = json.loads((tmp_path / "d2b_summary.json").read_text(encoding="utf-8"))
    assert records_payload[0]["external_id"] == "d2b:bid_notice:D2B-BID-001"
    assert summary_payload["source"] == "d2b"


def test_d2b_workflow_is_manual_staging_only() -> None:
    workflow = (ROOT / ".github" / "workflows" / "d2b-procurement-api-pilot.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow
    assert "push:" not in workflow
    assert "pull_request:" not in workflow
    assert "DATA_GO_KR_SERVICE_KEY: ${{ secrets.DATA_GO_KR_SERVICE_KEY }}" in workflow
    assert "python -m pip install -r requirements-dev.txt" in workflow
    assert "python -m pytest -q tests/test_d2b_procurement_api_pilot.py" in workflow
    assert "artifacts/d2b/" in workflow
    assert "if-no-files-found: warn" in workflow
    assert "D2B_SERVICE_KEY" not in workflow


def test_d2b_env_example_documents_current_gw_endpoints() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "D2B_GW_PLAN_FACILITY_ENDPOINT=https://apis.data.go.kr/1690000/PrcurePlanInfoService/getFcltyPrcurePlanList" in env_example
    assert "D2B_GW_BID_FACILITY_COMPETITIVE_ENDPOINT=https://apis.data.go.kr/1690000/BidPblancInfoService/getFcltyCmpetBidPblancList" in env_example
    assert "D2B_GW_BID_FACILITY_PRIVATE_ENDPOINT=https://apis.data.go.kr/1690000/BidPblancInfoService/getFcltyOthbcVltrnNtatPlanList" in env_example
    assert "D2B_GW_CODE_ORNT_ENDPOINT=https://apis.data.go.kr/1690000/CodeInqireService/getOrntCodeList" in env_example
