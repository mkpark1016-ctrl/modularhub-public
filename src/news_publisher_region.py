from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
PUBLISHER_REGION_CONFIG_PATH = ROOT / "config" / "news_publisher_regions.json"
INTERMEDIARY_DOMAINS = {"news.google.com"}
VALID_REGIONS = {"domestic", "overseas", "unknown"}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def normalize_key(value: Any) -> str:
    return clean_text(value).casefold()


@lru_cache(maxsize=1)
def load_publisher_region_config() -> dict[str, dict[str, str]]:
    try:
        payload = json.loads(PUBLISHER_REGION_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    domains = payload.get("domains", {}) if isinstance(payload, dict) else {}
    publishers = payload.get("publishers", {}) if isinstance(payload, dict) else {}
    return {
        "domains": {normalize_domain(key): value for key, value in domains.items() if value in VALID_REGIONS},
        "publishers": {normalize_key(key): value for key, value in publishers.items() if value in VALID_REGIONS},
    }


def normalize_domain(value: Any) -> str:
    text = clean_text(value).casefold()
    if not text:
        return ""
    if "://" in text:
        try:
            text = urlsplit(text).hostname or ""
        except ValueError:
            text = ""
    return text.removeprefix("www.")


def hostname_from_url(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"}:
        return ""
    return normalize_domain(parsed.hostname or "")


def is_intermediary_domain(domain: str) -> bool:
    normalized = normalize_domain(domain)
    return normalized in INTERMEDIARY_DOMAINS


def collection_pipeline_for_item(item: dict[str, Any]) -> str:
    source = clean_text(item.get("source") or item.get("source_name"))
    return "rss_overseas_pipeline" if "rss" in source.casefold() else "domestic_pipeline"


def collection_source_for_item(item: dict[str, Any]) -> str:
    return clean_text(item.get("source") or item.get("source_name"))


def title_suffix_publisher(item: dict[str, Any]) -> str:
    title = clean_text(item.get("title"))
    if " - " not in title:
        return ""
    suffix = title.rsplit(" - ", 1)[-1].strip()
    return suffix if suffix and len(suffix) <= 80 else ""


def explicit_publisher_name(item: dict[str, Any]) -> str:
    for key in ("media", "organization", "publisher", "source_name"):
        value = clean_text(item.get(key))
        if value:
            return value
    return title_suffix_publisher(item)


def mapped_region_for_domain(domain: str) -> tuple[str, str]:
    normalized = normalize_domain(domain)
    if not normalized:
        return "unknown", "domain_missing"
    config = load_publisher_region_config()
    domains = config["domains"]
    for candidate, region in domains.items():
        if normalized == candidate or normalized.endswith(f".{candidate}"):
            return region, f"domain_mapping:{candidate}"
    if normalized.endswith(".kr") or normalized.endswith(".co.kr"):
        return "domestic", "domain_tld_kr"
    if normalized.endswith((".co.uk", ".ie", ".com.au", ".ca")):
        return "overseas", "domain_tld_overseas"
    return "unknown", "domain_unmapped"


def mapped_region_for_publisher(name: str) -> tuple[str, str]:
    normalized = normalize_key(name)
    if not normalized:
        return "unknown", "publisher_missing"
    config = load_publisher_region_config()
    publishers = config["publishers"]
    for candidate, region in publishers.items():
        if normalized == candidate or candidate in normalized:
            return region, f"publisher_mapping:{candidate}"
    if "." in normalized and " " not in normalized:
        return mapped_region_for_domain(normalized)
    return "unknown", "publisher_unmapped"


def publisher_region_fields(item: dict[str, Any]) -> dict[str, Any]:
    collection_pipeline = collection_pipeline_for_item(item)
    collection_source = collection_source_for_item(item)
    direct_domain = hostname_from_url(item.get("original_url") or item.get("url"))
    publisher_name = explicit_publisher_name(item)
    publisher_domain = "" if is_intermediary_domain(direct_domain) else direct_domain

    if publisher_domain:
        region, reason = mapped_region_for_domain(publisher_domain)
        confidence = "mapped" if reason.startswith("domain_mapping") else ("inferred" if region != "unknown" else "unknown")
        if region != "unknown":
            return {
                "collection_pipeline": collection_pipeline,
                "collection_source": collection_source,
                "publisher_name": publisher_name,
                "publisher_domain": publisher_domain,
                "publisher_region": region,
                "publisher_region_confidence": confidence,
                "publisher_region_reason": reason,
            }

    if publisher_name:
        region, reason = mapped_region_for_publisher(publisher_name)
        if "." in publisher_name and " " not in publisher_name:
            candidate_domain = normalize_domain(publisher_name)
            if not is_intermediary_domain(candidate_domain):
                publisher_domain = candidate_domain
        if region != "unknown":
            return {
                "collection_pipeline": collection_pipeline,
                "collection_source": collection_source,
                "publisher_name": publisher_name,
                "publisher_domain": publisher_domain,
                "publisher_region": region,
                "publisher_region_confidence": "mapped" if "mapping" in reason else "inferred",
                "publisher_region_reason": reason,
            }

    suffix = title_suffix_publisher(item)
    if suffix and suffix != publisher_name:
        region, reason = mapped_region_for_publisher(suffix)
        if region != "unknown":
            return {
                "collection_pipeline": collection_pipeline,
                "collection_source": collection_source,
                "publisher_name": suffix,
                "publisher_domain": publisher_domain,
                "publisher_region": region,
                "publisher_region_confidence": "mapped" if "mapping" in reason else "inferred",
                "publisher_region_reason": f"title_suffix:{reason}",
            }

    return {
        "collection_pipeline": collection_pipeline,
        "collection_source": collection_source,
        "publisher_name": publisher_name or suffix,
        "publisher_domain": publisher_domain,
        "publisher_region": "unknown",
        "publisher_region_confidence": "unknown",
        "publisher_region_reason": "publisher_region_unknown",
    }


def apply_publisher_region_fields(item: dict[str, Any]) -> dict[str, Any]:
    return {**item, **publisher_region_fields(item)}


def apply_publisher_region_fields_to_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [apply_publisher_region_fields(item) for item in items]
