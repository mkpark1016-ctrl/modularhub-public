from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.news_publisher_region import (
    hostname_from_url,
    is_intermediary_domain,
    normalize_domain,
    normalize_key,
    publisher_region_fields,
)


ROOT = Path(__file__).resolve().parents[1]
PUBLISHER_COUNTRY_CONFIG_PATH = ROOT / "config" / "news_publisher_countries.json"

COUNTRY_NAMES: dict[str, str] = {
    "AU": "호주",
    "CA": "캐나다",
    "DE": "독일",
    "GB": "영국",
    "HK": "홍콩",
    "IE": "아일랜드",
    "JM": "자메이카",
    "KR": "대한민국",
    "NZ": "뉴질랜드",
    "TH": "태국",
    "UA": "우크라이나",
    "US": "미국",
}

COUNTRY_TLD_MAP: dict[str, str] = {
    ".com.au": "AU",
    ".co.uk": "GB",
    ".com.hk": "HK",
    ".co.kr": "KR",
    ".com.ua": "UA",
    ".co.nz": "NZ",
    ".au": "AU",
    ".ca": "CA",
    ".de": "DE",
    ".hk": "HK",
    ".ie": "IE",
    ".jm": "JM",
    ".kr": "KR",
    ".nz": "NZ",
    ".th": "TH",
    ".ua": "UA",
    ".uk": "GB",
}

VALID_CONFIDENCE = {"high", "medium", "low", "unknown"}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def country_payload(code: str, *, confidence: str, reason: str) -> dict[str, str]:
    normalized_code = clean_text(code).upper()
    if normalized_code not in COUNTRY_NAMES:
        return unknown_country(reason="unknown")
    return {
        "publisher_country_code": normalized_code,
        "publisher_country_name": COUNTRY_NAMES[normalized_code],
        "publisher_country_confidence": confidence if confidence in VALID_CONFIDENCE else "unknown",
        "publisher_country_reason": reason,
    }


def unknown_country(*, reason: str = "unknown") -> dict[str, str]:
    return {
        "publisher_country_code": "",
        "publisher_country_name": "국가 미확인",
        "publisher_country_confidence": "unknown",
        "publisher_country_reason": reason or "unknown",
    }


def _coerce_country_entry(value: Any) -> dict[str, str] | None:
    if isinstance(value, str):
        code = value.upper()
        if code in COUNTRY_NAMES:
            return {"country_code": code, "country_name": COUNTRY_NAMES[code], "confidence": "high"}
        return None
    if not isinstance(value, dict):
        return None
    code = clean_text(value.get("country_code")).upper()
    name = clean_text(value.get("country_name"))
    confidence = clean_text(value.get("confidence")) or "high"
    if code not in COUNTRY_NAMES or name != COUNTRY_NAMES[code]:
        return None
    return {"country_code": code, "country_name": name, "confidence": confidence}


@lru_cache(maxsize=1)
def load_publisher_country_config() -> dict[str, dict[str, dict[str, str]]]:
    try:
        payload = json.loads(PUBLISHER_COUNTRY_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    domains = payload.get("domains", {}) if isinstance(payload, dict) else {}
    publishers = payload.get("publishers", {}) if isinstance(payload, dict) else {}

    normalized_domains: dict[str, dict[str, str]] = {}
    for key, value in domains.items():
        entry = _coerce_country_entry(value)
        domain = normalize_domain(key)
        if domain and entry:
            normalized_domains[domain] = entry

    normalized_publishers: dict[str, dict[str, str]] = {}
    for key, value in publishers.items():
        entry = _coerce_country_entry(value)
        publisher = normalize_key(key)
        if publisher and entry:
            normalized_publishers[publisher] = entry

    return {"domains": normalized_domains, "publishers": normalized_publishers}


def mapped_country_for_domain(domain: Any) -> tuple[dict[str, str], str]:
    normalized = normalize_domain(domain)
    if not normalized or is_intermediary_domain(normalized):
        return unknown_country(reason="unknown"), "domain_missing"

    config = load_publisher_country_config()
    for candidate, entry in config["domains"].items():
        if normalized == candidate or normalized.endswith(f".{candidate}"):
            return (
                country_payload(
                    entry["country_code"],
                    confidence=entry.get("confidence", "high"),
                    reason="explicit_domain_map",
                ),
                candidate,
            )

    for suffix, code in COUNTRY_TLD_MAP.items():
        if normalized.endswith(suffix):
            return country_payload(code, confidence="medium", reason="country_tld"), suffix

    return unknown_country(reason="unknown"), "domain_unmapped"


def mapped_country_for_publisher(name: Any) -> tuple[dict[str, str], str]:
    normalized = normalize_key(name)
    if not normalized:
        return unknown_country(reason="unknown"), "publisher_missing"

    config = load_publisher_country_config()
    for candidate, entry in config["publishers"].items():
        if normalized == candidate or candidate in normalized:
            return (
                country_payload(
                    entry["country_code"],
                    confidence=entry.get("confidence", "high"),
                    reason="publisher_name_map",
                ),
                candidate,
            )

    if "." in normalized and " " not in normalized:
        return mapped_country_for_domain(normalized)
    return unknown_country(reason="unknown"), "publisher_unmapped"


def publisher_country_fields(item: dict[str, Any]) -> dict[str, str]:
    calculated_region = publisher_region_fields(item)
    publisher_region = clean_text(item.get("publisher_region")) or clean_text(calculated_region.get("publisher_region"))
    publisher_domain = clean_text(item.get("publisher_domain")) or clean_text(calculated_region.get("publisher_domain"))
    publisher_name = clean_text(item.get("publisher_name")) or clean_text(calculated_region.get("publisher_name"))

    if publisher_region == "domestic":
        return country_payload("KR", confidence="high", reason="publisher_region_domestic")

    if publisher_domain and not is_intermediary_domain(publisher_domain):
        country, _ = mapped_country_for_domain(publisher_domain)
        if country["publisher_country_confidence"] != "unknown":
            return country

    if publisher_name:
        country, _ = mapped_country_for_publisher(publisher_name)
        if country["publisher_country_confidence"] != "unknown":
            return country

    original_domain = hostname_from_url(item.get("original_url") or item.get("url"))
    if original_domain and not is_intermediary_domain(original_domain):
        country, _ = mapped_country_for_domain(original_domain)
        if country["publisher_country_confidence"] != "unknown":
            return {
                **country,
                "publisher_country_reason": "url_domain"
                if country["publisher_country_reason"] == "explicit_domain_map"
                else country["publisher_country_reason"],
            }

    return unknown_country(reason="unknown")


def apply_publisher_country_fields(item: dict[str, Any]) -> dict[str, Any]:
    return {**item, **publisher_country_fields(item)}


def apply_publisher_country_fields_to_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [apply_publisher_country_fields(item) for item in items]
