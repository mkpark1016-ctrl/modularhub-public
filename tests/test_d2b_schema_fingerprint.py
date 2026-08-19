from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import requests

from scripts.integrations.business.d2b import D2BClient
from scripts.integrations.business.d2b_schema_fingerprint import (
    EXPECTED_OPERATIONS,
    collect_schema_fingerprint,
    verify_schema_fingerprint,
    write_schema_fingerprint,
)


ROOT = Path(__file__).resolve().parents[1]
SECRET = "fingerprint-secret-not-for-output"


class FakeResponse:
    def __init__(self, payload: str, *, status_code: int = 200) -> None:
        self.content = payload.encode("utf-8")
        self.status_code = status_code
        self.encoding = "utf-8"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            error = requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error


def _payload(items: list[dict[str, Any]], *, result_code: str = "00") -> str:
    return json.dumps(
        {
            "response": {
                "header": {"resultCode": result_code, "resultMsg": "NORMAL SERVICE."},
                "body": {"totalCount": len(items), "items": {"item": items}},
            }
        }
    )


def _collect(fake_get: Any) -> dict[str, Any]:
    return collect_schema_fingerprint(
        client=D2BClient(service_key=SECRET, request_get=fake_get, max_attempts=1),
        plan_from=date(2026, 8, 1),
        plan_to=date(2027, 8, 1),
        bid_from=date(2026, 5, 1),
        bid_to=date(2026, 8, 19),
    )


def test_fingerprint_collects_only_sorted_keys_from_page_one(tmp_path: Path) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    forbidden_values = {"PLAN-VALUE", "TITLE-VALUE", "ORG-VALUE", "AMOUNT-VALUE"}

    def fake_get(endpoint: str, *, params: dict[str, Any], timeout: Any) -> FakeResponse:
        calls.append((endpoint, params))
        if "PrcurePlanInfoService" in endpoint:
            items = [
                {"zetaKey": "PLAN-VALUE", "planNo": "ID-VALUE", "planNm": "TITLE-VALUE"},
                {"planNm": "SECOND-TITLE", "amountKey": "AMOUNT-VALUE"},
            ]
        else:
            items = [{"bidTitle": "TITLE-VALUE", "agencyNm": "ORG-VALUE", "bidSeq": "ID-VALUE"}]
        return FakeResponse(_payload(items))

    summary = _collect(fake_get)
    verify_schema_fingerprint(summary, service_key=SECRET)
    write_schema_fingerprint(summary, tmp_path)

    assert tuple(summary["operations"]) == EXPECTED_OPERATIONS
    assert len(calls) == 3
    assert all(params["pageNo"] == 1 for _endpoint, params in calls)
    assert all(params["numOfRows"] == 50 for _endpoint, params in calls)
    for operation in summary["operations"].values():
        assert operation["observed_keys"] == sorted(
            set(operation["observed_keys"]),
            key=lambda value: (value.casefold(), value),
        )
        assert operation["key_count"] == len(operation["observed_keys"])
        for candidates in operation["candidate_mapping"].values():
            assert set(candidates) <= set(operation["observed_keys"])

    serialized = (tmp_path / "d2b-schema-fingerprint.json").read_text(encoding="utf-8")
    markdown = (tmp_path / "d2b-schema-fingerprint.md").read_text(encoding="utf-8")
    assert all(value not in serialized for value in forbidden_values)
    assert all(value not in markdown for value in forbidden_values)
    assert SECRET not in serialized
    assert "serviceKey=" not in serialized
    assert "raw_response" not in serialized.replace('"raw_response_persisted"', "")


def test_fingerprint_api_error_keeps_only_sanitized_diagnostics() -> None:
    def fake_get(_endpoint: str, *, params: dict[str, Any], timeout: Any) -> FakeResponse:
        return FakeResponse(_payload([], result_code="20"))

    summary = _collect(fake_get)

    assert summary["fingerprint_health"] == "failed"
    for operation in summary["operations"].values():
        assert operation["http_reached"] is True
        assert operation["api_result_code"] == "20"
        assert operation["error_category"] == "service_access_denied"
        assert operation["records_observed"] == 0
        assert operation["observed_keys"] == []
    verify_schema_fingerprint(summary, service_key=SECRET)
    assert "NORMAL SERVICE" not in json.dumps(summary)


@pytest.mark.parametrize(
    "unsafe_field",
    [
        {"raw_response": "payload"},
        {"response_body": "payload"},
        {"full_request_url": "https://example.test/?serviceKey=credential"},
        {"authorization": "Authorization: Bearer credential"},
    ],
)
def test_fingerprint_verifier_rejects_unexpected_or_credential_fields(unsafe_field: dict[str, str]) -> None:
    def fake_get(_endpoint: str, *, params: dict[str, Any], timeout: Any) -> FakeResponse:
        return FakeResponse(_payload([]))

    summary = _collect(fake_get)
    summary.update(unsafe_field)

    with pytest.raises(ValueError):
        verify_schema_fingerprint(summary, service_key=SECRET)


def test_fingerprint_verifier_rejects_actual_secret_and_security_failure() -> None:
    def fake_get(_endpoint: str, *, params: dict[str, Any], timeout: Any) -> FakeResponse:
        return FakeResponse(_payload([{"fieldName": "safe-value"}]))

    summary = _collect(fake_get)
    secret_summary = copy.deepcopy(summary)
    secret_summary["operations"][EXPECTED_OPERATIONS[0]]["exception_type"] = SECRET
    with pytest.raises(ValueError, match="credential value"):
        verify_schema_fingerprint(secret_summary, service_key=SECRET)

    security_summary = copy.deepcopy(summary)
    security_summary["security"]["response_item_values_persisted"] = True
    with pytest.raises(ValueError, match="response_item_values_persisted"):
        verify_schema_fingerprint(security_summary, service_key=SECRET)


def test_fingerprint_workflow_is_manual_page_one_and_read_only() -> None:
    workflow = (ROOT / ".github" / "workflows" / "d2b-schema-fingerprint.yml").read_text(encoding="utf-8")

    assert "name: D2B Live Schema Fingerprint" in workflow
    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow
    assert "push:" not in workflow
    assert "pull_request:" not in workflow
    assert "contents: read" in workflow
    assert "actions: read" in workflow
    assert "DATA_GO_KR_SERVICE_KEY: ${{ secrets.DATA_GO_KR_SERVICE_KEY }}" in workflow
    assert "--acknowledge-live" in workflow
    assert "--max-pages" not in workflow
    assert "d2b-schema-fingerprint.json" in workflow
    assert "verify_schema_fingerprint" in workflow
