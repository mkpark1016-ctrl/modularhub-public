from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .d2b import (
    D2BApiError,
    D2BClient,
    D2BOperation,
    D2BParseError,
    D2BTransportError,
    D2B_RESOURCES,
)


SCHEMA_VERSION = "1.0"
ENDPOINT_FAMILY = "d2b_gw_facility"
FINGERPRINT_FILE = "d2b-schema-fingerprint.json"
FINGERPRINT_MARKDOWN_FILE = "d2b-schema-fingerprint.md"
EXPECTED_OPERATIONS = (
    "getFcltyPrcurePlanList",
    "getFcltyCmpetBidPblancList",
    "getFcltyOthbcVltrnNtatPlanList",
)
CANONICAL_CANDIDATE_FIELDS = (
    "external_id",
    "title",
    "organization",
    "category",
    "amount",
    "published_at",
    "deadline_at",
)
_SAFE_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:-]{0,127}$")
_SAFE_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")


def collect_schema_fingerprint(
    *,
    client: D2BClient,
    plan_from: date,
    plan_to: date,
    bid_from: date,
    bid_to: date,
) -> dict[str, Any]:
    operations: dict[str, dict[str, Any]] = {}
    for resource_name in ("procurement_plan", "bid_notice"):
        resource = D2B_RESOURCES[resource_name]
        from_date, to_date = (plan_from, plan_to) if resource_name == "procurement_plan" else (bid_from, bid_to)
        for operation in resource.operations:
            operations[operation.name] = _fingerprint_operation(
                client=client,
                operation=operation,
                from_date=from_date,
                to_date=to_date,
            )

    successful = sum(1 for payload in operations.values() if payload["http_reached"] and not payload["error_category"])
    fingerprint_health = "complete" if successful == len(operations) else "partial" if successful else "failed"
    return {
        "schema_version": SCHEMA_VERSION,
        "source": "d2b",
        "endpoint_family": ENDPOINT_FAMILY,
        "page_limit": 1,
        "request_attempted": True,
        "fingerprint_health": fingerprint_health,
        "operations": operations,
        "security": {
            "secret_exposure_detected": False,
            "credential_url_exposure_detected": False,
            "raw_response_persisted": False,
            "response_item_values_persisted": False,
        },
    }


def _fingerprint_operation(
    *,
    client: D2BClient,
    operation: D2BOperation,
    from_date: date,
    to_date: date,
) -> dict[str, Any]:
    endpoint = urlparse(operation.endpoint())
    base = {
        "operation": operation.name,
        "endpoint_scheme": endpoint.scheme,
        "endpoint_host": endpoint.hostname or "",
        "http_reached": False,
        "http_status": None,
        "api_result_code": None,
        "response_format": None,
        "records_observed": 0,
        "key_count": 0,
        "observed_keys": [],
        "candidate_mapping": {field: [] for field in CANONICAL_CANDIDATE_FIELDS},
        "error_category": None,
        "exception_type": None,
    }
    try:
        page = client.fetch_page(operation, page_no=1, from_date=from_date, to_date=to_date)
    except (D2BApiError, D2BParseError, D2BTransportError, RuntimeError) as exc:
        diagnostic = getattr(exc, "diagnostic", {})
        base.update(
            {
                "http_reached": isinstance(exc, (D2BApiError, D2BParseError)),
                "api_result_code": diagnostic.get("result_code"),
                "error_category": diagnostic.get("category", "api_error"),
                "exception_type": diagnostic.get("exception_type") or type(exc).__name__,
            }
        )
        return base

    observed_keys = sorted(
        {str(key) for item in page.payload.items for key in item},
        key=lambda value: (value.casefold(), value),
    )
    base.update(
        {
            "http_reached": True,
            "http_status": page.http_status,
            "api_result_code": page.payload.result_code,
            "response_format": page.payload.response_format,
            "records_observed": len(page.payload.items),
            "key_count": len(observed_keys),
            "observed_keys": observed_keys,
            "candidate_mapping": candidate_mapping_from_keys(observed_keys),
        }
    )
    return base


def candidate_mapping_from_keys(observed_keys: list[str]) -> dict[str, list[str]]:
    rules = {
        "external_id": ("no", "id", "sn", "seq", "number"),
        "title": ("nm", "name", "title", "subject", "sj"),
        "organization": ("ornt", "org", "instt", "agency"),
        "category": ("se", "type", "div", "kind", "ctgry", "category"),
        "amount": ("amt", "amount", "price", "budget", "bdgt", "expt"),
        "published_at": ("anmt", "pblanc", "ntce", "reg", "rgst", "publish", "posted"),
        "deadline_at": ("clos", "close", "deadline", "end", "due"),
    }
    candidates: dict[str, list[str]] = {}
    for field in CANONICAL_CANDIDATE_FIELDS:
        tokens = rules[field]
        candidates[field] = [key for key in observed_keys if any(token in key.casefold() for token in tokens)]
    return candidates


def verify_schema_fingerprint(summary: dict[str, Any], *, service_key: str) -> None:
    expected_top_level = {
        "schema_version",
        "source",
        "endpoint_family",
        "page_limit",
        "request_attempted",
        "fingerprint_health",
        "operations",
        "security",
    }
    if set(summary) != expected_top_level:
        raise ValueError("Schema fingerprint has unexpected top-level fields")
    if summary.get("schema_version") != SCHEMA_VERSION or summary.get("source") != "d2b":
        raise ValueError("Schema fingerprint identity is invalid")
    if summary.get("endpoint_family") != ENDPOINT_FAMILY or summary.get("page_limit") != 1:
        raise ValueError("Schema fingerprint request scope is invalid")
    if summary.get("request_attempted") is not True:
        raise ValueError("Schema fingerprint request was not attempted")
    if summary.get("fingerprint_health") not in {"complete", "partial", "failed"}:
        raise ValueError("Schema fingerprint health is invalid")

    operations = summary.get("operations")
    if not isinstance(operations, dict) or tuple(operations) != EXPECTED_OPERATIONS:
        raise ValueError("Schema fingerprint operations are missing or out of order")
    for operation_name, payload in operations.items():
        _verify_operation(operation_name, payload)

    security = summary.get("security")
    expected_security = {
        "secret_exposure_detected",
        "credential_url_exposure_detected",
        "raw_response_persisted",
        "response_item_values_persisted",
    }
    if not isinstance(security, dict) or set(security) != expected_security:
        raise ValueError("Schema fingerprint security metadata is invalid")
    for field in expected_security:
        if security.get(field) is not False:
            raise ValueError(f"Schema fingerprint security check failed: {field}")

    serialized = json.dumps(summary, ensure_ascii=False)
    if service_key and service_key in serialized:
        raise ValueError("Schema fingerprint contains a credential value")
    if "serviceKey=" in serialized or "serviceKey%3D" in serialized:
        raise ValueError("Schema fingerprint contains a credential-bearing URL")
    lowered = serialized.casefold()
    if "authorization: bearer " in lowered or "authorization: basic " in lowered:
        raise ValueError("Schema fingerprint contains an authorization credential")


def _verify_operation(operation_name: str, payload: Any) -> None:
    expected_fields = {
        "operation",
        "endpoint_scheme",
        "endpoint_host",
        "http_reached",
        "http_status",
        "api_result_code",
        "response_format",
        "records_observed",
        "key_count",
        "observed_keys",
        "candidate_mapping",
        "error_category",
        "exception_type",
    }
    if not isinstance(payload, dict) or set(payload) != expected_fields:
        raise ValueError(f"Schema fingerprint operation fields are invalid: {operation_name}")
    if payload.get("operation") != operation_name:
        raise ValueError(f"Schema fingerprint operation name mismatch: {operation_name}")
    if payload.get("endpoint_scheme") != "https" or payload.get("endpoint_host") != "apis.data.go.kr":
        raise ValueError(f"Schema fingerprint endpoint is invalid: {operation_name}")
    if not isinstance(payload.get("http_reached"), bool):
        raise ValueError(f"Schema fingerprint HTTP state is invalid: {operation_name}")
    for field in ("http_status", "records_observed", "key_count"):
        value = payload.get(field)
        if field == "http_status" and value is None:
            continue
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"Schema fingerprint numeric metadata is invalid: {operation_name}.{field}")
    for field in ("api_result_code", "error_category", "exception_type"):
        value = payload.get(field)
        if value is not None and (not isinstance(value, str) or not _SAFE_TOKEN_PATTERN.fullmatch(value)):
            raise ValueError(f"Schema fingerprint token is invalid: {operation_name}.{field}")
    if payload.get("response_format") not in {None, "xml", "json", "empty"}:
        raise ValueError(f"Schema fingerprint response format is invalid: {operation_name}")

    observed_keys = payload.get("observed_keys")
    if not isinstance(observed_keys, list) or any(not isinstance(key, str) for key in observed_keys):
        raise ValueError(f"Schema fingerprint observed keys are invalid: {operation_name}")
    if any(not _SAFE_KEY_PATTERN.fullmatch(key) for key in observed_keys):
        raise ValueError(f"Schema fingerprint observed key format is invalid: {operation_name}")
    expected_order = sorted(set(observed_keys), key=lambda value: (value.casefold(), value))
    if observed_keys != expected_order or payload.get("key_count") != len(observed_keys):
        raise ValueError(f"Schema fingerprint observed keys are not deterministic: {operation_name}")

    candidate_mapping = payload.get("candidate_mapping")
    if not isinstance(candidate_mapping, dict) or tuple(candidate_mapping) != CANONICAL_CANDIDATE_FIELDS:
        raise ValueError(f"Schema fingerprint candidate mapping is invalid: {operation_name}")
    for candidates in candidate_mapping.values():
        if not isinstance(candidates, list) or any(candidate not in observed_keys for candidate in candidates):
            raise ValueError(f"Schema fingerprint candidate field was not observed: {operation_name}")


def write_schema_fingerprint(summary: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / FINGERPRINT_FILE).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / FINGERPRINT_MARKDOWN_FILE).write_text(render_fingerprint_markdown(summary), encoding="utf-8")


def render_fingerprint_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "## D2B Live Schema Fingerprint",
        "",
        f"- fingerprint_health: {summary.get('fingerprint_health', '-')}",
        f"- page_limit: {summary.get('page_limit', '-')}",
    ]
    for operation_name, payload in (summary.get("operations") or {}).items():
        keys = ", ".join(f"`{key}`" for key in payload.get("observed_keys") or []) or "-"
        lines.extend(
            [
                "",
                f"### {operation_name}",
                f"- http_status: {payload.get('http_status', '-')}",
                f"- api_result_code: {payload.get('api_result_code', '-')}",
                f"- records_observed: {payload.get('records_observed', 0)}",
                f"- key_count: {payload.get('key_count', 0)}",
                f"- error_category: {payload.get('error_category', '-')}",
                f"- observed_keys: {keys}",
            ]
        )
    return "\n".join(lines) + "\n"
