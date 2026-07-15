#!/usr/bin/env python3
"""Regression tests for Company Intelligence V2 migration and public materialization."""

from __future__ import annotations

from copy import deepcopy

from materialize_company_intelligence_v2 import materialize_companies, public_v2_payload
from migrate_company_intelligence_v2 import DEFAULT_COMPANIES, build_v2_dataset, protected_hash, read_json


def main() -> int:
    legacy = read_json(DEFAULT_COMPANIES)
    payload = build_v2_dataset(DEFAULT_COMPANIES)
    assert len(payload["companies"]) == 17
    assert len({item["company_id"] for item in payload["companies"]}) == 17
    assert len({item["fact_id"] for item in payload["facts"]}) == len(payload["facts"])
    assert len({item["event_id"] for item in payload["events"]}) == len(payload["events"])
    assert len({item["source_id"] for item in payload["evidence"]}) == len(payload["evidence"])

    corrected = next(item for item in payload["events"] if item["event_id"] == "event-yuchang-enc-samsung-ai-modular-home")
    assert corrected["event_type"] == "partnership"
    assert corrected["event_status"] == "not_signed"
    assert corrected["project_credit"] is False
    assert corrected["verification_status"] == "not_verified"
    assert len(corrected["source_ids"]) == 35
    assert not any(item["project_credit"] for item in payload["events"] if item["event_type"] in {"partnership", "mou"})

    credited = [item for item in payload["events"] if item["project_credit"]]
    assert len(credited) == 1
    assert all(item["event_type"] == "project" for item in credited)
    assert all(item["project_role"] not in {None, "", "unknown", "role_unknown"} for item in credited)

    public = public_v2_payload(payload)
    assert len(public["companies"]) == 17
    assert all(item.get("visibility") == "public" for key in ["companies", "facts", "events", "evidence", "corrections"] for item in public[key])
    assert not any(item.get("visibility") == "internal" for key in ["companies", "facts", "events", "evidence", "corrections"] for item in public[key])
    yuchang_summary = next(item for item in public["materialized_summaries"] if item["company_id"] == "yuchang-enc")
    assert yuchang_summary["event_counts"]["verified_projects"] == 0
    assert yuchang_summary["event_counts"]["partnerships_mou"] == 1
    assert yuchang_summary["article_evidence_count"] == 35
    assert yuchang_summary["project_status"] if "project_status" in yuchang_summary else True

    before = {company["company_id"]: protected_hash(company) for company in legacy["companies"]}
    materialized = materialize_companies(deepcopy(legacy), public, payload)
    after = {company["company_id"]: protected_hash(company) for company in materialized["companies"]}
    assert before == after
    assert all(company.get("intelligence_v2", {}).get("summary_ko") for company in materialized["companies"])
    assert all(company.get("intelligence_v2", {}).get("domain_statuses") for company in materialized["companies"])
    assert sum(company.get("intelligence_v2", {}).get("event_counts", {}).get("verified_projects", 0) for company in materialized["companies"]) == 1

    print("COMPANY INTELLIGENCE V2 TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
