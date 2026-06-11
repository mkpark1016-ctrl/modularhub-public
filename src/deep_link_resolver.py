from __future__ import annotations

from typing import Any

from src.d2b_deep_link import build_d2b_deep_link_candidates
from src.lh_deep_link import build_lh_deep_link_candidates
from src.link_validator import validate_candidate_url


SOURCE_ALIASES = {
    "G2B": "나라장터",
    "나라장터": "나라장터",
    "LH": "LH",
    "D2B": "D2B",
    "NAVER": "네이버뉴스",
    "네이버뉴스": "네이버뉴스",
}


def normalize_source(source: str) -> str:
    return SOURCE_ALIASES.get(source, source)


def resolve_deep_link_for_item(item: dict[str, Any], *, validate: bool = True) -> dict[str, Any]:
    candidates = generate_deep_link_candidates(item)
    result = {
        "candidates": candidates,
        "exact_url_candidate": candidates[0] if candidates else None,
        "original_url": None,
        "link_type": "unknown",
        "link_status": "unverified" if candidates else "unknown",
        "exact_url_verified": 0,
        "exact_url_verified_at": None,
        "exact_url_validation_reason": "no_candidate" if not candidates else "not_checked",
        "source_detail_api_url": item.get("source_detail_api_url"),
    }
    if not candidates or not validate:
        return result

    title = str(item.get("title") or "")
    record_id = str(item.get("source_record_id") or "")
    for candidate in candidates:
        validation = validate_candidate_url(candidate, title=title, source_record_id=record_id)
        result.update(
            {
                "exact_url_candidate": candidate,
                "exact_url_verified_at": validation["checked_at"],
                "exact_url_validation_reason": validation["reason"],
            }
        )
        if validation["is_valid"]:
            is_api_candidate = bool(item.get("source_detail_api_url") and candidate == item.get("source_detail_api_url"))
            result.update(
                {
                    "original_url": None if is_api_candidate else candidate,
                    "link_type": "exact_api" if is_api_candidate else "exact",
                    "link_status": "ok",
                    "exact_url_verified": 1,
                    "source_detail_api_url": candidate if is_api_candidate else item.get("source_detail_api_url"),
                }
            )
            return result

    result.update({"original_url": None, "link_type": "unknown", "link_status": "broken"})
    return result


def generate_deep_link_candidates(item: dict[str, Any]) -> list[str]:
    source_name = str(item.get("source_name") or "")
    candidates = []
    for key in ("exact_url_candidate", "source_detail_api_url"):
        value = item.get(key)
        if value:
            candidates.append(str(value).strip())

    # News exact links are already supplied by Naver originallink. Procurement sources
    # intentionally produce no guessed browser URL until an official detail pattern is proven.
    if source_name == "네이버뉴스" and item.get("original_url"):
        candidates.append(str(item["original_url"]).strip())

    if source_name == "LH":
        candidates.extend(build_lh_deep_link_candidates(item))
    if source_name == "D2B":
        candidates.extend(build_d2b_deep_link_candidates(item))

    seen = set()
    unique = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique
