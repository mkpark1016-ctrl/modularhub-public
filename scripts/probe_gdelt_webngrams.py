from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "global_news_webngrams_probe"
WEBNGRAMS_TEMPLATE = "https://data.gdeltproject.org/gdeltv3/webngrams/{timestamp}.webngrams.json.gz"
GAL_TEMPLATE = "https://data.gdeltproject.org/gdeltv3/gal/{timestamp}.gal.json.gz"
FIXTURE_WEBNGRAMS = ROOT / "tests" / "fixtures" / "webngrams_sample.jsonl"
FIXTURE_GAL = ROOT / "tests" / "fixtures" / "gal_sample.jsonl"
PUBLIC_DATA_PATHS = [
    ROOT / "frontend" / "public" / "data" / "business.json",
    ROOT / "frontend" / "public" / "data" / "news.json",
    ROOT / "frontend" / "public" / "data" / "meta.json",
]
CHECKPOINT_PATH = ROOT / "artifacts" / "global_news_probe" / "checkpoint.json"
KEYWORDS = ["modular", "prefab", "prefabricated", "offsite", "off-site"]
PHRASES = [
    "modular construction",
    "modular building",
    "modular housing",
    "prefab construction",
    "prefabricated building",
    "prefabricated housing",
    "offsite construction",
    "off-site construction",
]
NOISE_TERMS = [
    "software",
    "programming",
    "synthesizer",
    "smartphone",
    "furniture",
    "arithmetic",
    "nuclear reactor",
]
TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "yclid",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def file_hash(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def integrity_snapshot() -> dict[str, Any]:
    return {
        "public_json": {str(path): file_hash(path) for path in PUBLIC_DATA_PATHS},
        "db": {
            str(path): file_hash(path)
            for path in sorted((ROOT / "data").rglob("*"))
            if path.is_file() and path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}
        }
        if (ROOT / "data").exists()
        else {},
        "env": {str(ROOT / ".env"): file_hash(ROOT / ".env")},
        "checkpoint": {str(CHECKPOINT_PATH): file_hash(CHECKPOINT_PATH)},
    }


def integrity_unchanged(before: dict[str, Any], after: dict[str, Any]) -> dict[str, bool]:
    return {
        "public_json_unchanged": before.get("public_json") == after.get("public_json"),
        "db_unchanged": before.get("db") == after.get("db"),
        "env_unchanged": before.get("env") == after.get("env"),
        "checkpoint_unchanged": before.get("checkpoint") == after.get("checkpoint"),
    }


def validate_timestamp(timestamp: str) -> str:
    value = clean_text(timestamp)
    if not re.fullmatch(r"\d{14}", value):
        raise ValueError("timestamp must use YYYYMMDDHHMMSS UTC format")
    return value


def webngrams_url(timestamp: str) -> str:
    return WEBNGRAMS_TEMPLATE.format(timestamp=validate_timestamp(timestamp))


def gal_url(timestamp: str) -> str:
    return GAL_TEMPLATE.format(timestamp=validate_timestamp(timestamp))


def normalize_text(value: Any) -> str:
    text = clean_text(value).lower()
    text = text.replace("off-site", "off site")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def contains_phrase(normalized_context: str, phrase: str) -> bool:
    needle = normalize_text(phrase)
    if not needle:
        return False
    return f" {needle} " in f" {normalized_context} "


def row_context(row: dict[str, Any]) -> str:
    return " ".join(clean_text(row.get(key)) for key in ("pre", "ngram", "post") if clean_text(row.get(key)))


def canonicalize_url(url: Any) -> str:
    raw = clean_text(url)
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in TRACKING_PARAMS:
            continue
        query.append((key, value))
    return urlunsplit((scheme, netloc, parts.path.rstrip("/") or "/", urlencode(sorted(query)), ""))


def domain_from_url(url: str) -> str:
    try:
        return urlsplit(url).netloc.lower()
    except ValueError:
        return ""


def is_http_url(url: Any) -> bool:
    try:
        parts = urlsplit(clean_text(url))
    except ValueError:
        return False
    return parts.scheme.lower() in {"http", "https"} and bool(parts.netloc)


def cctld_candidate(domain: str) -> str:
    labels = [part for part in clean_text(domain).split(".") if part]
    if labels and len(labels[-1]) == 2:
        return labels[-1].upper()
    return ""


def noise_match(normalized_context: str) -> tuple[bool, str]:
    for term in NOISE_TERMS:
        if contains_phrase(normalized_context, term):
            return True, term
    return False, ""


def has_required_webngram_fields(row: dict[str, Any]) -> bool:
    return all(key in row and clean_text(row.get(key)) for key in ("date", "ngram", "pre", "post", "lang", "type", "url"))


def smoke_sample_from_row(row: dict[str, Any], *, timestamp: str) -> dict[str, Any]:
    canonical_url = canonicalize_url(row.get("url"))
    domain = domain_from_url(canonical_url)
    return {
        "timestamp": timestamp,
        "url": clean_text(row.get("url")),
        "canonical_url": canonical_url,
        "domain": domain,
        "published_at": clean_text(row.get("date")),
        "language": clean_text(row.get("lang")),
        "ngram": clean_text(row.get("ngram")),
        "gal_joined": False,
        "cc_tld_candidate": cctld_candidate(domain),
    }


def match_webngram_row(row: dict[str, Any]) -> dict[str, Any] | None:
    url = clean_text(row.get("url"))
    ngram = clean_text(row.get("ngram"))
    if not url or not ngram:
        return None
    context = row_context(row)
    normalized_context = normalize_text(context)
    matched_keyword = ""
    for keyword in KEYWORDS:
        if keyword == "off-site":
            if contains_phrase(normalized_context, "off site"):
                matched_keyword = keyword
                break
        elif contains_phrase(normalized_context, keyword):
            matched_keyword = keyword
            break
    matched_phrase = ""
    for phrase in PHRASES:
        if contains_phrase(normalized_context, phrase):
            matched_phrase = phrase
            break
    if not matched_keyword and not matched_phrase:
        return None
    suspected_noise, noise_reason = noise_match(normalized_context)
    canonical_url = canonicalize_url(url)
    domain = domain_from_url(canonical_url)
    return {
        "id": hashlib.sha1(canonical_url.encode("utf-8")).hexdigest()[:16],
        "url": url,
        "canonical_url": canonical_url,
        "domain": domain,
        "published_at": clean_text(row.get("date")),
        "language": clean_text(row.get("lang")),
        "matched_keyword": matched_keyword,
        "matched_phrase": matched_phrase,
        "matched_context": context[:500],
        "ngram_type": row.get("type"),
        "suspected_noise": suspected_noise,
        "noise_reason": noise_reason,
        "gal_joined": False,
        "country_code": None,
        "country_name": None,
        "country_status": "unresolved",
        "country_evidence": [],
        "source_type": "gdelt_web_news_ngrams",
        "cc_tld_candidate": cctld_candidate(domain),
    }


def iter_jsonl_text(lines: Iterable[str]) -> Iterator[tuple[dict[str, Any] | None, bool]]:
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            yield None, True
            continue
        yield (payload if isinstance(payload, dict) else None), not isinstance(payload, dict)


def scan_webngrams(
    lines: Iterable[str],
    *,
    timestamp: str,
    max_candidates: int,
    smoke_sample_limit: int = 5,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    candidates: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    smoke_samples: list[dict[str, Any]] = []
    seen_smoke_urls: set[str] = set()
    stats = {
        "scanned_row_count": 0,
        "keyword_match_count": 0,
        "duplicate_removed_count": 0,
        "malformed_row_count": 0,
        "early_stopped": 0,
        "join_smoke_sample_size": 0,
        "join_smoke_url_count": 0,
    }
    for row, malformed in iter_jsonl_text(lines):
        if malformed or row is None or not has_required_webngram_fields(row):
            stats["malformed_row_count"] += 1
            continue
        stats["scanned_row_count"] += 1
        canonical_for_smoke = canonicalize_url(row.get("url"))
        if (
            len(smoke_samples) < smoke_sample_limit
            and canonical_for_smoke
            and is_http_url(canonical_for_smoke)
            and canonical_for_smoke not in seen_smoke_urls
        ):
            seen_smoke_urls.add(canonical_for_smoke)
            smoke_samples.append(smoke_sample_from_row(row, timestamp=timestamp))
        candidate = match_webngram_row(row)
        if not candidate:
            continue
        stats["keyword_match_count"] += 1
        canonical_url = candidate["canonical_url"]
        if canonical_url in seen_urls:
            stats["duplicate_removed_count"] += 1
            continue
        seen_urls.add(canonical_url)
        candidate["timestamp"] = timestamp
        candidates.append(candidate)
        if len(candidates) >= max_candidates and len(smoke_samples) >= smoke_sample_limit:
            stats["early_stopped"] = 1
            break
    stats["join_smoke_sample_size"] = len(smoke_samples)
    stats["join_smoke_url_count"] = len(seen_smoke_urls)
    return candidates, smoke_samples, stats


def join_gal(lines: Iterable[str], candidates: list[dict[str, Any]], smoke_samples: list[dict[str, Any]] | None = None) -> dict[str, int]:
    by_url = {candidate["canonical_url"]: candidate for candidate in candidates}
    smoke_samples = smoke_samples or []
    smoke_by_url = {sample["canonical_url"]: sample for sample in smoke_samples}
    joined: set[str] = set()
    smoke_joined: set[str] = set()
    malformed = 0
    scanned = 0
    for row, is_malformed in iter_jsonl_text(lines):
        if is_malformed or row is None:
            malformed += 1
            continue
        scanned += 1
        canonical_url = canonicalize_url(row.get("url"))
        candidate = by_url.get(canonical_url)
        domain = clean_text(row.get("domain")) or domain_from_url(canonical_url)
        if candidate:
            joined.add(canonical_url)
            candidate.update(
                {
                    "title": clean_text(row.get("title")),
                    "domain": domain,
                    "outlet_name": clean_text(row.get("outletName")),
                    "published_at": clean_text(row.get("date")) or candidate.get("published_at", ""),
                    "language": clean_text(row.get("lang")) or candidate.get("language", ""),
                    "author": clean_text(row.get("author")),
                    "image": clean_text(row.get("image")),
                    "description": clean_text(row.get("desc")),
                    "gal_joined": True,
                    "cc_tld_candidate": cctld_candidate(domain),
                }
            )
        smoke = smoke_by_url.get(canonical_url)
        if smoke:
            smoke_joined.add(canonical_url)
            smoke.update(
                {
                    "title": clean_text(row.get("title")),
                    "domain": domain,
                    "outlet_name": clean_text(row.get("outletName")),
                    "gal_joined": True,
                }
            )
    for candidate in candidates:
        candidate.setdefault("title", "")
        candidate.setdefault("outlet_name", "")
        candidate.setdefault("author", "")
        candidate.setdefault("image", "")
        candidate.setdefault("description", "")
    return {
        "gal_scanned_row_count": scanned,
        "gal_join_success_count": len(joined),
        "gal_join_failed_count": len(candidates) - len(joined),
        "join_smoke_gal_joined_count": len(smoke_joined),
        "join_smoke_gal_missing_count": len(smoke_samples) - len(smoke_joined),
        "join_smoke_success_ratio": round(len(smoke_joined) / len(smoke_samples), 4) if smoke_samples else 0.0,
        "gal_malformed_row_count": malformed,
    }


def read_fixture_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


class CountingReader(io.RawIOBase):
    def __init__(self, raw: Any, prefix: bytes = b"") -> None:
        self.raw = raw
        self.prefix = io.BytesIO(prefix)
        self.bytes_read = len(prefix)

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        prefix_chunk = self.prefix.read(size)
        if size != -1:
            remaining_size = max(0, size - len(prefix_chunk))
        else:
            remaining_size = -1
        raw_chunk = self.raw.read(remaining_size) if remaining_size != 0 else b""
        chunk = prefix_chunk + (raw_chunk or b"")
        self.bytes_read += len(raw_chunk or b"")
        return chunk


def open_gzip_jsonl(url: str, *, timeout: float) -> tuple[Iterator[str], dict[str, Any]]:
    response = requests.get(url, stream=True, timeout=timeout, headers={"User-Agent": "ModularHubWebNGramsProbe/0.1"})
    info = {
        "url": url,
        "http_status": int(response.status_code),
        "content_type": response.headers.get("Content-Type", ""),
        "content_length": response.headers.get("Content-Length", ""),
        "downloaded_bytes": 0,
        "gzip_valid": False,
    }
    if response.status_code != 200:
        response.close()
        return iter(()), info
    first = response.raw.read(2)
    info["downloaded_bytes"] = len(first)
    if first != b"\x1f\x8b":
        response.close()
        return iter(()), info
    reader = CountingReader(response.raw, first)
    gz = gzip.GzipFile(fileobj=reader)
    info["gzip_valid"] = True

    def _lines() -> Iterator[str]:
        try:
            for raw_line in gz:
                yield raw_line.decode("utf-8", errors="replace")
        finally:
            info["downloaded_bytes"] = reader.bytes_read
            gz.close()
            response.close()

    return _lines(), info


def classify_source_failure(web_info: dict[str, Any], gal_info: dict[str, Any]) -> tuple[str, str]:
    statuses = [web_info.get("http_status"), gal_info.get("http_status")]
    content_types = [clean_text(web_info.get("content_type")).lower(), clean_text(gal_info.get("content_type")).lower()]
    if any(status == 404 for status in statuses):
        return "timestamp_missing", "source_file_404_for_approved_timestamp"
    if any(status in {403, 429} for status in statuses):
        return "provider_access_limited", "source_access_limited"
    if any(status == 200 and "html" in content_type for status, content_type in zip(statuses, content_types)):
        return "invalid_response", "source_returned_html"
    if any(status == 200 for status in statuses) and (not web_info.get("gzip_valid") or not gal_info.get("gzip_valid")):
        return "parser_or_archive_failure", "gzip_magic_or_archive_validation_failed"
    return "source_file_unavailable", "source_http_or_gzip_failure"


def close_iterable(value: Iterable[str]) -> None:
    close = getattr(value, "close", None)
    if callable(close):
        close()


def build_candidates(timestamp: str, web_lines: Iterable[str], gal_lines: Iterable[str], *, max_candidates: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
    candidates, smoke_samples, web_stats = scan_webngrams(web_lines, timestamp=timestamp, max_candidates=max_candidates)
    gal_stats = join_gal(gal_lines, candidates, smoke_samples)
    stats = {**web_stats, **gal_stats}
    stats["unique_candidate_count"] = len(candidates)
    stats["suspected_noise_count"] = sum(1 for candidate in candidates if candidate.get("suspected_noise"))
    return candidates, stats


def write_artifacts(output_dir: Path, report: dict[str, Any], candidates: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "candidates.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "download_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output_dir / "manual_review.csv").open("w", encoding="utf-8", newline="") as file:
        fieldnames = [
            "id",
            "timestamp",
            "title",
            "url",
            "canonical_url",
            "domain",
            "outlet_name",
            "language",
            "matched_keyword",
            "matched_phrase",
            "suspected_noise",
            "noise_reason",
            "gal_joined",
            "reviewer_decision",
            "reviewer_note",
        ]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for candidate in candidates:
            row = {key: candidate.get(key, "") for key in fieldnames}
            row["reviewer_decision"] = ""
            row["reviewer_note"] = ""
            writer.writerow(row)
    lines = [
        "# GDELT Web NGrams Probe",
        "",
        f"- status: `{report['status']}`",
        f"- timestamp: `{report['timestamp']}`",
        f"- http_request_count: `{report['http_request_count']}`",
        f"- scanned_row_count: `{report['scanned_row_count']}`",
        f"- unique_candidate_count: `{report['unique_candidate_count']}`",
        f"- gal_join_success_count: `{report['gal_join_success_count']}`",
        f"- gal_join_failed_count: `{report['gal_join_failed_count']}`",
        f"- join_smoke_sample_size: `{report.get('join_smoke_sample_size', 0)}`",
        f"- join_smoke_gal_joined_count: `{report.get('join_smoke_gal_joined_count', 0)}`",
        f"- transport_acceptance_passed: `{report.get('transport_acceptance_passed', False)}`",
        f"- keyword_observation: `{report.get('keyword_observation', '')}`",
        f"- suspected_noise_count: `{report['suspected_noise_count']}`",
        f"- 10.10-B2_ready: `{report['10.10-B2_ready']}`",
    ]
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_plan(timestamp: str, *, max_candidates: int) -> dict[str, Any]:
    return {
        "timestamp": validate_timestamp(timestamp),
        "webngrams_url": webngrams_url(timestamp),
        "gal_url": gal_url(timestamp),
        "max_candidates": max_candidates,
        "keywords": KEYWORDS,
        "phrase_rules": PHRASES,
        "network_request_count": 0,
        "planned_webngrams_request_count": 1,
        "planned_gal_request_count": 1,
        "planned_total_request_count": 2,
        "fallback_timestamp_count": 0,
        "public_json_unchanged": True,
        "db_unchanged": True,
        "env_unchanged": True,
        "doc_api_request_count": 0,
        "file_created_count": 0,
    }


def run_fixture(*, max_candidates: int, output_dir: Path) -> dict[str, Any]:
    return run_from_lines(
        timestamp="20260627000000",
        web_lines=read_fixture_lines(FIXTURE_WEBNGRAMS),
        gal_lines=read_fixture_lines(FIXTURE_GAL),
        max_candidates=max_candidates,
        output_dir=output_dir,
        manifest={
            "mode": "fixture",
            "webngrams_source": str(FIXTURE_WEBNGRAMS.relative_to(ROOT)),
            "gal_source": str(FIXTURE_GAL.relative_to(ROOT)),
            "http_request_count": 0,
        },
        download_info={
            "webngrams": {"http_status": None, "downloaded_bytes": 0},
            "gal": {"http_status": None, "downloaded_bytes": 0},
        },
    )


def run_from_lines(
    *,
    timestamp: str,
    web_lines: Iterable[str],
    gal_lines: Iterable[str],
    max_candidates: int,
    output_dir: Path,
    manifest: dict[str, Any],
    download_info: dict[str, Any],
) -> dict[str, Any]:
    before = integrity_snapshot()
    started_at = utc_now_iso()
    started = time.monotonic()
    candidates, stats = build_candidates(timestamp, web_lines, gal_lines, max_candidates=max_candidates)
    after = integrity_snapshot()
    integrity = integrity_unchanged(before, after)
    status = "success" if candidates else "success_no_matches"
    transport_acceptance = stats.get("scanned_row_count", 0) > 0 and stats.get("gal_scanned_row_count", 0) > 0 and stats.get("join_smoke_sample_size", 0) > 0 and stats.get("join_smoke_gal_joined_count", 0) > 0
    report = {
        "checked_at": utc_now_iso(),
        "started_at": started_at,
        "completed_at": utc_now_iso(),
        "status": status,
        "failure_reason": "",
        "timestamp": timestamp,
        "webngrams_url": webngrams_url(timestamp),
        "gal_url": gal_url(timestamp),
        "http_request_count": manifest.get("http_request_count", 0),
        "network_request_count": manifest.get("http_request_count", 0),
        "downloaded_file_count": manifest.get("downloaded_file_count", 0),
        "webngrams_http_status": download_info.get("webngrams", {}).get("http_status"),
        "gal_http_status": download_info.get("gal", {}).get("http_status"),
        "webngrams_content_type": download_info.get("webngrams", {}).get("content_type", ""),
        "gal_content_type": download_info.get("gal", {}).get("content_type", ""),
        "webngrams_gzip_valid": download_info.get("webngrams", {}).get("gzip_valid"),
        "gal_gzip_valid": download_info.get("gal", {}).get("gzip_valid"),
        "webngrams_downloaded_bytes": download_info.get("webngrams", {}).get("downloaded_bytes", 0),
        "gal_downloaded_bytes": download_info.get("gal", {}).get("downloaded_bytes", 0),
        "duration_seconds": round(time.monotonic() - started, 3),
        "doc_api_request_count": 0,
        "country_policy": "unresolved_without_article_validation",
        "transport_acceptance_passed": transport_acceptance,
        "keyword_observation": "matched" if candidates else "empty",
        "10.10-B1_live_accepted": False,
        "10.10-B2_ready": transport_acceptance,
        **stats,
        **integrity,
    }
    write_artifacts(output_dir, report, candidates, manifest)
    return report


def run_live(timestamp: str, *, max_candidates: int, timeout: float, output_dir: Path) -> dict[str, Any]:
    before = integrity_snapshot()
    started_at = utc_now_iso()
    started = time.monotonic()
    web_url = webngrams_url(timestamp)
    article_url = gal_url(timestamp)
    web_lines, web_info = open_gzip_jsonl(web_url, timeout=timeout)
    gal_lines, gal_info = open_gzip_jsonl(article_url, timeout=timeout)
    manifest = {
        "mode": "live",
        "timestamp": timestamp,
        "webngrams_url": web_url,
        "gal_url": article_url,
        "http_request_count": 2,
        "downloaded_file_count": int(web_info.get("http_status") == 200) + int(gal_info.get("http_status") == 200),
        "webngrams": web_info,
        "gal": gal_info,
    }
    if web_info.get("http_status") != 200 or gal_info.get("http_status") != 200 or not web_info.get("gzip_valid") or not gal_info.get("gzip_valid"):
        status, failure_reason = classify_source_failure(web_info, gal_info)
        close_iterable(web_lines)
        close_iterable(gal_lines)
        after = integrity_snapshot()
        report = {
            "checked_at": utc_now_iso(),
            "started_at": started_at,
            "completed_at": utc_now_iso(),
            "status": status,
            "failure_reason": failure_reason,
            "timestamp": timestamp,
            "webngrams_url": web_url,
            "gal_url": article_url,
            "http_request_count": 2,
            "network_request_count": 2,
            "downloaded_file_count": manifest["downloaded_file_count"],
            "webngrams_http_status": web_info.get("http_status"),
            "gal_http_status": gal_info.get("http_status"),
            "webngrams_content_type": web_info.get("content_type", ""),
            "gal_content_type": gal_info.get("content_type", ""),
            "webngrams_content_length": web_info.get("content_length", ""),
            "gal_content_length": gal_info.get("content_length", ""),
            "webngrams_gzip_valid": web_info.get("gzip_valid", False),
            "gal_gzip_valid": gal_info.get("gzip_valid", False),
            "webngrams_downloaded_bytes": web_info.get("downloaded_bytes", 0),
            "gal_downloaded_bytes": gal_info.get("downloaded_bytes", 0),
            "scanned_row_count": 0,
            "keyword_match_count": 0,
            "unique_candidate_count": 0,
            "duplicate_removed_count": 0,
            "gal_join_success_count": 0,
            "gal_join_failed_count": 0,
            "gal_scanned_row_count": 0,
            "join_smoke_sample_size": 0,
            "join_smoke_url_count": 0,
            "join_smoke_gal_joined_count": 0,
            "join_smoke_gal_missing_count": 0,
            "join_smoke_success_ratio": 0.0,
            "suspected_noise_count": 0,
            "malformed_row_count": 0,
            "duration_seconds": round(time.monotonic() - started, 3),
            "doc_api_request_count": 0,
            "transport_acceptance_passed": False,
            "keyword_observation": "failed",
            "10.10-B1_live_accepted": False,
            "10.10-B2_ready": False,
            **integrity_unchanged(before, after),
        }
        write_artifacts(output_dir, report, [], manifest)
        return report
    try:
        candidates, smoke_samples, web_stats = scan_webngrams(web_lines, timestamp=timestamp, max_candidates=max_candidates)
        close_iterable(web_lines)
        gal_stats = join_gal(gal_lines, candidates, smoke_samples)
        close_iterable(gal_lines)
    except (OSError, EOFError, gzip.BadGzipFile, UnicodeError) as exc:
        close_iterable(web_lines)
        close_iterable(gal_lines)
        after = integrity_snapshot()
        report = {
            "checked_at": utc_now_iso(),
            "started_at": started_at,
            "completed_at": utc_now_iso(),
            "status": "parser_or_archive_failure",
            "failure_reason": type(exc).__name__,
            "timestamp": timestamp,
            "webngrams_url": web_url,
            "gal_url": article_url,
            "http_request_count": 2,
            "network_request_count": 2,
            "downloaded_file_count": manifest["downloaded_file_count"],
            "webngrams_http_status": web_info.get("http_status"),
            "gal_http_status": gal_info.get("http_status"),
            "webngrams_content_type": web_info.get("content_type", ""),
            "gal_content_type": gal_info.get("content_type", ""),
            "webngrams_content_length": web_info.get("content_length", ""),
            "gal_content_length": gal_info.get("content_length", ""),
            "webngrams_gzip_valid": web_info.get("gzip_valid", False),
            "gal_gzip_valid": gal_info.get("gzip_valid", False),
            "webngrams_downloaded_bytes": web_info.get("downloaded_bytes", 0),
            "gal_downloaded_bytes": gal_info.get("downloaded_bytes", 0),
            "scanned_row_count": 0,
            "keyword_match_count": 0,
            "unique_candidate_count": 0,
            "duplicate_removed_count": 0,
            "gal_join_success_count": 0,
            "gal_join_failed_count": 0,
            "gal_scanned_row_count": 0,
            "join_smoke_sample_size": 0,
            "join_smoke_url_count": 0,
            "join_smoke_gal_joined_count": 0,
            "join_smoke_gal_missing_count": 0,
            "join_smoke_success_ratio": 0.0,
            "suspected_noise_count": 0,
            "malformed_row_count": 0,
            "duration_seconds": round(time.monotonic() - started, 3),
            "doc_api_request_count": 0,
            "transport_acceptance_passed": False,
            "keyword_observation": "failed",
            "10.10-B1_live_accepted": False,
            "10.10-B2_ready": False,
            **integrity_unchanged(before, after),
        }
        write_artifacts(output_dir, report, [], manifest)
        return report
    stats = {**web_stats, **gal_stats}
    stats["unique_candidate_count"] = len(candidates)
    stats["suspected_noise_count"] = sum(1 for candidate in candidates if candidate.get("suspected_noise"))
    transport_acceptance = (
        manifest["http_request_count"] == 2
        and web_info.get("http_status") == 200
        and gal_info.get("http_status") == 200
        and web_info.get("gzip_valid") is True
        and gal_info.get("gzip_valid") is True
        and stats.get("scanned_row_count", 0) > 0
        and stats.get("gal_scanned_row_count", 0) > 0
        and stats.get("join_smoke_sample_size", 0) > 0
        and stats.get("join_smoke_gal_joined_count", 0) > 0
    )
    if stats.get("scanned_row_count", 0) == 0 or stats.get("gal_scanned_row_count", 0) == 0:
        status = "parser_or_archive_failure"
        failure_reason = "jsonl_scan_returned_no_rows"
    elif stats.get("join_smoke_sample_size", 0) == 0 or stats.get("join_smoke_gal_joined_count", 0) == 0:
        status = "gal_join_failure"
        failure_reason = "smoke_sample_gal_join_zero"
    else:
        status = "success" if candidates else "success_no_matches"
        failure_reason = ""
    after = integrity_snapshot()
    report = {
        "checked_at": utc_now_iso(),
        "started_at": started_at,
        "completed_at": utc_now_iso(),
        "status": status,
        "failure_reason": failure_reason,
        "timestamp": timestamp,
        "webngrams_url": web_url,
        "gal_url": article_url,
        "http_request_count": 2,
        "network_request_count": 2,
        "downloaded_file_count": manifest["downloaded_file_count"],
        "webngrams_http_status": web_info.get("http_status"),
        "gal_http_status": gal_info.get("http_status"),
        "webngrams_content_type": web_info.get("content_type", ""),
        "gal_content_type": gal_info.get("content_type", ""),
        "webngrams_content_length": web_info.get("content_length", ""),
        "gal_content_length": gal_info.get("content_length", ""),
        "webngrams_gzip_valid": web_info.get("gzip_valid", False),
        "gal_gzip_valid": gal_info.get("gzip_valid", False),
        "webngrams_downloaded_bytes": web_info.get("downloaded_bytes", 0),
        "gal_downloaded_bytes": gal_info.get("downloaded_bytes", 0),
        "duration_seconds": round(time.monotonic() - started, 3),
        "doc_api_request_count": 0,
        "country_policy": "unresolved_without_article_validation",
        "transport_acceptance_passed": transport_acceptance,
        "keyword_observation": "matched" if candidates else "empty",
        "10.10-B1_live_accepted": transport_acceptance,
        "10.10-B2_ready": transport_acceptance,
        **stats,
        **integrity_unchanged(before, after),
    }
    write_artifacts(output_dir, report, candidates, manifest)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe GDELT Web News NGrams and GAL for modular news candidates.")
    parser.add_argument("--timestamp", default="")
    parser.add_argument("--print-plan", action="store_true")
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--max-candidates", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    if args.max_candidates <= 0 or args.max_candidates > 100:
        parser.error("--max-candidates must be between 1 and 100")
    if args.print_plan:
        if not args.timestamp:
            parser.error("--timestamp is required for --print-plan")
        print(json.dumps(print_plan(args.timestamp, max_candidates=args.max_candidates), ensure_ascii=False, indent=2))
        return 0
    if args.fixture:
        report = run_fixture(max_candidates=args.max_candidates, output_dir=args.output_dir)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if not args.timestamp:
        parser.error("--timestamp is required for live probe")
    report = run_live(validate_timestamp(args.timestamp), max_candidates=args.max_candidates, timeout=args.timeout, output_dir=args.output_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("10.10-B1_live_accepted") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
