from __future__ import annotations

from src.collectors.public_housing_contests.base import probe_source


def probe_gh(source: dict, *, max_pages: int = 3) -> dict:
    return probe_source(source, max_pages=max_pages)
