from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from scripts.integrations.business.base import clean_text, parse_date


KIPRIS_API_KEY_ENV = "KIPRIS_API_KEY"
TECHNOLOGY_RECORD_TYPES = frozenset({"patent", "construction_new_technology"})
SENSITIVE_QUERY_KEYS = frozenset({
    "accesskey",
    "apikey",
    "api_key",
    "authorization",
    "client_secret",
    "servicekey",
    "token",
})
FORBIDDEN_RAW_KEYS = frozenset({
    "accesskey",
    "apikey",
    "api_key",
    "authorization",
    "client_secret",
    "headers",
    "raw_response",
    "request_headers",
    "servicekey",
})


def _clean_tuple(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    cleaned = [clean_text(value) for value in (values or ())]
    return tuple(sorted(dict.fromkeys(value for value in cleaned if value), key=str.casefold))


def normalize_official_number(value: str | None) -> str | None:
    normalized = re.sub(r"[^0-9A-Za-z]", "", clean_text(value) or "").upper()
    return normalized or None


def validate_public_source_url(value: str | None) -> str | None:
    url = clean_text(value)
    if not url:
        return None
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("source_url must be an absolute HTTP(S) URL")
    query_keys = {key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    if query_keys & SENSITIVE_QUERY_KEYS:
        raise ValueError("source_url must not contain credential query parameters")
    if parsed.username or parsed.password:
        raise ValueError("source_url must not contain credentials")
    return url


def validate_raw_payload_keys(raw: dict[str, Any]) -> None:
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            lowered = {str(key).lower() for key in value}
            forbidden = sorted(lowered & FORBIDDEN_RAW_KEYS)
            if forbidden:
                raise ValueError(f"raw payload contains sensitive or non-canonical fields: {', '.join(forbidden)}")
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(raw)


@dataclass(frozen=True)
class NormalizedTechnologyRecord:
    source: str
    external_id: str
    title: str
    record_type: str = "patent"
    applicant: str | None = None
    owner: str | None = None
    applicants: tuple[str, ...] = ()
    owners: tuple[str, ...] = ()
    developers: tuple[str, ...] = ()
    application_number: str | None = None
    registration_number: str | None = None
    patent_number: str | None = None
    newtech_number: str | None = None
    status: str | None = None
    filed_at: str | None = None
    registered_at: str | None = None
    application_date: str | None = None
    registration_date: str | None = None
    designation_date: str | None = None
    expiration_date: str | None = None
    abstract: str | None = None
    keywords: tuple[str, ...] = ()
    technology_area: str | None = None
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
        record_type = (clean_text(self.record_type) or "").lower()
        if record_type not in TECHNOLOGY_RECORD_TYPES:
            raise ValueError(f"unsupported technology record_type={record_type!r}")
        object.__setattr__(self, "record_type", record_type)
        applicants = _clean_tuple((*self.applicants, self.applicant) if self.applicant else self.applicants)
        owners = _clean_tuple((*self.owners, self.owner) if self.owner else self.owners)
        object.__setattr__(self, "applicants", applicants)
        object.__setattr__(self, "owners", owners)
        object.__setattr__(self, "developers", _clean_tuple(self.developers))
        object.__setattr__(self, "keywords", _clean_tuple(self.keywords))
        application_date = parse_date(self.application_date or self.filed_at)
        registration_date = parse_date(self.registration_date or self.registered_at)
        object.__setattr__(self, "application_date", application_date)
        object.__setattr__(self, "registration_date", registration_date)
        object.__setattr__(self, "filed_at", application_date)
        object.__setattr__(self, "registered_at", registration_date)
        object.__setattr__(self, "designation_date", parse_date(self.designation_date))
        object.__setattr__(self, "expiration_date", parse_date(self.expiration_date))
        object.__setattr__(self, "source_updated_at", parse_date(self.source_updated_at))
        object.__setattr__(self, "source_url", validate_public_source_url(self.source_url))
        self.identity_key()

    @property
    def source_record_type(self) -> str:
        return self.record_type

    def identity_key(self) -> str:
        if self.record_type == "patent":
            number = (
                normalize_official_number(self.application_number)
                or normalize_official_number(self.registration_number)
                or normalize_official_number(self.patent_number)
            )
        else:
            number = normalize_official_number(self.newtech_number or self.registration_number)
        if not number:
            raise ValueError(f"official identity number is required for {self.record_type}")
        return f"{self.record_type}:{number}"

    def identity_aliases(self) -> tuple[str, ...]:
        if self.record_type == "patent":
            numbers = (self.application_number, self.registration_number, self.patent_number)
        else:
            numbers = (self.newtech_number, self.registration_number)
        return tuple(
            dict.fromkeys(
                f"{self.record_type}:{number}"
                for number in (normalize_official_number(value) for value in numbers)
                if number
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
