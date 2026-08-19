from __future__ import annotations

import json
import socket
import ssl
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests
from requests.exceptions import ConnectTimeout, ConnectionError, SSLError, Timeout

from .d2b import D2B_RESOURCES
from .g2b import G2B_PLAN_BASE_ENDPOINT, LH_AGENCY_IDENTIFIER


TARGET_HOST = "apis.data.go.kr"
TARGET_PORT = 443
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 10
PAGE_SIZE = 1

G2B_PROBE_ENDPOINT = (
    f"{G2B_PLAN_BASE_ENDPOINT}/getOrderPlanSttusListCnstwkPPSSrch"
)
D2B_PLAN_OPERATION = D2B_RESOURCES["procurement_plan"].operations[0]
D2B_BID_OPERATION = D2B_RESOURCES["bid_notice"].operations[0]

Resolver = Callable[..., Any]
Connector = Callable[..., Any]
RequestGet = Callable[..., Any]
Clock = Callable[[], float]


@dataclass
class ProbeResult:
    name: str
    host: str = TARGET_HOST
    scheme: str = "https"
    port: int = TARGET_PORT
    service_group: str | None = None
    operation: str | None = None
    dns_resolved: bool | None = None
    resolved_count: int | None = None
    tcp_connected: bool | None = None
    tls_reached: bool | None = None
    http_reached: bool | None = None
    http_status: int | None = None
    api_result_code: str | None = None
    transport_category: str = "none"
    exception_type: str | None = None
    elapsed_ms: int = 0
    implementation_error: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def probe_dns(
    *,
    host: str = TARGET_HOST,
    resolver: Resolver = socket.getaddrinfo,
    clock: Clock = time.perf_counter,
) -> ProbeResult:
    result = ProbeResult(name="dns", host=host, scheme="dns", port=TARGET_PORT)
    started = clock()
    try:
        addresses = resolver(host, TARGET_PORT, type=socket.SOCK_STREAM)
        result.dns_resolved = bool(addresses)
        result.resolved_count = len(addresses)
        if not addresses:
            result.transport_category = "dns_no_addresses"
    except socket.gaierror as exc:
        result.dns_resolved = False
        result.resolved_count = 0
        result.transport_category = "dns_error"
        result.exception_type = type(exc).__name__
    finally:
        result.elapsed_ms = _elapsed_ms(started, clock)
    return result


def probe_tcp(
    *,
    host: str = TARGET_HOST,
    port: int = TARGET_PORT,
    timeout_seconds: int = CONNECT_TIMEOUT_SECONDS,
    connector: Connector = socket.create_connection,
    clock: Clock = time.perf_counter,
) -> ProbeResult:
    result = ProbeResult(name="tcp", host=host, scheme="tcp", port=port)
    started = clock()
    connection: Any | None = None
    try:
        connection = connector((host, port), timeout=timeout_seconds)
        result.tcp_connected = True
    except (socket.timeout, TimeoutError, OSError) as exc:
        result.tcp_connected = False
        result.transport_category = _network_category(exc)
        result.exception_type = type(exc).__name__
    finally:
        if connection is not None:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
        result.elapsed_ms = _elapsed_ms(started, clock)
    return result


def probe_https(
    *,
    host: str = TARGET_HOST,
    request_get: RequestGet = requests.get,
    clock: Clock = time.perf_counter,
) -> ProbeResult:
    result = ProbeResult(name="https", host=host)
    started = clock()
    try:
        response = request_get(
            f"https://{host}/",
            timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
            allow_redirects=False,
        )
        result.tls_reached = True
        result.http_reached = True
        result.http_status = int(getattr(response, "status_code", 0)) or None
        result.transport_category = _http_category(result.http_status)
    except requests.RequestException as exc:
        result.tls_reached = False if isinstance(exc, SSLError) else None
        result.http_reached = False
        result.transport_category = _network_category(exc)
        result.exception_type = type(exc).__name__
    finally:
        result.elapsed_ms = _elapsed_ms(started, clock)
    return result


def probe_api_endpoint(
    *,
    name: str,
    endpoint: str,
    service_group: str,
    operation: str,
    params: dict[str, Any],
    request_get: RequestGet = requests.get,
    clock: Clock = time.perf_counter,
) -> ProbeResult:
    parsed = urlparse(endpoint)
    result = ProbeResult(
        name=name,
        host=parsed.hostname or "",
        scheme=parsed.scheme,
        port=parsed.port or TARGET_PORT,
        service_group=service_group,
        operation=operation,
    )
    started = clock()
    try:
        response = request_get(
            endpoint,
            params=params,
            timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
            allow_redirects=False,
        )
        result.tls_reached = True
        result.http_reached = True
        result.http_status = int(getattr(response, "status_code", 0)) or None
        result.api_result_code = extract_api_result_code(
            getattr(response, "content", b"")
        )
        result.transport_category = _http_category(result.http_status)
    except requests.RequestException as exc:
        result.tls_reached = False if isinstance(exc, SSLError) else None
        result.http_reached = False
        result.transport_category = _network_category(exc)
        result.exception_type = type(exc).__name__
    finally:
        result.elapsed_ms = _elapsed_ms(started, clock)
    return result


def run_connectivity_diagnostic(
    *,
    service_key: str,
    today: date | None = None,
    resolver: Resolver = socket.getaddrinfo,
    connector: Connector = socket.create_connection,
    request_get: RequestGet = requests.get,
    clock: Clock = time.perf_counter,
) -> dict[str, Any]:
    if not service_key:
        raise ValueError("DATA_GO_KR_SERVICE_KEY must be configured")

    current_date = today or datetime.now(timezone.utc).date()
    probes: dict[str, dict[str, Any]] = {}
    implementations: list[dict[str, str]] = []

    definitions: list[tuple[str, Callable[[], ProbeResult]]] = [
        (
            "dns",
            lambda: probe_dns(resolver=resolver, clock=clock),
        ),
        (
            "tcp",
            lambda: probe_tcp(connector=connector, clock=clock),
        ),
        (
            "https",
            lambda: probe_https(request_get=request_get, clock=clock),
        ),
        (
            "g2b",
            lambda: probe_api_endpoint(
                name="g2b",
                endpoint=G2B_PROBE_ENDPOINT,
                service_group="1230000",
                operation="getOrderPlanSttusListCnstwkPPSSrch",
                params=_g2b_params(service_key, current_date),
                request_get=request_get,
                clock=clock,
            ),
        ),
        (
            "d2b_procurement_plan",
            lambda: probe_api_endpoint(
                name="d2b_procurement_plan",
                endpoint=D2B_PLAN_OPERATION.endpoint(),
                service_group="1690000",
                operation=D2B_PLAN_OPERATION.name,
                params=_d2b_params(D2B_PLAN_OPERATION, service_key, current_date),
                request_get=request_get,
                clock=clock,
            ),
        ),
        (
            "d2b_bid_notice",
            lambda: probe_api_endpoint(
                name="d2b_bid_notice",
                endpoint=D2B_BID_OPERATION.endpoint(),
                service_group="1690000",
                operation=D2B_BID_OPERATION.name,
                params=_d2b_params(D2B_BID_OPERATION, service_key, current_date),
                request_get=request_get,
                clock=clock,
            ),
        ),
    ]

    for name, probe in definitions:
        try:
            probes[name] = probe().as_dict()
        except Exception as exc:
            implementations.append(
                {"probe": name, "exception_type": type(exc).__name__}
            )
            probes[name] = ProbeResult(
                name=name,
                transport_category="diagnostic_implementation_error",
                exception_type=type(exc).__name__,
                implementation_error=True,
            ).as_dict()

    classification = classify_diagnostic(probes, implementations)
    summary = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "request_attempted": True,
        "target_host": TARGET_HOST,
        "probes": probes,
        "implementation_errors": implementations,
        "classification": classification,
        "security": {
            "secret_exposure_detected": False,
            "credential_url_exposure_detected": False,
            "raw_response_persisted": False,
        },
    }
    assert_safe_summary(summary, service_key=service_key)
    return summary


def classify_diagnostic(
    probes: dict[str, dict[str, Any]],
    implementation_errors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    if implementation_errors or any(
        bool(probe.get("implementation_error")) for probe in probes.values()
    ):
        return {
            "case": "diagnostic_implementation_failure",
            "label": "diagnostic implementation failure",
            "recommended_next_action": "Fix the diagnostic implementation before interpreting network results.",
            "local_comparison_required": False,
        }

    g2b_reachable = bool((probes.get("g2b") or {}).get("http_reached"))
    plan_reachable = bool(
        (probes.get("d2b_procurement_plan") or {}).get("http_reached")
    )
    bid_reachable = bool(
        (probes.get("d2b_bid_notice") or {}).get("http_reached")
    )
    d2b_reachable = plan_reachable and bid_reachable

    if g2b_reachable and d2b_reachable:
        case = "case_1"
        label = "G2B reachable / D2B reachable"
        action = "Run D2B Live Acceptance once with max_pages=1."
        local_comparison_required = False
    elif g2b_reachable and not d2b_reachable:
        case = "case_2"
        label = "G2B reachable / D2B unreachable"
        action = (
            "Compare one local D2B probe with this hosted-runner result and contact the provider if the path remains blocked; do not increase retries."
        )
        local_comparison_required = True
    elif not g2b_reachable and not d2b_reachable:
        case = "case_3"
        label = "G2B unreachable / D2B unreachable"
        action = (
            "Compare locally, then consider one different hosted runner or a Korean-region/self-hosted ingestion worker."
        )
        local_comparison_required = True
    else:
        case = "diagnostic_inconclusive"
        label = "G2B unreachable / D2B reachable"
        action = "Review HTTP and API result codes before changing either integration."
        local_comparison_required = True

    return {
        "case": case,
        "label": label,
        "g2b_reachable": g2b_reachable,
        "d2b_procurement_plan_reachable": plan_reachable,
        "d2b_bid_notice_reachable": bid_reachable,
        "d2b_reachable": d2b_reachable,
        "recommended_next_action": action,
        "local_comparison_required": local_comparison_required,
    }


def extract_api_result_code(content: bytes | str) -> str | None:
    if isinstance(content, bytes):
        text = content.decode("utf-8", errors="replace").strip()
    else:
        text = str(content or "").strip()
    if not text:
        return None

    if text.startswith("{") or text.startswith("["):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
        return _find_result_code(payload)

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] == "resultCode":
            value = (node.text or "").strip()
            return value or None
    return None


def assert_safe_summary(summary: dict[str, Any], *, service_key: str) -> None:
    serialized = json.dumps(summary, ensure_ascii=False)
    if service_key and service_key in serialized:
        raise ValueError("Diagnostic summary contains a credential value")
    if "serviceKey=" in serialized or "serviceKey%3D" in serialized:
        raise ValueError("Diagnostic summary contains a credential-bearing URL")
    forbidden_key = _find_forbidden_key(summary)
    if forbidden_key:
        raise ValueError(f"Diagnostic summary contains unsafe field: {forbidden_key}")
    if _contains_authorization_credential(summary):
        raise ValueError("Diagnostic summary contains an authorization credential")


def verify_diagnostic_summary(summary: dict[str, Any], *, service_key: str) -> None:
    required_probes = {
        "dns",
        "tcp",
        "https",
        "g2b",
        "d2b_procurement_plan",
        "d2b_bid_notice",
    }
    if set(summary.get("probes") or {}) != required_probes:
        raise ValueError("Diagnostic output is missing a required probe")

    classification = (summary.get("classification") or {}).get("case")
    if classification == "diagnostic_implementation_failure":
        raise ValueError("Diagnostic implementation failure")
    if classification not in {
        "case_1",
        "case_2",
        "case_3",
        "diagnostic_inconclusive",
    }:
        raise ValueError("Diagnostic classification is invalid")

    security = summary.get("security")
    if not isinstance(security, dict):
        raise ValueError("Diagnostic security metadata is missing")
    for field in (
        "secret_exposure_detected",
        "credential_url_exposure_detected",
        "raw_response_persisted",
    ):
        if security.get(field) is not False:
            raise ValueError(f"Diagnostic security check failed: {field}")

    assert_safe_summary(summary, service_key=service_key)


def write_diagnostic_outputs(summary: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "diagnostic-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "diagnostic-summary.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )


def render_markdown(summary: dict[str, Any]) -> str:
    lines = ["## D2B / data.go.kr Connectivity Diagnostic", ""]
    for name, probe in (summary.get("probes") or {}).items():
        lines.extend(
            [
                f"### {name}",
                "",
                f"- host: {probe.get('host', '-')}",
                f"- scheme: {probe.get('scheme', '-')}",
                f"- port: {probe.get('port', '-')}",
                f"- service_group: {probe.get('service_group') or '-'}",
                f"- operation: {probe.get('operation') or '-'}",
                f"- dns_resolved: {_display(probe.get('dns_resolved'))}",
                f"- resolved_count: {_display(probe.get('resolved_count'))}",
                f"- tcp_connected: {_display(probe.get('tcp_connected'))}",
                f"- tls_reached: {_display(probe.get('tls_reached'))}",
                f"- http_reached: {_display(probe.get('http_reached'))}",
                f"- http_status: {_display(probe.get('http_status'))}",
                f"- api_result_code: {probe.get('api_result_code') or '-'}",
                f"- transport_category: {probe.get('transport_category') or '-'}",
                f"- exception_type: {probe.get('exception_type') or '-'}",
                f"- elapsed_ms: {probe.get('elapsed_ms', 0)}",
                "",
            ]
        )
    classification = summary.get("classification") or {}
    lines.extend(
        [
            "### Classification",
            "",
            f"- case: {classification.get('case', '-')}",
            f"- result: {classification.get('label', '-')}",
            f"- recommended_next_action: {classification.get('recommended_next_action', '-')}",
            "",
        ]
    )
    return "\n".join(lines)


def _g2b_params(service_key: str, current_date: date) -> dict[str, Any]:
    to_date = current_date + timedelta(days=31)
    return {
        "serviceKey": service_key,
        "pageNo": 1,
        "numOfRows": PAGE_SIZE,
        "type": "json",
        "orderBgnYm": current_date.strftime("%Y%m"),
        "orderEndYm": to_date.strftime("%Y%m"),
        "inqryBgnDt": current_date.strftime("%Y%m%d") + "0000",
        "inqryEndDt": to_date.strftime("%Y%m%d") + "2359",
        "orderInsttCd": LH_AGENCY_IDENTIFIER,
    }


def _d2b_params(operation: Any, service_key: str, current_date: date) -> dict[str, Any]:
    if operation.date_format == "%Y%m":
        from_date = current_date
        to_date = current_date + timedelta(days=92)
    else:
        from_date = current_date - timedelta(days=7)
        to_date = current_date
    return {
        "serviceKey": service_key,
        "pageNo": 1,
        "numOfRows": PAGE_SIZE,
        operation.date_start_param: from_date.strftime(operation.date_format),
        operation.date_end_param: to_date.strftime(operation.date_format),
    }


def _find_result_code(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "resultCode":
                result = str(child or "").strip()
                return result or None
            nested = _find_result_code(child)
            if nested:
                return nested
    elif isinstance(value, list):
        for child in value:
            nested = _find_result_code(child)
            if nested:
                return nested
    return None


def _find_forbidden_key(value: Any) -> str | None:
    forbidden_keys = {
        "authorization",
        "raw_payload",
        "raw_response",
        "request_headers",
        "response_body",
        "service_key",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).casefold() in forbidden_keys:
                return str(key)
            nested = _find_forbidden_key(child)
            if nested:
                return nested
    if isinstance(value, list):
        for child in value:
            nested = _find_forbidden_key(child)
            if nested:
                return nested
    return None


def _contains_authorization_credential(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.casefold()
        return "authorization: bearer " in normalized or "authorization: basic " in normalized
    if isinstance(value, dict):
        return any(_contains_authorization_credential(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_authorization_credential(child) for child in value)
    return False


def _network_category(exc: BaseException) -> str:
    if isinstance(exc, (ConnectTimeout, socket.timeout, TimeoutError)):
        return "connect_timeout"
    if isinstance(exc, SSLError) or isinstance(exc, ssl.SSLError):
        return "tls_error"
    if isinstance(exc, Timeout):
        return "timeout"
    if isinstance(exc, ConnectionError):
        return "connection_error"
    if isinstance(exc, socket.gaierror):
        return "dns_error"
    if isinstance(exc, OSError):
        return "connection_error"
    return "network_error"


def _http_category(status_code: int | None) -> str:
    if status_code is None:
        return "none"
    if status_code >= 500:
        return "http_server_error"
    if status_code >= 400:
        return "http_client_error"
    return "none"


def _elapsed_ms(started: float, clock: Clock) -> int:
    return max(0, round((clock() - started) * 1000))


def _display(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)
