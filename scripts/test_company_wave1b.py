#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "frontend/public/data/companies/companies.json"
V2 = ROOT / "frontend/public/data/companies/company_intelligence_v2.json"
TARGETS = ("yuchang-enc", "nrb", "planm")
INTERNAL_SOURCES = {
    "internal-research-yuchang-20260716",
    "internal-research-nrb-20260716",
    "internal-research-planm-20260716",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def by_company(data, company_id):
    return next(item for item in data["companies"] if item["company_id"] == company_id)


def main() -> int:
    v1 = load(V1)
    v2 = load(V2)

    assert len(v1["companies"]) == 17
    assert len({item["company_id"] for item in v1["companies"]}) == 17

    for company_id in TARGETS:
        company = by_company(v1, company_id)
        assert company["intelligence_v2"]["summary_ko"]
        assert any(source["source_id"] in INTERNAL_SOURCES for source in company.get("sources", []))
        assert any(item["source_id"] in INTERNAL_SOURCES for item in v2.get("evidence", []))

    yuchang = by_company(v1, "yuchang-enc")
    facility = next(item for item in yuchang["production"] if item["facility_id"] == "yuchang-enc-yoochang-factory")
    assert facility.get("capacity_value") is None
    assert facility.get("reported_capacity") is None
    assert facility.get("capacity_status") == "unavailable"
    assert "yc_official_home" in facility.get("source_ids", [])
    assert "internal-research-yuchang-20260716" in facility.get("source_ids", [])

    project = next(
        item
        for item in yuchang["project_portfolio"]
        if item["project_id"] == "yuchang-seongnam-hadaewon-happy-housing"
    )
    assert project["project_status"] == "completed"
    assert project["verification_status"] == "internally_confirmed"
    assert project["project_credit"] is True

    for company_id in ("nrb", "planm"):
        company = by_company(v1, company_id)
        assert company.get("production") == []
        assert company.get("project_portfolio") == []
        assert company["intelligence_v2"]["domain_statuses"]["production_status"] in {
            "unavailable",
            "not_verified",
            "partially_verified",
        }

    samsung = next(
        item
        for item in v2["events"]
        if item["event_id"] == "event-yuchang-enc-samsung-ai-modular-home"
    )
    assert samsung["event_type"] == "partnership"
    assert samsung["event_status"] == "not_signed"
    assert samsung["project_credit"] is False

    expected_events = {
        "event-yuchang-poscoac-modular-business-transfer",
        "event-nrb-automation-factory-expansion-strategy",
        "event-nrb-highrise-modular-strategy",
        "event-planm-capital-and-growth-strategy",
        "event-planm-overseas-highrise-datacenter-strategy",
    }
    actual_event_ids = {item["event_id"] for item in v2["events"]}
    assert expected_events.issubset(actual_event_ids)

    for fact in v2.get("facts", []):
        if set(fact.get("source_ids", [])) & INTERNAL_SOURCES:
            assert fact.get("value") not in (None, [], {})

    fact_ids = [item["fact_id"] for item in v2.get("facts", [])]
    event_ids = [item["event_id"] for item in v2.get("events", [])]
    evidence_ids = [item["source_id"] for item in v2.get("evidence", [])]
    assert len(fact_ids) == len(set(fact_ids))
    assert len(event_ids) == len(set(event_ids))
    assert len(evidence_ids) == len(set(evidence_ids))

    print("PASS: Wave 1B curated company baselines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
