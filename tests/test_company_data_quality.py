from __future__ import annotations

import json

from src.company_data_quality import (
    build_quality_audit,
    load_public_company_universe,
    source_registry,
    validate_quality_artifacts,
)


def test_public_company_universe_includes_runtime_daeseung_overlay():
    companies = load_public_company_universe()
    ids = {company["company_id"] for company in companies}

    assert len(companies) == 11
    assert "daeseung-engineering" in ids


def test_daeseung_identity_excludes_same_name_companies():
    daeseung = next(company for company in load_public_company_universe() if company["company_id"] == "daeseung-engineering")
    blob = json.dumps(daeseung, ensure_ascii=False)

    assert "채윤석" in blob
    assert "2009-04-09" in blob
    assert "최병천" not in blob
    assert "대승그룹" not in blob
    assert "자동차 부품" not in blob


def test_source_registry_is_deduplicated_and_tiered():
    registry = source_registry(load_public_company_universe())
    source_ids = [source["sourceId"] for source in registry]

    assert len(source_ids) == len(set(source_ids))
    assert any(source["sourceTier"] == "tier_1" for source in registry)
    assert any(source["sourceTier"] == "internal_verified" for source in registry)
    assert all("supports" in source for source in registry)


def test_quality_audit_scores_are_bounded_and_sorted():
    audit = build_quality_audit()
    scores = [row["score"] for row in audit["companies"]]

    assert audit["status"] == "passed"
    assert audit["companyCount"] == 11
    assert scores == sorted(scores)
    assert all(0 <= score <= 100 for score in scores)
    assert all(row["topResearchGaps"] for row in audit["companies"])


def test_quality_validator_rejects_company_count_mismatch():
    companies = load_public_company_universe()[:10]
    issues = validate_quality_artifacts(companies, source_registry(companies), [])

    assert any(issue["code"] == "company_count" for issue in issues)

