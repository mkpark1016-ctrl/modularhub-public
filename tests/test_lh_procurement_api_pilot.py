from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from scripts.integrations.business.lh import (
    LH_RESOURCES,
    LH_SERVICE_KEY_ENV,
    LHApiError,
    LHClient,
    LHPilotRunner,
    LHProcurementAdapter,
    parse_lh_response,
)
from scripts.integrations.business.run_lh_pilot import main as run_lh_pilot_main

ROOT = Path(__file__).resolve().parents[1]


PROCUREMENT_PLAN_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE.</resultMsg></header>
  <body>
    <totalCount>2</totalCount>
    <items>
      <item>
        <orderPlanNo>PLAN-001</orderPlanNo>
        <orderPlanNm>Modular housing procurement plan</orderPlanNm>
        <orderOrgNm>LH</orderOrgNm>
        <orderExpectYm>202608</orderExpectYm>
        <orderAmt>1,200,000</orderAmt>
        <orderKindNm>goods</orderKindNm>
      </item>
    </items>
  </body>
</response>"""


PRE_SPEC_XML = b"""<response>
  <header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE.</resultMsg></header>
  <body>
    <totalCount>1</totalCount>
    <items>
      <item>
        <advcinfoReqNo>SPEC-001</advcinfoReqNo>
        <advcinfoReqNm>Temporary school modular pre-specification</advcinfoReqNm>
        <deptNm>Procurement Department</deptNm>
        <opinionRegEndDtm>20260831</opinionRegEndDtm>
        <alctBudgetAmt></alctBudgetAmt>
      </item>
    </items>
  </body>
</response>"""


BID_NOTICE_XML = b"""<response>
  <header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE.</resultMsg></header>
  <body>
    <totalCount>1</totalCount>
    <items>
      <item>
        <bidNum>BID-001</bidNum>
        <bidnmKor>Modular dormitory bid notice</bidnmKor>
        <zoneHqCd>Headquarters</zoneHqCd>
        <tndrbidRegDt>20260818</tndrbidRegDt>
        <tndrdocAcptEndDtm>2026/08/25 14:00</tndrdocAcptEndDtm>
        <fdmtlAmt>3500000</fdmtlAmt>
        <tndrCtrctMedCd>open</tndrCtrctMedCd>
      </item>
    </items>
  </body>
</response>"""


EMPTY_XML = b"""<response>
  <header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE.</resultMsg></header>
  <body><totalCount>0</totalCount><items /></body>
</response>"""


API_ERROR_XML = b"""<response>
  <header><resultCode>30</resultCode><resultMsg>SERVICE KEY IS NOT REGISTERED ERROR.</resultMsg></header>
  <body><totalCount>0</totalCount></body>
</response>"""


class FakeResponse:
    def __init__(self, content: bytes, *, status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code
        self.encoding = "utf-8"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_procurement_plan_parsing_and_normalization() -> None:
    payload = parse_lh_response(PROCUREMENT_PLAN_XML)
    assert payload.result_code == "00"
    assert payload.total_count == 2
    assert payload.items[0]["orderPlanNo"] == "PLAN-001"

    record = LHProcurementAdapter(LH_RESOURCES["procurement_plan"]).normalize_raw_record(payload.items[0])
    assert record.source == "lh"
    assert record.source_record_type == "procurement_plan"
    assert record.external_id == "lh:procurement_plan:PLAN-001"
    assert record.title == "Modular housing procurement plan"
    assert record.estimated_amount == 1200000
    assert record.published_at == "2026-08-01"


def test_pre_spec_parsing_and_null_amount() -> None:
    payload = parse_lh_response(PRE_SPEC_XML)
    record = LHProcurementAdapter(LH_RESOURCES["pre_spec"]).normalize_raw_record(payload.items[0])
    assert record.source_record_type == "pre_spec"
    assert record.external_id == "lh:pre_spec:SPEC-001"
    assert record.estimated_amount is None
    assert record.deadline_at == "2026-08-31"


def test_bid_notice_parsing_and_normalization() -> None:
    payload = parse_lh_response(BID_NOTICE_XML)
    record = LHProcurementAdapter(LH_RESOURCES["bid_notice"]).normalize_raw_record(payload.items[0])
    assert record.source_record_type == "bid_notice"
    assert record.external_id == "lh:bid_notice:BID-001"
    assert record.deadline_at == "2026-08-25"
    assert record.source_url.endswith("bidNum=BID-001")


def test_empty_malformed_and_api_error_responses() -> None:
    empty = parse_lh_response(EMPTY_XML)
    assert empty.total_count == 0
    assert empty.items == []

    with pytest.raises(Exception):
        parse_lh_response(b"<response><broken></response>")

    with pytest.raises(LHApiError) as exc_info:
        parse_lh_response(API_ERROR_XML)
    assert exc_info.value.result_code == "30"


def test_pagination_deduplication_and_invalid_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LH_SERVICE_KEY_ENV, "secret-value-for-test")
    calls: list[dict] = []

    def fake_get(_endpoint: str, *, params: dict, timeout: int) -> FakeResponse:
        calls.append({"params": params, "timeout": timeout})
        if params["pageNo"] == 1:
            return FakeResponse(PROCUREMENT_PLAN_XML)
        return FakeResponse(
            b"""<response><header><resultCode>00</resultCode></header><body><totalCount>2</totalCount><items><item>
            <orderPlanNo>PLAN-001</orderPlanNo><orderPlanNm>duplicate</orderPlanNm><orderExpectYm>202608</orderExpectYm>
            </item><item><orderPlanNo>PLAN-BAD</orderPlanNo><orderPlanNm>bad date</orderPlanNm><orderExpectYm>not-a-date</orderExpectYm>
            </item></items></body></response>"""
        )

    runner = LHPilotRunner(client=LHClient(page_size=1, request_get=fake_get))
    records, summary = runner.collect(
        resource_names=["procurement_plan"],
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 31),
        max_pages=3,
    )

    assert len(calls) == 2
    assert calls[0]["params"]["serviceKey"] == "secret-value-for-test"
    assert [record.external_id for record in records] == ["lh:procurement_plan:PLAN-001"]
    resource_summary = summary["resources"]["procurement_plan"]
    assert resource_summary["pages_requested"] == 2
    assert resource_summary["records_received"] == 3
    assert resource_summary["records_normalized"] == 1
    assert resource_summary["duplicates"] == 1
    assert resource_summary["records_invalid"] == 1


def test_live_guard_writes_summary_without_request(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(LH_SERVICE_KEY_ENV, "secret-value-for-test")
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_lh_pilot.py",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert run_lh_pilot_main() == 2
    summary = json.loads((tmp_path / "lh_summary.json").read_text(encoding="utf-8"))
    assert summary["request_attempted"] is False
    assert summary["guard"] == "requires --live and --acknowledge-live"


def test_secret_redaction_and_no_sensitive_output() -> None:
    payload = parse_lh_response(BID_NOTICE_XML)
    record = LHProcurementAdapter(LH_RESOURCES["bid_notice"]).normalize_raw_record(payload.items[0]).as_dict()
    serialized = json.dumps(record, ensure_ascii=False)
    for forbidden in (
        "serviceKey",
        "secret-value-for-test",
        "request_headers",
        "raw_response",
        LH_SERVICE_KEY_ENV,
    ):
        assert forbidden not in serialized


def test_lh_workflow_installs_pytest_and_preserves_original_failure() -> None:
    workflow = (ROOT / ".github" / "workflows" / "lh-procurement-api-pilot.yml").read_text(encoding="utf-8")

    assert "python -m pip install -r requirements-dev.txt" in workflow
    assert "python -m pip show pytest" in workflow
    assert workflow.index("python -m pip show pytest") < workflow.index("python -m pytest -q")
    assert "No LH summary artifact was generated. An earlier workflow step failed" in workflow
    assert "cat lh-summary.md >> \"$GITHUB_STEP_SUMMARY\"" in workflow
    assert "if-no-files-found: warn" in workflow
    assert "Verify LH staging outputs" in workflow
    assert "test -f artifacts/lh/lh_summary.json" in workflow
    assert "test -f artifacts/lh/lh_records.json" in workflow
