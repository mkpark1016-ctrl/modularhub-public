from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.probe_gdelt_global_news import (  # noqa: E402
    COUNTRIES_PATH,
    DEFAULT_OUTPUT_DIR,
    QUERIES_PATH,
    clean_text,
    config_fingerprint,
    gdelt_sourcecountry,
    generate_run_id,
    load_json,
    utc_now_iso,
)


DEFAULT_REPORT_DIR = ROOT / "artifacts" / "global_news_health"
DEFAULT_STATE_FILE = DEFAULT_REPORT_DIR / "last_attempt.json"
HEALTH_QUERY_MAX_RAW_CHARS = 120
HEALTH_QUERY_MAX_ENCODED_CHARS = 240
HEALTH_URL_MAX_CHARS = 1000
NORMAL_COOLDOWN_SECONDS = 10
RATE_LIMIT_COOLDOWN_SECONDS = 3600
TRANSIENT_ERROR_COOLDOWN_SECONDS = 900
PROVIDER_QUARANTINE_SECONDS = 24 * 60 * 60
PUBLIC_DATA_PATHS = [
    ROOT / "frontend" / "public" / "data" / "business.json",
    ROOT / "frontend" / "public" / "data" / "news.json",
    ROOT / "frontend" / "public" / "data" / "meta.json",
]
CHECKPOINT_PATHS = [DEFAULT_OUTPUT_DIR / "checkpoint.json"]
EXIT_CODES = {
    "healthy": 0,
    "healthy_no_matches": 0,
    "rate_limited": 2,
    "cooldown_active": 2,
    "skipped_provider_quarantined": 2,
    "invalid_query": 3,
    "invalid_response": 3,
    "provider_blocked": 3,
    "provider_unavailable": 4,
    "network_error": 4,
    "timeout": 4,
    "plan": 0,
}
PROVIDER_STATES = {"unknown", "healthy", "degraded", "quarantined", "unavailable"}
RECOMMENDED_NEXT_SOURCE = "gdelt_web_news_ngrams"
INVALID_QUERY_PATTERNS = (
    "query was too short",
    "query was too long",
    "query was too short or too long",
    "invalid query",
    "malformed query",
    "query syntax",
)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot_paths(paths: list[Path]) -> dict[str, str | None]:
    snapshot: dict[str, str | None] = {}
    for path in paths:
        snapshot[str(path)] = file_hash(path) if path.exists() else None
    return snapshot


def db_paths() -> list[Path]:
    data_dir = ROOT / "data"
    if not data_dir.exists():
        return []
    suffixes = {".db", ".sqlite", ".sqlite3"}
    return sorted(path for path in data_dir.rglob("*") if path.is_file() and path.suffix.lower() in suffixes)


def integrity_snapshot() -> dict[str, dict[str, str | None]]:
    return {
        "public_json": snapshot_paths(PUBLIC_DATA_PATHS),
        "db": snapshot_paths(db_paths()),
        "env": snapshot_paths([ROOT / ".env"]),
        "checkpoint": snapshot_paths(CHECKPOINT_PATHS),
    }


def integrity_unchanged(before: dict[str, dict[str, str | None]], after: dict[str, dict[str, str | None]]) -> dict[str, bool]:
    return {
        "public_json_unchanged": before.get("public_json") == after.get("public_json"),
        "db_unchanged": before.get("db") == after.get("db"),
        "env_unchanged": before.get("env") == after.get("env"),
        "checkpoint_unchanged": before.get("checkpoint") == after.get("checkpoint"),
    }


def parse_iso_utc(value: Any) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def retry_after_seconds(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        seconds = int(float(text))
    except ValueError:
        return None
    return max(0, seconds)


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def cooldown_seconds_for_status(status: str, retry_after: int | None, *, rate_limit_cooldown_seconds: int) -> tuple[int, str]:
    if status in {"healthy", "healthy_no_matches"}:
        return NORMAL_COOLDOWN_SECONDS, "local_policy"
    if status == "rate_limited":
        if retry_after is not None and retry_after > rate_limit_cooldown_seconds:
            return retry_after, "retry_after"
        return rate_limit_cooldown_seconds, "local_policy"
    if status in {"timeout", "provider_unavailable", "invalid_response"}:
        return TRANSIENT_ERROR_COOLDOWN_SECONDS, "local_policy"
    return 0, "none"


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def fallback_state_from_health_report(report_dir: Path) -> dict[str, Any] | None:
    payload = load_json_if_exists(report_dir / "health.json")
    if not payload:
        return None
    attempted_at = clean_text(payload.get("checked_at"))
    if not attempted_at:
        return None
    return {
        "attempted_at": attempted_at,
        "country": payload.get("country_code"),
        "query_profile": payload.get("query_profile"),
        "query_fingerprint": payload.get("query_fingerprint"),
        "http_status": payload.get("http_status"),
        "health_status": payload.get("status"),
        "retry_after_seconds": retry_after_seconds(payload.get("retry_after")),
        "request_count": payload.get("request_count", 0),
        "state_source": "health_report",
    }


def load_cooldown_state(report_dir: Path) -> tuple[dict[str, Any] | None, bool]:
    state_file = report_dir / "last_attempt.json"
    payload = load_json_if_exists(state_file)
    if payload:
        payload["state_source"] = "state_file"
        return payload, True
    return fallback_state_from_health_report(report_dir), False


def rate_limit_count_from_state(state: dict[str, Any]) -> int:
    if state.get("consecutive_rate_limit_count") is not None:
        try:
            return max(0, int(state.get("consecutive_rate_limit_count") or 0))
        except (TypeError, ValueError):
            return 0
    if clean_text(state.get("health_status")) == "rate_limited" or safe_int(state.get("http_status")) == 429:
        # Legacy health state did not persist a counter. This project has already
        # observed repeated AU 429 responses; treat legacy 429 health state as the
        # second consecutive limit event so DOC API calls remain safely isolated.
        return 2
    return 0


def provider_state_from_status(status: str, count: int, *, network_error: bool = False) -> str:
    if status in {"healthy", "healthy_no_matches"}:
        return "healthy"
    if status == "rate_limited":
        return "quarantined" if count >= 2 else "degraded"
    if status in {"timeout", "provider_unavailable", "invalid_response"}:
        return "degraded"
    if status == "network_error" and network_error:
        return "unavailable"
    return "unknown"


def quarantine_until_for_state(state: dict[str, Any], count: int) -> str:
    explicit = clean_text(state.get("quarantine_until"))
    if explicit:
        return explicit
    if count < 2:
        return ""
    anchor = parse_iso_utc(state.get("last_rate_limited_at")) or parse_iso_utc(state.get("attempted_at"))
    if not anchor:
        return ""
    return iso_utc(anchor + timedelta(seconds=PROVIDER_QUARANTINE_SECONDS))


def enrich_provider_state(state: dict[str, Any] | None, *, now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not state:
        return {
            "provider_state": "unknown",
            "previous_health_status": "",
            "previous_http_status": None,
            "consecutive_rate_limit_count": 0,
            "first_rate_limited_at": "",
            "last_rate_limited_at": "",
            "quarantine_reason": "",
            "quarantine_until": "",
            "quarantine_active": False,
            "remaining_seconds": 0,
            "doc_api_collection_allowed": False,
            "webngrams_probe_allowed": False,
            "recommended_next_source": "",
        }
    status = clean_text(state.get("health_status"))
    http_status = state.get("http_status")
    count = rate_limit_count_from_state(state)
    first_rate_limited_at = clean_text(state.get("first_rate_limited_at"))
    last_rate_limited_at = clean_text(state.get("last_rate_limited_at"))
    if status == "rate_limited" or safe_int(http_status) == 429:
        attempted = clean_text(state.get("attempted_at"))
        first_rate_limited_at = first_rate_limited_at or attempted
        last_rate_limited_at = last_rate_limited_at or attempted
    provider_state = clean_text(state.get("provider_state")) or provider_state_from_status(status, count)
    if provider_state not in PROVIDER_STATES:
        provider_state = provider_state_from_status(status, count)
    quarantine_reason = clean_text(state.get("quarantine_reason"))
    if provider_state == "quarantined" and not quarantine_reason:
        quarantine_reason = "consecutive_http_429"
    quarantine_until = quarantine_until_for_state({**state, "last_rate_limited_at": last_rate_limited_at}, count)
    quarantine_dt = parse_iso_utc(quarantine_until)
    remaining = max(0, int((quarantine_dt - now).total_seconds())) if quarantine_dt else 0
    quarantine_active = provider_state == "quarantined" and remaining > 0
    doc_allowed = provider_state in {"healthy", "degraded"} and not quarantine_active
    webngrams_allowed = provider_state in {"degraded", "quarantined", "unavailable"}
    recommended = RECOMMENDED_NEXT_SOURCE if webngrams_allowed else ""
    return {
        "provider_state": provider_state,
        "previous_health_status": status,
        "previous_http_status": http_status,
        "consecutive_rate_limit_count": count,
        "first_rate_limited_at": first_rate_limited_at,
        "last_rate_limited_at": last_rate_limited_at,
        "quarantine_reason": quarantine_reason,
        "quarantine_until": quarantine_until,
        "quarantine_active": quarantine_active,
        "remaining_seconds": remaining,
        "doc_api_collection_allowed": doc_allowed,
        "webngrams_probe_allowed": webngrams_allowed,
        "recommended_next_source": recommended,
    }


def cooldown_status(
    *,
    report_dir: Path,
    country_code: str,
    query_profile: str,
    rate_limit_cooldown_seconds: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    state, state_file_exists = load_cooldown_state(report_dir)
    base = {
        "state_file": str((report_dir / "last_attempt.json").relative_to(ROOT)) if (report_dir / "last_attempt.json").is_relative_to(ROOT) else "last_attempt.json",
        "state_file_exists": state_file_exists,
        "cooldown_active": False,
        "last_attempted_at": "",
        "next_eligible_at": "",
        "remaining_seconds": 0,
        "previous_http_status": None,
        "previous_health_status": "",
        "actual_request_count": 0,
        "cooldown_source": "",
        "state_source": "none",
        **enrich_provider_state(None, now=now),
    }
    if not state:
        return base
    if clean_text(state.get("country")).upper() != clean_text(country_code).upper():
        return base
    if clean_text(state.get("query_profile")) and clean_text(state.get("query_profile")) != query_profile:
        return base
    attempted_at = parse_iso_utc(state.get("attempted_at"))
    if not attempted_at:
        return base
    provider_fields = enrich_provider_state(state, now=now)
    status = clean_text(state.get("health_status"))
    retry_after = retry_after_seconds(state.get("retry_after_seconds"))
    cooldown_seconds, source = cooldown_seconds_for_status(
        status,
        retry_after,
        rate_limit_cooldown_seconds=rate_limit_cooldown_seconds,
    )
    next_eligible = parse_iso_utc(state.get("next_eligible_at")) or attempted_at + timedelta(seconds=cooldown_seconds)
    remaining = max(0, int((next_eligible - now).total_seconds()))
    base.update(
        {
            "cooldown_active": remaining > 0,
            "last_attempted_at": iso_utc(attempted_at),
            "next_eligible_at": iso_utc(next_eligible),
            "remaining_seconds": remaining,
            "previous_http_status": state.get("http_status"),
            "previous_health_status": status,
            "actual_request_count": 0,
            "cooldown_source": source,
            "state_source": state.get("state_source", "state_file"),
            **provider_fields,
        }
    )
    return base


def state_fields_for_summary(
    summary: dict[str, Any],
    *,
    previous_state: dict[str, Any] | None,
) -> dict[str, Any]:
    status = clean_text(summary.get("status"))
    attempted = clean_text(summary.get("checked_at"))
    previous_count = rate_limit_count_from_state(previous_state or {})
    previous_first_rate_limited = clean_text((previous_state or {}).get("first_rate_limited_at"))
    if status == "rate_limited":
        count = previous_count + 1
        first_rate_limited_at = previous_first_rate_limited or attempted
        last_rate_limited_at = attempted
    elif status in {"healthy", "healthy_no_matches"}:
        count = 0
        first_rate_limited_at = ""
        last_rate_limited_at = ""
    else:
        count = previous_count
        first_rate_limited_at = previous_first_rate_limited
        last_rate_limited_at = clean_text((previous_state or {}).get("last_rate_limited_at"))

    provider_state = provider_state_from_status(status, count, network_error=status == "network_error")
    quarantine_reason = "consecutive_http_429" if provider_state == "quarantined" else ""
    quarantine_until = ""
    if provider_state == "quarantined":
        anchor = parse_iso_utc(last_rate_limited_at) or parse_iso_utc(attempted)
        if anchor:
            quarantine_until = iso_utc(anchor + timedelta(seconds=PROVIDER_QUARANTINE_SECONDS))
    doc_allowed = provider_state in {"healthy", "degraded"}
    webngrams_allowed = provider_state in {"degraded", "quarantined", "unavailable"}
    return {
        "consecutive_rate_limit_count": count,
        "first_rate_limited_at": first_rate_limited_at,
        "last_rate_limited_at": last_rate_limited_at,
        "provider_state": provider_state,
        "quarantine_reason": quarantine_reason,
        "quarantine_until": quarantine_until,
        "recommended_next_source": RECOMMENDED_NEXT_SOURCE if webngrams_allowed else "",
        "doc_api_collection_allowed": doc_allowed and provider_state != "quarantined",
        "webngrams_probe_allowed": webngrams_allowed,
    }


def write_cooldown_state(
    report_dir: Path,
    summary: dict[str, Any],
    *,
    rate_limit_cooldown_seconds: int,
    previous_state: dict[str, Any] | None = None,
) -> None:
    attempted = parse_iso_utc(summary.get("checked_at")) or datetime.now(timezone.utc)
    retry_after = retry_after_seconds(summary.get("retry_after"))
    cooldown_seconds, source = cooldown_seconds_for_status(
        clean_text(summary.get("status")),
        retry_after,
        rate_limit_cooldown_seconds=rate_limit_cooldown_seconds,
    )
    state = {
        "attempted_at": iso_utc(attempted),
        "country": summary.get("country_code"),
        "query_profile": summary.get("query_profile"),
        "query_fingerprint": summary.get("query_fingerprint"),
        "http_status": summary.get("http_status"),
        "health_status": summary.get("status"),
        "retry_after_seconds": retry_after,
        "local_cooldown_seconds": cooldown_seconds,
        "next_eligible_at": iso_utc(attempted + timedelta(seconds=cooldown_seconds)),
        "request_count": summary.get("request_count", 0),
        "cooldown_source": source,
    }
    state.update(state_fields_for_summary(summary, previous_state=previous_state))
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "last_attempt.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def find_country(country_config: dict[str, Any], code: str) -> dict[str, Any]:
    requested = clean_text(code).upper()
    for country in country_config.get("countries", []):
        if clean_text(country.get("code")).upper() == requested:
            return country
    raise ValueError(f"unknown country code: {code}")


def redact_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return ""
    sensitive = {"key", "token", "secret", "authorization", "cookie", "apikey", "api_key"}
    query = [
        (key, "REDACTED" if key.lower() in sensitive else val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def mask_sensitive(value: str) -> str:
    text = value[:500]
    patterns = [
        r"(?i)(authorization\s*[:=]\s*)[^\s<>&]+",
        r"(?i)(cookie\s*[:=]\s*)[^\s<>&]+",
        r"(?i)(token\s*[:=]\s*)[^\s<>&]+",
        r"(?i)(api[_-]?key\s*[:=]\s*)[^\s<>&]+",
        r"(?i)(secret\s*[:=]\s*)[^\s<>&]+",
    ]
    for pattern in patterns:
        text = re.sub(pattern, r"\1REDACTED", text)
    return text[:500]


def quote_phrase(value: str) -> str:
    return '"' + value.replace('"', r"\"") + '"'


def build_health_query(country: dict[str, Any], *, health_term: str = "modular", health_phrase: str = "") -> str:
    if clean_text(health_term) and clean_text(health_phrase):
        raise ValueError("--health-term and --health-phrase are mutually exclusive")
    sourcecountry = gdelt_sourcecountry(country)
    if clean_text(health_phrase):
        search = quote_phrase(clean_text(health_phrase))
    else:
        search = clean_text(health_term)
    return f"{search} sourcecountry:{sourcecountry}"


def max_parenthesis_depth(query: str) -> int:
    depth = 0
    max_depth = 0
    for char in query:
        if char == "(":
            depth += 1
            max_depth = max(max_depth, depth)
        elif char == ")":
            depth = max(0, depth - 1)
    return max_depth


def health_query_fingerprint(country: dict[str, Any], raw_query: str) -> str:
    payload = {
        "query_profile": "health",
        "country_code": clean_text(country.get("code")).upper(),
        "gdelt_sourcecountry": gdelt_sourcecountry(country),
        "raw_query": raw_query,
        "mode": "artlist",
        "format": "json",
        "sort": "datedesc",
        "maxrecords": "1",
        "timespan": "24h",
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def build_health_params(raw_query: str) -> dict[str, str]:
    return {
        "query": raw_query,
        "mode": "artlist",
        "format": "json",
        "sort": "datedesc",
        "maxrecords": "1",
        "timespan": "24h",
    }


def build_health_url(endpoint: str, raw_query: str) -> str:
    return f"{endpoint}?{urlencode(build_health_params(raw_query))}"


def describe_query_budget(raw_query: str, request_url: str) -> dict[str, Any]:
    encoded_query = urlencode({"query": raw_query}).split("=", 1)[1]
    return {
        "raw_query_length": len(raw_query),
        "encoded_query_length": len(encoded_query),
        "full_url_length": len(request_url),
        "search_term_count": 1 if raw_query.split(" sourcecountry:", 1)[0].strip() else 0,
        "sourcecountry_count": len(re.findall(r"\bsourcecountry:", raw_query, flags=re.IGNORECASE)),
        "boolean_or_count": len(re.findall(r"\bOR\b", raw_query)),
        "parenthesis_depth": max_parenthesis_depth(raw_query),
    }


def validate_health_query(raw_query: str, request_url: str, *, production_query: str = "") -> tuple[bool, str]:
    profile = describe_query_budget(raw_query, request_url)
    if not clean_text(raw_query):
        return False, "empty_health_query"
    if profile["sourcecountry_count"] != 1:
        return False, "sourcecountry_count_not_one"
    if profile["boolean_or_count"] > 1:
        return False, "too_many_boolean_or_terms"
    if profile["parenthesis_depth"] > 1:
        return False, "nested_parentheses_not_allowed"
    if production_query and clean_text(production_query).lower() == clean_text(raw_query).lower():
        return False, "health_query_matches_production_query"
    if profile["raw_query_length"] > HEALTH_QUERY_MAX_RAW_CHARS:
        return False, "raw_query_too_long_for_internal_budget"
    if profile["encoded_query_length"] > HEALTH_QUERY_MAX_ENCODED_CHARS:
        return False, "encoded_query_too_long_for_internal_budget"
    if profile["full_url_length"] > HEALTH_URL_MAX_CHARS:
        return False, "url_too_long_for_internal_budget"
    return True, ""


def is_invalid_query_message(body_preview: str) -> bool:
    lowered = body_preview.lower()
    return any(pattern in lowered for pattern in INVALID_QUERY_PATTERNS)


def health_plan(
    country_code: str = "AU",
    *,
    timeout: float = 20.0,
    health_term: str = "modular",
    health_phrase: str = "",
    report_dir: Path = DEFAULT_REPORT_DIR,
    cooldown_seconds: int = RATE_LIMIT_COOLDOWN_SECONDS,
) -> dict[str, Any]:
    country_config = load_json(COUNTRIES_PATH)
    query_config = load_json(QUERIES_PATH)
    country = find_country(country_config, country_code)
    fingerprint = config_fingerprint(country_config, query_config)
    run_id = generate_run_id(fingerprint)
    sourcecountry = gdelt_sourcecountry(country)
    raw_query = build_health_query(country, health_term=health_term, health_phrase=health_phrase)
    request_url = build_health_url(str(country_config["endpoint"]), raw_query)
    production_query = ""  # Health checks intentionally do not compose the production Query Pack.
    query_preflight_passed, query_preflight_reason = validate_health_query(raw_query, request_url, production_query=production_query)
    budget = describe_query_budget(raw_query, request_url)
    query_fingerprint = health_query_fingerprint(country, raw_query)
    cooldown = cooldown_status(
        report_dir=report_dir,
        country_code=clean_text(country.get("code")).upper(),
        query_profile="health",
        rate_limit_cooldown_seconds=cooldown_seconds,
    )
    return {
        "checked_at": utc_now_iso(),
        "run_id": run_id,
        "config_fingerprint": fingerprint,
        "country_code": clean_text(country.get("code")).upper(),
        "sourcecountry": sourcecountry,
        "query_fingerprint": query_fingerprint,
        "query_profile": "health",
        "health_term": clean_text(health_phrase) if clean_text(health_phrase) else clean_text(health_term),
        "query": raw_query,
        "raw_query_redacted": raw_query,
        **budget,
        "production_query_pack_used": False,
        "query_preflight_passed": query_preflight_passed,
        "query_preflight_reason": query_preflight_reason,
        "request_url_redacted": redact_url(request_url),
        "timeout_seconds": timeout,
        "state_file": cooldown["state_file"],
        "state_file_exists": cooldown["state_file_exists"],
        "cooldown_active": cooldown["cooldown_active"],
        "last_attempted_at": cooldown["last_attempted_at"],
        "next_eligible_at": cooldown["next_eligible_at"],
        "remaining_cooldown_seconds": cooldown["remaining_seconds"],
        "last_http_status": cooldown["previous_http_status"],
        "last_health_status": cooldown["previous_health_status"],
        "cooldown_source": cooldown.get("cooldown_source", ""),
        "provider_state": cooldown["provider_state"],
        "consecutive_rate_limit_count": cooldown["consecutive_rate_limit_count"],
        "quarantine_active": cooldown["quarantine_active"],
        "quarantine_until": cooldown["quarantine_until"],
        "quarantine_reason": cooldown["quarantine_reason"],
        "doc_api_collection_allowed": cooldown["doc_api_collection_allowed"],
        "webngrams_probe_allowed": cooldown["webngrams_probe_allowed"],
        "recommended_next_source": cooldown["recommended_next_source"],
        "10.10-A.4_ready": cooldown["provider_state"] == "healthy",
        "10.10-B1_ready": cooldown["provider_state"] == "quarantined"
        and cooldown["doc_api_collection_allowed"] is False
        and cooldown["webngrams_probe_allowed"] is True
        and cooldown["recommended_next_source"] == RECOMMENDED_NEXT_SOURCE,
        "request_count": 0,
        "retry_count": 0,
        "expected_request_count": 1,
        "file_created_count": 0,
        "status": "plan",
        "failure_reason": "",
        "http_status": None,
        "content_type": "",
        "json_parse_success": False,
        "schema_valid": False,
        "article_count": 0,
        "retry_after": "",
        "redirect_count": 0,
        "final_host": "",
        "elapsed_seconds": 0.0,
        "response_body_preview": "",
        "provider_reached": False,
        "response_error_category": "",
        "public_json_unchanged": True,
        "db_unchanged": True,
        "env_unchanged": True,
        "checkpoint_unchanged": True,
    }


def classify_success(payload: Any) -> tuple[str, str, bool, int]:
    if not isinstance(payload, dict):
        return "invalid_response", "top_level_not_object", False, 0
    articles = payload.get("articles")
    if not isinstance(articles, list):
        return "invalid_response", "articles_not_array", False, 0
    if articles:
        return "healthy", "", True, len(articles)
    return "healthy_no_matches", "", True, 0


def run_live_health(
    *,
    country_code: str = "AU",
    timeout: float = 20.0,
    health_term: str = "modular",
    health_phrase: str = "",
    cooldown_seconds: int = RATE_LIMIT_COOLDOWN_SECONDS,
    report_dir: Path = DEFAULT_REPORT_DIR,
    get_func: Callable[..., Any] = requests.get,
) -> dict[str, Any]:
    before = integrity_snapshot()
    summary = health_plan(
        country_code,
        timeout=timeout,
        health_term=health_term,
        health_phrase=health_phrase,
        report_dir=report_dir,
        cooldown_seconds=cooldown_seconds,
    )
    previous_state, _ = load_cooldown_state(report_dir)
    request_url = summary["request_url_redacted"]
    if not summary["query_preflight_passed"]:
        after = integrity_snapshot()
        integrity = integrity_unchanged(before, after)
        summary.update(
            {
                "request_count": 0,
                "retry_count": 0,
                "status": "invalid_query",
                "failure_reason": summary["query_preflight_reason"],
                "response_error_category": "query_preflight_failed",
                **integrity,
            }
        )
        write_reports(report_dir, summary)
        return summary
    if summary["provider_state"] == "quarantined" and summary["quarantine_active"]:
        after = integrity_snapshot()
        integrity = integrity_unchanged(before, after)
        summary.update(
            {
                "request_count": 0,
                "retry_count": 0,
                "actual_request_count": 0,
                "status": "skipped_provider_quarantined",
                "failure_reason": "provider_quarantine_active",
                "response_error_category": "provider_quarantine",
                "file_created_count": 2,
                **integrity,
            }
        )
        write_reports(report_dir, summary)
        return summary
    if summary["cooldown_active"]:
        after = integrity_snapshot()
        integrity = integrity_unchanged(before, after)
        summary.update(
            {
                "request_count": 0,
                "retry_count": 0,
                "actual_request_count": 0,
                "status": "cooldown_active",
                "failure_reason": "local_cooldown_active",
                "response_error_category": "cooldown_active",
                "file_created_count": 2,
                **integrity,
            }
        )
        write_reports(report_dir, summary)
        return summary
    started = time.monotonic()
    response = None
    payload: Any = None
    json_parse_success = False
    schema_valid = False
    status = "network_error"
    failure_reason = ""
    body_preview = ""
    request_count = 0
    try:
        request_count = 1
        response = get_func(
            request_url,
            headers={"User-Agent": "ModularHubGDELTHealth/0.1", "Accept": "application/json"},
            timeout=timeout,
            allow_redirects=True,
        )
        body_text = getattr(response, "text", "") or ""
        body_preview = mask_sensitive(body_text)
        http_status = int(getattr(response, "status_code", 0) or 0)
        if http_status == 429:
            status = "rate_limited"
            failure_reason = "http_429"
        elif http_status in {500, 502, 503, 504}:
            status = "provider_unavailable"
            failure_reason = f"http_{http_status}"
        elif http_status in {401, 403}:
            status = "provider_blocked"
            failure_reason = f"http_{http_status}"
        elif http_status == 200:
            try:
                payload = response.json()
                json_parse_success = True
            except (ValueError, json.JSONDecodeError):
                if is_invalid_query_message(body_preview):
                    status = "invalid_query"
                    failure_reason = "provider_query_error"
                else:
                    status = "invalid_response"
                    failure_reason = "json_parse_failed"
            else:
                status, failure_reason, schema_valid, article_count = classify_success(payload)
                summary["article_count"] = article_count
        else:
            if is_invalid_query_message(body_preview):
                status = "invalid_query"
                failure_reason = "provider_query_error"
            else:
                status = "invalid_response"
                failure_reason = f"unexpected_http_{http_status}"
    except requests.Timeout:
        status = "timeout"
        failure_reason = "timeout"
    except requests.RequestException as exc:
        status = "network_error"
        failure_reason = type(exc).__name__
    elapsed = round(time.monotonic() - started, 3)
    after = integrity_snapshot()
    integrity = integrity_unchanged(before, after)
    if response is not None:
        final_url = redact_url(str(getattr(response, "url", request_url) or request_url))
        try:
            final_host = urlsplit(final_url).netloc
        except ValueError:
            final_host = ""
        headers = getattr(response, "headers", {}) or {}
        summary.update(
            {
                "http_status": int(getattr(response, "status_code", 0) or 0),
                "content_type": str(headers.get("Content-Type") or headers.get("content-type") or ""),
                "retry_after": str(headers.get("Retry-After") or headers.get("retry-after") or ""),
                "redirect_count": len(getattr(response, "history", []) or []),
                "final_host": final_host,
                "request_url_redacted": final_url,
                "provider_reached": True,
            }
        )
    response_error_category = ""
    if status == "invalid_query":
        response_error_category = "invalid_query"
    elif status == "invalid_response":
        response_error_category = "invalid_response"
    elif status in {"rate_limited", "provider_blocked", "provider_unavailable", "network_error", "timeout"}:
        response_error_category = status
    summary.update(
        {
            "request_count": request_count,
            "retry_count": 0,
            "actual_request_count": request_count,
            "status": status,
            "failure_reason": failure_reason,
            "json_parse_success": json_parse_success,
            "schema_valid": schema_valid,
            "elapsed_seconds": elapsed,
            "response_body_preview": body_preview,
            "response_error_category": response_error_category,
            "file_created_count": 3,
            **integrity,
        }
    )
    summary.update(state_fields_for_summary(summary, previous_state=previous_state))
    write_cooldown_state(report_dir, summary, rate_limit_cooldown_seconds=cooldown_seconds, previous_state=previous_state)
    write_reports(report_dir, summary)
    return summary


def write_reports(report_dir: Path, summary: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "health.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# GDELT Provider Health",
        "",
        f"- status: `{summary['status']}`",
        f"- country: `{summary['country_code']}` / `{summary['sourcecountry']}`",
        f"- http_status: `{summary['http_status']}`",
        f"- content_type: `{summary['content_type']}`",
        f"- request_count: `{summary['request_count']}`",
        f"- retry_count: `{summary['retry_count']}`",
        f"- article_count: `{summary['article_count']}`",
        f"- query_profile: `{summary['query_profile']}`",
        f"- raw_query_length: `{summary['raw_query_length']}`",
        f"- encoded_query_length: `{summary['encoded_query_length']}`",
        f"- full_url_length: `{summary['full_url_length']}`",
        f"- query_preflight_passed: `{summary['query_preflight_passed']}`",
        f"- production_query_pack_used: `{summary['production_query_pack_used']}`",
        f"- query_fingerprint: `{summary['query_fingerprint']}`",
        f"- provider_state: `{summary.get('provider_state', '')}`",
        f"- consecutive_rate_limit_count: `{summary.get('consecutive_rate_limit_count', 0)}`",
        f"- quarantine_active: `{summary.get('quarantine_active', False)}`",
        f"- quarantine_until: `{summary.get('quarantine_until', '')}`",
        f"- recommended_next_source: `{summary.get('recommended_next_source', '')}`",
        f"- next_step_allowed: `{summary['status'] in {'healthy', 'healthy_no_matches'}}`",
        f"- response_error_category: `{summary['response_error_category']}`",
        f"- failure_reason: `{summary['failure_reason']}`",
    ]
    (report_dir / "health.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def show_cooldown(country_code: str, *, report_dir: Path, cooldown_seconds: int) -> dict[str, Any]:
    country_config = load_json(COUNTRIES_PATH)
    country = find_country(country_config, country_code)
    status = cooldown_status(
        report_dir=report_dir,
        country_code=clean_text(country.get("code")).upper(),
        query_profile="health",
        rate_limit_cooldown_seconds=cooldown_seconds,
    )
    return {
        "country_code": clean_text(country.get("code")).upper(),
        "sourcecountry": gdelt_sourcecountry(country),
        "state_file": status["state_file"],
        "state_file_exists": status["state_file_exists"],
        "cooldown_active": status["cooldown_active"],
        "last_attempted_at": status["last_attempted_at"],
        "next_eligible_at": status["next_eligible_at"],
        "remaining_seconds": status["remaining_seconds"],
        "previous_http_status": status["previous_http_status"],
        "previous_health_status": status["previous_health_status"],
        "provider_state": status["provider_state"],
        "consecutive_rate_limit_count": status["consecutive_rate_limit_count"],
        "quarantine_active": status["quarantine_active"],
        "quarantine_until": status["quarantine_until"],
        "quarantine_reason": status["quarantine_reason"],
        "doc_api_collection_allowed": status["doc_api_collection_allowed"],
        "webngrams_probe_allowed": status["webngrams_probe_allowed"],
        "recommended_next_source": status["recommended_next_source"],
        "actual_request_count": 0,
        "cooldown_source": status.get("cooldown_source", ""),
    }


def provider_decision(country_code: str, *, report_dir: Path, cooldown_seconds: int) -> dict[str, Any]:
    country_config = load_json(COUNTRIES_PATH)
    country = find_country(country_config, country_code)
    status = cooldown_status(
        report_dir=report_dir,
        country_code=clean_text(country.get("code")).upper(),
        query_profile="health",
        rate_limit_cooldown_seconds=cooldown_seconds,
    )
    b1_ready = (
        status["provider_state"] == "quarantined"
        and status["doc_api_collection_allowed"] is False
        and status["webngrams_probe_allowed"] is True
        and status["recommended_next_source"] == RECOMMENDED_NEXT_SOURCE
    )
    return {
        "country_code": clean_text(country.get("code")).upper(),
        "sourcecountry": gdelt_sourcecountry(country),
        "provider_state": status["provider_state"],
        "previous_health_status": status["previous_health_status"],
        "previous_http_status": status["previous_http_status"],
        "consecutive_rate_limit_count": status["consecutive_rate_limit_count"],
        "quarantine_active": status["quarantine_active"],
        "quarantine_until": status["quarantine_until"],
        "remaining_seconds": status["remaining_seconds"],
        "quarantine_reason": status["quarantine_reason"],
        "doc_api_collection_allowed": status["doc_api_collection_allowed"],
        "webngrams_probe_allowed": status["webngrams_probe_allowed"],
        "recommended_next_source": status["recommended_next_source"],
        "10.10-A.4_ready": status["provider_state"] == "healthy",
        "10.10-B1_ready": b1_ready,
        "state_file": status["state_file"],
        "state_file_exists": status["state_file_exists"],
        "actual_request_count": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a single-request GDELT provider health gate.")
    parser.add_argument("--country", default="AU")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--health-term", default="")
    parser.add_argument("--health-phrase", default="")
    parser.add_argument("--print-plan", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cooldown-seconds", type=int, default=RATE_LIMIT_COOLDOWN_SECONDS)
    parser.add_argument("--show-cooldown", action="store_true")
    parser.add_argument("--provider-decision", action="store_true")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args()
    if clean_text(args.health_term) and clean_text(args.health_phrase):
        parser.error("--health-term and --health-phrase cannot be used together")
    health_term = clean_text(args.health_term) or ("" if clean_text(args.health_phrase) else "modular")

    if args.show_cooldown:
        cooldown = show_cooldown(args.country, report_dir=args.report_dir, cooldown_seconds=args.cooldown_seconds)
        print(json.dumps(cooldown, ensure_ascii=False, indent=2))
        return 0

    if args.provider_decision:
        decision = provider_decision(args.country, report_dir=args.report_dir, cooldown_seconds=args.cooldown_seconds)
        print(json.dumps(decision, ensure_ascii=False, indent=2))
        return 0

    if args.print_plan or not args.live:
        plan = health_plan(
            args.country,
            timeout=args.timeout,
            health_term=health_term,
            health_phrase=args.health_phrase,
            report_dir=args.report_dir,
            cooldown_seconds=args.cooldown_seconds,
        )
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    summary = run_live_health(
        country_code=args.country,
        timeout=args.timeout,
        health_term=health_term,
        health_phrase=args.health_phrase,
        cooldown_seconds=args.cooldown_seconds,
        report_dir=args.report_dir,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return EXIT_CODES.get(summary["status"], 4)


if __name__ == "__main__":
    raise SystemExit(main())
