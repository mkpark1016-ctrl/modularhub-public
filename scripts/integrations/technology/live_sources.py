from __future__ import annotations

from dataclasses import asdict, dataclass, field
import os
import re
import time
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

import requests
from requests.exceptions import ConnectionError, ConnectTimeout, HTTPError, ReadTimeout, Timeout

from scripts.integrations.business.base import clean_text
from scripts.integrations.technology.base import KAIA_API_KEY_ENV, KIPRIS_API_KEY_ENV
from scripts.integrations.technology.matching import normalize_company_name


KIPRIS_APPLICANT_ENDPOINT = (
    "https://plus.kipris.or.kr/openapi/rest/"
    "patUtiModInfoSearchSevice/applicantNameSearchInfo"
)
KIPRIS_APPLICATION_EXACT_ENDPOINT = (
    "https://plus.kipris.or.kr/openapi/rest/"
    "patUtiModInfoSearchSevice/applicationNumberSearchInfo"
)
KIPRIS_REGISTRATION_EXACT_ENDPOINT = (
    "https://plus.kipris.or.kr/openapi/rest/"
    "patUtiModInfoSearchSevice/registrationNumberSearchInfo"
)
KIPRIS_LEGAL_STATUS_BASE_ENDPOINT = (
    "https://plus.kipris.or.kr/openapi/rest/legStatusST27InfoSearchService"
)
KIPRIS_LEGAL_STATUS_BASIC_ENDPOINT = f"{KIPRIS_LEGAL_STATUS_BASE_ENDPOINT}/BasicInfo"
KIPRIS_LEGAL_STATUS_STOP_RIGHT_ENDPOINT = f"{KIPRIS_LEGAL_STATUS_BASE_ENDPOINT}/StopRightInfo"
KIPRIS_SOURCE_URL = "https://plus.kipris.or.kr/portal/search/clasList/List.do"
KIPRIS_LEGAL_STATUS_SOURCE_URL = (
    "https://plus.kipris.or.kr/portal/data/service/DBII_000000000000540/view.do"
)
KAIA_NEWTECH_ENDPOINT = "https://www.kaia.re.kr/portal/openApi/newtecListData.xml"
KAIA_SOURCE_URL = "https://www.kaia.re.kr/portal/bbs/view/B0000007/3494.do?menuNo=200026"

DEFAULT_CONNECT_TIMEOUT_SECONDS = 5
DEFAULT_READ_TIMEOUT_SECONDS = 20
DEFAULT_MAX_ATTEMPTS = 2
DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 2
DEFAULT_MAX_RECORDS = 200
TRANSIENT_HTTP_STATUSES = frozenset({500, 502, 503, 504})
SOURCE_STATUSES = frozenset({
    "healthy",
    "authentication_denied",
    "service_denied",
    "transport_error",
    "schema_error",
    "empty_result",
})


RequestGet = Callable[..., Any]
SleepFunc = Callable[[int], None]


@dataclass
class TechnologySourceDiagnostic:
    source: str
    status: str
    configured: bool
    request_attempted: bool = False
    endpoint_scheme: str | None = None
    endpoint_host: str | None = None
    http_status: int | None = None
    api_result_code: str | None = None
    pages_requested: int = 0
    received_count: int = 0
    attempt_count: int = 0
    final_exception_type: str | None = None
    transport_category: str | None = None
    error_category: str | None = None
    observed_fields: list[str] = field(default_factory=list)
    documented_fields_missing_from_sample: list[str] = field(default_factory=list)
    undocumented_sample_fields: list[str] = field(default_factory=list)
    query_metrics: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in SOURCE_STATUSES:
            raise ValueError(f"unsupported source status={self.status!r}")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TechnologyCollectionResult:
    source: str
    records: list[dict[str, Any]]
    raw_pages: list[str]
    diagnostic: TechnologySourceDiagnostic

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "records": self.records,
            "diagnostic": self.diagnostic.as_dict(),
        }


class TechnologySourceError(RuntimeError):
    def __init__(self, message: str, diagnostic: dict[str, Any]) -> None:
        super().__init__(message)
        self.diagnostic = diagnostic


class TechnologyTransportError(TechnologySourceError):
    pass


class TechnologyApiError(TechnologySourceError):
    pass


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children_as_dict(element: ET.Element) -> dict[str, str]:
    values: dict[str, str] = {}
    for child in element:
        key = _local_name(child.tag)
        value = clean_text("".join(child.itertext()))
        if key and value is not None:
            values[key] = value
    return values


def _first_text(root: ET.Element, names: Iterable[str]) -> str | None:
    expected = {name.casefold() for name in names}
    for element in root.iter():
        if _local_name(element.tag).casefold() in expected:
            value = clean_text("".join(element.itertext()))
            if value:
                return value
    return None


def _candidate_elements(root: ET.Element, required_fields: set[str]) -> list[ET.Element]:
    candidates = []
    for element in root.iter():
        child_names = {_local_name(child.tag).casefold() for child in element}
        if child_names & required_fields:
            candidates.append(element)
    return candidates


def _parse_xml(content: bytes | str, *, source: str) -> ET.Element:
    payload = content.encode("utf-8") if isinstance(content, str) else content
    try:
        return ET.fromstring(payload)
    except ET.ParseError as exc:
        text = payload.decode("utf-8", errors="ignore").casefold()
        category = "authentication_denied" if _looks_like_auth_error(text) else "schema_error"
        raise TechnologyApiError(
            f"{source} response was not valid XML",
            {"status": category, "error_category": category, "final_exception_type": type(exc).__name__},
        ) from exc


def parse_kipris_applicant_response(
    content: bytes | str,
    *,
    collected_at: str | None = None,
) -> tuple[list[dict[str, Any]], int, set[str], str | None]:
    root = _parse_xml(content, source="kipris")
    result_code = _first_text(root, ("resultCode", "returnReasonCode", "errorCode"))
    result_message = _first_text(root, ("resultMsg", "returnAuthMsg", "errorMessage"))
    if result_code and result_code not in {"0", "00"}:
        category = _api_error_category(result_code, result_message)
        raise TechnologyApiError(
            "KIPRISPlus API rejected the request",
            {
                "status": category,
                "error_category": category,
                "api_result_code": result_code,
            },
        )

    elements = [
        element
        for element in root.iter()
        if _local_name(element.tag).casefold() == "patentutilityinfo"
    ]
    if not elements:
        elements = _candidate_elements(
            root,
            {"applicationnumber", "registrationnumber", "inventionname"},
        )

    rows: list[dict[str, Any]] = []
    observed_fields: set[str] = set()
    for element in elements:
        row = _children_as_dict(element)
        observed_fields.update(row)
        if not any(row.get(key) for key in ("ApplicationNumber", "RegistrationNumber")):
            continue
        row["source"] = "kipris"
        row["sourceUrl"] = KIPRIS_SOURCE_URL
        if collected_at:
            row["collectedAt"] = collected_at
        rows.append(row)

    total_text = _first_text(root, ("totalSearchCount", "TotalSearchCount", "totalCount"))
    try:
        total_count = int(total_text or len(rows))
    except ValueError:
        total_count = len(rows)
    if total_count > 0 and not rows:
        raise TechnologyApiError(
            "KIPRISPlus response did not contain documented patent rows",
            {"status": "schema_error", "error_category": "schema_error"},
        )
    return rows, total_count, observed_fields, result_code


def parse_kipris_exact_response(
    content: bytes | str,
    *,
    collected_at: str | None = None,
) -> tuple[list[dict[str, Any]], int, set[str], str | None]:
    """Parse the documented exact-number operations, which share the patent row schema."""
    return parse_kipris_applicant_response(content, collected_at=collected_at)


def parse_kipris_legal_status_response(
    content: bytes | str,
    *,
    operation: str,
    collected_at: str | None = None,
) -> tuple[list[dict[str, Any]], int, set[str], str | None]:
    """Parse KIPRISPlus ST.27 basic or right-termination history rows."""
    item_names = {
        "basic": "legalstatusst27info",
        "stop_right": "legalstatusst27stoprightinfo",
    }
    if operation not in item_names:
        raise ValueError(f"unsupported KIPRIS legal-status operation={operation!r}")

    root = _parse_xml(content, source="kipris_st27")
    result_code = _first_text(root, ("resultCode", "returnReasonCode", "errorCode"))
    result_message = _first_text(root, ("resultMsg", "returnAuthMsg", "errorMessage"))
    if result_code and result_code not in {"0", "00"}:
        category = _api_error_category(result_code, result_message)
        raise TechnologyApiError(
            "KIPRISPlus ST.27 API rejected the request",
            {
                "status": category,
                "error_category": category,
                "api_result_code": result_code,
            },
        )

    elements = [
        element
        for element in root.iter()
        if _local_name(element.tag).casefold() == item_names[operation]
    ]
    if not elements:
        required = {"applicationnumber", "eventdate"} if operation == "basic" else {
            "applicationnumber",
            "terminationregistrationcausedate",
            "terminationregistrationcausename",
        }
        elements = _candidate_elements(root, required)

    rows: list[dict[str, Any]] = []
    observed_fields: set[str] = set()
    for element in elements:
        row = _children_as_dict(element)
        if not row.get("applicationNumber"):
            continue
        observed_fields.update(row)
        row["source"] = "kipris_st27"
        row["operation"] = operation
        row["sourceUrl"] = KIPRIS_LEGAL_STATUS_SOURCE_URL
        if collected_at:
            row["collectedAt"] = collected_at
        rows.append(row)

    total_text = _first_text(root, ("totalSearchCount", "TotalSearchCount", "totalCount"))
    try:
        total_count = int(total_text or len(rows))
    except ValueError:
        total_count = len(rows)
    if total_count > 0 and not rows:
        raise TechnologyApiError(
            "KIPRISPlus ST.27 response did not contain documented history rows",
            {"status": "schema_error", "error_category": "schema_error"},
        )
    return rows, total_count, observed_fields, result_code


def normalize_kipris_exact_query_identifier(value: str, lookup_type: str) -> str:
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    if lookup_type == "application_number":
        if len(digits) != 13:
            raise ValueError("KIPRIS application number exact lookup requires 13 digits")
        return digits
    if lookup_type == "registration_number":
        if len(digits) == 9:
            return f"{digits}0000"
        if len(digits) == 13:
            return digits
        raise ValueError("KIPRIS registration number exact lookup requires 9 or 13 digits")
    raise ValueError(f"unsupported KIPRIS exact lookup type={lookup_type!r}")


def parse_kaia_newtech_response(
    content: bytes | str,
    *,
    collected_at: str | None = None,
) -> tuple[list[dict[str, Any]], int, set[str]]:
    root = _parse_xml(content, source="kaia_newtech")
    all_text = clean_text(" ".join(root.itertext())) or ""
    if _looks_like_auth_error(all_text):
        raise TechnologyApiError(
            "KAIA API rejected the credential",
            {"status": "authentication_denied", "error_category": "authentication_denied"},
        )

    elements = _candidate_elements(root, {"newtecid", "apntno", "newtecnm"})
    rows: list[dict[str, Any]] = []
    observed_fields: set[str] = set()
    seen_elements: set[int] = set()
    for element in elements:
        if id(element) in seen_elements:
            continue
        row = _children_as_dict(element)
        if not any(row.get(key) for key in ("newtecId", "apntNo", "newtecNm")):
            continue
        seen_elements.add(id(element))
        observed_fields.update(row)
        row["source"] = "kaia_newtech"
        row["sourceUrl"] = KAIA_SOURCE_URL
        if collected_at:
            row["collectedAt"] = collected_at
        rows.append(row)

    total_text = _first_text(root, ("cnt", "totalCount"))
    try:
        total_count = int(total_text or len(rows))
    except ValueError:
        total_count = len(rows)
    if total_count > 0 and not rows:
        raise TechnologyApiError(
            "KAIA response did not contain documented new-technology rows",
            {"status": "schema_error", "error_category": "schema_error"},
        )
    return rows, total_count, observed_fields


class _BoundedXmlClient:
    source = ""
    endpoint = ""
    secret_env = ""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: tuple[int, int] = (
            DEFAULT_CONNECT_TIMEOUT_SECONDS,
            DEFAULT_READ_TIMEOUT_SECONDS,
        ),
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        request_get: RequestGet | None = None,
        sleep_func: SleepFunc | None = None,
    ) -> None:
        self.api_key = (api_key if api_key is not None else os.getenv(self.secret_env, "")).strip()
        self.timeout = timeout
        self.max_attempts = max(1, max_attempts)
        self.request_get = request_get or requests.get
        self.sleep_func = sleep_func or _sleep_before_retry

    def configured(self) -> bool:
        return bool(self.api_key)

    def _get(self, params: dict[str, Any]) -> tuple[Any, int]:
        return self._get_at(self.endpoint, params)

    def _get_at(self, endpoint: str, params: dict[str, Any]) -> tuple[Any, int]:
        last_error: BaseException | None = None
        for attempt in range(self.max_attempts):
            try:
                response = self.request_get(endpoint, params=params, timeout=self.timeout)
                response.raise_for_status()
                return response, attempt + 1
            except (ConnectTimeout, ConnectionError, Timeout) as exc:
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    self.sleep_func(attempt)
                    continue
                break
            except HTTPError as exc:
                last_error = exc
                status_code = _status_code_from_http_error(exc)
                if status_code in TRANSIENT_HTTP_STATUSES and attempt + 1 < self.max_attempts:
                    self.sleep_func(attempt)
                    continue
                category = "authentication_denied" if status_code in {401, 403} else "transport_error"
                raise TechnologyTransportError(
                    f"{self.source} HTTP response failed",
                    _transport_diagnostic(
                        endpoint,
                        status=category,
                        error_category=category,
                        exception=exc,
                        attempt_count=attempt + 1,
                        http_status=status_code,
                    ),
                ) from exc
            except requests.RequestException as exc:
                raise TechnologyTransportError(
                    f"{self.source} request failed",
                    _transport_diagnostic(
                        endpoint,
                        status="transport_error",
                        error_category="transport_error",
                        exception=exc,
                        attempt_count=attempt + 1,
                    ),
                ) from exc

        raise TechnologyTransportError(
            f"{self.source} request failed",
            _transport_diagnostic(
                endpoint,
                status="transport_error",
                error_category="transport_error",
                exception=last_error,
                attempt_count=self.max_attempts,
            ),
        ) from last_error


class KiprisLiveClient(_BoundedXmlClient):
    source = "kipris"
    endpoint = KIPRIS_APPLICANT_ENDPOINT
    secret_env = KIPRIS_API_KEY_ENV
    documented_fields = {
        "Applicant",
        "OpeningDate",
        "OpeningNumber",
        "PublicNumber",
        "PublicDate",
        "RegistrationDate",
        "RegistrationNumber",
        "RegistrationStatus",
        "ApplicationDate",
        "ApplicationNumber",
        "Abstract",
        "DrawingPath",
        "ThumbnailPath",
        "SerialNumber",
        "InventionName",
        "InternationalpatentclassificationNumber",
    }

    def collect(
        self,
        applicant_aliases: Iterable[str],
        *,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_records: int = DEFAULT_MAX_RECORDS,
        collected_at: str | None = None,
    ) -> TechnologyCollectionResult:
        diagnostic = _new_diagnostic(self.source, self.endpoint, self.configured())
        if not self.configured():
            diagnostic.status = "authentication_denied"
            diagnostic.error_category = "missing_secret"
            return TechnologyCollectionResult(self.source, [], [], diagnostic)

        aliases = tuple(dict.fromkeys(clean_text(alias) for alias in applicant_aliases if clean_text(alias)))
        records: list[dict[str, Any]] = []
        raw_pages: list[str] = []
        observed_fields: set[str] = set()
        diagnostic.request_attempted = True
        try:
            for alias in aliases:
                query_identities: set[str] = set()
                query_metric = {
                    "alias": alias,
                    "query_attempted": False,
                    "received_count": 0,
                    "unique_application_identity_count": 0,
                }
                diagnostic.query_metrics.append(query_metric)
                for page in range(1, max_pages + 1):
                    if len(records) >= max_records:
                        break
                    params = {
                        "applicant": alias,
                        "docsStart": ((page - 1) * page_size) + 1,
                        "docsCount": min(page_size, max_records - len(records)),
                        "patent": "true",
                        "utility": "false",
                        "sortSpec": "GD",
                        "descSort": "true",
                        "accessKey": self.api_key,
                    }
                    query_metric["query_attempted"] = True
                    diagnostic.pages_requested += 1
                    response, attempts = self._get(params)
                    diagnostic.attempt_count += attempts
                    diagnostic.http_status = int(getattr(response, "status_code", 0))
                    raw_pages.append(sanitize_response_text(response, secrets=(self.api_key,)))
                    page_rows, total, fields, result_code = parse_kipris_applicant_response(
                        getattr(response, "content", b""),
                        collected_at=collected_at,
                    )
                    diagnostic.api_result_code = result_code
                    observed_fields.update(fields)
                    query_metric["received_count"] += len(page_rows)
                    query_identities.update(
                        str(row.get("ApplicationNumber") or row.get("RegistrationNumber") or "").strip()
                        for row in page_rows
                        if row.get("ApplicationNumber") or row.get("RegistrationNumber")
                    )
                    query_metric["unique_application_identity_count"] = len(query_identities)
                    records.extend(page_rows[: max_records - len(records)])
                    if not page_rows or page * page_size >= total:
                        break
        except (TechnologyApiError, TechnologyTransportError) as exc:
            _apply_error(diagnostic, exc)
            diagnostic.received_count = len(records)
            diagnostic.observed_fields = sorted(observed_fields)
            return TechnologyCollectionResult(self.source, records, raw_pages, diagnostic)

        records = _stable_unique_raw(records)
        diagnostic.received_count = len(records)
        diagnostic.observed_fields = sorted(observed_fields)
        diagnostic.documented_fields_missing_from_sample = sorted(self.documented_fields - observed_fields)
        diagnostic.undocumented_sample_fields = sorted(
            observed_fields - self.documented_fields - {"source", "sourceUrl", "collectedAt"}
        )
        diagnostic.status = "healthy" if records else "empty_result"
        return TechnologyCollectionResult(self.source, records, raw_pages, diagnostic)


class KiprisExactLookupClient(_BoundedXmlClient):
    source = "kipris"
    endpoint = KIPRIS_REGISTRATION_EXACT_ENDPOINT
    secret_env = KIPRIS_API_KEY_ENV
    endpoints = {
        "application_number": (KIPRIS_APPLICATION_EXACT_ENDPOINT, "applicationNumber"),
        "registration_number": (KIPRIS_REGISTRATION_EXACT_ENDPOINT, "registerNumber"),
    }
    documented_fields = KiprisLiveClient.documented_fields

    def lookup(
        self,
        lookup_type: str,
        identifier: str,
        *,
        collected_at: str | None = None,
    ) -> TechnologyCollectionResult:
        if lookup_type not in self.endpoints:
            raise ValueError(f"unsupported KIPRIS exact lookup type={lookup_type!r}")
        endpoint, parameter_name = self.endpoints[lookup_type]
        query_identifier = normalize_kipris_exact_query_identifier(identifier, lookup_type)
        diagnostic = _new_diagnostic(self.source, endpoint, self.configured())
        diagnostic.query_metrics = [{
            "lookup_type": lookup_type,
            "lookup_identifier": query_identifier,
            "query_attempted": False,
            "received_count": 0,
        }]
        if not self.configured():
            diagnostic.status = "authentication_denied"
            diagnostic.error_category = "missing_secret"
            return TechnologyCollectionResult(self.source, [], [], diagnostic)

        params = {
            parameter_name: query_identifier,
            "docsStart": 1,
            "accessKey": self.api_key,
        }
        diagnostic.request_attempted = True
        diagnostic.pages_requested = 1
        diagnostic.query_metrics[0]["query_attempted"] = True
        try:
            response, attempts = self._get_at(endpoint, params)
            diagnostic.attempt_count = attempts
            diagnostic.http_status = int(getattr(response, "status_code", 0))
            raw_pages = [sanitize_response_text(response, secrets=(self.api_key,))]
            records, _, observed_fields, result_code = parse_kipris_exact_response(
                getattr(response, "content", b""),
                collected_at=collected_at,
            )
            records = _stable_unique_raw(records)
            diagnostic.api_result_code = result_code
            diagnostic.received_count = len(records)
            diagnostic.query_metrics[0]["received_count"] = len(records)
            diagnostic.observed_fields = sorted(observed_fields)
            diagnostic.documented_fields_missing_from_sample = sorted(
                self.documented_fields - observed_fields
            )
            diagnostic.undocumented_sample_fields = sorted(
                observed_fields - self.documented_fields - {"source", "sourceUrl", "collectedAt"}
            )
            diagnostic.status = "healthy" if records else "empty_result"
            return TechnologyCollectionResult(self.source, records, raw_pages, diagnostic)
        except (TechnologyApiError, TechnologyTransportError) as exc:
            _apply_error(diagnostic, exc)
            return TechnologyCollectionResult(self.source, [], [], diagnostic)


class KiprisLegalStatusClient(_BoundedXmlClient):
    source = "kipris_st27"
    endpoint = KIPRIS_LEGAL_STATUS_BASIC_ENDPOINT
    secret_env = KIPRIS_API_KEY_ENV
    endpoints = {
        "basic": KIPRIS_LEGAL_STATUS_BASIC_ENDPOINT,
        "stop_right": KIPRIS_LEGAL_STATUS_STOP_RIGHT_ENDPOINT,
    }
    documented_fields = {
        "basic": {
            "applicationNumber", "supplySerialNumber", "rightTypeCode", "applicationDate",
            "openNumber", "openingDate", "registrationNumber", "registrationDate",
            "publicationNumber", "publicationDate", "trialNumber", "demurrerNumber",
            "keyEventCode", "detailLawEventCode", "stateCode", "previousStageCode",
            "currentStageCode", "eventIndicatorCode", "nationalEventCode", "eventDate",
        },
        "stop_right": {
            "applicationNumber", "SerialNumber", "terminationRegistrationCauseDate",
            "terminationRegistrationCauseName",
        },
    }

    def lookup(
        self,
        operation: str,
        application_number: str,
        *,
        collected_at: str | None = None,
    ) -> TechnologyCollectionResult:
        if operation not in self.endpoints:
            raise ValueError(f"unsupported KIPRIS legal-status operation={operation!r}")
        endpoint = self.endpoints[operation]
        query_identifier = normalize_kipris_exact_query_identifier(
            application_number, "application_number"
        )
        diagnostic = _new_diagnostic(self.source, endpoint, self.configured())
        diagnostic.query_metrics = [{
            "operation": operation,
            "lookup_identifier": query_identifier,
            "query_attempted": False,
            "received_count": 0,
        }]
        if not self.configured():
            diagnostic.status = "authentication_denied"
            diagnostic.error_category = "missing_secret"
            return TechnologyCollectionResult(self.source, [], [], diagnostic)

        diagnostic.request_attempted = True
        diagnostic.pages_requested = 1
        diagnostic.query_metrics[0]["query_attempted"] = True
        try:
            response, attempts = self._get_at(endpoint, {
                "applicationNumber": query_identifier,
                "accessKey": self.api_key,
            })
            diagnostic.attempt_count = attempts
            diagnostic.http_status = int(getattr(response, "status_code", 0))
            raw_pages = [sanitize_response_text(response, secrets=(self.api_key,))]
            records, _, observed_fields, result_code = parse_kipris_legal_status_response(
                getattr(response, "content", b""),
                operation=operation,
                collected_at=collected_at,
            )
            records = _stable_unique_raw(records)
            documented = self.documented_fields[operation]
            diagnostic.api_result_code = result_code
            diagnostic.received_count = len(records)
            diagnostic.query_metrics[0]["received_count"] = len(records)
            diagnostic.observed_fields = sorted(observed_fields)
            diagnostic.documented_fields_missing_from_sample = sorted(documented - observed_fields)
            diagnostic.undocumented_sample_fields = sorted(
                observed_fields - documented - {"source", "operation", "sourceUrl", "collectedAt"}
            )
            diagnostic.status = "healthy" if records else "empty_result"
            return TechnologyCollectionResult(self.source, records, raw_pages, diagnostic)
        except (TechnologyApiError, TechnologyTransportError) as exc:
            _apply_error(diagnostic, exc)
            return TechnologyCollectionResult(self.source, [], [], diagnostic)


class KaiaLiveClient(_BoundedXmlClient):
    source = "kaia_newtech"
    endpoint = KAIA_NEWTECH_ENDPOINT
    secret_env = KAIA_API_KEY_ENV
    documented_fields = {
        "cnt",
        "newtecId",
        "apntNo",
        "apntYear",
        "notNo",
        "notDt",
        "newtecNm",
        "tecDvs",
        "newtecScope",
        "newtecCts",
        "prtDt",
        "dvlprNm",
        "newTecDvs",
        "keyword",
        "tecDvsCode",
        "newTecDvsCode",
        "typ",
    }

    def collect(
        self,
        *,
        designation_numbers: Iterable[str],
        page_size: int = DEFAULT_PAGE_SIZE,
        max_records: int = DEFAULT_MAX_RECORDS,
        collected_at: str | None = None,
    ) -> TechnologyCollectionResult:
        diagnostic = _new_diagnostic(self.source, self.endpoint, self.configured())
        if not self.configured():
            diagnostic.status = "authentication_denied"
            diagnostic.error_category = "missing_secret"
            return TechnologyCollectionResult(self.source, [], [], diagnostic)

        numbers = tuple(dict.fromkeys(clean_text(number) for number in designation_numbers if clean_text(number)))
        records: list[dict[str, Any]] = []
        raw_pages: list[str] = []
        observed_fields: set[str] = set()
        diagnostic.request_attempted = True
        try:
            for number in numbers:
                if len(records) >= max_records:
                    break
                params = {
                    "apiKey": self.api_key,
                    "apntNo": number,
                    "firstIndex": 1,
                    "lastIndex": min(page_size, max_records - len(records)),
                }
                diagnostic.pages_requested += 1
                response, attempts = self._get(params)
                diagnostic.attempt_count += attempts
                diagnostic.http_status = int(getattr(response, "status_code", 0))
                raw_pages.append(sanitize_response_text(response, secrets=(self.api_key,)))
                page_rows, _, fields = parse_kaia_newtech_response(
                    getattr(response, "content", b""),
                    collected_at=collected_at,
                )
                observed_fields.update(fields)
                records.extend(page_rows[: max_records - len(records)])
        except (TechnologyApiError, TechnologyTransportError) as exc:
            _apply_error(diagnostic, exc)
            diagnostic.received_count = len(records)
            diagnostic.observed_fields = sorted(observed_fields)
            return TechnologyCollectionResult(self.source, records, raw_pages, diagnostic)

        records = _stable_unique_raw(records)
        diagnostic.received_count = len(records)
        diagnostic.observed_fields = sorted(observed_fields)
        diagnostic.documented_fields_missing_from_sample = sorted(self.documented_fields - observed_fields)
        diagnostic.undocumented_sample_fields = sorted(
            observed_fields - self.documented_fields - {"source", "sourceUrl", "collectedAt"}
        )
        diagnostic.status = "healthy" if records else "empty_result"
        return TechnologyCollectionResult(self.source, records, raw_pages, diagnostic)


def filter_samsung_participants(
    records: Iterable[dict[str, Any]],
    canonical_aliases: Iterable[str],
) -> list[dict[str, Any]]:
    aliases = {normalize_company_name(alias) for alias in canonical_aliases if normalize_company_name(alias)}
    selected = []
    for record in records:
        participant_values = (
            record.get("Applicant"),
            record.get("applicantName"),
            record.get("RightHolder"),
            record.get("rightHolder"),
            record.get("dvlprNm"),
        )
        participants = [
            part
            for value in participant_values
            for part in re.split(r"[;|,]", str(value or ""))
            if clean_text(part)
        ]
        if any(normalize_company_name(participant) in aliases for participant in participants):
            selected.append(record)
    return _stable_unique_raw(selected)


def sanitize_response_text(response: Any, *, secrets: Iterable[str] = ()) -> str:
    content = getattr(response, "content", b"")
    if isinstance(content, bytes):
        encoding = getattr(response, "encoding", None) or "utf-8"
        text = content.decode(encoding, errors="replace")
    else:
        text = str(content)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[credential-redacted]")
    text = re.sub(
        r"(?i)(?:accessKey|apiKey|serviceKey|Authorization|Bearer|token)\s*=\s*[^&<\s]+",
        "[credential-redacted]",
        text,
    )
    return text


def artifact_contains_credentials(payload: str, *, secrets: Iterable[str] = ()) -> bool:
    lowered = payload.casefold()
    patterns = ("accesskey=", "apikey=", "servicekey=", "authorization", "bearer ", "token=")
    if any(pattern in lowered for pattern in patterns):
        return True
    return any(bool(secret) and secret in payload for secret in secrets)


def _new_diagnostic(source: str, endpoint: str, configured: bool) -> TechnologySourceDiagnostic:
    parsed = urlsplit(endpoint)
    return TechnologySourceDiagnostic(
        source=source,
        status="empty_result",
        configured=configured,
        endpoint_scheme=parsed.scheme or None,
        endpoint_host=parsed.hostname,
    )


def _apply_error(diagnostic: TechnologySourceDiagnostic, exc: TechnologySourceError) -> None:
    data = exc.diagnostic
    diagnostic.status = str(data.get("status") or "schema_error")
    diagnostic.error_category = str(data.get("error_category") or diagnostic.status)
    diagnostic.api_result_code = data.get("api_result_code")
    diagnostic.http_status = data.get("http_status") or diagnostic.http_status
    diagnostic.final_exception_type = data.get("final_exception_type")
    diagnostic.transport_category = data.get("transport_category")
    diagnostic.attempt_count = max(diagnostic.attempt_count, int(data.get("attempt_count") or 0))


def _transport_diagnostic(
    endpoint: str,
    *,
    status: str,
    error_category: str,
    exception: BaseException | None,
    attempt_count: int,
    http_status: int | None = None,
) -> dict[str, Any]:
    parsed = urlsplit(endpoint)
    return {
        "status": status,
        "error_category": error_category,
        "attempt_count": attempt_count,
        "http_status": http_status,
        "final_exception_type": type(exception).__name__ if exception else None,
        "transport_category": _transport_category(exception, http_status=http_status),
        "endpoint_scheme": parsed.scheme,
        "endpoint_host": parsed.hostname,
    }


def _status_code_from_http_error(exc: HTTPError) -> int | None:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    try:
        return int(status_code) if status_code is not None else None
    except (TypeError, ValueError):
        return None


def _transport_category(exc: BaseException | None, *, http_status: int | None = None) -> str:
    if http_status in TRANSIENT_HTTP_STATUSES:
        return "http_5xx"
    if http_status is not None:
        return "http_error"
    if isinstance(exc, ConnectTimeout):
        return "connect_timeout"
    if isinstance(exc, ReadTimeout):
        return "read_timeout"
    if isinstance(exc, Timeout):
        return "timeout"
    if isinstance(exc, ConnectionError):
        return "connection_error"
    return "request_exception"


def _api_error_category(result_code: str, message: str | None) -> str:
    text = (message or "").casefold()
    if result_code in {"20", "12"} or "no openapi service" in text or "service access" in text:
        return "service_denied"
    if result_code in {"30", "31", "32", "33"} or _looks_like_auth_error(text):
        return "authentication_denied"
    return "service_denied"


def _looks_like_auth_error(text: str) -> bool:
    lowered = text.casefold()
    return any(
        term in lowered
        for term in (
            "invalid service key",
            "service key is not registered",
            "authentication",
            "unauthorized",
            "access denied",
            "인증키",
            "승인받은키",
        )
    )


def _stable_unique_raw(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    keyed: dict[str, dict[str, Any]] = {}
    for record in records:
        key = "|".join(
            str(record.get(name) or "")
            for name in (
                "source",
                "ApplicationNumber",
                "RegistrationNumber",
                "newtecId",
                "apntNo",
                "externalId",
            )
        )
        keyed.setdefault(key, record)
    return [keyed[key] for key in sorted(keyed)]


def _sleep_before_retry(attempt: int) -> None:
    time.sleep(1 if attempt == 0 else 3)
