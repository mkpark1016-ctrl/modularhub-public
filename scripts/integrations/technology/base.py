from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from scripts.integrations.business.base import clean_text, parse_date


KIPRIS_API_KEY_ENV = "KIPRIS_API_KEY"


@dataclass(frozen=True)
class NormalizedTechnologyRecord:
    source: str
    external_id: str
    title: str
    record_type: str = "patent"
    applicant: str | None = None
    owner: str | None = None
    application_number: str | None = None
    registration_number: str | None = None
    status: str | None = None
    filed_at: str | None = None
    registered_at: str | None = None
    source_url: str | None = None
    collected_at: str | None = None
    source_updated_at: str | None = None

    def __post_init__(self) -> None:
        if not clean_text(self.source):
            raise ValueError("source is required")
        if not clean_text(self.external_id):
            raise ValueError("external_id is required")
        if not clean_text(self.title):
            raise ValueError("title is required")
        object.__setattr__(self, "filed_at", parse_date(self.filed_at))
        object.__setattr__(self, "registered_at", parse_date(self.registered_at))
        object.__setattr__(self, "source_updated_at", parse_date(self.source_updated_at))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
