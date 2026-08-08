from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.build_company_report_insights import discover_source_files
from scripts.validate_company_audit_financials import load_payload, validate
from src.company_report_onboarding import (
    BLOCKED,
    PASS,
    REVIEW_REQUIRED,
    PipelineContext,
    preview_diff,
    preview_onboarding,
    protected_file_changes,
    promote_onboarding,
    stage_onboarding,
    validate_onboarding,
)

ROOT = Path(__file__).resolve().parents[1]
BASE_SOURCE = ROOT / "data" / "company_reports" / "yuchang-enc" / "audit_financials_2023_2025.json"
STATIC_FIXTURE = ROOT / "tests" / "fixtures" / "company_report_onboarding" / "pass_new_company"


def stable_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def sample_candidate(company_id: str = "sample-company") -> dict:
    payload = json.loads(BASE_SOURCE.read_text(encoding="utf-8"))
    payload["company_id"] = company_id
    payload["company_name"] = "샘플기업"
    payload["reporting_entity"] = "샘플기업 주식회사"
    payload["entity_attribution"]["reporting_entity"] = "샘플기업 주식회사"
    payload["entity_attribution"]["related_entity_attribution_required"] = False
    payload["entity_attribution"]["attribution_warning"] = "샘플기업 별도 재무제표 기준 후보 데이터입니다."
    payload["entity_attribution"]["special_events"] = []
    policy = payload["validation_metadata"].setdefault("validation_policy", {})
    policy["required_attribution_warning_terms"] = []
    policy["required_disclosure_limitations"] = []
    return payload


def sample_manifest(company_id: str = "sample-company", *, replace_existing: bool = False, allowed: list[str] | None = None) -> dict:
    return {
        "schema_version": "company_report_onboarding_manifest_v1",
        "company_id": company_id,
        "company_name": "샘플기업",
        "reporting_entity": "샘플기업 주식회사",
        "financial_scope": "standalone",
        "currency": "KRW",
        "unit": "won",
        "target_years": [2023, 2024, 2025],
        "candidate_input_path": f"data/company_reports/{company_id}/onboarding/candidate_audit_financials.json",
        "staging_output_path": f"data/company_reports/{company_id}/staging/audit_financials_2023_2025.json",
        "public_output_path": f"data/company_reports/{company_id}/audit_financials_2023_2025.json",
        "replace_existing": replace_existing,
        "source_priority": {
            "2023": {
                "primary_source_ref": "yuchang_audit_report_2025_04_04",
                "cross_check_source_refs": ["yuchang_audit_report_2024_04_05"],
            },
            "2024": {
                "primary_source_ref": "yuchang_audit_report_2026_04_08",
                "cross_check_source_refs": [],
            },
            "2025": {
                "primary_source_ref": "yuchang_audit_report_2026_04_08",
                "cross_check_source_refs": [],
            },
        },
        "required_metrics": [
            "revenue",
            "operating_profit",
            "operating_cash_flow",
            "total_assets",
            "total_liabilities",
            "total_equity",
        ],
        "optional_metrics": ["service_revenue"],
        "allowed_warning_codes": allowed if allowed is not None else ["pending_manual_page_check", "optional_metric_missing"],
        "promotion_policy": {
            "require_zero_blockers": True,
            "require_source_review_acknowledgement": True,
            "require_public_change_acknowledgement": True,
            "allow_verification_pending_required_metrics": False,
        },
    }


def write_fixture(root: Path, *, candidate: dict | None = None, manifest: dict | None = None) -> Path:
    candidate = candidate or sample_candidate()
    manifest = manifest or sample_manifest()
    candidate_path = root / manifest["candidate_input_path"]
    manifest_path = root / f"data/company_reports/{manifest['company_id']}/onboarding/manifest.json"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(stable_json(manifest), encoding="utf-8")
    candidate_path.write_text(stable_json(candidate), encoding="utf-8")
    (root / "frontend/public/data/companies").mkdir(parents=True, exist_ok=True)
    return manifest_path


def context(root: Path) -> PipelineContext:
    return PipelineContext(repo_root=root, artifact_root=Path("artifacts/company-report-onboarding-test"), base_ref=None)


def test_manifest_schema_valid_and_invalid(tmp_path: Path) -> None:
    manifest_path = write_fixture(tmp_path)
    result = validate_onboarding(manifest_path, context(tmp_path))
    assert result["verdict"] == PASS

    bad = sample_manifest()
    bad["target_years"] = [2025, 2024, 2023]
    bad_manifest = write_fixture(tmp_path / "bad", manifest=bad)
    result = validate_onboarding(bad_manifest, context(tmp_path / "bad"))
    assert result["verdict"] == BLOCKED
    assert any(item["code"] == "target_years_not_ascending" for item in result["blockers"])


def test_unsafe_path_is_blocked(tmp_path: Path) -> None:
    manifest = sample_manifest()
    manifest["candidate_input_path"] = "../candidate.json"
    manifest_path = write_fixture(tmp_path, manifest=manifest)
    result = validate_onboarding(manifest_path, context(tmp_path))
    assert result["verdict"] == BLOCKED
    assert any(item["code"] in {"manifest_schema_error", "unsafe_candidate_path"} or item["code"].endswith("mismatch") for item in result["blockers"])


def test_review_required_when_pending_page_check_not_allowed(tmp_path: Path) -> None:
    manifest = sample_manifest(allowed=["optional_metric_missing"])
    manifest_path = write_fixture(tmp_path, manifest=manifest)
    result = validate_onboarding(manifest_path, context(tmp_path))
    assert result["verdict"] == REVIEW_REQUIRED
    assert any(item["code"] == "pending_manual_page_check" for item in result["warnings"])


def test_blocked_contract_mismatches(tmp_path: Path) -> None:
    candidate = sample_candidate()
    candidate["unit"] = "thousand_won"
    manifest_path = write_fixture(tmp_path / "unit", candidate=candidate)
    result = validate_onboarding(manifest_path, context(tmp_path / "unit"))
    assert result["verdict"] == BLOCKED
    assert any(item["code"] == "unit_mismatch" for item in result["blockers"])

    missing_source_manifest = sample_manifest()
    missing_source_manifest["source_priority"]["2025"]["primary_source_ref"] = "missing_source"
    manifest_path = write_fixture(tmp_path / "source", manifest=missing_source_manifest)
    result = validate_onboarding(manifest_path, context(tmp_path / "source"))
    assert result["verdict"] == BLOCKED
    assert any(item["code"] == "primary_source_missing" for item in result["blockers"])


def test_required_metric_and_null_semantics_are_enforced(tmp_path: Path) -> None:
    manifest = sample_manifest()
    manifest["required_metrics"].append("rental_revenue")
    manifest_path = write_fixture(tmp_path / "zero", manifest=manifest)
    result = validate_onboarding(manifest_path, context(tmp_path / "zero"))
    assert result["verdict"] == PASS
    assert result["required_metric_coverage"]["rental_revenue"]["2024"]["reported"] == 0

    blocked = sample_candidate()
    blocked["financial_years"]["2025"]["income_statement"]["revenue"]["reported"] = None
    blocked["financial_years"]["2025"]["income_statement"]["revenue"]["disclosure_status"] = "verification_pending"
    manifest_path = write_fixture(tmp_path / "pending", candidate=blocked)
    result = validate_onboarding(manifest_path, context(tmp_path / "pending"))
    assert result["verdict"] == BLOCKED
    assert any(item["code"] in {"required_metric_verification_pending", "reported_null_without_disclosure_status"} for item in result["blockers"])


def test_stage_writes_only_staging_and_preserves_candidate_bytes(tmp_path: Path) -> None:
    manifest_path = write_fixture(tmp_path)
    candidate_path = tmp_path / sample_manifest()["candidate_input_path"]
    before_candidate = candidate_path.read_bytes()
    result = stage_onboarding(manifest_path, context(tmp_path))
    assert result["verdict"] == PASS
    staging_path = tmp_path / sample_manifest()["staging_output_path"]
    public_path = tmp_path / sample_manifest()["public_output_path"]
    assert staging_path.read_bytes() == before_candidate
    assert candidate_path.read_bytes() == before_candidate
    assert not public_path.exists()


def test_preview_is_deterministic_and_reports_new_company(tmp_path: Path) -> None:
    manifest_path = write_fixture(tmp_path)
    first = preview_onboarding(manifest_path, context(tmp_path))["public_diff_preview"]
    second = preview_onboarding(manifest_path, context(tmp_path))["public_diff_preview"]
    assert first["preview_sha256"] == second["preview_sha256"]
    assert first["pipeline_contract_version"] == "company_report_onboarding_gate_v1"
    assert first["manifest_sha256"]
    assert first["candidate_sha256"]
    assert first["operation"] == "add"
    assert first["added_company_ids"] == ["sample-company"]
    assert first["non_target_raw_source_change_count"] == 0


def test_preview_detects_non_target_raw_source_changes(tmp_path: Path) -> None:
    manifest = sample_manifest()
    old_target = {"company_id": "sample-company", "source_summary": {"count": 1}, "peer_benchmarks": []}
    old_other = {"company_id": "other-company", "available_years": [2023], "source_summary": {"count": 1}, "peer_benchmarks": [{"metric_id": "revenue"}]}
    new_other = {
        "company_id": "other-company",
        "available_years": [2023],
        "source_summary": {"count": 2},
        "peer_benchmarks": [{"metric_id": "revenue", "rank": 1}],
    }
    current = {"schema_version": "company_report_insights_v1", "companies": [old_target, old_other]}
    generated = {"schema_version": "company_report_insights_v1", "companies": [old_target, new_other]}
    (tmp_path / "frontend/public/data/companies").mkdir(parents=True, exist_ok=True)
    (tmp_path / "frontend/public/data/companies/company_report_insights.json").write_text(stable_json(current), encoding="utf-8")
    write_fixture(tmp_path, manifest=manifest)
    diff = preview_diff(manifest, generated, context(tmp_path))
    assert diff["non_target_raw_source_change_count"] == 1
    assert diff["non_target_raw_source_changes"][0]["company_id"] == "other-company"
    assert "source_summary" in diff["non_target_raw_source_changes"][0]["changed_paths"]


def test_peer_benchmark_only_change_is_reported_separately(tmp_path: Path) -> None:
    manifest = sample_manifest()
    other_before = {"company_id": "other-company", "available_years": [2023], "source_summary": {"count": 1}, "peer_benchmarks": []}
    other_after = {
        "company_id": "other-company",
        "available_years": [2023],
        "source_summary": {"count": 1},
        "peer_benchmarks": [{"metric_id": "revenue", "rank": 1}],
    }
    current = {"schema_version": "company_report_insights_v1", "companies": [other_before]}
    generated = {"schema_version": "company_report_insights_v1", "companies": [other_after]}
    (tmp_path / "frontend/public/data/companies").mkdir(parents=True, exist_ok=True)
    (tmp_path / "frontend/public/data/companies/company_report_insights.json").write_text(stable_json(current), encoding="utf-8")
    write_fixture(tmp_path, manifest=manifest)
    diff = preview_diff(manifest, generated, context(tmp_path))
    assert diff["non_target_raw_source_change_count"] == 0
    assert diff["affected_peer_benchmark_company_ids"] == ["other-company"]


def test_protected_file_hash_ignores_clean_worktree_line_endings(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "core.autocrlf", "true"], cwd=repo, check=True)

    protected_paths = [
        "frontend/public/data/business.json",
        "frontend/public/data/companies/companies.json",
        "frontend/public/data/companies/company_intelligence_v2.json",
        "frontend/public/data/meta.json",
        "frontend/public/data/news.json",
    ]
    for path in protected_paths:
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{\n  "ok": true\n}\n', encoding="utf-8", newline="\n")
    subprocess.run(["git", "add", *protected_paths], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=repo, check=True, capture_output=True)

    for path in protected_paths:
        (repo / path).write_text('{\r\n  "ok": true\r\n}\r\n', encoding="utf-8", newline="")

    clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *protected_paths], cwd=repo, check=False)
    assert clean.returncode == 0
    assert protected_file_changes(PipelineContext(repo_root=repo, artifact_root=repo / "artifacts", base_ref="HEAD")) == []


def test_preview_detects_unexpected_company_add_remove(tmp_path: Path) -> None:
    manifest = sample_manifest(replace_existing=True)
    current = {
        "schema_version": "company_report_insights_v1",
        "companies": [
            {"company_id": "sample-company", "source_summary": {}, "peer_benchmarks": []},
            {"company_id": "removed-company", "source_summary": {}, "peer_benchmarks": []},
        ],
    }
    generated = {
        "schema_version": "company_report_insights_v1",
        "companies": [
            {"company_id": "sample-company", "source_summary": {}, "peer_benchmarks": []},
            {"company_id": "unexpected-company", "source_summary": {}, "peer_benchmarks": []},
        ],
    }
    (tmp_path / "frontend/public/data/companies").mkdir(parents=True, exist_ok=True)
    (tmp_path / "frontend/public/data/companies/company_report_insights.json").write_text(stable_json(current), encoding="utf-8")
    write_fixture(tmp_path, manifest=manifest)
    diff = preview_diff(manifest, generated, context(tmp_path))
    assert diff["unexpected_added_company_ids"] == ["unexpected-company"]
    assert diff["unexpected_removed_company_ids"] == ["removed-company"]


def test_promote_requires_acknowledgements_and_matching_preview_sha(tmp_path: Path) -> None:
    manifest_path = write_fixture(tmp_path)
    preview = preview_onboarding(manifest_path, context(tmp_path))["public_diff_preview"]
    result = promote_onboarding(
        manifest_path,
        context(tmp_path),
        expected_preview_sha=preview["preview_sha256"],
        source_ack=False,
        public_ack=False,
        write=True,
    )
    assert result["verdict"] == BLOCKED
    assert not result["write_applied"]
    assert any(item["code"] == "source_review_acknowledgement_missing" for item in result["blockers"])

    result = promote_onboarding(
        manifest_path,
        context(tmp_path),
        expected_preview_sha="wrong",
        source_ack=True,
        public_ack=True,
        write=True,
    )
    assert result["verdict"] == BLOCKED
    assert any(item["code"] == "preview_sha_mismatch" for item in result["blockers"])


def test_promote_requires_existing_preview_artifact(tmp_path: Path) -> None:
    manifest_path = write_fixture(tmp_path)
    preview = preview_onboarding(manifest_path, context(tmp_path))["public_diff_preview"]
    (tmp_path / "artifacts/company-report-onboarding-test/sample-company/public-diff-preview.json").unlink()
    result = promote_onboarding(
        manifest_path,
        context(tmp_path),
        expected_preview_sha=preview["preview_sha256"],
        source_ack=True,
        public_ack=True,
        write=True,
    )
    assert result["verdict"] == BLOCKED
    assert any(item["code"] == "preview_artifact_missing" for item in result["blockers"])


def test_promote_blocks_candidate_change_after_preview(tmp_path: Path) -> None:
    manifest_path = write_fixture(tmp_path)
    preview = preview_onboarding(manifest_path, context(tmp_path))["public_diff_preview"]
    candidate_path = tmp_path / sample_manifest()["candidate_input_path"]
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["validation_metadata"]["note"] = "changed after preview"
    candidate_path.write_text(stable_json(candidate), encoding="utf-8")
    result = promote_onboarding(
        manifest_path,
        context(tmp_path),
        expected_preview_sha=preview["preview_sha256"],
        source_ack=True,
        public_ack=True,
        write=True,
    )
    assert result["verdict"] == BLOCKED
    assert any(item["code"] == "candidate_changed_after_preview" for item in result["blockers"])


def test_atomic_promotion_success_and_rollback(tmp_path: Path) -> None:
    manifest_path = write_fixture(tmp_path / "success")
    preview = preview_onboarding(manifest_path, context(tmp_path / "success"))["public_diff_preview"]
    result = promote_onboarding(
        manifest_path,
        context(tmp_path / "success"),
        expected_preview_sha=preview["preview_sha256"],
        source_ack=True,
        public_ack=True,
        write=True,
    )
    assert result["verdict"] == PASS
    assert result["write_applied"]
    assert (tmp_path / "success" / sample_manifest()["public_output_path"]).exists()
    assert (tmp_path / "success" / "frontend/public/data/companies/company_report_insights.json").exists()

    manifest_path = write_fixture(tmp_path / "rollback")
    preview = preview_onboarding(manifest_path, context(tmp_path / "rollback"))["public_diff_preview"]
    result = promote_onboarding(
        manifest_path,
        context(tmp_path / "rollback"),
        expected_preview_sha=preview["preview_sha256"],
        source_ack=True,
        public_ack=True,
        write=True,
        simulate_failure=True,
    )
    assert result["verdict"] == BLOCKED
    assert not result["write_applied"]
    assert result["rollback_applied"]
    assert result["promotion_manifest"]["rollback_applied"]
    assert not (tmp_path / "rollback" / sample_manifest()["public_output_path"]).exists()


def test_existing_company_update_and_public_file_gate(tmp_path: Path) -> None:
    manifest = sample_manifest(replace_existing=False)
    public_path = tmp_path / manifest["public_output_path"]
    public_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_text(stable_json(sample_candidate()), encoding="utf-8")
    manifest_path = write_fixture(tmp_path, manifest=manifest)
    result = validate_onboarding(manifest_path, context(tmp_path))
    assert result["verdict"] == BLOCKED
    assert any(item["code"] == "public_file_exists_replace_false" for item in result["blockers"])

    manifest["replace_existing"] = True
    (tmp_path / f"data/company_reports/{manifest['company_id']}/onboarding/manifest.json").write_text(stable_json(manifest), encoding="utf-8")
    result = validate_onboarding(manifest_path, context(tmp_path))
    assert result["verdict"] == PASS


def test_builder_discovery_excludes_onboarding_and_staging(tmp_path: Path) -> None:
    manifest_path = write_fixture(tmp_path)
    stage_onboarding(manifest_path, context(tmp_path))
    discovered = {path.relative_to(tmp_path / "data/company_reports").as_posix() for path in discover_source_files(tmp_path / "data/company_reports")}
    assert discovered == set()
    preview = preview_onboarding(manifest_path, context(tmp_path))
    assert preview["public_diff_preview"]["non_target_raw_source_change_count"] == 0


def test_source_priority_cross_check_and_covered_years_are_validated(tmp_path: Path) -> None:
    manifest = sample_manifest()
    manifest["source_priority"]["2023"]["cross_check_source_refs"] = ["missing_source"]
    manifest_path = write_fixture(tmp_path / "missing_cross", manifest=manifest)
    result = validate_onboarding(manifest_path, context(tmp_path / "missing_cross"))
    assert result["verdict"] == BLOCKED
    assert any(item["code"] == "source_priority_mismatch" for item in result["blockers"])
    assert any(item["code"] == "cross_check_source_missing" for item in result["blockers"])

    candidate = sample_candidate()
    candidate["source_documents"]["yuchang_audit_report_2026_04_08"]["covered_years"] = [2024]
    manifest_path = write_fixture(tmp_path / "coverage", candidate=candidate)
    result = validate_onboarding(manifest_path, context(tmp_path / "coverage"))
    assert result["verdict"] == BLOCKED
    assert any(item["code"] == "primary_source_year_not_covered" for item in result["blockers"])


def test_pending_manual_page_check_count_uses_unique_locations(tmp_path: Path) -> None:
    manifest_path = write_fixture(tmp_path)
    result = validate_onboarding(manifest_path, context(tmp_path))
    assert result["pending_manual_page_check_count"] > 1
    assert result["warnings"][-1]["actual"] == result["pending_manual_page_check_count"]
    assert result["pending_manual_page_check_source_ids"]
    assert result["pending_manual_page_check_years"]


def test_existing_five_company_audit_sources_still_validate() -> None:
    for company_id in ["yuchang-enc", "kumkang-kind", "daeseung-engineering", "planm", "nrb"]:
        path = ROOT / "data" / "company_reports" / company_id / "audit_financials_2023_2025.json"
        result = validate(load_payload(path), base_ref=None)
        assert result["valid"], (company_id, result["issues"])


def test_cli_exit_codes(tmp_path: Path) -> None:
    manifest_path = write_fixture(tmp_path)
    script = ROOT / "scripts" / "onboard_company_report.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "validate",
            "--repo-root",
            str(tmp_path),
            "--manifest",
            str(manifest_path.relative_to(tmp_path)),
            "--base-ref",
            "",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    manifest = sample_manifest(allowed=[])
    manifest_path = write_fixture(tmp_path / "review", manifest=manifest)
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "validate",
            "--repo-root",
            str(tmp_path / "review"),
            "--manifest",
            str(manifest_path.relative_to(tmp_path / "review")),
            "--base-ref",
            "",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2, result.stdout + result.stderr


def test_pdf_and_secret_like_text_are_blocked(tmp_path: Path) -> None:
    candidate = sample_candidate()
    candidate["validation_metadata"]["note"] = "DART_API_KEY=" + "abcdefghijklmnop"
    manifest_path = write_fixture(tmp_path, candidate=candidate)
    result = validate_onboarding(manifest_path, context(tmp_path))
    assert result["verdict"] == BLOCKED
    assert any(item["code"] == "secret_like_text_detected" for item in result["blockers"])

    safe = sample_candidate()
    safe["validation_metadata"]["note"] = "API Key is managed outside the repository with ${DART_API_KEY}."
    manifest_path = write_fixture(tmp_path / "safe", candidate=safe)
    result = validate_onboarding(manifest_path, context(tmp_path / "safe"))
    assert result["verdict"] == PASS


def test_static_synthetic_fixture_cli_validate_stage_preview(tmp_path: Path) -> None:
    fixture_root = tmp_path / "pass_new_company"
    shutil.copytree(STATIC_FIXTURE, fixture_root)
    script = ROOT / "scripts" / "onboard_company_report.py"
    manifest = "data/company_reports/sample-company/onboarding/manifest.json"
    for command in ["validate", "stage", "preview"]:
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                command,
                "--repo-root",
                str(fixture_root),
                "--manifest",
                manifest,
                "--artifact-root",
                str(tmp_path / "artifacts"),
                "--base-ref=",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    assert not (fixture_root / "data/company_reports/sample-company/audit_financials_2023_2025.json").exists()
    assert (fixture_root / "data/company_reports/sample-company/staging/audit_financials_2023_2025.json").exists()
