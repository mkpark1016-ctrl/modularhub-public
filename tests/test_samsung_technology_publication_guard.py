from __future__ import annotations

from copy import deepcopy

from src.public_data_policy import (
    CONTROLLED_PUBLIC_COMPANIES_PATH,
    SAMSUNG_TECHNOLOGY_NEW_IDS,
    SAMSUNG_TECHNOLOGY_SOURCE_ID,
    validate_controlled_samsung_technology_publication,
)


def existing_record(index: int) -> dict:
    return {
        "technology_id": f"tech-samsung-{index:03d}",
        "name": f"Samsung baseline technology {index}",
        "record_type": "construction_new_technology" if index == 1 else "patent",
        "registration_number": f"10-{index:07d}",
        "summary": "Accepted manual baseline",
        "status": "registered",
        "source_ids": ["manual-samsung"],
    }


def new_record(technology_id: str, index: int) -> dict:
    digits = technology_id.rsplit("-", 1)[-1]
    return {
        "technology_id": technology_id,
        "name": f"Samsung direct modular patent {index}",
        "record_type": "patent",
        "registration_number": f"10-28{index:05d}",
        "application_number": f"10-{digits[:4]}-{digits[4:]}",
        "patent_number": None,
        "status": "registered",
        "technology_area": "E04B 1/343",
        "application_date": "2023-01-16",
        "registration_date": "2025-06-10",
        "summary": "Official-source deterministic summary",
        "source_ids": [SAMSUNG_TECHNOLOGY_SOURCE_ID],
    }


def before_payload() -> dict:
    return {
        "schema_version": "company-universe-v1",
        "companies": [
            {"company_id": "other-company", "technology": {}, "sources": []},
            {
                "company_id": "samsung-ct-construction",
                "company_name": "Samsung C&T",
                "technology": {"new_construction_technologies": [existing_record(1)], "patents": [existing_record(index) for index in range(2, 8)]},
                "sources": [{"source_id": "manual-samsung", "source_url": None}],
            },
        ],
    }


def accepted_payloads() -> tuple[dict, dict]:
    before = before_payload()
    after = deepcopy(before)
    samsung = after["companies"][1]
    existing = {
        item["technology_id"]: item
        for rows in samsung["technology"].values()
        for item in rows
    }
    for index in range(2, 6):
        existing[f"tech-samsung-{index:03d}"].update(
            {
                "application_number": f"10-2021-000{index}",
                "patent_number": f"102023000{index}",
                "application_date": "2021-05-04",
                "registration_date": "2023-04-10",
            }
        )
    existing["tech-samsung-006"]["status"] = "expired"
    existing["tech-samsung-007"]["status"] = "expired"
    samsung["technology"]["patents"].extend(
        new_record(technology_id, index)
        for index, technology_id in enumerate(sorted(SAMSUNG_TECHNOLOGY_NEW_IDS), start=1)
    )
    samsung["sources"].append(
        {
            "source_id": SAMSUNG_TECHNOLOGY_SOURCE_ID,
            "source_type": "patent",
            "source_name": "KIPRIS Plus",
            "source_url": "https://plus.kipris.or.kr/portal/search/clasList/List.do",
            "visibility": "public",
        }
    )
    return before, after


def validate(before: dict, after: dict, paths=None) -> dict:
    return validate_controlled_samsung_technology_publication(
        before,
        after,
        paths or [CONTROLLED_PUBLIC_COMPANIES_PATH],
    )


def test_accepted_samsung_publication_delta_is_safe() -> None:
    result = validate(*accepted_payloads())

    assert result["passed"] is True
    assert result["status"] == "SAMSUNG_TECH_CONTROLLED_PUBLICATION_SAFE"
    assert result["counts"] == {
        "baseline": 7,
        "candidate": 13,
        "existing_preserved": 7,
        "enriched_existing": 4,
        "status_updated_existing": 2,
        "existing_modified": 6,
        "net_new": 6,
        "adjacent_published": 0,
        "removed": 0,
        "other_company_modified": 0,
        "identity_collisions": 0,
        "duplicate_identities": 0,
        "before_incomplete": 7,
        "after_incomplete": 3,
        "resolved_incomplete": 4,
    }
    assert result["security"] == {"credential_urls": 0, "forbidden_fields": 0, "passed": True}


def test_other_company_change_is_blocked() -> None:
    before, after = accepted_payloads()
    after["companies"][0]["name"] = "changed"
    assert "other_company_modified" in validate(before, after)["reason_codes"]


def test_existing_removal_is_blocked() -> None:
    before, after = accepted_payloads()
    after["companies"][1]["technology"]["patents"] = [
        item for item in after["companies"][1]["technology"]["patents"]
        if item["technology_id"] != "tech-samsung-002"
    ]
    assert "existing_technology_removed" in validate(before, after)["reason_codes"]


def test_existing_substantive_change_is_blocked() -> None:
    before, after = accepted_payloads()
    after["companies"][1]["technology"]["patents"][0]["name"] = "mutated title"
    assert "unexpected_existing_technology_change" in validate(before, after)["reason_codes"]


def test_unapproved_status_transition_is_blocked() -> None:
    before, after = accepted_payloads()
    after["companies"][1]["technology"]["patents"][0]["status"] = "expired"
    assert "unapproved_status_transition" in validate(before, after)["reason_codes"]


def test_unexpected_new_identity_is_blocked() -> None:
    before, after = accepted_payloads()
    after["companies"][1]["technology"]["patents"][-1]["technology_id"] = "tech-samsung-unreviewed"
    assert "new_technology_identity_mismatch" in validate(before, after)["reason_codes"]


def test_duplicate_official_identity_is_blocked() -> None:
    before, after = accepted_payloads()
    patents = after["companies"][1]["technology"]["patents"]
    patents[-1]["application_number"] = patents[-2]["application_number"]
    assert "duplicate_technology_identity" in validate(before, after)["reason_codes"]


def test_credential_url_is_blocked_without_secret_value_in_result() -> None:
    before, after = accepted_payloads()
    after["companies"][1]["sources"][-1]["source_url"] += "?serviceKey=do-not-report"
    result = validate(before, after)
    assert "sensitive_public_payload_detected" in result["reason_codes"]
    assert "do-not-report" not in str(result)


def test_dangling_source_and_broad_file_scope_are_blocked() -> None:
    before, after = accepted_payloads()
    after["companies"][1]["technology"]["patents"][-1]["source_ids"] = ["missing"]
    result = validate(before, after, [CONTROLLED_PUBLIC_COMPANIES_PATH, "src/example.py"])
    assert "technology_source_reference_invalid" in result["reason_codes"]
    assert "changed_file_scope_invalid" in result["reason_codes"]