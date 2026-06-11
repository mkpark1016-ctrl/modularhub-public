from __future__ import annotations

from datetime import date
from hashlib import sha256
from typing import Any


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def generate_unique_hash(*parts: Any) -> str:
    normalized = "|".join(normalize_text(part).lower() for part in parts)
    return sha256(normalized.encode("utf-8")).hexdigest()


def parse_optional_date(value: Any) -> date | None:
    text = normalize_text(value)
    if not text:
        return None
    return date.fromisoformat(text)


def parse_optional_int(value: Any) -> int | None:
    text = normalize_text(value).replace(",", "")
    if not text:
        return None
    return int(float(text))
