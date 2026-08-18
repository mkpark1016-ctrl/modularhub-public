from __future__ import annotations

import math
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests

from .base import ExternalBusinessSourceAdapter, NormalizedBusinessRecord, parse_amount


LH_SERVICE_KEY_ENV = "LH_SERVICE_KEY"
LH_SOURCE = "lh"
DEFAULT_PAGE_SIZE = 10
DEFAULT_TIMEOUT_SECONDS = 20
MAX_PAGES = 50


@dataclass(frozen=True)
class LHResource:
    name: str
    source_record_type: str
    endpoint_env: str
    default_endpoint: str
    date_start_param: str
    date_end_param: str
    date_format: str

    def endpoint(self) -> str:
        return os.getenv(self.endpoint_env, self.default_endpoint).strip() or self.default_endpoint


LH_RESOURCES: dict[str, LHResource] = {
    "procurement_plan": LHResource(
        name="procurement_plan",
        source_record_type="procurement_plan",
        endpoint_env="LH_ORDER_PLAN_ENDPOINT",
        default_endpoint="https://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenOrdergPlanList.dev",
        date_start_param="orderExpectYmStart",
        date_end_param="orderExpectYmEnd",
        date_format="%Y%m",
    ),
    "pre_spec": LHResource(
        name="pre_spec",
        source_record_type="pre_spec",
        endpoint_env="LH_PRE_SPEC_ENDPOINT",
        default_endpoint="https://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenAdvcinfoReqList.dev",
        date_start_param="opinionRegEndDtmStart",
        date_end_param="opinionRegEndDtmEnd",
        date_format="%Y%m%d",
    ),
    "bid_notice": LHResource(
        name="bid_notice",
        source_record_type="bid_notice",
        endpoint_env="LH_OPENBID_ENDPOINT",
        default_endpoint="https://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev",
        date_start_param="tndrbidRegDtStart",
        date_end_param="tndrbidRegDtEnd",
        date_format="%Y%m%d",
    ),
}


class LHApiError(RuntimeError):
    def __init__(self, result_code: str, result_message: str) -> None:
        super().__init__(f"LH API error: {result_code} {result_message}".strip())
        self.result_code = result_code
        self.result_message = result_message


class LHParseError(RuntimeError):
    pass


@dataclass(frozen=True)
class LHPayload:
    result_code: str | None
    result_message: str | None
    total_count: int
    items: list[dict[str, str]]
    response_format: str


@dataclass(frozen=True)
class LHPageResult:
    resource: str
    page_no: int
    page_size: int
    http_status: int
    payload: LHPayload
    endpoint: str


@dataclass
class LHCollectionSummary:
    pages_requested: int = 0
    records_received: int = 0
    records_normalized: int = 0
    records_invalid: int = 0
    duplicates: int = 0
    api_errors: list[dict[str, str]] = field(default_factory=list)
    http_statuses: list[int] = field(default_factory=list)
    api_result_codes: list[str | None] = field(default_factory=list)
    response_formats: list[str] = field(default_factory=list)
    total_count: int | None = None

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
            "total_count": self.total_count,
        }


RequestGet = Callable[..., Any]


class LHClient:
    def __init__(
        self,
        *,
        service_key: str | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        request_get: RequestGet | None = None,
    ) -> None:
        self.service_key = (service_key if service_key is not None else os.getenv(LH_SERVICE_KEY_ENV, "")).strip()
        self.page_size = page_size
        self.timeout_seconds = timeout_seconds
        self.request_get = request_get or requests.get

    def configured(self) -> bool:
        return bool(self.service_key)

    def fetch_page(self, resource: LHResource, *, page_no: int, from_date: date, to_date: date) -> LHPageResult:
        if not self.service_key:
            raise RuntimeError(f"{LH_SERVICE_KEY_ENV} is not configured")

        params = {
            "serviceKey": self.service_key,
            "numOfRows": self.page_size,
            "pageNo": page_no,
            resource.date_start_param: from_date.strftime(resource.date_format),
            resource.date_end_param: to_date.strftime(resource.date_format),
        }
        response = self.request_get(resource.endpoint(), params=params, timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = parse_lh_response(response.content, encoding=getattr(response, "encoding", None))
        return LHPageResult(
            resource=resource.name,
            page_no=page_no,
            page_size=self.page_size,
            http_status=int(response.status_code),
            payload=payload,
            endpoint=resource.endpoint(),
        )


def parse_lh_response(content: bytes | str, *, encoding: str | None = None) -> LHPayload:
    if isinstance(content, bytes):
        text = content.decode(encoding or "utf-8", errors="replace").strip()
    else:
        text = content.strip()
    if not text:
        return LHPayload(result_code=None, result_message=None, total_count=0, items=[], response_format="empty")

    if text.startswith("{"):
        raise LHParseError("LH JSON response is not supported by this XML parser")

    xml_text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text).strip()
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise LHParseError("LH XML response could not be parsed") from exc

    result_code = _find_text(root, "resultCode")
    result_message = _find_text(root, "resultMsg") or _find_text(root, "resultMag")
    if result_code and result_code not in {"00", "0"}:
        raise LHApiError(result_code, result_message or "")

    items = []
    for item_node in _iter_local(root, "item"):
        item = {_local_name(child.tag): (child.text or "").strip() for child in list(item_node)}
        if item:
            items.append(item)

    return LHPayload(
        result_code=result_code or None,
        result_message=result_message or None,
        total_count=_to_int(_find_text(root, "totalCount")),
        items=items,
        response_format="xml",
    )


class LHProcurementAdapter(ExternalBusinessSourceAdapter):
    source = LH_SOURCE
    api_key_env = LH_SERVICE_KEY_ENV
    endpoint_env = "LH_OPENBID_ENDPOINT"

    def __init__(self, resource: LHResource, *, collected_at: str | None = None) -> None:
        self.resource = resource
        self.collected_at = collected_at

    def collect_raw_records(self) -> list[dict[str, Any]]:
        raise NotImplementedError("Use LHPilotRunner for paginated live collection")

    def normalize_raw_record(self, raw: dict[str, Any]) -> NormalizedBusinessRecord:
        external_part = _pick(raw, *_external_id_keys(self.resource.source_record_type))
        external_id = f"{LH_SOURCE}:{self.resource.source_record_type}:{external_part}" if external_part else ""
        return NormalizedBusinessRecord(
            source=LH_SOURCE,
            source_record_type=self.resource.source_record_type,
            external_id=external_id,
            title=_pick(raw, *_title_keys(self.resource.source_record_type)),
            issuing_organization=_pick(raw, *_organization_keys(self.resource.source_record_type)) or "한국토지주택공사",
            category=_pick(raw, "bidKind", "cstrtnJobGbNm", "orderKindNm", "prdctClsfcNoNm", "prdlstNm", "bizTypeNm"),
            region=_join_values(raw, "zoneRstrct1", "zoneRstrct2", "zoneRstrct3", "zoneRstrct4", "regionNm", "zoneHqCd"),
            estimated_amount=parse_amount(_pick(raw, *_amount_keys(self.resource.source_record_type))),
            currency="KRW",
            published_at=_parse_lh_date(_pick(raw, *_published_at_keys(self.resource.source_record_type))),
            deadline_at=_parse_lh_date(_pick(raw, *_deadline_at_keys(self.resource.source_record_type))),
            status=_pick(raw, "bidProgrsStatus", "progStatNm", "prgrsSttusNm", "statusNm"),
            contract_method=_pick(raw, "tndrCtrctMedCd", "ctrctMthdNm", "contractMethod", "tndrWayNm"),
            source_url=_source_url(self.resource.source_record_type, external_part),
            collected_at=self.collected_at or self.collected_now(),
            source_updated_at=_parse_lh_date(_pick(raw, "chgDtm", "modDtm", "updatedAt")),
        )


class LHPilotRunner:
    def __init__(self, *, client: LHClient, resources: dict[str, LHResource] | None = None) -> None:
        self.client = client
        self.resources = resources or LH_RESOURCES

    def collect(
        self,
        *,
        resource_names: list[str],
        from_date: date,
        to_date: date,
        max_pages: int = MAX_PAGES,
    ) -> tuple[list[NormalizedBusinessRecord], dict[str, Any]]:
        started_at = _now()
        all_records: list[NormalizedBusinessRecord] = []
        seen: set[tuple[str, str, str]] = set()
        resource_summaries: dict[str, LHCollectionSummary] = {
            name: LHCollectionSummary() for name in resource_names
        }

        for resource_name in resource_names:
            resource = self.resources[resource_name]
            adapter = LHProcurementAdapter(resource, collected_at=started_at)
            summary = resource_summaries[resource_name]
            total_pages = 1
            page_no = 1
            while page_no <= min(total_pages, max_pages):
                try:
                    page = self.client.fetch_page(resource, page_no=page_no, from_date=from_date, to_date=to_date)
                except LHApiError as exc:
                    summary.api_errors.append({"category": "api_error", "result_code": exc.result_code})
                    break
                except LHParseError:
                    summary.api_errors.append({"category": "response_parse_error"})
                    break
                except requests.RequestException:
                    summary.api_errors.append({"category": "transport_error"})
                    break

                summary.pages_requested += 1
                summary.http_statuses.append(page.http_status)
                summary.api_result_codes.append(page.payload.result_code)
                summary.response_formats.append(page.payload.response_format)
                summary.total_count = page.payload.total_count
                summary.records_received += len(page.payload.items)
                total_pages = max(1, math.ceil(page.payload.total_count / max(page.page_size, 1)))

                for raw in page.payload.items:
                    try:
                        normalized = adapter.normalize_raw_record(raw)
                    except ValueError:
                        summary.records_invalid += 1
                        continue
                    key = (normalized.source, normalized.source_record_type, normalized.external_id)
                    if key in seen:
                        summary.duplicates += 1
                        continue
                    seen.add(key)
                    summary.records_normalized += 1
                    all_records.append(normalized)

                page_no += 1

        finished_at = _now()
        summary_payload = {
            "source": LH_SOURCE,
            "collection_started_at": started_at,
            "collection_finished_at": finished_at,
            "resources": {name: summary.as_dict() for name, summary in resource_summaries.items()},
            "records_normalized": len(all_records),
        }
        return all_records, summary_payload


def write_staging_outputs(records: list[NormalizedBusinessRecord], summary: dict[str, Any], output_dir: Path) -> None:
    import json

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "lh_records.json").write_text(
        json.dumps([record.as_dict() for record in records], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "lh_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def redact_url(url: str) -> str:
    return re.sub(r"([?&]serviceKey=)[^&]+", r"\1<redacted>", url)


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


def _parse_lh_date(value: Any) -> str | None:
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
        "%Y-%m-%d %H:%M",
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y%m%d%H%M",
    ):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"invalid LH date: {text!r}")


def _pick(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _join_values(item: dict[str, Any], *keys: str) -> str | None:
    values = [_pick(item, key) for key in keys]
    joined = "; ".join(value for value in values if value)
    return joined or None


def _external_id_keys(record_type: str) -> tuple[str, ...]:
    if record_type == "procurement_plan":
        return ("orderPlanNo", "orderPlanNum", "orderNo", "orderExpectYm", "bidNum", "seq")
    if record_type == "pre_spec":
        return ("advcinfoReqNo", "advncReqNo", "preSpecNo", "bidNum", "seq")
    return ("bidNum", "bidNo", "tndrNo", "pblancNo")


def _title_keys(record_type: str) -> tuple[str, ...]:
    if record_type == "procurement_plan":
        return ("orderPlanNm", "bizNm", "bidnmKor", "prdctNm", "title")
    if record_type == "pre_spec":
        return ("advcinfoReqNm", "preSpecNm", "prdctNm", "bidnmKor", "title")
    return ("bidnmKor", "bidnmEng", "bidName", "title")


def _organization_keys(record_type: str) -> tuple[str, ...]:
    if record_type == "pre_spec":
        return ("deptNm", "chrgDeptNm", "demandDeptNm", "orderOrgNm")
    return ("orderOrgNm", "orderInsttNm", "deptNm", "zoneHqCd")


def _amount_keys(record_type: str) -> tuple[str, ...]:
    if record_type == "procurement_plan":
        return ("orderAmt", "bdgtAmt", "budgetAmount", "presmtPrc", "fdmtlAmt")
    if record_type == "pre_spec":
        return ("alctBudgetAmt", "bdgtAmt", "budgetAmount", "presmtPrc")
    return ("fdmtlAmt", "presmtPrc", "designPrc", "budgetAmount")


def _published_at_keys(record_type: str) -> tuple[str, ...]:
    if record_type == "procurement_plan":
        return ("orderExpectYm", "orderExpectDt", "regDt", "bidStartDt")
    if record_type == "pre_spec":
        return ("regDt", "opinionRegStartDtm", "rqstDt")
    return ("tndrbidRegDt", "bidStartDt", "regDt")


def _deadline_at_keys(record_type: str) -> tuple[str, ...]:
    if record_type == "procurement_plan":
        return ("orderExpectYm", "orderExpectDt")
    if record_type == "pre_spec":
        return ("opinionRegEndDtm", "opninRegEndDtm", "closeDt")
    return ("tndrdocAcptEndDtm", "openDtm", "cooperdocAcptEndDtm")


def _source_url(record_type: str, external_part: str) -> str:
    base = "https://ebid.lh.or.kr/"
    if record_type == "bid_notice" and external_part:
        return f"{base}ebid.et.tp.cmd.BidListCmd.dev?bidNum={external_part}"
    return base


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
