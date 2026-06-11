from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class Item(BaseModel):
    source_type: str = Field(..., description="입찰/조달, 뉴스, R&D/특허 등")
    source_name: str
    title: str
    organization: str | None = None
    posted_at: date | None = None
    due_at: date | None = None
    amount: int | None = None
    region: str | None = None
    keywords: str | None = None
    summary: str | None = None
    url: str | None = None
    relevance_score: float = 0.0
    unique_hash: str
    is_mock: int = 0
    data_quality: str = "real"
    original_url: str | None = None
    source_search_url: str | None = None
    link_type: str = "unknown"
    link_status: str = "unknown"
    link_checked_at: str | None = None
    source_record_id: str | None = None
    source_record_no: str | None = None
    bid_no: str | None = None
    bid_order: str | None = None
    notice_status: str | None = None
    business_type: str | None = None
    business_subtype: str | None = None
    operating_scope: str | None = None
    is_operating_scope: int = 0
    is_known_important: int = 0
    contract_method: str | None = None
    bid_method: str | None = None
    demand_org: str | None = None
    notice_org: str | None = None
    exact_url_candidate: str | None = None
    exact_url_verified: int = 0
    exact_url_verified_at: str | None = None
    exact_url_validation_reason: str | None = None
    source_detail_api_url: str | None = None
    source_portal_name: str | None = None
    api_detail_verified: int = 0
