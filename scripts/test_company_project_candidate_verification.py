from audit_company_project_candidate_verification import audit_candidate_verification


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    result = audit_candidate_verification()
    require(result["status"] == "PASS_WITH_RESEARCH_GAPS", result["status"])
    require(result["raw_candidate_article_count"] == 50, result["raw_candidate_article_count"])
    require(result["duplicate_article_count"] == 47, result["duplicate_article_count"])
    require(result["project_candidate_cluster_count"] == 1, result["project_candidate_cluster_count"])
    require(result["verified_project_count"] == 0, result["verified_project_count"])
    require(result["pending_project_count"] == 1, result["pending_project_count"])
    require(result["verified_without_official_source_count"] == 0, result["verified_without_official_source_count"])
    require(result["verified_without_role_count"] == 0, result["verified_without_role_count"])
    require(result["validation_error_count"] == 0, result["validation_error_count"])
    coverage = {row["company_id"]: row for row in result["company_coverage"]}
    require(coverage["yuchang-enc"]["raw_candidate_article_count"] == 45, coverage["yuchang-enc"])
    require(coverage["yuchang-enc"]["project_candidate_cluster_count"] == 1, coverage["yuchang-enc"])
    require(coverage["planm"]["raw_candidate_article_count"] == 5, coverage["planm"])
    require(coverage["planm"]["project_candidate_cluster_count"] == 0, coverage["planm"])
    require(coverage["daeseung-engineering"]["raw_candidate_article_count"] == 0, coverage["daeseung-engineering"])
    require(coverage["sungji-steel"]["raw_candidate_article_count"] == 0, coverage["sungji-steel"])
    print("COMPANY PROJECT CANDIDATE VERIFICATION TESTS PASSED")


if __name__ == "__main__":
    main()
