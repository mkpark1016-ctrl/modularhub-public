from __future__ import annotations

import json
import math
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests
from requests.exceptions import ConnectionError, ConnectTimeout, HTTPError, ReadTimeout, Timeout

from src.collectors.d2b_bid import calculate_d2b_bid_relevance
from src.collectors.d2b_plan import calculate_d2b_relevance

from .base import ExternalBusinessSourceAdapter, NormalizedBusinessRecord, parse_amount


D2B_SOURCE = "d2b"
D2B_SERVICE_KEY_ENV = "DATA_GO_KR_SERVICE_KEY"
DEFAULT_PAGE_SIZE = 50
DEFAULT_MAX_PAGES = 3
DEFAULT_LOOKBACK_DAYS = 90
DEFAULT_LOOKAHEAD_MONTHS = 12
DEFAULT_CONNECT_TIMEOUT_SECONDS = 10
DEFAULT_READ_TIMEOUT_SECONDS = 30
MAX_REQUEST_ATTEMPTS = 3
D2B_GW_PLAN_BASE_ENDPOINT = "https://apis.data.go.kr/1690000/PrcurePlanInfoService"
D2B_GW_BID_BASE_ENDPOINT = "https://apis.data.go.kr/1690000/BidPblancInfoService"
D2B_GW_CODE_BASE_ENDPOINT = "https://apis.data.go.kr/1690000/CodeInqireService"


@dataclass(frozen=True)
class D2BOperation:
    name: str
    label: str
    endpoint_env: str
    default_endpoint: str
    date_start_param: str
    date_end_param: str
    date_format: str

    def endpoint(self) -> str:
        return os.getenv(self.endpoint_env, self.default_endpoint).strip() or self.default_endpoint


@dataclass(frozen=True)
class D2BResource:
    name: str
    source_record_type: str
    operations: tuple[D2BOperation, ...]


D2B_RESOURCES: dict[str, D2BResource] = {
    "procurement_plan": D2BResource(
        name="procurement_plan",
        source_record_type="procurement_plan",
        operations=(
            D2BOperation(
                name="getFcltyPrcurePlanList",
                label="facility_procurement_plan",
                endpoint_env="D2B_GW_PLAN_FACILITY_ENDPOINT",
                default_endpoint=f"{D2B_GW_PLAN_BASE_ENDPOINT}/getFcltyPrcurePlanList",
                date_start_param="orderPrearngeMtBegin",
                date_end_param="orderPrearngeMtEnd",
                date_format="%Y%m",
            ),
        ),
    ),
    "bid_notice": D2BResource(
        name="bid_notice",
        source_record_type="bid_notice",
        operations=(
            D2BOperation(
                name="getFcltyCmpetBidPblancList",
                label="facility_competitive_bid_notice",
                endpoint_env="D2B_GW_BID_FACILITY_COMPETITIVE_ENDPOINT",
                default_endpoint=f"{D2B_GW_BID_BASE_ENDPOINT}/getFcltyCmpetBidPblancList",
                date_start_param="anmtDateBegin",
                date_end_param="anmtDateEnd",
                date_format="%Y%m%d",
            ),
            D2BOperation(
                name="getFcltyOthbcVltrnNtatPlanList",
                label="facility_private_negotiation_plan",
                endpoint_env="D2B_GW_BID_FACILITY_PRIVATE_ENDPOINT",
                default_endpoint=f"{D2B_GW_BID_BASE_ENDPOINT}/getFcltyOthbcVltrnNtatPlanList",
                date_start_param="anmtDateBegin",
                date_end_param="anmtDateEnd",
                date_format="%Y%m%d",
            ),
        ),
    ),
}


class D2BApiError(RuntimeError):
    def __init__(self, result_code: str, result_message: str, *, endpoint: str | None = None) -> None:
        super().__init__(f"D2B GW API error: {result_code} {result_message}".strip())
        self.result_code = result_code
        self.result_message = result_message
        self.diagnostic = _diagnostic(_category_for_result_code(result_code), endpoint, result_code=result_code)


class D2BParseError(RuntimeError):
    def __init__(self, message: str, *, endpoint: str | None = None) -> None:
        super().__init__(message)
        self.diagnostic = _diagnostic("response_parse_error", endpoint)


class D2BTransportError(RuntimeError):
    def __init__(self, message: str, *, diagnostic: dict[str, str]) -> None:
        super().__init__(message)
        self.diagnostic = diagnostic


@dataclass(frozen=True)
class D2BPayload:
    result_code: str | None
    result_message: str | None
    total_count: int
    items: list[dict[str, str]]
    response_format: str


@dataclass(frozen=True)
class D2BPageResult:
    operation: D2BOperation
    page_no: int
    page_size: int
    http_status: int
    payload: D2BPayload
    endpoint: str


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
    operation_counts: dict[str, dict[str, Any]] = field(default_factory=dict)
    invalid_reasons: dict[str, int] = field(default_factory=dict)
    primary_endpoint_family: str = "d2b_gw_facility"
    legacy_endpoint_used: bool = False

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
            "operation_counts": self.operation_counts,
            "invalid_reasons": self.invalid_reasons,
            "primary_endpoint_family": self.primary_endpoint_family,
            "legacy_endpoint_used": self.legacy_endpoint_used,
        }


RequestGet = Callable[..., Any]
SleepFunc = Callable[[int], None]


class D2BClient:
    def __init__(
        self,
        *,
        service_key: str | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        timeout_seconds: int | tuple[int, int] = DEFAULT_READ_TIMEOUT_SECONDS,
        connect_timeout_seconds: int = DEFAULT_CONNECT_TIMEOUT_SECONDS,
        max_attempts: int = MAX_REQUEST_ATTEMPTS,
        request_get: RequestGet | None = None,
        sleep_func: SleepFunc | None = None,
    ) -> None:
        self.service_key = (service_key if service_key is not None else os.getenv(D2B_SERVICE_KEY_ENV, "")).strip()
        self.page_size = page_size
        self.timeout = _timeout_tuple(timeout_seconds, connect_timeout_seconds)
        self.max_attempts = max(1, max_attempts)
        self.request_get = request_get or requests.get
        self.sleep_func = sleep_func or _sleep_before_retry

    def configured(self) -> bool:
        return bool(self.service_key)

    def fetch_page(self, operation: D2BOperation, *, page_no: int, from_date: date, to_date: date) -> D2BPageResult:
        if not self.service_key:
            raise RuntimeError(f"{D2B_SERVICE_KEY_ENV} is not configured")
        endpoint = operation.endpoint()
        params = {
            "serviceKey": self.service_key,
            "pageNo": page_no,
            "numOfRows": self.page_size,
            operation.date_start_param: from_date.strftime(operation.date_format),
            operation.date_end_param: to_date.strftime(operation.date_format),
        }
        response = self._get_with_retries(endpoint, params=params)
        payload = parse_d2b_response(
            response.content,
            encoding=getattr(response, "encoding", None),
            endpoint=endpoint,
        )
        return D2BPageResult(
            operation=operation,
            page_no=page_no,
            page_size=self.page_size,
            http_status=int(getattr(response, "status_code", 0)),
            payload=payload,
            endpoint=endpoint,
        )

    def _get_with_retries(self, endpoint: str, *, params: dict[str, Any]) -> Any:
        last_error: BaseException | None = None
        for attempt in range(self.max_attempts):
            try:
                response = self.request_get(endpoint, params=params, timeout=self.timeout)
                response.raise_for_status()
                return response
            except (ConnectTimeout, ConnectionError, Timeout) as exc:
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    self.sleep_func(attempt)
                    continue
                break
            except HTTPError as exc:
                last_error = exc
                status_code = _status_code_from_http_error(exc)
                if status_code is not None and status_code >= 500 and attempt + 1 < self.max_attempts:
                    self.sleep_func(attempt)
                    continue
                raise D2BTransportError(
                    "D2B GW HTTP response failed",
                    diagnostic=_diagnostic(
                        "transport_error",
                        endpoint,
                        exception=exc,
                        attempt_count=attempt + 1,
                        http_status=status_code,
                        transport_category=_transport_category(exc, status_code=status_code),
                    ),
                ) from exc
            except requests.RequestException as exc:
                last_error = exc
                raise D2BTransportError(
                    "D2B GW transport request failed",
                    diagnostic=_diagnostic(
                        "transport_error",
                        endpoint,
                        exception=exc,
                        attempt_count=attempt + 1,
                        transport_category=_transport_category(exc),
                    ),
                ) from exc

        raise D2BTransportError(
            "D2B GW transport request failed",
            diagnostic=_diagnostic(
                "transport_error",
                endpoint,
                exception=last_error,
                attempt_count=self.max_attempts,
                transport_category=_transport_category(last_error),
            ),
        ) from last_error


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
            title=_pick(raw, *_title_keys(self.resource.source_record_type)),
            issuing_organization=_pick(raw, *_organization_keys()) or "방위사업청",
            category=_pick(raw, *_category_keys(self.resource.source_record_type)),
            region=_pick(raw, "orntNm", "orderInsttNm", "region", "areaNm"),
            estimated_amount=parse_amount(_pick(raw, *_amount_keys(self.resource.source_record_type))),
            currency="KRW",
            published_at=_parse_d2b_date(_pick(raw, *_published_at_keys(self.resource.source_record_type))),
            deadline_at=_parse_d2b_date(_pick(raw, *_deadline_at_keys(self.resource.source_record_type))),
            status=_pick(raw, "progrsSttus", "progressStatus", "progress_status", "pblancSe", "bidProgrsStatus", "sttusNm"),
            contract_method=_pick(raw, "cntrctMth", "cntrctMthNm", "contractMethod", "contractMthd"),
            source_url=_pick(raw, "url", "source_url") or _source_url(self.resource.source_record_type, external_part),
            collected_at=self.collected_at or self.collected_now(),
            source_updated_at=_parse_d2b_date(_pick(raw, "chgDt", "chgDttm", "updtDt", "updatedAt")),
        )


class D2BPilotRunner:
    def __init__(self, *, client: D2BClient, resources: dict[str, D2BResource] | None = None) -> None:
        self.client = client
        self.resources = resources or D2B_RESOURCES

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
            resource = self.resources[resource_name]
            adapter = D2BProcurementAdapter(resource, collected_at=started_at)
            summary = resource_summaries[resource_name]
            if not self.client.configured():
                summary.api_errors.append({"category": "missing_secret", "required_secret": D2B_SERVICE_KEY_ENV})
                summary.source_health = "failed"
                continue

            from_date, to_date = (plan_from, plan_to) if resource.name == "procurement_plan" else (bid_from, bid_to)
            for operation in resource.operations:
                operation_counts = _operation_counts(summary, operation)
                parsed_endpoint = urlparse(operation.endpoint())
                operation_counts["endpoint_scheme"] = parsed_endpoint.scheme
                operation_counts["endpoint_host"] = parsed_endpoint.hostname or ""
                total_pages = 1
                page_no = 1
                while page_no <= min(total_pages, max(1, max_pages)):
                    try:
                        page = self.client.fetch_page(operation, page_no=page_no, from_date=from_date, to_date=to_date)
                    except D2BApiError as exc:
                        summary.api_errors.append(exc.diagnostic)
                        summary.source_health = "failed"
                        break
                    except D2BParseError as exc:
                        summary.api_errors.append(exc.diagnostic)
                        summary.source_health = "failed"
                        break
                    except D2BTransportError as exc:
                        summary.api_errors.append(exc.diagnostic)
                        summary.source_health = "failed"
                        break
                    except RuntimeError as exc:
                        summary.api_errors.append(_diagnostic_from_exception(exc, operation.endpoint()))
                        summary.source_health = "failed"
                        break

                    summary.pages_requested += 1
                    operation_counts["pages_requested"] += 1
                    operation_counts["endpoint_scheme"] = urlparse(page.endpoint).scheme
                    operation_counts["endpoint_host"] = urlparse(page.endpoint).hostname or ""
                    summary.total_count = page.payload.total_count
                    summary.records_received += len(page.payload.items)
                    operation_counts["records_received"] += len(page.payload.items)
                    total_pages = max(1, math.ceil(page.payload.total_count / max(page.page_size, 1)))

                    for raw in page.payload.items:
                        if not _is_relevant(resource.source_record_type, raw):
                            continue
                        summary.records_matched += 1
                        operation_counts["records_matched"] += 1
                        try:
                            normalized = adapter.normalize_raw_record(raw)
                        except ValueError as exc:
                            summary.records_invalid += 1
                            operation_counts["records_invalid"] += 1
                            reason = _validation_error_reason(resource.source_record_type, raw, exc)
                            summary.invalid_reasons[reason] = summary.invalid_reasons.get(reason, 0) + 1
                            continue
                        key = (normalized.source, normalized.source_record_type, normalized.external_id)
                        if key in seen:
                            summary.duplicates += 1
                            operation_counts["duplicates"] += 1
                            continue
                        seen.add(key)
                        summary.records_normalized += 1
                        operation_counts["records_normalized"] += 1
                        records.append(normalized)
                    page_no += 1

            if summary.source_health != "failed":
                summary.source_health = _resource_health(summary)

        finished_at = _now()
        summary_payload = {
            "source": D2B_SOURCE,
            "collection_started_at": started_at,
            "collection_finished_at": finished_at,
            "resources": {name: summary.as_dict() for name, summary in resource_summaries.items()},
            "records_normalized": len(records),
            "overall_health": _overall_health(resource_summaries),
            "legacy_endpoint_used": any(summary.legacy_endpoint_used for summary in resource_summaries.values()),
        }
        return records, summary_payload


def parse_d2b_response(content: bytes | str, *, encoding: str | None = None, endpoint: str | None = None) -> D2BPayload:
    if isinstance(content, bytes):
        text = content.decode(encoding or "utf-8", errors="replace").strip()
    else:
        text = content.strip()
    if not text:
        return D2BPayload(result_code=None, result_message=None, total_count=0, items=[], response_format="empty")

    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise D2BParseError("D2B GW JSON response could not be parsed", endpoint=endpoint) from exc
        return _payload_from_json(payload, endpoint=endpoint)

    xml_text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text).strip()
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise D2BParseError("D2B GW XML response could not be parsed", endpoint=endpoint) from exc

    result_code = _find_text(root, "resultCode")
    result_message = _find_text(root, "resultMsg") or _find_text(root, "resultMag")
    if result_code and result_code not in {"00", "0"}:
        raise D2BApiError(result_code, result_message or "", endpoint=endpoint)
    items = []
    for item_node in _iter_local(root, "item"):
        item = {_local_name(child.tag): (child.text or "").strip() for child in list(item_node)}
        if item:
            items.append(item)
    return D2BPayload(
        result_code=result_code or None,
        result_message=result_message or None,
        total_count=_to_int(_find_text(root, "totalCount")),
        items=items,
        response_format="xml",
    )


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


def _payload_from_json(payload: dict[str, Any], *, endpoint: str | None) -> D2BPayload:
    response = payload.get("response") or payload
    header = response.get("header") or {}
    result_code = str(header.get("resultCode") or payload.get("resultCode") or "")
    result_message = str(header.get("resultMsg") or header.get("resultMag") or payload.get("resultMsg") or "")
    if result_code and result_code not in {"00", "0"}:
        raise D2BApiError(result_code, result_message, endpoint=endpoint)
    body = response.get("body") or payload
    total_count = _to_int(body.get("totalCount"))
    items = body.get("items", [])
    if isinstance(items, dict):
        item = items.get("item", items)
        items = item if isinstance(item, list) else [item]
    if not isinstance(items, list):
        items = []
    return D2BPayload(
        result_code=result_code or None,
        result_message=result_message or None,
        total_count=total_count,
        items=[_stringify_values(item) for item in items if isinstance(item, dict)],
        response_format="json",
    )


def _stringify_values(item: dict[str, Any]) -> dict[str, str]:
    return {str(key): "" if value is None else str(value).strip() for key, value in item.items()}


def _operation_counts(summary: D2BCollectionSummary, operation: D2BOperation) -> dict[str, Any]:
    return summary.operation_counts.setdefault(
        operation.name,
        {
            "pages_requested": 0,
            "records_received": 0,
            "records_matched": 0,
            "records_normalized": 0,
            "records_invalid": 0,
            "duplicates": 0,
            "endpoint_scheme": "",
            "endpoint_host": "",
        },
    )


def _is_relevant(record_type: str, raw: dict[str, Any]) -> bool:
    mapped = {
        "title": _pick(raw, *_title_keys(record_type)),
        "summary": " ".join(str(value or "") for value in raw.values()),
        "description": " ".join(str(value or "") for value in raw.values()),
        "amount": _pick(raw, *_amount_keys(record_type)),
        "execution_type": _pick(raw, *_category_keys(record_type)),
        "progress_status": _pick(raw, "progrsSttus", "progressStatus", "pblancSe", "bidProgrsStatus", "sttusNm"),
        "organization": _pick(raw, *_organization_keys()),
        "business_type": _pick(raw, *_category_keys(record_type)),
    }
    if record_type == "procurement_plan":
        return calculate_d2b_relevance(mapped) > 0
    return calculate_d2b_bid_relevance(mapped) > 0


def _resource_health(summary: D2BCollectionSummary) -> str:
    if summary.api_errors:
        return "failed"
    if summary.records_normalized > 0:
        return "healthy"
    if summary.records_matched > 0 and summary.records_invalid > 0:
        return "schema_mismatch"
    return "healthy_empty"


def _overall_health(summaries: dict[str, D2BCollectionSummary]) -> str:
    if any(summary.source_health == "failed" for summary in summaries.values()):
        return "failed"
    if any(summary.source_health == "schema_mismatch" for summary in summaries.values()):
        return "schema_mismatch"
    if any(summary.records_normalized > 0 for summary in summaries.values()):
        return "healthy"
    return "healthy_empty"


def is_d2b_acceptance_failure(summary: dict[str, Any]) -> bool:
    return summary.get("overall_health") in {"failed", "schema_mismatch"}


def _validation_error_reason(record_type: str, raw: dict[str, Any], exc: ValueError) -> str:
    if not _pick(raw, *_external_id_keys(record_type)):
        return "missing_external_id"
    if not _pick(raw, *_title_keys(record_type)):
        return "missing_title"
    message = str(exc).lower()
    if "external_id" in message:
        return "missing_external_id"
    if "title" in message:
        return "missing_title"
    return "other_validation_error"


def _diagnostic_from_exception(exc: Exception, endpoint: str | None) -> dict[str, str]:
    if isinstance(exc.__cause__, requests.RequestException):
        return _diagnostic("transport_error", endpoint, exception=exc.__cause__, transport_category=_transport_category(exc.__cause__))
    return _diagnostic("api_error", endpoint, exception=exc)


def _diagnostic(
    category: str,
    endpoint: str | None,
    *,
    exception: BaseException | None = None,
    result_code: str | None = None,
    attempt_count: int | None = None,
    http_status: int | None = None,
    transport_category: str | None = None,
) -> dict[str, str]:
    parsed = urlparse(endpoint or "")
    diagnostic: dict[str, str] = {"category": category}
    if result_code:
        diagnostic["result_code"] = result_code
    if attempt_count is not None:
        diagnostic["attempt_count"] = str(attempt_count)
    if http_status is not None:
        diagnostic["http_status"] = str(http_status)
    if transport_category:
        diagnostic["transport_category"] = transport_category
    if exception is not None:
        diagnostic["exception_type"] = type(exception).__name__
        diagnostic["final_exception_type"] = type(exception).__name__
    if parsed.scheme:
        diagnostic["endpoint_scheme"] = parsed.scheme
    if parsed.hostname:
        diagnostic["endpoint_host"] = parsed.hostname
    return diagnostic


def _timeout_tuple(timeout_seconds: int | tuple[int, int], connect_timeout_seconds: int) -> tuple[int, int]:
    if isinstance(timeout_seconds, tuple):
        return timeout_seconds
    return (min(connect_timeout_seconds, timeout_seconds), timeout_seconds)


def _sleep_before_retry(attempt: int) -> None:
    time.sleep(1 if attempt == 0 else 3)


def _status_code_from_http_error(exc: HTTPError) -> int | None:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    try:
        return int(status_code) if status_code is not None else None
    except (TypeError, ValueError):
        return None


def _transport_category(exc: BaseException | None, *, status_code: int | None = None) -> str:
    if status_code is not None:
        if status_code >= 500:
            return "http_5xx"
        return "http_error"
    if isinstance(exc, ConnectTimeout):
        return "connect_timeout"
    if isinstance(exc, ReadTimeout):
        return "read_timeout"
    if isinstance(exc, Timeout):
        return "timeout"
    if isinstance(exc, ConnectionError):
        return "connection_error"
    if isinstance(exc, requests.RequestException):
        return "request_exception"
    return "unknown"


def _category_for_result_code(result_code: str) -> str:
    if result_code == "20":
        return "service_access_denied"
    if result_code == "30":
        return "auth_error"
    if result_code in {"22", "23"}:
        return "rate_limited"
    if result_code == "10":
        return "invalid_request"
    return "api_error"


def _external_id_keys(record_type: str) -> tuple[str, ...]:
    if record_type == "procurement_plan":
        return ("dcsNo", "judgmntNo", "dcsnNo", "dcsNoList", "cntrwkNo", "source_record_id")
    return ("bidNo", "pblancNo", "bidNtceNo", "ntatPlanNo", "source_record_id")


def _title_keys(record_type: str) -> tuple[str, ...]:
    if record_type == "procurement_plan":
        return ("reprsntPrdlstNm", "representPrdlstNm", "prcurePlanNm", "planNm", "prdctNm", "itemNm", "prdlstNm", "cntrwkNm", "title")
    return ("bidNm", "bidName", "bidPblancNm", "pblancNm", "ntatPlanNm", "bidNtceNm", "cntrwkNm", "title")


def _organization_keys() -> tuple[str, ...]:
    return ("orntNm", "ornt", "orntCode", "orntCd", "orderInsttNm", "orderAgency", "organization")


def _category_keys(record_type: str) -> tuple[str, ...]:
    if record_type == "procurement_plan":
        return ("excutTy", "excutTyNm", "execType", "bsnsSe", "bsnsSeNm", "cntrwkSe", "business_type", "business_subtype", "category")
    return ("busiDivs", "excutTy", "bsnsSe", "jobSe", "workSe", "bidJobGb", "business_type", "business_subtype", "category")


def _amount_keys(record_type: str) -> tuple[str, ...]:
    if record_type == "procurement_plan":
        return ("bdgtAmount", "budgetAmount", "bdgtAmt", "budgetAmt", "estmtAmount", "amount")
    return ("bsicExpt", "budgetAmount", "baseAmnt", "bdgtAmount", "presmptPrce", "bssamt", "amount")


def _published_at_keys(record_type: str) -> tuple[str, ...]:
    if record_type == "procurement_plan":
        return ("regDt", "rgstDt", "frstRegDt", "planRegDt", "orderPrearngeMt", "orderPrerngeMt", "orderPrearngeYm", "posted_at")
    return ("pblancDate", "ntatPlanDate", "anmtDate", "bidPblancDate", "bidNtceDate", "posted_at")


def _deadline_at_keys(record_type: str) -> tuple[str, ...]:
    if record_type == "procurement_plan":
        return ("orderPrearngeMt", "orderPrerngeMt", "orderPrearngeYm", "orderPlanDt", "due_at")
    return ("biddocPresentnClosDt", "prqudoPresentnClosDt", "bidDcPeoClseDttm", "bidSubmitClseDttm", "bidClseDttm", "ntatClosDttm", "due_at")


def _source_url(_record_type: str, _external_part: str) -> str:
    return "https://www.d2b.go.kr/"


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


def _find_text(root: ET.Element, tag: str) -> str:
    for node in root.iter():
        if _local_name(node.tag) == tag:
            return (node.text or "").strip()
    return ""


def _iter_local(root: ET.Element, tag: str):
    for node in root.iter():
        if _local_name(node.tag) == tag:
            yield node


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _to_int(value: Any) -> int:
    try:
        return int(str(value or "0").replace(",", ""))
    except ValueError:
        return 0


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
