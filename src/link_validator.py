from __future__ import annotations

from datetime import datetime
from typing import Any

import requests


ERROR_PAGE_MARKERS = [
    "프로그램에 오류가 발생",
    "요청하신 서비스를 처리할 수 없습니다",
    "담당자에게 문의",
    "잘못된 접근",
    "로그인",
    "login",
    "프로그램에 오류가 발생",
    "요청하신 서비스를 처리할 수 없습니다",
    "담당자에게 문의",
    "error",
    "exception",
    "session",
    "잘못된 접근",
]


def validate_candidate_url(
    url: str,
    title: str | None = None,
    source_record_id: str | None = None,
    timeout: int = 10,
) -> dict[str, Any]:
    checked_at = datetime.now().isoformat(timespec="seconds")
    if not url:
        return {"is_valid": False, "status_code": None, "reason": "empty_url", "checked_at": checked_at}

    headers = {"User-Agent": "modular-info-dashboard/0.1"}
    try:
        response = requests.get(url, headers=headers, allow_redirects=True, timeout=timeout)
    except requests.RequestException as exc:
        return {"is_valid": False, "status_code": None, "reason": str(exc), "checked_at": checked_at}

    status_code = response.status_code
    text = response.text[:20000].lower()
    if not 200 <= status_code < 400:
        return {"is_valid": False, "status_code": status_code, "reason": "http_error", "checked_at": checked_at}
    if any(marker.lower() in text for marker in ERROR_PAGE_MARKERS):
        return {"is_valid": False, "status_code": status_code, "reason": "error_page_marker", "checked_at": checked_at}

    record_id = str(source_record_id or "").strip().lower()
    title_tokens = [token for token in str(title or "").lower().split() if len(token) >= 4]
    has_record = bool(record_id and record_id in text)
    has_title = any(token in text for token in title_tokens[:5])
    if (record_id or title_tokens) and not (has_record or has_title):
        return {"is_valid": False, "status_code": status_code, "reason": "content_mismatch", "checked_at": checked_at}

    return {"is_valid": True, "status_code": status_code, "reason": "ok", "checked_at": checked_at}
