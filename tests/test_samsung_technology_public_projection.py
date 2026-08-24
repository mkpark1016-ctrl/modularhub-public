from __future__ import annotations

from copy import deepcopy

from scripts.integrations.technology.public_projection import (
    PUBLIC_TECHNOLOGY_FIELDS,
    build_samsung_public_projection,
)


def accepted_inputs() -> dict:
    newtech = {
        "technology_id": "tech-samsung-001",
        "name": "삼성 건설신기술",
        "registration_number": "건설신기술 제1005호",
        "record_type": "construction_new_technology",
        "status": "registered",
        "application_date": None,
        "registration_date": None,
        "source_ids": ["manual-source"],
    }
    patents = []
    exact = []
    for index in range(2, 8):
        technology_id = f"tech-samsung-00{index}"
        registration = f"10-200000{index}"
        patents.append({
            "technology_id": technology_id,
            "name": f"모듈러 특허 {index}",
            "registration_number": registration,
            "record_type": "patent",
            "status": "registered",
            "application_date": None,
            "registration_date": None,
            "source_ids": ["manual-source"],
        })
        application = f"10-2023-000000{index}"
        report = {
            "baseline_technology_id": technology_id,
            "official_application_number": application,
            "official_registration_number": registration,
            "official_patent_public_number": f"102024000000{index}",
            "official_application_date": "2023-01-01",
            "official_registration_date": "2025-01-01",
            "official_status": "registered" if index < 6 else "expired",
            "match_decision": "MATCHED_OFFICIAL" if index < 6 else "CONFLICT",
            "conflict_fields": [] if index < 6 else ["status"],
            "enrichment_fields": (
                {
                    "application_number": application,
                    "patent_number": f"102024000000{index}",
                    "application_date": "2023-01-01",
                    "registration_date": "2025-01-01",
                }
                if index < 6
                else {}
            ),
        }
        exact.append(report)
    status = [
        {
            "technology_id": f"tech-samsung-00{index}",
            "decision": "CONFIRMED_EXPIRED",
            "current_status": "expired",
            "status_field_semantics": "current_lifecycle_status",
            "status_update_candidate": {"from": "registered", "to": "expired"},
            "termination_events": [{"date": "20200101", "reason": "등록료불납"}],
        }
        for index in (6, 7)
    ]
    direct = candidate("10-2026-0000001", "신규 모듈러 특허", "direct")
    adjacent = candidate("10-2026-0000002", "인접 건설 특허", "adjacent")
    summary = {
        "net_new_records": [
            {"official_identity": direct["official_identity"], "applicants": ["삼성물산 주식회사"]},
            {"official_identity": adjacent["official_identity"], "applicants": ["삼성물산 주식회사"]},
        ]
    }
    return {
        "companies": [{
            "company_id": "samsung-ct-construction",
            "technology": {"new_construction_technologies": [newtech], "patents": patents},
        }],
        "exact_reports": exact,
        "status_reports": status,
        "applicant_candidates": [direct, adjacent],
        "applicant_summary": summary,
    }


def candidate(application: str, title: str, relevance: str) -> dict:
    digits = application.replace("-", "")
    return {
        "candidate_type": "net_new",
        "official_identity": f"patent:{digits}",
        "company_ids": ["samsung-ct-construction"],
        "company_match": "normalized_alias",
        "source": "kipris",
        "source_record_type": "patent",
        "external_id": digits[-3:],
        "name": title,
        "record_type": "patent",
        "application_number": application,
        "registration_number": f"10-300{digits[-4:]}",
        "patent_number": None,
        "status": "registered",
        "technology_area": "E04B 1/343",
        "application_date": "2026-01-01",
        "registration_date": "2026-07-01",
        "summary": "공식 모듈러 기술 요약",
        "source_url": "https://plus.kipris.or.kr/portal/search/clasList/List.do",
        "source_ids": [f"official:kipris:{digits[-3:]}"],
        "modular_relevance": relevance,
    }


def build(inputs: dict | None = None) -> dict:
    return build_samsung_public_projection(**(inputs or accepted_inputs()))


def test_existing_enrichment_and_status_adjudication_are_projected() -> None:
    projection = build()
    diff = {row["technology_id"]: row for row in projection["existing_diff_report"]}

    assert diff["tech-samsung-002"]["change_classification"] == "ENRICHMENT"
    assert diff["tech-samsung-002"]["after"]["application_number"] == "10-2023-0000002"
    assert diff["tech-samsung-002"]["after"]["registration_date"] == "2025-01-01"
    assert diff["tech-samsung-006"]["change_classification"] == "STATUS_UPDATE"
    assert diff["tech-samsung-006"]["after"]["status"] == "expired"
    assert diff["tech-samsung-007"]["after"]["status"] == "expired"
    assert projection["metrics"]["enriched_existing_count"] == 4
    assert projection["metrics"]["status_updated_existing_count"] == 2
    assert projection["metrics"]["existing_modified_total"] == 6


def test_manual_kaia_record_is_preserved_exactly() -> None:
    inputs = accepted_inputs()
    baseline = deepcopy(inputs["companies"][0]["technology"]["new_construction_technologies"])
    projection = build(inputs)

    assert projection["candidate_company_technology"]["technology"]["new_construction_technologies"] == baseline
    first = projection["existing_diff_report"][0]
    assert first["change_classification"] == "UNCHANGED"
    assert first["before"] == first["after"]


def test_direct_candidate_is_publishable_and_adjacent_is_review_only() -> None:
    projection = build()
    public = projection["candidate_company_technology"]["technology"]["patents"]

    assert len(public) == 7
    new_item = next(row for row in public if row["technology_id"].startswith("tech-samsung-kipris"))
    assert set(PUBLIC_TECHNOLOGY_FIELDS) == set(new_item)
    assert new_item["source_ids"] == ["official:kipris:001"]
    assert projection["new_candidate_report"][0]["applicant"] == ["삼성물산 주식회사"]
    assert projection["new_candidate_report"][0]["publication_decision"] == "net_new_public_candidate"
    assert projection["adjacent_review_report"][0]["publication_decision"] == "review_only_adjacent"
    assert projection["metrics"]["net_new_count"] == 1
    assert projection["metrics"]["adjacent_review_count"] == 1


def test_duplicate_candidate_is_filtered_deterministically() -> None:
    inputs = accepted_inputs()
    inputs["applicant_candidates"].append(deepcopy(inputs["applicant_candidates"][0]))
    projection = build(inputs)

    assert projection["metrics"]["direct_duplicate_count"] == 1
    assert projection["metrics"]["direct_publishable_count"] == 1
    assert projection["new_candidate_report"][1]["filter_reason"] == ["duplicate_candidate"]


def test_identity_collision_is_blocking() -> None:
    inputs = accepted_inputs()
    collision = deepcopy(inputs["applicant_candidates"][0])
    collision["name"] = "서로 다른 공식 제목"
    inputs["applicant_candidates"].append(collision)
    projection = build(inputs)

    assert projection["metrics"]["identity_collision_count"] == 1
    assert "identity_collision" in projection["new_candidate_report"][1]["filter_reason"]


def test_conflicting_enrichment_does_not_partially_modify_existing_record() -> None:
    inputs = accepted_inputs()
    patent = inputs["companies"][0]["technology"]["patents"][0]
    patent["application_number"] = "10-1999-9999999"
    projection = build(inputs)
    report = next(
        row for row in projection["existing_diff_report"] if row["technology_id"] == "tech-samsung-002"
    )

    assert report["change_classification"] == "CONFLICT"
    assert "conflicting_enrichment:application_number" in report["conflicts"]
    assert report["after"] == report["before"]
    assert report["field_changes"] == []


def test_credential_url_is_rejected_without_being_copied_to_report() -> None:
    inputs = accepted_inputs()
    inputs["applicant_candidates"][0]["source_url"] = (
        "https://plus.kipris.or.kr/search?accessKey=do-not-store"
    )
    projection = build(inputs)
    report = projection["new_candidate_report"][0]

    assert projection["metrics"]["credential_exposure_count"] == 1
    assert projection["metrics"]["direct_publishable_count"] == 0
    assert report["source_url"] is None
    assert report["filter_reason"] == ["credential_url"]
    assert "do-not-store" not in str(projection)


def test_adjacent_credential_url_is_counted_and_redacted() -> None:
    inputs = accepted_inputs()
    inputs["applicant_candidates"][1]["source_url"] = (
        "https://plus.kipris.or.kr/search?serviceKey=do-not-store"
    )
    projection = build(inputs)

    assert projection["metrics"]["credential_exposure_count"] == 1
    assert projection["adjacent_review_report"][0]["source_url"] is None
    assert "do-not-store" not in str(projection)


def test_projection_order_is_deterministic() -> None:
    inputs = accepted_inputs()
    second_direct = candidate("10-2026-0000003", "두 번째 신규 특허", "direct")
    inputs["applicant_candidates"].append(second_direct)
    inputs["applicant_summary"]["net_new_records"].append({
        "official_identity": second_direct["official_identity"],
        "applicants": ["삼성물산 주식회사"],
    })
    first = build(inputs)
    reversed_inputs = deepcopy(inputs)
    reversed_inputs["applicant_candidates"].reverse()
    reversed_inputs["exact_reports"].reverse()
    reversed_inputs["status_reports"].reverse()
    second = build(reversed_inputs)

    assert first == second


def test_information_completeness_improvement_matches_ui_rule() -> None:
    projection = build()
    metrics = projection["metrics"]

    assert metrics["baseline_info_incomplete_count"] == 7
    assert metrics["candidate_info_incomplete_count"] == 3
    assert metrics["resolved_info_incomplete_count"] == 4


def test_existing_records_are_never_removed() -> None:
    projection = build()
    metrics = projection["metrics"]

    assert metrics["baseline_count"] == 7
    assert metrics["removed_count"] == 0
    assert metrics["conflict_count"] == 0
    assert metrics["matched_official_count"] == 6
