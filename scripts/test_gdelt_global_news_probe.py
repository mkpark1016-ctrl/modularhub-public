from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import requests
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.probe_gdelt_global_news import (  # noqa: E402
    RateLimiter,
    active_query_terms,
    bias_report,
    build_query_manifest,
    build_run_plan,
    build_country_query,
    build_gdelt_params,
    build_gdelt_url,
    build_integrated_query,
    canonical_url,
    checkpoint_compatibility,
    checkpoint_compatibility_from_payload,
    config_fingerprint,
    country_query_fingerprint,
    choose_countries_to_run,
    country_filter_matches,
    dedupe_metrics,
    generate_run_id,
    detect_noise_terms,
    load_checkpoint,
    load_json,
    local_query_tags,
    make_manual_review_articles,
    normalize_article,
    parse_retry_after,
    query_quality,
    request_gdelt,
    retry_delay_seconds,
    run_probe,
    validate_country_config,
)


COUNTRIES_PATH = ROOT / "config" / "global_news_countries.json"
QUERIES_PATH = ROOT / "config" / "global_news_queries.json"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "gdelt_news_sample.json"


class FakeResponse:
    def __init__(self, status_code: int, payload: Any = None, headers: dict[str, str] | None = None, url: str = "https://api.gdelt.test/doc") -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {"articles": []}
        self.headers = headers or {}
        self.url = url

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeTransport:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get(self, endpoint: str, **kwargs: Any) -> Any:
        self.calls.append({"endpoint": endpoint, **kwargs})
        if not self.responses:
            return FakeResponse(200, {"articles": []})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def no_sleep(_: float) -> None:
    return None


def main() -> int:
    countries_config = load_json(COUNTRIES_PATH)
    query_config = load_json(QUERIES_PATH)
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    countries = countries_config["countries"]
    query_packs = query_config["query_packs"]
    noise_terms = query_config["noise_terms"]

    require(len(countries) == 8, "expected 8 configured countries")
    expected_sourcecountries = {
        "GB": "unitedkingdom",
        "DE": "germany",
        "PL": "poland",
        "AU": "australia",
        "US": "unitedstates",
        "CN": "china",
        "SG": "singapore",
        "JP": "japan",
    }
    require({country["code"]: country.get("gdelt_sourcecountry") for country in countries} == expected_sourcecountries, "gdelt sourcecountry mapping mismatch")
    for configured_country in countries:
        validate_country_config(configured_country)
        country_query = build_country_query(configured_country, query_config)
        operator_value = country_query.split("sourcecountry:", 1)[1]
        require(operator_value == expected_sourcecountries[configured_country["code"]], "sourcecountry must use configured full value")
        require(operator_value != configured_country["code"], "internal ISO code leaked into sourcecountry operator")
        require(country_query.count(" OR ") == len(active_query_terms(query_config)) - 1, "OR block should be flat")
        require(country_query.count("sourcecountry:") == 1, "sourcecountry operator missing or duplicated")
        params = build_gdelt_params(configured_country, query_config, timespan="7d", maxrecords=50)
        final_url = build_gdelt_url(countries_config["endpoint"], configured_country, query_config, timespan="7d", maxrecords=50)
        parsed_query = parse_qs(urlsplit(final_url).query)
        require(parsed_query["query"][0] == params["query"], "URL-encoded query did not round-trip")
        require(parsed_query["mode"][0] == "artlist" and parsed_query["format"][0] == "json", "GDELT params missing")
    try:
        validate_country_config({"code": "XX", "name": "Broken", "enabled": True})
        raise AssertionError("invalid country config should fail")
    except ValueError as exc:
        require("gdelt_sourcecountry" in str(exc), "invalid country error should mention gdelt_sourcecountry")
    require([pack["id"] for pack in query_packs] == ["core_modular", "prefab_offsite", "applications"], "query pack mismatch")
    applications = next(pack for pack in query_packs if pack["id"] == "applications")
    require("modern methods of construction" not in applications["queries"], "broad MMC query must be disabled")
    require("industrialized construction" not in applications["queries"], "broad industrialized construction query must be disabled")
    require(any(item["query"] == "modern methods of construction" for item in applications["disabled_queries"]), "disabled query not preserved")

    country = next(item for item in countries if item["code"] == "US")
    query = build_integrated_query(query_config, "unitedstates")
    require("sourcecountry:unitedstates" in query, "sourcecountry filter missing")
    require('"modular construction"' in query and '"prefabricated housing"' in query, "integrated query terms missing")
    require("modern methods of construction" not in query, "disabled query leaked into integrated query")
    require(country_filter_matches(country, "United States"), "reported sourcecountry should match country")
    require(not country_filter_matches(country, "Germany"), "wrong country should not match")

    with tempfile.TemporaryDirectory() as tmp_print:
        print_result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "probe_gdelt_global_news.py"),
                "--print-queries",
                "--output-dir",
                tmp_print,
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        printed = json.loads(print_result.stdout)
        require(len(printed["countries"]) == 8, "--print-queries should print all countries")
        require(not any(Path(tmp_print).iterdir()), "--print-queries must not create artifacts")
        printed_map = {row["code"]: row for row in printed["countries"]}
        require(printed_map["GB"]["gdelt_sourcecountry"] == "unitedkingdom", "printed GB sourcecountry mismatch")
        require("sourcecountry:GB" not in printed_map["GB"]["query"], "printed query leaked GB code")
        require("modern methods of construction" not in printed_map["AU"]["query"], "printed query includes disabled term")

    base_config_fp = config_fingerprint(countries_config, query_config)
    require(len(base_config_fp) == 64, "config fingerprint should be full sha256")
    key_reordered_config = {
        "countries": countries_config["countries"],
        "circuit_breaker_consecutive_429": countries_config["circuit_breaker_consecutive_429"],
        "max_retries": countries_config["max_retries"],
        "retry_backoff_seconds": countries_config["retry_backoff_seconds"],
        "timespans": countries_config["timespans"],
        "maxrecords": countries_config["maxrecords"],
        "request_interval_seconds": countries_config["request_interval_seconds"],
        "endpoint": countries_config["endpoint"],
        "provider": countries_config["provider"],
    }
    require(config_fingerprint(key_reordered_config, query_config) == base_config_fp, "JSON key order should not change config fingerprint")
    compact_roundtrip_config = json.loads(json.dumps(countries_config, separators=(",", ":")))
    require(config_fingerprint(compact_roundtrip_config, query_config) == base_config_fp, "JSON formatting should not change config fingerprint")
    reordered_countries_config = json.loads(json.dumps(countries_config))
    reordered_countries_config["countries"] = list(reversed(reordered_countries_config["countries"]))
    require(config_fingerprint(reordered_countries_config, query_config) == base_config_fp, "country order should not change config fingerprint")
    reordered_query_config = json.loads(json.dumps(query_config))
    reordered_query_config["query_packs"] = list(reversed(reordered_query_config["query_packs"]))
    require(config_fingerprint(countries_config, reordered_query_config) == base_config_fp, "query pack order should not change config fingerprint")
    changed_query_config = json.loads(json.dumps(query_config))
    changed_query_config["query_packs"][0]["queries"][0] = "modular construction changed"
    require(config_fingerprint(countries_config, changed_query_config) != base_config_fp, "changed query should change config fingerprint")
    changed_enabled_config = json.loads(json.dumps(countries_config))
    changed_enabled_config["countries"][0]["enabled"] = False
    require(config_fingerprint(changed_enabled_config, query_config) != base_config_fp, "enabled change should change config fingerprint")

    us_query_fp = country_query_fingerprint(country, query_config, timespan="7d", maxrecords=50)
    changed_us_config = json.loads(json.dumps(countries_config))
    for item in changed_us_config["countries"]:
        if item["code"] == "US":
            item["gdelt_sourcecountry"] = "usa"
    changed_us = next(item for item in changed_us_config["countries"] if item["code"] == "US")
    changed_gb = next(item for item in changed_us_config["countries"] if item["code"] == "GB")
    require(country_query_fingerprint(changed_us, query_config, timespan="7d", maxrecords=50) != us_query_fp, "sourcecountry change should change that country query fingerprint")
    require(
        country_query_fingerprint(changed_gb, query_config, timespan="7d", maxrecords=50)
        == country_query_fingerprint(next(item for item in countries if item["code"] == "GB"), query_config, timespan="7d", maxrecords=50),
        "other country query fingerprint should remain unchanged",
    )

    manifest = build_query_manifest(countries_config, query_config)
    require(manifest["config_fingerprint"] == base_config_fp, "manifest config fingerprint mismatch")
    require(manifest["run_id"].endswith(manifest["config_fingerprint_short"]), "run_id should include short fingerprint")
    fixed_run_id = generate_run_id(base_config_fp, now=datetime(2026, 6, 26, 0, 0, tzinfo=timezone.utc))
    require(fixed_run_id == f"20260626T000000Z-{base_config_fp[:12]}", "deterministic run_id format mismatch")
    later_run_id = generate_run_id(base_config_fp, now=datetime(2026, 6, 26, 0, 0, 1, tzinfo=timezone.utc))
    require(later_run_id != fixed_run_id, "different execution times should produce different run_ids")
    require(fixed_run_id.endswith("Z-" + base_config_fp[:12]), "run_id must contain UTC Z marker and hyphen separator")
    require(not any(ch in fixed_run_id for ch in '<>:"/\\|?*'), "run_id must be safe for Windows filenames")
    require(len({manifest["run_id"], *[manifest["run_id"] for _ in manifest["countries"]]}) == 1, "one manifest should use one run_id")
    compatible_checkpoint = {
        "schema_version": manifest["schema_version"],
        "run_id": manifest["run_id"],
        "created_at": manifest["generated_at"],
        "updated_at": manifest["generated_at"],
        "config_fingerprint": manifest["config_fingerprint"],
        "probe_version": manifest["probe_version"],
        "countries": {
            row["code"]: {
                "query_fingerprint": row["query_fingerprint"],
                "status": "success",
                "attempt_count": 1,
                "last_http_status": 200,
                "last_error_type": "",
            }
            for row in manifest["countries"]
        },
    }
    compatible_state = checkpoint_compatibility_from_payload(compatible_checkpoint, manifest)
    require(compatible_state["status"] == "compatible" and compatible_state["resume_possible"], "compatible checkpoint rejected")
    unsupported_checkpoint = dict(compatible_checkpoint)
    unsupported_checkpoint["schema_version"] = 999
    unsupported_state = checkpoint_compatibility_from_payload(unsupported_checkpoint, manifest)
    require(unsupported_state["status"] == "unsupported_schema" and not unsupported_state["resume_possible"], "schema mismatch should be unsupported")
    stale_config_checkpoint = dict(compatible_checkpoint)
    stale_config_checkpoint["config_fingerprint"] = "0" * 64
    stale_config_state = checkpoint_compatibility_from_payload(stale_config_checkpoint, manifest)
    require(stale_config_state["status"] == "stale_config" and not stale_config_state["resume_possible"], "config mismatch should be stale")
    stale_query_checkpoint = json.loads(json.dumps(compatible_checkpoint))
    stale_query_checkpoint["countries"]["US"]["query_fingerprint"] = "1" * 64
    stale_query_state = checkpoint_compatibility_from_payload(stale_query_checkpoint, manifest)
    require(stale_query_state["status"] == "stale_query" and not stale_query_state["resume_possible"], "query mismatch should be stale")
    corrupt_state = checkpoint_compatibility_from_payload(["not", "object"], manifest)
    require(corrupt_state["status"] == "corrupt" and not corrupt_state["resume_possible"], "non-object checkpoint should be corrupt")
    with tempfile.TemporaryDirectory() as tmp_plan:
        tmpdir = Path(tmp_plan)
        missing_state = checkpoint_compatibility(tmpdir / "checkpoint.json", manifest)
        require(missing_state["status"] == "missing" and not missing_state["resume_possible"], "missing checkpoint status mismatch")
        (tmpdir / "checkpoint.json").write_text("{", encoding="utf-8")
        corrupt_file_state = checkpoint_compatibility(tmpdir / "checkpoint.json", manifest)
        require(corrupt_file_state["status"] == "corrupt" and not corrupt_file_state["resume_possible"], "corrupt checkpoint status mismatch")

    with tempfile.TemporaryDirectory() as tmp_plan:
        plan_result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "probe_gdelt_global_news.py"),
                "--print-run-plan",
                "--output-dir",
                tmp_plan,
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        plan = json.loads(plan_result.stdout)
        require(plan["checkpoint"]["status"] == "missing", "--print-run-plan checkpoint status mismatch")
        require(plan["planned_country_count"] == 8, "--print-run-plan country count mismatch")
        require(plan["base_http_requests_per_country"] == 1, "--print-run-plan base per-country count missing")
        require(plan["max_http_requests_per_country"] == 10, "--print-run-plan max per-country count mismatch")
        require(plan["expected_base_http_requests"] == 8, "--print-run-plan expected base request count missing")
        require(plan["expected_max_http_requests"] == 80, "--print-run-plan expected max request count mismatch")
        require(":\\" not in plan["checkpoint"]["path"], "--print-run-plan must not expose local absolute paths")
        require(not any(Path(tmp_plan).iterdir()), "--print-run-plan must not create artifacts")
        direct_plan = build_run_plan(countries_config, query_config, output_dir=Path(tmp_plan))
        require(direct_plan["config_fingerprint"] == plan["config_fingerprint"], "direct run plan mismatch")

    require(parse_retry_after("30") == 30.0, "numeric Retry-After parse failed")
    now = datetime(2026, 6, 26, 0, 0, tzinfo=timezone.utc)
    retry_at = now + timedelta(seconds=90)
    retry_header = retry_at.strftime("%a, %d %b %Y %H:%M:%S GMT")
    require(round(parse_retry_after(retry_header, now=now) or 0) == 90, "HTTP-date Retry-After parse failed")
    retry_delay, retry_after = retry_delay_seconds(
        attempt=1,
        retry_after_header=None,
        retry_backoff_seconds=[30, 60, 120, 240],
        rng=__import__("random").Random(1),
        jitter_seconds=0,
    )
    require(retry_delay == 30 and retry_after is None, "default backoff failed")

    limiter = RateLimiter(12, sleep_func=no_sleep)
    fake = FakeTransport([FakeResponse(429, headers={"Retry-After": "1"}), FakeResponse(200, {"articles": fixture["articles"][:1]})])
    response = request_gdelt(
        "https://api.gdelt.test/doc",
        query,
        country_code="US",
        timespan="7d",
        maxrecords=50,
        timeout=1,
        rate_limiter=limiter,
        retry_backoff_seconds=[30, 60, 120, 240],
        max_retries=4,
        get_func=fake.get,
        sleep_func=no_sleep,
        jitter_seconds=0,
    )
    require(response["status"] == "success", "429 retry should recover")
    require(len(fake.calls) == 2, "retry call count mismatch")
    require(response["attempts"][0]["scheduled_retry_delay_seconds"] == 1, "Retry-After delay not used")

    limiter = RateLimiter(0, sleep_func=no_sleep)
    fake = FakeTransport([FakeResponse(429), FakeResponse(429)])
    response = request_gdelt(
        "https://api.gdelt.test/doc",
        query,
        country_code="US",
        timespan="7d",
        maxrecords=50,
        timeout=1,
        rate_limiter=limiter,
        retry_backoff_seconds=[30, 60, 120, 240],
        max_retries=1,
        get_func=fake.get,
        sleep_func=no_sleep,
        jitter_seconds=0,
    )
    require(response["status"] == "provider_rate_limited", "max retry exceeded should rate-limit")
    require(response["attempts"][-1]["will_retry"] is False, "final 429 must not retry")

    fake = FakeTransport([requests.Timeout("timeout")])
    response = request_gdelt(
        "https://api.gdelt.test/doc",
        query,
        country_code="US",
        timespan="7d",
        maxrecords=50,
        timeout=1,
        rate_limiter=RateLimiter(0, sleep_func=no_sleep),
        retry_backoff_seconds=[30],
        max_retries=0,
        get_func=fake.get,
        sleep_func=no_sleep,
        jitter_seconds=0,
    )
    require(response["status"] == "provider_timeout", "timeout status mismatch")

    articles = fixture["articles"]
    normalized = [
        normalize_article(article, country=country, query_config=query_config, sourcecountry_filter="unitedstates", timespan="7d")
        for article in articles
    ]
    require(normalized[0]["canonical_url"] == "https://example-news.invalid/building/modular-housing", "tracking params not removed")
    require(normalized[0]["summary"] == "" and normalized[0]["description"] == "", "summary must not be generated")
    require("core_modular" in normalized[0]["matched_query_groups"], "core modular local tag missing")
    require("applications" in normalized[0]["matched_query_groups"], "applications local tag missing")
    require("software" in detect_noise_terms(articles[1], noise_terms), "software noise term not detected")
    require(normalized[1]["suspected_noise"], "suspected noise not tagged")

    duplicate_article = dict(normalized[0])
    duplicate_article["matched_query_groups"] = ["prefab_offsite"]
    metrics = dedupe_metrics(normalized + [duplicate_article])
    require(metrics["canonical_url_duplicates"] == 1, "canonical duplicate not counted")
    require(metrics["query_pack_cross_duplicates"] == 1, "query pack duplicate not counted")
    quality = query_quality(normalized + [duplicate_article], query_packs)
    require(quality["core_modular"]["article_observations"] >= 1, "query quality grouping mismatch")
    manual_review = make_manual_review_articles(normalized + [duplicate_article])
    require(manual_review[0]["reviewer_decision"] == "" and manual_review[0]["reviewer_note"] == "", "review fields must be blank")
    require(len(manual_review) == 2, "manual review should dedupe canonical duplicates")
    bias = bias_report(normalized + [duplicate_article], [{"status": "success", "attempts": [{"http_status": 429}, {"http_status": 200}]}])
    require(bias["rate_limit_event_count"] == 1 and bias["retry_success_count"] == 1, "bias retry metrics mismatch")

    checkpoint = {"version": 1, "countries": {"US": {"status": "success"}, "GB": {"status": "provider_rate_limited"}}}
    selected = choose_countries_to_run(countries, checkpoint, resume=True, all_countries=False, force_countries=[], max_countries=None, seed=1)
    selected_codes = {item["code"] for item in selected}
    require("US" not in selected_codes and "GB" in selected_codes, "resume should skip success and include failed")
    forced = choose_countries_to_run(countries, checkpoint, resume=False, all_countries=False, force_countries=["US"], max_countries=None, seed=1)
    require([item["code"] for item in forced] == ["US"], "force country should only run requested country")
    require([item["code"] for item in choose_countries_to_run(countries, checkpoint, resume=False, all_countries=True, force_countries=[], max_countries=2, seed=123)] == [item["code"] for item in choose_countries_to_run(countries, checkpoint, resume=False, all_countries=True, force_countries=[], max_countries=2, seed=123)], "seeded order should reproduce")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        fake = FakeTransport([
            FakeResponse(200, {"articles": []}),
            FakeResponse(200, {"articles": fixture["articles"][:1]}),
        ])
        report = run_probe(
            max_countries=1,
            output_dir=tmpdir,
            request_interval=0,
            seed=1,
            get_func=fake.get,
            sleep_func=no_sleep,
            jitter_seconds=0,
        )
        require(report["api_call_stats"]["initial_request_count"] == 2, "30d fallback should run only after 7d no matches")
        require((tmpdir / "checkpoint.json").exists(), "checkpoint not written")
        require((tmpdir / "manual_review_articles.csv").exists(), "manual review csv not written")

        fake = FakeTransport([FakeResponse(429), FakeResponse(429), FakeResponse(429), FakeResponse(429), FakeResponse(429)])
        report = run_probe(
            max_countries=1,
            output_dir=tmpdir,
            request_interval=0,
            seed=1,
            all_countries=True,
            get_func=fake.get,
            sleep_func=no_sleep,
            jitter_seconds=0,
        )
        require(report["api_call_stats"]["initial_request_count"] == 1, "429 must not trigger 30d fallback")
        require(any(country["status"] == "provider_rate_limited" for country in report["countries"]), "429 country status mismatch")

    corrupt_path = Path(tempfile.mkdtemp()) / "checkpoint.json"
    corrupt_path.write_text("{", encoding="utf-8")
    require(load_checkpoint(corrupt_path).get("checkpoint_warning"), "corrupt checkpoint should restart safely")

    print("GDELT GLOBAL NEWS PROBE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
