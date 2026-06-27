from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_gdelt_provider_health import (  # noqa: E402
    EXIT_CODES,
    build_health_url,
    health_plan,
    provider_decision,
    run_live_health,
    show_cooldown,
    validate_health_query,
)


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: Any = None,
        *,
        text: str = "",
        headers: dict[str, str] | None = None,
        url: str = "https://api.gdeltproject.org/api/v2/doc/doc",
        history: list[Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {"articles": []}
        self.text = text
        self.headers = headers or {"Content-Type": "application/json"}
        self.url = url
        self.history = history or []

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeTransport:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> Any:
        self.calls.append({"url": url, **kwargs})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_case(response: Any, expected_status: str, **kwargs: Any) -> tuple[dict[str, Any], FakeTransport, Path]:
    transport = FakeTransport(response)
    tmpdir = Path(tempfile.mkdtemp())
    summary = run_live_health(country_code="AU", timeout=1, report_dir=tmpdir, get_func=transport.get, **kwargs)
    require(summary["status"] == expected_status, f"expected {expected_status}, got {summary['status']}")
    require(summary["request_count"] <= 1, "health check must issue at most one request")
    require(len(transport.calls) <= 1, "transport called more than once")
    require(summary["retry_count"] == 0, "health check must not retry")
    require(summary["public_json_unchanged"], "public JSON mutated")
    require(summary["db_unchanged"], "DB mutated")
    require(summary["env_unchanged"], ".env mutated")
    require(summary["checkpoint_unchanged"], "checkpoint mutated")
    require((tmpdir / "health.json").exists(), "health.json not written")
    require((tmpdir / "health.md").exists(), "health.md not written")
    return summary, transport, tmpdir


def main() -> int:
    plan = health_plan("AU")
    require(plan["country_code"] == "AU", "plan country mismatch")
    require(plan["sourcecountry"] == "australia", "sourcecountry mismatch")
    require(plan["request_count"] == 0 and plan["retry_count"] == 0, "plan must not request")
    require(plan["query_profile"] == "health", "plan should use health query profile")
    require(plan["query"] == "modular sourcecountry:australia", "AU health query mismatch")
    require(plan["raw_query_redacted"] == "modular sourcecountry:australia", "raw query mismatch")
    require(plan["production_query_pack_used"] is False, "health plan must not use production query pack")
    require(plan["query_preflight_passed"] is True, "default health query should pass preflight")
    require(plan["raw_query_length"] == len("modular sourcecountry:australia"), "raw query length mismatch")
    require(plan["encoded_query_length"] < 240 and plan["full_url_length"] < 1000, "health query budget mismatch")
    require(plan["sourcecountry_count"] == 1 and plan["boolean_or_count"] == 0 and plan["parenthesis_depth"] == 0, "health query complexity mismatch")
    require("mode=artlist" in plan["request_url_redacted"], "plan URL missing mode")
    require("modular+construction" not in plan["request_url_redacted"], "production query leaked into health URL")

    require(health_plan("GB")["query"] == "modular sourcecountry:unitedkingdom", "GB health query mismatch")
    require(health_plan("DE")["query"] == "modular sourcecountry:germany", "DE health query mismatch")
    require(health_plan("PL")["query"] == "modular sourcecountry:poland", "PL health query mismatch")
    require(health_plan("US")["query"] == "modular sourcecountry:unitedstates", "US health query mismatch")
    phrase_plan = health_plan("AU", health_term="", health_phrase="modular housing")
    require(phrase_plan["query"] == '"modular housing" sourcecountry:australia', "health phrase query mismatch")

    ok, reason = validate_health_query("modular sourcecountry:australia", build_health_url("https://api.gdelt.test/doc", "modular sourcecountry:australia"))
    require(ok and not reason, "valid health query rejected")
    for raw_query, expected_reason in [
        ("", "empty_health_query"),
        ("modular", "sourcecountry_count_not_one"),
        ("modular sourcecountry:australia sourcecountry:germany", "sourcecountry_count_not_one"),
        ("modular OR prefab OR offsite sourcecountry:australia", "too_many_boolean_or_terms"),
        ("((modular)) sourcecountry:australia", "nested_parentheses_not_allowed"),
        ("m" * 121 + " sourcecountry:australia", "raw_query_too_long_for_internal_budget"),
    ]:
        valid, reason = validate_health_query(raw_query, build_health_url("https://api.gdelt.test/doc", raw_query))
        require(not valid and reason == expected_reason, f"expected {expected_reason}, got {reason}")

    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_gdelt_provider_health.py"),
                "--country",
                "AU",
                "--print-plan",
                "--report-dir",
                tmp,
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        printed = json.loads(result.stdout)
        require(printed["status"] == "plan", "--print-plan status mismatch")
        require(printed["query_profile"] == "health", "--print-plan should use health profile")
        require(printed["query"] == "modular sourcecountry:australia", "--print-plan health query mismatch")
        require(printed["production_query_pack_used"] is False, "--print-plan must not use production query")
        require(printed["query_preflight_passed"] is True, "--print-plan preflight mismatch")
        require(printed["file_created_count"] == 0, "--print-plan file count mismatch")
        require(printed["state_file"].endswith("last_attempt.json"), "--print-plan state file mismatch")
        require(printed["cooldown_active"] is False, "--print-plan unexpected cooldown")
        require(printed["request_count"] == 0, "--print-plan must not request")
        require(not any(Path(tmp).iterdir()), "--print-plan must not create files")

    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_gdelt_provider_health.py"),
                "--country",
                "AU",
                "--show-cooldown",
                "--report-dir",
                tmp,
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        cooldown = json.loads(result.stdout)
        require(cooldown["actual_request_count"] == 0, "--show-cooldown must not request")
        require(cooldown["cooldown_active"] is False, "empty cooldown should not be active")
        require(cooldown["provider_state"] == "unknown", "empty provider state should be unknown")
        require(not any(Path(tmp).iterdir()), "--show-cooldown must not create files")

    with tempfile.TemporaryDirectory() as tmp:
        decision = provider_decision("AU", report_dir=Path(tmp), cooldown_seconds=3600)
        require(decision["actual_request_count"] == 0, "provider decision must not request")
        require(decision["provider_state"] == "unknown", "missing state should be unknown")
        require(decision["10.10-A.4_ready"] is False, "missing state should not be A.4 ready")
        require(decision["10.10-B1_ready"] is False, "missing state should not be B1 ready")
        require(not any(Path(tmp).iterdir()), "provider decision must not create files")

    with tempfile.TemporaryDirectory() as tmp:
        conflict = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_gdelt_provider_health.py"),
                "--country",
                "AU",
                "--health-term",
                "modular",
                "--health-phrase",
                "modular housing",
                "--print-plan",
                "--report-dir",
                tmp,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        require(conflict.returncode != 0, "health term and phrase should be mutually exclusive")
        require(not any(Path(tmp).iterdir()), "invalid print-plan args must not create files")

    summary, transport, _ = run_case(FakeResponse(200, {"articles": [{"title": "Modular housing"}]}), "healthy")
    require(summary["article_count"] == 1 and summary["schema_valid"], "healthy schema mismatch")
    require(EXIT_CODES[summary["status"]] == 0, "healthy exit code mismatch")
    require("allow_redirects" in transport.calls[0] and transport.calls[0]["allow_redirects"] is True, "redirect option missing")

    tmpdir = Path(tempfile.mkdtemp())
    first_transport = FakeTransport(FakeResponse(200, {"articles": [{"title": "Modular housing"}]}))
    first = run_live_health(country_code="AU", timeout=1, report_dir=tmpdir, get_func=first_transport.get)
    require(first["status"] == "healthy", "first healthy cooldown setup failed")
    state = json.loads((tmpdir / "last_attempt.json").read_text(encoding="utf-8"))
    require(state["local_cooldown_seconds"] == 10, "normal cooldown seconds mismatch")
    second_transport = FakeTransport(FakeResponse(200, {"articles": [{"title": "Should not request"}]}))
    second = run_live_health(country_code="AU", timeout=1, report_dir=tmpdir, get_func=second_transport.get)
    require(second["status"] == "cooldown_active", "normal cooldown should block immediate rerun")
    require(second["actual_request_count"] == 0 and len(second_transport.calls) == 0, "cooldown_active must not call transport")
    visible = show_cooldown("AU", report_dir=tmpdir, cooldown_seconds=3600)
    require(visible["cooldown_active"], "show cooldown should report active normal cooldown")

    summary, _, _ = run_case(FakeResponse(200, {"articles": []}), "healthy_no_matches")
    require(summary["article_count"] == 0 and summary["schema_valid"], "healthy_no_matches schema mismatch")
    require(EXIT_CODES[summary["status"]] == 0, "healthy_no_matches exit code mismatch")

    summary, _, _ = run_case(FakeResponse(429, {"articles": []}, headers={"Content-Type": "application/json", "Retry-After": "60"}), "rate_limited")
    require(summary["retry_after"] == "60", "Retry-After not recorded")
    require(EXIT_CODES[summary["status"]] == 2, "rate_limited exit code mismatch")
    require(summary["provider_state"] == "degraded", "first 429 should degrade provider")
    state = json.loads((_ / "last_attempt.json").read_text(encoding="utf-8"))
    require(state["consecutive_rate_limit_count"] == 1, "first 429 count mismatch")
    require(state["provider_state"] == "degraded", "first 429 state mismatch")
    require(state["webngrams_probe_allowed"] is True, "degraded provider should allow Web NGrams probe")

    tmpdir = Path(tempfile.mkdtemp())
    first_transport = FakeTransport(FakeResponse(429, {"articles": []}, headers={"Content-Type": "application/json"}))
    first = run_live_health(country_code="AU", timeout=1, report_dir=tmpdir, get_func=first_transport.get)
    require(first["status"] == "rate_limited", "429 setup failed")
    state = json.loads((tmpdir / "last_attempt.json").read_text(encoding="utf-8"))
    require(state["local_cooldown_seconds"] == 3600, "429 default cooldown mismatch")
    second_transport = FakeTransport(FakeResponse(200, {"articles": []}))
    second = run_live_health(country_code="AU", timeout=1, report_dir=tmpdir, get_func=second_transport.get)
    require(second["status"] == "cooldown_active" and len(second_transport.calls) == 0, "429 cooldown should block rerun")

    tmpdir = Path(tempfile.mkdtemp())
    (tmpdir / "last_attempt.json").write_text(
        json.dumps(
            {
                "attempted_at": "2099-01-01T00:00:00Z",
                "country": "AU",
                "query_profile": "health",
                "query_fingerprint": "legacy",
                "http_status": 429,
                "health_status": "rate_limited",
                "request_count": 1,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    decision = provider_decision("AU", report_dir=tmpdir, cooldown_seconds=3600)
    require(decision["provider_state"] == "quarantined", "legacy repeated 429 should quarantine provider")
    require(decision["consecutive_rate_limit_count"] >= 2, "legacy repeated 429 count mismatch")
    require(decision["doc_api_collection_allowed"] is False, "quarantine should block DOC API")
    require(decision["webngrams_probe_allowed"] is True, "quarantine should allow Web NGrams probe")
    require(decision["recommended_next_source"] == "gdelt_web_news_ngrams", "next source mismatch")
    require(decision["10.10-A.4_ready"] is False, "quarantine should block A.4")
    require(decision["10.10-B1_ready"] is True, "quarantine should prepare B1")
    blocked_transport = FakeTransport(FakeResponse(200, {"articles": []}))
    blocked = run_live_health(country_code="AU", timeout=1, report_dir=tmpdir, get_func=blocked_transport.get)
    require(blocked["status"] == "skipped_provider_quarantined", "quarantined provider should skip live")
    require(blocked["actual_request_count"] == 0 and len(blocked_transport.calls) == 0, "quarantine skip must not call transport")

    tmpdir = Path(tempfile.mkdtemp())
    run_live_health(country_code="AU", timeout=1, report_dir=tmpdir, get_func=FakeTransport(FakeResponse(429, {"articles": []}, headers={"Retry-After": "7200"})).get)
    state = json.loads((tmpdir / "last_attempt.json").read_text(encoding="utf-8"))
    require(state["local_cooldown_seconds"] == 7200 and state["cooldown_source"] == "retry_after", "Retry-After 7200 should win")

    tmpdir = Path(tempfile.mkdtemp())
    run_live_health(country_code="AU", timeout=1, report_dir=tmpdir, get_func=FakeTransport(FakeResponse(429, {"articles": []}, headers={"Retry-After": "60"})).get)
    state = json.loads((tmpdir / "last_attempt.json").read_text(encoding="utf-8"))
    require(state["local_cooldown_seconds"] == 3600 and state["cooldown_source"] == "local_policy", "internal 429 cooldown should beat short Retry-After")

    summary, _, _ = run_case(
        FakeResponse(200, ValueError("html"), text="Your query was too short or too long.\n", headers={"Content-Type": "text/html"}),
        "invalid_query",
    )
    require(summary["failure_reason"] == "provider_query_error", "invalid query reason mismatch")
    require(summary["response_error_category"] == "invalid_query", "invalid query category mismatch")
    require(EXIT_CODES[summary["status"]] == 3, "invalid_query exit code mismatch")
    state = json.loads((_ / "last_attempt.json").read_text(encoding="utf-8"))
    require(state["local_cooldown_seconds"] == 0, "invalid_query should not create cooldown")
    require(state["consecutive_rate_limit_count"] == 0, "invalid_query should not increment rate limit count")

    long_term = "m" * 121
    summary, transport, _ = run_case(FakeResponse(200, {"articles": [{"title": "Should not request"}]}), "invalid_query", health_term=long_term)
    require(len(transport.calls) == 0 and summary["request_count"] == 0, "preflight failure must block HTTP request")
    require(summary["failure_reason"] == "raw_query_too_long_for_internal_budget", "long query preflight reason mismatch")

    for code in (500, 502, 503, 504):
        summary, _, _ = run_case(FakeResponse(code, {"articles": []}), "provider_unavailable")
        require(summary["http_status"] == code, "provider unavailable status mismatch")
        require(EXIT_CODES[summary["status"]] == 4, "provider_unavailable exit code mismatch")

    summary, _, _ = run_case(FakeResponse(200, ValueError("not json"), text="<html><title>Bad</title></html>", headers={"Content-Type": "text/html"}), "invalid_response")
    require(not summary["json_parse_success"], "invalid JSON should not parse")
    require(len(summary["response_body_preview"]) <= 500, "body preview too long")
    require(EXIT_CODES[summary["status"]] == 3, "invalid_response exit code mismatch")
    state = json.loads((_ / "last_attempt.json").read_text(encoding="utf-8"))
    require(state["local_cooldown_seconds"] == 900, "invalid_response cooldown mismatch")

    summary, _, _ = run_case(FakeResponse(200, ValueError("html"), text="<html>Cookie: abc</html>", headers={"Content-Type": "text/html"}), "invalid_response")
    require("Cookie: REDACTED" in summary["response_body_preview"], "sensitive body preview not masked")

    summary, _, _ = run_case(FakeResponse(200, {"not_articles": []}), "invalid_response")
    require(summary["json_parse_success"] and not summary["schema_valid"], "wrong schema mismatch")

    for code in (401, 403):
        summary, _, _ = run_case(FakeResponse(code, {"articles": []}), "provider_blocked")
        require(summary["http_status"] == code, "blocked status mismatch")
        require(EXIT_CODES[summary["status"]] == 3, "provider_blocked exit code mismatch")

    summary, _, _ = run_case(requests.ConnectionError("connection refused"), "network_error")
    require(summary["request_count"] == 1, "network error request count mismatch")
    require(EXIT_CODES[summary["status"]] == 4, "network_error exit code mismatch")

    summary, _, _ = run_case(requests.Timeout("timeout"), "timeout")
    require(summary["request_count"] == 1, "timeout request count mismatch")
    require(EXIT_CODES[summary["status"]] == 4, "timeout exit code mismatch")
    state = json.loads((_ / "last_attempt.json").read_text(encoding="utf-8"))
    require(state["local_cooldown_seconds"] == 900, "timeout cooldown mismatch")

    summary, _, tmpdir = run_case(FakeResponse(200, {"articles": [{"title": "Modular housing"}]}), "healthy")
    state = json.loads((tmpdir / "last_attempt.json").read_text(encoding="utf-8"))
    require(state["consecutive_rate_limit_count"] == 0, "healthy response should reset rate limit count")
    require(state["provider_state"] == "healthy", "healthy provider state mismatch")

    print("GDELT PROVIDER HEALTH TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
