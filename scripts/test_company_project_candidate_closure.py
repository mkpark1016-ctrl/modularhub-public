from audit_company_project_candidate_closure import audit_closure


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    result = audit_closure()
    require(result["status"] == "PASS_RESEARCH_CLOSED", result["status"])
    require(result["project_candidate_id"] == "yuchang-enc-samsung-ai-modular-home", result["project_candidate_id"])
    require(result["article_evidence_count"] == 35, result["article_evidence_count"])
    require(result["official_source_check_count"] == 5, result["official_source_check_count"])
    require(result["official_source_confirmed_count"] == 0, result["official_source_confirmed_count"])
    require(result["company_role"] == "role_unknown", result["company_role"])
    require(result["final_verification_status"] == "research_exhausted_no_verified_project", result["final_verification_status"])
    require(result["raw_candidate_article_count"] == 50, result["raw_candidate_article_count"])
    require(result["duplicate_article_count"] == 47, result["duplicate_article_count"])
    require(result["representative_unique_article_count"] == 3, result["representative_unique_article_count"])
    require(result["raw_candidate_article_count"] == result["duplicate_article_count"] + result["representative_unique_article_count"], result)
    require(result["unique_article_group_count"] == 3, result["unique_article_group_count"])
    require(result["non_project_article_group_count"] == 2, result["non_project_article_group_count"])
    require(result["project_candidate_cluster_count"] == 1, result["project_candidate_cluster_count"])
    require(result["verified_project_count"] == 0, result["verified_project_count"])
    require(result["pending_project_count"] == 0, result["pending_project_count"])
    require(result["research_closed_project_count"] == 1, result["research_closed_project_count"])
    require(result["rejected_raw_article_count"] == 22, result["rejected_raw_article_count"])
    require(result["rejected_cluster_count"] == 2, result["rejected_cluster_count"])
    require(result["overlap_allowed"] is True, result["overlap_allowed"])
    require(result["overlap_count"] == 13, result["overlap_count"])
    require(result["validation_error_count"] == 0, result["validation_error_count"])
    print("COMPANY PROJECT CANDIDATE CLOSURE TESTS PASSED")


if __name__ == "__main__":
    main()
