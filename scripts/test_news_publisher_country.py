from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.news_publisher_country import (  # noqa: E402
    apply_publisher_country_fields,
    apply_publisher_country_fields_to_items,
    load_publisher_country_config,
    mapped_country_for_domain,
    publisher_country_fields,
)
from scripts.audit_news_publisher_country import audit  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def item(**overrides):
    base = {
        "id": 1,
        "title": "Modular housing factory opens - Assembly Magazine",
        "media": "Assembly Magazine",
        "publisher_name": "Assembly Magazine",
        "publisher_domain": "assemblymag.com",
        "publisher_region": "overseas",
        "collection_pipeline": "rss_overseas_pipeline",
        "collection_source": "해외 모듈러 RSS",
        "original_url": "https://example.com/article",
        "relevance_score": 75,
        "relevance_level": "direct",
        "relevance_score_version": "unified-v2",
    }
    return {**base, **overrides}


def test_explicit_domain_country_mapping() -> None:
    fields = publisher_country_fields(item(publisher_domain="assemblymag.com", publisher_name=""))
    require(fields["publisher_country_code"] == "US", "assemblymag.com must map to US")
    require(fields["publisher_country_reason"] == "explicit_domain_map", "domain mapping reason mismatch")


def test_country_tld_mapping() -> None:
    fields = publisher_country_fields(
        item(publisher_domain="regional.publisher.co.uk", publisher_name="", publisher_region="unknown")
    )
    require(fields["publisher_country_code"] == "GB", "co.uk must map to GB")
    require(fields["publisher_country_confidence"] == "medium", "TLD confidence must be medium")


def test_generic_dot_com_is_not_inferred() -> None:
    country, _ = mapped_country_for_domain("unknown-example.com")
    require(country["publisher_country_code"] == "", ".com must not infer a country")
    require(country["publisher_country_confidence"] == "unknown", ".com country must stay unknown")


def test_google_news_is_not_publisher_domain() -> None:
    country, _ = mapped_country_for_domain("news.google.com")
    require(country["publisher_country_code"] == "", "news.google.com must not infer country")


def test_domestic_news_defaults_to_kr() -> None:
    fields = publisher_country_fields(
        item(
            publisher_region="domestic",
            publisher_domain="",
            publisher_name="국내 언론",
            collection_pipeline="domestic_pipeline",
        )
    )
    require(fields["publisher_country_code"] == "KR", "domestic publisher_region must map to KR")
    require(fields["publisher_country_name"] == "대한민국", "KR display name mismatch")


def test_overseas_publisher_name_mapping() -> None:
    fields = publisher_country_fields(item(publisher_domain="", publisher_name="CHEK News"))
    require(fields["publisher_country_code"] == "CA", "CHEK News must map to Canada")
    require(fields["publisher_country_reason"] == "publisher_name_map", "publisher mapping reason mismatch")


def test_unknown_fallback() -> None:
    fields = publisher_country_fields(
        item(publisher_domain="", publisher_name="Unknown Modular Daily", publisher_region="unknown")
    )
    require(fields["publisher_country_code"] == "", "unknown publisher must have blank country code")
    require(fields["publisher_country_name"] == "국가 미확인", "unknown country label mismatch")
    require(fields["publisher_country_confidence"] == "unknown", "unknown confidence mismatch")


def test_code_name_consistency() -> None:
    config = load_publisher_country_config()
    for group in ("domains", "publishers"):
        for key, value in config[group].items():
            applied = publisher_country_fields(item(publisher_domain=key if group == "domains" else "", publisher_name=key))
            code = applied["publisher_country_code"]
            if code:
                require(applied["publisher_country_name"], f"country name missing for {key}")


def test_apply_preserves_identity_and_scores() -> None:
    original = item(id=42, original_url="https://assemblymag.com/example", relevance_score=88, relevance_level="direct")
    enriched = apply_publisher_country_fields(original)
    require(enriched["id"] == original["id"], "id changed")
    require(enriched["original_url"] == original["original_url"], "original_url changed")
    require(enriched["relevance_score"] == original["relevance_score"], "score changed")
    require(enriched["relevance_level"] == original["relevance_level"], "level changed")
    require(enriched["publisher_country_code"] == "US", "country field missing")
    require("publisher_country_code" not in original, "apply must not mutate input")


def test_audit_fixture(tmp_path: Path | None = None) -> None:
    out = ROOT / "artifacts" / "test_news_publisher_country_fixture.json"
    payload = {
        "generated_at": "2026-07-12T00:00:00+09:00",
        "items": apply_publisher_country_fields_to_items(
            [
                item(id=1, publisher_region="domestic", publisher_domain="", publisher_name="국내 언론"),
                item(id=2, publisher_region="overseas", publisher_domain="realestate.com.au", publisher_name=""),
                item(id=3, publisher_region="unknown", publisher_domain="", publisher_name="Unknown Publisher"),
            ]
        ),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result = audit(out, strict_stored_fields=True)
    require(result["audit_status"] in {"passed", "passed_with_country_mapping_required"}, "audit fixture failed")
    require(result["invalid_country_code_count"] == 0, "invalid country code found")
    require(result["country_name_mismatch_count"] == 0, "country name mismatch found")


def test_actual_public_data_invariants() -> None:
    path = ROOT / "frontend" / "public" / "data" / "news.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items", [])
    enriched = apply_publisher_country_fields_to_items(items)
    require(len(enriched) == len(items), "item count changed")
    for before, after in zip(items, enriched):
        for field in (
            "id",
            "original_url",
            "relevance_score",
            "relevance_level",
            "relevance_score_version",
            "collection_pipeline",
            "publisher_region",
        ):
            require(before.get(field) == after.get(field), f"{field} changed for item {before.get('id')}")


def main() -> int:
    tests = [
        test_explicit_domain_country_mapping,
        test_country_tld_mapping,
        test_generic_dot_com_is_not_inferred,
        test_google_news_is_not_publisher_domain,
        test_domestic_news_defaults_to_kr,
        test_overseas_publisher_name_mapping,
        test_unknown_fallback,
        test_code_name_consistency,
        test_apply_preserves_identity_and_scores,
        test_audit_fixture,
        test_actual_public_data_invariants,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("NEWS PUBLISHER COUNTRY TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
