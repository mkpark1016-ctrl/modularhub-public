from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse


OPPORTUNITY_STAGES = {"pre_notice", "main_notice", "re_notice", "correction"}

MODULAR_CONFIRMED_TERMS = [
    "모듈러",
    "OSC",
    "Off-Site",
    "공업화주택",
    "프리패브",
    "PC 모듈러",
    "스틸 모듈러",
    "공장제작",
    "DfMA",
]

PUBLIC_HOUSING_CONTEXT_TERMS = [
    "민간참여 공공주택",
    "민간참여 공공주택건설사업",
    "민간참여 공공주택사업",
    "민간사업자 공모",
    "공공주택건설사업",
]


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_title(title: str) -> str:
    text = clean_text(title)
    remove_terms = [
        "사전예고",
        "본공고",
        "재공고",
        "정정공고",
        "수정공고",
        "평가결과",
        "우선협상대상자",
        "선정결과",
        "심사결과",
        "당선작",
        "계약체결",
    ]
    for term in remove_terms:
        text = text.replace(term, " ")
    text = re.sub(r"\b20\d{2}\s*년?\s*제?\s*\d+\s*차\b", " ", text)
    text = re.sub(r"\[[^\]]+\]|\([^)]+\)", " ", text)
    text = re.sub(r"[-_·ㆍ:]+", " ", text)
    return clean_text(text)


def classify_notice_stage(title: str, body: str = "") -> str:
    text = f"{title} {body}"
    if any(term in text for term in ["우선협상대상자", "선정결과", "심사결과", "평가결과", "당선작", "계약체결"]):
        return "result"
    if any(term in text for term in ["질의답변", "일정변경", "자료수정", "추가자료", "추가 안내"]):
        return "update"
    if any(term in text for term in ["정정공고", "수정공고"]):
        return "correction"
    if any(term in text for term in ["재공고", "재공모"]):
        return "re_notice"
    if "사전예고" in text:
        return "pre_notice"
    if any(term in text for term in ["공모", "공고"]):
        return "main_notice"
    return "unknown"


def is_business_opportunity_stage(stage: str) -> bool:
    return stage in OPPORTUNITY_STAGES


@dataclass(frozen=True)
class ModularRelevance:
    value: str
    score: int
    evidence: list[str]


def classify_modular_relevance(*texts: str, attachment_names: Iterable[str] = ()) -> ModularRelevance:
    haystack = " ".join([clean_text(text) for text in texts] + [clean_text(name) for name in attachment_names])
    lowered = haystack.lower()
    evidence = [term for term in MODULAR_CONFIRMED_TERMS if term.lower() in lowered]
    if evidence:
        return ModularRelevance("confirmed", 10, evidence)
    if any(term in haystack for term in PUBLIC_HOUSING_CONTEXT_TERMS):
        return ModularRelevance("review_candidate", 3, ["민간참여 공공주택 공모"])
    return ModularRelevance("unconfirmed", 0, [])


def host_allowed(url: str, allowed_domains: Iterable[str]) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    return any(host == domain.lower() or host.endswith("." + domain.lower()) for domain in allowed_domains)


def is_probable_list_url(url: str) -> bool:
    parsed = urlparse(url)
    query = parsed.query.lower()
    if not query:
        return True
    return not any(key in query for key in ["list_no=", "articleno=", "msg_seq=", "seq=", "ntt", "view", "act=view"])


def validate_exact_detail_url(url: str, *, allowed_domains: Iterable[str], source_record_id: str) -> tuple[bool, str]:
    if not host_allowed(url, allowed_domains):
        return False, "domain_not_allowed"
    if is_probable_list_url(url):
        return False, "list_url_not_exact"
    if source_record_id and source_record_id not in url:
        return False, "source_record_id_missing_in_url"
    return True, "candidate_url_ok"
