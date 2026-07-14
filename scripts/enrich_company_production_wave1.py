#!/usr/bin/env python3
"""Apply source-backed Wave 1 production facility enrichment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COMPANIES_PATH = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"
TODAY = "2026-07-14"
NOW = "2026-07-14T00:00:00+09:00"


def upsert_source(company: dict[str, Any], source: dict[str, Any]) -> None:
    sources = company.setdefault("sources", [])
    for index, existing in enumerate(sources):
        if existing.get("source_id") == source["source_id"]:
            sources[index] = {**existing, **source}
            return
    sources.append(source)


def set_gap(company: dict[str, Any], area: str, status: str, note: str, source_ids: list[str] | None = None) -> None:
    gaps = [gap for gap in company.setdefault("research_gaps", []) if gap.get("area") != area]
    gap: dict[str, Any] = {"area": area, "status": status, "note": note}
    if source_ids:
        gap["source_ids"] = source_ids
        gap["verified_at"] = TODAY
    gaps.insert(0, gap)
    company["research_gaps"] = gaps


def set_production(company: dict[str, Any], summary: dict[str, Any], facilities: list[dict[str, Any]]) -> None:
    company["production_summary"] = summary
    company["production"] = facilities


def dart_source_ids(company: dict[str, Any]) -> list[str]:
    return [source["source_id"] for source in company.get("sources", []) if source.get("source_type") == "regulatory_filing"][:3]


def enrich() -> None:
    payload = json.loads(COMPANIES_PATH.read_text(encoding="utf-8"))
    companies = {company["company_id"]: company for company in payload["companies"]}

    yuchang = companies["yuchang-enc"]
    upsert_source(
        yuchang,
        {
            "source_id": "yc_official_home",
            "source_type": "official_website",
            "source_name": "YooChang official website",
            "title": "YooChang official website Factory section",
            "source_url": "https://yoochangenc.com/",
            "published_at": None,
            "accessed_at": TODAY,
            "publisher": "YooChang E&C",
            "primary_source": True,
            "confidence": "medium",
            "verification_note": "Official SPA exposes a YOOCHANG E&C Factory section with factory scale metrics in the bundled site content.",
            "page_or_section": "YOOCHANG E&C Factory",
            "supported_claims": ["facility_name", "ownership_type", "site_area_m2", "building_area_m2", "production_scope"],
        },
    )
    set_production(
        yuchang,
        {
            "research_status": "partially_verified",
            "verification_status": "verified_facility_without_capacity",
            "summary": "공식 홈페이지 Factory 섹션에서 생산시설 존재와 부지·공장 규모는 확인되나 공식 생산능력 수치는 공개자료에서 확인되지 않았습니다.",
            "own_facility_status": "confirmed_own_facility",
            "manufacturing_model": "own_manufacturing",
            "confirmed_facility_count": 1,
            "reported_capacity_available": False,
            "source_ids": ["yc_official_home"],
            "verified_at": TODAY,
            "data_confidence": "medium",
        },
        [
            {
                "facility_id": "yuchang-enc-yoochang-factory",
                "facility_name": "YOOCHANG E&C Factory",
                "facility_aliases": ["유창이앤씨 Factory"],
                "facility_type": "modular_factory",
                "own_facility_status": "confirmed_own_facility",
                "ownership_type": "company_operated_factory_claimed_by_official_site",
                "operation_status": "current_operation_unconfirmed",
                "country": "KR",
                "region": None,
                "city": None,
                "address": None,
                "site_area_m2": 60427.8,
                "building_area_m2": 25832,
                "production_scope": ["steel_modular_factory"],
                "structural_systems": ["steel_modular"],
                "main_equipment": [],
                "line_count": None,
                "reported_capacity": None,
                "capacity_value": None,
                "capacity_unit": None,
                "capacity_period": None,
                "capacity_basis": "not_publicly_disclosed",
                "capacity_as_of": None,
                "source_ids": ["yc_official_home"],
                "verified_at": TODAY,
                "confidence": "medium",
                "verification_note": "Facility name and site/building areas are taken from the official website Factory section; current operating status and capacity are not independently disclosed.",
            }
        ],
    )
    set_gap(
        yuchang,
        "production",
        "partially_verified",
        "Official website confirms a Factory section and scale metrics, but location, current operation, and official capacity remain incomplete.",
        ["yc_official_home"],
    )

    kumkang = companies["kumkang-kind"]
    upsert_source(
        kumkang,
        {
            "source_id": "kumkang_official_modular",
            "source_type": "official_website",
            "source_name": "Kumkang Kind official modular architecture page",
            "title": "금강공업 모듈러건축",
            "source_url": "https://www.kumkangkind.com/business/boxunit.asp?mCode=3",
            "published_at": None,
            "accessed_at": TODAY,
            "publisher": "Kumkang Kind",
            "primary_source": True,
            "confidence": "high",
            "verification_note": "Official modular architecture page states that modular units are produced at the factory and identifies Boeun factory in the modular system content.",
            "page_or_section": "사업분야 > 모듈러건축",
            "supported_claims": ["production_scope", "facility_name", "manufacturing_model", "ownership_type"],
        },
    )
    upsert_source(
        kumkang,
        {
            "source_id": "kumkang_official_domestic_network",
            "source_type": "official_website",
            "source_name": "Kumkang Kind domestic production network",
            "title": "금강공업 국내 생산공장",
            "source_url": "https://www.kumkangkind.com/company/network_internal.asp",
            "published_at": None,
            "accessed_at": TODAY,
            "publisher": "Kumkang Kind",
            "primary_source": True,
            "confidence": "high",
            "verification_note": "Official domestic network page lists production factories including Boeun factories under the construction business division.",
            "page_or_section": "회사소개 > 국내 생산공장",
            "supported_claims": ["facility_name", "location", "ownership_type", "operation_status"],
        },
    )
    set_production(
        kumkang,
        {
            "research_status": "partially_verified",
            "verification_status": "verified_facility_without_capacity",
            "summary": "공식 홈페이지에서 보은공장 기반 모듈러 유닛 생산은 확인되나 공식 생산능력 수치는 공개자료에서 확인되지 않았습니다.",
            "own_facility_status": "confirmed_own_facility",
            "manufacturing_model": "own_manufacturing",
            "confirmed_facility_count": 1,
            "reported_capacity_available": False,
            "source_ids": ["kumkang_official_modular", "kumkang_official_domestic_network"],
            "verified_at": TODAY,
            "data_confidence": "high",
        },
        [
            {
                "facility_id": "kumkang-kind-boeun-factory",
                "facility_name": "보은공장",
                "facility_aliases": ["보은1공장", "보은2공장"],
                "facility_type": "modular_factory",
                "own_facility_status": "confirmed_own_facility",
                "ownership_type": "company_production_factory",
                "operation_status": "active_on_official_site",
                "country": "KR",
                "region": "충청북도",
                "city": "보은군",
                "address": None,
                "site_area_m2": None,
                "building_area_m2": None,
                "production_scope": ["steel_modular_units"],
                "structural_systems": ["steel_volumetric"],
                "main_equipment": [],
                "line_count": None,
                "reported_capacity": None,
                "capacity_value": None,
                "capacity_unit": None,
                "capacity_period": None,
                "capacity_basis": "not_publicly_disclosed",
                "capacity_as_of": None,
                "source_ids": ["kumkang_official_modular", "kumkang_official_domestic_network"],
                "verified_at": TODAY,
                "confidence": "high",
                "verification_note": "Official modular page links modular unit production to Boeun factory; network page identifies Boeun production factories. Official capacity is not disclosed.",
            }
        ],
    )
    set_gap(
        kumkang,
        "production",
        "partially_verified",
        "Official sources confirm Boeun-factory modular unit production, but official capacity and detailed modular line metrics remain undisclosed.",
        ["kumkang_official_modular", "kumkang_official_domestic_network"],
    )

    for company_id in ["planm", "daeseung-engineering"]:
        company = companies[company_id]
        source_ids = dart_source_ids(company)
        set_production(
            company,
            {
                "research_status": "searched_not_confirmed",
                "verification_status": "not_publicly_confirmed",
                "summary": "OpenDART 감사보고서와 기존 공개 출처 범위에서 검증된 생산시설 또는 공식 생산능력 수치를 확인하지 못했습니다.",
                "own_facility_status": "not_publicly_confirmed",
                "manufacturing_model": "not_publicly_confirmed",
                "confirmed_facility_count": 0,
                "reported_capacity_available": False,
                "source_ids": source_ids,
                "verified_at": TODAY,
                "data_confidence": "unknown",
            },
            [],
        )
        set_gap(
            company,
            "production",
            "not_publicly_confirmed",
            "No source-backed production facility or official capacity record was confirmed in OpenDART filings and available public-source review for this step.",
            source_ids,
        )

    for company_id in ["yuchang-enc", "kumkang-kind", "planm", "daeseung-engineering"]:
        companies[company_id]["last_verified_at"] = NOW

    COMPANIES_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    enrich()
