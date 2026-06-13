from __future__ import annotations

from datetime import date, datetime
from typing import Any

from src.collectors.d2b_plan import calculate_d2b_relevance
from src.collectors.d2b_bid import calculate_d2b_bid_relevance
from src.collectors.g2b import calculate_g2b_relevance
from src.collectors.lh import calculate_lh_relevance
from src.collectors.naver_news import calculate_naver_news_relevance
from src.dedup import make_unique_hash
from src.keywords import DEFAULT_KEYWORDS, EXCLUDE_KEYWORDS
from src.link_resolver import resolve_link
from src.text_utils import contains_modular_keyword


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _date_text(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    if isinstance(value, date):
        return value.isoformat()
    if len(text) == 6 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-01"

    for fmt in (
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y%m%d%H%M",
        "%Y%m%d",
    ):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return text


def _amount(value: Any) -> int | None:
    text = _text(value).replace(",", "").replace("원", "")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _raw_value(raw_item: dict, *keys: str) -> str:
    raw = raw_item.get("raw")
    if not isinstance(raw, dict):
        return ""
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _matched_keywords(raw_item: dict) -> list[str]:
    haystack = " ".join(
        _text(raw_item.get(key))
        for key in (
            "title",
            "summary",
            "description",
            "keywords",
            "organization",
            "demand_org",
            "category",
            "progress_status",
            "contract_method",
            "bid_method",
        )
    ).lower()
    if any(keyword.lower() in haystack for keyword in EXCLUDE_KEYWORDS):
        return []
    return [keyword for keyword in DEFAULT_KEYWORDS if keyword.lower() in haystack]


def _keyword_text(raw_item: dict, matched_keywords: list[str]) -> str | None:
    keywords = raw_item.get("keywords")
    if isinstance(keywords, list):
        return ";".join(str(keyword).strip() for keyword in keywords if str(keyword).strip()) or None
    return _optional_text(keywords) or (";".join(matched_keywords) if matched_keywords else None)


def normalize_item(raw_item: dict) -> dict:
    if raw_item.get("source_name") == "나라장터" and raw_item.get("source_type") == "procurement_plan":
        return _normalize_g2b_plan_item(raw_item)
    if raw_item.get("source_name") == "나라장터":
        return _normalize_g2b_item(raw_item)
    if raw_item.get("source_name") == "LH":
        return _normalize_lh_item(raw_item)
    if raw_item.get("source_name") == "D2B" and raw_item.get("source_type") == "procurement_plan":
        return _normalize_d2b_plan_item(raw_item)
    if raw_item.get("source_name") == "D2B" and raw_item.get("source_type") == "bid":
        return _normalize_d2b_bid_item(raw_item)
    if raw_item.get("source_name") == "네이버뉴스" and raw_item.get("source_type") == "news":
        return _normalize_naver_news_item(raw_item)

    matched_keywords = _matched_keywords(raw_item)
    item = {
        "source_type": _text(raw_item.get("source_type")),
        "source_name": _text(raw_item.get("source_name")),
        "title": _text(raw_item.get("title")),
        "organization": _optional_text(raw_item.get("organization")),
        "posted_at": _date_text(raw_item.get("posted_at")),
        "due_at": _date_text(raw_item.get("due_at")),
        "amount": _amount(raw_item.get("amount")),
        "region": _optional_text(raw_item.get("region")),
        "keywords": _keyword_text(raw_item, matched_keywords),
        "summary": _optional_text(raw_item.get("summary") or raw_item.get("description")),
        "url": _optional_text(raw_item.get("url")),
        "relevance_score": _generic_relevance_score(raw_item, matched_keywords),
    }
    return _finalize_item(raw_item, item)


def _finalize_item(raw_item: dict, item: dict) -> dict:
    item["is_mock"] = int(raw_item.get("is_mock") or 0)
    item["data_quality"] = _text(raw_item.get("data_quality")) or ("mock" if item["is_mock"] else "real")
    if item["data_quality"] in {"mock", "sample", "test"}:
        item["is_mock"] = 1

    resolved = resolve_link({**raw_item, **item})
    item.update(
        {
            "original_url": raw_item.get("original_url") or resolved.get("original_url"),
            "source_search_url": raw_item.get("source_search_url") or resolved.get("source_search_url"),
            "link_type": raw_item.get("link_type") or resolved.get("link_type") or "unknown",
            "link_status": raw_item.get("link_status") or resolved.get("link_status") or "unknown",
            "link_checked_at": raw_item.get("link_checked_at") or resolved.get("link_checked_at"),
            "source_record_id": raw_item.get("source_record_id") or resolved.get("source_record_id"),
            "source_record_no": raw_item.get("source_record_no") or resolved.get("source_record_no"),
            "exact_url_candidate": raw_item.get("exact_url_candidate") or resolved.get("exact_url_candidate"),
            "exact_url_verified": int(raw_item.get("exact_url_verified") or 0),
            "exact_url_verified_at": raw_item.get("exact_url_verified_at"),
            "exact_url_validation_reason": raw_item.get("exact_url_validation_reason"),
            "source_detail_api_url": raw_item.get("source_detail_api_url"),
            "source_portal_name": raw_item.get("source_portal_name") or _source_portal_name(item),
            "api_detail_verified": int(raw_item.get("api_detail_verified") or 0),
            "business_subtype": raw_item.get("business_subtype") or item.get("business_subtype"),
            "operating_scope": raw_item.get("operating_scope") or item.get("operating_scope"),
            "is_operating_scope": int(raw_item.get("is_operating_scope") or item.get("is_operating_scope") or 0),
            "is_known_important": int(raw_item.get("is_known_important") or item.get("is_known_important") or 0),
        }
    )
    if not item.get("url"):
        item["url"] = item.get("original_url") or item.get("source_search_url")
    item["unique_hash"] = raw_item.get("unique_hash") or make_unique_hash(item)
    return item


def _source_portal_name(item: dict) -> str | None:
    source_name = item.get("source_name")
    if source_name == "나라장터":
        return "나라장터"
    if source_name == "LH":
        return "LH 전자조달"
    if source_name == "D2B":
        return "국방전자조달"
    if source_name == "네이버뉴스":
        return "네이버뉴스"
    return None


def _generic_relevance_score(raw_item: dict, matched_keywords: list[str]) -> float:
    explicit_score = raw_item.get("relevance_score")
    if explicit_score not in (None, ""):
        try:
            return float(explicit_score)
        except ValueError:
            pass
    return min(100.0, 50.0 + (len(matched_keywords) * 10.0)) if matched_keywords else 0.0


def _normalize_g2b_item(raw_item: dict) -> dict:
    matched_keywords = _matched_keywords(raw_item)
    organization = _optional_text(raw_item.get("organization") or raw_item.get("demand_org"))
    bid_no = _text(raw_item.get("bidNtceNo") or raw_item.get("source_record_id"))
    bid_order = _text(raw_item.get("bidNtceOrd") or raw_item.get("source_record_no"))
    business_type = _text(raw_item.get("category") or raw_item.get("bsnsDivNm"))
    business_subtype = _text(raw_item.get("business_subtype") or raw_item.get("srvceDivNm") or business_type)
    is_scope = int(
        raw_item.get("is_operating_scope")
        or (
            business_type in {"물품", "용역", "臾쇳뭹", "?⑹뿭"}
            and contains_modular_keyword(raw_item.get("title"), "모듈러")
        )
        or 0
    )
    operating_scope = _text(raw_item.get("operating_scope")) or ("modular_goods_service" if is_scope else "")
    notice_status = _text(raw_item.get("ntceKindNm") or raw_item.get("notice_status"))
    contract_method = _text(raw_item.get("contract_method") or raw_item.get("cntrctCnclsMthdNm"))
    bid_method = _text(raw_item.get("bid_method") or raw_item.get("bidMethdNm"))
    demand_org = _text(raw_item.get("demand_org"))
    notice_org = _text(raw_item.get("notice_org") or raw_item.get("organization"))
    summary = _optional_text(raw_item.get("summary") or raw_item.get("description")) or (
        f"공고번호: {bid_no or '-'}; 공고차수: {bid_order or '-'}; 업무구분: {business_type or '-'}; "
        f"공고상태: {notice_status or '-'}; 계약방법: {contract_method or '-'}; 입찰방법: {bid_method or '-'}; "
        f"공고기관: {notice_org or '-'}; 수요기관: {demand_org or '-'}; 마감일: {_text(raw_item.get('due_at')) or '-'}"
    )
    item = {
        "source_type": "bid",
        "source_name": "나라장터",
        "title": _text(raw_item.get("title")),
        "organization": organization,
        "posted_at": _date_text(raw_item.get("posted_at")),
        "due_at": _date_text(raw_item.get("due_at")),
        "amount": _amount(raw_item.get("amount")),
        "region": _optional_text(raw_item.get("region")),
        "keywords": _keyword_text(raw_item, matched_keywords),
        "summary": summary,
        "url": _optional_text(raw_item.get("url")),
        "relevance_score": calculate_g2b_relevance(raw_item),
        "bid_no": bid_no,
        "bid_order": bid_order,
        "notice_status": notice_status,
        "business_type": business_type,
        "business_subtype": business_subtype,
        "operating_scope": operating_scope or None,
        "is_operating_scope": is_scope,
        "is_known_important": int(raw_item.get("is_known_important") or 0),
        "contract_method": contract_method,
        "bid_method": bid_method,
        "demand_org": demand_org,
        "notice_org": notice_org,
    }
    return _finalize_item(raw_item, item)


def _normalize_g2b_plan_item(raw_item: dict) -> dict:
    matched_keywords = _matched_keywords(raw_item)
    plan_no = _text(raw_item.get("plan_no") or raw_item.get("source_record_id") or raw_item.get("bid_no"))
    plan_order = _text(raw_item.get("source_record_no"))
    business_type = _text(raw_item.get("business_type") or raw_item.get("category"))
    amount = raw_item.get("amount") or _raw_value(raw_item, "sumOrderAmt", "orderAmt", "bdgtAmt", "budgetAmt")
    summary = _optional_text(raw_item.get("summary")) or (
        f"발주계획번호: {plan_no or '-'}; 발주예정: {_text(raw_item.get('due_at')) or '-'}; "
        f"업무구분: {business_type or '-'}; 계약방법: {_text(raw_item.get('contract_method')) or '-'}; "
        f"입찰방법: {_text(raw_item.get('bid_method')) or '-'}; "
        f"발주기관: {_text(raw_item.get('organization')) or '-'}; "
        f"수요기관: {_text(raw_item.get('demand_org')) or '-'}; 예산액: {_text(amount) or '-'}"
    )
    item = {
        "source_type": "procurement_plan",
        "source_name": "나라장터",
        "title": _text(raw_item.get("title")),
        "organization": _optional_text(raw_item.get("organization")),
        "posted_at": _date_text(raw_item.get("posted_at")),
        "due_at": _date_text(raw_item.get("due_at")),
        "amount": _amount(amount),
        "region": _optional_text(raw_item.get("region")),
        "keywords": _keyword_text(raw_item, matched_keywords),
        "summary": summary,
        "url": _optional_text(raw_item.get("url")),
        "relevance_score": _generic_relevance_score(raw_item, matched_keywords),
        "bid_no": plan_no,
        "bid_order": plan_order,
        "notice_status": _text(raw_item.get("notice_status")),
        "business_type": business_type,
        "business_subtype": _text(raw_item.get("business_subtype")) or "발주계획",
        "operating_scope": _text(raw_item.get("operating_scope")) or "modular_procurement_plan",
        "is_operating_scope": int(raw_item.get("is_operating_scope") or 1),
        "contract_method": _text(raw_item.get("contract_method")),
        "bid_method": _text(raw_item.get("bid_method")),
        "demand_org": _text(raw_item.get("demand_org")),
        "notice_org": _text(raw_item.get("organization")),
    }
    return _finalize_item(raw_item, item)


def _normalize_lh_item(raw_item: dict) -> dict:
    matched_keywords = _matched_keywords(raw_item)
    estimate = _raw_value(raw_item, "presmtPrc")
    base_amount = _raw_value(raw_item, "fdmtlAmt")
    bid_no = _text(raw_item.get("bid_no"))
    region = _optional_text(raw_item.get("region"))
    summary = _optional_text(raw_item.get("summary")) or (
        f"공고번호: {bid_no or '-'}; 담당지역: {region or '-'}; "
        f"추정가격: {estimate or '-'}; 기초금액: {base_amount or '-'}; "
        f"계약유형: {_text(raw_item.get('category')) or '-'}"
    )
    item = {
        "source_type": "bid",
        "source_name": "LH",
        "title": _text(raw_item.get("title")),
        "organization": _optional_text(raw_item.get("organization")) or "한국토지주택공사",
        "posted_at": _date_text(raw_item.get("posted_at")),
        "due_at": _date_text(raw_item.get("due_at")),
        "amount": _amount(raw_item.get("amount")),
        "region": region,
        "keywords": _keyword_text(raw_item, matched_keywords),
        "summary": summary,
        "url": _optional_text(raw_item.get("url")),
        "relevance_score": calculate_lh_relevance(raw_item),
    }
    return _finalize_item(raw_item, item)


def _normalize_d2b_plan_item(raw_item: dict) -> dict:
    matched_keywords = _matched_keywords(raw_item)
    order_month = _text(raw_item.get("order_month") or raw_item.get("posted_at"))
    amount = raw_item.get("amount") or _raw_value(raw_item, "bdgtAmount", "budgetAmount", "bdgtAmt")
    summary = _optional_text(raw_item.get("summary")) or (
        f"판단번호: {_text(raw_item.get('dcs_no')) or '-'}; 발주예정월: {order_month or '-'}; "
        f"계약방법: {_text(raw_item.get('contract_method')) or '-'}; "
        f"입찰방법: {_text(raw_item.get('bid_method')) or '-'}; "
        f"진행상태: {_text(raw_item.get('progress_status')) or '-'}; "
        f"예산금액: {_text(amount) or '-'}"
    )
    item = {
        "source_type": "procurement_plan",
        "source_name": "D2B",
        "title": _text(raw_item.get("title") or _raw_value(raw_item, "reprsntPrdlstNm")),
        "organization": _optional_text(raw_item.get("organization")) or _optional_text(raw_item.get("region")),
        "posted_at": _date_text(raw_item.get("posted_at")) or _date_text(order_month),
        "due_at": _date_text(raw_item.get("due_at") or order_month),
        "amount": _amount(amount),
        "region": _optional_text(raw_item.get("region")),
        "keywords": _keyword_text(raw_item, matched_keywords),
        "summary": summary,
        "url": _optional_text(raw_item.get("url")),
        "relevance_score": calculate_d2b_relevance(raw_item),
        "bid_no": _text(raw_item.get("plan_no") or raw_item.get("dcs_no") or raw_item.get("source_record_id")),
        "bid_order": _text(raw_item.get("source_record_no")),
        "notice_status": _text(raw_item.get("notice_status") or raw_item.get("progress_status")),
        "business_type": _text(raw_item.get("business_type") or raw_item.get("category")),
        "business_subtype": _text(raw_item.get("business_subtype")) or "조달계획",
        "operating_scope": _text(raw_item.get("operating_scope")) or "modular_procurement_plan",
        "is_operating_scope": int(raw_item.get("is_operating_scope") or 1),
        "contract_method": _text(raw_item.get("contract_method")),
        "bid_method": _text(raw_item.get("bid_method")),
        "demand_org": _text(raw_item.get("demand_org")),
        "notice_org": _text(raw_item.get("organization")),
    }
    return _finalize_item(raw_item, item)


def _normalize_d2b_bid_item(raw_item: dict) -> dict:
    matched_keywords = _matched_keywords(raw_item)
    amount = raw_item.get("amount") or _raw_value(raw_item, "budgetAmount", "bdgtAmount")
    due_at = raw_item.get("bid_submission_deadline") or raw_item.get("registration_deadline") or raw_item.get("due_at")
    summary = _optional_text(raw_item.get("summary")) or (
        f"공고번호: {_text(raw_item.get('bid_no') or raw_item.get('notice_no')) or '-'}; "
        f"요구년도: {_text(raw_item.get('demand_year')) or '-'}; "
        f"발주기관: {_text(raw_item.get('organization')) or '-'}; "
        f"계약방법: {_text(raw_item.get('contract_method')) or '-'}; "
        f"입찰방법: {_text(raw_item.get('bid_method')) or '-'}; "
        f"업무구분: {_text(raw_item.get('business_type') or raw_item.get('category')) or '-'}; "
        f"등록마감: {_text(raw_item.get('registration_deadline')) or '-'}; "
        f"입찰서제출마감: {_text(raw_item.get('bid_submission_deadline')) or '-'}; "
        f"개찰일시: {_text(raw_item.get('opening_datetime')) or '-'}"
    )
    item = {
        "source_type": "bid",
        "source_name": "D2B",
        "title": _text(raw_item.get("title") or raw_item.get("bid_name")),
        "organization": _optional_text(raw_item.get("organization")),
        "posted_at": _date_text(raw_item.get("posted_at")),
        "due_at": _date_text(due_at),
        "amount": _amount(amount),
        "region": _optional_text(raw_item.get("region") or raw_item.get("organization")),
        "keywords": _keyword_text(raw_item, matched_keywords),
        "summary": summary,
        "url": _optional_text(raw_item.get("url")),
        "relevance_score": calculate_d2b_bid_relevance(raw_item),
    }
    return _finalize_item(raw_item, item)


def _normalize_naver_news_item(raw_item: dict) -> dict:
    matched_keywords = raw_item.get("keywords")
    if not isinstance(matched_keywords, list):
        matched_keywords = _matched_keywords(raw_item)
    keyword_query = _text(raw_item.get("keyword_query"))
    keyword_text = _keyword_text(raw_item, matched_keywords)
    if keyword_query and (not keyword_text or keyword_query not in keyword_text):
        keyword_text = f"{keyword_text};{keyword_query}" if keyword_text else keyword_query

    item = {
        "source_type": "news",
        "source_name": "네이버뉴스",
        "title": _text(raw_item.get("title")),
        "organization": _optional_text(raw_item.get("publisher") or raw_item.get("organization")),
        "posted_at": _date_text(raw_item.get("pub_date") or raw_item.get("posted_at")),
        "due_at": None,
        "amount": None,
        "region": None,
        "keywords": keyword_text,
        "summary": _optional_text(raw_item.get("summary")),
        "url": _optional_text(raw_item.get("original_link") or raw_item.get("url") or raw_item.get("naver_link")),
        "relevance_score": calculate_naver_news_relevance(raw_item),
    }
    return _finalize_item(
        {**raw_item, "keyword_query": keyword_query},
        item,
    )
