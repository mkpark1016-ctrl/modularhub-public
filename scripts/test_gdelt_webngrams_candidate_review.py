from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.review_gdelt_webngrams_candidates import (  # noqa: E402
    REVIEW_FIXTURE,
    build_duplicate_groups,
    normalize_url,
    review_candidates,
    to_review_candidate,
)


RUN8_QUALITY_FIXTURE = ROOT / "tests" / "fixtures" / "gdelt_webngrams_run8_quality_sample.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def candidate(title: str, url: str, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": extra.pop("id", "fixture-id"),
        "title": title,
        "url": url,
        "canonical_url": url,
        "published_at": "20260627000000",
        "language": "en",
        "source_type": "gdelt_web_news_ngrams",
        "gal_joined": True,
    }
    payload.update(extra)
    return payload


def load_fixture() -> list[dict[str, Any]]:
    payload = json.loads(REVIEW_FIXTURE.read_text(encoding="utf-8"))
    require(isinstance(payload, list), "review fixture must be list")
    return payload


def normalize_for_hash(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: normalize_for_hash(item)
            for key, item in sorted(value.items())
            if key
            not in {
                "checked_at",
                "generated_at",
                "output_file_hashes",
                "source_artifact_hash",
            }
        }
    if isinstance(value, list):
        return [normalize_for_hash(item) for item in value]
    return value


def load_artifact_set(directory: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for filename in [
        "review_report.json",
        "publish_candidates.json",
        "review_required.json",
        "irrelevant.json",
        "malformed.json",
        "duplicate_groups.json",
        "country_resolution.json",
        "processing_manifest.json",
    ]:
        payload[filename] = json.loads((directory / filename).read_text(encoding="utf-8"))
    return normalize_for_hash(payload)


def run_fixture_cli(output_dir: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "review_gdelt_webngrams_candidates.py"),
            "--fixture",
            "--output-dir",
            str(output_dir),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def main() -> int:
    normalized = normalize_url(" HTTPS://Example.org:443/news/modular/?utm_source=x&b=2&a=1&fbclid=abc#frag ")
    require(normalized["normalized_url"] == "https://example.org/news/modular?a=1&b=2", "tracking/default-port normalization mismatch")
    require(normalized["domain"] == "example.org", "domain normalization mismatch")
    require(normalized["url_valid"] is True and normalized["url_validation_reason"] == "ok", "valid URL reason mismatch")

    mobile = normalize_url("https://m.example.org/story?ref=feed&id=10")
    require(mobile["mobile_url"] == "https://m.example.org/story?ref=feed&id=10", "mobile URL must be preserved")
    require(mobile["normalized_url"] == "https://m.example.org/story?id=10", "mobile tracking normalization mismatch")
    require(normalize_url("not-a-url")["url_validation_reason"] == "missing_scheme", "missing scheme must be invalid")
    require(normalize_url("ftp://files.example.org/a")["url_validation_reason"] == "unsupported_scheme", "unsupported scheme mismatch")
    require(normalize_url("https:///missing-host")["url_validation_reason"] == "missing_hostname", "missing host mismatch")

    modular = to_review_candidate(candidate("Factory opens modular construction facility", "https://news.example.org/a"))
    require(modular["classification"] == "publish_candidate", "modular construction should be publish candidate")
    require(modular["relevance_score"] >= 80, "modular construction score too low")

    require(to_review_candidate(candidate("Prefabricated building factory supports housing", "https://news.example.org/b"))["classification"] == "publish_candidate", "prefabricated building should publish")
    require(to_review_candidate(candidate("Offsite construction school classrooms completed", "https://news.example.org/c"))["classification"] == "publish_candidate", "offsite construction should publish")
    require(to_review_candidate(candidate("Modular housing project expands", "https://news.example.org/d"))["classification"] == "publish_candidate", "modular housing should publish")
    require(to_review_candidate(candidate("Modular school opens", "https://news.example.org/e"))["classification"] == "publish_candidate", "modular school should publish")
    require(to_review_candidate(candidate("Modular hotel accommodation reaches site", "https://news.example.org/f"))["classification"] == "publish_candidate", "modular hotel should publish")

    score_49 = to_review_candidate(candidate("Modular project update", "https://score.example.org/49"))
    score_50 = to_review_candidate(candidate("Modular parts for construction", "https://score.example.org/50"))
    score_79 = to_review_candidate(candidate("Modular project home factory office apartment dormitory council", "https://score.example.org/79"))
    score_80 = to_review_candidate(candidate("Modular construction", "https://score.example.org/80"))
    require(score_49["relevance_score"] == 49 and score_49["classification"] == "irrelevant", "49 boundary mismatch")
    require(score_50["relevance_score"] == 50 and score_50["classification"] == "review_required", "50 boundary mismatch")
    require(score_79["relevance_score"] == 79 and score_79["classification"] == "review_required", "79 boundary mismatch")
    require(score_80["relevance_score"] == 80 and score_80["classification"] == "publish_candidate", "80 boundary mismatch")

    for title in [
        "New modular synthesizer reaches stores",
        "Retailer launches modular furniture collection",
        "Software module improves developer workflow",
        "Battery module capacity rises",
        "Modular smartphone module returns",
    ]:
        reviewed = to_review_candidate(candidate(title, f"https://noise.example.org/{abs(hash(title))}"))
        require(reviewed["classification"] == "irrelevant", f"noise should be irrelevant: {title}")

    positive_cases = [
        "Modular housing project adds residential apartments",
        "Volumetric modular hotel factory starts construction",
        "Prefabricated school building opens classrooms",
        "Off-site construction factory builds hospital modules",
        "Modular apartment development reaches construction stage",
    ]
    for index, title in enumerate(positive_cases, start=1):
        reviewed = to_review_candidate(candidate(title, f"https://positive.example.org/{index}"))
        require(reviewed["classification"] in {"publish_candidate", "review_required"}, f"positive fixture lost: {title}")
        require(not reviewed["exclusion_reason_codes"], f"positive fixture was excluded: {title}")

    require(to_review_candidate(candidate("", "https://bad.example.org/no-title"))["classification"] == "malformed", "missing title should be malformed")
    require(to_review_candidate(candidate("Missing URL", ""))["classification"] == "malformed", "missing URL should be malformed")
    require(to_review_candidate(candidate("Invalid URL", "not-a-url"))["classification"] == "malformed", "invalid URL should be malformed")

    domain_only = to_review_candidate(candidate("Modular construction update", "https://example.de/build", language="en"))
    require(domain_only["country_resolution_status"] == "unresolved", "domain alone must not resolve country")
    explicit = to_review_candidate(candidate("Modular construction update", "https://example.de/build", source_country_code="AU", language="de"))
    require(explicit["country_resolution_status"] == "confirmed" and explicit["country_code"] == "AU", "explicit country mismatch")
    conflict = to_review_candidate(candidate("Modular construction update", "https://example.org/build", source_country_code="AU", publication_country="DE"))
    require(conflict["country_resolution_status"] == "conflicting", "conflicting country evidence must be preserved")
    require(len(conflict["conflicting_evidence"]) >= 2, "conflicting evidence missing")
    inferred = to_review_candidate(candidate("Australia modular construction update", "https://country.test.com.au/build", language="en"))
    require(inferred["country_resolution_status"] == "inferred" and inferred["country_code"] == "AU", "inferred country mismatch")
    require(len(inferred["country_evidence"]) >= 2 and inferred["country_confidence"] >= 0.7, "inferred evidence/confidence mismatch")

    language_match = to_review_candidate(candidate("Modular construction language", "https://language.example.org/match", language="en", gal_language="en"))
    require(language_match["conflicting_language"] is False, "matching language should not conflict")
    language_conflict = to_review_candidate(candidate("Modular construction language", "https://language.example.org/conflict", language="en", gal_language="de"))
    require(language_conflict["conflicting_language"] is True, "language conflict should be preserved")

    duplicate_candidates = [
        to_review_candidate(candidate("Modular construction project", "https://example.org/a?utm_source=x", id="one")),
        to_review_candidate(candidate("Modular construction project", "https://example.org/a#frag", id="two")),
        to_review_candidate(candidate("Other modular housing project", "https://example.org/b", id="three", article_identifier="same-gal")),
        to_review_candidate(candidate("Other modular housing project updated", "https://example.org/c", id="four", article_identifier="same-gal")),
        to_review_candidate(candidate("Modular school project awarded", "https://domain-title.example.org/a", id="five")),
        to_review_candidate(candidate("Modular school project awarded", "https://domain-title.example.org/b", id="six")),
    ]
    duplicate_groups, _item_to_group = build_duplicate_groups(duplicate_candidates)
    reasons = {group["duplicate_reason"] for group in duplicate_groups}
    require("same_gal_article_identifier" in reasons, "GAL id duplicate missing")
    require("same_normalized_url" in reasons or "same_canonical_url" in reasons, "URL duplicate missing")
    require("same_domain_normalized_title" in reasons, "domain/title duplicate missing")
    require(all(group["duplicate_group_id"].startswith("dup-") for group in duplicate_groups), "deterministic duplicate id prefix missing")

    fixture = load_fixture()
    with tempfile.TemporaryDirectory() as tmp:
        report = review_candidates(fixture, None, source="fixture", output_dir=Path(tmp))
        require(report["schema_version"] == 1, "schema version mismatch")
        require(report["live_acceptance_status"]["live_acceptance_status"] == "fixture_only", "fixture live status mismatch")
        require(report["total_input_count"] == report["valid_input_count"] + report["malformed_input_count"], "metric conservation A failed")
        require(report["pre_dedup_valid_count"] == report["valid_input_count"], "metric conservation B failed")
        require(report["unique_valid_candidate_count"] == report["pre_dedup_valid_count"] - report["duplicate_suppressed_count"], "metric conservation C failed")
        require(report["classified_candidate_count"] == report["unique_valid_candidate_count"], "metric conservation D failed")
        require(
            report["classified_candidate_count"]
            == report["publish_candidate_count"] + report["review_required_count"] + report["irrelevant_count"],
            "metric conservation E failed",
        )
        require(
            report["total_input_count"]
            == report["malformed_count"]
            + report["duplicate_suppressed_count"]
            + report["publish_candidate_count"]
            + report["review_required_count"]
            + report["irrelevant_unique_count"],
            "deduped input bucket conservation failed",
        )
        require(report["publish_candidate_count"] >= 1, "fixture publish candidates missing")
        require(report["review_required_count"] >= 1, "fixture review required missing")
        require(report["irrelevant_count"] >= 1, "fixture irrelevant missing")
        require(report["malformed_count"] >= 1, "fixture malformed missing")
        require(report["duplicate_group_count"] >= 1, "fixture duplicate groups missing")
        require(report["gal_join_attempt_count"] == report["gal_join_success_count"] + report["gal_join_failure_count"], "GAL denominator mismatch")
        require(report["gal_join_eligible_count"] == report["gal_join_attempt_count"], "GAL eligible/attempt mismatch")
        require(report["gal_join_success_ratio"] is not None, "GAL ratio should be present")
        require(
            report["country_resolution_eligible_count"]
            == report["country_confirmed_count"]
            + report["country_inferred_count"]
            + report["country_unresolved_count"]
            + report["country_conflicting_count"],
            "country denominator mismatch",
        )
        require(report["country_resolution_success_count"] == report["country_confirmed_count"] + report["country_inferred_count"], "country numerator mismatch")
        require(report["country_confirmed_count"] >= 1, "confirmed country missing")
        require(report["country_inferred_count"] >= 1, "inferred country missing")
        require(report["country_unresolved_count"] >= 1, "unresolved country missing")
        require(report["country_conflicting_count"] >= 1, "conflicting country missing")
        require(report["external_http_request_count"] == 0, "review must not request network")
        require(report["public_json_unchanged"], "review mutated public JSON")
        require(report["db_unchanged"], "review mutated DB")
        require(report["env_unchanged"], "review mutated .env")
        require(report["checkpoint_unchanged"], "review mutated checkpoint")
        for filename in [
            "review_report.json",
            "review_report.md",
            "publish_candidates.json",
            "review_required.json",
            "irrelevant.json",
            "malformed.json",
            "manual_review.csv",
            "duplicate_groups.json",
            "country_resolution.json",
            "processing_manifest.json",
        ]:
            require((Path(tmp) / filename).exists(), f"{filename} missing")
        for filename in [
            "review_report.json",
            "publish_candidates.json",
            "review_required.json",
            "irrelevant.json",
            "malformed.json",
            "duplicate_groups.json",
            "country_resolution.json",
            "processing_manifest.json",
        ]:
            payload = json.loads((Path(tmp) / filename).read_text(encoding="utf-8"))
            require(payload["schema_version"] == 1, f"{filename} schema missing")
        with (Path(tmp) / "manual_review.csv").open("r", encoding="utf-8", newline="") as file:
            header = next(csv.reader(file))
        require(header[:4] == ["item_id", "title", "original_url", "canonical_url"], "manual review CSV header mismatch")
        publish_payload = json.loads((Path(tmp) / "publish_candidates.json").read_text(encoding="utf-8"))
        publish_text = json.dumps(publish_payload, ensure_ascii=False).lower()
        require("localhost" not in publish_text and "example.com" not in publish_text, "publish candidates contain forbidden local/example host")

    run8_candidates = json.loads(RUN8_QUALITY_FIXTURE.read_text(encoding="utf-8"))
    for raw in run8_candidates:
        reviewed = to_review_candidate(raw)
        if raw["id"] == "run8_vertical_lift_army":
            require(reviewed["classification"] == "irrelevant", "Run #8 Army candidate must be irrelevant")
            require("defense_modular_system" in reviewed["exclusion_reason_codes"], "Army exclusion reason missing")
        if raw["id"] in {"run8_log4j_wfsu", "run8_log4j_tpr"}:
            require(reviewed["classification"] == "irrelevant", "Run #8 Log4j candidate must be irrelevant")
            require("software_component" in reviewed["exclusion_reason_codes"], "Log4j exclusion reason missing")
        if raw["id"] == "run8_fashion_week_wiki":
            require(reviewed["classification"] == "irrelevant", "Run #8 off-site venue candidate must be irrelevant")
            require("offsite_venue_not_construction" in reviewed["exclusion_reason_codes"], "off-site venue exclusion reason missing")
        if raw["id"] == "run8_modular_bridge_forces":
            require(reviewed["classification"] == "irrelevant", "Run #8 modular bridge candidate must be irrelevant")
            require("non_building_military_infrastructure" in reviewed["exclusion_reason_codes"], "modular bridge exclusion reason missing")

    live_probe_report = {
        "timestamp": "20211215000100",
        "status": "success",
        "transport_acceptance_passed": True,
        "10.10-B1_live_accepted": True,
        "network_request_count": 2,
        "http_request_count": 2,
        "doc_api_request_count": 0,
        "public_json_unchanged": True,
        "db_unchanged": True,
        "env_unchanged": True,
        "config_fingerprint": "run8-quality-fixture",
        "query_fingerprint": "run8-quality-fixture",
    }
    with tempfile.TemporaryDirectory() as tmp:
        report = review_candidates(run8_candidates, live_probe_report, source="run8-quality", output_dir=Path(tmp), source_mode="live")
        require(report["total_input_count"] == 5, "Run #8 total input mismatch")
        require(report["valid_input_count"] == 5, "Run #8 valid count mismatch")
        require(report["duplicate_group_count"] == 1, "Run #8 duplicate group mismatch")
        require(report["duplicate_member_count"] == 2, "Run #8 duplicate member mismatch")
        require(report["duplicate_suppressed_count"] == 1, "Run #8 duplicate suppressed mismatch")
        require(report["unique_post_dedup_count"] == 4, "Run #8 unique post-dedup mismatch")
        require(report["publish_candidate_count"] == 0, "Run #8 publish candidate mismatch")
        require(report["review_required_count"] == 0, "Run #8 review required mismatch")
        require(report["irrelevant_input_count"] == 5, "Run #8 irrelevant input mismatch")
        require(report["irrelevant_unique_count"] == 4, "Run #8 irrelevant unique mismatch")
        require(report["country_resolution_eligible_count"] == 0, "Run #8 country eligibility mismatch")
        require(report["country_resolution_success_ratio"] == "not_applicable", "Run #8 country ratio must be not_applicable")
        require(report["pipeline_shadow_ready"] is True, "Run #8 pipeline shadow ready mismatch")
        require(report["shadow_ready"] is True, "Run #8 backward shadow ready mismatch")
        require(report["content_sample_usable"] is False, "Run #8 content usability mismatch")
        require(report["candidate_manual_review_required"] is False, "Run #8 candidate manual review mismatch")
        require(report["artifact_audit_required"] is True, "Run #8 artifact audit should remain required")
        require(report["production_publish_allowed"] is False, "Run #8 production publish guard mismatch")
        groups = json.loads((Path(tmp) / "duplicate_groups.json").read_text(encoding="utf-8"))["items"]
        require(len(groups) == 1, "Run #8 duplicate artifact count mismatch")
        require(groups[0]["duplicate_reason"] == "cross_domain_syndicated_duplicate", "Run #8 duplicate reason mismatch")
        require(set(groups[0]["member_item_ids"]) == {"run8_log4j_wfsu", "run8_log4j_tpr"}, "Run #8 duplicate members mismatch")
        country_items = json.loads((Path(tmp) / "country_resolution.json").read_text(encoding="utf-8"))["items"]
        require(all(item["country_resolution_status"] == "not_applicable" for item in country_items), "Run #8 irrelevant country status mismatch")

    with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
        report_a = run_fixture_cli(Path(tmp_a))
        report_b = run_fixture_cli(Path(tmp_b))
        normalized_a = normalize_for_hash(load_artifact_set(Path(tmp_a)))
        normalized_b = normalize_for_hash(load_artifact_set(Path(tmp_b)))
        require(normalized_a == normalized_b, "fixture artifacts are not deterministic")
        require(normalize_for_hash(report_a) == normalize_for_hash(report_b), "fixture stdout reports are not deterministic")

    with tempfile.TemporaryDirectory() as tmp:
        missing = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "review_gdelt_webngrams_candidates.py"),
                "--input",
                str(Path(tmp) / "missing.json"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        require(missing.returncode == 2, "missing input should return code 2")

    print("GDELT WEBNGRAMS CANDIDATE REVIEW TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
