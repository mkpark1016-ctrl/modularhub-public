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
    build_country_query,
    build_gdelt_params,
    build_gdelt_url,
    build_integrated_query,
    canonical_url,
    choose_countries_to_run,
    country_filter_matches,
    dedupe_metrics,
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
