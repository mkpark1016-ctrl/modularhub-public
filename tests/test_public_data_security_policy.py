from __future__ import annotations

import json

import pytest

from scripts.validate_company_audit_financials import protected_public_security_status
from src.public_data_policy import (
    classify_public_local_path,
    find_public_local_paths,
    scan_public_payload_security,
    validate_public_local_path_cleanup,
)


@pytest.mark.parametrize("value", [r"C:\private\source.xml", r"Z:\build\generated.json"])
def test_windows_drive_absolute_paths_are_rejected(value: str) -> None:
    assert classify_public_local_path(value) == "windows_drive"


def test_file_url_is_rejected() -> None:
    assert classify_public_local_path("file:///Users/example/report.xml") == "file_url"


def test_unc_path_is_rejected() -> None:
    assert classify_public_local_path(r"\\server\share\report.xml") == "unc"


@pytest.mark.parametrize(
    "value",
    [
        "https://plus.kipris.or.kr/portal/patent",
        "http://example.test/public/report",
        "original_document.xml",
        "10-2023-0005994",
        "1020230005994",
        "official:kipris:patent:1020230005994",
        "2026-08-27",
    ],
)
def test_public_identifiers_and_urls_are_allowed(value: str) -> None:
    assert classify_public_local_path(value) is None


def test_nested_dict_and_list_path_is_detected_with_redacted_diagnostic() -> None:
    sensitive_value = r"D:\private\company\original.xml"
    payload = {"companies": [{"documents": [{"document_path": sensitive_value}]}]}
    findings = find_public_local_paths(payload)
    assert findings == [{
        "json_path": "$.companies[0].documents[0].document_path",
        "field": "document_path",
        "path_kind": "windows_drive",
    }]
    assert sensitive_value not in json.dumps(findings)


def test_public_payload_security_rejects_local_path_without_echoing_value() -> None:
    sensitive_value = r"C:\Users\example\private.xml"
    result = scan_public_payload_security({"document_path": sensitive_value})
    assert result["passed"] is False
    assert result["local_path_count"] == 1
    assert sensitive_value not in json.dumps(result)


def test_local_path_cleanup_allows_only_path_value_deletion() -> None:
    before = {
        "companies": [{
            "company_id": "sample",
            "documents": [{
                "document_name": "original.xml",
                "document_path": r"D:\private\original.xml",
            }],
        }]
    }
    after = {
        "companies": [{
            "company_id": "sample",
            "documents": [{"document_name": "original.xml"}],
        }]
    }

    result = validate_public_local_path_cleanup(before, after)

    assert result == {
        "passed": True,
        "removed_local_path_count": 1,
        "remaining_local_path_count": 0,
        "other_changes": 0,
    }


def test_local_path_cleanup_rejects_any_other_value_change() -> None:
    before = {
        "document_name": "original.xml",
        "document_path": r"D:\private\original.xml",
    }
    after = {"document_name": "renamed.xml"}

    result = validate_public_local_path_cleanup(before, after)

    assert result["passed"] is False
    assert result["other_changes"] == 1


def test_actual_public_json_is_security_clean() -> None:
    result = protected_public_security_status()
    assert result["passed"] is True
    assert result["local_path_count"] == 0
    assert result["credential_url_count"] == 0
    assert result["forbidden_field_count"] == 0
