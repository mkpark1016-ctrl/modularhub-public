from pathlib import Path

from audit_company_project_alignment import audit_alignment


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    result = audit_alignment()
    require(result["status"] == "PASS_WITH_RESEARCH_GAPS", result["status"])
    require(result["wave1_targets"] == ["yuchang-enc", "planm", "daeseung-engineering", "sungji-steel"], result["wave1_targets"])
    require(result["total_verified_projects"] == 3, result["total_verified_projects"])
    require(result["preexisting_verified_projects"] == 3, result["preexisting_verified_projects"])
    require(result["wave1_verified_projects"] == 0, result["wave1_verified_projects"])
    require(result["wave1_candidate_projects"] == 50, result["wave1_candidate_projects"])
    require(result["non_target_wave1_count"] == 0, result["non_target_wave1_count"])
    require(result["candidate_marked_verified_count"] == 0, result["candidate_marked_verified_count"])
    require(result["validation_error_count"] == 0, result["validation_error_count"])
    artifact_dir = Path("artifacts/company-project-portfolio-wave-1-r1")
    for filename in [
        "wave1_target_snapshot.csv",
        "project_classification.csv",
        "project_candidates.csv",
        "preexisting_verified_projects.csv",
        "wave1_alignment_audit.json",
        "wave1_alignment_audit.md",
    ]:
        require((artifact_dir / filename).exists(), f"Missing artifact: {filename}")
    print("COMPANY PROJECT ALIGNMENT TESTS PASSED")


if __name__ == "__main__":
    main()
