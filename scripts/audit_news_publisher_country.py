from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.news_publisher_country import COUNTRY_NAMES, publisher_country_fields  # noqa: E402
from src.news_publisher_region import is_intermediary_domain, normalize_domain  # noqa: E402


COUNTRY_FIELDS = (
    "publisher_country_code",
    "publisher_country_name",
    "publisher_country_confidence",
    "publisher_country_reason",
)
VALID_CONFIDENCE = {"high", "medium", "low", "unknown"}
VALID_REASONS = {
    "explicit_domain_map",
    "country_tld",
    "publisher_name_map",
    "feed_metadata",
    "url_domain",
    "publisher_region_domestic",
    "unknown",
}


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def load_items(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {"items": payload}, payload
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("news payload must be an object with items[]")
    return payload, payload["items"]


def effective_country(item: dict[str, Any]) -> dict[str, str]:
    missing = [field for field in COUNTRY_FIELDS if field not in item]
    if missing:
        return publisher_country_fields(item)
    return {field: clean_text(item.get(field)) for field in COUNTRY_FIELDS}


def sample_row(item: dict[str, Any], country: dict[str, str]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "publisher_name": item.get("publisher_name") or item.get("media"),
        "publisher_domain": item.get("publisher_domain"),
        "publisher_region": item.get("publisher_region"),
        "collection_pipeline": item.get("collection_pipeline"),
        "publisher_country_code": country.get("publisher_country_code"),
        "publisher_country_name": country.get("publisher_country_name"),
        "publisher_country_confidence": country.get("publisher_country_confidence"),
        "publisher_country_reason": country.get("publisher_country_reason"),
        "original_url": item.get("original_url"),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "id",
        "title",
        "publisher_name",
        "publisher_domain",
        "publisher_region",
        "collection_pipeline",
        "publisher_country_code",
        "publisher_country_name",
        "publisher_country_confidence",
        "publisher_country_reason",
        "original_url",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def audit(path: Path, *, strict_stored_fields: bool = False) -> dict[str, Any]:
    payload, items = load_items(path)
    required_missing_rows: list[dict[str, Any]] = []
    invalid_code_rows: list[dict[str, Any]] = []
    name_mismatch_rows: list[dict[str, Any]] = []
    domestic_conflict_rows: list[dict[str, Any]] = []
    overseas_kr_rows: list[dict[str, Any]] = []
    google_domain_rows: list[dict[str, Any]] = []
    invalid_confidence_rows: list[dict[str, Any]] = []
    invalid_reason_rows: list[dict[str, Any]] = []
    unknown_rows: list[dict[str, Any]] = []
    sample_rows: list[dict[str, Any]] = []
    country_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()

    for item in items:
        country = effective_country(item)
        missing = [field for field in COUNTRY_FIELDS if field not in item]
        if missing:
            required_missing_rows.append({**sample_row(item, country), "missing_fields": ",".join(missing)})

        code = clean_text(country.get("publisher_country_code")).upper()
        name = clean_text(country.get("publisher_country_name"))
        confidence = clean_text(country.get("publisher_country_confidence"))
        reason = clean_text(country.get("publisher_country_reason"))
        publisher_region = clean_text(item.get("publisher_region"))
        publisher_domain = normalize_domain(item.get("publisher_domain"))

        if publisher_domain and is_intermediary_domain(publisher_domain):
            google_domain_rows.append(sample_row(item, country))
        if code and code not in COUNTRY_NAMES:
            invalid_code_rows.append(sample_row(item, country))
        if code and COUNTRY_NAMES.get(code) != name:
            name_mismatch_rows.append(sample_row(item, country))
        if confidence not in VALID_CONFIDENCE:
            invalid_confidence_rows.append(sample_row(item, country))
        if reason not in VALID_REASONS:
            invalid_reason_rows.append(sample_row(item, country))
        if publisher_region == "domestic" and code and code != "KR":
            domestic_conflict_rows.append(sample_row(item, country))
        if publisher_region == "overseas" and code == "KR":
            overseas_kr_rows.append(sample_row(item, country))
        if not code:
            unknown_rows.append(sample_row(item, country))

        country_counts[code or "unknown"] += 1
        confidence_counts[confidence or "unknown"] += 1
        reason_counts[reason or "unknown"] += 1
        if len(sample_rows) < 100:
            sample_rows.append(sample_row(item, country))

    hard_error_count = (
        len(invalid_code_rows)
        + len(name_mismatch_rows)
        + len(domestic_conflict_rows)
        + len(overseas_kr_rows)
        + len(google_domain_rows)
        + len(invalid_confidence_rows)
        + len(invalid_reason_rows)
    )
    if strict_stored_fields:
        hard_error_count += len(required_missing_rows)

    overseas_items = [
        item for item in items
        if item.get("publisher_region") == "overseas" or item.get("collection_pipeline") == "rss_overseas_pipeline"
    ]
    overseas_unknown = [
        row for row in unknown_rows
        if row.get("publisher_region") == "overseas" or row.get("collection_pipeline") == "rss_overseas_pipeline"
    ]
    overseas_count = len(overseas_items)
    overseas_known_count = overseas_count - len(overseas_unknown)
    overseas_known_rate = round((overseas_known_count / overseas_count) * 100, 2) if overseas_count else 100.0

    if hard_error_count:
        status = "failed"
    elif overseas_count and overseas_known_rate < 90:
        status = "passed_with_country_mapping_required"
    elif required_missing_rows:
        status = "passed_with_warnings"
    else:
        status = "passed"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_path": str(path),
        "public_news_generated_at": payload.get("generated_at"),
        "total_news_count": len(items),
        "country_known_count": len(items) - len(unknown_rows),
        "country_unknown_count": len(unknown_rows),
        "country_known_rate": round(((len(items) - len(unknown_rows)) / len(items)) * 100, 2) if items else 100.0,
        "overseas_news_count": overseas_count,
        "overseas_country_known_count": overseas_known_count,
        "overseas_country_unknown_count": len(overseas_unknown),
        "overseas_country_known_rate": overseas_known_rate,
        "required_field_missing_count": len(required_missing_rows),
        "invalid_country_code_count": len(invalid_code_rows),
        "country_name_mismatch_count": len(name_mismatch_rows),
        "domestic_region_non_kr_count": len(domestic_conflict_rows),
        "overseas_region_kr_count": len(overseas_kr_rows),
        "google_news_publisher_domain_count": len(google_domain_rows),
        "invalid_confidence_count": len(invalid_confidence_rows),
        "invalid_reason_count": len(invalid_reason_rows),
        "country_distribution": dict(country_counts),
        "confidence_distribution": dict(confidence_counts),
        "reason_distribution": dict(reason_counts),
        "validation_errors": {
            "missing_fields": required_missing_rows[:50],
            "invalid_country_codes": invalid_code_rows[:50],
            "country_name_mismatches": name_mismatch_rows[:50],
            "domestic_region_non_kr": domestic_conflict_rows[:50],
            "overseas_region_kr": overseas_kr_rows[:50],
            "google_news_publisher_domain": google_domain_rows[:50],
            "invalid_confidence": invalid_confidence_rows[:50],
            "invalid_reason": invalid_reason_rows[:50],
        },
        "unknown_samples": unknown_rows[:100],
        "sample_rows": sample_rows,
        "audit_status": status,
        "strict_stored_fields": strict_stored_fields,
    }


def write_markdown(path: Path, result: dict[str, Any]) -> None:
    lines = [
        "# News Publisher Country Audit",
        "",
        f"- Audit Status: {result['audit_status']}",
        f"- Public news generated_at: {result.get('public_news_generated_at') or ''}",
        f"- Total news count: {result['total_news_count']}",
        f"- Country known count: {result['country_known_count']}",
        f"- Country unknown count: {result['country_unknown_count']}",
        f"- Country known rate: {result['country_known_rate']}%",
        f"- Overseas news count: {result['overseas_news_count']}",
        f"- Overseas country known count: {result['overseas_country_known_count']}",
        f"- Overseas country unknown count: {result['overseas_country_unknown_count']}",
        f"- Overseas country known rate: {result['overseas_country_known_rate']}%",
        f"- Required field missing count: {result['required_field_missing_count']}",
        f"- Invalid country code count: {result['invalid_country_code_count']}",
        f"- Country/name mismatch count: {result['country_name_mismatch_count']}",
        f"- Domestic region non-KR count: {result['domestic_region_non_kr_count']}",
        f"- Overseas region KR count: {result['overseas_region_kr_count']}",
        f"- Google News publisher domain count: {result['google_news_publisher_domain_count']}",
        "",
        "## Country Distribution",
    ]
    for code, count in sorted(result["country_distribution"].items()):
        lines.append(f"- {code}: {count}")
    lines.extend(["", "## Confidence Distribution"])
    for confidence, count in sorted(result["confidence_distribution"].items()):
        lines.append(f"- {confidence}: {count}")
    lines.extend(["", "## Reason Distribution"])
    for reason, count in sorted(result["reason_distribution"].items()):
        lines.append(f"- {reason}: {count}")
    lines.extend(["", "## Unknown Samples"])
    if result["unknown_samples"]:
        for row in result["unknown_samples"][:20]:
            lines.append(f"- #{row.get('id')} {row.get('publisher_name') or ''} | {row.get('title') or ''}")
    else:
        lines.append("- None")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit publisher country metadata for public news.")
    parser.add_argument("--input", default=str(ROOT / "frontend" / "public" / "data" / "news.json"))
    parser.add_argument("--output-dir", default=str(ROOT / "artifacts" / "news_publisher_country_audit"))
    parser.add_argument("--strict-stored-fields", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result = audit(Path(args.input), strict_stored_fields=args.strict_stored_fields)

    (output_dir / "news_publisher_country_audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown(output_dir / "news_publisher_country_audit.md", result)
    write_csv(output_dir / "news_publisher_country_samples.csv", result["sample_rows"])
    write_csv(output_dir / "news_publisher_country_unknown.csv", result["unknown_samples"])
    conflicts = []
    for key in (
        "domestic_region_non_kr",
        "overseas_region_kr",
        "google_news_publisher_domain",
        "invalid_country_codes",
        "country_name_mismatches",
    ):
        conflicts.extend(result["validation_errors"].get(key, []))
    write_csv(output_dir / "news_publisher_country_conflicts.csv", conflicts)

    print(
        "news_publisher_country_audit "
        f"status={result['audit_status']} total={result['total_news_count']} "
        f"known={result['country_known_count']} unknown={result['country_unknown_count']} "
        f"overseas_known_rate={result['overseas_country_known_rate']}%"
    )
    return 1 if result["audit_status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
