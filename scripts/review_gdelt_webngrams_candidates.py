from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "global_news_webngrams_review"
REVIEW_FIXTURE = ROOT / "tests" / "fixtures" / "gdelt_webngrams_review_candidates.json"
SCHEMA_VERSION = 1
CLASSIFIER_VERSION = 1
COUNTRY_RESOLVER_VERSION = 1
DUPLICATE_RESOLVER_VERSION = 1
PUBLIC_DATA_PATHS = [
    ROOT / "frontend" / "public" / "data" / "business.json",
    ROOT / "frontend" / "public" / "data" / "news.json",
    ROOT / "frontend" / "public" / "data" / "meta.json",
]
CHECKPOINT_PATH = ROOT / "artifacts" / "global_news_probe" / "checkpoint.json"

STRONG_POSITIVE_KEYWORDS = [
    "modular construction",
    "modular building",
    "modular housing",
    "modular home",
    "prefabricated building",
    "prefab construction",
    "prefabricated construction",
    "offsite construction",
    "off-site construction",
    "volumetric modular",
    "modular school",
    "modular classroom",
    "modular hospital",
    "modular hotel",
    "modular data center",
    "modular dormitory",
    "modular accommodation",
    "modular factory",
    "modular office building",
]
SUPPORTING_POSITIVE_KEYWORDS = [
    "steel modular",
    "timber modular",
    "concrete modular",
    "factory-built",
    "factory manufactured building",
    "manufactured building",
    "module manufacturing",
    "module assembly",
    "prefabrication",
    "mmc",
    "modern methods of construction",
    "industrialized construction",
    "panelized construction",
]
STRONG_EXCLUSION_KEYWORDS = [
    "software module",
    "software modularity",
    "modular synthesizer",
    "modular smartphone",
    "modular phone",
    "modular furniture",
    "modular sofa",
    "modular kitchen",
    "modular arithmetic",
    "mathematical modular",
    "nuclear reactor module",
    "gaming module",
    "electronic module",
    "battery module",
    "camera module",
    "memory module",
    "python module",
    "javascript module",
]
STRONG_POSITIVE_SCORE = 70
SUPPORTING_POSITIVE_SCORE = 18
WEAK_POSITIVE_SCORE = 40
CONSTRUCTION_CONTEXT_WEIGHTS = {
    "construction": 10,
    "site": 9,
    "building": 10,
    "housing": 10,
    "home": 5,
    "school": 10,
    "classroom": 5,
    "hospital": 10,
    "hotel": 10,
    "dormitory": 5,
    "apartment": 5,
    "factory": 5,
    "office": 5,
    "accommodation": 5,
    "developer": 5,
    "council": 5,
}
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "ref",
    "source",
}
COUNTRY_NAMES = {
    "GB": "United Kingdom",
    "DE": "Germany",
    "PL": "Poland",
    "AU": "Australia",
    "US": "United States",
    "CN": "China",
    "SG": "Singapore",
    "JP": "Japan",
}
COUNTRY_ALIASES = {
    "uk": "GB",
    "gb": "GB",
    "great britain": "GB",
    "united kingdom": "GB",
    "germany": "DE",
    "de": "DE",
    "poland": "PL",
    "pl": "PL",
    "australia": "AU",
    "au": "AU",
    "united states": "US",
    "unitedstates": "US",
    "usa": "US",
    "us": "US",
    "china": "CN",
    "cn": "CN",
    "singapore": "SG",
    "sg": "SG",
    "japan": "JP",
    "jp": "JP",
}
TRUSTED_PUBLISHER_COUNTRIES = {
    "bbc.co.uk": "GB",
    "theguardian.com": "GB",
    "abc.net.au": "AU",
    "smh.com.au": "AU",
    "japantimes.co.jp": "JP",
    "straitstimes.com": "SG",
}
COUNTRY_DOMAIN_RULES = [
    (".co.uk", "GB", {"en"}),
    (".com.au", "AU", {"en"}),
    (".de", "DE", {"de"}),
    (".pl", "PL", {"pl"}),
    (".cn", "CN", {"zh", "zh-cn", "cn"}),
    (".sg", "SG", {"en"}),
    (".jp", "JP", {"ja", "jp"}),
]
EVIDENCE_PRIORITY = {
    "gal_source_country": 1,
    "gal_publication_country": 2,
    "gal_location_country": 3,
    "trusted_publisher_domain": 4,
    "domain_language_combo": 5,
    "article_context_country": 5,
    "input_country_evidence": 6,
}
CLASSIFICATION_ORDER = {"publish_candidate": 0, "review_required": 1, "irrelevant": 2, "malformed": 3}
VOLATILE_HASH_FIELDS = {
    "checked_at",
    "generated_at",
    "normalized_result_hash",
    "output_file_hashes",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_text(value: Any) -> str:
    text = clean_text(value).lower()
    text = text.replace("off-site", "off site")
    text = text.replace("factory-built", "factory built")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def contains_phrase(normalized_context: str, phrase: str) -> bool:
    needle = normalize_text(phrase)
    return bool(needle and f" {needle} " in f" {normalized_context} ")


def file_hash(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def normalize_for_result_hash(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: normalize_for_result_hash(item)
            for key, item in sorted(value.items())
            if key not in VOLATILE_HASH_FIELDS
        }
    if isinstance(value, list):
        return [normalize_for_result_hash(item) for item in value]
    return value


def safe_path_label(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return path.name


def probe_run_id(report: dict[str, Any] | None, source: str, source_hash: str | None) -> str:
    if report:
        for key in ("run_id", "probe_run_id"):
            value = clean_text(report.get(key))
            if value:
                return value
        timestamp = clean_text(report.get("timestamp"))
        if timestamp:
            return f"probe-{timestamp}"
    if source == "fixture":
        return "probe-fixture"
    return f"probe-artifact-{(source_hash or stable_hash(source))[:12]}"


def review_run_id(probe_id: str, source_hash: str | None) -> str:
    return f"review-{probe_id}-{(source_hash or stable_hash(probe_id))[:12]}"


def fallback_fingerprint(label: str, payload: Any) -> str:
    return stable_hash({"label": label, "payload": payload})


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


def parse_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"input file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"input file is not valid JSON: {path}: {exc}") from exc


def contains_unsafe_local_reference(value: Any) -> bool:
    if isinstance(value, dict):
        return any(contains_unsafe_local_reference(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_unsafe_local_reference(item) for item in value)
    text = clean_text(value)
    if not text:
        return False
    return bool(re.search(r"(?i)([a-z]:\\users\\|/home/[^/]+/|/users/[^/]+/)", text))


def normalize_url(raw_url: Any) -> dict[str, Any]:
    original = clean_text(raw_url)
    if not original:
        return {
            "original_url": "",
            "canonical_url": "",
            "normalized_url": "",
            "domain": "",
            "mobile_url": "",
            "url_valid": False,
            "url_validation_reason": "missing_url",
        }
    try:
        parts = urlsplit(original)
    except ValueError:
        return {
            "original_url": original,
            "canonical_url": original,
            "normalized_url": original,
            "domain": "",
            "mobile_url": "",
            "url_valid": False,
            "url_validation_reason": "url_parse_error",
        }
    if not parts.scheme:
        return {
            "original_url": original,
            "canonical_url": original,
            "normalized_url": original,
            "domain": "",
            "mobile_url": "",
            "url_valid": False,
            "url_validation_reason": "missing_scheme",
        }
    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").lower()
    if scheme not in {"http", "https"}:
        return {
            "original_url": original,
            "canonical_url": original,
            "normalized_url": original,
            "domain": "",
            "mobile_url": "",
            "url_valid": False,
            "url_validation_reason": "unsupported_scheme",
        }
    if not hostname:
        return {
            "original_url": original,
            "canonical_url": original,
            "normalized_url": original,
            "domain": "",
            "mobile_url": "",
            "url_valid": False,
            "url_validation_reason": "missing_hostname",
        }
    port = parts.port
    include_port = port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443))
    netloc = f"{hostname}:{port}" if include_port else hostname
    path = quote(unquote(parts.path or "/"), safe="/:@")
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    query_pairs = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in TRACKING_PARAMS or key.lower().startswith("utm_"):
            continue
        query_pairs.append((key, value))
    query = urlencode(sorted(query_pairs, key=lambda item: (item[0].lower(), item[1])), doseq=True)
    normalized = urlunsplit((scheme, netloc, path, query, ""))
    mobile_url = original if hostname.startswith("m.") or hostname.startswith("mobile.") else ""
    return {
        "original_url": original,
        "canonical_url": normalized,
        "normalized_url": normalized,
        "domain": netloc,
        "mobile_url": mobile_url,
        "url_valid": True,
        "url_validation_reason": "ok",
    }


def parse_date(value: Any) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    for fmt in ("%Y%m%d%H%M%S", "%Y%m%d%H%M", "%Y%m%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def make_item_id(candidate: dict[str, Any], normalized_url: str) -> str:
    existing = clean_text(candidate.get("item_id") or candidate.get("id") or candidate.get("article_identifier"))
    if existing:
        return existing
    digest = hashlib.sha1((normalized_url or json.dumps(candidate, sort_keys=True, ensure_ascii=False)).encode("utf-8")).hexdigest()
    return f"gdelt_webngrams:{digest[:16]}"


def article_identifier(candidate: dict[str, Any], item_id: str) -> str:
    return clean_text(candidate.get("article_identifier") or candidate.get("gal_article_id") or candidate.get("id") or item_id)


def evaluate_relevance(candidate: dict[str, Any], normalized_title: str) -> dict[str, Any]:
    url_text = " ".join(
        [
            clean_text(candidate.get("original_url") or candidate.get("url")),
            clean_text(candidate.get("canonical_url")),
            clean_text(candidate.get("domain")),
        ]
    )
    context = " ".join(
        clean_text(candidate.get(key))
        for key in ("title", "description", "matched_context", "matched_keyword", "matched_phrase", "outlet_name", "outletName")
    )
    normalized_context = normalize_text(f"{context} {url_text}")
    positives: list[str] = []
    exclusions: list[str] = []
    score = 0
    keyword_positive_found = False
    for term in STRONG_POSITIVE_KEYWORDS:
        if contains_phrase(normalized_context, term):
            positives.append(f"strong_positive:{term}")
            score += STRONG_POSITIVE_SCORE
            keyword_positive_found = True
    for term in SUPPORTING_POSITIVE_KEYWORDS:
        if contains_phrase(normalized_context, term):
            positives.append(f"supporting_positive:{term}")
            score += SUPPORTING_POSITIVE_SCORE
            keyword_positive_found = True
    for term, weight in CONSTRUCTION_CONTEXT_WEIGHTS.items():
        if contains_phrase(normalized_context, term):
            positives.append(f"construction_context:{term}")
            score += weight
    for term in STRONG_EXCLUSION_KEYWORDS:
        if contains_phrase(normalized_context, term):
            exclusions.append(f"strong_exclusion:{term}")
            score -= 80
    if candidate.get("suspected_noise") and candidate.get("noise_reason"):
        exclusions.append(f"probe_noise:{candidate.get('noise_reason')}")
        score -= 20
    if not keyword_positive_found and contains_phrase(normalized_context, "modular"):
        positives.append("weak_positive:modular")
        score += WEAK_POSITIVE_SCORE
    if not keyword_positive_found and contains_phrase(normalized_context, "prefab"):
        positives.append("weak_positive:prefab")
        score += WEAK_POSITIVE_SCORE
    score = max(0, min(100, score))
    if (
        not clean_text(candidate.get("title"))
        or not clean_text(candidate.get("original_url") or candidate.get("url"))
        or candidate.get("url_valid") is False
    ):
        return {
            "relevance_score": 0,
            "classification": "malformed",
            "positive_reason_codes": positives,
            "exclusion_reason_codes": exclusions or ["missing_required_title_or_url_or_invalid_url"],
            "classification_reason": "missing_required_title_or_url_or_invalid_url",
        }
    if score >= 80 and not exclusions:
        classification = "publish_candidate"
    elif score >= 50:
        classification = "review_required"
    elif score <= 49:
        classification = "irrelevant"
    else:
        classification = "review_required"
    if exclusions and score < 80:
        classification = "irrelevant"
    return {
        "relevance_score": score,
        "classification": classification,
        "positive_reason_codes": positives,
        "exclusion_reason_codes": exclusions,
        "classification_reason": f"score_{score}",
    }


def normalize_country_code(value: Any) -> str:
    text = clean_text(value).lower()
    return COUNTRY_ALIASES.get(text, "")


def country_context_mentions(candidate: dict[str, Any]) -> list[str]:
    text = normalize_text(
        " ".join(
            clean_text(candidate.get(key))
            for key in ("title", "description", "matched_context", "country_context")
        )
    )
    mentions: list[str] = []
    for alias, code in COUNTRY_ALIASES.items():
        if len(alias) <= 2:
            continue
        if contains_phrase(text, alias):
            mentions.append(code)
    return sorted(set(mentions))


def country_evidence(candidate: dict[str, Any], domain: str, language: str) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    explicit_fields = [
        ("gal_source_country", candidate.get("gal_source_country") or candidate.get("source_country_code") or candidate.get("sourceCountry") or candidate.get("sourcecountry")),
        ("gal_publication_country", candidate.get("publication_country") or candidate.get("publicationCountry")),
        ("gal_location_country", candidate.get("location_country") or candidate.get("locationCountry")),
    ]
    for source, value in explicit_fields:
        code = normalize_country_code(value)
        if code:
            evidence.append({"source": source, "country_code": code, "confidence": 0.95})
    for value in candidate.get("country_evidence") or []:
        if isinstance(value, dict):
            code = normalize_country_code(value.get("country_code") or value.get("code") or value.get("country"))
            if code:
                evidence.append({"source": clean_text(value.get("source")) or "input_country_evidence", "country_code": code, "confidence": float(value.get("confidence") or 0.75)})
    domain_l = domain.lower()
    if domain_l in TRUSTED_PUBLISHER_COUNTRIES:
        evidence.append({"source": "trusted_publisher_domain", "country_code": TRUSTED_PUBLISHER_COUNTRIES[domain_l], "confidence": 0.85})
    lang = clean_text(language).lower()
    for suffix, code, languages in COUNTRY_DOMAIN_RULES:
        if domain_l.endswith(suffix) and lang in languages:
            evidence.append({"source": "domain_language_combo", "country_code": code, "confidence": 0.7})
    for code in country_context_mentions(candidate):
        evidence.append({"source": "article_context_country", "country_code": code, "confidence": 0.7})
    return sorted(
        evidence,
        key=lambda item: (
            EVIDENCE_PRIORITY.get(item["source"], 99),
            item["source"],
            item["country_code"],
            item["confidence"],
        ),
    )


def resolve_country(candidate: dict[str, Any], domain: str, language: str) -> dict[str, Any]:
    evidence = country_evidence(candidate, domain, language)
    explicit = [item for item in evidence if item["source"].startswith("gal_")]
    explicit_codes = sorted({item["country_code"] for item in explicit})
    if len(explicit_codes) > 1:
        return {
            "country_code": None,
            "country_name": None,
            "country_confidence": 0.0,
            "country_evidence": evidence,
            "conflicting_evidence": evidence,
            "country_resolution_status": "conflicting",
            "resolution_status": "conflicting",
            "confidence": 0.0,
            "evidence": evidence,
        }
    if len(explicit_codes) == 1:
        code = explicit_codes[0]
        return {
            "country_code": code,
            "country_name": COUNTRY_NAMES[code],
            "country_confidence": 0.95,
            "country_evidence": evidence,
            "conflicting_evidence": [],
            "country_resolution_status": "confirmed",
            "resolution_status": "confirmed",
            "confidence": 0.95,
            "evidence": evidence,
        }
    inferred_codes = sorted({item["country_code"] for item in evidence})
    if len(inferred_codes) > 1:
        return {
            "country_code": None,
            "country_name": None,
            "country_confidence": 0.0,
            "country_evidence": evidence,
            "conflicting_evidence": evidence,
            "country_resolution_status": "conflicting",
            "resolution_status": "conflicting",
            "confidence": 0.0,
            "evidence": evidence,
        }
    if len(inferred_codes) == 1 and len(evidence) >= 2:
        code = inferred_codes[0]
        confidence = max(item["confidence"] for item in evidence if item["country_code"] == code)
        return {
            "country_code": code,
            "country_name": COUNTRY_NAMES[code],
            "country_confidence": confidence,
            "country_evidence": evidence,
            "conflicting_evidence": [],
            "country_resolution_status": "inferred",
            "resolution_status": "inferred",
            "confidence": confidence,
            "evidence": evidence,
        }
    return {
        "country_code": None,
        "country_name": None,
        "country_confidence": 0.0,
        "country_evidence": evidence,
        "conflicting_evidence": [],
        "country_resolution_status": "unresolved",
        "resolution_status": "unresolved",
        "confidence": 0.0,
        "evidence": evidence,
    }


def detect_language(title: str) -> tuple[str, float]:
    if re.search(r"[\u3040-\u30ff]", title):
        return "ja", 0.75
    if re.search(r"[\u4e00-\u9fff]", title):
        return "zh", 0.65
    if re.search(r"[A-Za-z]", title):
        return "en", 0.55
    return "", 0.0


def resolve_language(candidate: dict[str, Any], title: str) -> dict[str, Any]:
    gdelt_language = clean_text(candidate.get("language") or candidate.get("lang"))
    gal_language = clean_text(candidate.get("gal_language") or candidate.get("gal_lang") or candidate.get("article_language"))
    detected, confidence = detect_language(title)
    present = {value.lower() for value in (gdelt_language, gal_language, detected) if value}
    return {
        "gdelt_language": gdelt_language,
        "gal_language": gal_language,
        "detected_language": detected,
        "language_confidence": confidence,
        "conflicting_language": len(present) > 1,
        "language": gdelt_language or gal_language or detected,
    }


def to_review_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    url_info = normalize_url(candidate.get("original_url") or candidate.get("url") or candidate.get("canonical_url"))
    canonical_info = normalize_url(candidate.get("canonical_url") or url_info["normalized_url"])
    title = clean_text(candidate.get("title"))
    normalized_title = normalize_text(title)
    item_id = make_item_id(candidate, url_info["normalized_url"])
    article_id = article_identifier(candidate, item_id)
    language = resolve_language(candidate, title)
    country = resolve_country(candidate, url_info["domain"], language["language"])
    relevance = evaluate_relevance({**candidate, **url_info, "title": title}, normalized_title)
    gal_joined = bool(candidate.get("gal_joined"))
    if gal_joined:
        gal_join_status = "joined"
        gal_join_failure_reason = ""
    elif not article_id:
        gal_join_status = "failed"
        gal_join_failure_reason = "identifier_missing"
    elif not title:
        gal_join_status = "failed"
        gal_join_failure_reason = "metadata_missing"
    else:
        gal_join_status = "failed"
        gal_join_failure_reason = "unknown"
    reviewed = {
        "item_id": item_id,
        "title": title,
        "normalized_title": normalized_title,
        "original_url": url_info["original_url"],
        "canonical_url": canonical_info["normalized_url"] or url_info["canonical_url"],
        "normalized_url": url_info["normalized_url"],
        "mobile_url": url_info["mobile_url"],
        "url_valid": bool(url_info.get("url_valid")),
        "url_validation_reason": clean_text(url_info.get("url_validation_reason")),
        "domain": canonical_info["domain"] or url_info["domain"] or clean_text(candidate.get("domain")),
        "published_at": clean_text(candidate.get("published_at") or candidate.get("date")),
        "seen_at": clean_text(candidate.get("seen_at") or candidate.get("timestamp")),
        "language": language["language"],
        "gdelt_language": language["gdelt_language"],
        "gal_language": language["gal_language"],
        "detected_language": language["detected_language"],
        "language_confidence": language["language_confidence"],
        "conflicting_language": language["conflicting_language"],
        "source_dataset": clean_text(candidate.get("source_dataset") or candidate.get("source_type") or "gdelt_web_news_ngrams"),
        "article_identifier": article_id,
        "gal_join_status": gal_join_status,
        "gal_join_failure_reason": gal_join_failure_reason,
        "review_status": "pending_manual_review",
        "raw_candidate": candidate,
        **relevance,
        **country,
    }
    return reviewed


class UnionFind:
    def __init__(self, values: Iterable[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        l_root = self.find(left)
        r_root = self.find(right)
        if l_root != r_root:
            self.parent[r_root] = l_root


def date_close(left: str, right: str, days: int = 2) -> bool:
    l_date = parse_date(left)
    r_date = parse_date(right)
    if not l_date or not r_date:
        return False
    return abs((l_date.date() - r_date.date()).days) <= days


def representative_rank(candidate: dict[str, Any]) -> tuple[int, int, int, int, int, str]:
    return (
        -1 if candidate.get("gal_join_status") == "joined" else 0,
        -1 if candidate.get("canonical_url") else 0,
        -1 if clean_text(candidate.get("original_url")).startswith(("http://", "https://")) else 0,
        -1 if parse_date(candidate.get("published_at")) else 0,
        -len(clean_text(candidate.get("title"))),
        clean_text(candidate.get("item_id")),
    )


def candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, str, str, str, str]:
    parsed = parse_date(candidate.get("published_at"))
    date_key = parsed.strftime("%Y%m%d%H%M%S") if parsed else "99999999999999"
    return (
        CLASSIFICATION_ORDER.get(clean_text(candidate.get("classification")), 99),
        date_key,
        clean_text(candidate.get("normalized_url")),
        clean_text(candidate.get("normalized_title")),
        clean_text(candidate.get("item_id")),
    )


def duplicate_group_id(member_ids: list[str]) -> str:
    joined = "|".join(sorted(member_ids))
    return f"dup-{hashlib.sha256(joined.encode('utf-8')).hexdigest()[:12]}"


def build_duplicate_groups(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if not candidates:
        return [], {}
    uf = UnionFind(candidate["item_id"] for candidate in candidates)
    reason_by_pair: dict[tuple[str, str], str] = {}

    def union_for(key_name: str, key_func: Any, reason: str) -> None:
        buckets: dict[str, list[str]] = defaultdict(list)
        for candidate in candidates:
            key = clean_text(key_func(candidate))
            if key:
                buckets[key].append(candidate["item_id"])
        for members in buckets.values():
            if len(members) > 1:
                first = members[0]
                for other in members[1:]:
                    uf.union(first, other)
                    reason_by_pair.setdefault((first, other), reason)

    union_for("article_identifier", lambda item: item.get("article_identifier"), "same_gal_article_identifier")
    union_for("canonical_url", lambda item: item.get("canonical_url"), "same_canonical_url")
    union_for("normalized_url", lambda item: item.get("normalized_url"), "same_normalized_url")
    union_for("domain_title", lambda item: f"{item.get('domain')}|{item.get('normalized_title')}", "same_domain_normalized_title")
    for index, left in enumerate(candidates):
        for right in candidates[index + 1 :]:
            if left.get("domain") != right.get("domain"):
                continue
            if not date_close(left.get("published_at"), right.get("published_at")):
                continue
            similarity = SequenceMatcher(None, clean_text(left.get("normalized_title")), clean_text(right.get("normalized_title"))).ratio()
            if similarity >= 0.92:
                uf.union(left["item_id"], right["item_id"])
                reason_by_pair.setdefault((left["item_id"], right["item_id"]), "similar_title_close_date")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        groups[uf.find(candidate["item_id"])].append(candidate)
    duplicate_groups = []
    item_to_group: dict[str, str] = {}
    for root in sorted(groups):
        members = sorted(groups[root], key=lambda item: item["item_id"])
        if len(members) < 2:
            continue
        representative = min(members, key=representative_rank)
        reason = "duplicate"
        member_ids = sorted(member["item_id"] for member in members)
        for (left, right), pair_reason in reason_by_pair.items():
            if left in member_ids and right in member_ids:
                reason = pair_reason
                break
        group_id = duplicate_group_id(member_ids)
        for member in members:
            item_to_group[member["item_id"]] = group_id
            member["duplicate_group_id"] = group_id
            member["duplicate_reason"] = reason
            member["representative_item_id"] = representative["item_id"]
        duplicate_groups.append(
            {
                "schema_version": SCHEMA_VERSION,
                "duplicate_group_id": group_id,
                "duplicate_reason": reason,
                "representative_item_id": representative["item_id"],
                "member_item_ids": member_ids,
            }
        )
    return sorted(duplicate_groups, key=lambda group: group["duplicate_group_id"]), item_to_group


def load_fixture_candidates() -> tuple[list[dict[str, Any]], dict[str, Any] | None, str]:
    if REVIEW_FIXTURE.exists():
        payload = parse_json_file(REVIEW_FIXTURE)
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise ValueError(f"review fixture must be a JSON array of objects: {REVIEW_FIXTURE}")
        return payload, None, "fixture"
    from scripts.probe_gdelt_webngrams import FIXTURE_GAL, FIXTURE_WEBNGRAMS, join_gal, read_fixture_lines, scan_webngrams

    candidates, smoke_samples, _stats = scan_webngrams(read_fixture_lines(FIXTURE_WEBNGRAMS), timestamp="20260627000000", max_candidates=20)
    join_gal(read_fixture_lines(FIXTURE_GAL), candidates, smoke_samples)
    return candidates, None, "fixture"


def load_input_candidates(input_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any] | None, str]:
    candidates, report, _source_mode = load_candidate_artifact(input_path, input_path.with_name("report.json"), source_mode="artifact")
    return candidates, report, str(input_path)


def load_candidate_artifact(
    candidates_path: Path,
    report_path: Path | None,
    *,
    source_mode: str,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, str]:
    payload = parse_json_file(candidates_path)
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        candidates = payload["items"]
    elif isinstance(payload, list):
        candidates = payload
    else:
        raise ValueError("candidate input must be a JSON array or an object with an items array")
    if not all(isinstance(item, dict) for item in candidates):
        raise ValueError("candidate input contains non-object entries")
    report = parse_json_file(report_path) if report_path and report_path.exists() else None
    if source_mode == "live":
        validate_live_inputs(candidates, report, candidates_path, report_path)
    return candidates, report, str(candidates_path)


def validate_live_inputs(
    candidates: list[dict[str, Any]],
    report: dict[str, Any] | None,
    candidates_path: Path,
    report_path: Path | None,
) -> None:
    if report is None:
        raise ValueError("--source-mode live requires --input-probe-report")
    if not isinstance(report, dict):
        raise ValueError("live probe report must be a JSON object")
    required_report_fields = ["timestamp", "transport_acceptance_passed", "http_request_count", "doc_api_request_count"]
    missing = [field for field in required_report_fields if field not in report]
    if missing:
        raise ValueError(f"live probe report is missing required fields: {', '.join(missing)}")
    if not clean_text(report.get("timestamp")):
        raise ValueError("live probe report timestamp is empty")
    if int(report.get("doc_api_request_count") or 0) != 0:
        raise ValueError("live probe report indicates DOC API requests")
    if int(report.get("network_request_count") or report.get("http_request_count") or 0) > 2:
        raise ValueError("live probe report exceeded the two-request limit")
    if "fixture" in clean_text(report.get("mode")).lower() or clean_text(report.get("input_mode")).lower() == "fixture":
        raise ValueError("live review input must not be a fixture report")
    if contains_unsafe_local_reference(report) or contains_unsafe_local_reference(candidates):
        raise ValueError("live review input contains a local absolute path")
    if candidates_path == report_path:
        raise ValueError("candidate and probe report inputs must be separate files")


def summarize_live_acceptance(report: dict[str, Any] | None, source: str) -> dict[str, Any]:
    if report is None:
        return {
            "live_acceptance_status": "fixture_only" if source == "fixture" else "pending",
            "live_acceptance_pending": True,
            "transport_acceptance_passed": False,
            "10.10-B1_live_accepted": False,
            "operational_publish_allowed": False,
            "live_source": source,
        }
    accepted = bool(report.get("transport_acceptance_passed")) and bool(report.get("10.10-B1_live_accepted"))
    unchanged = all(report.get(key) is True for key in ("public_json_unchanged", "db_unchanged", "env_unchanged"))
    request_count_ok = int(report.get("actual_request_count") or report.get("network_request_count") or report.get("http_request_count") or 0) <= 2
    return {
        "live_acceptance_status": "accepted" if accepted and unchanged and request_count_ok else "failed",
        "live_acceptance_pending": False,
        "transport_acceptance_passed": bool(report.get("transport_acceptance_passed")),
        "10.10-B1_live_accepted": bool(report.get("10.10-B1_live_accepted")),
        "operational_publish_allowed": False,
        "live_source": source,
        "live_report_status": report.get("status"),
        "live_request_count": int(report.get("actual_request_count") or report.get("network_request_count") or report.get("http_request_count") or 0),
    }


def metric_conservation(report: dict[str, Any]) -> dict[str, bool]:
    return {
        "input_count_conserved": report["total_input_count"] == report["valid_input_count"] + report["malformed_input_count"],
        "pre_dedup_count_conserved": report["pre_dedup_valid_count"] == report["valid_input_count"],
        "dedup_count_conserved": report["unique_valid_candidate_count"]
        == report["pre_dedup_valid_count"] - report["duplicate_suppressed_count"],
        "classified_count_conserved": report["classified_candidate_count"] == report["unique_valid_candidate_count"],
        "classification_bucket_count_conserved": report["classified_candidate_count"]
        == report["publish_candidate_count"] + report["review_required_count"] + report["irrelevant_count"],
        "country_status_count_conserved": report["country_confirmed_count"]
        + report["country_inferred_count"]
        + report["country_unresolved_count"]
        + report["country_conflicting_count"]
        == report["country_resolution_eligible_count"],
        "country_success_count_conserved": report["country_resolution_success_count"]
        == report["country_confirmed_count"] + report["country_inferred_count"],
    }


def review_candidates(
    raw_candidates: list[dict[str, Any]],
    report: dict[str, Any] | None,
    *,
    source: str,
    output_dir: Path,
    source_mode: str | None = None,
    candidates_path: Path | None = None,
    probe_report_path: Path | None = None,
) -> dict[str, Any]:
    before = integrity_snapshot()
    reviewed = sorted((to_review_candidate(candidate) for candidate in raw_candidates), key=candidate_sort_key)
    malformed_candidates = [item for item in reviewed if item["classification"] == "malformed"]
    valid_pre_dedup = [item for item in reviewed if item["classification"] != "malformed"]
    duplicate_groups, _item_to_group = build_duplicate_groups(valid_pre_dedup)
    representative_ids = {group["representative_item_id"] for group in duplicate_groups}
    duplicate_member_ids = {item_id for group in duplicate_groups for item_id in group["member_item_ids"]}
    unique_valid_candidates = sorted(
        [
            candidate
            for candidate in valid_pre_dedup
            if candidate["item_id"] not in duplicate_member_ids or candidate["item_id"] in representative_ids
        ],
        key=candidate_sort_key,
    )
    buckets = {
        "publish_candidate": [item for item in unique_valid_candidates if item["classification"] == "publish_candidate"],
        "review_required": [item for item in unique_valid_candidates if item["classification"] == "review_required"],
        "irrelevant": [item for item in unique_valid_candidates if item["classification"] == "irrelevant"],
        "malformed": sorted(malformed_candidates, key=candidate_sort_key),
    }
    gal_join_eligible = [item for item in unique_valid_candidates if clean_text(item.get("article_identifier"))]
    gal_join_attempt_count = len(gal_join_eligible)
    gal_join_success_count = sum(1 for item in gal_join_eligible if item.get("gal_join_status") == "joined")
    after = integrity_snapshot()
    integrity = integrity_unchanged(before, after)
    all_country_status_counts = Counter(item["country_resolution_status"] for item in reviewed)
    valid_country_status_counts = Counter(item["country_resolution_status"] for item in unique_valid_candidates)
    country_counts = Counter(item.get("country_code") or "UNRESOLVED" for item in unique_valid_candidates)
    language_counts = Counter(item.get("language") or "unknown" for item in unique_valid_candidates)
    duplicate_member_count = len(duplicate_member_ids)
    duplicate_suppressed_count = sum(len(group["member_item_ids"]) - 1 for group in duplicate_groups)
    classified_candidate_count = len(unique_valid_candidates)
    country_resolution_eligible_count = len(unique_valid_candidates)
    country_confirmed_count = valid_country_status_counts.get("confirmed", 0)
    country_inferred_count = valid_country_status_counts.get("inferred", 0)
    country_unresolved_count = valid_country_status_counts.get("unresolved", 0)
    country_conflicting_count = valid_country_status_counts.get("conflicting", 0)
    country_resolution_success_count = country_confirmed_count + country_inferred_count
    input_mode = "fixture" if source == "fixture" else "artifact"
    resolved_source_mode = source_mode or ("fixture" if source == "fixture" else "artifact")
    source_artifact = "" if source == "fixture" else safe_path_label(candidates_path or Path(source))
    live = summarize_live_acceptance(report, source_artifact or source)
    source_artifact_hash = file_hash(candidates_path or Path(source)) if source_artifact and (candidates_path or Path(source)).exists() else None
    probe_hash = file_hash(probe_report_path) if probe_report_path and probe_report_path.exists() else None
    input_file_hashes = {}
    if candidates_path:
        input_file_hashes[safe_path_label(candidates_path)] = file_hash(candidates_path)
    elif source_artifact:
        input_file_hashes[source_artifact] = source_artifact_hash
    if probe_report_path:
        input_file_hashes[safe_path_label(probe_report_path)] = probe_hash
    probe_id = probe_run_id(report, source, source_artifact_hash)
    run_id = review_run_id(probe_id, source_artifact_hash or probe_hash)
    timestamp = clean_text(report.get("timestamp") if report else "")
    config_fingerprint = clean_text(report.get("config_fingerprint") if report else "") or fallback_fingerprint("config", {"source_mode": resolved_source_mode})[:32]
    query_fingerprint = clean_text(report.get("query_fingerprint") if report else "") or fallback_fingerprint(
        "query",
        {"timestamp": timestamp, "source_hash": source_artifact_hash, "probe_hash": probe_hash},
    )[:32]
    report_payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "probe_run_id": probe_id,
        "classifier_version": CLASSIFIER_VERSION,
        "country_resolver_version": COUNTRY_RESOLVER_VERSION,
        "duplicate_resolver_version": DUPLICATE_RESOLVER_VERSION,
        "checked_at": utc_now_iso(),
        "generated_at": utc_now_iso(),
        "input_source": source_artifact or source,
        "input_mode": input_mode,
        "source_mode": resolved_source_mode,
        "source_artifact": source_artifact,
        "source_artifact_hash": source_artifact_hash,
        "input_file_hashes": dict(sorted(input_file_hashes.items())),
        "timestamp": timestamp,
        "config_fingerprint": config_fingerprint,
        "query_fingerprint": query_fingerprint,
        "transport_acceptance_passed": live["transport_acceptance_passed"],
        "total_input_count": len(raw_candidates),
        "malformed_input_count": len(malformed_candidates),
        "valid_input_count": len(valid_pre_dedup),
        "pre_dedup_valid_count": len(valid_pre_dedup),
        "duplicate_member_count": duplicate_member_count,
        "duplicate_group_count": len(duplicate_groups),
        "duplicate_suppressed_count": duplicate_suppressed_count,
        "unique_all_input_count": len(raw_candidates) - duplicate_suppressed_count,
        "unique_valid_candidate_count": len(unique_valid_candidates),
        "classified_candidate_count": classified_candidate_count,
        "publish_candidate_count": len(buckets["publish_candidate"]),
        "review_required_count": len(buckets["review_required"]),
        "irrelevant_count": len(buckets["irrelevant"]),
        "malformed_count": len(malformed_candidates),
        "input_count": len(raw_candidates),
        "valid_count": len(valid_pre_dedup),
        "duplicate_count": duplicate_suppressed_count,
        "unique_count": len(unique_valid_candidates),
        "country_counts": dict(sorted(country_counts.items())),
        "unresolved_country_count": country_unresolved_count,
        "conflicting_country_count": country_conflicting_count,
        "language_counts": dict(sorted(language_counts.items())),
        "gal_join_eligible_count": len(gal_join_eligible),
        "gal_join_attempt_count": gal_join_attempt_count,
        "gal_join_success_count": gal_join_success_count,
        "gal_join_failure_count": gal_join_attempt_count - gal_join_success_count,
        "gal_join_success_ratio": round(gal_join_success_count / gal_join_attempt_count, 4) if gal_join_attempt_count else None,
        "country_resolution_eligible_count": country_resolution_eligible_count,
        "country_confirmed_count": country_confirmed_count,
        "country_inferred_count": country_inferred_count,
        "country_unresolved_count": country_unresolved_count,
        "country_conflicting_count": country_conflicting_count,
        "country_resolution_success_count": country_resolution_success_count,
        "country_resolution_success_ratio": round(country_resolution_success_count / country_resolution_eligible_count, 4)
        if country_resolution_eligible_count
        else None,
        "all_input_country_status_counts": dict(sorted(all_country_status_counts.items())),
        "valid_candidate_country_status_counts": dict(sorted(valid_country_status_counts.items())),
        "suspected_noise_count": sum(1 for item in reviewed if item.get("raw_candidate", {}).get("suspected_noise")),
        "positive_keyword_count": sum(1 for item in reviewed if item.get("positive_reason_codes")),
        "exclusion_keyword_count": sum(1 for item in reviewed if item.get("exclusion_reason_codes")),
        "live_acceptance_status": live,
        "candidate_schema_valid": True,
        "external_http_request_count": 0,
        **integrity,
    }
    conservation = metric_conservation(report_payload)
    report_payload["metric_conservation"] = conservation
    report_payload["metric_conservation_passed"] = all(conservation.values())
    report_payload["publish_candidates_present"] = report_payload["publish_candidate_count"] > 0
    report_payload["manual_review_required"] = any(
        [
            report_payload["review_required_count"] > 0,
            report_payload["malformed_count"] > 0,
            report_payload["country_unresolved_count"] > 0,
            report_payload["country_conflicting_count"] > 0,
            not report_payload["transport_acceptance_passed"] and resolved_source_mode == "live",
        ]
    )
    report_payload["quality_pipeline_valid"] = bool(
        report_payload["candidate_schema_valid"]
        and report_payload["metric_conservation_passed"]
        and report_payload["public_json_unchanged"]
        and report_payload["db_unchanged"]
        and report_payload["env_unchanged"]
        and report_payload["checkpoint_unchanged"]
    )
    report_payload["shadow_ready"] = bool(report_payload["transport_acceptance_passed"] and report_payload["quality_pipeline_valid"])
    report_payload["production_publish_allowed"] = False
    report_payload["normalized_result_hash"] = stable_hash(normalize_for_result_hash(report_payload))
    write_review_artifacts(output_dir, report_payload, buckets, reviewed, duplicate_groups)
    return report_payload


def csv_join(values: Any) -> str:
    if isinstance(values, list):
        return ";".join(json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, dict) else str(value) for value in values)
    return clean_text(values)


def write_review_artifacts(
    output_dir: Path,
    report: dict[str, Any],
    buckets: dict[str, list[dict[str, Any]]],
    reviewed: list[dict[str, Any]],
    duplicate_groups: list[dict[str, Any]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_filename = "live_review_report.json" if report.get("source_mode") == "live" else "review_report.json"
    report_markdown_filename = "live_review_report.md" if report.get("source_mode") == "live" else "review_report.md"
    common = {
        "schema_version": SCHEMA_VERSION,
        "run_id": report["run_id"],
        "probe_run_id": report["probe_run_id"],
        "timestamp": report["timestamp"],
        "source_mode": report["source_mode"],
        "generated_at": report["generated_at"],
        "normalized_result_hash": report["normalized_result_hash"],
        "input_file_hashes": report["input_file_hashes"],
        "config_fingerprint": report["config_fingerprint"],
        "query_fingerprint": report["query_fingerprint"],
        "transport_acceptance_passed": report["transport_acceptance_passed"],
        "quality_pipeline_valid": report["quality_pipeline_valid"],
        "manual_review_required": report["manual_review_required"],
        "public_json_unchanged": report["public_json_unchanged"],
        "db_unchanged": report["db_unchanged"],
        "env_unchanged": report["env_unchanged"],
    }
    country_resolution_items = [
        {
            "item_id": item["item_id"],
            "country_code": item["country_code"],
            "country_name": item["country_name"],
            "country_confidence": item["country_confidence"],
            "country_resolution_status": item["country_resolution_status"],
            "country_evidence": item["country_evidence"],
            "conflicting_evidence": item["conflicting_evidence"],
        }
        for item in sorted(reviewed, key=lambda candidate: candidate["item_id"])
    ]
    files = {
        report_filename: report,
        "publish_candidates.json": {**common, "items": buckets["publish_candidate"]},
        "review_required.json": {**common, "items": buckets["review_required"]},
        "irrelevant.json": {**common, "items": buckets["irrelevant"]},
        "malformed.json": {**common, "items": buckets["malformed"]},
        "duplicate_groups.json": {**common, "duplicate_resolver_version": DUPLICATE_RESOLVER_VERSION, "items": duplicate_groups},
        "country_resolution.json": {
            **common,
            "generated_at": report["generated_at"],
            "classifier_version": CLASSIFIER_VERSION,
            "country_resolver_version": COUNTRY_RESOLVER_VERSION,
            "items": country_resolution_items,
        },
    }
    for filename, payload in files.items():
        (output_dir / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    output_hashes = {filename: file_hash(output_dir / filename) for filename in sorted(files)}
    manifest = {
            **common,
            "generated_at": report["checked_at"],
            "input_mode": report["input_mode"],
            "source_artifact": report["source_artifact"],
            "source_artifact_hash": report["source_artifact_hash"],
            "source_mode": report["source_mode"],
            "total_input_count": report["total_input_count"],
            "valid_input_count": report["valid_input_count"],
            "malformed_input_count": report["malformed_input_count"],
            "duplicate_suppressed_count": report["duplicate_suppressed_count"],
            "unique_valid_candidate_count": report["unique_valid_candidate_count"],
            "output_file_hashes": output_hashes,
            "external_http_request_count": 0,
            "transport_acceptance_passed": report["transport_acceptance_passed"],
            "quality_pipeline_valid": report["quality_pipeline_valid"],
            "shadow_ready": report["shadow_ready"],
            "production_publish_allowed": report["production_publish_allowed"],
            "public_json_unchanged": report["public_json_unchanged"],
            "db_unchanged": report["db_unchanged"],
            "env_unchanged": report["env_unchanged"],
            "checkpoint_unchanged": report["checkpoint_unchanged"],
        }
    (output_dir / "processing_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    with (output_dir / "manual_review.csv").open("w", encoding="utf-8", newline="") as file:
        fieldnames = [
            "item_id",
            "title",
            "original_url",
            "canonical_url",
            "domain",
            "published_at",
            "language",
            "country_code",
            "country_confidence",
            "country_resolution_status",
            "relevance_score",
            "classification",
            "positive_reasons",
            "exclusion_reasons",
            "gal_join_status",
            "source_dataset",
            "reviewer_decision",
            "reviewer_note",
        ]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for item in sorted(reviewed, key=lambda candidate: candidate["item_id"]):
            writer.writerow(
                {
                    "item_id": item["item_id"],
                    "title": item["title"],
                    "original_url": item["original_url"],
                    "canonical_url": item["canonical_url"],
                    "domain": item["domain"],
                    "published_at": item["published_at"],
                    "language": item["language"],
                    "country_code": item["country_code"] or "",
                    "country_confidence": item["country_confidence"],
                    "country_resolution_status": item["country_resolution_status"],
                    "relevance_score": item["relevance_score"],
                    "classification": item["classification"],
                    "positive_reasons": csv_join(item["positive_reason_codes"]),
                    "exclusion_reasons": csv_join(item["exclusion_reason_codes"]),
                    "gal_join_status": item["gal_join_status"],
                    "source_dataset": item["source_dataset"],
                    "reviewer_decision": "",
                    "reviewer_note": "",
                }
            )
    lines = [
        "# GDELT Web NGrams Candidate Review",
        "",
        f"- schema_version: `{report['schema_version']}`",
        f"- total_input_count: `{report['total_input_count']}`",
        f"- valid_input_count: `{report['valid_input_count']}`",
        f"- malformed_input_count: `{report['malformed_input_count']}`",
        f"- unique_valid_candidate_count: `{report['unique_valid_candidate_count']}`",
        f"- publish_candidate_count: `{report['publish_candidate_count']}`",
        f"- review_required_count: `{report['review_required_count']}`",
        f"- irrelevant_count: `{report['irrelevant_count']}`",
        f"- malformed_count: `{report['malformed_count']}`",
        f"- duplicate_group_count: `{report['duplicate_group_count']}`",
        f"- duplicate_suppressed_count: `{report['duplicate_suppressed_count']}`",
        f"- gal_join_attempt_count: `{report['gal_join_attempt_count']}`",
        f"- gal_join_success_ratio: `{report['gal_join_success_ratio']}`",
        f"- country_resolution_eligible_count: `{report['country_resolution_eligible_count']}`",
        f"- country_resolution_success_ratio: `{report['country_resolution_success_ratio']}`",
        f"- live_acceptance_status: `{report['live_acceptance_status']['live_acceptance_status']}`",
        f"- transport_acceptance_passed: `{report['transport_acceptance_passed']}`",
        f"- metric_conservation_passed: `{report['metric_conservation_passed']}`",
        f"- quality_pipeline_valid: `{report['quality_pipeline_valid']}`",
        f"- shadow_ready: `{report['shadow_ready']}`",
        f"- production_publish_allowed: `{report['production_publish_allowed']}`",
        f"- external_http_request_count: `{report['external_http_request_count']}`",
        f"- public_json_unchanged: `{report['public_json_unchanged']}`",
        f"- db_unchanged: `{report['db_unchanged']}`",
        f"- env_unchanged: `{report['env_unchanged']}`",
    ]
    (output_dir / report_markdown_filename).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Review GDELT Web NGrams candidate quality without network access.")
    parser.add_argument("--input", type=Path, default=None, help="Path to live candidates.json")
    parser.add_argument("--input-candidates", type=Path, default=None, help="Path to live probe candidates.json")
    parser.add_argument("--input-probe-report", type=Path, default=None, help="Path to live probe report.json")
    parser.add_argument("--source-mode", choices=["fixture", "artifact", "live"], default="artifact")
    parser.add_argument("--fixture", action="store_true", help="Use local Web NGrams and GAL fixtures")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    try:
        if args.fixture:
            candidates, report, source = load_fixture_candidates()
            source_mode = "fixture"
            candidates_path = None
            probe_report_path = None
        elif args.input_candidates:
            candidates, report, source = load_candidate_artifact(
                args.input_candidates,
                args.input_probe_report,
                source_mode=args.source_mode,
            )
            source_mode = args.source_mode
            candidates_path = args.input_candidates
            probe_report_path = args.input_probe_report
        elif args.input:
            candidates, report, source = load_input_candidates(args.input)
            source_mode = args.source_mode
            candidates_path = args.input
            probe_report_path = args.input.with_name("report.json") if args.input.with_name("report.json").exists() else None
        else:
            parser.error("--input, --input-candidates, or --fixture is required")
        result = review_candidates(
            candidates,
            report,
            source=source,
            output_dir=args.output_dir,
            source_mode=source_mode,
            candidates_path=candidates_path,
            probe_report_path=probe_report_path,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
