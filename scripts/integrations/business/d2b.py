from __future__ import annotations

import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from src.collectors.d2b_bid import D2BBidCollector
from src.collectors.d2b_plan import D2BPlanCollector

from .base import ExternalBusinessSourceAdapter, NormalizedBusinessRecord, clean_text, parse_amount


D2B_SOURCE = "d2b"
D2B_SERVICE_KEY_ENV = "DATA_GO_KR_SERVICE_KEY"
DEFAULT_PAGE_SIZE = 50
DEFAULT_MAX_PAGES = 3
DEFAULT_LOOKBACK_DAYS = 90
DEFAULT_LOOKAHEAD_MONTHS = 12


@dataclass(frozen=True)
class D2BResource:
    name: str
    source_record_type: str


D2B_RESOURCES: dict[str, D2BResource] = {
    "procurement_plan": D2BResource("procurement_plan", "procurement_plan"),
    "bid_notice": D2BResource("bid_notice", "bid_notice"),
}


@dataclass
class D2BCollectionSummary:
    pages_requested: int = 0
    records_received: int = 0
    records_matched: int = 0
    records_normalized: int = 0
    records_invalid: int = 0
    duplicates: int = 0
    api_errors: list[dict[str, str]] = field(default_factory=list)
    total_count: int | None = None
    source_health: str = "healthy"
    endpoint_groups: dict[str, dict[str, int]] = field(default_factory=dict)
    invalid_reasons: dict[str, int] = field(default_factory=dict)
    facility_endpoint_configured: bool | None = None
    facility_endpoint_status: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "pages_requested": self.pages_requested,
            "records_received": self.records_received,
            "records_matched": self.records_matched,
            "records_normalized": self.records_normalized,
            "records_invalid": self.records_invalid,
            "duplicates": self.duplicates,
            "api_errors": self.api_errors,
            "total_count": self.total_count,
            "source_health": self.source_health,
            "endpoint_groups": self.endpoint_groups,
            "invalid_reasons": self.invalid_reasons,
            "facility_endpoint_configured": self.facility_endpoint_configured,
            "facility_endpoint_status": self.facility_endpoint_status,
        }


class D2BClient:
    def __init__(
        self,
        *,
        service_key: str | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        request_get: Any | None = None,
    ) -> None:
        self.service_key = (service_key if service_key is not None else os.getenv(D2B_SERVICE_KEY_ENV, "")).strip()
        self.page_size = page_size
        self.request_get = request_get

    def configured(self) -> bool:
        return bool(self.service_key)


class D2BProcurementAdapter(ExternalBusinessSourceAdapter):
    source = D2B_SOURCE
    api_key_env = D2B_SERVICE_KEY_ENV
    endpoint_env = None

    def __init__(self, resource: D2BResource, *, collected_at: str | None = None) -> None:
        self.resource = resource
        self.collected_at = collected_at

    def collect_raw_records(self) -> list[dict[str, Any]]:
        raise NotImplementedError("Use D2BPilotRunner for bounded staging collection")

    def normalize_raw_record(self, raw: dict[str, Any]) -> NormalizedBusinessRecord:
        external_part = _pick(raw, *_external_id_keys(self.resource.source_record_type))
        external_id = f"{D2B_SOURCE}:{self.resource.source_record_type}:{external_part}" if external_part else ""
        return NormalizedBusinessRecord(
            source=D2B_SOURCE,
            source_record_type=self.resource.source_record_type,
            external_id=external_id,
            title=_pick(raw, "title"),
            issuing_organization=_pick(raw, "organization") or "방위사업청",
            category=_pick(raw, "business_type", "business_subtype", "category"),
            region=_pick(raw, "region", "organization"),
            estimated_amount=parse_amount(_pick(raw, "amount")),
            currency="KRW",
            published_at=_parse_d2b_date(_pick(raw, "posted_at", "order_month")),
            deadline_at=_parse_d2b_date(_pick(raw, "due_at", "order_month")),
            status=_pick(raw, "progress_status", "notice_status"),
            contract_method=_pick(raw, "contract_method", "bid_method"),
            source_url=_pick(raw, "url"),
            collected_at=self.collected_at or self.collected_now(),
            source_updated_at=_parse_d2b_date(_pick(raw, "source_updated_at")),
        )


class D2BPilotRunner:
    def __init__(self, *, client: D2BClient) -> None:
        self.client = client

    def collect(
        self,
        *,
        resource_names: list[str],
        plan_from: date,
        plan_to: date,
        bid_from: date,
        bid_to: date,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> tuple[list[NormalizedBusinessRecord], dict[str, Any]]:
        started_at = _now()
        seen: set[tuple[str, str, str]] = set()
        records: list[NormalizedBusinessRecord] = []
        resource_summaries: dict[str, D2BCollectionSummary] = {
            name: D2BCollectionSummary() for name in resource_names
        }

        for resource_name in resource_names:
            resource = D2B_RESOURCES[resource_name]
            summary = resource_summaries[resource_name]
            adapter = D2BProcurementAdapter(resource, collected_at=started_at)

            if not self.client.configured():
                summary.api_errors.append({"category": "missing_secret", "required_secret": D2B_SERVICE_KEY_ENV})
                summary.source_health = "failed"
                continue

            try:
                raw_records = self._collect_raw_resource(resource, summary, plan_from, plan_to, bid_from, bid_to, max_pages)
            except Exception as exc:  # noqa: BLE001 - sanitized summary keeps live pilot from leaking request details.
                summary.api_errors.append(_diagnostic_from_exception(exc, _last_endpoint(summary)))
                summary.source_health = "failed"
                continue

            summary.records_matched = len(raw_records)
            for raw in raw_records:
                try:
                    normalized = adapter.normalize_raw_record(raw)
                except ValueError as exc:
                    summary.records_invalid += 1
                    reason = _validation_error_reason(raw, exc)
                    summary.invalid_reasons[reason] = summary.invalid_reasons.get(reason, 0) + 1
                    continue
                key = (normalized.source, normalized.source_record_type, normalized.external_id)
                if key in seen:
                    summary.duplicates += 1
                    continue
                seen.add(key)
                summary.records_normalized += 1
                records.append(normalized)

            summary.source_health = _resource_health(summary)

        finished_at = _now()
        summary_payload = {
            "source": D2B_SOURCE,
            "collection_started_at": started_at,
            "collection_finished_at": finished_at,
            "resources": {name: summary.as_dict() for name, summary in resource_summaries.items()},
            "records_normalized": len(records),
            "overall_health": _overall_health(resource_summaries),
        }
        return records, summary_payload

    def _collect_raw_resource(
        self,
        resource: D2BResource,
        summary: D2BCollectionSummary,
        plan_from: date,
        plan_to: date,
        bid_from: date,
        bid_to: date,
        max_pages: int,
    ) -> list[dict[str, Any]]:
        if resource.name == "procurement_plan":
            collector = _configured_plan_collector(self.client)
            summary.facility_endpoint_configured = bool(collector.facility_endpoint)
            summary.facility_endpoint_status = (
                "configured"
                if collector.facility_endpoint
                else "not_configured_official_facility_operation_not_confirmed"
            )
            endpoints = [("domestic_procurement_plan", "국내 조달계획", collector.domestic_endpoint)]
            if collector.facility_endpoint:
                endpoints.append(("facility_procurement_plan", "시설 조달계획", collector.facility_endpoint))
            begin, end = plan_from.strftime("%Y%m"), plan_to.strftime("%Y%m")
            return _collect_with_existing_collector(collector, summary, endpoints, begin, end, max_pages)

        collector = _configured_bid_collector(self.client)
        endpoints = [("domestic_bid_notice", "국내 경쟁입찰공고", collector.domestic_endpoint)]
        if collector.foreign_endpoint:
            endpoints.append(("foreign_bid_notice", "국외 경쟁입찰공고", collector.foreign_endpoint))
        if collector.public_private_endpoint:
            endpoints.append(("public_private_bid_notice", "공개수의 협상계획", collector.public_private_endpoint))
        begin, end = bid_from.strftime("%Y%m%d"), bid_to.strftime("%Y%m%d")
        return _collect_with_existing_collector(collector, summary, endpoints, begin, end, max_pages)


def write_staging_outputs(records: list[NormalizedBusinessRecord], summary: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "d2b_records.json").write_text(
        json.dumps([record.as_dict() for record in records], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "d2b_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _configured_plan_collector(client: D2BClient) -> D2BPlanCollector:
    collector = D2BPlanCollector()
    collector.service_key = client.service_key
    collector.page_size = client.page_size
    if client.request_get is not None:
        collector._request_get = client.request_get  # type: ignore[attr-defined]
    return collector


def _configured_bid_collector(client: D2BClient) -> D2BBidCollector:
    collector = D2BBidCollector()
    collector.service_key = client.service_key
    collector.page_size = client.page_size
    if client.request_get is not None:
        collector._request_get = client.request_get  # type: ignore[attr-defined]
    return collector


def _collect_with_existing_collector(
    collector: Any,
    summary: D2BCollectionSummary,
    endpoints: list[tuple[str, str, str]],
    begin: str,
    end: str,
    max_pages: int,
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    max_pages = max(1, max_pages)

    for endpoint_key, category, endpoint in endpoints:
        endpoint_counts = summary.endpoint_groups.setdefault(
            endpoint_key,
            {
                "pages_requested": 0,
                "records_received": 0,
                "records_matched": 0,
            },
        )
        page_no = 1
        total_pages = 1
        while page_no <= min(total_pages, max_pages):
            summary.pages_requested += 1
            endpoint_counts["pages_requested"] += 1
            endpoint_counts["endpoint_scheme"] = urlparse(endpoint).scheme  # type: ignore[assignment]
            endpoint_counts["endpoint_host"] = urlparse(endpoint).hostname or ""  # type: ignore[assignment]
            endpoint_counts["last_endpoint"] = endpoint  # type: ignore[assignment]
            try:
                payload = _request_page(collector, endpoint, page_no, begin, end)
                total_count, items = collector._extract_payload(payload)
            except Exception:
                raise
            summary.total_count = total_count
            summary.records_received += len(items)
            endpoint_counts["records_received"] += len(items)
            total_pages = max(1, math.ceil(total_count / max(collector.page_size, 1)))
            for item in items:
                raw_item = collector._to_raw_item(category, item)
                if collector._is_relevant(raw_item):
                    matched.append(raw_item)
                    endpoint_counts["records_matched"] += 1
            page_no += 1

    return matched


def _request_page(collector: Any, endpoint: str, page_no: int, begin: str, end: str) -> dict[str, Any]:
    request_get = getattr(collector, "_request_get", None)
    if request_get is None:
        return collector._request(endpoint, page_no, begin, end)
    original_get = requests.get
    try:
        requests.get = request_get
        return collector._request(endpoint, page_no, begin, end)
    finally:
        requests.get = original_get


def _resource_health(summary: D2BCollectionSummary) -> str:
    if summary.api_errors:
        return "failed"
    if summary.records_normalized > 0:
        return "healthy"
    return "healthy_empty"


def _overall_health(summaries: dict[str, D2BCollectionSummary]) -> str:
    if any(summary.source_health == "failed" for summary in summaries.values()):
        return "failed"
    if any(summary.records_normalized > 0 for summary in summaries.values()):
        return "healthy"
    return "healthy_empty"


def _validation_error_reason(raw: dict[str, Any], exc: ValueError) -> str:
    if not _pick(raw, "source_record_id", "dcs_no", "plan_no", "notice_no", "bid_no"):
        return "missing_external_id"
    if not _pick(raw, "title"):
        return "missing_title"
    message = str(exc).lower()
    if "external_id" in message:
        return "missing_external_id"
    if "title" in message:
        return "missing_title"
    return "other_validation_error"


def _diagnostic_from_exception(exc: Exception, endpoint: str | None) -> dict[str, str]:
    message = str(exc)
    result_code = _result_code_from_message(message)
    category = "api_error"
    if isinstance(exc, requests.RequestException):
        category = "transport_error"
    elif "JSON" in message or "XML" in message or "빈 응답" in message:
        category = "response_parse_error"
    diagnostic = _diagnostic(category, endpoint, exception=exc, result_code=result_code)
    return diagnostic


def _diagnostic(
    category: str,
    endpoint: str | None,
    *,
    exception: BaseException | None = None,
    result_code: str | None = None,
) -> dict[str, str]:
    parsed = urlparse(endpoint or "")
    diagnostic: dict[str, str] = {"category": category}
    if result_code:
        diagnostic["result_code"] = result_code
    if exception is not None:
        diagnostic["exception_type"] = type(exception).__name__
    if parsed.scheme:
        diagnostic["endpoint_scheme"] = parsed.scheme
    if parsed.hostname:
        diagnostic["endpoint_host"] = parsed.hostname
    return diagnostic


def _result_code_from_message(message: str) -> str | None:
    match = re.search(r"API 오류:\s*([A-Za-z0-9_-]+)", message)
    return match.group(1) if match else None


def _last_endpoint(summary: D2BCollectionSummary) -> str | None:
    for payload in reversed(list(summary.endpoint_groups.values())):
        endpoint = payload.get("last_endpoint")
        if isinstance(endpoint, str):
            return endpoint
    return None


def _external_id_keys(record_type: str) -> tuple[str, ...]:
    if record_type == "procurement_plan":
        return ("source_record_id", "dcs_no", "plan_no", "bid_no")
    return ("source_record_id", "notice_no", "bid_no")


def _pick(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _parse_d2b_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in (
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%Y%m%d",
        "%Y%m",
        "%Y-%m-%d %H:%M:%S",
        "%Y.%m.%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y%m%d%H%M",
    ):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.date().isoformat()
        except ValueError:
            continue
    return text


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sleep_for_live_retry(attempt: int) -> None:
    time.sleep(0.5 * (attempt + 1))
