from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.integrations.technology.reconciliation import normalize_fixture_records, reconcile_technology_records


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_COMPANIES = ROOT / "frontend/public/data/companies/companies.json"
DEFAULT_FIXTURE = ROOT / "tests/fixtures/company_technology/samsung_official_records.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts/company-technology/samsung-pilot"


def load_companies(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    companies = payload.get("companies") if isinstance(payload, dict) else payload
    if not isinstance(companies, list):
        raise ValueError("companies input must contain a companies array")
    return companies


def run_dry_run(
    companies_path: Path,
    fixture_path: Path,
    output_dir: Path,
    company_id: str = "samsung-ct-construction",
) -> dict[str, Any]:
    companies = [company for company in load_companies(companies_path) if company.get("company_id") == company_id]
    if len(companies) != 1:
        raise ValueError(f"pilot company must resolve exactly once: {company_id}")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    raw_records = fixture.get("records") if isinstance(fixture, dict) else fixture
    if not isinstance(raw_records, list):
        raise ValueError("fixture input must contain a records array")
    normalization = normalize_fixture_records(raw_records)
    candidates, report = reconcile_technology_records(companies, normalization)

    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_payload = [record.as_dict() for record in normalization.records]
    _write_json(output_dir / "normalized_technology_records.json", normalized_payload)
    _write_json(output_dir / "public_projection_candidates.json", candidates)
    _write_json(output_dir / "reconciliation_report.json", report)
    report["deterministic_content_sha256"] = {
        "normalized": _content_hash(normalized_payload),
        "candidates": _content_hash(candidates),
        "report_without_hashes": _content_hash(report),
    }
    _write_json(output_dir / "reconciliation_report.json", report)
    return report


def _content_hash(payload: Any) -> str:
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the offline Samsung technology fixture reconciliation.")
    parser.add_argument("--companies", type=Path, default=DEFAULT_COMPANIES)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--company-id", default="samsung-ct-construction")
    args = parser.parse_args()
    report = run_dry_run(args.companies, args.fixture, args.output_dir, args.company_id)
    metrics = {key: value for key, value in report.items() if key.endswith("_count")}
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["conflict_count"] == 0 and report["credential_exposure_count"] == report["invalid_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
