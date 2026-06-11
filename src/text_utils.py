from __future__ import annotations

import re


def normalize_korean_title(text: str | None) -> str:
    value = str(text or "").lower()
    value = re.sub(r"[\s\(\)\[\]\{\}·ㆍ\-_.,/\\:;\"'“”‘’]+", "", value)
    return value


def contains_modular_keyword(title: str | None, keyword: str = "모듈러") -> bool:
    normalized = normalize_korean_title(title)
    normalized_keyword = normalize_korean_title(keyword)
    if not normalized_keyword:
        return False
    return normalized_keyword in normalized
