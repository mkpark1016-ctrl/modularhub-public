from __future__ import annotations

import argparse
import csv
import email.utils
import hashlib
import json
import random
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests


ROOT = Path(__file__).resolve().parents[1]
COUNTRIES_PATH = ROOT / "config" / "global_news_countries.json"
QUERIES_PATH = ROOT / "config" / "global_news_queries.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "global_news_probe"
USER_AGENT = "ModularHubGDELTProbe/0.2 (+https://github.com/mkpark1016-ctrl/modularhub-public)"
PROBE_VERSION = "0.3"
CHECKPOINT_SCHEMA_VERSION = 2
PROBE_SCHEMA_VERSION = "gdelt-global-news-probe-checkpoint-v2"
QUERY_GENERATOR_VERSION = "query-generator-r2"
TERMINAL_SUCCESS = {"success", "success_no_matches"}
ERROR_STATUSES = {
    "provider_rate_limited",
    "provider_timeout",
    "provider_error",
    "invalid_response_schema",
    "pending_rate_limit",
}
TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "ref",
    "ref_src",
    "cmpid",
}
CSV_REVIEW_FIELDS = [
    "review_id",
    "country_code",
    "sourcecountry",
    "title",
    "domain",
    "language",
    "seendate",
    "url",
    "canonical_url",
    "matched_query_groups",
    "matched_keywords",
    "suspected_noise",
    "reviewer_decision",
    "reviewer_note",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def quote_term(term: str) -> str:
    escaped = term.replace('"', r"\"")
    return f'"{escaped}"' if " " in escaped else escaped


def active_query_terms(query_config: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for pack in query_config["query_packs"]:
        for term in pack.get("queries", []):
            cleaned = clean_text(term)
            if cleaned and cleaned.lower() not in {value.lower() for value in terms}:
                terms.append(cleaned)
    return terms


def build_integrated_query(query_config: dict[str, Any], sourcecountry: str) -> str:
    grouped = " OR ".join(quote_term(term) for term in active_query_terms(query_config))
    return f"({grouped}) sourcecountry:{sourcecountry}"


def validate_country_config(country: dict[str, Any]) -> None:
    missing = [field for field in ("code", "name", "gdelt_sourcecountry", "enabled") if field not in country]
    if missing:
        raise ValueError(f"country config missing required field(s): {', '.join(missing)}")
    if not clean_text(country.get("gdelt_sourcecountry")):
        raise ValueError(f"country {country.get('code') or '<unknown>'} has empty gdelt_sourcecountry")


def gdelt_sourcecountry(country: dict[str, Any]) -> str:
    validate_country_config(country)
    return clean_text(country["gdelt_sourcecountry"])


def build_country_query(country: dict[str, Any], query_config: dict[str, Any]) -> str:
    return build_integrated_query(query_config, gdelt_sourcecountry(country))


def build_gdelt_params(country: dict[str, Any], query_config: dict[str, Any], *, timespan: str, maxrecords: int) -> dict[str, str]:
    return {
        "query": build_country_query(country, query_config),
        "mode": "artlist",
        "format": "json",
        "sort": "datedesc",
        "maxrecords": str(maxrecords),
        "timespan": timespan,
    }


def build_gdelt_url(endpoint: str, country: dict[str, Any], query_config: dict[str, Any], *, timespan: str, maxrecords: int) -> str:
    return f"{endpoint}?{urlencode(build_gdelt_params(country, query_config, timespan=timespan, maxrecords=maxrecords))}"


def normalize_country_config_for_fingerprint(country_config: dict[str, Any]) -> dict[str, Any]:
    normalized = {key: value for key, value in country_config.items() if key != "countries"}
    normalized["countries"] = sorted(
        [dict(country) for country in country_config.get("countries", [])],
        key=lambda country: clean_text(country.get("code")).upper(),
    )
    return normalized


def normalize_query_config_for_fingerprint(query_config: dict[str, Any]) -> dict[str, Any]:
    normalized = {key: value for key, value in query_config.items() if key != "query_packs"}
    normalized["query_packs"] = sorted(
        [dict(pack) for pack in query_config.get("query_packs", [])],
        key=lambda pack: clean_text(pack.get("id")),
    )
    return normalized


def config_fingerprint_payload(country_config: dict[str, Any], query_config: dict[str, Any]) -> dict[str, Any]:
    return {
        "probe_schema_version": PROBE_SCHEMA_VERSION,
        "query_generator_version": QUERY_GENERATOR_VERSION,
        "countries": normalize_country_config_for_fingerprint(country_config),
        "queries": normalize_query_config_for_fingerprint(query_config),
    }


def config_fingerprint(country_config: dict[str, Any], query_config: dict[str, Any]) -> str:
    return sha256_json(config_fingerprint_payload(country_config, query_config))


def short_fingerprint(value: str) -> str:
    return value[:12]


def active_query_pack_manifest(query_config: dict[str, Any]) -> list[dict[str, Any]]:
    packs: list[dict[str, Any]] = []
    for pack in query_config.get("query_packs", []):
        queries = [clean_text(term) for term in pack.get("queries", []) if clean_text(term)]
        if queries:
            packs.append({"id": clean_text(pack.get("id")), "queries": queries})
    return packs


def query_fingerprint_payload(country: dict[str, Any], query_config: dict[str, Any], *, timespan: str, maxrecords: int) -> dict[str, Any]:
    params = build_gdelt_params(country, query_config, timespan=timespan, maxrecords=maxrecords)
    return {
        "country_code": clean_text(country.get("code")).upper(),
        "gdelt_sourcecountry": gdelt_sourcecountry(country),
        "active_query_packs": active_query_pack_manifest(query_config),
        "query": params["query"],
        "timespan": params["timespan"],
        "maxrecords": params["maxrecords"],
        "mode": params["mode"],
        "format": params["format"],
        "sort": params["sort"],
    }


def country_query_fingerprint(country: dict[str, Any], query_config: dict[str, Any], *, timespan: str, maxrecords: int) -> str:
    return sha256_json(query_fingerprint_payload(country, query_config, timespan=timespan, maxrecords=maxrecords))


def generate_run_id(config_fingerprint_value: str, *, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{short_fingerprint(config_fingerprint_value)}"


def build_query_manifest(
    country_config: dict[str, Any],
    query_config: dict[str, Any],
    *,
    generated_at: str | None = None,
    run_id: str | None = None,
    timespan: str | None = None,
    maxrecords: int | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or utc_now_iso()
    fingerprint = config_fingerprint(country_config, query_config)
    run_id = run_id or generate_run_id(fingerprint)
    timespan = timespan or str((country_config.get("timespans") or ["7d"])[0])
    maxrecords = int(maxrecords if maxrecords is not None else country_config.get("maxrecords") or 50)
    endpoint = str(country_config["endpoint"])
    countries: list[dict[str, Any]] = []
    for country in sorted(country_config.get("countries", []), key=lambda item: clean_text(item.get("code")).upper()):
        if not country.get("enabled", True):
            continue
        validate_country_config(country)
        query_fp = country_query_fingerprint(country, query_config, timespan=timespan, maxrecords=maxrecords)
        countries.append(
            {
                "code": clean_text(country.get("code")).upper(),
                "name": clean_text(country.get("name")),
                "gdelt_sourcecountry": gdelt_sourcecountry(country),
                "query": build_country_query(country, query_config),
                "url": build_gdelt_url(endpoint, country, query_config, timespan=timespan, maxrecords=maxrecords),
                "timespan": timespan,
                "maxrecords": str(maxrecords),
                "mode": "artlist",
                "format": "json",
                "sort": "datedesc",
                "query_fingerprint": query_fp,
                "query_fingerprint_short": short_fingerprint(query_fp),
            }
        )
    return {
        "run_id": run_id,
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "probe_version": PROBE_VERSION,
        "query_generator_version": QUERY_GENERATOR_VERSION,
        "config_fingerprint": fingerprint,
        "config_fingerprint_short": short_fingerprint(fingerprint),
        "generated_at": generated_at,
        "countries": countries,
        "query_packs": active_query_pack_manifest(query_config),
    }


def canonical_url(value: str) -> str:
    text = clean_text(value)
    if not text:
        return ""
    try:
        parts = urlsplit(text)
    except ValueError:
        return ""
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    query = [
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS and not key.lower().startswith(TRACKING_QUERY_PREFIXES)
    ]
    netloc = parts.netloc.lower()
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    return urlunsplit((parts.scheme.lower(), netloc, path, urlencode(query), ""))


def publisher_domain(article: dict[str, Any], url: str) -> str:
    domain = clean_text(article.get("domain") or article.get("source") or "")
    if domain:
        return domain.lower().removeprefix("www.")
    try:
        return urlsplit(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


def normalized_text(value: str) -> str:
    text = clean_text(value).lower()
    return re.sub(r"\s+", " ", re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)).strip()


def term_matches_title(title: str, term: str) -> bool:
    title_norm = normalized_text(title)
    term_norm = normalized_text(term)
    return bool(term_norm and term_norm in title_norm)


def local_query_tags(title: str, query_config: dict[str, Any]) -> tuple[list[str], list[str]]:
    matched_groups: list[str] = []
    matched_keywords: list[str] = []
    for pack in query_config["query_packs"]:
        group_matched = False
        for term in pack.get("queries", []):
            if term_matches_title(title, term):
                group_matched = True
                if term not in matched_keywords:
                    matched_keywords.append(term)
        if group_matched:
            matched_groups.append(pack["id"])
    return matched_groups, matched_keywords


def parse_gdelt_datetime(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    for fmt in ("%Y%m%d%H%M%S", "%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        except ValueError:
            pass
    return text


def detect_noise_terms(article: dict[str, Any], noise_terms: list[str]) -> list[str]:
    haystack = clean_text(article.get("title")).lower()
    return [term for term in noise_terms if term.lower() in haystack]


def article_image_url(article: dict[str, Any]) -> str:
    for key in ("socialimage", "image", "imageurl", "image_url"):
        value = clean_text(article.get(key))
        if value.startswith(("http://", "https://")):
            return value
    return ""


def country_filter_matches(country: dict[str, Any], reported: str) -> bool:
    if not reported:
        return False
    norm_reported = re.sub(r"[^a-z0-9]", "", reported.lower())
    acceptable = {
        re.sub(r"[^a-z0-9]", "", str(country.get("code", "")).lower()),
        re.sub(r"[^a-z0-9]", "", str(country.get("name_en", "")).lower()),
        re.sub(r"[^a-z0-9]", "", str(country.get("name_ko", "")).lower()),
    }
    acceptable.update(
        re.sub(r"[^a-z0-9]", "", str(value).lower())
        for value in country.get("gdelt_sourcecountry_candidates", [])
    )
    aliases = {
        "GB": {"unitedkingdom", "greatbritain", "uk", "gb"},
        "US": {"unitedstates", "unitedstatesofamerica", "usa", "us"},
    }
    acceptable.update(aliases.get(str(country.get("code")), set()))
    return norm_reported in acceptable


def normalize_article(
    article: dict[str, Any],
    *,
    country: dict[str, Any],
    query_config: dict[str, Any],
    sourcecountry_filter: str,
    timespan: str,
) -> dict[str, Any]:
    url = clean_text(article.get("url") or article.get("url_mobile") or article.get("link"))
    normalized = canonical_url(url)
    domain = publisher_domain(article, normalized or url)
    title = clean_text(article.get("title"))
    matched_groups, matched_keywords = local_query_tags(title, query_config)
    source_country = clean_text(article.get("sourcecountry") or article.get("sourceCountry"))
    language = clean_text(article.get("language") or article.get("sourcelanguage") or article.get("sourceLanguage"))
    image_url = article_image_url(article)
    noise_matches = detect_noise_terms(article, list(query_config.get("noise_terms") or []))
    seendate = clean_text(article.get("seendate") or article.get("date") or article.get("datetime"))
    return {
        "news_scope": "global",
        "news_provider": "GDELT DOC 2.0",
        "source_country_code": country["code"],
        "source_country_name": country["name_en"],
        "source_country_filter": sourcecountry_filter,
        "source_country_reported": source_country,
        "source_language": language,
        "original_title": title,
        "title": title,
        "api_query_mode": "integrated_country_query",
        "matched_query_groups": matched_groups,
        "matched_keywords": matched_keywords,
        "query_group": matched_groups[0] if matched_groups else "unmatched",
        "keyword_query": "; ".join(matched_keywords),
        "url": url,
        "canonical_url": normalized,
        "publisher_domain": domain,
        "published_at": parse_gdelt_datetime(seendate),
        "seendate": seendate,
        "image_url": image_url,
        "has_image_url": bool(image_url),
        "summary": "",
        "description": "",
        "suspected_noise": bool(noise_matches),
        "noise_terms": noise_matches,
        "is_noise_sample": bool(noise_matches),
        "domain_title_key": f"{domain}|{normalized_text(title)}" if domain and title else "",
        "timespan": timespan,
        "raw_field_names": sorted(str(key) for key in article.keys()),
    }


def file_hash(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def integrity_targets() -> list[Path]:
    targets = [
        ROOT / "frontend" / "public" / "data" / "news.json",
        ROOT / "frontend" / "public" / "data" / "meta.json",
        ROOT / "frontend" / "public" / "data" / "business.json",
        ROOT / ".env",
    ]
    data_dir = ROOT / "data"
    if data_dir.exists():
        targets.extend(sorted(data_dir.glob("*.db")))
        targets.extend(sorted(data_dir.glob("*.sqlite")))
        targets.extend(sorted(data_dir.glob("*.sqlite3")))
    return targets


def snapshot_integrity() -> dict[str, str | None]:
    return {str(path.relative_to(ROOT)): file_hash(path) for path in integrity_targets()}


def compare_integrity(before: dict[str, str | None], after: dict[str, str | None]) -> dict[str, Any]:
    paths = sorted(set(before) | set(after))
    changed = [path for path in paths if before.get(path) != after.get(path)]
    return {"unchanged": not changed, "changed_paths": changed, "checked_paths": paths}


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> float | None:
    text = clean_text(value)
    if not text:
        return None
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return max(0.0, float(text))
    try:
        retry_at = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return max(0.0, (retry_at - now).total_seconds())


class RateLimiter:
    def __init__(
        self,
        interval_seconds: float,
        *,
        sleep_func: Callable[[float], None] = time.sleep,
        clock_func: Callable[[], float] = time.monotonic,
    ) -> None:
        self.interval_seconds = max(0.0, float(interval_seconds))
        self.sleep_func = sleep_func
        self.clock_func = clock_func
        self.last_started_at: float | None = None
        self.events: list[dict[str, Any]] = []

    def wait_before_request(self, *, country_code: str, timespan: str, attempt: int) -> dict[str, Any]:
        now = self.clock_func()
        elapsed = None if self.last_started_at is None else now - self.last_started_at
        wait_seconds = 0.0 if elapsed is None else max(0.0, self.interval_seconds - elapsed)
        if wait_seconds > 0:
            self.sleep_func(wait_seconds)
        started = self.clock_func()
        event = {
            "request_index": len(self.events) + 1,
            "country_code": country_code,
            "timespan": timespan,
            "attempt": attempt,
            "started_at": utc_now_iso(),
            "elapsed_since_previous_seconds": None if elapsed is None else round(elapsed, 3),
            "pre_request_wait_seconds": round(wait_seconds, 3),
        }
        self.events.append(event)
        self.last_started_at = started
        return event


def retry_delay_seconds(
    *,
    attempt: int,
    retry_after_header: str | None,
    retry_backoff_seconds: list[float],
    rng: random.Random,
    jitter_seconds: float,
) -> tuple[float, float | None]:
    retry_after = parse_retry_after(retry_after_header)
    if retry_after is not None:
        base = retry_after
    else:
        base = retry_backoff_seconds[min(max(attempt - 1, 0), len(retry_backoff_seconds) - 1)]
    jitter = rng.uniform(0, jitter_seconds) if jitter_seconds > 0 else 0.0
    return base + jitter, retry_after


def response_json(response: Any) -> Any:
    return response.json()


def request_gdelt(
    endpoint: str,
    query: str,
    *,
    country_code: str,
    timespan: str,
    maxrecords: int,
    timeout: float,
    rate_limiter: RateLimiter,
    retry_backoff_seconds: list[float],
    max_retries: int,
    get_func: Callable[..., Any] = requests.get,
    sleep_func: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
    jitter_seconds: float = 1.0,
) -> dict[str, Any]:
    rng = rng or random.Random()
    attempts: list[dict[str, Any]] = []
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "sort": "datedesc",
        "maxrecords": str(maxrecords),
        "timespan": timespan,
    }
    for attempt_index in range(1, max_retries + 2):
        event = rate_limiter.wait_before_request(country_code=country_code, timespan=timespan, attempt=attempt_index)
        started = time.perf_counter()
        try:
            response = get_func(endpoint, params=params, timeout=timeout, headers={"User-Agent": USER_AGENT})
        except requests.Timeout:
            attempts.append({**event, "status": "provider_timeout", "duration_seconds": round(time.perf_counter() - started, 3)})
            return {
                "status": "provider_timeout",
                "http_status": None,
                "duration_seconds": attempts[-1]["duration_seconds"],
                "failure_reason": "request_timeout",
                "payload": None,
                "request_url": endpoint,
                "attempts": attempts,
            }
        except requests.RequestException as exc:
            attempts.append({**event, "status": "provider_error", "duration_seconds": round(time.perf_counter() - started, 3)})
            return {
                "status": "provider_error",
                "http_status": None,
                "duration_seconds": attempts[-1]["duration_seconds"],
                "failure_reason": f"request_error:{exc.__class__.__name__}",
                "payload": None,
                "request_url": endpoint,
                "attempts": attempts,
            }

        duration = round(time.perf_counter() - started, 3)
        http_status = int(getattr(response, "status_code", 0) or 0)
        request_url = str(getattr(response, "url", endpoint))
        headers = getattr(response, "headers", {}) or {}
        if http_status == 429:
            retry_after_header = headers.get("Retry-After") if hasattr(headers, "get") else None
            can_retry = attempt_index <= max_retries
            retry_delay = 0.0
            retry_after_seconds = None
            if can_retry:
                retry_delay, retry_after_seconds = retry_delay_seconds(
                    attempt=attempt_index,
                    retry_after_header=retry_after_header,
                    retry_backoff_seconds=retry_backoff_seconds,
                    rng=rng,
                    jitter_seconds=jitter_seconds,
                )
            attempts.append(
                {
                    **event,
                    "status": "provider_rate_limited",
                    "http_status": http_status,
                    "duration_seconds": duration,
                    "retry_after_header": retry_after_header or "",
                    "retry_after_seconds": retry_after_seconds,
                    "scheduled_retry_delay_seconds": round(retry_delay, 3),
                    "will_retry": can_retry,
                }
            )
            if can_retry:
                sleep_func(retry_delay)
                continue
            return {
                "status": "provider_rate_limited",
                "http_status": http_status,
                "duration_seconds": duration,
                "failure_reason": "http_429",
                "payload": None,
                "request_url": request_url,
                "attempts": attempts,
            }
        if http_status >= 400:
            attempts.append({**event, "status": "provider_error", "http_status": http_status, "duration_seconds": duration})
            return {
                "status": "provider_error",
                "http_status": http_status,
                "duration_seconds": duration,
                "failure_reason": f"http_{http_status}",
                "payload": None,
                "request_url": request_url,
                "attempts": attempts,
            }
        try:
            payload = response_json(response)
        except ValueError:
            attempts.append({**event, "status": "invalid_response_schema", "http_status": http_status, "duration_seconds": duration})
            return {
                "status": "invalid_response_schema",
                "http_status": http_status,
                "duration_seconds": duration,
                "failure_reason": "non_json_response",
                "payload": None,
                "request_url": request_url,
                "attempts": attempts,
            }
        if not isinstance(payload, dict) or "articles" not in payload or not isinstance(payload.get("articles"), list):
            attempts.append({**event, "status": "invalid_response_schema", "http_status": http_status, "duration_seconds": duration})
            return {
                "status": "invalid_response_schema",
                "http_status": http_status,
                "duration_seconds": duration,
                "failure_reason": "missing_articles_list",
                "payload": payload if isinstance(payload, dict) else None,
                "request_url": request_url,
                "attempts": attempts,
            }
        status = "success" if payload["articles"] else "success_no_matches"
        attempts.append(
            {
                **event,
                "status": status,
                "http_status": http_status,
                "duration_seconds": duration,
                "result_count": len(payload["articles"]),
            }
        )
        return {
            "status": status,
            "http_status": http_status,
            "duration_seconds": duration,
            "failure_reason": "",
            "payload": payload,
            "request_url": request_url,
            "attempts": attempts,
        }
    return {
        "status": "provider_error",
        "http_status": None,
        "duration_seconds": 0,
        "failure_reason": "retry_loop_exhausted",
        "payload": None,
        "request_url": endpoint,
        "attempts": attempts,
    }


def load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "countries": {}}
    try:
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "countries": {}, "checkpoint_warning": "checkpoint_corrupt_restarted"}
    if not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("countries"), dict):
        return {"version": 1, "countries": {}, "checkpoint_warning": "checkpoint_invalid_restarted"}
    return checkpoint


def new_checkpoint(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "run_id": manifest["run_id"],
        "created_at": manifest["generated_at"],
        "updated_at": manifest["generated_at"],
        "config_fingerprint": manifest["config_fingerprint"],
        "probe_version": PROBE_VERSION,
        "countries": {},
    }


def checkpoint_country_query_fingerprints(manifest: dict[str, Any]) -> dict[str, str]:
    return {country["code"]: country["query_fingerprint"] for country in manifest.get("countries", [])}


def checkpoint_compatibility_from_payload(checkpoint: Any, manifest: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(checkpoint, dict):
        return {"status": "corrupt", "resume_possible": False, "reason": "checkpoint_root_not_object"}
    if checkpoint.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
        return {
            "status": "unsupported_schema",
            "resume_possible": False,
            "reason": f"expected_schema_{CHECKPOINT_SCHEMA_VERSION}_got_{checkpoint.get('schema_version') or checkpoint.get('version') or 'missing'}",
        }
    if checkpoint.get("config_fingerprint") != manifest.get("config_fingerprint"):
        return {"status": "stale_config", "resume_possible": False, "reason": "config_fingerprint_mismatch"}
    countries = checkpoint.get("countries")
    if not isinstance(countries, dict):
        return {"status": "corrupt", "resume_possible": False, "reason": "checkpoint_countries_not_object"}
    expected_queries = checkpoint_country_query_fingerprints(manifest)
    stale_queries = [
        code
        for code, record in countries.items()
        if code in expected_queries
        and isinstance(record, dict)
        and record.get("query_fingerprint")
        and record.get("query_fingerprint") != expected_queries[code]
    ]
    if stale_queries:
        return {
            "status": "stale_query",
            "resume_possible": False,
            "reason": "query_fingerprint_mismatch",
            "countries": sorted(stale_queries),
        }
    return {"status": "compatible", "resume_possible": True, "reason": ""}


def checkpoint_compatibility(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "resume_possible": False, "reason": "checkpoint_not_found"}
    try:
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"status": "corrupt", "resume_possible": False, "reason": type(exc).__name__}
    return checkpoint_compatibility_from_payload(checkpoint, manifest)


def checkpoint_record_for_country(
    country: dict[str, Any],
    query_config: dict[str, Any],
    *,
    timespan: str,
    maxrecords: int,
    status: str,
    attempt_count: int = 0,
    last_http_status: int | None = None,
    last_error_type: str = "",
    **extra: Any,
) -> dict[str, Any]:
    record = {
        "query_fingerprint": country_query_fingerprint(country, query_config, timespan=timespan, maxrecords=maxrecords),
        "status": status,
        "attempt_count": attempt_count,
        "last_http_status": last_http_status,
        "last_error_type": last_error_type,
        **extra,
    }
    return record


def bootstrap_checkpoint_from_report(output_dir: Path) -> dict[str, Any]:
    checkpoint = {"version": 1, "countries": {}}
    report_path = output_dir / "report.json"
    sample_path = output_dir / "sample_articles.json"
    if not report_path.exists():
        return checkpoint
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        samples = json.loads(sample_path.read_text(encoding="utf-8")) if sample_path.exists() else []
    except (json.JSONDecodeError, OSError):
        return checkpoint
    sample_by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for article in samples if isinstance(samples, list) else []:
        if isinstance(article, dict) and article.get("source_country_code"):
            sample_by_country[str(article["source_country_code"])].append(article)
    for country in report.get("countries", []):
        if not isinstance(country, dict) or country.get("status") not in TERMINAL_SUCCESS:
            continue
        code = str(country.get("code") or "")
        checkpoint["countries"][code] = {
            "status": country.get("status"),
            "updated_at": report.get("checked_at") or utc_now_iso(),
            "article_observations": country.get("article_observations", 0),
            "selected_sourcecountry": country.get("selected_sourcecountry", ""),
            "sourcecountry_validated": country.get("sourcecountry_validated", False),
            "timespan_counts": country.get("timespan_counts", {}),
            "query_group_counts": country.get("query_group_counts", {}),
            "articles": sample_by_country.get(code, []),
            "from_previous_report": True,
        }
    return checkpoint


def save_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    checkpoint["updated_at"] = utc_now_iso()
    write_json(path, checkpoint)


def country_order(countries: list[dict[str, Any]], *, seed: int) -> list[dict[str, Any]]:
    ordered = list(countries)
    rng = random.Random(seed)
    rng.shuffle(ordered)
    return ordered


def dedupe_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for article in articles:
        key = article.get("canonical_url") or article.get("url") or f"{article.get('publisher_domain')}|{article.get('title')}"
        if not key or key in seen:
            continue
        seen.add(str(key))
        deduped.append(article)
    return deduped


def article_groups(article: dict[str, Any]) -> list[str]:
    groups = article.get("matched_query_groups")
    if isinstance(groups, list) and groups:
        return [str(group) for group in groups if str(group)]
    legacy = clean_text(article.get("query_group"))
    return [legacy] if legacy and legacy != "unmatched" else ["unmatched"]


def dedupe_metrics(articles: list[dict[str, Any]]) -> dict[str, Any]:
    raw_urls = [article["url"] for article in articles if article.get("url")]
    canonical_urls = [article["canonical_url"] for article in articles if article.get("canonical_url")]
    domain_titles = [article["domain_title_key"] for article in articles if article.get("domain_title_key")]
    by_canonical_groups: dict[str, set[str]] = defaultdict(set)
    by_canonical_countries: dict[str, set[str]] = defaultdict(set)
    for article in articles:
        canonical = article.get("canonical_url")
        if not canonical:
            continue
        for group in article_groups(article):
            by_canonical_groups[canonical].add(str(group))
        by_canonical_countries[canonical].add(str(article.get("source_country_code")))
    return {
        "total_article_observations": len(articles),
        "same_url_duplicates": len(raw_urls) - len(set(raw_urls)),
        "canonical_url_duplicates": len(canonical_urls) - len(set(canonical_urls)),
        "domain_title_duplicates": len(domain_titles) - len(set(domain_titles)),
        "query_pack_cross_duplicates": sum(1 for groups in by_canonical_groups.values() if len(groups) > 1),
        "country_cross_duplicates": sum(1 for countries in by_canonical_countries.values() if len(countries) > 1),
        "unique_canonical_urls": len(set(canonical_urls)),
    }


def query_quality(articles: list[dict[str, Any]], packs: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for pack in packs:
        group_id = pack["id"]
        group_articles = [article for article in articles if group_id in article_groups(article)]
        noise_counter = Counter(term for article in group_articles for term in article.get("noise_terms", []))
        noise_count = sum(1 for article in group_articles if article.get("suspected_noise"))
        result[group_id] = {
            "article_observations": len(group_articles),
            "noise_sample_count": noise_count,
            "noise_ratio": round(noise_count / len(group_articles), 4) if group_articles else 0,
            "noise_terms": dict(noise_counter),
        }
    return result


def distribution(values: list[str]) -> dict[str, Any]:
    total = len(values)
    counts = Counter(value or "unknown" for value in values)
    return {
        key: {"count": count, "ratio": round(count / total, 4) if total else 0}
        for key, count in counts.most_common()
    }


def bias_report(articles: list[dict[str, Any]], request_reports: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(articles)
    country_dist = distribution([str(article.get("source_country_code") or "") for article in articles])
    query_values: list[str] = []
    for article in articles:
        groups = article_groups(article)
        query_values.extend(str(group) for group in groups)
    query_dist = distribution(query_values)
    language_dist = distribution([str(article.get("source_language") or "") for article in articles])
    domain_dist = distribution([str(article.get("publisher_domain") or "") for article in articles])
    http_attempts = [attempt for report in request_reports for attempt in report.get("attempts", [])]
    rate_limit_events = [attempt for attempt in http_attempts if attempt.get("http_status") == 429]
    retry_successes = sum(1 for report in request_reports if any(a.get("http_status") == 429 for a in report.get("attempts", [])) and report.get("status") == "success")
    return {
        "country_distribution": country_dist,
        "query_pack_distribution": query_dist,
        "language_distribution": language_dist,
        "domain_distribution": domain_dist,
        "rate_limit_event_count": len(rate_limit_events),
        "api_attempt_count": len(http_attempts),
        "rate_limit_rate": round(len(rate_limit_events) / len(http_attempts), 4) if http_attempts else 0,
        "retry_success_count": retry_successes,
        "retry_success_rate": round(retry_successes / len(rate_limit_events), 4) if rate_limit_events else 0,
        "skew_warning": any(data["ratio"] >= 0.7 for data in country_dist.values()) if total else False,
        "query_pack_skew_warning": any(data["ratio"] >= 0.7 for data in query_dist.values()) if query_values else False,
    }


def make_manual_review_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    country_counts: Counter[str] = Counter()
    group_counts: Counter[str] = Counter()
    for article in dedupe_articles(articles):
        if len(selected) >= 100:
            break
        country = str(article.get("source_country_code") or "")
        groups = article_groups(article)
        if country_counts[country] >= 10:
            continue
        if all(group_counts[group] >= 20 for group in groups):
            continue
        key = article.get("canonical_url") or article.get("url")
        if key in seen:
            continue
        seen.add(str(key))
        country_counts[country] += 1
        for group in groups:
            group_counts[group] += 1
        selected.append(
            {
                "review_id": f"GN-{len(selected) + 1:04d}",
                "country_code": country,
                "sourcecountry": article.get("source_country_reported") or "",
                "title": article.get("title") or "",
                "domain": article.get("publisher_domain") or "",
                "language": article.get("source_language") or "",
                "seendate": article.get("seendate") or "",
                "url": article.get("url") or "",
                "canonical_url": article.get("canonical_url") or "",
                "matched_query_groups": groups,
                "matched_keywords": article.get("matched_keywords") or [],
                "suspected_noise": bool(article.get("suspected_noise")),
                "reviewer_decision": "",
                "reviewer_note": "",
            }
        )
    return selected


def write_manual_review_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_REVIEW_FIELDS)
        writer.writeheader()
        for row in rows:
            serializable = dict(row)
            serializable["matched_query_groups"] = ";".join(row.get("matched_query_groups") or [])
            serializable["matched_keywords"] = ";".join(row.get("matched_keywords") or [])
            writer.writerow(serializable)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# GDELT Global News Probe",
        "",
        f"- Checked at: `{report['checked_at']}`",
        f"- Endpoint: `{report['endpoint']}`",
        f"- Overall status: `{report['overall_status']}`",
        f"- API attempts: `{report['api_call_stats']['api_attempt_count']}`",
        f"- First requests: `{report['api_call_stats']['initial_request_count']}`",
        f"- Retry attempts: `{report['api_call_stats']['retry_attempt_count']}`",
        f"- Rate limit events: `{report['bias']['rate_limit_event_count']}`",
        f"- Retry successes after 429: `{report['bias']['retry_success_count']}`",
        f"- Request order seed: `{report['request_order_seed']}`",
        f"- Country request order: `{', '.join(report['country_request_order'])}`",
        f"- Country skew warning: `{report['bias']['skew_warning']}`",
        f"- Query pack skew warning: `{report['bias']['query_pack_skew_warning']}`",
        f"- Manual review articles: `{report['manual_review_article_count']}`",
        f"- Data integrity unchanged: `{report['data_integrity']['unchanged']}`",
        "",
        "## Country Results",
        "",
        "| Country | Status | Sourcecountry | Attempts | Retries | Articles | Filter validated | Failure |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for country in report["countries"]:
        lines.append(
            "| {code} {name} | `{status}` | `{sourcecountry}` | {attempts} | {retries} | {articles} | {validated} | {failure} |".format(
                code=country["code"],
                name=country["name_en"],
                status=country["status"],
                sourcecountry=country.get("selected_sourcecountry") or "",
                attempts=country.get("api_attempt_count", 0),
                retries=country.get("retry_attempt_count", 0),
                articles=country["article_observations"],
                validated="yes" if country["sourcecountry_validated"] else "not confirmed",
                failure=country.get("failure_reason") or "",
            )
        )
    lines.extend(["", "## Query Pack Quality", ""])
    lines.append("| Query pack | Observations | Noise samples | Noise ratio |")
    lines.append("| --- | ---: | ---: | ---: |")
    for group_id, quality in report["query_quality"].items():
        lines.append(f"| `{group_id}` | {quality['article_observations']} | {quality['noise_sample_count']} | {quality['noise_ratio']} |")
    lines.extend(
        [
            "",
            "## Bias",
            "",
            f"- Country distribution: `{json.dumps(report['bias']['country_distribution'], ensure_ascii=False)}`",
            f"- Query pack distribution: `{json.dumps(report['bias']['query_pack_distribution'], ensure_ascii=False)}`",
            f"- Language distribution: `{json.dumps(report['bias']['language_distribution'], ensure_ascii=False)}`",
            f"- Top domains: `{json.dumps(dict(list(report['bias']['domain_distribution'].items())[:10]), ensure_ascii=False)}`",
            f"- 429 rate: `{report['bias']['rate_limit_rate']}`",
            f"- Retry success rate: `{report['bias']['retry_success_rate']}`",
            "",
            "## Response Schema",
            "",
            f"- Top-level fields: `{', '.join(report['schema']['top_level_fields']) or 'none'}`",
            f"- Article fields: `{', '.join(report['schema']['article_fields']) or 'none'}`",
            "",
            "## Deduplication",
            "",
            f"- Same URL duplicates: `{report['deduplication']['same_url_duplicates']}`",
            f"- Canonical URL duplicates: `{report['deduplication']['canonical_url_duplicates']}`",
            f"- Same domain + same title duplicates: `{report['deduplication']['domain_title_duplicates']}`",
            f"- Query pack cross-duplicates: `{report['deduplication']['query_pack_cross_duplicates']}`",
            f"- Country cross-duplicates: `{report['deduplication']['country_cross_duplicates']}`",
            "",
            "## Recommendations",
            "",
            f"- Exclude terms to keep testing: `{', '.join(report['recommendations']['exclude_terms'])}`",
            f"- Recommended maxrecords: `{report['recommendations']['maxrecords']}`",
            f"- Recommended lookback period: `{report['recommendations']['lookback_period']}`",
            f"- Recommended daily API calls: `{report['recommendations']['daily_api_calls']}`",
            f"- 10.10-B ready: `{report['recommendations']['ready_for_10_10_b']}`",
            f"- Blocking reasons: `{', '.join(report['recommendations']['blocking_reasons']) or 'none'}`",
            "",
            "## 10.10-B Implementation Targets",
            "",
        ]
    )
    for target in report["next_step_10_10_b_targets"]:
        lines.append(f"- `{target}`")
    lines.extend(["", "## Notes", ""])
    lines.append("- The probe records only public metadata returned by GDELT. It does not crawl article bodies.")
    lines.append("- Empty summaries/descriptions are preserved when GDELT does not provide them.")
    lines.append("- `success_no_matches` means the API worked but returned zero articles.")
    lines.append("- HTTP 429 is never treated as a zero-result country.")
    return "\n".join(lines) + "\n"


def initial_country_report(country: dict[str, Any], status: str = "pending") -> dict[str, Any]:
    return {
        "code": country["code"],
        "name_ko": country["name_ko"],
        "name_en": country["name_en"],
        "status": status,
        "selected_sourcecountry": gdelt_sourcecountry(country),
        "sourcecountry_candidates": country.get("gdelt_sourcecountry_candidates") or [],
        "sourcecountry_values_seen": [],
        "sourcecountry_validated": False,
        "timespan_counts": {},
        "article_observations": 0,
        "unique_canonical_urls": 0,
        "query_group_counts": {},
        "noise_count": 0,
        "api_attempt_count": 0,
        "initial_request_count": 0,
        "retry_attempt_count": 0,
        "failure_reason": "",
        "articles": [],
    }


def report_from_checkpoint(country: dict[str, Any], checkpoint_record: dict[str, Any]) -> dict[str, Any]:
    report = initial_country_report(country, str(checkpoint_record.get("status") or "pending"))
    report.update(
        {
            "selected_sourcecountry": checkpoint_record.get("selected_sourcecountry") or report["selected_sourcecountry"],
            "sourcecountry_validated": bool(checkpoint_record.get("sourcecountry_validated")),
            "timespan_counts": checkpoint_record.get("timespan_counts") or {},
            "article_observations": int(checkpoint_record.get("article_observations") or 0),
            "unique_canonical_urls": len({a.get("canonical_url") for a in checkpoint_record.get("articles", []) if a.get("canonical_url")}),
            "query_group_counts": checkpoint_record.get("query_group_counts") or {},
            "articles": checkpoint_record.get("articles") or [],
            "from_checkpoint": True,
        }
    )
    return report


def collect_country(
    *,
    country: dict[str, Any],
    endpoint: str,
    query_config: dict[str, Any],
    maxrecords: int,
    timeout: float,
    rate_limiter: RateLimiter,
    retry_backoff_seconds: list[float],
    max_retries: int,
    get_func: Callable[..., Any],
    sleep_func: Callable[[float], None],
    rng: random.Random,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sourcecountry = gdelt_sourcecountry(country)
    query = build_country_query(country, query_config)
    request_reports: list[dict[str, Any]] = []
    selected = request_gdelt(
        endpoint,
        query,
        country_code=country["code"],
        timespan="7d",
        maxrecords=maxrecords,
        timeout=timeout,
        rate_limiter=rate_limiter,
        retry_backoff_seconds=retry_backoff_seconds,
        max_retries=max_retries,
        get_func=get_func,
        sleep_func=sleep_func,
        rng=rng,
    )
    selected.update({"timespan": "7d", "sourcecountry_filter": sourcecountry, "query": query})
    request_reports.append(selected)
    if selected["status"] == "success_no_matches":
        fallback = request_gdelt(
            endpoint,
            query,
            country_code=country["code"],
            timespan="30d",
            maxrecords=maxrecords,
            timeout=timeout,
            rate_limiter=rate_limiter,
            retry_backoff_seconds=retry_backoff_seconds,
            max_retries=max_retries,
            get_func=get_func,
            sleep_func=sleep_func,
            rng=rng,
        )
        fallback.update({"timespan": "30d", "sourcecountry_filter": sourcecountry, "query": query})
        request_reports.append(fallback)
        selected = fallback

    payload = selected.get("payload") if isinstance(selected.get("payload"), dict) else {}
    raw_articles = payload.get("articles") if isinstance(payload.get("articles"), list) else []
    normalized_articles = [
        normalize_article(article, country=country, query_config=query_config, sourcecountry_filter=sourcecountry, timespan=str(selected.get("timespan") or ""))
        for article in raw_articles
        if isinstance(article, dict)
    ]
    sourcecountry_values = sorted({article["source_country_reported"] for article in normalized_articles if article.get("source_country_reported")})
    sourcecountry_validated = any(country_filter_matches(country, value) for value in sourcecountry_values)
    group_counts: Counter[str] = Counter()
    for article in normalized_articles:
        groups = article.get("matched_query_groups") or ["unmatched"]
        for group in groups:
            group_counts[group] += 1
    api_attempt_count = sum(len(report.get("attempts", [])) for report in request_reports)
    retry_attempt_count = sum(max(0, len(report.get("attempts", [])) - 1) for report in request_reports)
    country_report = {
        **initial_country_report(country, selected["status"]),
        "selected_sourcecountry": sourcecountry,
        "sourcecountry_values_seen": sourcecountry_values,
        "sourcecountry_validated": sourcecountry_validated,
        "timespan_counts": {
            str(report.get("timespan") or ""): len((report.get("payload") or {}).get("articles", []))
            for report in request_reports
            if isinstance(report.get("payload"), dict)
        },
        "article_observations": len(normalized_articles),
        "unique_canonical_urls": len({article["canonical_url"] for article in normalized_articles if article.get("canonical_url")}),
        "query_group_counts": dict(group_counts),
        "noise_count": sum(1 for article in normalized_articles if article.get("suspected_noise")),
        "api_attempt_count": api_attempt_count,
        "initial_request_count": len(request_reports),
        "retry_attempt_count": retry_attempt_count,
        "failure_reason": selected.get("failure_reason") or "",
        "articles": normalized_articles,
    }
    return country_report, request_reports


def choose_countries_to_run(
    countries: list[dict[str, Any]],
    checkpoint: dict[str, Any],
    *,
    resume: bool,
    all_countries: bool,
    force_countries: list[str],
    max_countries: int | None,
    seed: int,
) -> list[dict[str, Any]]:
    force_set = {code.upper() for code in force_countries}
    ordered = country_order(countries, seed=seed)
    selected: list[dict[str, Any]] = []
    for country in ordered:
        code = country["code"]
        checkpoint_status = (checkpoint.get("countries") or {}).get(code, {}).get("status")
        if force_set:
            if code in force_set:
                selected.append(country)
            continue
        if all_countries:
            selected.append(country)
            continue
        if resume:
            if checkpoint_status not in TERMINAL_SUCCESS:
                selected.append(country)
            continue
        selected.append(country)
    if max_countries is not None:
        selected = selected[:max_countries]
    return selected


def run_probe(
    *,
    max_countries: int | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    timeout: float = 20.0,
    request_interval: float | None = None,
    resume: bool = False,
    all_countries: bool = False,
    force_countries: list[str] | None = None,
    seed: int | None = None,
    max_retries_override: int | None = None,
    get_func: Callable[..., Any] = requests.get,
    sleep_func: Callable[[float], None] = time.sleep,
    jitter_seconds: float = 1.0,
) -> dict[str, Any]:
    country_config = load_json(COUNTRIES_PATH)
    query_config = load_json(QUERIES_PATH)
    endpoint = country_config["endpoint"]
    maxrecords = int(country_config.get("maxrecords") or 50)
    request_interval = float(country_config.get("request_interval_seconds") if request_interval is None else request_interval)
    retry_backoff_seconds = [float(value) for value in country_config.get("retry_backoff_seconds", [30, 60, 120, 240])]
    max_retries = int(country_config.get("max_retries", 4) if max_retries_override is None else max_retries_override)
    circuit_breaker_threshold = int(country_config.get("circuit_breaker_consecutive_429", 2))
    countries = [country for country in country_config["countries"] if country.get("enabled", True)]
    for country in countries:
        validate_country_config(country)
    default_timespan = str((country_config.get("timespans") or ["7d"])[0])
    manifest = build_query_manifest(country_config, query_config, timespan=default_timespan, maxrecords=maxrecords)
    force_countries = force_countries or []
    seed = seed if seed is not None else int(datetime.now(timezone.utc).strftime("%Y%m%d%H%M"))
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "checkpoint.json"
    checkpoint_state = checkpoint_compatibility(checkpoint_path, manifest)
    checkpoint = load_checkpoint(checkpoint_path) if checkpoint_state["status"] == "compatible" else new_checkpoint(manifest)
    checkpoint["checkpoint_compatibility"] = checkpoint_state
    checkpoint.setdefault("countries", {})

    before_integrity = snapshot_integrity()
    rate_limiter = RateLimiter(request_interval, sleep_func=sleep_func)
    rng = random.Random(seed)
    run_countries = choose_countries_to_run(
        countries,
        checkpoint,
        resume=resume,
        all_countries=all_countries,
        force_countries=force_countries,
        max_countries=max_countries,
        seed=seed,
    )
    run_codes = [country["code"] for country in run_countries]
    request_reports: list[dict[str, Any]] = []
    country_reports_by_code: dict[str, dict[str, Any]] = {}
    consecutive_429 = 0
    circuit_opened = False

    for country in run_countries:
        if circuit_opened:
            pending = initial_country_report(country, "pending_rate_limit")
            pending["failure_reason"] = "circuit_breaker_open_after_consecutive_429"
            country_reports_by_code[country["code"]] = pending
            checkpoint["countries"][country["code"]] = checkpoint_record_for_country(
                country,
                query_config,
                timespan=default_timespan,
                maxrecords=maxrecords,
                status="pending_rate_limit",
                attempt_count=0,
                last_http_status=None,
                last_error_type="pending_rate_limit",
                updated_at=utc_now_iso(),
                article_observations=0,
                selected_sourcecountry=pending["selected_sourcecountry"],
                sourcecountry_validated=False,
                timespan_counts={},
                query_group_counts={},
                articles=[],
            )
            continue
        country_report, country_requests = collect_country(
            country=country,
            endpoint=endpoint,
            query_config=query_config,
            maxrecords=maxrecords,
            timeout=timeout,
            rate_limiter=rate_limiter,
            retry_backoff_seconds=retry_backoff_seconds,
            max_retries=max_retries,
            get_func=get_func,
            sleep_func=sleep_func,
            rng=rng,
        )
        request_reports.extend(country_requests)
        country_reports_by_code[country["code"]] = country_report
        last_http_status = None
        for request_report in reversed(country_requests):
            if request_report.get("http_status") is not None:
                last_http_status = int(request_report["http_status"])
                break
        checkpoint["countries"][country["code"]] = checkpoint_record_for_country(
            country,
            query_config,
            timespan=default_timespan,
            maxrecords=maxrecords,
            status=country_report["status"],
            attempt_count=int(country_report.get("api_attempt_count") or 0),
            last_http_status=last_http_status,
            last_error_type="" if country_report["status"] in TERMINAL_SUCCESS else country_report["status"],
            updated_at=utc_now_iso(),
            article_observations=country_report["article_observations"],
            selected_sourcecountry=country_report["selected_sourcecountry"],
            sourcecountry_validated=country_report["sourcecountry_validated"],
            timespan_counts=country_report["timespan_counts"],
            query_group_counts=country_report["query_group_counts"],
            articles=country_report["articles"],
        )
        save_checkpoint(checkpoint_path, checkpoint)
        if country_report["status"] == "provider_rate_limited":
            consecutive_429 += 1
        else:
            consecutive_429 = 0
        if consecutive_429 >= circuit_breaker_threshold:
            circuit_opened = True

    for country in countries:
        code = country["code"]
        if code in country_reports_by_code:
            continue
        record = checkpoint.get("countries", {}).get(code)
        if record:
            country_reports_by_code[code] = report_from_checkpoint(country, record)
        else:
            country_reports_by_code[code] = initial_country_report(country, "pending")

    country_reports = [country_reports_by_code[country["code"]] for country in countries]
    all_articles = [article for country in country_reports for article in country.get("articles", [])]
    dedupe = dedupe_metrics(all_articles)
    quality = query_quality(all_articles, list(query_config["query_packs"]))
    bias = bias_report(all_articles, request_reports)
    manual_review = make_manual_review_articles(all_articles)
    top_level_fields = {"articles"} if any(country.get("article_observations") for country in country_reports) else set()
    article_fields = sorted({field for article in all_articles for field in article.get("raw_field_names", [])})
    after_integrity = snapshot_integrity()
    integrity = compare_integrity(before_integrity, after_integrity)
    status_counts = Counter(country["status"] for country in country_reports)
    blocking_reasons = []
    if status_counts.get("provider_rate_limited") or status_counts.get("pending_rate_limit"):
        blocking_reasons.append("rate_limited_countries_remaining")
    if status_counts.get("provider_timeout") or status_counts.get("provider_error") or status_counts.get("invalid_response_schema"):
        blocking_reasons.append("provider_errors_remaining")
    ready_for_10_10_b = not blocking_reasons and any(country["status"] == "success" for country in country_reports)
    api_attempt_count = sum(len(report.get("attempts", [])) for report in request_reports)
    retry_attempt_count = sum(max(0, len(report.get("attempts", [])) - 1) for report in request_reports)
    error_country_count = sum(count for status, count in status_counts.items() if status in ERROR_STATUSES)
    if error_country_count:
        overall_status = "partial"
    elif any(country["status"] == "success" for country in country_reports):
        overall_status = "success"
    else:
        overall_status = "success_no_matches"
    report = {
        "checked_at": utc_now_iso(),
        "endpoint": endpoint,
        "overall_status": overall_status,
        "request_order_seed": seed,
        "country_request_order": run_codes,
        "countries_checked_this_run": run_codes,
        "countries_total": len(countries),
        "query_mode": "integrated_country_query",
        "integrated_query_terms": active_query_terms(query_config),
        "disabled_queries": {
            pack["id"]: pack.get("disabled_queries", [])
            for pack in query_config["query_packs"]
            if pack.get("disabled_queries")
        },
        "api_call_stats": {
            "api_attempt_count": api_attempt_count,
            "initial_request_count": len(request_reports),
            "retry_attempt_count": retry_attempt_count,
            "request_interval_seconds": request_interval,
            "max_retries": max_retries,
            "circuit_breaker_consecutive_429": circuit_breaker_threshold,
        },
        "summary": {
            "total_article_observations": len(all_articles),
            "unique_canonical_urls": dedupe["unique_canonical_urls"],
            "countries_with_success": status_counts.get("success", 0),
            "countries_with_no_matches": status_counts.get("success_no_matches", 0),
            "countries_with_errors": error_country_count,
            "noise_sample_count": sum(1 for article in all_articles if article.get("suspected_noise")),
        },
        "schema": {
            "top_level_fields": sorted(top_level_fields),
            "article_fields": article_fields,
        },
        "countries": country_reports,
        "requests": request_reports,
        "rate_limit_events": [
            {**attempt, "country_code": report.get("country_code", attempt.get("country_code"))}
            for report in request_reports
            for attempt in report.get("attempts", [])
            if attempt.get("http_status") == 429
        ],
        "request_schedule_events": rate_limiter.events,
        "deduplication": dedupe,
        "query_quality": quality,
        "bias": bias,
        "manual_review_article_count": len(manual_review),
        "recommendations": {
            "exclude_terms": sorted(set(query_config.get("noise_terms") or [])),
            "maxrecords": maxrecords,
            "lookback_period": "7d primary, fallback to 30d only when 7d succeeds with zero articles",
            "daily_api_calls": len(countries),
            "ready_for_10_10_b": ready_for_10_10_b,
            "blocking_reasons": blocking_reasons,
            "db_field_changes_needed": True,
            "recommended_fields": query_config.get("recommended_output_fields", []),
        },
        "next_step_10_10_b_targets": [
            "src/collectors/gdelt_global_news.py",
            "scripts/collect_gdelt_global_news.py",
            "scripts/test_gdelt_global_news_collector.py",
            "scripts/export_public_json.py",
            "frontend/public/data/news.json",
            "frontend/public/data/meta.json",
        ],
        "data_integrity": integrity,
    }
    country_counts = {
        country["code"]: {
            "name_en": country["name_en"],
            "status": country["status"],
            "article_observations": country["article_observations"],
            "unique_canonical_urls": country["unique_canonical_urls"],
            "timespan_counts": country["timespan_counts"],
            "query_group_counts": country["query_group_counts"],
            "sourcecountry_validated": country["sourcecountry_validated"],
        }
        for country in country_reports
    }
    write_json(output_dir / "report.json", report)
    (output_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
    write_json(output_dir / "country_counts.json", country_counts)
    write_json(output_dir / "query_quality.json", quality)
    write_json(output_dir / "sample_articles.json", dedupe_articles(all_articles)[:200])
    write_json(output_dir / "manual_review_articles.json", manual_review)
    write_manual_review_csv(output_dir / "manual_review_articles.csv", manual_review)
    write_json(output_dir / "rate_limit_events.json", report["rate_limit_events"])
    save_checkpoint(checkpoint_path, checkpoint)
    return report


def print_queries() -> int:
    country_config = load_json(COUNTRIES_PATH)
    query_config = load_json(QUERIES_PATH)
    endpoint = country_config["endpoint"]
    maxrecords = int(country_config.get("maxrecords") or 50)
    timespan = (country_config.get("timespans") or ["7d"])[0]
    active_packs = [
        {"id": pack["id"], "queries": list(pack.get("queries") or [])}
        for pack in query_config["query_packs"]
        if pack.get("queries")
    ]
    rows: list[dict[str, Any]] = []
    for country in country_config["countries"]:
        if not country.get("enabled", True):
            continue
        validate_country_config(country)
        params = build_gdelt_params(country, query_config, timespan=timespan, maxrecords=maxrecords)
        rows.append(
            {
                "code": country["code"],
                "name": country["name"],
                "gdelt_sourcecountry": gdelt_sourcecountry(country),
                "active_query_packs": active_packs,
                "query": params["query"],
                "url": build_gdelt_url(endpoint, country, query_config, timespan=timespan, maxrecords=maxrecords),
                "timespan": params["timespan"],
                "maxrecords": params["maxrecords"],
                "mode": params["mode"],
                "format": params["format"],
            }
        )
    print(json.dumps({"endpoint": endpoint, "countries": rows}, ensure_ascii=False, indent=2))
    return 0


def expected_max_http_requests(country_config: dict[str, Any], country_count: int) -> int:
    timespan_count = len(country_config.get("timespans") or ["7d"])
    max_retries = int(country_config.get("max_retries", 4))
    return country_count * timespan_count * (max_retries + 1)


def relative_display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return path.name


def build_run_plan(country_config: dict[str, Any], query_config: dict[str, Any], *, output_dir: Path) -> dict[str, Any]:
    manifest = build_query_manifest(country_config, query_config)
    checkpoint_path = output_dir / "checkpoint.json"
    checkpoint_state = checkpoint_compatibility(checkpoint_path, manifest)
    planned_countries = len(manifest["countries"])
    timespan_count = len(country_config.get("timespans") or ["7d"])
    max_retries = int(country_config.get("max_retries", 4))
    max_http_requests_per_country = timespan_count * (max_retries + 1)
    return {
        **manifest,
        "checkpoint": {
            "path": relative_display_path(checkpoint_path),
            **checkpoint_state,
        },
        "resume_possible": checkpoint_state["status"] == "compatible",
        "planned_country_count": planned_countries,
        "base_http_requests_per_country": 1,
        "max_http_requests_per_country": max_http_requests_per_country,
        "expected_base_http_requests": planned_countries,
        "expected_max_http_requests": expected_max_http_requests(country_config, planned_countries),
    }


def print_run_plan(*, output_dir: Path = DEFAULT_OUTPUT_DIR) -> int:
    country_config = load_json(COUNTRIES_PATH)
    query_config = load_json(QUERIES_PATH)
    plan = build_run_plan(country_config, query_config, output_dir=output_dir)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe GDELT DOC 2.0 global modular construction news coverage.")
    parser.add_argument("--print-queries", action="store_true", help="Print country query plans without network, checkpoint, or artifact writes.")
    parser.add_argument("--print-run-plan", action="store_true", help="Print run IDs, fingerprints, URLs, and checkpoint compatibility without network or writes.")
    parser.add_argument("--max-countries", type=int, default=None, help="Limit countries for smoke testing.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--request-interval", type=float, default=None)
    parser.add_argument("--resume", action="store_true", help="Only request countries without success/success_no_matches in checkpoint.")
    parser.add_argument("--all", action="store_true", help="Request all enabled countries, ignoring terminal checkpoint states.")
    parser.add_argument("--force-country", action="append", default=[], help="Request a specific country code regardless of checkpoint.")
    parser.add_argument("--seed", type=int, default=None, help="Request order seed.")
    parser.add_argument("--max-retries", type=int, default=None, help="Override configured 429 retry count for bounded diagnostics.")
    parser.add_argument("--jitter-seconds", type=float, default=1.0, help="Maximum random jitter added to 429 retry waits.")
    args = parser.parse_args()
    if args.print_queries:
        return print_queries()
    if args.print_run_plan:
        return print_run_plan(output_dir=args.output_dir)
    report = run_probe(
        max_countries=args.max_countries,
        output_dir=args.output_dir,
        timeout=args.timeout,
        request_interval=args.request_interval,
        resume=args.resume,
        all_countries=args.all,
        force_countries=args.force_country,
        seed=args.seed,
        max_retries_override=args.max_retries,
        jitter_seconds=args.jitter_seconds,
    )
    print(f"overall_status={report['overall_status']}")
    print(f"countries_checked_this_run={','.join(report['countries_checked_this_run'])}")
    print(f"total_article_observations={report['summary']['total_article_observations']}")
    print(f"unique_canonical_urls={report['summary']['unique_canonical_urls']}")
    print(f"api_attempt_count={report['api_call_stats']['api_attempt_count']}")
    print(f"rate_limit_events={report['bias']['rate_limit_event_count']}")
    print(f"data_integrity_unchanged={report['data_integrity']['unchanged']}")
    print(f"report_path={args.output_dir / 'report.json'}")
    if not report["data_integrity"]["unchanged"]:
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
