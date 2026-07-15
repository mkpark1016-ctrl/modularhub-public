import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  Building2,
  ChevronDown,
  ExternalLink,
  Factory,
  FileText,
  Home,
  Newspaper,
  RotateCcw,
  Search,
} from "lucide-react";
import { Link, NavLink, Route, Routes, useParams, useSearchParams } from "react-router-dom";
import { matchesBusinessFilters } from "./businessFilters";
import {
  COMPANY_TYPE_LABELS,
  COMPETITIVE_ROLE_LABELS,
  TIER_LABELS,
  compareCompanies,
  companyMatchesFilters,
  formatCompanyDate,
  formatKrwReadable,
  getCompanyDataStatus,
  getCompanyDataStatusLabel,
  getCompanyHighlights,
  getCompanyItems,
  getCompanySummary,
  getCompanyTypeLabel,
  getCompetitiveRoleLabel,
  getConfidenceLabel,
  getCompanyProjectSummary,
  getLatestFinancial,
  getLatestVerifiedAt,
  getProjectRoleLabel,
  getProjectStatusLabel,
  getProductionModelLabel,
  getReviewStatusLabel,
  getStructureTypeLabel,
  getTierLabel,
  isDartIdentityConfirmed,
  metricSourceValue,
  optionCounts,
  productionFacilities,
  productionSummary,
  representativeProject,
  sourceHasUrl,
  statusOptions,
  technologyCount,
} from "./companyInsights";
import { COMPANY_SORT_VALUES, sanitizeCompanySearchParams } from "./companyUrlParams";
import {
  compareBusinessByPriority,
  compareBusinessBySort,
  dDayLabel,
  getBusinessPriority,
  getBusinessPriorityInfo,
  getBusinessPriorityReasons,
  getBusinessStatus,
  getBusinessSummary,
  isBusinessActionable,
  isDeadlineWithin,
  isImportantBusiness,
  isRecentlyPosted,
  parseDate,
} from "./businessInsights";
import {
  compareNewsBySort,
  getNewsRelevance,
  getNewsRelevanceLabel,
  getNewsSummary,
  getNewsTopic,
  matchesNewsSearch,
  NEWS_RELEVANCE_LEVELS,
  NEWS_TOPICS,
  newsScore,
} from "./newsInsights";
import {
  countryOptionLabel,
  getNewsCountryBadgeLabel,
  getNewsDetailCountryLabel,
  getOverseasCountryOptions,
  newsCountryMatches,
} from "./newsCountry";
import {
  getNewsCollectionLabel,
  getNewsPublisherLabel,
  getNewsRegionLabel,
  getNewsRegionType,
  newsRegionCounts,
  newsRegionMatches,
} from "./newsRegion";
import {
  addRecentId,
  getLastVisitAt,
  isStoredId,
  readIdList,
  setLastVisitAt,
  toggleId,
} from "./storage";
import { NEWS_REGION_VALUES, sanitizeNewsSearchParams } from "./newsUrlParams";
import { normalizeSearchCommitValue } from "./searchInput";
import ActiveFilterChips from "./components/ActiveFilterChips";
import DashboardSummary from "./components/DashboardSummary";
import FavoriteButton from "./components/FavoriteButton";
import PriorityBusinessList from "./components/PriorityBusinessList";
import SourceHealthPanel from "./components/SourceHealthPanel";
import { buildDashboardSummary } from "./dashboardSummary";

const DATA_BASE = import.meta.env.VITE_DATA_BASE_URL || "/data";

const TYPE_OPTIONS = [
  { value: "all", label: "전체", sourceType: "" },
  { value: "bid", label: "입찰공고", sourceType: "bid" },
  { value: "procurement_plan", label: "발주계획", sourceType: "procurement_plan" },
  { value: "public_agency_contest", label: "공공기관 공모", sourceType: "public_agency_contest" },
];

const AGENCY_OPTIONS = [
  { value: "all", label: "전체" },
  { value: "G2B", label: "나라장터" },
  { value: "D2B", label: "D2B" },
  { value: "LH", label: "LH" },
  { value: "GH", label: "GH" },
  { value: "iH", label: "iH" },
  { value: "SH", label: "SH" },
];

const STATUS_OPTIONS = [
  { value: "all", label: "전체" },
  { value: "active", label: "진행 중" },
  { value: "closed", label: "마감" },
  { value: "unknown", label: "상태 미확인" },
];

const BUSINESS_PRIORITY_FILTERS = [
  { value: "all", label: "전체" },
  { value: "immediate", label: "즉시 검토" },
  { value: "this_week", label: "이번 주 검토" },
  { value: "recent7", label: "최근 7일 신규" },
  { value: "due7", label: "마감 7일 이내" },
  { value: "important", label: "우선 검토" },
  { value: "favorites", label: "관심목록" },
];

const BUSINESS_SORT_OPTIONS = [
  { value: "priority", label: "영업 우선순위순" },
  { value: "deadline", label: "마감 임박순" },
  { value: "newest", label: "최신 등록순" },
  { value: "oldest", label: "오래된 등록순" },
  { value: "agency", label: "기관명순" },
];

const NEWS_SORT_OPTIONS = [
  { value: "newest", label: "최신순" },
  { value: "relevance", label: "관련도순" },
  { value: "oldest", label: "오래된순" },
];

const NEWS_RELEVANCE_FILTERS = [
  { value: "all", label: "전체" },
  { value: "direct", label: NEWS_RELEVANCE_LEVELS.direct.label },
  { value: "adjacent", label: NEWS_RELEVANCE_LEVELS.adjacent.label },
  { value: "reference", label: NEWS_RELEVANCE_LEVELS.reference.label },
];

const COMPANY_SORT_OPTIONS = [
  { value: "tier", label: "분석 우선순위" },
  { value: "verified", label: "최신 검증순" },
  { value: "name", label: "기업명순" },
];

function useDataset(name) {
  const [state, setState] = useState({ loading: true, error: "", data: null });
  useEffect(() => {
    let active = true;
    fetch(`${DATA_BASE}/${name}.json`)
      .then((response) => {
        if (!response.ok) throw new Error(`데이터를 불러오지 못했습니다. (${response.status})`);
        return response.json();
      })
      .then((data) => active && setState({ loading: false, error: "", data }))
      .catch((error) => active && setState({ loading: false, error: error.message, data: null }));
    return () => {
      active = false;
    };
  }, [name]);
  return state;
}

function getItems(data) {
  if (!data) return [];
  return Array.isArray(data) ? data : data.items || [];
}

function formatDate(value) {
  if (!value) return "-";
  const date = parseDate(value);
  return date ? new Intl.DateTimeFormat("ko-KR").format(date) : String(value).slice(0, 10);
}

function formatAmount(value) {
  const amount = Number(value);
  return Number.isFinite(amount) && amount > 0 ? `${new Intl.NumberFormat("ko-KR").format(amount)}원` : "금액 미공개";
}

function normalizeText(value) {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function getBusinessStatusLabel(item) {
  const status = getBusinessStatus(item);
  if (status === "active") return "진행 중";
  if (status === "closed") return "마감";
  return "상태 미확인";
}

function businessKind(item) {
  if (item.source_type === "public_agency_contest") return "공공기관 공모";
  if (item.source_type === "procurement_plan") return "발주계획";
  return "입찰공고";
}

function displayNoticeStatus(item) {
  const value = item.notice_status || item.notice_stage || "";
  if (!value) return "";
  if (item.source_type !== "public_agency_contest") return value;
  const labels = {
    pre_notice: "사전예고",
    main_notice: "본공고",
    re_notice: "재공모",
    correction: "정정공고",
    update: "자료/일정 변경",
    result: "결과공고",
    unknown: "단계 미확인",
  };
  return labels[value] || value;
}

function displayAgency(item) {
  const code = item.source_code;
  if (code === "LH_CONTEST") return "LH";
  if (code === "GH_CONTEST") return "GH";
  if (code === "IH_NOTICE") return "iH";
  if (code === "SH_CONTEST") return "SH";
  const combined = `${item.source || ""} ${item.source_name || ""}`.toLowerCase();
  if (combined.includes("d2b")) return "D2B";
  if (item.source_type === "bid" || item.source_type === "procurement_plan") return "나라장터";
  return item.source_name || item.source || "출처 미확인";
}

function agencyFilterValue(item) {
  const agency = displayAgency(item);
  if (agency === "나라장터") return "G2B";
  return agency;
}

function projectLocation(item) {
  const sites = Array.isArray(item.project_sites) ? item.project_sites : [];
  const blocks = Array.isArray(item.project_blocks) ? item.project_blocks : [];
  return [...sites, ...blocks].filter(Boolean).join(" / ");
}

function originalUrl(item) {
  return item.external_original_url || item.original_url || item.manual_check?.site_url || "";
}

function isOfficialLinkEnabled(item) {
  const url = originalUrl(item);
  if (!url) return false;
  if (item.source_type === "public_agency_contest") return item.link_verified !== false;
  return true;
}

function attachmentCount(item) {
  return Array.isArray(item.attachments) ? item.attachments.length : 0;
}

function getSearchText(item) {
  return [
    item.title,
    item.organization,
    item.demand_org,
    item.summary,
    item.plan_no,
    item.bid_no,
    item.source_record_id,
    item.business_type,
    item.business_subtype,
    item.notice_status,
    item.notice_stage,
    displayAgency(item),
    projectLocation(item),
  ].join(" ").toLowerCase();
}

function getValidParam(searchParams, key, options, fallback) {
  const value = searchParams.get(key) || fallback;
  return options.includes(value) ? value : fallback;
}

function Layout({ children }) {
  return (
    <div className="site-shell">
      <header className="topbar">
        <Link className="brand" to="/">ModularHub</Link>
        <nav aria-label="주요 메뉴">
          <NavLink to="/business"><Building2 size={17} />사업정보</NavLink>
          <NavLink to="/news"><Newspaper size={17} />뉴스정보</NavLink>
          <NavLink to="/companies"><Factory size={17} />기업정보</NavLink>
        </nav>
      </header>
      <main>{children}</main>
      <footer>공식 OpenAPI와 기관 웹페이지, 뉴스 검색 결과를 정리한 정보 서비스입니다. 최종 판단 전 원문을 확인하세요.</footer>
    </div>
  );
}

function SearchBar({ value, onChange, placeholder, debounceMs = 300 }) {
  const externalValue = String(value || "");
  const [draftValue, setDraftValue] = useState(externalValue);
  const composingRef = useRef(false);
  const timerRef = useRef(null);
  const lastCommittedRef = useRef(externalValue);
  const skipNextChangeRef = useRef(false);

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const commit = useCallback((rawValue) => {
    clearTimer();
    const nextValue = normalizeSearchCommitValue(rawValue);
    if (nextValue === lastCommittedRef.current) return;
    lastCommittedRef.current = nextValue;
    onChange(nextValue);
  }, [clearTimer, onChange]);

  const scheduleCommit = useCallback((nextValue) => {
    clearTimer();
    timerRef.current = setTimeout(() => commit(nextValue), debounceMs);
  }, [clearTimer, commit, debounceMs]);

  useEffect(() => {
    if (!composingRef.current) setDraftValue(externalValue);
    lastCommittedRef.current = externalValue;
  }, [externalValue]);

  useEffect(() => clearTimer, [clearTimer]);

  const handleChange = (event) => {
    const nextValue = event.target.value;
    setDraftValue(nextValue);
    const normalized = normalizeSearchCommitValue(nextValue);
    if (skipNextChangeRef.current && normalized === lastCommittedRef.current) {
      skipNextChangeRef.current = false;
      return;
    }
    if (composingRef.current || event.nativeEvent?.isComposing) return;
    scheduleCommit(nextValue);
  };

  const handleCompositionStart = () => {
    composingRef.current = true;
    clearTimer();
  };

  const handleCompositionEnd = (event) => {
    composingRef.current = false;
    const normalized = normalizeSearchCommitValue(event.currentTarget.value);
    skipNextChangeRef.current = true;
    setDraftValue(normalized);
    commit(normalized);
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && !event.nativeEvent?.isComposing) {
      commit(draftValue);
    }
  };

  const handleBlur = () => {
    if (!composingRef.current) commit(draftValue);
  };

  return (
    <label className="search">
      <Search size={18} />
      <input
        value={draftValue}
        onChange={handleChange}
        onCompositionStart={handleCompositionStart}
        onCompositionEnd={handleCompositionEnd}
        onKeyDown={handleKeyDown}
        onBlur={handleBlur}
        placeholder={placeholder}
      />
    </label>
  );
}

function SummaryItem({ label, value, suffix = "건" }) {
  return (
    <div className="summary-chip">
      <span>{label}</span>
      <strong>{Number(value || 0).toLocaleString("ko-KR")}{suffix}</strong>
    </div>
  );
}

function useFavorites() {
  const [businessFavorites, setBusinessFavorites] = useState(() => readIdList("favoriteBusinessIds"));
  const [newsFavorites, setNewsFavorites] = useState(() => readIdList("favoriteNewsIds"));
  const [recentBusiness, setRecentBusiness] = useState(() => readIdList("recentlyViewedBusinessIds"));
  const [recentNews, setRecentNews] = useState(() => readIdList("recentlyViewedNewsIds"));

  const toggleBusiness = useCallback((id) => setBusinessFavorites(toggleId("favoriteBusinessIds", id)), []);
  const toggleNews = useCallback((id) => setNewsFavorites(toggleId("favoriteNewsIds", id)), []);
  const addRecentBusiness = useCallback((id) => setRecentBusiness(addRecentId("recentlyViewedBusinessIds", id)), []);
  const addRecentNews = useCallback((id) => setRecentNews(addRecentId("recentlyViewedNewsIds", id)), []);

  return {
    businessFavorites,
    newsFavorites,
    recentBusiness,
    recentNews,
    toggleBusiness,
    toggleNews,
    addRecentBusiness,
    addRecentNews,
    isBusinessFavorite: (id) => businessFavorites.includes(String(id)) || isStoredId("favoriteBusinessIds", id),
    isNewsFavorite: (id) => newsFavorites.includes(String(id)) || isStoredId("favoriteNewsIds", id),
  };
}

function HomePage() {
  const metaState = useDataset("meta");
  const businessState = useDataset("business");
  const newsState = useDataset("news");
  const companyState = useDataset("companies/companies");
  const favorites = useFavorites();
  const businessItems = getItems(businessState.data);
  const newsItems = getItems(newsState.data).map((item) => ({ ...item, topic: getNewsTopic(item), relevanceGrade: getNewsRelevance(item) })).sort((a, b) => compareNewsBySort(a, b, "newest"));
  const companyItems = getCompanyItems(companyState.data);
  const companySummary = getCompanySummary(companyItems);
  const dashboardAsOf = parseDate(metaState.data?.generated_at) || parseDate(metaState.data?.last_updated_at) || new Date();
  const businessSummary = getBusinessSummary(businessItems, dashboardAsOf);
  const newsSummary = getNewsSummary(newsItems, dashboardAsOf);
  const summary = buildDashboardSummary({ businessSummary, newsSummary });
  const priorityItems = businessItems
    .filter((item) => isBusinessActionable(item, dashboardAsOf))
    .sort((a, b) => compareBusinessByPriority(a, b, dashboardAsOf))
    .slice(0, 5);
  const lastVisit = getLastVisitAt();

  useEffect(() => {
    setLastVisitAt();
  }, []);

  return (
    <Layout>
      <section className="intro">
        <p className="eyebrow">모듈러 건축 영업 인사이트</p>
        <h1><span>오늘 확인할 사업과</span><span>모듈러 시장 뉴스</span></h1>
        <p>수집된 사업정보와 뉴스정보를 영업 우선순위, 관심목록, 최근 본 항목 기준으로 빠르게 탐색하세요.</p>
        <div className="intro-actions">
          <Link className="button primary" to="/business">사업정보 보기</Link>
          <Link className="button secondary" to="/news">뉴스정보 보기</Link>
          <Link className="button secondary" to="/companies">기업정보 보기</Link>
        </div>
      </section>
      <DashboardSummary
        summary={summary}
        newsItems={newsItems}
        formatDate={formatDate}
        isNewsFavorite={favorites.isNewsFavorite}
        onToggleNewsFavorite={favorites.toggleNews}
      />
      <PriorityBusinessList
        items={priorityItems}
        formatDate={formatDate}
        businessKind={businessKind}
        displayAgency={displayAgency}
        isFavorite={favorites.isBusinessFavorite}
        onToggleFavorite={favorites.toggleBusiness}
        referenceDate={dashboardAsOf}
      />
      <SourceHealthPanel meta={metaState.data || {}} />
      <section className="category-grid" aria-label="서비스 카테고리">
        <Link className="category-panel" to="/business">
          <Building2 size={26} />
          <div><strong>사업정보</strong><span>진행 중 {businessSummary.active}건 · 누적 {businessSummary.total}건 · 마감 {businessSummary.closed}건 · 확인 필요 {businessSummary.unknown}건</span></div>
          <b>{businessSummary.active}건 진행 중</b>
        </Link>
        <Link className="category-panel" to="/news">
          <Newspaper size={26} />
          <div><strong>뉴스정보</strong><span>국내뉴스와 해외 모듈러 RSS</span></div>
          <b>{metaState.data?.news_count ?? newsItems.length}건</b>
        </Link>
        <Link className="category-panel" to="/companies">
          <Factory size={26} />
          <div><strong>기업정보</strong><span>분석 대상 {companySummary.total}개사 · 직접 경쟁사 {companySummary.directCompetitors}개사 · 검증 완료 {companySummary.verified}개사</span></div>
          <b>{companySummary.verified}개사 검증 완료</b>
        </Link>
      </section>
      <div className="public-data-note">
        <strong>검증된 공개 데이터 기준</strong>
        <span>데이터 갱신: {metaState.data?.generated_at ? formatDate(metaState.data.generated_at) : "확인 중"}</span>
        {lastVisit && <span>마지막 방문: {formatDate(lastVisit)}</span>}
        {businessSummary.unknown > 0 && <p>상태 확인 필요 {businessSummary.unknown}건: 마감일 또는 상태 정보가 부족한 누적 사업입니다.</p>}
      </div>
    </Layout>
  );
}

function FilterPanel({ title, open, setOpen, children }) {
  return (
    <aside className={`filters ${open ? "open" : ""}`}>
      <button type="button" className="filter-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span>{title}</span>
        <ChevronDown size={16} />
      </button>
      <div className="filter-body">{children}</div>
    </aside>
  );
}

function BusinessFilters({ values, setParam, filteredCount, onReset, chips, favoriteCount }) {
  const [open, setOpen] = useState(false);
  return (
    <FilterPanel title="사업 검색조건" open={open} setOpen={setOpen}>
      <div className="filter-heading">
        <h2>검색조건</h2>
        <button type="button" className="icon-button" onClick={onReset} aria-label="필터 초기화" title="필터 초기화">
          <RotateCcw size={16} />
        </button>
      </div>
      <SearchBar value={values.q} onChange={(value) => setParam("q", value)} placeholder="공고명, 기관, 번호, 지역" />
      <label>빠른 필터
        <select value={values.priority} onChange={(event) => setParam("priority", event.target.value)}>
          {BUSINESS_PRIORITY_FILTERS.map((option) => <option key={option.value} value={option.value}>{option.label}{option.value === "favorites" ? ` (${favoriteCount})` : ""}</option>)}
        </select>
      </label>
      <label>사업 유형
        <select value={values.type} onChange={(event) => setParam("type", event.target.value)}>
          {TYPE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      <label>기관
        <select value={values.agency} onChange={(event) => setParam("agency", event.target.value)}>
          {AGENCY_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      <label>진행 상태
        <select value={values.status} onChange={(event) => setParam("status", event.target.value)}>
          {STATUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      <label>정렬
        <select value={values.sort} onChange={(event) => setParam("sort", event.target.value)}>
          {BUSINESS_SORT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      <ActiveFilterChips chips={chips} onReset={onReset} />
      <button type="button" className="reset-button" onClick={onReset}>필터 초기화</button>
      <p className="filter-note">검색 결과 {filteredCount.toLocaleString("ko-KR")}건</p>
    </FilterPanel>
  );
}

function NewsFilters({ values, setParam, regionCounts, countryOptions, filteredCount, chips, favoriteCount }) {
  const [open, setOpen] = useState(false);
  const regionOptions = [
    { value: "all", label: "전체", count: regionCounts.all },
    { value: "domestic", label: "국내", count: regionCounts.domestic },
    { value: "overseas", label: "해외", count: regionCounts.overseas },
  ];
  const reset = () => {
    ["q", "region", "country", "days", "topic", "relevance", "sort"].forEach((key) => setParam(key, ""));
  };
  return (
    <FilterPanel title="뉴스 검색조건" open={open} setOpen={setOpen}>
      <h2>검색조건</h2>
      <div className="segmented-filter" role="group" aria-label="뉴스 유형">
        {regionOptions.map((option) => (
          <button key={option.value} type="button" className={values.region === option.value ? "active" : ""} onClick={() => setParam("region", option.value)}>
            <span>{option.label}</span>
            <strong>{option.count.toLocaleString("ko-KR")}</strong>
          </button>
        ))}
      </div>
      {values.region === "overseas" && (
        <label>국가
          <select value={values.country} onChange={(event) => setParam("country", event.target.value)}>
            <option value="all">전체 국가</option>
            {countryOptions.map((option) => (
              <option key={option.value} value={option.value}>{countryOptionLabel(option)}</option>
            ))}
          </select>
        </label>
      )}
      <SearchBar value={values.q} onChange={(value) => setParam("q", value)} placeholder="뉴스 제목, 내용, 언론사 검색" />
      <label>기간
        <select value={values.days} onChange={(event) => setParam("days", event.target.value)}>
          <option value="all">전체</option>
          <option value="7">최근 7일</option>
          <option value="30">최근 30일</option>
          <option value="90">최근 90일</option>
        </select>
      </label>
      <label>주제
        <select value={values.topic} onChange={(event) => setParam("topic", event.target.value)}>
          {NEWS_TOPICS.map((topic) => <option key={topic} value={topic}>{topic}</option>)}
          <option value="favorites">관심목록 ({favoriteCount})</option>
        </select>
      </label>
      <label>관련도
        <select value={values.relevance} onChange={(event) => setParam("relevance", event.target.value)}>
          {NEWS_RELEVANCE_FILTERS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      <label>정렬
        <select value={values.sort} onChange={(event) => setParam("sort", event.target.value)}>
          {NEWS_SORT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      <ActiveFilterChips chips={chips} onReset={reset} />
      <button type="button" className="reset-button" onClick={reset}>필터 초기화</button>
      <p className="filter-note">검색 결과 {filteredCount.toLocaleString("ko-KR")}건</p>
    </FilterPanel>
  );
}

function PriorityBadge({ item, referenceDate }) {
  const info = getBusinessPriorityInfo(item, referenceDate);
  return <span className={`priority-badge ${info.reviewBadgeClass}`}>{info.reviewLabel}</span>;
}

function BusinessCard({ item, isFavorite, onToggleFavorite, recentlyViewed, referenceDate }) {
  const status = getBusinessStatus(item);
  const official = originalUrl(item);
  const info = getBusinessPriorityInfo(item, referenceDate);
  const reasons = info.priorityReasons;
  const isContest = item.source_type === "public_agency_contest";
  const attachments = attachmentCount(item);
  return (
    <article className={`result-card ${isContest ? "contest-card" : ""} status-${status}`}>
      <div className="card-topline">
        <div className="badge-row">
          <span>{displayAgency(item)}</span>
          <span>{businessKind(item)}</span>
          <span className={`status-badge ${status}`}>{getBusinessStatusLabel(item)}</span>
          {info.important && <span className="important">우선 검토</span>}
          <PriorityBadge item={item} referenceDate={referenceDate} />
          {isRecentlyPosted(item, 7, referenceDate) && <span className="new-badge">신규</span>}
          {recentlyViewed && <span>최근 본 항목</span>}
        </div>
        <FavoriteButton active={isFavorite} onClick={onToggleFavorite} />
      </div>
      <h2><Link to={`/business/${item.id}`}>{item.title}</Link></h2>
      {isContest && <p className="contest-subline">{projectLocation(item) || item.organization || "대상지구는 공고문 확인 필요"}</p>}
      <div className="reason-list">{reasons.slice(0, 2).map((reason) => <span key={reason}>{reason}</span>)}</div>
      <dl className="metadata">
        <div><dt>기관</dt><dd>{item.organization || displayAgency(item)}</dd></div>
        <div><dt>게시일</dt><dd>{formatDate(item.posted_at)}</dd></div>
        <div><dt>마감일</dt><dd>{formatDate(item.due_at || item.deadline_at)}</dd></div>
        <div><dt>{isContest ? "D-Day" : "금액"}</dt><dd>{isContest ? (dDayLabel(item) || "일정 확인 필요") : formatAmount(item.amount)}</dd></div>
      </dl>
      {isContest && (
        <div className="contest-extra">
          {attachments > 0 ? <span><FileText size={14} />첨부파일 {attachments}개</span> : <span>첨부파일 정보 없음</span>}
          <span>{item.source_record_id ? `원문 ID ${item.source_record_id}` : "원문 ID 확인 필요"}</span>
        </div>
      )}
      <div className="card-footer">
        <span>{item.source_record_id || item.plan_no || item.bid_no || "출처번호 미확인"}</span>
        <div className="card-actions">
          <Link to={`/business/${item.id}`}>상세보기</Link>
          {official && isOfficialLinkEnabled(item) && <a href={official} target="_blank" rel="noopener noreferrer">공식 원문</a>}
        </div>
      </div>
    </article>
  );
}

function NewsCard({ item, isFavorite, onToggleFavorite, recentlyViewed }) {
  const isOverseas = getNewsRegionType(item) === "overseas";
  const regionLabel = getNewsCountryBadgeLabel(item, isOverseas ? "overseas" : "domestic");
  const publisherLabel = getNewsPublisherLabel(item);
  const original = item.original_url;
  const keywords = Array.isArray(item.keywords) ? item.keywords.join(", ") : item.keywords;
  const score = newsScore(item);
  const scoreReasons = Array.isArray(item.relevance_reasons) ? item.relevance_reasons.slice(0, 3).join(" · ") : "";
  const topic = getNewsTopic(item);
  const relevance = getNewsRelevance(item);
  return (
    <article className="result-card news-card">
      <div className="card-topline">
        <div className="badge-row">
          <span className={isOverseas ? "overseas-badge" : ""}>{regionLabel}</span>
          <span className={`relevance-badge ${relevance}`}>{getNewsRelevanceLabel(relevance)}</span>
          <span>{topic}</span>
          <span>{formatDate(item.published_at)}</span>
          {recentlyViewed && <span>최근 본 항목</span>}
        </div>
        <FavoriteButton active={isFavorite} onClick={onToggleFavorite} label="관심 뉴스" />
      </div>
      <h2><Link to={`/news/${item.id}`}>{item.title}</Link></h2>
      <p>{item.summary || "요약이 없습니다."}</p>
      <div className="news-extra">
        {keywords && <span>{keywords}</span>}
      </div>
      <div className="card-footer">
        <span title={scoreReasons || undefined} aria-label={scoreReasons ? `${publisherLabel}. 관련도 ${score}/100. ${scoreReasons}` : `${publisherLabel}. 관련도 ${score}/100`}>{publisherLabel} · 관련도 {score}/100</span>
        <div className="card-actions">
          {original && <a href={original} target="_blank" rel="noopener noreferrer">원문 보기</a>}
          <Link to={`/news/${item.id}`}>상세보기</Link>
        </div>
      </div>
    </article>
  );
}

function CompanyFilters({ values, setParam, roleOptions, relationshipOptions, tierOptions, statusFilterOptions, filteredCount, chips, onReset }) {
  const [open, setOpen] = useState(false);
  return (
    <FilterPanel title="기업 검색조건" open={open} setOpen={setOpen}>
      <div className="filter-heading">
        <h2>검색조건</h2>
        <button type="button" className="icon-button" onClick={onReset} aria-label="필터 초기화" title="필터 초기화">
          <RotateCcw size={16} />
        </button>
      </div>
      <SearchBar value={values.q} onChange={(value) => setParam("q", value)} placeholder="기업명, 프로젝트, 기술 검색" />
      <label>역할
        <select value={values.role} onChange={(event) => setParam("role", event.target.value)}>
          <option value="all">전체 역할</option>
          {roleOptions.map((option) => <option key={option.value} value={option.value}>{option.label} ({option.count})</option>)}
        </select>
      </label>
      <label>경쟁 관계
        <select value={values.relationship} onChange={(event) => setParam("relationship", event.target.value)}>
          <option value="all">전체</option>
          {relationshipOptions.map((option) => <option key={option.value} value={option.value}>{option.label} ({option.count})</option>)}
        </select>
      </label>
      <label>분석 우선순위
        <select value={values.tier} onChange={(event) => setParam("tier", event.target.value)}>
          <option value="all">전체</option>
          {tierOptions.map((option) => <option key={option.value} value={option.value}>{option.label} ({option.count})</option>)}
        </select>
      </label>
      <label>데이터 상태
        <select value={values.status} onChange={(event) => setParam("status", event.target.value)}>
          <option value="all">전체 상태</option>
          {statusFilterOptions.map((option) => <option key={option.value} value={option.value}>{option.label} ({option.count})</option>)}
        </select>
      </label>
      <label>정렬
        <select value={values.sort} onChange={(event) => setParam("sort", event.target.value)}>
          {COMPANY_SORT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      <ActiveFilterChips chips={chips} onReset={onReset} />
      <button type="button" className="reset-button" onClick={onReset}>필터 초기화</button>
      <p className="filter-note">검색 결과 {filteredCount.toLocaleString("ko-KR")}개사</p>
    </FilterPanel>
  );
}

function CompanyCard({ company }) {
  const highlights = getCompanyHighlights(company);
  const latestFinancial = getLatestFinancial(company);
  const latestRevenue = metricSourceValue(latestFinancial?.revenue);
  const projectSummary = getCompanyProjectSummary(company);
  return (
    <article className="result-card company-card">
      <div className="card-topline">
        <div className="badge-row">
          <span>{getCompanyTypeLabel(company)}</span>
          <span>{getCompetitiveRoleLabel(company)}</span>
          <span>{getTierLabel(company)}</span>
          <span className={`company-status ${getCompanyDataStatus(company)}`}>{getCompanyDataStatusLabel(company)}</span>
        </div>
      </div>
      <h2><Link to={`/companies/${company.company_id}`}>{company.company_name}</Link></h2>
      <p>{company.summary || "현재 공개자료를 추가 조사 중입니다."}</p>
      {highlights.length > 0 ? (
        <div className="company-highlight-grid">
          {highlights.map((highlight) => <span key={highlight}>{highlight}</span>)}
        </div>
      ) : (
        <p className="empty-inline">현재 공개자료를 추가 조사 중입니다.</p>
      )}
      <dl className="metadata">
        <div><dt>최근 재무</dt><dd>{latestFinancial && latestRevenue !== null ? `${latestFinancial.year}년 ${formatKrwReadable(latestRevenue)}` : "공개자료 없음"}</dd></div>
        <div><dt>프로젝트</dt><dd>{projectSummary.verified > 0 ? `검증 ${projectSummary.verified}건${projectSummary.latestYear ? ` · 최신 ${projectSummary.latestYear}` : ""}` : "프로젝트 검증 중"}</dd></div>
        <div><dt>기술·특허</dt><dd>{technologyCount(company) > 0 ? `${technologyCount(company)}건` : "확인 중"}</dd></div>
        <div><dt>최신 기준일</dt><dd>{formatCompanyDate(getLatestVerifiedAt(company))}</dd></div>
        <div><dt>신뢰도</dt><dd>{getConfidenceLabel(company)}</dd></div>
      </dl>
      <div className="card-footer">
        <span>{company.company_name_en || (company.aliases || [])[0] || "별칭 확인 중"}</span>
        <div className="card-actions">
          <Link to={`/companies/${company.company_id}`}>상세보기</Link>
        </div>
      </div>
    </article>
  );
}

function CompanyListingPage() {
  const { loading, error, data } = useDataset("companies/companies");
  const [searchParams, setSearchParams] = useSearchParams();
  const items = getCompanyItems(data);
  const summary = useMemo(() => getCompanySummary(items), [items]);
  const roleOptions = useMemo(() => optionCounts(items, "company_type", COMPANY_TYPE_LABELS), [items]);
  const relationshipOptions = useMemo(() => optionCounts(items, "competitive_role", COMPETITIVE_ROLE_LABELS), [items]);
  const tierOptions = useMemo(() => optionCounts(items, "analysis_tier", TIER_LABELS), [items]);
  const statusFilterOptions = useMemo(() => statusOptions(items), [items]);
  const validValues = useMemo(() => ({
    roles: roleOptions.map((option) => option.value),
    relationships: relationshipOptions.map((option) => option.value),
    tiers: tierOptions.map((option) => option.value),
  }), [relationshipOptions, roleOptions, tierOptions]);

  useEffect(() => {
    if (!items.length) return;
    const { params, changed } = sanitizeCompanySearchParams(searchParams, validValues);
    if (changed) setSearchParams(params, { replace: true });
  }, [items.length, searchParams, setSearchParams, validValues]);

  const values = useMemo(() => ({
    q: searchParams.get("q") || "",
    role: getValidParam(searchParams, "role", ["all", ...validValues.roles], "all"),
    relationship: getValidParam(searchParams, "relationship", ["all", ...validValues.relationships], "all"),
    tier: getValidParam(searchParams, "tier", ["all", ...validValues.tiers], "all"),
    status: getValidParam(searchParams, "status", ["all", "verified", "partial", "collecting"], "all"),
    sort: getValidParam(searchParams, "sort", COMPANY_SORT_VALUES, "tier"),
  }), [searchParams, validValues]);

  const setParam = useCallback((key, value) => {
    const next = new URLSearchParams(searchParams);
    const defaults = { q: "", role: "all", relationship: "all", tier: "all", status: "all", sort: "tier" };
    if (!value || value === defaults[key]) next.delete(key);
    else next.set(key, value);
    if (next.toString() === searchParams.toString()) return;
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  const reset = () => {
    const next = new URLSearchParams(searchParams);
    ["q", "role", "relationship", "tier", "status", "sort"].forEach((key) => next.delete(key));
    setSearchParams(next, { replace: true });
  };

  const filtered = useMemo(() => items
    .filter((company) => companyMatchesFilters(company, values))
    .sort((a, b) => compareCompanies(a, b, values.sort)), [items, values]);

  const chips = [
    { key: "q", active: Boolean(values.q), label: `검색어: ${values.q}`, onRemove: () => setParam("q", "") },
    { key: "role", active: values.role !== "all", label: COMPANY_TYPE_LABELS[values.role], onRemove: () => setParam("role", "all") },
    { key: "relationship", active: values.relationship !== "all", label: COMPETITIVE_ROLE_LABELS[values.relationship], onRemove: () => setParam("relationship", "all") },
    { key: "tier", active: values.tier !== "all", label: TIER_LABELS[values.tier], onRemove: () => setParam("tier", "all") },
    { key: "status", active: values.status !== "all", label: statusFilterOptions.find((option) => option.value === values.status)?.label, onRemove: () => setParam("status", "all") },
  ];

  return (
    <Layout>
      <section className="page-heading">
        <p className="eyebrow">COMPANY</p>
        <h1>스틸 모듈러 기업정보</h1>
        <p>건설사, 모듈러 전문 제작사, 설계사의 사업 역량과 경쟁 현황을 확인합니다.</p>
      </section>
      <section className="summary-strip company-summary-strip" aria-label="기업정보 요약">
        <SummaryItem label="전체 기업" value={summary.total} suffix="개사" />
        <SummaryItem label="직접 경쟁사" value={summary.directCompetitors} suffix="개사" />
        <SummaryItem label="검증 완료" value={summary.verified} suffix="개사" />
        <SummaryItem label="생산시설 확인 기업" value={summary.facilityConfirmed} suffix="개사" />
      </section>
      <div className="content-layout">
        <CompanyFilters
          values={values}
          setParam={setParam}
          roleOptions={roleOptions}
          relationshipOptions={relationshipOptions}
          tierOptions={tierOptions}
          statusFilterOptions={statusFilterOptions}
          filteredCount={filtered.length}
          chips={chips}
          onReset={reset}
        />
        <section className="results" aria-live="polite">
          <div className="source-status lifecycle-summary">
            <p>전체 {summary.total.toLocaleString("ko-KR")}개사 · 직접 경쟁사 {summary.directCompetitors.toLocaleString("ko-KR")}개사 · 검증 완료 {summary.verified.toLocaleString("ko-KR")}개사</p>
            <div className="mini-bars" aria-label="기업 역할별 분포">
              {summary.roleCounts.slice(0, 5).map((option) => (
                <div key={option.value}><span>{option.label}</span><b style={{ width: `${Math.max(8, (option.count / Math.max(summary.total, 1)) * 100)}%` }} /> <em>{option.count}</em></div>
              ))}
            </div>
          </div>
          {loading && <div className="state">기업정보를 불러오는 중입니다.</div>}
          {error && <div className="state error">기업정보 데이터를 불러오지 못했습니다.</div>}
          {!loading && !error && items.length === 0 && <div className="state">등록된 기업정보가 없습니다.</div>}
          {!loading && !error && items.length > 0 && filtered.length === 0 && <div className="state">현재 검색조건에 맞는 기업정보가 없습니다.</div>}
          {filtered.map((company) => <CompanyCard key={company.company_id} company={company} />)}
        </section>
      </div>
    </Layout>
  );
}

function CompanyDetailPage() {
  const { companyId } = useParams();
  const { loading, error, data } = useDataset("companies/companies");
  const company = getCompanyItems(data).find((item) => item.company_id === companyId);

  if (loading) return <Layout><div className="state">기업정보를 불러오는 중입니다.</div></Layout>;
  if (error) return <Layout><div className="state error">기업정보 데이터를 불러오지 못했습니다.</div></Layout>;
  if (!company) {
    return (
      <Layout>
        <div className="state company-not-found">
          <span>기업정보를 찾을 수 없습니다.</span>
          <Link className="button secondary" to="/companies">기업정보 목록으로 돌아가기</Link>
        </div>
      </Layout>
    );
  }

  const financials = [...(Array.isArray(company.financials) ? company.financials : [])].sort((a, b) => Number(b.year || 0) - Number(a.year || 0)).slice(0, 3);
  const latestAudit = [...(Array.isArray(company.audit_information) ? company.audit_information : [])].sort((a, b) => Number(b.fiscal_year || 0) - Number(a.fiscal_year || 0))[0];
  const projects = Array.isArray(company.project_portfolio) ? company.project_portfolio : [];
  const production = productionFacilities(company);
  const productionInfo = productionSummary(company);
  const signals = Array.isArray(company.recent_signals) ? company.recent_signals : [];
  const sources = (Array.isArray(company.sources) ? company.sources : []).filter((source) => !String(source.source_url || "").includes(".cache"));
  const technology = company.technology && typeof company.technology === "object" ? company.technology : {};
  const technologyItems = Object.values(technology).flatMap((value) => Array.isArray(value) ? value : []).slice(0, 8);
  const project = representativeProject(company);
  const gaps = Array.isArray(company.research_gaps) ? company.research_gaps : [];

  return (
    <Layout>
      <article className="detail-page company-detail">
        <Link className="back" to="/companies"><ArrowLeft size={17} />목록으로</Link>
        <div className="badge-row">
          <span>{getCompanyTypeLabel(company)}</span>
          <span>{getCompetitiveRoleLabel(company)}</span>
          <span>{getTierLabel(company)}</span>
          <span className={`company-status ${getCompanyDataStatus(company)}`}>{getCompanyDataStatusLabel(company)}</span>
        </div>
        <h1>{company.company_name}</h1>
        <dl className="detail-grid">
          <div><dt>검증 상태</dt><dd>{getReviewStatusLabel(company)}</dd></div>
          <div><dt>데이터 신뢰도</dt><dd>{getConfidenceLabel(company)}</dd></div>
          <div><dt>기준일</dt><dd>{formatCompanyDate(getLatestVerifiedAt(company))}</dd></div>
          <div><dt>영문명</dt><dd>{company.company_name_en || "확인 중"}</dd></div>
          <div><dt>본사</dt><dd>{company.headquarters || "확인 중"}</dd></div>
          <div><dt>OpenDART</dt><dd>{isDartIdentityConfirmed(company) ? "OpenDART 법인 식별 완료" : "확인 중"}</dd></div>
        </dl>

        <section className="summary">
          <h2>경쟁 포지션</h2>
          <p>{company.summary || "현재 공개자료를 추가 조사 중입니다."}</p>
          <div className="company-highlight-grid">
            <span>{project?.project_name ? `대표 실적: ${project.project_name}` : "대표 실적 확인 중"}</span>
            <span>{technologyCount(company) > 0 ? `기술·특허 ${technologyCount(company)}건 확인` : "기술 자료 확인 중"}</span>
            <span>{financials.length ? `재무 ${financials.map((item) => item.year).join(", ")}년 확인` : "재무 공개자료 없음"}</span>
          </div>
        </section>

        <section className="summary">
          <h2>기업 개요</h2>
          <dl className="detail-grid compact-detail-grid">
            <div><dt>회사 유형</dt><dd>{getCompanyTypeLabel(company)}</dd></div>
            <div><dt>경쟁 관계</dt><dd>{getCompetitiveRoleLabel(company)}</dd></div>
            <div><dt>분석 우선순위</dt><dd>{getTierLabel(company)}</dd></div>
            <div><dt>모듈러 공법</dt><dd>{(company.modular_methods || []).join(", ") || "확인 중"}</dd></div>
            <div><dt>목표 시장</dt><dd>{(company.target_markets || []).join(", ") || "확인 중"}</dd></div>
            <div><dt>웹사이트</dt><dd>{company.website_url ? <a href={company.website_url} target="_blank" rel="noopener noreferrer">공식 사이트 <ExternalLink size={13} /></a> : "확인 중"}</dd></div>
          </dl>
        </section>

        <section className="summary">
          <h2>생산 역량</h2>
          <p className="finance-note">생산 운영 방식: {getProductionModelLabel(company)}</p>
          {production.length ? (
            <div className="company-section-list">
              {production.map((item) => (
                <div key={item.facility_id || item.facility_name}>
                  <strong>{item.facility_name || "시설명 확인 중"}</strong>
                  <span>{[item.city || item.region || item.location, item.ownership_type, item.operation_status].filter(Boolean).join(" · ") || "세부 정보 확인 중"}</span>
                  {(item.production_scope || []).length > 0 && <span>생산 대상: {item.production_scope.join(", ")}</span>}
                  {item.site_area_m2 && <span>부지면적 {Number(item.site_area_m2).toLocaleString("ko-KR")}㎡</span>}
                  {item.building_area_m2 && <span>건축면적 {Number(item.building_area_m2).toLocaleString("ko-KR")}㎡</span>}
                  {item.reported_capacity && item.capacity_unit
                    ? <span>공식 생산능력 {item.reported_capacity} {item.capacity_unit}</span>
                    : <span>공개자료에서 공식 생산능력 수치가 확인되지 않았습니다.</span>}
                  <span>기준일: {formatCompanyDate(item.verified_at || productionInfo.verified_at)}</span>
                </div>
              ))}
            </div>
          ) : <p>{productionInfo.own_facility_status === "not_publicly_confirmed" ? "현재 공개자료에서 검증된 생산시설 정보를 확인하지 못했습니다." : "검증된 생산시설 정보를 추가 조사 중입니다."}</p>}
        </section>

        <section className="summary">
          <h2>최근 3개년 재무</h2>
          {financials.length ? (
            <>
              <p className="finance-note">회사 전체 재무 · {latestAudit?.reporting_scope === "consolidated" ? "연결" : "별도"} · {latestAudit?.accounting_standard === "general_korean_gaap" ? "일반기업회계기준" : latestAudit?.accounting_standard || "회계기준 확인 중"} · 감사의견 {latestAudit?.audit_opinion === "unmodified" ? "적정" : latestAudit?.audit_opinion || "확인 중"}</p>
              <div className="company-table-wrap">
                <table className="company-financial-table">
                  <thead><tr><th>연도</th><th>매출</th><th>영업이익</th><th>순이익</th><th>영업현금흐름</th></tr></thead>
                  <tbody>
                    {financials.map((item) => (
                      <tr key={item.year}>
                        <th>{item.year}</th>
                        <td>{formatKrwReadable(metricSourceValue(item.revenue))}</td>
                        <td>{formatKrwReadable(metricSourceValue(item.operating_profit))}</td>
                        <td>{formatKrwReadable(metricSourceValue(item.net_income))}</td>
                        <td>{formatKrwReadable(metricSourceValue(item.operating_cash_flow))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="finance-note">모듈러 부문 별도 재무는 공개자료에서 확인되지 않았습니다.</p>
            </>
          ) : <p>공개자료에서 확인된 재무정보가 없습니다.</p>}
        </section>

        <section className="summary">
          <h2>주요 모듈러 실적</h2>
          {projects.length ? (
            <div className="company-section-list project-portfolio-list">
              {projects.slice(0, 6).map((item) => (
                <div key={item.project_id || item.project_name}>
                  <strong>{item.project_name || "프로젝트명 확인 중"}</strong>
                  <span>{[
                    item.client_name || item.client || item.ordering_agency,
                    item.sector || item.building_use,
                    getProjectRoleLabel(item),
                    getProjectStatusLabel(item),
                  ].filter(Boolean).join(" · ") || "세부 정보 확인 중"}</span>
                  <span>{[
                    item.location,
                    getStructureTypeLabel(item),
                    item.completion_date ? `준공 ${item.completion_date}` : null,
                    item.contract_date ? `계약 ${item.contract_date}` : null,
                  ].filter(Boolean).join(" · ")}</span>
                  {(item.gross_floor_area || item.module_count || item.contract_amount) && (
                    <span>{[
                      item.gross_floor_area ? `연면적 ${Number(item.gross_floor_area).toLocaleString("ko-KR")}${item.gross_floor_area_unit || ""}` : null,
                      item.module_count ? `모듈 ${Number(item.module_count).toLocaleString("ko-KR")}개` : null,
                      item.contract_amount ? `계약금액 ${formatKrwReadable(item.contract_amount)}` : null,
                    ].filter(Boolean).join(" · ")}</span>
                  )}
                  {item.project_summary && <span>{item.project_summary}</span>}
                  <span>검증 상태: {item.evidence_status === "verified" ? "검증 완료" : item.evidence_status === "partially_verified" ? "부분 검증" : "확인 중"}</span>
                </div>
              ))}
            </div>
          ) : <p>현재 공개자료를 추가 조사 중입니다.</p>}
        </section>

        <section className="summary">
          <h2>기술·특허</h2>
          {technologyItems.length ? (
            <div className="company-section-list">
              {technologyItems.map((item, index) => (
                <div key={item.technology_id || item.registration_number || `${item.name}-${index}`}>
                  <strong>{item.name || item.registration_number || "기술명 확인 중"}</strong>
                  <span>{[item.record_type, item.status, item.technology_area].filter(Boolean).join(" · ") || item.summary || "세부 정보 확인 중"}</span>
                </div>
              ))}
            </div>
          ) : <p>현재 공개자료를 추가 조사 중입니다.</p>}
        </section>

        <section className="summary">
          <h2>최근 동향</h2>
          {signals.length ? (
            <div className="company-section-list">
              {signals.map((item) => (
                <div key={item.signal_id || item.title}>
                  <strong>{item.title || "동향 제목 확인 중"}</strong>
                  <span>{[item.occurred_at, item.signal_type].filter(Boolean).join(" · ")}</span>
                  {item.summary && <span>{item.summary}</span>}
                </div>
              ))}
            </div>
          ) : <p>현재 공개자료를 추가 조사 중입니다.</p>}
        </section>

        <section className="summary">
          <h2>데이터 검증 정보</h2>
          <dl className="detail-grid compact-detail-grid">
            <div><dt>검토 상태</dt><dd>{getReviewStatusLabel(company)}</dd></div>
            <div><dt>신뢰도</dt><dd>{getConfidenceLabel(company)}</dd></div>
            <div><dt>DART corp_code</dt><dd>{company.dart_identity?.dart_corp_code || "확인 중"}</dd></div>
            <div><dt>최근 감사보고서</dt><dd>{latestAudit?.receipt_number || "공개자료 없음"}</dd></div>
          </dl>
          {gaps.length > 0 && (
            <div className="company-section-list">
              {gaps.slice(0, 4).map((gap) => <div key={`${gap.area}-${gap.status}`}><strong>{gap.area}</strong><span>{gap.description || gap.status}</span></div>)}
            </div>
          )}
        </section>

        <section className="summary">
          <h2>출처</h2>
          {sources.length ? (
            <div className="source-list">
              {sources.slice(0, 12).map((source) => (
                <div key={source.source_id || source.source_url}>
                  <strong>{source.source_name || source.publisher || "출처"}</strong>
                  <span>{[source.source_type, source.published_at || source.accessed_at, source.confidence].filter(Boolean).join(" · ")}</span>
                  {source.receipt_number && <span>접수번호 {source.receipt_number}</span>}
                  {sourceHasUrl(source) && <a href={source.source_url} target="_blank" rel="noopener noreferrer">원문 보기 <ExternalLink size={13} /></a>}
                </div>
              ))}
            </div>
          ) : <p>공개 출처를 추가 정리 중입니다.</p>}
        </section>
      </article>
    </Layout>
  );
}

function BusinessListingPage() {
  const { loading, error, data } = useDataset("business");
  const metaState = useDataset("meta");
  const [searchParams, setSearchParams] = useSearchParams();
  const favorites = useFavorites();
  const items = getItems(data);
  const businessAsOf = useMemo(
    () => parseDate(metaState.data?.generated_at) || parseDate(metaState.data?.last_updated_at) || new Date(),
    [metaState.data?.generated_at, metaState.data?.last_updated_at],
  );
  const values = {
    q: searchParams.get("q") || "",
    type: getValidParam(searchParams, "type", TYPE_OPTIONS.map((item) => item.value), "all"),
    agency: getValidParam(searchParams, "agency", AGENCY_OPTIONS.map((item) => item.value), "all"),
    status: getValidParam(searchParams, "status", STATUS_OPTIONS.map((item) => item.value), "all"),
    priority: getValidParam(searchParams, "priority", BUSINESS_PRIORITY_FILTERS.map((item) => item.value), "all"),
    sort: getValidParam(searchParams, "sort", BUSINESS_SORT_OPTIONS.map((item) => item.value), "priority"),
  };
  const setParam = useCallback((key, value) => {
    const next = new URLSearchParams(searchParams);
    if (!value || value === "all" || (key === "sort" && value === "priority")) next.delete(key);
    else next.set(key, value);
    if (key === "priority" && value === "important") next.delete("sort");
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);
  const reset = () => setSearchParams({}, { replace: true });

  const filtered = useMemo(() => {
    const queryTerms = normalizeText(values.q).split(" ").filter(Boolean);
    return items.filter((item) => {
      const filterMatches = matchesBusinessFilters(
        item,
        { sourceType: values.type, agency: values.agency, status: values.status },
        { getAgencyValue: agencyFilterValue, getStatus: getBusinessStatus },
      );
      if (!filterMatches) return false;
      if (values.priority === "favorites" && !favorites.isBusinessFavorite(item.id)) return false;
      if (values.priority === "recent7" && !isRecentlyPosted(item, 7, businessAsOf)) return false;
      if (values.priority === "due7" && !isDeadlineWithin(item, 7, businessAsOf)) return false;
      if (values.priority === "important" && !isImportantBusiness(item, businessAsOf)) return false;
      if (["immediate", "this_week"].includes(values.priority) && getBusinessPriority(item, businessAsOf) !== values.priority) return false;
      const text = getSearchText(item);
      return !queryTerms.length || queryTerms.every((term) => text.includes(term));
    }).sort((a, b) => compareBusinessBySort(a, b, values.sort, businessAsOf, displayAgency));
  }, [businessAsOf, favorites, items, values.agency, values.priority, values.q, values.sort, values.status, values.type]);

  const summary = useMemo(() => getBusinessSummary(items, businessAsOf), [businessAsOf, items]);
  const chips = [
    { key: "q", active: Boolean(values.q), label: `검색어: ${values.q}`, onRemove: () => setParam("q", "") },
    { key: "priority", active: values.priority !== "all", label: BUSINESS_PRIORITY_FILTERS.find((item) => item.value === values.priority)?.label, onRemove: () => setParam("priority", "all") },
    { key: "type", active: values.type !== "all", label: TYPE_OPTIONS.find((item) => item.value === values.type)?.label, onRemove: () => setParam("type", "all") },
    { key: "agency", active: values.agency !== "all", label: AGENCY_OPTIONS.find((item) => item.value === values.agency)?.label, onRemove: () => setParam("agency", "all") },
    { key: "status", active: values.status !== "all", label: STATUS_OPTIONS.find((item) => item.value === values.status)?.label, onRemove: () => setParam("status", "all") },
  ];

  let emptyMessage = "조건에 맞는 사업정보가 없습니다. 검색어 또는 필터를 줄여보세요.";
  if (values.priority === "favorites") emptyMessage = "관심목록에 저장한 사업이 없습니다.";
  if (values.priority === "important") emptyMessage = "현재 검토 가능한 우선 사업이 없습니다.";
  if (values.agency === "SH") emptyMessage = "현재 공개 가능한 SH 민간참여 공공주택 공모가 없습니다. SH 수집기는 정상 모니터링 중입니다.";

  return (
    <Layout>
      <section className="page-heading">
        <p className="eyebrow">BUSINESS</p>
        <h1>모듈러 사업정보</h1>
        <p>입찰공고, 발주계획, 공공기관 공모를 영업 우선순위 기준으로 확인합니다.</p>
      </section>
      <section className="summary-strip" aria-label="사업정보 요약">
        <SummaryItem label="전체" value={summary.total} />
        <SummaryItem label="진행 중" value={summary.active} />
        <SummaryItem label="마감 7일" value={summary.dueWithin7} />
        <SummaryItem label="최근 7일" value={summary.recentlyPosted7} />
        <SummaryItem label="우선 검토" value={summary.important} />
      </section>
      <div className="content-layout">
        <BusinessFilters values={values} setParam={setParam} filteredCount={filtered.length} onReset={reset} chips={chips} favoriteCount={favorites.businessFavorites.length} />
        <section className="results" aria-live="polite">
          <div className="source-status lifecycle-summary">
            <p>전체 {summary.total.toLocaleString("ko-KR")}건 · 진행 중 {summary.active}건 · 마감 {summary.closed}건 · 상태 미확인 {summary.unknown}건</p>
            <div className="mini-bars" aria-label="출처별 진행 중 사업">
              {summary.sourceCounts.slice(0, 5).map(([name, count]) => (
                <div key={name}><span>{name}</span><b style={{ width: `${Math.max(8, (count / Math.max(summary.active, 1)) * 100)}%` }} /> <em>{count}</em></div>
              ))}
            </div>
          </div>
          {loading && <div className="state">데이터를 불러오는 중입니다.</div>}
          {error && <div className="state error">{error}</div>}
          {!loading && !error && filtered.length === 0 && <div className="state">{emptyMessage}</div>}
          {filtered.map((item) => (
            <BusinessCard
              key={item.id}
              item={item}
              isFavorite={favorites.isBusinessFavorite(item.id)}
              onToggleFavorite={() => favorites.toggleBusiness(item.id)}
              recentlyViewed={favorites.recentBusiness.includes(String(item.id))}
              referenceDate={businessAsOf}
            />
          ))}
        </section>
      </div>
    </Layout>
  );
}

function NewsListingPage() {
  const { loading, error, data } = useDataset("news");
  const [searchParams, setSearchParams] = useSearchParams();
  const favorites = useFavorites();
  const items = getItems(data);
  const enriched = useMemo(() => items.map((item) => ({ ...item, topic: getNewsTopic(item), relevanceGrade: getNewsRelevance(item) })), [items]);

  useEffect(() => {
    const { params, changed } = sanitizeNewsSearchParams(searchParams);
    if (changed) setSearchParams(params, { replace: true });
  }, [searchParams, setSearchParams]);

  const countryParam = searchParams.get("country");
  const values = {
    q: searchParams.get("q") || "",
    region: getValidParam(searchParams, "region", NEWS_REGION_VALUES, "all"),
    country: countryParam ? (countryParam === "unknown" ? "unknown" : countryParam.toUpperCase()) : "all",
    days: getValidParam(searchParams, "days", ["all", "7", "30", "90"], "all"),
    topic: NEWS_TOPICS.includes(searchParams.get("topic")) || searchParams.get("topic") === "favorites" ? searchParams.get("topic") : "전체 주제",
    relevance: getValidParam(searchParams, "relevance", NEWS_RELEVANCE_FILTERS.map((item) => item.value), "all"),
    sort: getValidParam(searchParams, "sort", NEWS_SORT_OPTIONS.map((item) => item.value), "newest"),
  };
  const setParam = useCallback((key, value) => {
    const next = new URLSearchParams(searchParams);
    const before = searchParams.toString();
    const defaults = { region: "all", days: "all", topic: "전체 주제", relevance: "all", sort: "newest", q: "" };
    defaults.country = "all";
    if (!value || value === defaults[key]) next.delete(key);
    else next.set(key, value);
    if (key === "region" && value !== "overseas") next.delete("country");
    if (key === "country" && values.region !== "overseas") next.delete("country");
    if (next.toString() === before) return;
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams, values.region]);

  const countryOptions = useMemo(() => getOverseasCountryOptions(enriched, getNewsRegionType), [enriched]);

  useEffect(() => {
    if (values.region !== "overseas") return;
    if (values.country === "all") return;
    if (!enriched.length) return;
    if (countryOptions.some((option) => option.value === values.country)) return;
    setParam("country", "all");
  }, [countryOptions, enriched.length, setParam, values.country, values.region]);

  const filtered = useMemo(() => {
    return enriched.filter((item) => {
      if (!newsRegionMatches(item, values.region)) return false;
      if (values.region === "overseas" && !newsCountryMatches(item, values.country)) return false;
      if (values.topic === "favorites" && !favorites.isNewsFavorite(item.id)) return false;
      if (values.topic !== "전체 주제" && values.topic !== "favorites" && item.topic !== values.topic) return false;
      if (values.relevance !== "all" && item.relevanceGrade !== values.relevance) return false;
      if (values.days !== "all") {
        const published = parseDate(item.published_at);
        const threshold = new Date();
        threshold.setDate(threshold.getDate() - Number(values.days));
        if (!published || published < threshold) return false;
      }
      return matchesNewsSearch(item, values.q);
    }).sort((a, b) => compareNewsBySort(a, b, values.sort));
  }, [enriched, favorites, values.country, values.days, values.q, values.region, values.relevance, values.sort, values.topic]);

  const counts = newsRegionCounts(enriched);
  const chips = [
    { key: "q", active: Boolean(values.q), label: `검색어: ${values.q}`, onRemove: () => setParam("q", "") },
    { key: "region", active: values.region !== "all", label: { domestic: "국내", overseas: "해외" }[values.region], onRemove: () => setParam("region", "all") },
    { key: "days", active: values.days !== "all", label: `최근 ${values.days}일`, onRemove: () => setParam("days", "all") },
    { key: "topic", active: values.topic !== "전체 주제", label: values.topic === "favorites" ? "관심목록" : values.topic, onRemove: () => setParam("topic", "전체 주제") },
    { key: "relevance", active: values.relevance !== "all", label: `관련도: ${getNewsRelevanceLabel(values.relevance)}`, onRemove: () => setParam("relevance", "all") },
  ];
  if (values.region === "overseas" && values.country !== "all") {
    chips.splice(2, 0, {
      key: "country",
      active: true,
      label: countryOptions.find((option) => option.value === values.country)?.label || "국가",
      onRemove: () => setParam("country", "all"),
    });
  }
  const domesticCount = counts.domestic;
  const overseasCount = counts.overseas;
  const total = Math.max(counts.all, 1);
  const emptyMessage = values.region === "overseas" && values.country !== "all"
    ? "현재 선택한 국가와 검색조건에 맞는 뉴스가 없습니다."
    : values.topic === "favorites"
    ? "관심목록에 저장한 뉴스가 없습니다."
    : values.q
      ? "입력한 검색어와 일치하는 뉴스가 없습니다."
      : "현재 검색조건에 맞는 뉴스가 없습니다.";

  return (
    <Layout>
      <section className="page-heading">
        <p className="eyebrow">NEWS</p>
        <h1>모듈러 뉴스정보</h1>
        <p>국내·해외 뉴스와 주제, 기간, 관련도를 조합해 모듈러 시장 신호를 확인합니다.</p>
      </section>
      <div className="content-layout">
        <NewsFilters values={values} setParam={setParam} regionCounts={counts} countryOptions={countryOptions} filteredCount={filtered.length} chips={chips} favoriteCount={favorites.newsFavorites.length} />
        <section className="results" aria-live="polite">
          <div className="source-status lifecycle-summary">
            <p>전체 {counts.all.toLocaleString("ko-KR")}건 · 국내 {domesticCount.toLocaleString("ko-KR")}건 · 해외 {overseasCount.toLocaleString("ko-KR")}건</p>
            <div className="ratio-bar" aria-label="국내뉴스와 해외뉴스 비중">
              <span style={{ width: `${(domesticCount / total) * 100}%` }}>국내</span>
              <b style={{ width: `${(overseasCount / total) * 100}%` }}>해외</b>
            </div>
          </div>
          {loading && <div className="state">뉴스를 불러오는 중입니다.</div>}
          {error && <div className="state error">{error}</div>}
          {!loading && !error && filtered.length === 0 && <div className="state">{emptyMessage}</div>}
          {filtered.map((item) => (
            <NewsCard
              key={item.id}
              item={item}
              isFavorite={favorites.isNewsFavorite(item.id)}
              onToggleFavorite={() => favorites.toggleNews(item.id)}
              recentlyViewed={favorites.recentNews.includes(String(item.id))}
            />
          ))}
        </section>
      </div>
    </Layout>
  );
}

function DetailPage({ type }) {
  const { id } = useParams();
  const isBusiness = type === "business";
  const { loading, error, data } = useDataset(type);
  const metaState = useDataset("meta");
  const favorites = useFavorites();
  const { addRecentBusiness, addRecentNews } = favorites;
  const item = getItems(data).find((entry) => String(entry.id) === String(id));

  useEffect(() => {
    if (!item) return;
    if (isBusiness) addRecentBusiness(item.id);
    else addRecentNews(item.id);
  }, [addRecentBusiness, addRecentNews, isBusiness, item]);

  if (loading) return <Layout><div className="state">상세정보를 불러오는 중입니다.</div></Layout>;
  if (error || !item) return <Layout><div className="state error">해당 정보를 찾을 수 없습니다.</div></Layout>;

  const official = isBusiness ? originalUrl(item) : item.original_url;
  const detailAsOf = parseDate(metaState.data?.generated_at) || parseDate(metaState.data?.last_updated_at) || new Date();
  const businessPriorityInfo = isBusiness ? getBusinessPriorityInfo(item, detailAsOf) : null;
  const isContest = isBusiness && item.source_type === "public_agency_contest";
  const status = isBusiness ? getBusinessStatus(item) : "";
  const noticeStatus = isBusiness ? displayNoticeStatus(item) : "";
  const attachments = Array.isArray(item.attachments) ? item.attachments : [];
  const topic = !isBusiness ? getNewsTopic(item) : "";
  const newsPublisherLabel = !isBusiness ? getNewsPublisherLabel(item) : "";
  const newsCollectionLabel = !isBusiness ? getNewsCollectionLabel(item) : "";
  const newsDisplayRegionLabel = !isBusiness ? getNewsRegionLabel(item) : "";
  const newsCountryLabel = !isBusiness ? getNewsDetailCountryLabel(item) : "";
  const newsRelevanceScore = !isBusiness ? newsScore(item) : 0;
  const newsRelevanceReasons = !isBusiness && Array.isArray(item.relevance_reasons) ? item.relevance_reasons.slice(0, 3).join(" · ") : "";

  return (
    <Layout>
      <article className="detail-page">
        <Link className="back" to={`/${type}`}><ArrowLeft size={17} />목록으로</Link>
        <div className="detail-action-row">
          <div className="badge-row">
            <span>{isBusiness ? displayAgency(item) : newsDisplayRegionLabel}</span>
            <span>{isBusiness ? businessKind(item) : topic}</span>
            {!isBusiness && <span>{newsPublisherLabel}</span>}
            {!isBusiness && newsCollectionLabel && <span>{newsCollectionLabel}</span>}
            {isBusiness && <span className={`status-badge ${status}`}>{getBusinessStatusLabel(item)}</span>}
            {isBusiness && businessPriorityInfo.important && <span className="important">우선 검토</span>}
            {isBusiness && <PriorityBadge item={item} referenceDate={detailAsOf} />}
            {isBusiness && noticeStatus && <span>{noticeStatus}</span>}
          </div>
          <FavoriteButton
            active={isBusiness ? favorites.isBusinessFavorite(item.id) : favorites.isNewsFavorite(item.id)}
            onClick={() => (isBusiness ? favorites.toggleBusiness(item.id) : favorites.toggleNews(item.id))}
            label={isBusiness ? "관심 사업" : "관심 뉴스"}
          />
        </div>
        <h1>{item.title}</h1>
        {isBusiness && <div className="reason-list">{getBusinessPriorityReasons(item, detailAsOf).map((reason) => <span key={reason}>{reason}</span>)}</div>}
        <dl className="detail-grid">
          {!isBusiness && <div><dt>표시 지역</dt><dd>{newsDisplayRegionLabel}</dd></div>}
          {!isBusiness && <div><dt>발행 국가</dt><dd>{newsCountryLabel}</dd></div>}
          <div><dt>{isBusiness ? "기관" : "발행 언론사"}</dt><dd>{(isBusiness ? item.organization : newsPublisherLabel) || "-"}</dd></div>
          <div><dt>게시일</dt><dd>{formatDate(isBusiness ? item.posted_at : item.published_at)}</dd></div>
          <div><dt>{isBusiness ? "마감일" : "수집 경로"}</dt><dd>{isBusiness ? formatDate(item.due_at || item.deadline_at) : (newsCollectionLabel || item.collection_source || item.source || "뉴스")}</dd></div>
          {isBusiness && <div><dt>수요기관</dt><dd>{item.demand_org || "-"}</dd></div>}
          {isBusiness && <div><dt>업무구분</dt><dd>{[item.business_type, item.business_subtype].filter(Boolean).join(" / ") || "-"}</dd></div>}
          {isBusiness && <div><dt>검토 시점</dt><dd>{businessPriorityInfo.reviewLabel}</dd></div>}
          {isBusiness && <div><dt>우선 검토</dt><dd>{businessPriorityInfo.important ? "대상" : "아님"}</dd></div>}
          {isBusiness && <div><dt>금액</dt><dd>{formatAmount(item.amount)}</dd></div>}
          {isBusiness && <div><dt>공고/판단/계획번호</dt><dd>{item.source_record_id || item.plan_no || item.bid_no || "-"}</dd></div>}
          {isBusiness && <div><dt>진행 상태</dt><dd>{getBusinessStatusLabel(item)}</dd></div>}
          {isContest && <div><dt>대상지구/블록</dt><dd>{projectLocation(item) || "공고문 확인 필요"}</dd></div>}
          {!isBusiness && <div><dt>관련도</dt><dd title={newsRelevanceReasons || undefined}>{newsRelevanceScore}/100</dd></div>}
        </dl>
        <section className="summary"><h2>내용</h2><p>{item.summary || "상세 요약이 없습니다."}</p></section>
        {isContest && <section className="summary"><h2>공모 일정</h2><p>{item.application_schedule_text || "공모 일정은 첨부 공고문 확인"}</p></section>}
        {isContest && attachments.length > 0 && (
          <section className="summary">
            <h2>첨부파일</h2>
            <ul className="attachment-list">
              {attachments.map((file) => <li key={`${file.url}-${file.name}`}><a href={file.url} target="_blank" rel="noopener noreferrer">{file.name || "첨부파일"}{file.file_type ? ` (${file.file_type})` : ""}</a></li>)}
            </ul>
          </section>
        )}
        <div className="detail-actions">
          {official && <a className="button primary" href={official} target="_blank" rel="noopener noreferrer">{isBusiness ? "공식 원문" : "원문 보기"} <ExternalLink size={16} /></a>}
          {isBusiness && item.manual_check?.site_url && <a className="button secondary" href={item.manual_check.site_url} target="_blank" rel="noopener noreferrer">공식 확인 사이트 <ExternalLink size={16} /></a>}
        </div>
        {isBusiness && item.detail && <details className="api-detail"><summary>공식 API 상세 정보</summary><pre>{JSON.stringify(item.detail, null, 2)}</pre></details>}
        {isBusiness && (
          <div className="manual-note">
            <strong>{official ? "공식 사이트 수동 확인" : "정확한 상세 원문 링크 미확인"}</strong>
            <p>{item.manual_check?.guide_text || "최종 제출 전 공식 원문과 첨부 공고문을 확인하세요."}</p>
            <label>공고/계획번호<input readOnly value={item.plan_no || item.bid_no || item.source_record_id || ""} onFocus={(event) => event.target.select()} /></label>
            <label>공고명<input readOnly value={item.title || ""} onFocus={(event) => event.target.select()} /></label>
            <label>검색 조합<input readOnly value={item.manual_check?.search_text || `${item.title || ""} ${item.organization || ""}`.trim()} onFocus={(event) => event.target.select()} /></label>
          </div>
        )}
      </article>
    </Layout>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/business" element={<BusinessListingPage />} />
      <Route path="/business/:id" element={<DetailPage type="business" />} />
      <Route path="/news" element={<NewsListingPage />} />
      <Route path="/news/:id" element={<DetailPage type="news" />} />
      <Route path="/companies" element={<CompanyListingPage />} />
      <Route path="/companies/:companyId" element={<CompanyDetailPage />} />
      <Route path="*" element={<Layout><div className="state"><Home size={22} />페이지를 찾을 수 없습니다.</div></Layout>} />
    </Routes>
  );
}
