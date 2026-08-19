from __future__ import annotations

import json
import math
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse

import requests

from .base import ExternalBusinessSourceAdapter, NormalizedBusinessRecord, parse_amount, parse_date


G2B_SERVICE_KEY_ENV = "DATA_GO_KR_SERVICE_KEY"
G2B_SOURCE = "g2b"
DEFAULT_PAGE_SIZE = 10
DEFAULT_TIMEOUT_SECONDS = 30
MAX_PAGES = 3
G2B_PORTAL_URL = "https://www.g2b.go.kr"
G2B_PLAN_BASE_ENDPOINT = "https://apis.data.go.kr/1230000/ao/OrderPlanSttusService"
G2B_PRE_SPEC_BASE_ENDPOINT = "https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService"
LH_AGENCY_IDENTIFIER = "B552555"
LH_AGENCY_IDENTIFIER_SOURCE = "g2b_demand_institution_code"
LH_AGENCY_NAME = "한국토지주택공사"
LH_AGENCY_CODES = frozenset({LH_AGENCY_IDENTIFIER})
LH_AGENCY_NAMES = frozenset({LH_AGENCY_NAME})
LH_AGENCY_ALIASES = frozenset({"LH", "한국토지주택공사 본사"})


@dataclass(frozen=True)
class G2BResource:
    name: str
    source_record_type: str
    endpoint_env: str
    default_base_endpoint: str
    operations: tuple[str, ...]
    agency_filter_mode: str

    def base_endpoint(self) -> str:
        return os.getenv(self.endpoint_env, self.default_base_endpoint).strip().rstrip("/") or self.default_base_endpoint

    def endpoints(self) -> list[str]:
        base = self.base_endpoint()
        return [f"{base}/{operation}" for operation in self.operations]


G2B_RESOURCES: dict[str, G2BResource] = {
    "g2b_procurement_plan": G2BResource(
        name="g2b_procurement_plan",
        source_record_type="procurement_plan",
        endpoint_env="G2B_PLAN_BASE_ENDPOINT",
        default_base_endpoint=G2B_PLAN_BASE_ENDPOINT,
        operations=(
            "getOrderPlanSttusListCnstwkPPSSrch",
            "getOrderPlanSttusListServcPPSSrch",
            "getOrderPlanSttusListThngPPSSrch",
        ),
        agency_filter_mode="server_side_agency_code",
    ),
    "g2b_pre_spec": G2BResource(
        name="g2b_pre_spec",
        source_record_type="pre_spec",
        endpoint_env="G2B_PRE_SPEC_BASE_ENDPOINT",
        default_base_endpoint=G2B_PRE_SPEC_BASE_ENDPOINT,
        operations=(
            "getInsttAcctoThngListInfoCnstwk",
            "getInsttAcctoThngListInfoServc",
            "getInsttAcctoThngListInfoThng",
            "getInsttAcctoThngListInfoFrgcpt",
        ),
        agency_filter_mode="institution_endpoint_agency_code",
    ),
}


class G2BApiError(RuntimeError):
    def __init__(self, result_code: str, result_message: str, *, diagnostic: dict[str, str] | None = None) -> None:
        super().__init__(f"G2B API error: {result_code} {result_message}".strip())
        self.result_code = result_code
        self.result_message = result_message
        self.diagnostic = diagnostic or {"category": "api_error", "result_code": result_code}


class G2BParseError(RuntimeError):
    def __init__(self, message: str, *, diagnostic: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.diagnostic = diagnostic or {"category": "response_parse_error"}


class G2BTransportError(RuntimeError):
    def __init__(self, message: str, *, diagnostic: dict[str, str]) -> None:
        super().__init__(message)
        self.diagnostic = diagnostic


@dataclass(frozen=True)
class G2BPayload:
    result_code: str | None
    result_message: str | None
    total_count: int
    items: list[dict[str, Any]]
    response_format: str


@dataclass(frozen=True)
class G2BPageResult:
    resource: str
    endpoint: str
    operation: str
    page_no: int
    page_size: int
    http_status: int
    payload: G2BPayload


@dataclass
class G2BCollectionSummary:
    pages_requested: int = 0
    records_received: int = 0
    records_normalized: int = 0
    records_invalid: int = 0
    duplicates: int = 0
    api_errors: list[dict[str, str]] = field(default_factory=list)
    http_statuses: list[int] = field(default_factory=list)
    api_result_codes: list[str | None] = field(default_factory=list)
    response_formats: list[str] = field(default_factory=list)
    operations: list[str] = field(default_factory=list)
    total_count: int | None = None
    fallback_used: bool = True
    source_health: str = "healthy"
    records_agency_matched: int = 0
    records_filtered_non_lh: int = 0
    agency_filter_mode: str = ""
    agency_code_verified: bool = bool(LH_AGENCY_CODES)
    agency_identifier: str = LH_AGENCY_IDENTIFIER
    agency_identifier_source: str = LH_AGENCY_IDENTIFIER_SOURCE
    agency_diagnostics: list[dict[str, str]] = field(default_factory=list)
    operation_counts: dict[str, dict[str, int]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "pages_requested": self.pages_requested,
            "records_received": self.records_received,
            "records_normalized": self.records_normalized,
            "records_invalid": self.records_invalid,
            "duplicates": self.duplicates,
            "api_errors": self.api_errors,
            "http_statuses": self.http_statuses,
            "api_result_codes": self.api_result_codes,
            "response_formats": self.response_formats,
            "operations": self.operations,
            "total_count": self.total_count,
            "fallback_used": self.fallback_used,
            "source_health": self.source_health,
            "records_agency_matched": self.records_agency_matched,
            "records_filtered_non_lh": self.records_filtered_non_lh,
            "agency_filter_mode": self.agency_filter_mode,
            "agency_code_verified": self.agency_code_verified,
            "agency_identifier": self.agency_identifier,
            "agency_identifier_source": self.agency_identifier_source,
            "agency_diagnostics": self.agency_diagnostics,
            "operation_counts": self.operation_counts,
        }


RequestGet = Callable[..., Any]


class G2BClient:
    def __init__(
        self,
        *,
        service_key: str | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        request_get: RequestGet | None = None,
    ) -> None:
        self.service_key = (service_key if service_key is not None else os.getenv(G2B_SERVICE_KEY_ENV, "")).strip()
        self.page_size = page_size
        self.timeout_seconds = timeout_seconds
        self.request_get = request_get or requests.get

    def configured(self) -> bool:
        return bool(self.service_key)

    def fetch_page(
        self,
        resource: G2BResource,
        *,
        endpoint: str,
        page_no: int,
        from_date: date,
        to_date: date,
    ) -> G2BPageResult:
        if not self.service_key:
            raise RuntimeError(f"{G2B_SERVICE_KEY_ENV} is not configured")

        params = _request_params(resource.source_record_type, self.service_key, self.page_size, page_no, from_date, to_date)
        try:
            response = self.request_get(endpoint, params=params, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise G2BTransportError(
                "G2B request failed",
                diagnostic=_diagnostic("transport_error", endpoint, exception=exc),
            ) from exc

        payload = parse_g2b_response(response.content, encoding=getattr(response, "encoding", None), endpoint=endpoint)
        return G2BPageResult(
            resource=resource.name,
            endpoint=endpoint,
            operation=_operation_name(endpoint),
            page_no=page_no,
            page_size=self.page_size,
            http_status=int(response.status_code),
            payload=payload,
        )


class G2BProcurementAdapter(ExternalBusinessSourceAdapter):
    source = G2B_SOURCE
    api_key_env = G2B_SERVICE_KEY_ENV
    endpoint_env = None

    def __init__(self, resource: G2BResource, *, collected_at: str | None = None) -> None:
        self.resource = resource
        self.collected_at = collected_at

    def collect_raw_records(self) -> list[dict[str, Any]]:
        raise NotImplementedError("Use G2BFallbackRunner for paginated staging collection")

    def normalize_raw_record(self, raw: dict[str, Any]) -> NormalizedBusinessRecord:
        external_part = _pick(raw, *_external_id_keys(self.resource.source_record_type))
        external_id = f"{G2B_SOURCE}:{self.resource.source_record_type}:{external_part}" if external_part else ""
        return NormalizedBusinessRecord(
            source=G2B_SOURCE,
            source_record_type=self.resource.source_record_type,
            external_id=external_id,
            title=_pick(raw, *_title_keys(self.resource.source_record_type)),
            issuing_organization=_issuing_organization(raw),
            category=_pick(raw, "bsnsDivNm", "bizTypeNm", "business_type", "prdctClsfcNoNm", "srvceDivNm"),
            region=_pick(raw, "cnstwkRgnNm", "insttLctNm", "rgnNm", "regionNm", "areaNm"),
            estimated_amount=parse_amount(_pick(raw, *_amount_keys(self.resource.source_record_type))),
            currency="KRW",
            published_at=_parse_g2b_date(_pick(raw, *_published_at_keys(self.resource.source_record_type))),
            deadline_at=_parse_g2b_date(_pick(raw, *_deadline_at_keys(self.resource.source_record_type))),
            status=_pick(raw, "orderPlanSttusNm", "planSttusNm", "sttusNm", "opninRegistSttusNm", "prgrsSttusNm"),
            contract_method=_pick(raw, "cntrctMthdNm", "contractMethodNm", "cntrctMthNm"),
            source_url=G2B_PORTAL_URL,
            collected_at=self.collected_at or self.collected_now(),
            source_updated_at=_parse_g2b_date(_pick(raw, "chgDt", "updtDt", "modDtm", "updatedAt")),
        )


class G2BFallbackRunner:
    def __init__(self, *, client: G2BClient, resources: dict[str, G2BResource] | None = None) -> None:
        self.client = client
        self.resources = resources or G2B_RESOURCES

    def collect(
        self,
        *,
        resource_names: list[str],
        from_date: date,
        to_date: date,
        max_pages: int = MAX_PAGES,
    ) -> tuple[list[NormalizedBusinessRecord], dict[str, Any]]:
        started_at = _now()
        records: list[NormalizedBusinessRecord] = []
        seen: set[tuple[str, str, str]] = set()
        summaries: dict[str, G2BCollectionSummary] = {name: G2BCollectionSummary() for name in resource_names}

        if not self.client.configured():
            for summary in summaries.values():
                summary.source_health = "failed"
                summary.api_errors.append({"category": "missing_secret", "required_secret": G2B_SERVICE_KEY_ENV})
            return records, _summary_payload(started_at, records, summaries)

        for resource_name in resource_names:
            resource = self.resources[resource_name]
            adapter = G2BProcurementAdapter(resource, collected_at=started_at)
            summary = summaries[resource_name]
            summary.agency_filter_mode = resource.agency_filter_mode
            for endpoint in resource.endpoints():
                total_pages = 1
                page_no = 1
                while page_no <= min(total_pages, max_pages):
                    try:
                        page = self.client.fetch_page(resource, endpoint=endpoint, page_no=page_no, from_date=from_date, to_date=to_date)
                    except G2BApiError as exc:
                        summary.api_errors.append(exc.diagnostic)
                        break
                    except G2BParseError as exc:
                        summary.api_errors.append(exc.diagnostic)
                        break
                    except G2BTransportError as exc:
                        summary.api_errors.append(exc.diagnostic)
                        break

                    summary.pages_requested += 1
                    summary.http_statuses.append(page.http_status)
                    summary.api_result_codes.append(page.payload.result_code)
                    summary.response_formats.append(page.payload.response_format)
                    if page.operation not in summary.operations:
                        summary.operations.append(page.operation)
                    operation_counts = _operation_counts(summary, page.operation)
                    operation_counts["pages_requested"] += 1
                    summary.total_count = (summary.total_count or 0) + page.payload.total_count
                    summary.records_received += len(page.payload.items)
                    operation_counts["records_received"] += len(page.payload.items)
                    total_pages = max(1, math.ceil(page.payload.total_count / max(page.page_size, 1)))

                    for raw in page.payload.items:
                        _append_agency_diagnostic(summary, raw, page.operation)
                        if not is_lh_agency_record(raw):
                            summary.records_filtered_non_lh += 1
                            operation_counts["records_filtered_non_lh"] += 1
                            continue
                        summary.records_agency_matched += 1
                        operation_counts["records_agency_matched"] += 1
                        try:
                            normalized = adapter.normalize_raw_record(raw)
                        except ValueError:
                            summary.records_invalid += 1
                            operation_counts["records_invalid"] += 1
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

            _finalize_source_health(summary)

        return records, _summary_payload(started_at, records, summaries)


def parse_g2b_response(content: bytes | str, *, encoding: str | None = None, endpoint: str | None = None) -> G2BPayload:
    text = content.decode(encoding or "utf-8", errors="replace").strip() if isinstance(content, bytes) else content.strip()
    if not text:
        return G2BPayload(None, None, 0, [], "empty")
    if text.startswith(("{", "[")):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise G2BParseError("G2B JSON response could not be parsed", diagnostic=_diagnostic("response_parse_error", endpoint)) from exc
        return _payload_from_json(payload, endpoint=endpoint)
    return _payload_from_xml(text, endpoint=endpoint)


def is_lh_agency_record(raw: dict[str, Any]) -> bool:
    code = _pick(raw, "dminsttCd", "dmndInsttCd", "demandInsttCd", "orderInsttCd", "ntceInsttCd")
    if code and code in LH_AGENCY_CODES:
        return True
    for key in (
        "dminsttNm",
        "dmndInsttNm",
        "demandInsttNm",
        "orderInsttNm",
        "orderInsttName",
        "ntceInsttNm",
        "insttNm",
        "totlmngInsttNm",
        "rlDminsttNm",
    ):
        name = _pick(raw, key)
        if _normalize_agency_name(name) in {_normalize_agency_name(value) for value in LH_AGENCY_NAMES | LH_AGENCY_ALIASES}:
            return True
    return False


def related_record_key(record: NormalizedBusinessRecord) -> tuple[str | None, str]:
    return (record.published_at or record.deadline_at, re.sub(r"\s+", "", record.title).lower())


def build_related_record_candidates(records: list[NormalizedBusinessRecord]) -> list[dict[str, str]]:
    by_key: dict[tuple[str | None, str], list[NormalizedBusinessRecord]] = {}
    for record in records:
        by_key.setdefault(related_record_key(record), []).append(record)
    candidates = []
    for grouped in by_key.values():
        sources = {record.source for record in grouped}
        if len(sources) < 2:
            continue
        for record in grouped:
            candidates.append(
                {
                    "external_id": record.external_id,
                    "source": record.source,
                    "source_record_type": record.source_record_type,
                    "match_basis": "published_at_and_normalized_title",
                }
            )
    return candidates


def _payload_from_json(payload: Any, *, endpoint: str | None) -> G2BPayload:
    if not isinstance(payload, dict):
        raise G2BParseError("G2B JSON response root must be an object", diagnostic=_diagnostic("response_parse_error", endpoint))
    response = payload.get("response", payload)
    header = response.get("header", {}) if isinstance(response, dict) else {}
    body = response.get("body", {}) if isinstance(response, dict) else {}
    result_code = str(header.get("resultCode") or payload.get("resultCode") or "")
    result_message = str(header.get("resultMsg") or header.get("resultMag") or payload.get("resultMsg") or "")
    _raise_api_error(result_code, result_message, endpoint)
    return G2BPayload(
        result_code=result_code or None,
        result_message=result_message or None,
        total_count=_to_int(body.get("totalCount") or payload.get("totalCount")),
        items=_extract_items(body.get("items") or payload.get("items") or []),
        response_format="json",
    )


def _payload_from_xml(text: str, *, endpoint: str | None) -> G2BPayload:
    xml_text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text).strip()
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise G2BParseError("G2B XML response could not be parsed", diagnostic=_diagnostic("response_parse_error", endpoint)) from exc
    result_code = _find_text(root, "resultCode")
    result_message = _find_text(root, "resultMsg") or _find_text(root, "resultMag")
    _raise_api_error(result_code, result_message, endpoint)
    items = []
    for node in _iter_local(root, "item"):
        item = {_local_name(child.tag): (child.text or "").strip() for child in list(node)}
        if item:
            items.append(item)
    return G2BPayload(result_code or None, result_message or None, _to_int(_find_text(root, "totalCount")), items, "xml")


def _request_params(
    record_type: str,
    service_key: str,
    page_size: int,
    page_no: int,
    from_date: date,
    to_date: date,
) -> dict[str, Any]:
    params = {"serviceKey": service_key, "pageNo": page_no, "numOfRows": page_size, "type": "json"}
    if record_type == "procurement_plan":
        params.update(
            {
                "orderBgnYm": from_date.strftime("%Y%m"),
                "orderEndYm": to_date.strftime("%Y%m"),
                "inqryBgnDt": from_date.strftime("%Y%m%d") + "0000",
                "inqryEndDt": to_date.strftime("%Y%m%d") + "2359",
                "orderInsttCd": LH_AGENCY_IDENTIFIER,
            }
        )
    else:
        params.update(
            {
                "inqryDiv": "1",
                "inqryBgnDt": from_date.strftime("%Y%m%d") + "0000",
                "inqryEndDt": to_date.strftime("%Y%m%d") + "2359",
                "rlDminsttNm": LH_AGENCY_NAME,
            }
        )
    return params


def _summary_payload(
    started_at: str,
    records: list[NormalizedBusinessRecord],
    summaries: dict[str, G2BCollectionSummary],
) -> dict[str, Any]:
    return {
        "source": G2B_SOURCE,
        "collection_started_at": started_at,
        "collection_finished_at": _now(),
        "resources": {name: summary.as_dict() for name, summary in summaries.items()},
        "records_normalized": len(records),
    }


def _raise_api_error(result_code: str, result_message: str, endpoint: str | None) -> None:
    code = str(result_code or "").strip()
    message = str(result_message or "").strip()
    if not code or code in {"0", "00", "03"} or "NORMAL SERVICE" in message.upper() or "NO DATA" in message.upper():
        return
    category = "service_access_denied" if code == "20" else "api_error"
    raise G2BApiError(code, message, diagnostic=_diagnostic(category, endpoint, result_code=code))


def _extract_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        item = value.get("item", value)
        return item if isinstance(item, list) else [item]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _diagnostic(
    category: str,
    endpoint: str | None,
    *,
    result_code: str | None = None,
    exception: BaseException | None = None,
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


def _append_agency_diagnostic(summary: G2BCollectionSummary, raw: dict[str, Any], operation: str) -> None:
    if len(summary.agency_diagnostics) >= 5:
        return
    diagnostic = {"operation": operation}
    for key in ("dminsttCd", "dmndInsttCd", "demandInsttCd", "orderInsttCd", "ntceInsttCd"):
        value = _pick(raw, key)
        if value:
            diagnostic["agency_code_field"] = key
            diagnostic["agency_code"] = value
            break
    for key in ("dminsttNm", "dmndInsttNm", "demandInsttNm", "rlDminsttNm", "orderInsttNm", "ntceInsttNm", "insttNm"):
        value = _pick(raw, key)
        if value:
            diagnostic["agency_name_field"] = key
            diagnostic["agency_name"] = value
            break
    summary.agency_diagnostics.append(diagnostic)


def _operation_counts(summary: G2BCollectionSummary, operation: str) -> dict[str, int]:
    return summary.operation_counts.setdefault(
        operation,
        {
            "pages_requested": 0,
            "records_received": 0,
            "records_agency_matched": 0,
            "records_filtered_non_lh": 0,
            "records_normalized": 0,
            "records_invalid": 0,
            "duplicates": 0,
        },
    )


def _finalize_source_health(summary: G2BCollectionSummary) -> None:
    if summary.api_errors and summary.pages_requested == 0:
        summary.source_health = "failed"
        return
    if summary.records_normalized > 0:
        summary.source_health = "degraded" if summary.api_errors else "healthy"
        return
    if summary.records_agency_matched > 0:
        summary.source_health = "failed"
        return
    if summary.records_received > 0:
        summary.source_health = "unverified_empty"
        return
    if summary.pages_requested > 0 and summary.agency_code_verified:
        summary.source_health = "healthy_empty" if not summary.api_errors else "degraded"
        return
    summary.source_health = "failed"


def _external_id_keys(record_type: str) -> tuple[str, ...]:
    if record_type == "procurement_plan":
        return ("orderPlanUntyNo", "orderPlanNo", "prcrmntPlanNo", "planNo", "orderPlanId")
    return ("bfSpecRgstNo", "preSpecRgstNo", "publicPrcureNo", "prcrmntReqNo", "specRegNo")


def _title_keys(record_type: str) -> tuple[str, ...]:
    if record_type == "procurement_plan":
        return ("bizNm", "orderPlanNm", "prcrmntObjNm", "prdctNm", "cnstwkNm", "servcNm")
    return ("prdctNm", "bizNm", "bfSpecNm", "preSpecNm", "publicPrcureNm", "cnstwkNm", "servcNm")


def _amount_keys(record_type: str) -> tuple[str, ...]:
    if record_type == "procurement_plan":
        return ("sumOrderAmt", "totOrderAmt", "orderAmt", "bdgtAmt", "budgetAmt", "estmtAmt")
    return ("asignBdgtAmt", "alctBudgetAmt", "bdgtAmt", "budgetAmt", "presmptPrce")


def _published_at_keys(record_type: str) -> tuple[str, ...]:
    if record_type == "procurement_plan":
        return ("nticeDt", "rgstDt", "regDt", "orderPlanRegDt", "frstRegDt", "pubDt")
    return ("rlseDt", "rgstDt", "regDt", "bfSpecRgstDt", "opinionRegStartDt", "opinionRegStartDtm")


def _deadline_at_keys(record_type: str) -> tuple[str, ...]:
    if record_type == "procurement_plan":
        return ("orderPrerngeDate", "orderPrearngeDate", "orderPrerngeYm", "orderPrearngeYm", "orderPlanDt")
    return ("opinionRegEndDt", "opinionRegEndDtm", "opninRegEndDtm", "closeDt")


def _issuing_organization(raw: dict[str, Any]) -> str:
    return _pick(raw, "dminsttNm", "dmndInsttNm", "demandInsttNm", "rlDminsttNm", "orderInsttNm", "ntceInsttNm") or "한국토지주택공사"


def _pick(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _parse_g2b_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if re.fullmatch(r"\d{6}", text):
        return datetime.strptime(text, "%Y%m").date().isoformat()
    return parse_date(text)


def _normalize_agency_name(value: str) -> str:
    text = str(value or "").lower()
    text = text.replace("(주)", "").replace("㈜", "").replace("주식회사", "")
    return re.sub(r"[\s()]+", "", text)


def _operation_name(endpoint: str) -> str:
    return endpoint.rstrip("/").rsplit("/", 1)[-1]


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
