from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Any, ClassVar


CANONICAL_SOURCE_RECORD_TYPES = {
    "procurement_plan",
    "pre_spec",
    "bid_notice",
    "bid_result",
    "contract",
}

SOURCE_RECORD_TYPE_ALIASES = {
    "plan": "procurement_plan",
    "order_plan": "procurement_plan",
    "pre_notice": "pre_spec",
    "prespec": "pre_spec",
    "spec": "pre_spec",
    "bid": "bid_notice",
    "notice": "bid_notice",
    "announcement": "bid_notice",
    "result": "bid_result",
    "award": "bid_result",
    "contract_result": "contract",
}


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    for fmt in (
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%Y%m%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y.%m.%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y%m%d%H%M",
    ):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


def parse_amount(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if not text:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if not cleaned or cleaned in {"-", "."}:
        return None
    amount = float(cleaned)
    return int(amount) if amount.is_integer() else amount


def normalize_source_record_type(value: str) -> str:
    normalized = clean_text(value)
    if not normalized:
        raise ValueError("source_record_type is required")
    normalized = SOURCE_RECORD_TYPE_ALIASES.get(normalized.lower(), normalized.lower())
    if normalized not in CANONICAL_SOURCE_RECORD_TYPES:
        allowed = ", ".join(sorted(CANONICAL_SOURCE_RECORD_TYPES))
        raise ValueError(f"unsupported source_record_type={value!r}; allowed={allowed}")
    return normalized


@dataclass(frozen=True)
class BusinessApiConfig:
    source: str
    api_key_env: str
    endpoint_env: str | None = None

    def configured_status(self) -> dict[str, bool | str]:
        return {
            "source": self.source,
            "api_key_env": self.api_key_env,
            "configured": bool(os.getenv(self.api_key_env, "").strip()),
        }


@dataclass(frozen=True)
class NormalizedBusinessRecord:
    source: str
    source_record_type: str
    external_id: str
    title: str
    issuing_organization: str | None = None
    category: str | None = None
    region: str | None = None
    estimated_amount: int | float | None = None
    currency: str = "KRW"
    published_at: str | None = None
    deadline_at: str | None = None
    status: str | None = None
    contract_method: str | None = None
    source_url: str | None = None
    collected_at: str | None = None
    source_updated_at: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_record_type", normalize_source_record_type(self.source_record_type))
        if not clean_text(self.source):
            raise ValueError("source is required")
        if not clean_text(self.external_id):
            raise ValueError("external_id is required")
        if not clean_text(self.title):
            raise ValueError("title is required")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_existing_collector_item(self) -> dict[str, Any]:
        """Return a sanitized item shape that can later enter the existing normalizer."""

        source_type = "procurement_plan" if self.source_record_type == "procurement_plan" else "bid"
        return {
            "source_type": source_type,
            "source_name": self.source,
            "source_record_type": self.source_record_type,
            "source_record_id": self.external_id,
            "title": self.title,
            "organization": self.issuing_organization,
            "category": self.category,
            "region": self.region,
            "amount": self.estimated_amount,
            "currency": self.currency,
            "posted_at": self.published_at,
            "due_at": self.deadline_at,
            "notice_status": self.status,
            "contract_method": self.contract_method,
            "original_url": self.source_url,
            "source_updated_at": self.source_updated_at,
            "collected_at": self.collected_at,
            "data_quality": "external_api_normalized",
        }


class ExternalBusinessSourceAdapter(ABC):
    source: ClassVar[str]
    api_key_env: ClassVar[str]
    endpoint_env: ClassVar[str | None] = None

    @classmethod
    def api_config(cls) -> BusinessApiConfig:
        return BusinessApiConfig(
            source=cls.source,
            api_key_env=cls.api_key_env,
            endpoint_env=cls.endpoint_env,
        )

    @classmethod
    def configured_status(cls) -> dict[str, bool | str]:
        return cls.api_config().configured_status()

    @abstractmethod
    def collect_raw_records(self) -> list[dict[str, Any]]:
        """Fetch raw API records.

        Phase 10A intentionally does not wire this into public JSON generation.
        """

    @abstractmethod
    def normalize_raw_record(self, raw: dict[str, Any]) -> NormalizedBusinessRecord:
        """Map one source-specific raw record into the canonical contract."""

    def normalize_raw_records(self, raw_records: list[dict[str, Any]]) -> list[NormalizedBusinessRecord]:
        return [self.normalize_raw_record(raw) for raw in raw_records]

    @staticmethod
    def collected_now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
