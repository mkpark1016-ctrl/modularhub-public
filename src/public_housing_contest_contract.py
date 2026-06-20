from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


SOURCE_TYPE = "public_agency_contest"
BUSINESS_TYPE = "private_participation_public_housing"


@dataclass
class PublicHousingContestItem:
    id: str | None = None
    source_code: str = ""
    source_name: str = ""
    organization: str = ""
    source_type: str = SOURCE_TYPE
    business_type: str = BUSINESS_TYPE
    notice_stage: str = "unknown"
    title: str = ""
    normalized_title: str = ""
    project_name: str = ""
    project_sites: list[str] = field(default_factory=list)
    project_blocks: list[str] = field(default_factory=list)
    posted_at: str | None = None
    deadline_at: str | None = None
    application_schedule_text: str = ""
    estimated_cost: str | None = None
    household_count: str | None = None
    housing_type: str | None = None
    body_summary: str = ""
    original_url: str | None = None
    board_url: str = ""
    source_record_id: str = ""
    attachments: list[dict[str, str]] = field(default_factory=list)
    status: str = "probe_only"
    modular_relevance: str = "unconfirmed"
    modular_relevance_score: int = 0
    modular_evidence: list[str] = field(default_factory=list)
    collected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    fingerprint: str = ""
    related_group_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["fingerprint"]:
            data["fingerprint"] = make_fingerprint(data)
        return data


def make_fingerprint(item: dict[str, Any]) -> str:
    parts = [
        str(item.get("source_code") or ""),
        str(item.get("source_record_id") or ""),
        str(item.get("normalized_title") or item.get("title") or ""),
        str(item.get("posted_at") or ""),
    ]
    return sha256("|".join(parts).encode("utf-8")).hexdigest()


def default_contract_fields() -> list[str]:
    return list(PublicHousingContestItem().__dataclass_fields__.keys())
