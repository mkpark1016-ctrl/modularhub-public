#!/usr/bin/env python3
"""Tests for the OpenDART client wrapper."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.opendart_client import OpenDartApiKeyRequired, OpenDartClient, normalize_name  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    old_key = os.environ.pop("OPENDART_API_KEY", None)
    try:
        client = OpenDartClient(api_key=None, cache_dir=Path(tempfile.mkdtemp()))
        require(not client.has_api_key, "client should not report an API key when env is unset")
        try:
            client.require_api_key()
        except OpenDartApiKeyRequired:
            pass
        else:
            raise AssertionError("require_api_key should fail without OPENDART_API_KEY")

        require(normalize_name(" 금강 공업 ") == "금강공업", "Korean corporate-name normalization failed")
        require(normalize_name("Kumkang Kind") == "kumkangkind", "English corporate-name normalization failed")

        keyed = OpenDartClient(api_key="test-key", cache_dir=Path(tempfile.mkdtemp()))
        require(keyed.has_api_key, "explicit API key should be recognized")
        require(keyed.require_api_key() == "test-key", "explicit API key should be returned unchanged")
    finally:
        if old_key is not None:
            os.environ["OPENDART_API_KEY"] = old_key

    print("OPENDART CLIENT TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
