from __future__ import annotations

from scripts.integrations.technology.public_projection import (
    CompanyProjectionPolicy,
    build_company_public_projection,
    build_samsung_public_projection,
    deterministic_technology_id,
)


def _baseline(company_id: str = "example-builder", count: int = 1) -> dict:
    return {
        "company_id": company_id,
        "technology": {
            "new_construction_technologies": [],
            "patents": [
                {
                    "technology_id": f"tech-{company_id}-{index}",
                    "name": f"Baseline {index}",
                    "record_type": "patent",
                    "registration_number": f"10-100000{index}",
                    "application_number": None,
                    "patent_number": None,
                    "status": "registered",
                    "technology_area": "E04B",
                    "application_date": None,
                    "registration_date": None,
                    "summary": "Verified baseline",
                    "source_ids": ["manual:baseline"],
                }
                for index in range(1, count + 1)
            ],
        },
    }


def _exact(company_id: str = "example-builder", count: int = 1) -> list[dict]:
    return [
        {
            "baseline_technology_id": f"tech-{company_id}-{index}",
            "match_decision": "MATCHED_OFFICIAL",
            "official_application_number": f"10-2020-00000{index}",
            "official_registration_number": f"10-100000{index}",
            "enrichment_fields": {
                "application_number": f"10-2020-00000{index}",
                "patent_number": f"10202200000{index}",
                "application_date": "2020-01-01",
                "registration_date": "2022-01-01",
            },
            "conflict_fields": [],
        }
        for index in range(1, count + 1)
    ]


def _candidate(
    identity: str,
    *,
    company_id: str = "example-builder",
    status: str = "registered",
    relevance: str = "direct",
    title: str = "Modular assembly",
) -> dict:
    digits = identity.split(":", 1)[-1]
    return {
        "official_identity": identity,
        "name": title,
        "record_type": "patent",
        "source": "kipris",
        "source_ids": [f"official:kipris:{digits}"],
        "source_url": "https://example.test/patent",
        "candidate_type": "net_new",
        "modular_relevance": relevance,
        "company_ids": [company_id],
        "company_match": "exact",
        "application_number": digits,
        "registration_number": f"10-{digits[-7:]}" if status == "registered" else None,
        "patent_number": digits,
        "status": status,
        "technology_area": "E04B 1/343",
        "application_date": "2024-01-01",
        "registration_date": "2025-01-01" if status == "registered" else None,
        "summary": "Official abstract",
        "applicants": ["Example Builder Inc."],
    }


def _project(
    *,
    company: dict | None = None,
    exact: list[dict] | None = None,
    candidates: list[dict] | None = None,
    policy: CompanyProjectionPolicy | None = None,
) -> dict:
    company = company or _baseline()
    return build_company_public_projection(
        companies=[company],
        exact_reports=_exact() if exact is None else exact,
        status_reports=[],
        applicant_candidates=candidates or [],
        applicant_summary={"net_new_records": []},
        policy=policy or CompanyProjectionPolicy(company_id=company["company_id"]),
    )


def test_generic_projection_accepts_registered_candidate_for_non_samsung_company() -> None:
    result = _project(candidates=[_candidate("patent:1020240000001")])
    new = result["candidate_company_technology"]["technology"]["patents"][-1]
    assert result["metrics"]["candidate_total"] == 2
    assert new["technology_id"] == "tech-example-builder-kipris-1020240000001"
    assert result["registered_candidate_report"][0]["publication_decision"] == "net_new_public_candidate"


def test_deterministic_id_uses_company_source_and_official_identity_not_title() -> None:
    first = deterministic_technology_id("alpha", "kipris", "patent:1020240000001")
    same = deterministic_technology_id("alpha", "kipris", "patent:1020240000001")
    other_company = deterministic_technology_id("beta", "kipris", "patent:1020240000001")
    assert first == same
    assert first != other_company
    row_a = _candidate("patent:1020240000002", title="Original title")
    row_b = _candidate("patent:1020240000002", title="Renamed title")
    assert _project(candidates=[row_a])["candidate_company_technology"]["technology"]["patents"][-1]["technology_id"] == _project(candidates=[row_b])["candidate_company_technology"]["technology"]["patents"][-1]["technology_id"]


def test_published_application_is_review_only_under_policy_a() -> None:
    result = _project(candidates=[_candidate("patent:1020240000003", status="published")])
    assert result["metrics"]["net_new_count"] == 0
    assert result["metrics"]["published_application_review_count"] == 1
    assert result["published_application_review"][0]["filter_reason"] == [
        "status_not_allowed_by_policy:published"
    ]


def test_empty_field_enrichment_is_allowed_and_conflict_rolls_back() -> None:
    enriched = _project()
    after = enriched["existing_diff_report"][0]["after"]
    assert after["application_number"] == "10-2020-000001"
    conflict_company = _baseline()
    conflict_company["technology"]["patents"][0]["application_number"] = "10-1999-999999"
    conflict = _project(company=conflict_company)
    diff = conflict["existing_diff_report"][0]
    assert diff["change_classification"] == "CONFLICT"
    assert diff["after"] == diff["before"]
    assert "conflicting_enrichment:application_number" in diff["conflicts"]


def test_adjacent_and_wrong_applicant_never_enter_public_candidate() -> None:
    adjacent = _candidate("patent:1020240000004", relevance="adjacent")
    wrong = _candidate("patent:1020240000005")
    wrong.update({"company_ids": [], "company_match": "unmatched"})
    result = _project(candidates=[adjacent, wrong])
    assert result["metrics"]["net_new_count"] == 0
    assert result["metrics"]["adjacent_review_count"] == 1
    assert result["metrics"]["excluded_applicant_count"] == 1


def test_credential_bearing_url_is_filtered() -> None:
    row = _candidate("patent:1020240000006")
    row["source_url"] = "https://reader:private@example.test/patent"
    result = _project(candidates=[row])
    assert result["metrics"]["credential_exposure_count"] == 1
    assert result["metrics"]["net_new_count"] == 0
    assert "credential_url" in result["registered_candidate_report"][0]["filter_reason"]


def test_samsung_wrapper_preserves_schema_and_id_namespace() -> None:
    company = _baseline("samsung-ct-construction", 6)
    company["technology"]["new_construction_technologies"] = [{
        "technology_id": "tech-samsung-kaia-1",
        "name": "Manual new technology",
        "record_type": "construction_new_technology",
        "status": "active",
    }]
    candidate = _candidate(
        "patent:1020240000007",
        company_id="samsung-ct-construction",
    )
    result = build_samsung_public_projection(
        companies=[company],
        exact_reports=_exact("samsung-ct-construction", 6),
        status_reports=[],
        applicant_candidates=[candidate],
        applicant_summary={"net_new_records": []},
    )
    assert set(result) == {
        "candidate_company_technology",
        "existing_diff_report",
        "new_candidate_report",
        "adjacent_review_report",
        "metrics",
    }
    assert result["candidate_company_technology"]["schema_version"] == "samsung-technology-public-projection-v1"
    assert result["candidate_company_technology"]["technology"]["patents"][-1]["technology_id"] == "tech-samsung-kipris-1020240000007"


def test_samsung_wrapper_preserves_thirteen_record_projection_contract() -> None:
    company = _baseline("samsung-ct-construction", 6)
    company["technology"]["new_construction_technologies"] = [{
        "technology_id": "tech-samsung-kaia-1",
        "name": "Manual new technology",
        "record_type": "construction_new_technology",
        "status": "active",
    }]
    candidates = [
        _candidate(f"patent:10202400001{index:02d}", company_id="samsung-ct-construction")
        for index in range(6)
    ]
    result = build_samsung_public_projection(
        companies=[company],
        exact_reports=_exact("samsung-ct-construction", 6),
        status_reports=[],
        applicant_candidates=candidates,
        applicant_summary={"net_new_records": []},
    )
    assert result["metrics"]["baseline_count"] == 7
    assert result["metrics"]["net_new_count"] == 6
    assert result["metrics"]["candidate_total"] == 13


def test_gs_policy_a_projection_metrics_are_three_plus_four_equals_seven() -> None:
    company = _baseline("gs-ec", 3)
    candidates = [
        _candidate(f"patent:102024000001{index}", company_id="gs-ec")
        for index in range(4)
    ]
    candidates.extend(
        _candidate(f"patent:102024000002{index}", company_id="gs-ec", status="published")
        for index in range(3)
    )
    candidates.extend(
        _candidate(f"patent:1020240001{index:03d}", company_id="gs-ec", relevance="adjacent")
        for index in range(186)
    )
    for index in range(3):
        wrong = _candidate(f"patent:102024000003{index}", company_id="gs-ec", relevance="adjacent")
        wrong.update({"company_ids": [], "company_match": "unmatched"})
        candidates.append(wrong)
    result = _project(
        company=company,
        exact=_exact("gs-ec", 3),
        candidates=candidates,
        policy=CompanyProjectionPolicy(company_id="gs-ec"),
    )
    expected = {
        "baseline_count": 3,
        "enriched_existing_count": 3,
        "net_new_count": 4,
        "published_application_review_count": 3,
        "adjacent_review_count": 186,
        "excluded_applicant_count": 3,
        "candidate_total": 7,
    }
    assert {key: result["metrics"][key] for key in expected} == expected
