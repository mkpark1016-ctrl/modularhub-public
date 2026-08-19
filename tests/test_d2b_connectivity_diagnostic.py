from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from requests.exceptions import ConnectTimeout, ConnectionError, SSLError

from scripts.integrations.business.d2b_connectivity import (
    G2B_PROBE_ENDPOINT,
    assert_safe_summary,
    classify_diagnostic,
    extract_api_result_code,
    probe_api_endpoint,
    probe_https,
    run_connectivity_diagnostic,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, content: bytes | str, status_code: int = 200) -> None:
        self.content = content.encode("utf-8") if isinstance(content, str) else content
        self.status_code = status_code


class FakeSocket:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def ticking_clock() -> Any:
    value = -0.001

    def clock() -> float:
        nonlocal value
        value += 0.001
        return value

    return clock


def normal_payload(code: str = "00") -> str:
    return json.dumps(
        {"response": {"header": {"resultCode": code}, "body": {"items": []}}}
    )


def test_successful_api_probe_extracts_safe_result_code() -> None:
    captured: dict[str, Any] = {}

    def fake_get(endpoint: str, **kwargs: Any) -> FakeResponse:
        captured["endpoint"] = endpoint
        captured["params"] = kwargs["params"]
        return FakeResponse(normal_payload())

    result = probe_api_endpoint(
        name="g2b",
        endpoint=G2B_PROBE_ENDPOINT,
        service_group="1230000",
        operation="getOrderPlanSttusListCnstwkPPSSrch",
        params={"serviceKey": "secret-value", "numOfRows": 1},
        request_get=fake_get,
        clock=ticking_clock(),
    ).as_dict()

    assert captured["endpoint"] == G2B_PROBE_ENDPOINT
    assert captured["params"]["serviceKey"] == "secret-value"
    assert result["http_reached"] is True
    assert result["http_status"] == 200
    assert result["api_result_code"] == "00"
    assert "secret-value" not in json.dumps(result)
    assert "?" not in captured["endpoint"]


@pytest.mark.parametrize(
    ("exception", "category"),
    [
        (ConnectTimeout("connect timeout"), "connect_timeout"),
        (ConnectionError("connection failed"), "connection_error"),
        (SSLError("certificate failed"), "tls_error"),
    ],
)
def test_expected_transport_failures_are_sanitized(
    exception: Exception, category: str
) -> None:
    def fake_get(_endpoint: str, **_kwargs: Any) -> FakeResponse:
        raise exception

    result = probe_api_endpoint(
        name="d2b_procurement_plan",
        endpoint="https://apis.data.go.kr/1690000/PrcurePlanInfoService/getFcltyPrcurePlanList",
        service_group="1690000",
        operation="getFcltyPrcurePlanList",
        params={"serviceKey": "secret-value"},
        request_get=fake_get,
        clock=ticking_clock(),
    ).as_dict()

    assert result["http_reached"] is False
    assert result["transport_category"] == category
    assert result["exception_type"] == type(exception).__name__
    assert "secret-value" not in json.dumps(result)


@pytest.mark.parametrize(
    ("status", "category"),
    [(404, "http_client_error"), (503, "http_server_error")],
)
def test_http_errors_are_reachable_and_not_hidden(status: int, category: str) -> None:
    result = probe_api_endpoint(
        name="g2b",
        endpoint=G2B_PROBE_ENDPOINT,
        service_group="1230000",
        operation="getOrderPlanSttusListCnstwkPPSSrch",
        params={"serviceKey": "secret-value"},
        request_get=lambda *_args, **_kwargs: FakeResponse("upstream", status),
        clock=ticking_clock(),
    ).as_dict()

    assert result["tls_reached"] is True
    assert result["http_reached"] is True
    assert result["http_status"] == status
    assert result["transport_category"] == category
    assert result["api_result_code"] is None


def test_https_probe_distinguishes_tls_failure() -> None:
    def fake_get(_endpoint: str, **_kwargs: Any) -> FakeResponse:
        raise SSLError("tls handshake failed")

    result = probe_https(request_get=fake_get, clock=ticking_clock()).as_dict()

    assert result["tls_reached"] is False
    assert result["http_reached"] is False
    assert result["transport_category"] == "tls_error"


def test_result_code_extraction_supports_json_and_xml() -> None:
    assert extract_api_result_code(normal_payload("00")) == "00"
    assert (
        extract_api_result_code(
            "<response><header><resultCode>20</resultCode></header></response>"
        )
        == "20"
    )
    assert extract_api_result_code("<html>not an API response</html>") is None


def test_diagnostic_classification_cases() -> None:
    case_1 = classify_diagnostic(
        {
            "g2b": {"http_reached": True},
            "d2b_procurement_plan": {"http_reached": True},
            "d2b_bid_notice": {"http_reached": True},
        }
    )
    case_2 = classify_diagnostic(
        {
            "g2b": {"http_reached": True},
            "d2b_procurement_plan": {"http_reached": False},
            "d2b_bid_notice": {"http_reached": False},
        }
    )
    case_3 = classify_diagnostic(
        {
            "g2b": {"http_reached": False},
            "d2b_procurement_plan": {"http_reached": False},
            "d2b_bid_notice": {"http_reached": False},
        }
    )
    implementation_failure = classify_diagnostic({}, [{"probe": "dns"}])

    assert case_1["case"] == "case_1"
    assert case_2["case"] == "case_2"
    assert case_3["case"] == "case_3"
    assert implementation_failure["case"] == "diagnostic_implementation_failure"


def test_full_diagnostic_continues_after_d2b_transport_failures() -> None:
    fake_socket = FakeSocket()

    def fake_get(endpoint: str, **_kwargs: Any) -> FakeResponse:
        if endpoint == "https://apis.data.go.kr/":
            return FakeResponse("reachable", 404)
        if "/1230000/" in endpoint:
            return FakeResponse(normal_payload())
        raise ConnectTimeout("d2b path timed out")

    summary = run_connectivity_diagnostic(
        service_key="secret-value",
        today=date(2026, 8, 19),
        resolver=lambda *_args, **_kwargs: [(None, None, None, None, None)],
        connector=lambda *_args, **_kwargs: fake_socket,
        request_get=fake_get,
        clock=ticking_clock(),
    )

    assert fake_socket.closed is True
    assert summary["classification"]["case"] == "case_2"
    assert summary["probes"]["g2b"]["http_reached"] is True
    assert summary["probes"]["d2b_procurement_plan"]["http_reached"] is False
    assert summary["probes"]["d2b_bid_notice"]["http_reached"] is False
    assert summary["probes"]["d2b_bid_notice"]["transport_category"] == "connect_timeout"


def test_programming_error_is_not_mislabeled_as_network_failure() -> None:
    def broken_resolver(*_args: Any, **_kwargs: Any) -> Any:
        raise ValueError("broken diagnostic")

    summary = run_connectivity_diagnostic(
        service_key="secret-value",
        today=date(2026, 8, 19),
        resolver=broken_resolver,
        connector=lambda *_args, **_kwargs: FakeSocket(),
        request_get=lambda *_args, **_kwargs: FakeResponse(normal_payload()),
        clock=ticking_clock(),
    )

    assert summary["classification"]["case"] == "diagnostic_implementation_failure"
    assert summary["probes"]["dns"]["implementation_error"] is True
    assert summary["probes"]["g2b"]["http_reached"] is True


def test_summary_rejects_secret_urls_and_raw_response_fields() -> None:
    safe = {"probes": {"g2b": {"host": "apis.data.go.kr"}}}
    assert_safe_summary(safe, service_key="secret-value")

    with pytest.raises(ValueError, match="credential value"):
        assert_safe_summary({"value": "secret-value"}, service_key="secret-value")
    with pytest.raises(ValueError, match="credential-bearing URL"):
        assert_safe_summary(
            {"url": "https://apis.data.go.kr/path?serviceKey=redacted"},
            service_key="secret-value",
        )
    with pytest.raises(ValueError, match="raw response"):
        assert_safe_summary({"raw_response": "body"}, service_key="secret-value")


def test_cli_guard_prevents_network_without_dual_opt_in(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("DATA_GO_KR_SERVICE_KEY", None)
    result = subprocess.run(
        [
            sys.executable,
            "scripts/integrations/business/run_d2b_connectivity_diagnostic.py",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    summary = json.loads(
        (tmp_path / "diagnostic-summary.json").read_text(encoding="utf-8")
    )
    assert summary["request_attempted"] is False


def test_connectivity_workflow_is_manual_read_only_and_sanitized() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "d2b-connectivity-diagnostic.yml"
    ).read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow
    assert "push:" not in workflow
    assert "pull_request:" not in workflow
    assert "DATA_GO_KR_SERVICE_KEY: ${{ secrets.DATA_GO_KR_SERVICE_KEY }}" in workflow
    assert "acknowledge_live" in workflow
    assert "requirements-dev.txt" in workflow
    assert "tests/test_d2b_connectivity_diagnostic.py" in workflow
    assert "artifacts/d2b-connectivity/" in workflow
    assert "if-no-files-found: warn" in workflow
    assert "verify=False" not in workflow
    assert 'echo "${DATA_GO_KR_SERVICE_KEY}"' not in workflow
