from __future__ import annotations

from typing import Any

PROJECT_TERMS = ("수주", "계약", "낙찰", "착공", "공사 중", "준공", "완공")
MOU_TERMS = ("MOU", "업무협약", "협약", "양해각서")
PREFERRED_TERMS = ("우선협상", "우선대상", "preferred bidder")
STRATEGY_TERMS = ("인수", "투자", "증설", "신규시설", "영업양수", "합병", "분할")
TECH_TERMS = ("특허", "출원", "등록", "신기술", "인증")
PRODUCTION_TERMS = ("공장", "생산라인", "생산시설", "생산능력")
R_AND_D_TERMS = ("R&D", "연구개발", "실증", "전시", "박람회")
PLANNED_TERMS = ("검토", "예정", "계획", "추진", "후보", "기사에 따르면", "Pre-Con")


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def classify_text(title: str, summary: str = "") -> dict[str, Any]:
    text = f"{title} {summary}"
    result: dict[str, Any] = {
        "candidate_kind": "evidence",
        "domain": "market",
        "event_status": None,
        "project_credit": None,
        "promotion_blockers": [],
    }
    if contains_any(text, MOU_TERMS):
        result.update(candidate_kind="event", domain="strategy", event_status="mou_signed", project_credit=False)
        result["promotion_blockers"].append("mou_or_partnership_not_project_credit")
    elif contains_any(text, PREFERRED_TERMS):
        result.update(candidate_kind="event", domain="project", event_status="preferred_bidder", project_credit=False)
        result["promotion_blockers"].append("preferred_bidder_not_project_credit")
    elif contains_any(text, R_AND_D_TERMS):
        result.update(candidate_kind="event", domain="technology", event_status="r_and_d", project_credit=False)
        result["promotion_blockers"].append("research_or_exhibition_not_project_credit")
    elif contains_any(text, PRODUCTION_TERMS):
        result.update(candidate_kind="fact", domain="production")
    elif contains_any(text, TECH_TERMS):
        result.update(candidate_kind="fact", domain="technology")
    elif contains_any(text, STRATEGY_TERMS):
        result.update(candidate_kind="event", domain="strategy", event_status="planned", project_credit=False)
    elif contains_any(text, PROJECT_TERMS):
        result.update(candidate_kind="event", domain="project")
        if contains_any(text, ("준공", "완공")):
            result["event_status"] = "completed"
        elif contains_any(text, ("착공", "공사 중")):
            result["event_status"] = "under_construction"
        elif contains_any(text, ("수주", "계약", "낙찰")):
            result["event_status"] = "contracted"
        result["project_credit"] = False
        result["promotion_blockers"].append("official_role_review_required")

    if contains_any(text, PLANNED_TERMS):
        result["project_credit"] = False
        if result.get("event_status") in {"completed", "under_construction", "contracted", "awarded"}:
            result["event_status"] = "planned"
        if "planned_or_unconfirmed_not_project_credit" not in result["promotion_blockers"]:
            result["promotion_blockers"].append("planned_or_unconfirmed_not_project_credit")
    return result


def classify_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    classified = classify_text(candidate.get("title", ""), candidate.get("summary", ""))
    output = dict(candidate)
    for key in ("candidate_kind", "domain", "event_status", "project_credit"):
        if output.get(key) in (None, "", "market", "evidence"):
            output[key] = classified.get(key)
    blockers = list(dict.fromkeys([*(output.get("promotion_blockers") or []), *classified.get("promotion_blockers", [])]))
    output["promotion_blockers"] = blockers
    if output.get("project_credit") is True and output.get("event_status") not in {"completed", "under_construction", "contracted", "awarded"}:
        output["project_credit"] = False
        output["promotion_blockers"].append("project_credit_status_not_allowed")
    return output
