from __future__ import annotations

import json
from datetime import date

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.api_contract import get_health, get_item_detail, get_source_detail_for_item, get_trends, safe_text
from src.config import DB_PATH
from src.database import add_favorite, add_favorites, load_favorite_item_ids, load_source_detail, remove_favorite
from src.dashboard_data import (
    BID_TYPES,
    HIGH_RELEVANCE_THRESHOLD,
    NEWS_TYPES,
    PLAN_TYPES,
    calculate_kpis,
    collect_status_summary,
    filter_items,
    get_priority_items,
    load_collect_logs,
    load_items,
    posted_trend,
    prepare_dashboard_dataframe,
    relevance_buckets,
    source_name_counts,
    source_type_counts,
)


KNOWN_BIDS_PATH = DB_PATH.parent.parent / "config" / "known_important_bids.json"


st.set_page_config(
    page_title="한국 모듈러 정보 대시보드",
    layout="wide",
    initial_sidebar_state="expanded",
)

TABLE_COLUMNS = [
    "title",
    "source_type_label",
    "source_name",
    "organization",
    "posted_at",
    "due_at",
    "amount",
    "region",
    "keywords",
    "relevance_score",
    "source_record_id",
    "source_record_no",
    "notice_status",
    "business_type",
    "business_subtype",
    "display_operating_scope",
    "display_known_important",
    "display_action_type",
    "display_link_status",
]

APP_SECTIONS = [
    {"id": "bid", "label": "입찰공고", "source_type": "bid", "description": "나라장터, LH, D2B 입찰·공고"},
    {"id": "news", "label": "모듈러 뉴스", "source_type": "news", "description": "시장동향, 공공정책, 경쟁사 뉴스"},
    {"id": "rnd-announce", "label": "R&D 공고", "source_type": "rnd", "description": "정부 R&D 및 연구과제 공고"},
    {"id": "rnd-outcome", "label": "R&D 성과", "source_type": "rnd", "description": "성과·보고서·기술자료"},
    {"id": "patent", "label": "특허", "source_type": "patent", "description": "모듈러·OSC 관련 특허"},
    {"id": "trend", "label": "트렌드", "source_type": "trend", "description": "수집 데이터 기반 시장 흐름"},
    {"id": "blog", "label": "블로그", "source_type": "blog", "description": "해설 콘텐츠 placeholder"},
    {"id": "community", "label": "커뮤니티", "source_type": "community", "description": "업계 소통 공간 placeholder"},
    {"id": "favorites", "label": "즐겨찾기", "source_type": "favorites", "description": "관심 항목 저장 placeholder"},
]
SECTION_BY_ID = {section["id"]: section for section in APP_SECTIONS}


def sync_hash_route() -> None:
    components.html(
        r"""
        <script>
        const loc = window.parent.location;
        const path = loc.pathname.replace(/\/+$/, "");
        const hash = loc.hash ? loc.hash.slice(1) : "";
        const params = new URLSearchParams(loc.search);
        let changed = false;
        if (path.endsWith("/app") && params.get("page") !== "app") {
          params.set("page", "app");
          changed = true;
        }
        if (hash && !params.get("section")) {
          params.set("section", hash);
          changed = true;
        }
        if (changed) {
          const next = "/?" + params.toString() + (hash ? "#" + hash : "");
          loc.replace(next);
        }
        </script>
        """,
        height=0,
    )


def _query_value(name: str, default: str = "") -> str:
    value = st.query_params.get(name, default)
    if isinstance(value, list):
        return str(value[0]) if value else default
    return str(value or default)


def get_route() -> tuple[str, str]:
    page = _query_value("page", "landing")
    section = _query_value("section", "bid")
    if section not in SECTION_BY_ID:
        section = "bid"
    return page, section


def set_app_section(section_id: str) -> None:
    st.query_params["page"] = "app"
    st.query_params["section"] = section_id


def render_landing_page() -> None:
    st.markdown(
        """
        <style>
        .mh-hero {padding: 58px 0 34px 0; border-bottom: 1px solid #e5e7eb;}
        .mh-label {font-size: 14px; color: #52525b; margin-bottom: 10px;}
        .mh-title {font-size: 48px; line-height: 1.12; font-weight: 760; letter-spacing: 0; margin: 0 0 16px 0;}
        .mh-copy {font-size: 18px; color: #52525b; max-width: 760px;}
        .mh-card {border: 1px solid #e5e7eb; border-radius: 8px; padding: 18px; min-height: 112px; background: #fff;}
        .mh-card-title {font-weight: 700; margin-bottom: 8px;}
        .mh-card-desc {font-size: 14px; color: #71717a;}
        </style>
        <div class="mh-hero">
          <div class="mh-label">모듈러건축 전문 정보 플랫폼</div>
          <div class="mh-title">ModularHub</div>
          <div class="mh-copy">입찰·뉴스·R&D·특허를 한 곳에서. 나라장터 입찰공고부터 모듈러 뉴스, R&D 공고, 특허까지 통합 검색합니다.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    cta_cols = st.columns([1, 1, 4])
    with cta_cols[0]:
        st.link_button("앱 열기", "?page=app&section=bid#bid", type="primary", use_container_width=True)
    with cta_cols[1]:
        st.button("Google 로그인", disabled=True, use_container_width=True)
    st.caption("Google 로그인은 향후 인증 단계에서 연결됩니다.")

    st.subheader("카테고리")
    cards = [
        ("입찰공고", "G2B·LH·D2B 공고와 조달계획", "bid"),
        ("모듈러 뉴스", "시장·정책·경쟁사 동향", "news"),
        ("R&D 공고", "정부 연구과제와 지원사업", "rnd-announce"),
        ("R&D 성과", "성과·보고서·기술자료", "rnd-outcome"),
        ("특허", "KIPRIS 기반 특허 정보", "patent"),
        ("트렌드", "수집 데이터 기반 흐름", "trend"),
        ("커뮤니티", "업계 소통 공간 예정", "community"),
        ("즐겨찾기", "관심 항목 저장 예정", "favorites"),
    ]
    for row_start in range(0, len(cards), 4):
        cols = st.columns(4)
        for col, (title, desc, section_id) in zip(cols, cards[row_start : row_start + 4]):
            with col:
                st.markdown(
                    f"""
                    <a href="?page=app&section={section_id}#{section_id}" style="text-decoration:none;color:inherit;">
                      <div class="mh-card">
                        <div class="mh-card-title">{title}</div>
                        <div class="mh-card-desc">{desc}</div>
                      </div>
                    </a>
                    """,
                    unsafe_allow_html=True,
                )


def render_top_header(active_section: str) -> None:
    health = get_health()
    home_col, brand_col, status_col = st.columns([0.8, 4.2, 2.4])
    with home_col:
        st.link_button("홈", "?page=landing", use_container_width=True)
    with brand_col:
        st.markdown("### ModularHub")
        st.caption("입찰공고 · 뉴스 · R&D · 특허 · 블로그 · 커뮤니티")
    with status_col:
        st.caption("서버 연결 상태")
        st.success(f"서버 {health['server']} · DB {health['database']}")
        st.caption(
            "연결 소스: "
            f"G2B {health['g2b']} · DAPA {health['dapa']} · "
            f"Naver {health['naver']} · KIPRIS {health['kipris']} · KCI {health['kci']}"
        )
        st.caption(f"마지막 수집: {health.get('last_collected_at') or '-'}")
        st.caption("사용자: 로그인 전")


def render_section_nav(active_section: str) -> str:
    labels = [section["label"] for section in APP_SECTIONS]
    ids = [section["id"] for section in APP_SECTIONS]
    current_index = ids.index(active_section) if active_section in ids else 0
    selected_label = st.radio("섹션", labels, index=current_index, horizontal=True, label_visibility="collapsed")
    selected_id = ids[labels.index(selected_label)]
    if selected_id != active_section:
        set_app_section(selected_id)
        st.rerun()
    st.markdown(
        " ".join(
            f'<a href="?page=app&section={section["id"]}#{section["id"]}" style="margin-right:14px;">#{section["id"]}</a>'
            for section in APP_SECTIONS
        ),
        unsafe_allow_html=True,
    )
    return selected_id


def section_dataframe(df: pd.DataFrame, section_id: str) -> pd.DataFrame:
    if df.empty:
        return df
    if section_id == "bid":
        return df[df["source_type"].isin(BID_TYPES)]
    if section_id == "news":
        return df[df["source_type"].isin(NEWS_TYPES)]
    if section_id == "rnd-announce":
        return df[df["source_type"].eq("rnd") & df["summary"].fillna("").str.contains("공고|지원|사업", regex=True)]
    if section_id == "rnd-outcome":
        return df[df["source_type"].eq("rnd") & ~df["summary"].fillna("").str.contains("공고|지원|사업", regex=True)]
    if section_id == "patent":
        return df[df["source_type"].eq("patent")]
    if section_id == "favorites":
        return df.iloc[0:0].copy()
    return df.iloc[0:0].copy()


def section_source_filter(section_id: str, df: pd.DataFrame) -> tuple[list[str] | None, list[str] | None]:
    source_types = set(df["source_type"].dropna().astype(str)) if "source_type" in df.columns else set()
    source_names = set(df["source_name"].dropna().astype(str)) if "source_name" in df.columns else set()
    if section_id == "bid":
        return [value for value in ["bid", "입찰/조달"] if value in source_types], [
            value for value in ["나라장터", "G2B", "조달청", "LH", "D2B"] if value in source_names
        ]
    if section_id == "news":
        return [value for value in ["news", "뉴스"] if value in source_types], [
            value for value in ["네이버뉴스", "NaverNews", "NAVER"] if value in source_names
        ]
    if section_id == "rnd-announce":
        return [value for value in ["rnd_announce", "rnd"] if value in source_types], None
    if section_id == "rnd-outcome":
        return [value for value in ["rnd_report", "rnd_outcome", "rnd"] if value in source_types], None
    if section_id == "patent":
        return [value for value in ["patent"] if value in source_types], None
    return None, None


def render_placeholder_section(section_id: str) -> None:
    section = SECTION_BY_ID[section_id]
    st.info(f"{section['label']} 섹션은 정보 구조 placeholder입니다. 실제 CRUD와 추가 수집기는 다음 단계에서 연결합니다.")


def show_db_missing_message() -> None:
    st.title("한국 모듈러 정보 데일리 브리핑")
    st.warning("SQLite DB 파일을 찾을 수 없습니다.")
    st.write("아래 명령어를 프로젝트 루트에서 실행한 뒤 Streamlit을 다시 시작하세요.")
    st.code("python db/init_db.py\npython scripts/load_sample_data.py", language="powershell")
    st.caption(f"예상 DB 경로: {DB_PATH}")


def format_amount(value: object) -> str:
    if pd.isna(value) or value in ("", None):
        return "-"
    amount = int(value)
    if amount == 0:
        return "-"
    if amount >= 100_000_000:
        return f"{amount / 100_000_000:.1f}억 원"
    return f"{amount:,}원"


def render_section_filter_controls(active_section: str) -> None:
    st.sidebar.markdown("### 섹션 필터")
    keyword_sets = {
        "bid": ["모듈러", "모듈러 학교", "모듈러 교실", "모듈러 기숙사", "모듈러 주택"],
        "news": ["모듈러 건축", "OSC 건설", "공업화주택", "학교 모듈러", "국방부 병영생활관"],
        "rnd-announce": ["모듈러", "OSC", "스마트건설", "프리패브"],
        "rnd-outcome": ["모듈러", "OSC", "DfMA", "프리패브"],
        "patent": ["모듈러", "조립식", "프리패브", "스틸 모듈러"],
    }
    for keyword in keyword_sets.get(active_section, ["모듈러", "OSC", "스마트건설"]):
        if st.sidebar.button(keyword, key=f"quick_keyword_{active_section}_{keyword}", use_container_width=True):
            st.session_state["sidebar_search_text"] = keyword
    if active_section == "bid":
        st.sidebar.checkbox("마감 전 공고만 보기", value=False, key="bid_open_only")
        st.sidebar.checkbox("전체 페이지 수집 옵션", value=False, key="bid_all_pages_collect_option")
        st.sidebar.button("검색 시작", key="bid_search_start", use_container_width=True)
        with st.sidebar.expander("시스템 로그", expanded=False):
            st.caption("수집 로그는 앱 하단의 최근 수집 로그에서도 확인할 수 있습니다.")
            st.code("scripts\\collect_g2b_modular_scope.py")
    elif active_section == "news":
        st.sidebar.text_input("포함 단어", key="news_include_words")
        st.sidebar.text_input("제외 단어", key="news_exclude_words")
        st.sidebar.button("뉴스 검색", key="news_search_start", use_container_width=True)
    elif active_section == "patent":
        st.sidebar.text_input("IPC 코드", key="patent_ipc_filter")
        st.sidebar.selectbox("정렬", ["최신순", "관련도순"], key="patent_sort_order")
        st.sidebar.button("특허 검색", key="patent_search_start", use_container_width=True)
    elif active_section in {"rnd-announce", "rnd-outcome"}:
        st.sidebar.button("R&D 공고 검색" if active_section == "rnd-announce" else "R&D 성과 검색", key=f"{active_section}_search_start", use_container_width=True)


def build_sidebar_filters(df: pd.DataFrame, active_section: str = "bid") -> dict:
    st.sidebar.header("필터")
    render_section_filter_controls(active_section)
    search_text = st.sidebar.text_input(
        "검색어",
        placeholder="제목, 기관, 키워드, 요약",
        key="sidebar_search_text",
    )

    source_types = sorted(df["source_type"].dropna().unique())
    selected_source_types = st.sidebar.multiselect("source_type", source_types, default=source_types)

    source_names = sorted(df["source_name"].dropna().unique())
    selected_source_names = st.sidebar.multiselect("source_name", source_names, default=source_names)
    advanced_source_filter = st.sidebar.checkbox("고급 source_type/source_name 필터 직접 적용", value=False)

    posted_min = df["posted_at"].dropna().min()
    posted_max = df["posted_at"].dropna().max()
    default_posted = (
        posted_min.date() if not pd.isna(posted_min) else None,
        posted_max.date() if not pd.isna(posted_max) else None,
    )
    posted_range = st.sidebar.date_input("게시일/발주월 기간", value=default_posted)
    posted_range = _normalize_date_input(posted_range)

    due_range = st.sidebar.date_input("마감일 범위", value=())
    due_range = _normalize_date_input(due_range)

    min_relevance = st.sidebar.slider("최소 관련도", 0.0, 20.0, 0.0, 0.5)
    business_types = sorted(value for value in df["business_type"].dropna().unique() if str(value).strip())
    selected_business_types = st.sidebar.multiselect("업무구분", business_types, default=business_types)
    g2b_modular_scope_only = st.sidebar.checkbox("나라장터 모듈러 운영범위만 보기", value=True)
    service_candidate_only = st.sidebar.checkbox("일반용역 후보만 보기", value=False)
    g2b_modular_goods_only = st.sidebar.checkbox("나라장터 모듈러 물품만 보기", value=False)
    title_modular_only = st.sidebar.checkbox("공고명 모듈러 포함", value=False)
    include_cancelled = st.sidebar.checkbox("취소공고 포함", value=True)
    include_correction = st.sidebar.checkbox("정정공고 포함", value=True)

    keyword_options = sorted(
        {
            keyword.strip()
            for keywords in df["keywords"].dropna()
            for keyword in str(keywords).split(";")
            if keyword.strip()
        }
    )
    keyword = st.sidebar.selectbox("키워드 포함", [""] + keyword_options)

    st.sidebar.subheader("빠른 보기")
    due_soon_only = st.sidebar.checkbox("마감 7일 이내만 보기")
    news_only = st.sidebar.checkbox("뉴스만 보기")
    bid_only = st.sidebar.checkbox("입찰·공고만 보기")
    plan_only = st.sidebar.checkbox("조달계획만 보기")
    important_only = st.sidebar.checkbox("중요공고만 보기")
    include_outside_important = st.sidebar.checkbox("운영 필터 외 중요공고 포함", value=True)
    show_mock = st.sidebar.checkbox("개발용 mock 데이터 표시", value=False)
    show_selection_debug = st.sidebar.checkbox("선택 상태 디버그 보기", value=False)

    sort_order = st.sidebar.selectbox("정렬", ["게시일 최신순", "관련도 높은순", "마감일 임박순"])

    return {
        "search_text": search_text,
        "source_types": selected_source_types,
        "source_names": selected_source_names,
        "advanced_source_filter": advanced_source_filter,
        "posted_range": posted_range,
        "due_range": due_range,
        "min_relevance": min_relevance,
        "business_types": selected_business_types,
        "g2b_modular_goods_only": g2b_modular_goods_only,
        "g2b_modular_scope_only": g2b_modular_scope_only,
        "service_candidate_only": service_candidate_only,
        "title_modular_only": title_modular_only,
        "include_cancelled": include_cancelled,
        "include_correction": include_correction,
        "keyword": keyword,
        "due_soon_only": due_soon_only,
        "news_only": news_only,
        "bid_only": bid_only,
        "plan_only": plan_only,
        "important_only": important_only,
        "include_outside_important": include_outside_important,
        "show_mock": show_mock,
        "show_selection_debug": show_selection_debug,
        "sort_order": sort_order,
    }


def _normalize_date_input(value: object) -> tuple[date | None, date | None] | None:
    if value in (None, (), []):
        return None
    if isinstance(value, tuple):
        if len(value) == 0:
            return None
        if len(value) == 1:
            return value[0], value[0]
        return value[0], value[1]
    if isinstance(value, date):
        return value, value
    return None


def render_kpis(df: pd.DataFrame) -> None:
    kpis = calculate_kpis(df)
    cols = st.columns(7)
    cols[0].metric("전체 데이터", f"{kpis['total']:,}")
    cols[1].metric("최근 24시간 신규", f"{kpis['new_24h']:,}")
    cols[2].metric("입찰·공고", f"{kpis['bid']:,}")
    cols[3].metric("조달계획", f"{kpis['plan']:,}")
    cols[4].metric("뉴스", f"{kpis['news']:,}")
    cols[5].metric("마감 7일 이내", f"{kpis['due_soon']:,}")
    cols[6].metric("관련도 8+", f"{kpis['high_relevance']:,}")


def load_known_important_bids() -> list[dict]:
    if not KNOWN_BIDS_PATH.exists():
        return []
    try:
        return json.loads(KNOWN_BIDS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def render_known_bid_status(df: pd.DataFrame, known_bids: list[dict]) -> None:
    if not known_bids:
        return
    bid_nos = [bid.get("bid_no") for bid in known_bids if bid.get("bid_no")]
    existing = set(df[df["source_record_id"].isin(bid_nos)]["source_record_id"].dropna())
    missing = [bid_no for bid_no in bid_nos if bid_no not in existing]
    cols = st.columns(3)
    cols[0].metric("중요 공고 전체", len(bid_nos))
    cols[1].metric("DB 존재", len(existing))
    cols[2].metric("누락", len(missing))
    if missing:
        st.warning(
            "중요 공고 중 일부가 현재 DB에 없습니다. "
            "collect_known_g2b_bids.py를 실행하세요. "
            f"누락 공고번호: {', '.join(missing)}"
        )
    else:
        st.success("중요 공고 회귀 점검 대상이 현재 DB에 있습니다.")


def render_priority_section(df: pd.DataFrame) -> None:
    st.subheader("오늘의 우선 확인")
    priority_df = get_priority_items(df)
    if priority_df.empty:
        st.info("현재 필터 조건에서 우선 확인 항목이 없습니다.")
        return
    render_table(priority_df, key="priority_table", height=300, hide_low_signal_columns=True)


def render_charts(df: pd.DataFrame) -> None:
    st.subheader("요약 차트")
    col1, col2 = st.columns(2)
    with col1:
        st.caption("source_type별 건수")
        st.bar_chart(source_type_counts(df), use_container_width=True)
    with col2:
        st.caption("source_name별 건수")
        st.bar_chart(source_name_counts(df), use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        st.caption("최근 14일 게시일 기준 추이")
        st.line_chart(posted_trend(df), use_container_width=True)
    with col4:
        st.caption("관련도 구간별 건수")
        st.bar_chart(relevance_buckets(df), use_container_width=True)


def render_source_badge(text: str, tone: str = "default") -> str:
    text = safe_text(text)
    if not text:
        return ""
    colors = {
        "default": ("#f4f4f5", "#27272a"),
        "bid": ("#eef2ff", "#3730a3"),
        "news": ("#ecfeff", "#155e75"),
        "rnd": ("#f0fdf4", "#166534"),
        "patent": ("#fff7ed", "#9a3412"),
        "important": ("#fef2f2", "#991b1b"),
    }
    bg, fg = colors.get(tone, colors["default"])
    return f'<span style="display:inline-block;padding:3px 8px;border-radius:999px;background:{bg};color:{fg};font-size:12px;border:1px solid rgba(0,0,0,.06);">{text}</span>'


def render_status_badge(text: str) -> str:
    return render_source_badge(text or "-", "default")


def favorite_button(item_id: int, favorite_ids: set[int], key_prefix: str) -> None:
    is_favorite = item_id in favorite_ids
    label = "★ 즐겨찾기 해제" if is_favorite else "☆ 즐겨찾기"
    if st.button(label, key=f"{key_prefix}_favorite_{item_id}", use_container_width=True):
        if is_favorite:
            remove_favorite(item_id)
        else:
            add_favorite(item_id)
        st.rerun()


def render_action_buttons(row: pd.Series, variant: str, favorite_ids: set[int], key_prefix: str) -> None:
    item_id = int(row.get("id"))
    source_detail_exists = bool(get_source_detail_for_item(item_id))
    action_type = get_link_action_type(row, has_detail=source_detail_exists)
    cols = st.columns([1, 1, 1])
    with cols[0]:
        if st.button("상세보기", key=f"detail_{key_prefix}_{item_id}", use_container_width=True):
            st.session_state.selected_item_id = item_id
            st.session_state.selected_detail_source = key_prefix
            st.session_state.detail_panel_open = True
            st.session_state.last_selection_source = "card"
            st.rerun()
    with cols[1]:
        if action_type == "original_exact" and row.get("original_url"):
            st.link_button("원문 보기", row.get("original_url"), use_container_width=True)
        elif action_type == "api_detail":
            if st.button("API 상세 보기", key=f"api_detail_{key_prefix}_{item_id}", use_container_width=True):
                st.session_state.selected_item_id = item_id
                st.session_state.selected_detail_source = key_prefix
                st.session_state.detail_panel_open = True
                st.session_state.last_selection_source = "card_api"
                st.rerun()
        else:
            site_url = _manual_site_url(row)
            if site_url:
                st.link_button("확인 사이트 열기", site_url, use_container_width=True)
            else:
                st.button("원문 미확인", disabled=True, key=f"{key_prefix}_unavailable_{item_id}", use_container_width=True)
    with cols[2]:
        favorite_button(item_id, favorite_ids, key_prefix)


def _manual_site_url(row: pd.Series) -> str | None:
    source_name = row.get("source_name")
    if source_name == "나라장터":
        return "https://www.g2b.go.kr"
    if source_name == "LH":
        return "https://ebid.lh.or.kr"
    if source_name == "D2B":
        return "https://www.d2b.go.kr"
    return None


def render_result_card(row: pd.Series, *, variant: str, favorite_ids: set[int], key_prefix: str) -> None:
    source_name = safe_text(row.get("source_name"), "-")
    source_type = safe_text(row.get("source_type"))
    title = safe_text(row.get("title"), "-")
    summary = safe_text(row.get("summary"))
    badge_tone = {
        "bid": "bid",
        "news": "news",
        "rnd_announce": "rnd",
        "rnd_outcome": "rnd",
        "patent": "patent",
    }.get(variant, "default")
    important = int(row.get("is_known_important") or 0) == 1
    st.markdown(
        f"""
        <div style="border:1px solid #e5e7eb;border-radius:8px;padding:18px;background:#fff;margin-bottom:10px;">
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px;">
            {render_source_badge(source_name, badge_tone)}
            {render_status_badge(safe_text(row.get('business_type')) or source_type)}
            {render_source_badge('중요공고', 'important') if important else ''}
          </div>
          <div style="font-size:18px;font-weight:720;line-height:1.35;margin-bottom:8px;">{title}</div>
          <div style="font-size:13px;color:#52525b;margin-bottom:10px;">
            {card_metadata(row, variant)}
          </div>
          <div style="font-size:14px;color:#3f3f46;line-height:1.55;">{summary[:420] if summary else '-'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_action_buttons(row, variant, favorite_ids, key_prefix)
    st.divider()


def card_metadata(row: pd.Series, variant: str) -> str:
    def value(key: str) -> str:
        raw = row.get(key)
        if pd.isna(raw):
            return "-"
        text = str(raw).strip()
        return text if text and text.lower() != "nan" else "-"

    if variant == "bid":
        return " · ".join(
            part
            for part in [
                f"공고번호 {value('source_record_id')}",
                f"차수 {value('source_record_no')}",
                f"기관 {value('organization')}",
                f"수요기관 {value('demand_org')}",
                f"금액 {format_amount(row.get('amount'))}",
                f"공고일 {_display_date(row.get('posted_at'))}",
                f"마감일 {_display_date(row.get('due_at'))}",
                f"상태 {value('notice_status')}",
                f"관련도 {float(row.get('relevance_score') or 0):.1f}",
            ]
            if part
        )
    if variant == "news":
        return " · ".join(
            [
                f"매체 {value('organization') if value('organization') != '-' else value('source_name')}",
                f"게시일 {_display_date(row.get('posted_at'))}",
                f"관련도 {float(row.get('relevance_score') or 0):.1f}",
            ]
        )
    if variant == "patent":
        return " · ".join([f"출원인 {value('organization')}", f"공개/출원일 {_display_date(row.get('posted_at'))}"])
    if variant in {"rnd_announce", "rnd_outcome"}:
        return " · ".join([f"기관 {value('organization')}", f"게시/발행일 {_display_date(row.get('posted_at'))}"])
    return f"게시일 {_display_date(row.get('posted_at'))}"


def render_result_cards(df: pd.DataFrame, *, variant: str, favorite_ids: set[int], key_prefix: str) -> None:
    if df.empty:
        render_empty_state("조건에 맞는 결과가 없습니다.")
        return
    for row in df.head(50).itertuples(index=False):
        render_result_card(pd.Series(row._asdict()), variant=variant, favorite_ids=favorite_ids, key_prefix=key_prefix)
    if len(df) > 50:
        st.caption(f"상위 50건을 표시했습니다. 전체 {len(df):,}건은 CSV 또는 보조 테이블에서 확인하세요.")


def render_empty_state(message: str) -> None:
    st.info(message)


def render_loading_state(message: str = "데이터를 불러오는 중입니다.") -> None:
    st.caption(message)


def sync_favorites_to_local_storage(favorite_ids: set[int]) -> None:
    payload = json.dumps(
        [
            {"item_id": int(item_id), "saved_at": None}
            for item_id in sorted(favorite_ids)
        ],
        ensure_ascii=False,
    )
    components.html(
        f"""
        <script>
        try {{
          window.parent.localStorage.setItem("modularhub_favorites", {json.dumps(payload)});
        }} catch (err) {{}}
        </script>
        """,
        height=0,
    )


def render_bid_summary_cards(df: pd.DataFrame) -> None:
    g2b_count = int(df["source_name"].eq("나라장터").sum()) if not df.empty else 0
    lh_count = int(df["source_name"].eq("LH").sum()) if not df.empty else 0
    d2b_count = int(df["source_name"].eq("D2B").sum()) if not df.empty else 0
    total_amount = pd.to_numeric(df["amount"], errors="coerce").fillna(0).sum() if not df.empty else 0
    cols = st.columns(5)
    cols[0].metric("나라장터 G2B", f"{g2b_count:,}")
    cols[1].metric("LH 공사", f"{lh_count:,}")
    cols[2].metric("국방조달", f"{d2b_count:,}")
    cols[3].metric("전체 합계", f"{len(df):,}")
    cols[4].metric("총 금액", format_amount(total_amount))


def render_trend_section() -> None:
    trends = get_trends()
    cols = st.columns(4)
    cols[0].metric("전체 수집 건수", f"{trends['total_items']:,}")
    cols[1].metric("소스 수", f"{trends['source_count']:,}")
    cols[2].metric("매칭 키워드 수", f"{trends['keyword_count']:,}")
    cols[3].metric("최근 일자 수", f"{len(trends['daily_counts']):,}")
    chart_cols = st.columns(2)
    with chart_cols[0]:
        st.caption("키워드별 빈도")
        st.bar_chart(pd.DataFrame.from_dict(trends["keyword_frequency"], orient="index", columns=["count"]))
    with chart_cols[1]:
        st.caption("소스별 건수")
        st.bar_chart(pd.DataFrame.from_dict(trends["source_counts"], orient="index", columns=["count"]))
    st.caption("일자별 추이")
    st.line_chart(pd.DataFrame.from_dict(trends["daily_counts"], orient="index", columns=["count"]))


def section_variant(section_id: str) -> str:
    return {
        "bid": "bid",
        "news": "news",
        "rnd-announce": "rnd_announce",
        "rnd-outcome": "rnd_outcome",
        "patent": "patent",
    }.get(section_id, section_id)


def render_table(
    df: pd.DataFrame,
    *,
    key: str,
    height: int = 430,
    hide_low_signal_columns: bool = False,
    tab_key: str | None = None,
    tab_label: str | None = None,
) -> pd.Series | None:
    if df.empty:
        st.info("조건에 맞는 데이터가 없습니다.")
        return None

    tab_key = tab_key or key
    tab_label = tab_label or key
    table_df = df.copy().reset_index(drop=True)
    table_df["_item_id"] = table_df["id"].astype(int)
    columns = TABLE_COLUMNS.copy()
    if hide_low_signal_columns:
        columns = [
            "title",
            "source_type_label",
            "source_name",
            "organization",
            "posted_at",
            "due_at",
            "keywords",
            "relevance_score",
            "source_record_id",
            "source_record_no",
            "notice_status",
            "business_type",
            "business_subtype",
            "display_operating_scope",
            "display_known_important",
            "display_action_type",
            "display_link_status",
        ]
    table_df["display_original"] = table_df.apply(_display_original_value, axis=1)
    table_df["display_link_status"] = table_df.apply(_display_link_status, axis=1)
    table_df["display_link_method"] = table_df.apply(_display_link_method, axis=1)
    table_df["action_type"] = table_df.apply(get_link_action_type, axis=1)
    table_df["display_operating_scope"] = table_df["operating_scope"].fillna("").map(
        {"modular_goods_service": "모듈러 물품·용역"}
    ).fillna("")
    table_df["display_known_important"] = table_df["is_known_important"].apply(lambda value: "중요" if int(value or 0) else "")
    table_df["display_action_type"] = table_df["action_type"].map(
        {
            "original_exact": "원문 확인됨",
            "api_detail": "API 상세 있음",
            "manual_check": "수동 확인 필요",
            "unavailable": "링크 없음",
        }
    )
    display_columns = ["_item_id"] + columns
    display_df = table_df[display_columns].rename(
        columns={
            "_item_id": "_item_id",
            "title": "제목",
            "source_type_label": "유형",
            "source_name": "출처",
            "organization": "기관",
            "posted_at": "게시일",
            "due_at": "마감일",
            "amount": "금액",
            "region": "지역",
            "keywords": "키워드",
            "relevance_score": "관련도",
            "source_record_id": "공고/출처번호",
            "source_record_no": "공고차수",
            "notice_status": "공고상태",
            "business_type": "업무구분",
            "business_subtype": "세부구분",
            "display_operating_scope": "운영범위",
            "display_known_important": "중요공고",
            "display_action_type": "확인 방식",
            "display_link_status": "원문 상태",
        }
    )

    event = st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=height,
        on_select="rerun",
        selection_mode="single-row",
        key=key,
        column_config={
            "_item_id": None,
            "금액": st.column_config.NumberColumn("금액", format="₩%d"),
            "관련도": st.column_config.ProgressColumn("관련도", min_value=0, max_value=100, format="%.1f"),
            "게시일": st.column_config.DateColumn("게시일", format="YYYY-MM-DD"),
            "마감일": st.column_config.DateColumn("마감일", format="YYYY-MM-DD"),
        },
    )
    selected_rows = get_selected_rows_from_dataframe_event(event)
    selected_item_id = selected_item_id_from_display_df(display_df, selected_rows)
    if selected_item_id is None:
        return None
    selected_row_index = selected_rows[0]
    st.session_state.selected_item_id = selected_item_id
    st.session_state.selected_tab_key = tab_key
    st.session_state.last_selection_source = "table"
    st.session_state.last_selected_row_index = int(selected_row_index)
    st.session_state.last_selected_table_key = key
    return table_df.iloc[selected_row_index]


def render_selectable_items_table(df: pd.DataFrame, tab_key: str, tab_label: str) -> int | None:
    selected_row = render_table(df, key=f"items_table_{tab_key}", tab_key=tab_key, tab_label=tab_label)
    if selected_row is None:
        return None
    selected_item_id = selected_row.get("id")
    if pd.isna(selected_item_id):
        return None
    return int(selected_item_id)


def get_selected_rows_from_dataframe_event(event: object) -> list[int]:
    if event is None:
        return []
    selection = getattr(event, "selection", None)
    rows = getattr(selection, "rows", None)
    if rows is not None:
        return list(rows)
    if isinstance(event, dict):
        selection = event.get("selection") or {}
        rows = selection.get("rows") or []
        return list(rows)
    return []


def selected_item_id_from_display_df(display_df: pd.DataFrame, selected_rows: list[int]) -> int | None:
    if not selected_rows:
        return None
    selected_row_index = selected_rows[0]
    if selected_row_index < 0 or selected_row_index >= len(display_df):
        return None
    value = display_df.iloc[selected_row_index].get("_item_id")
    if pd.isna(value):
        return None
    return int(value)


def render_detail(df: pd.DataFrame, selected_row: pd.Series | None = None) -> None:
    st.subheader("상세 보기")
    selected_item_id = st.session_state.get("selected_item_id")
    if selected_item_id is not None:
        render_detail_panel(int(selected_item_id))
        return
    row = None
    if selected_item_id is not None and not df.empty and "id" in df.columns:
        matched = df[df["id"].astype("Int64") == int(selected_item_id)]
        if not matched.empty:
            row = matched.iloc[0]
    if row is None:
        row = selected_row
    if not df.empty:
        option_rows = df.head(200).copy().reset_index(drop=True)
        options = ["테이블 선택 항목"] + [
            f"{int(item_id)}. {title[:80]}"
            for item_id, title in zip(option_rows["id"], option_rows["title"].fillna(""))
        ]
        selected = st.selectbox("상세 확인할 항목", options)
        if selected != "테이블 선택 항목":
            selected_item_id = int(selected.split(".", 1)[0])
            st.session_state.selected_item_id = selected_item_id
            st.session_state.last_selection_source = "selectbox"
            st.session_state.selected_tab_key = "detail_selectbox"
            st.session_state.detail_panel_open = True
            matched = df[df["id"].astype("Int64") == selected_item_id]
            if not matched.empty:
                row = matched.iloc[0]

    if row is None:
        st.caption("테이블에서 행을 선택하거나 위 선택 상자에서 항목을 고르면 상세 정보가 표시됩니다.")
        return

    detail = load_source_detail(int(row.get("id"))) if row.get("id") else None
    action_type = get_link_action_type(row, has_detail=bool(detail))
    st.markdown(f"### {row.get('title') or '-'}")
    st.caption(f"확인 방식: {_display_action_label(action_type)}")

    summary_tab, api_tab, manual_tab, raw_tab = st.tabs(["요약", "API 상세", "수동 확인", "원본 Raw"])
    with summary_tab:
        render_summary_detail(row, action_type)
    with api_tab:
        if detail:
            render_api_detail(detail)
        elif _is_verified_api(row):
            st.link_button("API 상세 보기", row.get("source_detail_api_url"))
        else:
            st.info("저장된 API 상세 응답이 아직 없습니다.")
    with manual_tab:
        render_manual_check_guide(row)
    with raw_tab:
        st.caption("현재 대시보드 테이블에 적재된 정규화 레코드입니다.")
        st.json(_json_ready(row.to_dict()))
        if detail:
            with st.expander("저장된 API 상세 payload"):
                payload_text = detail.get("detail_payload_json")
                if payload_text:
                    try:
                        st.json(json.loads(payload_text))
                    except json.JSONDecodeError:
                        st.code(payload_text[:5000])


def render_detail_panel(item_id: int) -> None:
    try:
        detail_contract = get_item_detail(item_id)
    except KeyError:
        st.warning(f"선택한 항목을 찾을 수 없습니다. item_id={item_id}")
        return

    item = detail_contract["item"]
    row = pd.Series(item)
    source_detail = detail_contract.get("source_detail")
    action_type = "api_detail" if "api_detail" in detail_contract["available_actions"] else get_link_action_type(row, has_detail=bool(source_detail))
    st.markdown(f"### {safe_text(item.get('title'), '-')}")
    st.caption(f"item_id={item_id} · 상세 출처={st.session_state.get('selected_detail_source') or '-'}")

    summary_tab, api_tab, manual_tab, raw_tab = st.tabs(["요약", "API 상세", "수동 확인", "원본 Raw"])
    with summary_tab:
        render_summary_detail(row, action_type)
    with api_tab:
        if source_detail:
            render_api_detail(source_detail)
        elif item.get("source_detail_api_url"):
            st.info("상세 API URL 후보는 있지만 저장된 API 응답은 아직 없습니다. resolve_*_deep_links 또는 collect_known_g2b_bids.py를 실행하면 내부 상세가 채워집니다.")
        else:
            st.info("저장된 API 상세 응답이 아직 없습니다.")
    with manual_tab:
        render_manual_check_contract(detail_contract["manual_check"])
    with raw_tab:
        st.json(_json_ready(item))
        if source_detail:
            with st.expander("저장된 API 상세 payload"):
                payload = detail_contract.get("detail_payload_json")
                if isinstance(payload, (dict, list)):
                    st.json(payload)
                elif payload:
                    st.code(str(payload)[:5000])


def render_manual_check_contract(manual_check: dict) -> None:
    st.markdown(f"#### {manual_check.get('site_name') or '확인 사이트'} 수동 확인")
    st.info(manual_check.get("guide_text") or "공식 사이트에서 아래 값을 검색해 확인하세요.")
    site_url = manual_check.get("site_url")
    if site_url:
        st.link_button("공식 사이트 열기", site_url)
    search_keys = manual_check.get("search_keys") or {}
    clean_parts = []
    for label, value in search_keys.items():
        text = safe_text(value)
        if text:
            st.text_input(f"{label} 복사용", value=text, key=f"manual_copy_{label}_{text[:16]}")
            clean_parts.append(text)
    if clean_parts:
        st.caption("검색 조합 복사용")
        st.code(" ".join(clean_parts))


def render_summary_detail(row: pd.Series, action_type: str) -> None:
    col1, col2, col3 = st.columns(3)
    col1.write(f"**출처:** {row.get('source_name') or '-'}")
    col1.write(f"**유형:** {row.get('source_type_label') or row.get('source_type') or '-'}")
    col2.write(f"**기관:** {row.get('organization') or '-'}")
    col2.write(f"**지역:** {row.get('region') or '-'}")
    col3.write(f"**게시일:** {_display_date(row.get('posted_at'))}")
    col3.write(f"**마감일:** {_display_date(row.get('due_at'))}")
    st.write(f"**금액:** {format_amount(row.get('amount'))}")
    st.write(f"**관련도:** {row.get('relevance_score') or 0:.1f}")
    st.write(f"**공고/출처번호:** {row.get('source_record_id') or '-'}")
    st.write(f"**공고차수/보조번호:** {row.get('source_record_no') or '-'}")
    if row.get("business_type") or row.get("notice_status"):
        st.write(f"**업무구분:** {row.get('business_type') or '-'}")
        st.write(f"**공고상태:** {row.get('notice_status') or '-'}")
    st.write(f"**키워드:** {row.get('keywords') or '-'}")
    st.write(f"**요약:** {row.get('summary') or '-'}")
    link_status = row.get("link_status") or "unknown"
    st.write(f"**원문 상태:** {_display_link_status(row)}")
    st.write(f"**원문 확인 방식:** {_display_link_method(row)}")
    if link_status == "broken":
        st.warning("링크 확인 필요")
    elif action_type == "original_exact":
        st.link_button("원문 열기", row.get("original_url"))
    elif action_type == "api_detail":
        st.info("상단의 `API 상세` 탭에서 공공데이터 OpenAPI 응답을 확인할 수 있습니다.")
    elif action_type == "manual_check":
        st.info("상단의 `수동 확인` 탭에서 확인 사이트와 복사용 공고번호/판단번호를 확인하세요.")
    else:
        st.info(
            "이 항목은 API에서 공고 메타데이터는 수집되었지만, 브라우저에서 바로 열리는 정확한 상세 원문 URL은 아직 검증되지 않았습니다. "
            "공고번호와 기관명을 기준으로 해당 조달 포털에서 확인해 주세요."
        )


def render_api_detail(detail: dict | None) -> None:
    st.success("API 상세 보기")
    if not detail:
        st.caption("저장된 API 상세 응답이 아직 없습니다.")
        return
    st.write(f"**상세 API 확인 시간:** {detail.get('fetched_at') or '-'}")
    st.write(f"**상태:** {detail.get('status') or '-'}")
    if detail.get("error_message"):
        st.warning(f"API 상세 오류: {detail.get('error_message')}")

    payload_text = detail.get("detail_payload_json")
    if not payload_text:
        st.caption("저장된 상세 payload가 없습니다.")
        return
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        st.code(payload_text[:5000])
        return

    flat = _flatten_detail(payload)
    summary_keys = [
        "bidNtceNo",
        "bidNtceOrd",
        "bidNtceNm",
        "ntceInsttNm",
        "dminsttNm",
        "cntrctCnclsMthdNm",
        "bidMethdNm",
        "bidNtceDt",
        "bidClseDt",
        "presmptPrce",
        "bssamt",
        "prtcptPsblRgnNm",
        "bidNum",
        "bidnmKor",
        "organization",
        "zoneHqCd",
        "posted_at",
        "tndrdocAcptEndDtm",
        "amount",
        "summary",
        "source_record_id",
        "source_record_no",
        "dcs_no",
        "notice_no",
        "bid_name",
        "representative_item_name",
        "order_month",
        "ordering_organization",
        "budget_amount",
        "contract_method",
        "bid_method",
        "business_type",
        "registration_deadline",
        "bid_submission_deadline",
        "opening_datetime",
        "progress_status",
        "판단번호",
        "공고번호",
        "발주예정월",
        "대표품목명",
        "발주기관",
        "예산금액",
        "계약방법",
        "입찰방법",
        "진행상태",
        "입찰명",
        "업무구분",
        "등록마감",
        "입찰서제출마감",
        "개찰일시",
    ]
    summary = {key: flat[key] for key in summary_keys if flat.get(key)}
    if summary:
        st.dataframe(pd.DataFrame([summary]), use_container_width=True, hide_index=True)
    with st.expander("원본 상세 API 응답"):
        st.json(payload)


def render_lh_manual_check_guide(row: pd.Series) -> None:
    st.markdown("#### 수동 확인 가이드")
    st.info("LH 전자조달 사이트에서 공고번호 또는 공고명으로 조회해 확인하세요.")
    guide_cols = st.columns(2)
    guide_cols[0].write("**사이트명:** LH 전자조달")
    guide_cols[0].write(f"**공고번호:** {row.get('source_record_id') or '-'}")
    guide_cols[0].write(f"**담당지역:** {row.get('region') or '-'}")
    guide_cols[1].write(f"**공고명:** {row.get('title') or '-'}")
    guide_cols[1].write(f"**게시일:** {_display_date(row.get('posted_at'))}")
    guide_cols[1].write(f"**마감일:** {_display_date(row.get('due_at'))}")

    item_id = row.get("id") or "selected"
    copy_cols = st.columns(2)
    copy_cols[0].text_input(
        "공고번호 복사",
        value=str(row.get("source_record_id") or ""),
        key=f"lh_bid_number_copy_{item_id}",
    )
    copy_cols[1].text_input(
        "공고명 복사",
        value=str(row.get("title") or ""),
        key=f"lh_title_copy_{item_id}",
    )
    st.link_button("확인 사이트 열기", "https://ebid.lh.or.kr")


def render_manual_check_guide(row: pd.Series) -> None:
    source_name = row.get("source_name")
    if source_name == "나라장터":
        render_g2b_manual_check_guide(row)
    elif source_name == "LH":
        render_lh_manual_check_guide(row)
    elif source_name == "D2B":
        render_d2b_manual_check_guide(row)
    elif _is_verified_exact(row):
        st.link_button("원문 열기", row.get("original_url"))
    else:
        st.info("이 항목은 별도 수동 확인 가이드가 없습니다.")


def render_g2b_manual_check_guide(row: pd.Series) -> None:
    st.markdown("#### 나라장터 수동 확인 가이드")
    st.info("나라장터에서 공고번호 또는 공고명으로 검색해 확인하세요.")
    guide_cols = st.columns(2)
    guide_cols[0].write("**확인 사이트:** 나라장터")
    guide_cols[0].write(f"**공고번호:** {row.get('source_record_id') or '-'}")
    guide_cols[0].write(f"**공고차수:** {row.get('source_record_no') or '-'}")
    guide_cols[1].write(f"**공고명:** {row.get('title') or '-'}")
    guide_cols[1].write(f"**공고기관:** {row.get('organization') or '-'}")

    item_id = row.get("id") or "selected"
    copy_cols = st.columns(2)
    copy_cols[0].text_input(
        "공고번호 복사",
        value=str(row.get("source_record_id") or ""),
        key=f"g2b_record_copy_{item_id}",
    )
    copy_cols[1].text_input(
        "공고명 복사",
        value=str(row.get("title") or ""),
        key=f"g2b_title_copy_{item_id}",
    )
    st.link_button("확인 사이트 열기", "https://www.g2b.go.kr")


def render_d2b_manual_check_guide(row: pd.Series) -> None:
    source_type = row.get("source_type")
    is_plan = source_type == "procurement_plan"
    item_label = "D2B 조달계획" if is_plan else "D2B 입찰공고"
    record_label = "판단번호" if is_plan else "공고번호"
    title_label = "대표품목명" if is_plan else "입찰명"
    date_label = "발주예정월" if is_plan else "공고일자"

    st.markdown(f"#### {item_label} 수동 확인 가이드")
    st.info("D2B 국방전자조달 사이트에서 판단번호, 공고번호 또는 제목으로 조회해 확인하세요.")
    guide_cols = st.columns(2)
    guide_cols[0].write("**사이트명:** D2B 국방전자조달")
    guide_cols[0].write(f"**{record_label}:** {row.get('source_record_id') or '-'}")
    guide_cols[0].write(f"**발주기관:** {row.get('organization') or '-'}")
    guide_cols[1].write(f"**{title_label}:** {row.get('title') or '-'}")
    guide_cols[1].write(f"**{date_label}:** {_display_date(row.get('posted_at'))}")
    if not is_plan:
        guide_cols[1].write(f"**마감일:** {_display_date(row.get('due_at'))}")

    item_id = row.get("id") or "selected"
    copy_cols = st.columns(2)
    copy_cols[0].text_input(
        f"{record_label} 복사",
        value=str(row.get("source_record_id") or ""),
        key=f"d2b_record_copy_{item_id}",
    )
    copy_cols[1].text_input(
        "제목 복사",
        value=str(row.get("title") or ""),
        key=f"d2b_title_copy_{item_id}",
    )
    st.link_button("확인 사이트 열기", "https://www.d2b.go.kr")


def _flatten_detail(value: object, prefix: str = "") -> dict:
    flat = {}
    if isinstance(value, dict):
        for key, nested in value.items():
            flat.update(_flatten_detail(nested, key))
    elif isinstance(value, list):
        for idx, nested in enumerate(value):
            flat.update(_flatten_detail(nested, f"{prefix}_{idx}"))
    else:
        flat[prefix] = value
    return flat


def render_collect_status(logs_df: pd.DataFrame) -> None:
    st.subheader("최근 수집 상태")
    status = collect_status_summary(logs_df)
    col1, col2, col3 = st.columns(3)
    col1.metric("마지막 수집 시간", status["last_time"])
    col2.metric("최근 성공 collector", status["recent_success"])
    col3.metric("최근 실패 collector", status["recent_failure"])
    if status["recent_error"] != "-":
        st.warning(f"최근 실패 메시지: {status['recent_error']}")
    if not status["collector_summary"].empty:
        st.dataframe(status["collector_summary"], use_container_width=True)


def render_logs_tab(logs_df: pd.DataFrame) -> None:
    render_collect_status(logs_df)
    st.subheader("수집 로그 최근 50건")
    if logs_df.empty:
        st.caption("아직 수집 로그가 없습니다.")
        return
    st.dataframe(logs_df, use_container_width=True, hide_index=True, height=420)


def render_download(df: pd.DataFrame) -> None:
    export_df = df.copy()
    for column in ("posted_at", "due_at", "created_at", "updated_at"):
        if column in export_df.columns:
            export_df[column] = export_df[column].dt.strftime("%Y-%m-%d")
    csv = export_df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "필터 적용 결과 CSV 다운로드",
        data=csv,
        file_name=f"modular_dashboard_filtered_{date.today():%Y%m%d}.csv",
        mime="text/csv",
    )


def _display_date(value: object) -> str:
    if pd.isna(value):
        return "-"
    if hasattr(value, "date"):
        return str(value.date())
    return str(value)


def get_link_action_type(row: pd.Series, has_detail: bool = False) -> str:
    if _is_verified_exact(row):
        return "original_exact"
    if has_detail or int(row.get("api_detail_verified") or 0) == 1 or _is_verified_api(row):
        return "api_detail"
    if row.get("source_name") in {"나라장터", "LH", "D2B"}:
        return "manual_check"
    return "unavailable"


def _display_action_label(action_type: str) -> str:
    return {
        "original_exact": "원문 확인됨",
        "api_detail": "API 상세 있음",
        "manual_check": "수동 확인 필요",
        "unavailable": "링크 없음",
    }.get(action_type, "링크 없음")


def _json_ready(value: object) -> object:
    if isinstance(value, dict):
        return {key: _json_ready(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        missing = False
    if isinstance(missing, bool) and missing:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _display_original_value(row: pd.Series) -> str:
    if row.get("link_status") == "broken" and row.get("original_url"):
        return "링크 오류"
    if _is_verified_exact(row):
        return "원문 열기"
    if int(row.get("api_detail_verified") or 0) == 1:
        return "API 상세 보기"
    if _is_verified_api(row):
        return "상세 API 보기"
    return "정확 원문 링크 미확인"


def _display_link_status(row: pd.Series) -> str:
    status = row.get("link_status") or "unknown"
    if status == "ok":
        return "확인됨"
    if status == "broken":
        return "링크 오류"
    if _is_verified_exact(row) or _is_verified_api(row) or int(row.get("api_detail_verified") or 0) == 1:
        return "확인됨"
    if row.get("link_type") in {"exact", "exact_api"} and row.get("original_url"):
        return "미점검"
    return "미확인"


def _display_link_method(row: pd.Series) -> str:
    link_type = row.get("link_type") or "unknown"
    if link_type == "exact":
        return "정확 상세 URL"
    if link_type == "exact_api":
        return "API 원문"
    if int(row.get("api_detail_verified") or 0) == 1:
        return "OpenAPI 상세 응답"
    return "공고번호 기반 수동 확인 필요"


def _is_verified_exact(row: pd.Series) -> bool:
    return (
        row.get("link_type") == "exact"
        and bool(row.get("original_url"))
        and int(row.get("exact_url_verified") or 0) == 1
        and row.get("link_status") in {"ok", "unchecked"}
    )


def _is_verified_api(row: pd.Series) -> bool:
    return (
        row.get("link_type") == "exact_api"
        and bool(row.get("source_detail_api_url"))
        and int(row.get("api_detail_verified") or 0) == 1
        and row.get("link_status") in {"ok", "unchecked"}
    )


def render_selection_debug(tab_counts: dict[str, int]) -> None:
    with st.sidebar.expander("선택 상태 디버그", expanded=True):
        selected_item_id = st.session_state.get("selected_item_id")
        st.write(f"selected_item_id: {st.session_state.get('selected_item_id')}")
        st.write(f"detail_panel_open: {st.session_state.get('detail_panel_open')}")
        st.write(f"selected_detail_source: {st.session_state.get('selected_detail_source')}")
        st.write(f"selected_tab_key: {st.session_state.get('selected_tab_key')}")
        st.write(f"last_selection_source: {st.session_state.get('last_selection_source')}")
        st.write(f"last_selected_row_index: {st.session_state.get('last_selected_row_index')}")
        st.write(f"last_selected_table_key: {st.session_state.get('last_selected_table_key')}")
        if selected_item_id is not None:
            try:
                detail = get_item_detail(int(selected_item_id))
                st.write(f"source_details exists: {bool(detail.get('source_detail'))}")
            except Exception as exc:
                st.write(f"source_details lookup error: {exc}")
        st.write("탭별 dataframe 건수")
        st.json(tab_counts)


def main() -> None:
    sync_hash_route()
    page, active_section = get_route()
    if page != "app":
        render_landing_page()
        return

    if not DB_PATH.exists():
        show_db_missing_message()
        return

    render_top_header(active_section)
    active_section = render_section_nav(active_section)
    section_meta = SECTION_BY_ID[active_section]
    st.markdown(f"## {section_meta['label']}")
    st.caption(section_meta["description"])
    if active_section == "bid":
        st.info("나라장터 운영 수집 기준: 공고명에 '모듈러'가 포함된 물품·용역 공고입니다. 용역 중 일반용역은 세부구분이 확인되는 경우 별도 표시합니다.")

    try:
        items_df = prepare_dashboard_dataframe(load_items())
        logs_df = load_collect_logs(limit=50)
    except Exception as exc:
        st.error("DB를 읽는 중 오류가 발생했습니다.")
        st.code("python db/init_db.py\npython scripts/load_sample_data.py", language="powershell")
        st.exception(exc)
        return

    if items_df.empty:
        st.warning("데이터가 없습니다. 먼저 샘플 데이터 또는 수집기를 실행하세요.")
        st.code("python scripts/load_sample_data.py\npython scripts/collect_all.py", language="powershell")
        return

    filters = build_sidebar_filters(items_df, active_section)
    show_mock = filters.pop("show_mock")
    show_selection_debug = filters.pop("show_selection_debug")
    advanced_source_filter = filters.pop("advanced_source_filter")
    if not show_mock:
        items_df = items_df[
            (items_df["is_mock"] != 1)
            & (~items_df["data_quality"].isin(["mock", "sample", "test"]))
        ]
    known_bids = load_known_important_bids()
    known_bid_nos = [bid.get("bid_no") for bid in known_bids if bid.get("bid_no")]
    filters["known_bid_nos"] = known_bid_nos
    if not advanced_source_filter:
        auto_types, auto_names = section_source_filter(active_section, items_df)
        filters["source_types"] = auto_types
        filters["source_names"] = auto_names
    filtered_df = filter_items(items_df, **filters)
    favorite_ids = load_favorite_item_ids()
    sync_favorites_to_local_storage(favorite_ids)
    active_df = section_dataframe(filtered_df, active_section)
    if active_section == "favorites":
        active_df = filtered_df[filtered_df["id"].isin(favorite_ids)]
    if active_section == "bid" and st.session_state.get("bid_open_only"):
        active_df = active_df[active_df["due_at"].notna() & (active_df["due_at"] >= pd.Timestamp(date.today()))]
    if active_section == "news":
        include_words = str(st.session_state.get("news_include_words") or "").strip()
        exclude_words = str(st.session_state.get("news_exclude_words") or "").strip()
        news_text = active_df["title"].fillna("") + " " + active_df["summary"].fillna("")
        if include_words:
            active_df = active_df[news_text.str.contains(include_words, case=False, regex=False, na=False)]
        if exclude_words:
            active_df = active_df[~news_text.str.contains(exclude_words, case=False, regex=False, na=False)]
    if active_section == "patent":
        ipc = str(st.session_state.get("patent_ipc_filter") or "").strip()
        if ipc:
            patent_text = active_df["keywords"].fillna("") + " " + active_df["summary"].fillna("")
            active_df = active_df[patent_text.str.contains(ipc, case=False, regex=False, na=False)]

    render_kpis(active_df if active_section in {"bid", "news", "rnd-announce", "rnd-outcome", "patent"} else filtered_df)
    if active_section == "bid":
        render_known_bid_status(items_df, known_bids)
        render_bid_summary_cards(active_df)
        if st.button("현재 입찰공고 결과 전체 즐겨찾기 추가", use_container_width=True):
            added = add_favorites([int(item_id) for item_id in active_df["id"].dropna().tolist()])
            st.success(f"{added:,}건을 즐겨찾기에 추가했습니다.")
            st.rerun()
    st.divider()
    if active_section in {"trend", "blog", "community", "favorites"}:
        if active_section == "favorites":
            render_result_cards(active_df, variant="bid", favorite_ids=favorite_ids, key_prefix="favorites")
        else:
            render_placeholder_section(active_section)
        if active_section == "trend":
            render_trend_section()
            render_charts(filtered_df)
    elif active_df.empty and active_section in {"rnd-announce", "rnd-outcome", "patent"}:
        render_placeholder_section(active_section)
    else:
        if active_section == "bid":
            render_priority_section(active_df)
            st.divider()
        render_result_cards(active_df, variant=section_variant(active_section), favorite_ids=favorite_ids, key_prefix=active_section)
        render_download(active_df)
        with st.expander("보조 테이블 보기", expanded=False):
            render_selectable_items_table(active_df, active_section, section_meta["label"])

    with st.expander("최근 수집 로그", expanded=False):
        render_logs_tab(logs_df)

    st.divider()
    if show_selection_debug:
        tab_counts = {
            "active_section": len(active_df),
            "all_filtered": len(filtered_df),
            "bid": int(filtered_df["source_type"].isin(BID_TYPES).sum()),
            "plan": int(filtered_df["source_type"].isin(PLAN_TYPES).sum()),
            "news": int(filtered_df["source_type"].isin(NEWS_TYPES).sum()),
        }
        render_selection_debug(tab_counts)
    render_detail(active_df if not active_df.empty else filtered_df)


if __name__ == "__main__":
    main()
