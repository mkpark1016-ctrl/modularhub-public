from __future__ import annotations

import gzip
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import probe_gdelt_webngrams as probe  # noqa: E402
from scripts.probe_gdelt_webngrams import (  # noqa: E402
    FIXTURE_GAL,
    FIXTURE_WEBNGRAMS,
    canonicalize_url,
    join_gal,
    print_plan,
    read_fixture_lines,
    run_fixture,
    run_live,
    scan_webngrams,
    validate_source_url,
    validate_timestamp,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class FakeResponse:
    def __init__(self, status_code: int, body: bytes, *, content_type: str = "application/gzip", headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        if headers:
            self.headers.update(headers)
        self.raw = io.BytesIO(body)

    def close(self) -> None:
        self.raw.close()


class BrokenRawResponse(FakeResponse):
    def __init__(self) -> None:
        super().__init__(200, b"", content_type="application/gzip")

    @property
    def raw(self):  # type: ignore[override]
        class BrokenRaw:
            def read(self, size: int = -1) -> bytes:
                raise OSError("simulated local stream failure")

        return BrokenRaw()

    @raw.setter
    def raw(self, value: object) -> None:
        pass


def gzip_jsonl(lines: list[str]) -> bytes:
    return gzip.compress(("\n".join(lines) + "\n").encode("utf-8"))


def live_jsonl_lines(path: Path, *, timestamp: str = "20211215000100") -> list[str]:
    lines: list[str] = []
    for line in read_fixture_lines(path):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payload["date"] = timestamp
            lines.append(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return lines


def run_live_with_fake(items: list[object], tmp: Path) -> tuple[dict[str, object], list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []
    original_get = probe.requests.get

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        calls.append({"url": url, "kwargs": kwargs})
        require(kwargs.get("allow_redirects") is False, "redirects must be disabled")
        require("verify" not in kwargs, "verify must not be overridden")
        headers = kwargs.get("headers")
        require(isinstance(headers, dict), "headers must be explicit")
        require(headers.get("Accept-Encoding") == "identity", "compressed transport must not be double-encoded")
        for forbidden_header in ["Authorization", "Cookie", "Proxy-Authorization", "Referer"]:
            require(forbidden_header not in headers, f"{forbidden_header} header must not be sent")
        index = len(calls) - 1
        if index >= len(items):
            raise AssertionError("unexpected extra HTTP request")
        item = items[index]
        if callable(item):
            item = item()
        if isinstance(item, BaseException):
            raise item
        return item  # type: ignore[return-value]

    probe.requests.get = fake_get  # type: ignore[assignment]
    try:
        report = run_live("20211215000100", max_candidates=20, timeout=0.1, output_dir=tmp)
    finally:
        probe.requests.get = original_get  # type: ignore[assignment]
    return report, calls


def require_failure_artifacts(tmp: Path, *, expected_failure: str, expected_source: str) -> dict[str, object]:
    for filename in [
        "report.json",
        "report.md",
        "candidates.json",
        "manual_review.csv",
        "download_manifest.json",
        "failure_report.json",
        "failure_report.md",
    ]:
        require((tmp / filename).exists(), f"{filename} missing for failed live probe")
    failure = json.loads((tmp / "failure_report.json").read_text(encoding="utf-8"))
    require(failure["failure_type"] == expected_failure, f"failure type mismatch: {failure}")
    require(failure["failed_source"] == expected_source, f"failed source mismatch: {failure}")
    require(failure["doc_api_request_count"] == 0, "failed live probe must not call DOC API")
    require(failure["retry_count"] == 0, "failed live probe must not retry")
    require(failure["fallback_count"] == 0, "failed live probe must not fallback")
    return failure


def main() -> int:
    require(validate_timestamp("20260627000000") == "20260627000000", "timestamp validation mismatch")
    try:
        validate_timestamp("2026-06-27")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid timestamp accepted")

    require(
        canonicalize_url("https://Example-News.com/build/modular-homes?utm_source=x&b=2&a=1#frag")
        == "https://example-news.com/build/modular-homes?a=1&b=2",
        "canonical URL mismatch",
    )

    plan = print_plan("20260627000000", max_candidates=20)
    require(plan["network_request_count"] == 0, "print plan must not request")
    require(plan["doc_api_request_count"] == 0, "print plan must not call DOC API")
    require(plan["planned_webngrams_request_count"] == 1, "planned web request count mismatch")
    require(plan["planned_gal_request_count"] == 1, "planned GAL request count mismatch")
    require(plan["planned_total_request_count"] == 2, "planned total request count mismatch")
    require(plan["fallback_timestamp_count"] == 0, "fallback timestamp count mismatch")
    require("api.gdeltproject.org/api/v2/doc/doc" not in json.dumps(plan), "DOC API leaked into plan")
    require(plan["webngrams_url"] == "http://data.gdeltproject.org/gdeltv3/webngrams/20260627000000.webngrams.json.gz", "webngrams HTTP URL mismatch")
    require(plan["gal_url"] == "http://data.gdeltproject.org/gdeltv3/gal/20260627000000.gal.json.gz", "GAL HTTP URL mismatch")
    require(plan["transport_scheme"] == "http", "transport scheme mismatch")
    require(plan["redirects_allowed"] is False, "redirects must be disabled")
    require(plan["webngrams_url"].endswith(".webngrams.json.gz"), "webngrams URL mismatch")
    require(plan["gal_url"].endswith(".gal.json.gz"), "GAL URL mismatch")

    ok, reason, _details = validate_source_url("webngrams", plan["webngrams_url"], timestamp="20260627000000")
    require(ok and not reason, "valid Web NGrams source URL rejected")
    ok, reason, _details = validate_source_url("gal", plan["gal_url"], timestamp="20260627000000")
    require(ok and not reason, "valid GAL source URL rejected")
    invalid_urls = [
        ("webngrams", "https://data.gdeltproject.org/gdeltv3/webngrams/20260627000000.webngrams.json.gz"),
        ("webngrams", "http://evil.example/gdeltv3/webngrams/20260627000000.webngrams.json.gz"),
        ("webngrams", "http://data.gdeltproject.org.evil/gdeltv3/webngrams/20260627000000.webngrams.json.gz"),
        ("webngrams", "http://user:pass@data.gdeltproject.org/gdeltv3/webngrams/20260627000000.webngrams.json.gz"),
        ("webngrams", "http://data.gdeltproject.org/gdeltv3/webngrams/20260627000000.webngrams.json.gz?a=1"),
        ("webngrams", "http://data.gdeltproject.org/gdeltv3/webngrams/20260627000000.webngrams.json.gz#x"),
        ("webngrams", "http://data.gdeltproject.org/gdeltv3/webngrams/../gal/20260627000000.gal.json.gz"),
        ("webngrams", "http://data.gdeltproject.org/gdeltv3/webngrams/19990101000000.webngrams.json.gz"),
    ]
    for source_name, url in invalid_urls:
        ok, reason, _details = validate_source_url(source_name, url, timestamp="20260627000000")
        require(not ok and reason, f"invalid URL accepted: {url}")

    web_lines = read_fixture_lines(FIXTURE_WEBNGRAMS)
    candidates, smoke_samples, stats = scan_webngrams(web_lines, timestamp="20260627000000", max_candidates=20)
    require(stats["scanned_row_count"] == 8, "web scanned row count mismatch")
    require(stats["malformed_row_count"] == 2, "web malformed count mismatch")
    require(stats["keyword_match_count"] == 7, "keyword match count mismatch")
    require(stats["duplicate_removed_count"] == 1, "duplicate count mismatch")
    require(len(candidates) == 6, "unique candidates mismatch")
    require(len(smoke_samples) == 5, "smoke sample size mismatch")
    require(stats["join_smoke_sample_size"] == 5, "smoke sample stat mismatch")
    require(any(candidate["matched_phrase"] == "modular construction" for candidate in candidates), "phrase match missing")
    require(any(candidate["matched_keyword"] == "prefab" for candidate in candidates), "keyword match missing")
    require(any(candidate["ngram_type"] == 2 for candidate in candidates), "type=2 candidate missing")
    require(any(candidate["suspected_noise"] and candidate["noise_reason"] == "software" for candidate in candidates), "noise candidate missing")

    gal_stats = join_gal(read_fixture_lines(FIXTURE_GAL), candidates, smoke_samples)
    require(gal_stats["gal_scanned_row_count"] == 4, "GAL scanned count mismatch")
    require(gal_stats["gal_join_success_count"] == 4, "GAL join success mismatch")
    require(gal_stats["gal_join_failed_count"] == 2, "GAL join failure mismatch")
    require(gal_stats["join_smoke_gal_joined_count"] == 4, "smoke GAL join success mismatch")
    require(gal_stats["join_smoke_gal_missing_count"] == 1, "smoke GAL join missing mismatch")
    require(gal_stats["gal_malformed_row_count"] == 1, "GAL malformed count mismatch")
    require(all(candidate["country_status"] == "unresolved" for candidate in candidates), "country should remain unresolved")
    require(all(candidate["country_code"] is None for candidate in candidates), "country code should remain null")

    empty_candidates, empty_smoke, empty_stats = scan_webngrams(
        ['{"date":"20260627000000","ngram":"ordinary","pre":"local","post":"bridge","lang":"en","type":1,"url":"https://example.com/a"}'],
        timestamp="20260627000000",
        max_candidates=20,
    )
    require(not empty_candidates and empty_stats["keyword_match_count"] == 0, "empty result mismatch")
    require(len(empty_smoke) == 1, "empty keyword scan should still collect smoke sample")

    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "probe_gdelt_webngrams.py"),
                "--print-plan",
                "--timestamp",
                "20260627000000",
                "--output-dir",
                tmp,
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        printed = json.loads(result.stdout)
        require(printed["network_request_count"] == 0, "--print-plan network count mismatch")
        require(printed["file_created_count"] == 0, "--print-plan file count mismatch")
        require(not any(Path(tmp).iterdir()), "--print-plan must not create artifacts")

    with tempfile.TemporaryDirectory() as tmp:
        report = run_fixture(max_candidates=20, output_dir=Path(tmp))
        require(report["status"] == "success", "fixture probe should succeed")
        require(report["http_request_count"] == 0, "fixture probe must not request")
        require(report["network_request_count"] == 0, "fixture probe network count mismatch")
        require(report["doc_api_request_count"] == 0, "fixture probe must not call DOC API")
        require(report["unique_candidate_count"] == 6, "fixture candidate count mismatch")
        require(report["duplicate_removed_count"] == 1, "fixture duplicate count mismatch")
        require(report["gal_join_success_count"] == 4, "fixture GAL success mismatch")
        require(report["gal_join_failed_count"] == 2, "fixture GAL failure mismatch")
        require(report["join_smoke_sample_size"] == 5, "fixture smoke size mismatch")
        require(report["join_smoke_gal_joined_count"] == 4, "fixture smoke join mismatch")
        require(report["transport_acceptance_passed"] is True, "fixture transport acceptance mismatch")
        require(report["keyword_observation"] == "matched", "fixture keyword observation mismatch")
        require(report["suspected_noise_count"] == 1, "fixture noise count mismatch")
        require(report["public_json_unchanged"], "fixture mutated public JSON")
        require(report["db_unchanged"], "fixture mutated DB")
        require(report["env_unchanged"], "fixture mutated .env")
        for filename in ["report.json", "report.md", "candidates.json", "manual_review.csv", "download_manifest.json"]:
            require((Path(tmp) / filename).exists(), f"{filename} missing")
        stored = json.loads((Path(tmp) / "candidates.json").read_text(encoding="utf-8"))
        require(len(stored) == 6, "stored candidate count mismatch")

    def live_web() -> FakeResponse:
        return FakeResponse(200, gzip_jsonl(live_jsonl_lines(FIXTURE_WEBNGRAMS)))

    def live_gal() -> FakeResponse:
        return FakeResponse(200, gzip_jsonl(live_jsonl_lines(FIXTURE_GAL)))

    failure_cases = [
        ("web timeout", [probe.requests.Timeout("timeout")], "provider_timeout", "webngrams", 1, 0, 0),
        ("web connection", [probe.requests.ConnectionError("connection")], "provider_connection_error", "webngrams", 1, 0, 0),
        ("web ssl", [probe.requests.exceptions.SSLError("ssl")], "provider_ssl_error", "webngrams", 1, 0, 0),
        ("web request exception", [probe.requests.RequestException("request")], "provider_request_error", "webngrams", 1, 0, 0),
        ("web local stream", [BrokenRawResponse()], "local_io_error", "webngrams", 1, 0, 0),
        ("web redirect 301", [FakeResponse(301, b"", content_type="text/plain", headers={"Location": "http://data.gdeltproject.org/redirect"})], "provider_redirect_rejected", "webngrams", 1, 1, 0),
        ("web redirect 302", [FakeResponse(302, b"", content_type="text/plain", headers={"Location": "http://data.gdeltproject.org/redirect"})], "provider_redirect_rejected", "webngrams", 1, 1, 0),
        ("web 404", [FakeResponse(404, b"missing", content_type="text/plain")], "timestamp_missing", "webngrams", 1, 1, 0),
        ("web 403", [FakeResponse(403, b"forbidden", content_type="text/plain")], "provider_access_limited", "webngrams", 1, 1, 0),
        ("web 429", [FakeResponse(429, b"rate limited", content_type="text/plain")], "provider_access_limited", "webngrams", 1, 1, 0),
        ("web html", [FakeResponse(200, b"<html>nope</html>", content_type="text/html")], "invalid_response", "webngrams", 1, 1, 0),
        ("web empty", [FakeResponse(200, b"")], "parser_or_archive_failure", "webngrams", 1, 1, 0),
        ("web invalid gzip", [FakeResponse(200, b"not gzip")], "parser_or_archive_failure", "webngrams", 1, 1, 0),
        ("gal timeout", [live_web, probe.requests.Timeout("timeout")], "provider_timeout", "gal", 2, 1, 1),
        ("gal connection", [live_web, probe.requests.ConnectionError("connection")], "provider_connection_error", "gal", 2, 1, 1),
        ("gal 404", [live_web, FakeResponse(404, b"missing", content_type="text/plain")], "timestamp_missing", "gal", 2, 2, 1),
        ("unexpected exception", [ValueError("surprise")], "unexpected_probe_error", "webngrams", 1, 0, 0),
    ]
    for name, items, failure_type, failed_source, attempts, responses, gal_count in failure_cases:
        with tempfile.TemporaryDirectory() as tmp:
            report, calls = run_live_with_fake(items, Path(tmp))
            require(report["status"] == failure_type, f"{name}: status mismatch {report}")
            require(report["failure_type"] == failure_type, f"{name}: failure_type mismatch")
            require(report["failed_source"] == failed_source, f"{name}: failed_source mismatch")
            require(report["request_attempt_count"] == attempts, f"{name}: attempt count mismatch")
            require(report["network_request_count"] == attempts, f"{name}: network count mismatch")
            require(report["http_response_count"] == responses, f"{name}: response count mismatch")
            require(report["webngrams_request_count"] == 1, f"{name}: web count mismatch")
            require(report["gal_request_count"] == gal_count, f"{name}: GAL count mismatch")
            require(report["doc_api_request_count"] == 0, f"{name}: DOC API count mismatch")
            require(report["retry_count"] == 0 and report["fallback_count"] == 0, f"{name}: retry/fallback mismatch")
            require(report["production_publish_allowed"] is False, f"{name}: production publish must stay disabled")
            failure = require_failure_artifacts(Path(tmp), expected_failure=failure_type, expected_source=failed_source)
            require(failure["request_attempt_count"] == attempts, f"{name}: failure report attempt mismatch")
            require(len(calls) == attempts, f"{name}: fake request count mismatch")

    with tempfile.TemporaryDirectory() as tmp:
        report, calls = run_live_with_fake([live_web, live_gal], Path(tmp))
        require(report["status"] == "success", "successful live fake should succeed")
        require(report["network_request_count"] == 2, "successful fake request count mismatch")
        require(report["http_response_count"] == 2, "successful fake response count mismatch")
        require(report["transport_acceptance_passed"] is True, "successful fake transport mismatch")
        require(report["transport_scheme"] == "http", "successful fake transport scheme mismatch")
        require(report["endpoint_contract_valid"] is True, "successful fake endpoint contract mismatch")
        require(report["redirect_count"] == 0 and report["redirect_followed"] is False, "successful fake redirect mismatch")
        require(report["source_integrity_checks_passed"] is True, "successful fake integrity mismatch")
        require(report["compressed_bytes"] > 0 and report["decompressed_bytes"] > 0, "successful fake byte counters missing")
        require(report["compressed_sha256"]["webngrams"], "successful fake Web NGrams hash missing")
        require(report["compressed_sha256"]["gal"], "successful fake GAL hash missing")
        require(not (Path(tmp) / "failure_report.json").exists(), "successful fake must not write failure report")
        require(len(calls) == 2, "successful fake should request two files")
        require(calls[0]["url"] == "http://data.gdeltproject.org/gdeltv3/webngrams/20211215000100.webngrams.json.gz", "wrong Web NGrams URL requested")
        require(calls[1]["url"] == "http://data.gdeltproject.org/gdeltv3/gal/20211215000100.gal.json.gz", "wrong GAL URL requested")

    with tempfile.TemporaryDirectory() as tmp:
        report, _calls = run_live_with_fake([FakeResponse(200, b"\x1f\x8bnot-valid"), live_gal], Path(tmp))
        require(report["status"] == "parser_or_archive_failure", "parser failure status mismatch")
        require(report["failed_source"] == "parser", "parser failure source mismatch")
        require(report["network_request_count"] == 2, "parser failure request count mismatch")
        require_failure_artifacts(Path(tmp), expected_failure="parser_or_archive_failure", expected_source="parser")

    with tempfile.TemporaryDirectory() as tmp:
        report, _calls = run_live_with_fake([FakeResponse(200, gzip_jsonl(["not json"])), live_gal], Path(tmp))
        require(report["status"] == "parser_or_archive_failure", "invalid JSONL status mismatch")
        require(report["failed_source"] == "webngrams", "invalid JSONL source mismatch")
        require_failure_artifacts(Path(tmp), expected_failure="parser_or_archive_failure", expected_source="webngrams")

    wrong_timestamp = json.dumps(
        {
            "date": "19990101000000",
            "ngram": "modular",
            "pre": "new",
            "post": "construction project",
            "lang": "en",
            "type": 1,
            "url": "https://news.invalid/modular",
        }
    )
    with tempfile.TemporaryDirectory() as tmp:
        report, _calls = run_live_with_fake([FakeResponse(200, gzip_jsonl([wrong_timestamp])), live_gal], Path(tmp))
        require(report["status"] == "invalid_response", "timestamp mismatch status mismatch")
        require(report["failed_source"] == "webngrams", "timestamp mismatch source mismatch")
        require_failure_artifacts(Path(tmp), expected_failure="invalid_response", expected_source="webngrams")

    with tempfile.TemporaryDirectory() as tmp:
        original_limit = probe.MAX_DECOMPRESSED_BYTES
        probe.MAX_DECOMPRESSED_BYTES = 1
        try:
            report, _calls = run_live_with_fake([live_web, live_gal], Path(tmp))
        finally:
            probe.MAX_DECOMPRESSED_BYTES = original_limit
        require(report["status"] == "source_size_limit_exceeded", "decompressed size limit status mismatch")
        require(report["failed_source"] == "webngrams", "decompressed size limit source mismatch")
        require_failure_artifacts(Path(tmp), expected_failure="source_size_limit_exceeded", expected_source="webngrams")

    with tempfile.TemporaryDirectory() as tmp:
        original_limit = probe.MAX_COMPRESSED_BYTES
        probe.MAX_COMPRESSED_BYTES = 2
        try:
            report, _calls = run_live_with_fake([live_web, live_gal], Path(tmp))
        finally:
            probe.MAX_COMPRESSED_BYTES = original_limit
        require(report["status"] == "source_size_limit_exceeded", "compressed size limit status mismatch")
        require(report["failed_source"] == "webngrams", "compressed size limit source mismatch")
        require_failure_artifacts(Path(tmp), expected_failure="source_size_limit_exceeded", expected_source="webngrams")

    with tempfile.TemporaryDirectory() as tmp:
        original_limit = probe.MAX_JSONL_LINE_BYTES
        probe.MAX_JSONL_LINE_BYTES = 8
        try:
            report, _calls = run_live_with_fake([live_web, live_gal], Path(tmp))
        finally:
            probe.MAX_JSONL_LINE_BYTES = original_limit
        require(report["status"] == "source_size_limit_exceeded", "line size limit status mismatch")
        require(report["failed_source"] == "webngrams", "line size limit source mismatch")
        require_failure_artifacts(Path(tmp), expected_failure="source_size_limit_exceeded", expected_source="webngrams")

    with tempfile.TemporaryDirectory() as tmp:
        original_template = probe.WEBNGRAMS_TEMPLATE
        probe.WEBNGRAMS_TEMPLATE = "https://data.gdeltproject.org/gdeltv3/webngrams/{timestamp}.webngrams.json.gz"
        try:
            report, calls = run_live_with_fake([live_web], Path(tmp))
        finally:
            probe.WEBNGRAMS_TEMPLATE = original_template
        require(report["status"] == "source_contract_invalid", "source contract invalid status mismatch")
        require(report["failed_source"] == "webngrams", "source contract invalid source mismatch")
        require(report["network_request_count"] == 0, "source contract invalid must block before request")
        require(len(calls) == 0, "source contract invalid must not call requests.get")
        require_failure_artifacts(Path(tmp), expected_failure="source_contract_invalid", expected_source="webngrams")

    script_text = (ROOT / "scripts" / "probe_gdelt_webngrams.py").read_text(encoding="utf-8")
    require("api.gdeltproject.org/api/v2/doc/doc" not in script_text, "DOC API endpoint must not be used")
    lowered_script = script_text.lower()
    for forbidden in [
        "verify=false",
        "session.verify = false",
        "urllib3.disable_warnings",
        "pythonhttpsverify=0",
        "requests_ca_bundle=\"\"",
        "curl_ca_bundle=\"\"",
    ]:
        require(forbidden not in lowered_script, f"forbidden SSL bypass present: {forbidden}")

    print("GDELT WEBNGRAMS PROBE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
