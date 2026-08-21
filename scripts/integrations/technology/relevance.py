from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from scripts.integrations.technology.base import NormalizedTechnologyRecord


DIRECT_TERMS = (
    "모듈러 건축",
    "모듈러 건축물",
    "모듈러 주택",
    "모듈러",
    "공업화주택",
    "프리패브",
    "프리팹",
    "modular construction",
    "modular building",
    "modular housing",
)
SUPPORTING_TERMS = (
    "유닛",
    "접합",
    "체결",
    "슬래브",
    "철골",
    "바닥",
    "외장",
    "내화",
    "방수",
    "기밀",
    "패널",
    "적층",
    "시공",
)
CONSTRUCTION_CONTEXT = (
    "건축",
    "건설",
    "구조",
    "공법",
    "주택",
    "현장",
    "콘크리트",
    "철골",
    "슬래브",
    "외장",
    "내화",
    "방수",
    "기밀",
    "시공",
)
ELECTRONIC_CONTEXT = (
    "전자",
    "통신",
    "반도체",
    "배터리",
    "회로",
    "안테나",
    "센서",
    "디스플레이",
    "메모리",
    "무선",
)

AREA_RULES = (
    ("내화", ("내화", "화재", "방화")),
    ("차음·진동", ("차음", "소음", "진동")),
    ("방수·기밀", ("방수", "수밀", "기밀")),
    ("외장·단열", ("외장", "단열", "커튼월")),
    ("바닥·슬래브", ("바닥", "슬래브")),
    ("고층화", ("고층", "적층", "층간")),
    ("운송·양중", ("운송", "양중", "인양")),
    ("제작자동화", ("자동화", "로봇", "제작라인")),
    ("MEP·설비", ("배관", "전기설비", "기계설비", "mep")),
    ("BIM·디지털", ("bim", "디지털", "스마트건설")),
    ("친환경·재사용", ("재사용", "재활용", "친환경", "탄소")),
    ("구조·접합", ("접합", "체결", "연결", "브래킷", "플레이트", "구조")),
    ("현장시공", ("시공", "공법", "현장")),
)


@dataclass(frozen=True)
class RelevanceDecision:
    level: str
    matched_terms: tuple[str, ...]
    relevance_reason: str
    technology_area: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "matched_terms": list(self.matched_terms),
            "relevance_reason": self.relevance_reason,
            "technology_area": self.technology_area,
        }


def _record_text(record: NormalizedTechnologyRecord) -> str:
    return " ".join((record.title, record.abstract or "", *record.keywords)).casefold()


def _contains(text: str, term: str) -> bool:
    if term.casefold() == "osc":
        return bool(re.search(r"(?<![0-9a-z])osc(?![0-9a-z])", text))
    return term.casefold() in text


def classify_technology_area(record: NormalizedTechnologyRecord) -> str:
    if record.technology_area:
        return record.technology_area
    text = _record_text(record)
    for area, terms in AREA_RULES:
        if any(_contains(text, term) for term in terms):
            return area
    return "기타"


def assess_modular_relevance(record: NormalizedTechnologyRecord) -> RelevanceDecision:
    text = _record_text(record)
    direct = tuple(term for term in DIRECT_TERMS if _contains(text, term))
    if _contains(text, "osc"):
        direct = tuple(dict.fromkeys((*direct, "OSC")))
    if direct:
        return RelevanceDecision(
            "direct",
            direct,
            "direct_modular_concept",
            classify_technology_area(record),
        )

    supporting = tuple(term for term in SUPPORTING_TERMS if _contains(text, term))
    construction = tuple(term for term in CONSTRUCTION_CONTEXT if _contains(text, term))
    electronic = tuple(term for term in ELECTRONIC_CONTEXT if _contains(text, term))
    if electronic and not construction:
        return RelevanceDecision(
            "irrelevant",
            tuple(dict.fromkeys((*supporting, *electronic))),
            "electronic_or_non_construction_module_context",
            classify_technology_area(record),
        )
    if supporting and construction:
        return RelevanceDecision(
            "adjacent",
            tuple(dict.fromkeys((*supporting, *construction))),
            "construction_supporting_concepts",
            classify_technology_area(record),
        )
    return RelevanceDecision(
        "irrelevant",
        supporting,
        "no_direct_or_supported_modular_construction_match",
        classify_technology_area(record),
    )
