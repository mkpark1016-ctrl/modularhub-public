#!/usr/bin/env python3
"""Apply QA-R1A display and evidence normalization for Kumkang Kind facilities.

This is a narrow, auditable overlay for the pilot PR. It does not invent capacity,
change financials, or touch protected business/news/meta datasets.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OVERLAY_PATH = ROOT / "config/companies/curated/kumkang-kind-qa-r1a.json"
V1_PATH = ROOT / "frontend/public/data/companies/companies.json"
V2_PATH = ROOT / "frontend/public/data/companies/company_intelligence_v2.json"
APP_PATH = ROOT / "frontend/src/App.jsx"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def merge_unique(*collections: Any) -> list[Any]:
    result: list[Any] = []
    for collection in collections:
        if collection is None:
            continue
        values = collection if isinstance(collection, list) else [collection]
        for value in values:
            if value not in result:
                result.append(value)
    return result


def normalize_v1(payload: dict[str, Any], overlay: dict[str, Any]) -> None:
    company = next(
        (
            item
            for item in payload.get("companies", [])
            if item.get("company_id") == overlay["company_id"]
        ),
        None,
    )
    if company is None:
        raise SystemExit("Kumkang Kind is missing from companies.json")

    production = company.get("production")
    if not isinstance(production, list):
        raise SystemExit("Kumkang production must be a list")

    by_id = {item.get("facility_id"): item for item in production}
    if len(by_id) != len(production):
        raise SystemExit("Duplicate facility_id found before QA-R1A normalization")

    for correction in overlay["facilities"]:
        facility_id = correction["facility_id"]
        facility = by_id.get(facility_id)
        if facility is None:
            raise SystemExit(f"Facility missing from companies.json: {facility_id}")

        original_name = facility.get("facility_name")
        display_name = correction["display_name"]
        if original_name and original_name != display_name:
            facility.setdefault("official_name", original_name)

        facility["facility_name"] = display_name
        facility["display_name"] = display_name
        facility["facility_aliases"] = merge_unique(
            facility.get("facility_aliases"),
            correction.get("facility_aliases"),
            [original_name] if original_name else [],
        )
        facility["address"] = correction.get("address")
        facility["verification_status"] = correction["verification_status"]
        facility["data_confidence"] = correction["data_confidence"]
        facility["confidence"] = correction["data_confidence"]
        facility["verification_basis_label"] = correction[
            "verification_basis_label"
        ]
        facility["identity_note"] = correction["identity_note"]
        facility["qa_reviewed_at"] = overlay["reviewed_at"]

    boeun_1 = by_id["kumkang-kind-boeun-factory"]
    boeun_2 = by_id["kumkang-kind-boeun-2-factory"]
    if boeun_1.get("address") == boeun_2.get("address"):
        raise SystemExit("Boeun 1 and Boeun 2 must not share the same address")

    alias_1 = set(boeun_1.get("facility_aliases") or [])
    alias_2 = set(boeun_2.get("facility_aliases") or [])
    overlap = alias_1 & alias_2
    if overlap:
        raise SystemExit(f"Boeun facility alias collision: {sorted(overlap)}")


def normalize_v2(payload: dict[str, Any], overlay: dict[str, Any]) -> None:
    facts = payload.get("facts")
    if not isinstance(facts, list):
        raise SystemExit("V2 facts must be a list")

    fact_by_field = {
        fact.get("field"): fact
        for fact in facts
        if fact.get("company_id") == overlay["company_id"]
        and fact.get("domain") == "production"
    }

    for correction in overlay["facilities"]:
        field = f"facility_{correction['facility_id']}"
        fact = fact_by_field.get(field)
        if fact is None:
            raise SystemExit(f"V2 facility fact missing: {field}")
        value = fact.get("value")
        if not isinstance(value, dict):
            raise SystemExit(f"V2 facility fact value must be an object: {field}")

        original_name = value.get("facility_name")
        value["facility_name"] = correction["display_name"]
        value["display_name"] = correction["display_name"]
        value["facility_aliases"] = merge_unique(
            value.get("facility_aliases"),
            correction.get("facility_aliases"),
            [original_name] if original_name else [],
        )
        value["address"] = correction.get("address")
        value["verification_basis_label"] = correction[
            "verification_basis_label"
        ]
        value["identity_note"] = correction["identity_note"]
        value["qa_reviewed_at"] = overlay["reviewed_at"]
        fact["verification_status"] = correction["verification_status"]
        fact["confidence"] = correction["data_confidence"]
        fact["updated_at"] = overlay["reviewed_at"]


def patch_app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    old_title = '<strong>{item.facility_name || "시설명 확인 중"}</strong>'
    new_title = '<strong>{item.display_name || item.facility_name || "시설명 확인 중"}</strong>'
    if old_title in text:
        text = text.replace(old_title, new_title, 1)
    elif new_title not in text:
        raise SystemExit("Production facility title marker not found in App.jsx")

    location_line = '                    <span>{[item.region || item.city || item.location, getDisplayValue(item.ownership_type), getDisplayValue(item.operation_status)].filter(Boolean).join(" · ") || "위치 정보 확인 중"}</span>\n'
    evidence_lines = (
        location_line
        + '                    {item.address && <span>주소: {item.address}</span>}\n'
        + '                    {item.identity_note && <span>{item.identity_note}</span>}\n'
    )
    if "{item.address && <span>주소: {item.address}</span>}" not in text:
        if location_line not in text:
            raise SystemExit("Production facility location marker not found in App.jsx")
        text = text.replace(location_line, evidence_lines, 1)

    confidence_line = '                    <span>검증 상태: {getConfidenceLabel({ data_confidence: item.data_confidence || item.confidence || productionInfo.data_confidence })}</span>\n'
    normalized_confidence_lines = (
        '                    {item.verification_basis_label && <span>근거 기준: {item.verification_basis_label}</span>}\n'
        + '                    <span>신뢰도: {getConfidenceLabel({ data_confidence: item.data_confidence || item.confidence || productionInfo.data_confidence })}</span>\n'
    )
    if "근거 기준: {item.verification_basis_label}" not in text:
        if confidence_line not in text:
            raise SystemExit("Production confidence marker not found in App.jsx")
        text = text.replace(confidence_line, normalized_confidence_lines, 1)

    path.write_text(text, encoding="utf-8")


def main() -> int:
    overlay = load_json(OVERLAY_PATH)
    v1 = load_json(V1_PATH)
    v2 = load_json(V2_PATH)

    normalize_v1(v1, overlay)
    normalize_v2(v2, overlay)
    patch_app(APP_PATH)

    dump_json(V1_PATH, v1)
    dump_json(V2_PATH, v2)
    print("PASS: QA-R1A Kumkang facility identity and evidence normalization")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
