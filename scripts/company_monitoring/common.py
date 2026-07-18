from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CONFIG_DIR = ROOT / "config" / "company_monitoring"
RAW_DIR = ROOT / "artifacts" / "company_monitoring" / "raw"
DATA_DIR = ROOT / "data" / "company_monitoring"
REPORT_DIR = ROOT / "reports" / "company_monitoring"
FRONTEND_COMPANIES_PATH = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"

PROJECT_CREDIT_ALLOWED_STATUSES = {"completed", "under_construction", "contracted", "awarded"}
PROJECT_CREDIT_BLOCKED_STATUSES = {
    "preferred_bidder",
    "planned",
    "unconfirmed",
    "cancelled",
    "mou_signed",
    "partnership_discussion",
    "r_and_d",
    "exhibition",
    "pre_con",
    "not_signed",
}


@dataclass(frozen=True)
class MonitorCompany:
    company_id: str
    canonical_name: str
    aliases: tuple[str, ...]
    english_names: tuple[str, ...]
    dart_corp_code: str | None
    stock_code: str | None
    official_domains: tuple[str, ...]
    positive_keywords: tuple[str, ...]
    negative_keywords: tuple[str, ...]
    enabled_sources: tuple[str, ...]
    enabled: bool

    @property
    def search_names(self) -> list[str]:
        values = [self.canonical_name, *self.aliases, *self.english_names]
        output: list[str] = []
        for value in values:
            if value and value not in output:
                output.append(value)
        return output


def parse_company_arg(value: str | None) -> set[str] | None:
    if not value:
        return None
    return {item.strip() for item in value.split(",") if item.strip()}


def parse_common_args(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--companies", default="", help="Comma-separated company_id list. Defaults to enabled companies.")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--fixture", type=Path, default=None, help="Optional fixture payload for tests/offline runs.")
    parser.add_argument("--output-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--live", action="store_true", help="Allow real external API requests.")
    parser.add_argument("--acknowledge-live", action="store_true", help="Acknowledge that this run may call external APIs.")
    return parser


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def iso_now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def yyyymmdd_days_ago(days: int) -> str:
    return (utc_now() - timedelta(days=days)).strftime("%Y%m%d")


def yyyymmdd_today() -> str:
    return utc_now().strftime("%Y%m%d")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_monitor_companies(selected: set[str] | None = None, *, include_disabled: bool = False) -> list[MonitorCompany]:
    payload = read_json(CONFIG_DIR / "companies.json")
    companies: list[MonitorCompany] = []
    for row in payload.get("companies", []):
        if selected is not None and row.get("company_id") not in selected:
            continue
        if selected is None and not include_disabled and not row.get("enabled"):
            continue
        companies.append(
            MonitorCompany(
                company_id=row["company_id"],
                canonical_name=row["canonical_name"],
                aliases=tuple(row.get("aliases") or []),
                english_names=tuple(row.get("english_names") or []),
                dart_corp_code=row.get("dart_corp_code"),
                stock_code=row.get("stock_code"),
                official_domains=tuple(row.get("official_domains") or []),
                positive_keywords=tuple(row.get("positive_keywords") or []),
                negative_keywords=tuple(row.get("negative_keywords") or []),
                enabled_sources=tuple(row.get("enabled_sources") or []),
                enabled=bool(row.get("enabled")),
            )
        )
    return companies


def load_source_policy() -> dict[str, Any]:
    return read_json(CONFIG_DIR / "source_policy.json")


def load_query_keywords() -> dict[str, Any]:
    return read_json(CONFIG_DIR / "query_keywords.json")


def load_public_companies() -> dict[str, Any]:
    return read_json(FRONTEND_COMPANIES_PATH)


def public_company_ids() -> set[str]:
    return {row["company_id"] for row in load_public_companies().get("companies", [])}


TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    import html

    return SPACE_RE.sub(" ", TAG_RE.sub("", html.unescape(str(value)))).strip()


def normalize_title(value: str | None) -> str:
    text = strip_html(value).lower()
    text = re.sub(r"[\[\]\(\){}<>\"'“”‘’|·]", " ", text)
    text = re.sub(r"\b(주식회사|주|co ltd|ltd|inc)\b", " ", text)
    return SPACE_RE.sub(" ", text).strip()


def canonical_url(value: str | None) -> str:
    if not value:
        return ""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    split = urlsplit(str(value).strip())
    scheme = split.scheme.lower() or "https"
    netloc = split.netloc.lower()
    path = split.path.rstrip("/") or split.path
    query_items = [
        (key, val)
        for key, val in parse_qsl(split.query, keep_blank_values=False)
        if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}
    ]
    query = urlencode(query_items, doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def hash_evidence(*parts: object) -> str:
    text = "\n".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_id(source_type: str, company_id: str, document_id: str | None, url: str | None, title: str | None) -> str:
    digest = hash_evidence(source_type, company_id, document_id or canonical_url(url), normalize_title(title))[:16]
    return f"{source_type}-{company_id}-{digest}"


def load_monitoring_environment() -> bool:
    """Load repository-root .env through the central env loader."""

    from src.env_config import load_project_dotenv

    return load_project_dotenv()


def masked_config_status(value: str | None) -> str:
    if not value:
        return "missing"
    return "configured"


def env_flag(name: str) -> bool:
    load_monitoring_environment()
    return bool(os.getenv(name))


def live_opt_in_enabled(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "live", False) and getattr(args, "acknowledge_live", False))


def live_opt_in_error(source_type: str, companies: list[MonitorCompany], fetched_at: str) -> list[dict[str, Any]]:
    return [
        {
            "source_type": source_type,
            "company_id": company.company_id,
            "status": "error",
            "error_type": "LIVE_OPT_IN_REQUIRED",
            "fetched_at": fetched_at,
            "records": [],
            "candidates": [],
        }
        for company in companies
    ]


def fail_source(source_type: str, message: str, *, company_id: str | None = None) -> dict[str, Any]:
    return {
        "source_type": source_type,
        "company_id": company_id,
        "status": "error",
        "error_type": message,
        "fetched_at": iso_now(),
    }


def safe_error_message(exc: Exception, fallback: str) -> str:
    message = str(exc) or fallback
    message = re.sub(r"(crtfc_key=)[^&\s]+", r"\1***", message, flags=re.I)
    message = re.sub(r"(X-Naver-Client-Secret[:=]\s*)\S+", r"\1***", message, flags=re.I)
    if len(message) > 180:
        message = message[:177] + "..."
    return message


def ensure_repo_root_on_path() -> None:
    root_str = str(ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
