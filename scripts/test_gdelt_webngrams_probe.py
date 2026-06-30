from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.probe_gdelt_webngrams import (  # noqa: E402
    FIXTURE_GAL,
    FIXTURE_WEBNGRAMS,
    canonicalize_url,
    join_gal,
    print_plan,
    read_fixture_lines,
    run_fixture,
    scan_webngrams,
    validate_timestamp,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


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
    require(plan["webngrams_url"].endswith(".webngrams.json.gz"), "webngrams URL mismatch")
    require(plan["gal_url"].endswith(".gal.json.gz"), "GAL URL mismatch")

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

    script_text = (ROOT / "scripts" / "probe_gdelt_webngrams.py").read_text(encoding="utf-8")
    require("api.gdeltproject.org/api/v2/doc/doc" not in script_text, "DOC API endpoint must not be used")

    print("GDELT WEBNGRAMS PROBE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
