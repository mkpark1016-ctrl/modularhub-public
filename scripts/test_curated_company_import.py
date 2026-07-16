#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/import_curated_company_baseline.py"
spec = importlib.util.spec_from_file_location("curated_importer", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def main() -> int:
    curated = module.load(module.DEFAULT_CURATED)
    v1_original = module.load(module.DEFAULT_V1)
    v2_original = module.load(module.DEFAULT_V2)

    protected = {
        path: (ROOT / path).read_bytes()
        for path in (
            "frontend/public/data/business.json",
            "frontend/public/data/news.json",
            "frontend/public/data/meta.json",
        )
    }

    v1 = module.merge_v1(copy.deepcopy(v1_original), curated)
    v2 = module.merge_v2(copy.deepcopy(v2_original), curated)

    assert len(v1["companies"]) == len(v1_original["companies"]) == 17
    assert {c["company_id"] for c in v1["companies"]} == {c["company_id"] for c in v1_original["companies"]}

    company = next(c for c in v1["companies"] if c["company_id"] == "kumkang-kind")
    assert len(company["production"]) >= 3
    assert len(company["project_portfolio"]) >= 10
    assert len(company["technology"]["patents"]) >= 4
    assert all(f.get("reported_capacity") is None for f in company["production"] if f["facility_id"].startswith("kumkang-kind-"))
    assert len(company.get("financials", [])) == len(next(c for c in v1_original["companies"] if c["company_id"] == "kumkang-kind").get("financials", []))

    project_ids = [p["project_id"] for p in company["project_portfolio"]]
    assert len(project_ids) == len(set(project_ids))
    event_ids = [e["event_id"] for e in v2["events"]]
    fact_ids = [f["fact_id"] for f in v2["facts"]]
    source_ids = [e["source_id"] for e in v2["evidence"]]
    assert len(event_ids) == len(set(event_ids))
    assert len(fact_ids) == len(set(fact_ids))
    assert len(source_ids) == len(set(source_ids))

    credited = [e for e in v2["events"] if e.get("company_id") == "kumkang-kind" and e.get("event_type") == "project" and e.get("project_credit")]
    noncredited = [e for e in v2["events"] if e.get("company_id") == "kumkang-kind" and not e.get("project_credit")]
    assert credited
    assert noncredited

    for path, before in protected.items():
        assert (ROOT / path).read_bytes() == before, f"protected file changed: {path}"

    serialized = json.dumps(v1, ensure_ascii=False) + json.dumps(v2, ensure_ascii=False)
    for forbidden in ("OPEN_DART_API_KEY", "DART_API_KEY", "api_key=", "secret="):
        assert forbidden.lower() not in serialized.lower()

    print("PASS: curated Kumkang baseline merge contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
