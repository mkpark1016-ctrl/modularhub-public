from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPANIES_PATH = ROOT / "frontend/public/data/companies/companies.json"
STRATEGY_PATH = ROOT / "frontend/public/data/companies/company_strategy.json"

EXPECTED_DIRECT_COMPETITORS = {
    "daeseung-engineering",
    "geogwang-enterprise",
    "kumkang-kind",
    "nrb",
    "planm",
    "sungji-steel",
    "yuchang-enc",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_strategy_covers_exact_canonical_company_universe() -> None:
    companies_payload = load(COMPANIES_PATH)
    companies = companies_payload if isinstance(companies_payload, list) else companies_payload["companies"]
    strategy = load(STRATEGY_PATH)
    records = strategy["records"]

    canonical_ids = {company["company_id"] for company in companies}
    strategy_ids = [record["company_id"] for record in records]

    assert strategy["schema_version"] == "company_strategy_v1"
    assert strategy["as_of_date"] == "2026-08-10"
    assert len(companies) == 11
    assert len(records) == 11
    assert len(strategy_ids) == len(set(strategy_ids))
    assert set(strategy_ids) == canonical_ids


def test_user_business_judgment_marks_exact_seven_modular_competitors() -> None:
    strategy = load(STRATEGY_PATH)
    records = strategy["records"]

    direct_ids = {
        record["company_id"]
        for record in records
        if record["strategic_role"] == "direct_competitor"
    }
    inherited_ids = {
        record["company_id"]
        for record in records
        if record["strategic_role"] == "inherit"
    }

    assert direct_ids == EXPECTED_DIRECT_COMPETITORS
    assert len(inherited_ids) == 4

    for record in records:
        if record["company_id"] in EXPECTED_DIRECT_COMPETITORS:
            assert record["basis"] == "user_business_judgment"
            assert record["reviewed_at"] == "2026-08-10"
        else:
            assert record["basis"] == "canonical_fallback"
            assert record["reviewed_at"] is None
        assert record["priority"] is None
        assert record["watch_reason"] is None
        assert record["owner_note"] is None
