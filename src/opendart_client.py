"""Small OpenDART client used by company research scripts.

The client never embeds API credentials. Set OPENDART_API_KEY in the
environment before making live requests. Cache files live under
.cache/opendart, which is intentionally ignored by git.
"""

from __future__ import annotations

import os
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from src.env_config import load_project_dotenv


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = ROOT / ".cache" / "opendart"
BASE_URL = "https://opendart.fss.or.kr/api"


class OpenDartError(RuntimeError):
    """Base error for OpenDART calls."""


class OpenDartApiKeyRequired(OpenDartError):
    """Raised when a live OpenDART call is attempted without an API key."""


class OpenDartResponseError(OpenDartError):
    """Raised when OpenDART returns a non-success status."""

    def __init__(self, status: str, message: str | None = None) -> None:
        self.status = status
        self.message = message or ""
        super().__init__(f"OpenDART status={status} message={self.message}")


@dataclass
class OpenDartClient:
    api_key: str | None = None
    cache_dir: Path = DEFAULT_CACHE_DIR
    timeout: int = 30
    retries: int = 2
    retry_delay_seconds: float = 1.0

    def __post_init__(self) -> None:
        load_project_dotenv()
        if self.api_key is None:
            self.api_key = os.getenv("OPENDART_API_KEY")
        self.cache_dir = Path(self.cache_dir)

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)

    def require_api_key(self) -> str:
        if not self.api_key:
            raise OpenDartApiKeyRequired("OPENDART_API_KEY is not set")
        return self.api_key

    def _request_bytes(self, endpoint: str, params: dict[str, Any], *, require_json_status: bool = True) -> bytes:
        key = self.require_api_key()
        query = dict(params)
        query["crtfc_key"] = key
        url = f"{BASE_URL}/{endpoint}?{urllib.parse.urlencode(query)}"
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "ModularHubOpenDart/1.0"})
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = response.read()
                if require_json_status and body[:1] == b"{":
                    import json

                    payload = json.loads(body.decode("utf-8"))
                    status = str(payload.get("status", ""))
                    if status and status != "000":
                        raise OpenDartResponseError(status, str(payload.get("message", "")))
                return body
            except Exception as exc:  # pragma: no cover - live network retry guard
                if isinstance(exc, OpenDartResponseError):
                    raise
                last_error = exc
                if attempt < self.retries:
                    time.sleep(self.retry_delay_seconds * (attempt + 1))
        raise OpenDartError(f"OpenDART request failed: {last_error}")

    def list_corp_codes(self, *, refresh: bool = False) -> list[dict[str, str]]:
        cache_path = self.cache_dir / "corp_codes.xml"
        if refresh or not cache_path.exists():
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            body = self._request_bytes("corpCode.xml", {}, require_json_status=False)
            zip_path = self.cache_dir / "corp_codes.zip"
            zip_path.write_bytes(body)
            with zipfile.ZipFile(zip_path) as archive:
                xml_name = next(name for name in archive.namelist() if name.lower().endswith(".xml"))
                cache_path.write_bytes(archive.read(xml_name))
        root = ElementTree.fromstring(cache_path.read_bytes())
        rows: list[dict[str, str]] = []
        for node in root.findall("list"):
            rows.append(
                {
                    "corp_code": text(node, "corp_code"),
                    "corp_name": text(node, "corp_name"),
                    "stock_code": text(node, "stock_code"),
                    "modify_date": text(node, "modify_date"),
                }
            )
        return rows

    def find_corp_codes(self, names: list[str]) -> list[dict[str, str]]:
        normalized = {normalize_name(name) for name in names if normalize_name(name)}
        return [row for row in self.list_corp_codes() if normalize_name(row.get("corp_name")) in normalized]

    def list_filings(
        self,
        *,
        corp_code: str,
        start_date: str,
        end_date: str,
        pblntf_detail_ty: str | None = None,
        page_no: int = 1,
        page_count: int = 100,
    ) -> dict[str, Any]:
        import json

        params: dict[str, Any] = {
            "corp_code": corp_code,
            "bgn_de": start_date,
            "end_de": end_date,
            "page_no": page_no,
            "page_count": page_count,
        }
        if pblntf_detail_ty:
            params["pblntf_detail_ty"] = pblntf_detail_ty
        body = self._request_bytes(
            "list.json",
            params,
        )
        return json.loads(body.decode("utf-8"))

    def company_overview(self, corp_code: str) -> dict[str, Any]:
        import json

        body = self._request_bytes("company.json", {"corp_code": corp_code})
        return json.loads(body.decode("utf-8"))

    def single_account_all(self, *, corp_code: str, fiscal_year: int, report_code: str = "11011") -> dict[str, Any]:
        import json

        body = self._request_bytes(
            "fnlttSinglAcntAll.json",
            {
                "corp_code": corp_code,
                "bsns_year": str(fiscal_year),
                "reprt_code": report_code,
                "fs_div": "OFS",
            },
        )
        return json.loads(body.decode("utf-8"))

    def download_document(self, receipt_number: str) -> Path:
        directory = self.cache_dir / "documents"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{receipt_number}.zip"
        if not path.exists():
            path.write_bytes(self._request_bytes("document.xml", {"rcept_no": receipt_number}, require_json_status=False))
        return path


def text(node: ElementTree.Element, tag: str) -> str:
    value = node.findtext(tag)
    return "" if value is None else value.strip()


def normalize_name(value: str | None) -> str:
    if not value:
        return ""
    return "".join(str(value).lower().split())
