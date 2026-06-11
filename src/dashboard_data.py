from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from src.database import load_collect_logs_dataframe, load_items_dataframe
from src.keywords import NAVER_NEWS_COMPETITOR_KEYWORDS
from src.text_utils import contains_modular_keyword


SOURCE_TYPE_LABELS = {
    "bid": "입찰·공고",
    "입찰/조달": "입찰·공고",
    "procurement_plan": "조달계획",
    "news": "뉴스",
    "뉴스": "뉴스",
    "patent": "특허",
    "rnd": "R&D",
    "R&D/특허": "R&D/특허",
    "mock": "샘플",
}

BID_TYPES = {"bid", "입찰/조달"}
PLAN_TYPES = {"procurement_plan"}
NEWS_TYPES = {"news", "뉴스"}
HIGH_RELEVANCE_THRESHOLD = 8.0


@st.cache_data(ttl=300)
def load_items() -> pd.DataFrame:
    return load_items_dataframe()


@st.cache_data(ttl=300)
def load_collect_logs(limit: int = 50) -> pd.DataFrame:
    return load_collect_logs_dataframe(limit=limit)


def _to_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def prepare_dashboard_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    prepared = df.copy()
    for column in ("posted_at", "due_at", "created_at", "updated_at"):
        if column in prepared.columns:
            prepared[column] = _to_datetime(prepared[column])

    prepared["source_type_label"] = prepared["source_type"].map(SOURCE_TYPE_LABELS).fillna(prepared["source_type"])
    for column, default in {
        "is_mock": 0,
        "data_quality": "real",
        "original_url": None,
        "source_search_url": None,
        "link_type": "unknown",
        "link_status": "unknown",
        "source_record_id": None,
        "source_record_no": None,
        "bid_no": None,
        "bid_order": None,
        "notice_status": None,
        "business_type": None,
        "business_subtype": None,
        "operating_scope": None,
        "is_operating_scope": 0,
        "is_known_important": 0,
        "contract_method": None,
        "bid_method": None,
        "demand_org": None,
        "notice_org": None,
        "exact_url_candidate": None,
        "exact_url_verified": 0,
        "exact_url_verified_at": None,
        "exact_url_validation_reason": None,
        "source_detail_api_url": None,
        "source_portal_name": None,
        "api_detail_verified": 0,
    }.items():
        if column not in prepared.columns:
            prepared[column] = default
    prepared["is_mock"] = pd.to_numeric(prepared["is_mock"], errors="coerce").fillna(0).astype(int)
    prepared["data_quality"] = prepared["data_quality"].fillna("real")
    prepared["link_type"] = prepared["link_type"].fillna("unknown")
    prepared["link_status"] = prepared["link_status"].fillna("unknown")
    prepared["exact_url_verified"] = pd.to_numeric(prepared["exact_url_verified"], errors="coerce").fillna(0).astype(int)
    prepared["api_detail_verified"] = pd.to_numeric(prepared["api_detail_verified"], errors="coerce").fillna(0).astype(int)
    prepared["is_operating_scope"] = pd.to_numeric(prepared["is_operating_scope"], errors="coerce").fillna(0).astype(int)
    prepared["is_known_important"] = pd.to_numeric(prepared["is_known_important"], errors="coerce").fillna(0).astype(int)
    prepared["relevance_score"] = pd.to_numeric(prepared["relevance_score"], errors="coerce").fillna(0)
    prepared["amount"] = pd.to_numeric(prepared["amount"], errors="coerce")
    prepared["is_bid"] = prepared["source_type"].isin(BID_TYPES)
    prepared["is_plan"] = prepared["source_type"].isin(PLAN_TYPES)
    prepared["is_news"] = prepared["source_type"].isin(NEWS_TYPES)
    prepared["is_due_soon"] = _is_due_soon(prepared)
    prepared["is_high_relevance"] = prepared["relevance_score"] >= HIGH_RELEVANCE_THRESHOLD
    prepared["has_competitor_news"] = prepared.apply(_has_competitor_news, axis=1)
    return prepared


def calculate_kpis(df: pd.DataFrame) -> dict[str, int]:
    if df.empty:
        return {
            "total": 0,
            "new_24h": 0,
            "bid": 0,
            "plan": 0,
            "news": 0,
            "due_soon": 0,
            "high_relevance": 0,
        }

    now = pd.Timestamp.now()
    created_at = df["created_at"] if "created_at" in df.columns else pd.Series(pd.NaT, index=df.index)
    return {
        "total": len(df),
        "new_24h": int((created_at >= now - pd.Timedelta(hours=24)).sum()),
        "bid": int(df["is_bid"].sum()),
        "plan": int(df["is_plan"].sum()),
        "news": int(df["is_news"].sum()),
        "due_soon": int(df["is_due_soon"].sum()),
        "high_relevance": int(df["is_high_relevance"].sum()),
    }


def filter_items(
    df: pd.DataFrame,
    *,
    search_text: str = "",
    source_types: list[str] | None = None,
    source_names: list[str] | None = None,
    posted_range: tuple[date | None, date | None] | None = None,
    due_range: tuple[date | None, date | None] | None = None,
    min_relevance: float = 0.0,
    business_types: list[str] | None = None,
    g2b_modular_goods_only: bool = False,
    g2b_modular_scope_only: bool = False,
    service_candidate_only: bool = False,
    title_modular_only: bool = False,
    include_cancelled: bool = True,
    include_correction: bool = True,
    keyword: str = "",
    due_soon_only: bool = False,
    news_only: bool = False,
    bid_only: bool = False,
    plan_only: bool = False,
    important_only: bool = False,
    include_outside_important: bool = True,
    known_bid_nos: list[str] | None = None,
    sort_order: str = "게시일 최신순",
) -> pd.DataFrame:
    filtered = df.copy()
    if filtered.empty:
        return filtered

    if source_types:
        filtered = filtered[filtered["source_type"].isin(source_types)]
    if source_names:
        filtered = filtered[filtered["source_name"].isin(source_names)]
    if min_relevance > 0:
        filtered = filtered[filtered["relevance_score"] >= min_relevance]
    if business_types:
        filtered = filtered[
            filtered["business_type"].isin(business_types) | filtered["business_type"].isna() | filtered["business_type"].eq("")
        ]
    known_bid_nos = known_bid_nos or []
    before_operating_filter = filtered.copy()
    if g2b_modular_scope_only:
        modular_title = filtered["title"].fillna("").apply(contains_modular_keyword)
        g2b_source = filtered["source_name"].isin(["나라장터", "G2B", "조달청"])
        g2b_scope = g2b_source & (
            filtered["operating_scope"].eq("modular_goods_service")
            | filtered["is_operating_scope"].eq(1)
            | (filtered["business_type"].isin(["물품", "용역"]) & modular_title)
        )
        filtered = filtered[~g2b_source | g2b_scope]
        if include_outside_important and known_bid_nos:
            important_rows = before_operating_filter[before_operating_filter["source_record_id"].isin(known_bid_nos)]
            filtered = pd.concat([filtered, important_rows]).drop_duplicates(subset=["id"])
    if g2b_modular_goods_only:
        normalized_title = filtered["title"].fillna("").str.lower().str.replace(" ", "", regex=False)
        filtered = filtered[
            filtered["source_name"].eq("나라장터")
            & filtered["business_type"].eq("물품")
            & normalized_title.str.contains("모듈러", regex=False)
        ]
        if include_outside_important and known_bid_nos:
            important_rows = before_operating_filter[before_operating_filter["source_record_id"].isin(known_bid_nos)]
            filtered = pd.concat([filtered, important_rows]).drop_duplicates(subset=["id"])
    elif title_modular_only:
        normalized_title = filtered["title"].fillna("").str.lower().str.replace(" ", "", regex=False)
        filtered = filtered[normalized_title.str.contains("모듈러", regex=False)]
    if service_candidate_only:
        filtered = filtered[filtered["business_type"].eq("용역")]
    if not include_cancelled:
        filtered = filtered[~filtered["notice_status"].fillna("").str.contains("취소", case=False, regex=False)]
    if not include_correction:
        status = filtered["notice_status"].fillna("")
        filtered = filtered[
            ~status.str.contains("정정", case=False, regex=False)
            & ~status.str.contains("변경", case=False, regex=False)
        ]
    if keyword:
        filtered = filtered[filtered["keywords"].fillna("").str.contains(keyword, case=False, regex=False)]
    if due_soon_only:
        filtered = filtered[filtered["is_due_soon"]]
    if news_only:
        filtered = filtered[filtered["is_news"]]
    if bid_only:
        filtered = filtered[filtered["is_bid"]]
    if plan_only:
        filtered = filtered[filtered["is_plan"]]
    if important_only and known_bid_nos:
        filtered = filtered[filtered["source_record_id"].isin(known_bid_nos)]

    filtered = _filter_date_range(filtered, "posted_at", posted_range)
    filtered = _filter_date_range(filtered, "due_at", due_range)

    if search_text:
        haystack = (
            filtered["title"].fillna("")
            + " "
            + filtered["organization"].fillna("")
            + " "
            + filtered["keywords"].fillna("")
            + " "
            + filtered["summary"].fillna("")
            + " "
            + filtered["source_name"].fillna("")
            + " "
            + filtered["source_record_id"].fillna("")
            + " "
            + filtered["source_record_no"].fillna("")
            + " "
            + filtered["notice_status"].fillna("")
            + " "
            + filtered["business_type"].fillna("")
        )
        filtered = filtered[haystack.str.contains(search_text, case=False, na=False, regex=False)]

    if sort_order == "관련도 높은순":
        return filtered.sort_values(["relevance_score", "posted_at"], ascending=[False, False], na_position="last")
    if sort_order == "마감일 임박순":
        return filtered.sort_values(["due_at", "relevance_score"], ascending=[True, False], na_position="last")
    return filtered.sort_values(["posted_at", "relevance_score"], ascending=[False, False], na_position="last")


def get_priority_items(df: pd.DataFrame, limit: int = 12) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    recent_news_cutoff = pd.Timestamp(date.today() - timedelta(days=7))
    priority = df[
        df["is_due_soon"]
        | df["is_high_relevance"]
        | (df["is_plan"] & (df["source_name"].eq("D2B")) & (df["relevance_score"] >= 5))
        | (df["is_news"] & (df["posted_at"] >= recent_news_cutoff) & (df["relevance_score"] >= 5))
        | df["has_competitor_news"]
    ].copy()

    if priority.empty:
        return priority

    priority["priority_score"] = (
        priority["is_due_soon"].astype(int) * 20
        + priority["is_high_relevance"].astype(int) * 10
        + priority["has_competitor_news"].astype(int) * 8
        + priority["relevance_score"]
    )
    return priority.sort_values(["priority_score", "posted_at"], ascending=[False, False], na_position="last").head(limit)


def source_type_counts(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["source_type", "count"])
    return df.groupby("source_type_label").size().rename("count").reset_index().set_index("source_type_label")


def source_name_counts(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["source_name", "count"])
    return df.groupby("source_name").size().rename("count").sort_values(ascending=False).head(12).reset_index().set_index("source_name")


def posted_trend(df: pd.DataFrame, days: int = 14) -> pd.DataFrame:
    if df.empty or "posted_at" not in df.columns:
        return pd.DataFrame(columns=["date", "count"])
    cutoff = pd.Timestamp(date.today() - timedelta(days=days - 1))
    trend_df = df[df["posted_at"].notna() & (df["posted_at"] >= cutoff)].copy()
    if trend_df.empty:
        return pd.DataFrame(columns=["count"])
    trend_df["date"] = trend_df["posted_at"].dt.date
    return trend_df.groupby("date").size().rename("count").reset_index().set_index("date")


def relevance_buckets(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["count"])
    bins = [-0.1, 0, 4, 7.99, 100]
    labels = ["0", "1-4", "5-7", "8+"]
    bucket = pd.cut(df["relevance_score"], bins=bins, labels=labels)
    return bucket.value_counts(sort=False).rename("count").reset_index().rename(columns={"relevance_score": "bucket"}).set_index("bucket")


def collect_status_summary(logs_df: pd.DataFrame) -> dict[str, Any]:
    if logs_df.empty:
        return {
            "last_time": "-",
            "recent_success": "-",
            "recent_failure": "-",
            "recent_error": "-",
            "collector_summary": pd.DataFrame(),
        }

    logs = logs_df.copy()
    logs["started_at"] = pd.to_datetime(logs["started_at"], errors="coerce")
    last_time = logs["started_at"].max()
    success = logs[logs["status"].eq("success")]
    failed = logs[logs["status"].eq("failed")]
    collector_summary = (
        logs.groupby("collector_name")[["inserted_count", "updated_count", "skipped_count"]]
        .sum()
        .sort_values("inserted_count", ascending=False)
    )
    return {
        "last_time": "-" if pd.isna(last_time) else str(last_time),
        "recent_success": success.iloc[0]["collector_name"] if not success.empty else "-",
        "recent_failure": failed.iloc[0]["collector_name"] if not failed.empty else "-",
        "recent_error": failed.iloc[0]["error_message"] if not failed.empty else "-",
        "collector_summary": collector_summary,
    }


def _filter_date_range(
    df: pd.DataFrame,
    column: str,
    value_range: tuple[date | None, date | None] | None,
) -> pd.DataFrame:
    if not value_range or column not in df.columns:
        return df
    start, end = value_range
    filtered = df
    if start:
        filtered = filtered[filtered[column].notna() & (filtered[column] >= pd.Timestamp(start))]
    if end:
        filtered = filtered[filtered[column].notna() & (filtered[column] <= pd.Timestamp(end))]
    return filtered


def _is_due_soon(df: pd.DataFrame) -> pd.Series:
    today = pd.Timestamp(date.today())
    return df["due_at"].notna() & (df["due_at"] >= today) & (df["due_at"] <= today + pd.Timedelta(days=7))


def _has_competitor_news(row: pd.Series) -> bool:
    if row.get("source_type") not in NEWS_TYPES:
        return False
    text = f"{row.get('title') or ''} {row.get('summary') or ''}"
    competitor_names = [keyword.replace(" 모듈러", "") for keyword in NAVER_NEWS_COMPETITOR_KEYWORDS]
    return any(name and name in text for name in competitor_names)
