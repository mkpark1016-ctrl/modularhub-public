import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  Building2,
  ExternalLink,
  FileText,
  Home,
  Newspaper,
  RotateCcw,
  Search,
} from "lucide-react";
import { Link, NavLink, Route, Routes, useParams } from "react-router-dom";

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

function parseDate(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
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
  return String(value || "").trim().toLowerCase();
}

function getBusinessStatus(item) {
  if (item.lifecycle_status) return item.lifecycle_status;
  if (item.opportunity_status) return item.opportunity_status;
  const due = parseDate(item.due_at || item.deadline_at);
  if (!due) return "unknown";
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return due >= today ? "active" : "closed";
}

function getBusinessStatusLabel(item) {
  const status = getBusinessStatus(item);
  if (status === "active") return "진행 중";
  if (status === "closed") return "마감";
  return "상태 미확인";
}

function getStatusRank(item) {
  const status = getBusinessStatus(item);
  if (status === "active") return 0;
  if (status === "unknown") return 1;
  return 2;
}

function getSortDate(item, field) {
  const date = parseDate(item[field]);
  return date ? date.getTime() : null;
}

function compareNullableDate(a, b, direction = "asc") {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return direction === "asc" ? a - b : b - a;
}

function compareBusinessItems(a, b) {
  const statusDelta = getStatusRank(a) - getStatusRank(b);
  if (statusDelta !== 0) return statusDelta;

  const status = getBusinessStatus(a);
  if (status === "active") {
    return compareNullableDate(getSortDate(a, "due_at") ?? getSortDate(a, "deadline_at"), getSortDate(b, "due_at") ?? getSortDate(b, "deadline_at"), "asc");
  }
  if (status === "closed") {
    return compareNullableDate(getSortDate(a, "due_at") ?? getSortDate(a, "deadline_at"), getSortDate(b, "due_at") ?? getSortDate(b, "deadline_at"), "desc");
  }
  return compareNullableDate(getSortDate(a, "posted_at"), getSortDate(b, "posted_at"), "desc");
}

function businessKind(item) {
  if (item.source_type === "public_agency_contest") return "민간사업자 공모";
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

function dDayLabel(item) {
  const status = getBusinessStatus(item);
  const explicit = Number(item.days_until_deadline);
  if (Number.isFinite(explicit)) {
    if (explicit === 0) return "D-Day";
    return explicit > 0 ? `D-${explicit}` : `마감 ${Math.abs(explicit)}일 경과`;
  }
  const due = parseDate(item.due_at || item.deadline_at);
  if (!due) return "";
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  due.setHours(0, 0, 0, 0);
  const diff = Math.round((due.getTime() - today.getTime()) / 86400000);
  if (diff === 0) return "D-Day";
  if (diff > 0) return `D-${diff}`;
  return status === "closed" ? `마감 ${Math.abs(diff)}일 경과` : "";
}

function hasUpcomingDeadline(item) {
  return getBusinessStatus(item) === "active" && Number(item.days_until_deadline) >= 0 && Number(item.days_until_deadline) <= 7;
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

function Layout({ children }) {
  return (
    <div className="site-shell">
      <header className="topbar">
        <Link className="brand" to="/">ModularHub</Link>
        <nav aria-label="주요 메뉴">
          <NavLink to="/business"><Building2 size={17} />사업정보</NavLink>
          <NavLink to="/news"><Newspaper size={17} />뉴스정보</NavLink>
        </nav>
      </header>
      <main>{children}</main>
      <footer>공식 OpenAPI와 기관 홈페이지, 뉴스 검색 결과를 정리한 정보 서비스입니다. 최종 판단 전 원문을 확인하세요.</footer>
    </div>
  );
}

function HomePage() {
  const { data } = useDataset("meta");
  return (
    <Layout>
      <section className="intro">
        <p className="eyebrow">모듈러 건축 정보 플랫폼</p>
        <h1>사업기회와 시장 뉴스를<br />한 흐름으로 확인하세요</h1>
        <p>나라장터와 공공기관 공모, 네이버 뉴스 원문을 정리해 모듈러 관련 영업 정보를 빠르게 확인할 수 있습니다.</p>
        <div className="intro-actions">
          <Link className="button primary" to="/business">사업정보 보기</Link>
          <Link className="button secondary" to="/news">뉴스정보 보기</Link>
        </div>
      </section>
      <section className="category-grid" aria-label="서비스 카테고리">
        <Link className="category-panel" to="/business">
          <Building2 size={26} />
          <div><strong>사업정보</strong><span>입찰공고, 발주계획, 공공기관 민간사업자 공모</span></div>
          <b>{data?.business_count ?? "-"}건</b>
        </Link>
        <Link className="category-panel" to="/news">
          <Newspaper size={26} />
          <div><strong>뉴스정보</strong><span>모듈러 산업, 정책, 기업 뉴스 원문</span></div>
          <b>{data?.news_count ?? "-"}건</b>
        </Link>
      </section>
      <div className="public-data-note">
        <strong>누적 검증 데이터 기준</strong>
        <span>데이터 갱신: {data?.generated_at ? formatDate(data.generated_at) : "확인 중"}</span>
        {data?.workflow_last_run_status === "warning" && <p>일부 수집원은 일시적으로 제외되었고 기존 검증 데이터를 유지했습니다.</p>}
      </div>
    </Layout>
  );
}

function SearchBar({ value, onChange, placeholder }) {
  return (
    <label className="search">
      <Search size={18} />
      <input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} />
    </label>
  );
}

function SummaryItem({ label, value }) {
  return (
    <div className="summary-chip">
      <span>{label}</span>
      <strong>{value.toLocaleString("ko-KR")}건</strong>
    </div>
  );
}

function BusinessCard({ item }) {
  const kind = businessKind(item);
  const status = getBusinessStatus(item);
  const statusLabel = getBusinessStatusLabel(item);
  const agency = displayAgency(item);
  const dDay = dDayLabel(item);
  const isContest = item.source_type === "public_agency_contest";
  const noticeStatus = displayNoticeStatus(item);
  const modularLabel = item.modular_relevance === "confirmed" ? "모듈러 명시" : (
    item.modular_relevance === "review_candidate" ? "모듈러 적용 검토 대상" : ""
  );
  const location = projectLocation(item);
  const attachments = attachmentCount(item);
  const official = originalUrl(item);

  return (
    <article className={`result-card ${isContest ? "contest-card" : ""} status-${status}`}>
      <div className="badge-row">
        <span>{agency}</span>
        <span>{kind}</span>
        <span className={`status-badge ${status}`}>{statusLabel}</span>
        {item.business_type && !isContest && <span>{item.business_type}</span>}
        {noticeStatus && <span>{noticeStatus}</span>}
        {modularLabel && <span>{modularLabel}</span>}
        {item.is_known_important && <span className="important">중요공고</span>}
      </div>
      <h2><Link to={`/business/${item.id}`}>{item.title}</Link></h2>
      {isContest && (
        <p className="contest-subline">{location || item.organization || "대상지구는 공고문 확인 필요"}</p>
      )}
      <dl className="metadata">
        <div><dt>기관</dt><dd>{item.organization || agency}</dd></div>
        <div><dt>게시일</dt><dd>{formatDate(item.posted_at)}</dd></div>
        <div><dt>마감일</dt><dd>{formatDate(item.due_at || item.deadline_at)}</dd></div>
        <div><dt>{isContest ? "D-Day" : "금액"}</dt><dd>{isContest ? (dDay || "일정 확인 필요") : formatAmount(item.amount)}</dd></div>
      </dl>
      {isContest && (
        <div className="contest-extra">
          {attachments > 0 && <span><FileText size={14} />첨부파일 {attachments}개</span>}
          {!attachments && <span>첨부파일 정보 없음</span>}
          <span>{item.source_record_id ? `원문 ID ${item.source_record_id}` : "원문 ID 확인 필요"}</span>
        </div>
      )}
      <div className="card-footer">
        <span>{item.source_record_id || item.plan_no || item.bid_no || "출처번호 미확인"}</span>
        <div className="card-actions">
          <Link to={`/business/${item.id}`}>상세보기</Link>
          {official && isOfficialLinkEnabled(item) && <a href={official} target="_blank" rel="noreferrer">공식 원문</a>}
        </div>
      </div>
    </article>
  );
}

function NewsCard({ item }) {
  return (
    <article className="result-card news-card">
      <div className="badge-row"><span>뉴스</span><span>{formatDate(item.published_at)}</span></div>
      <h2><Link to={`/news/${item.id}`}>{item.title}</Link></h2>
      <p>{item.summary || "요약이 없습니다."}</p>
      <div className="card-footer">
        <span>{item.media || item.source || "네이버뉴스"}</span>
        <div className="card-actions">
          <a href={item.original_url} target="_blank" rel="noreferrer">원문 보기</a>
          <Link to={`/news/${item.id}`}>상세보기</Link>
        </div>
      </div>
    </article>
  );
}

function BusinessFilters({ query, setQuery, typeFilter, setTypeFilter, agencyFilter, setAgencyFilter, statusFilter, setStatusFilter, filteredCount, onReset }) {
  return (
    <aside className="filters">
      <div className="filter-heading">
        <h2>검색 조건</h2>
        <button type="button" className="icon-button" onClick={onReset} aria-label="필터 초기화" title="필터 초기화">
          <RotateCcw size={16} />
        </button>
      </div>
      <SearchBar value={query} onChange={setQuery} placeholder="공고명, 기관, 공고번호, 지역" />
      <label>사업 유형
        <select aria-label="사업 유형" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
          {TYPE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      <label>기관
        <select aria-label="기관" value={agencyFilter} onChange={(event) => setAgencyFilter(event.target.value)}>
          {AGENCY_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      <label>진행 상태
        <select aria-label="진행 상태" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
          {STATUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      <button type="button" className="reset-button" onClick={onReset}>필터 초기화</button>
      <p className="filter-note">검색 결과 {filteredCount.toLocaleString("ko-KR")}건</p>
    </aside>
  );
}

function NewsFilters({ query, setQuery, source, setSource, sources, newsDays, setNewsDays, filteredCount }) {
  return (
    <aside className="filters">
      <h2>검색 조건</h2>
      <SearchBar value={query} onChange={setQuery} placeholder="뉴스 제목, 요약" />
      <label>출처
        <select aria-label="출처" value={source} onChange={(event) => setSource(event.target.value)}>
          {sources.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
      </label>
      <label>기간
        <select aria-label="기간" value={newsDays} onChange={(event) => setNewsDays(event.target.value)}>
          <option>전체</option>
          <option value="7">최근 7일</option>
          <option value="30">최근 30일</option>
          <option value="90">최근 90일</option>
        </select>
      </label>
      <p className="filter-note">검색 결과 {filteredCount.toLocaleString("ko-KR")}건</p>
    </aside>
  );
}

function ListingPage({ type }) {
  const isBusiness = type === "business";
  const { loading, error, data } = useDataset(type);
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("전체");
  const [newsDays, setNewsDays] = useState("전체");
  const [typeFilter, setTypeFilter] = useState("all");
  const [agencyFilter, setAgencyFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const items = getItems(data);

  const businessSummary = useMemo(() => {
    if (!isBusiness) return null;
    return {
      total: items.length,
      active: items.filter((item) => getBusinessStatus(item) === "active").length,
      closed: items.filter((item) => getBusinessStatus(item) === "closed").length,
      unknown: items.filter((item) => getBusinessStatus(item) === "unknown").length,
      urgent: items.filter(hasUpcomingDeadline).length,
      procurementPlan: items.filter((item) => item.source_type === "procurement_plan").length,
      contest: items.filter((item) => item.source_type === "public_agency_contest").length,
    };
  }, [isBusiness, items]);

  const sources = useMemo(() => ["전체", ...new Set(items.map((item) => item.media || item.source || item.source_name).filter(Boolean))], [items]);

  const filtered = useMemo(() => {
    const queryText = normalizeText(query);
    return items.filter((item) => {
      if (isBusiness) {
        const selectedType = TYPE_OPTIONS.find((option) => option.value === typeFilter)?.sourceType;
        const typeMatches = !selectedType || item.source_type === selectedType;
        const agencyMatches = agencyFilter === "all" || agencyFilterValue(item) === agencyFilter;
        const statusMatches = statusFilter === "all" || getBusinessStatus(item) === statusFilter;
        const searchMatches = !queryText || getSearchText(item).includes(queryText);
        return typeMatches && agencyMatches && statusMatches && searchMatches;
      }

      const text = `${item.title || ""} ${item.media || ""} ${item.source || ""} ${item.summary || ""}`.toLowerCase();
      const sourceMatches = source === "전체" || item.media === source || item.source === source;
      let dateMatches = true;
      if (newsDays !== "전체") {
        const published = parseDate(item.published_at);
        const threshold = new Date();
        threshold.setDate(threshold.getDate() - Number(newsDays));
        dateMatches = Boolean(published) && published >= threshold;
      }
      return (!queryText || text.includes(queryText)) && sourceMatches && dateMatches;
    }).sort((a, b) => (isBusiness ? compareBusinessItems(a, b) : 0));
  }, [agencyFilter, isBusiness, items, newsDays, query, source, statusFilter, typeFilter]);

  function resetBusinessFilters() {
    setQuery("");
    setTypeFilter("all");
    setAgencyFilter("all");
    setStatusFilter("all");
  }

  let emptyMessage = "조건에 맞는 사업정보가 없습니다.";
  if (isBusiness && agencyFilter === "SH") {
    emptyMessage = "현재 공개 가능한 SH 민간사업자 공모가 없습니다. SH 수집기는 정상 모니터링 중입니다.";
  }

  return (
    <Layout>
      <section className="page-heading">
        <p className="eyebrow">{isBusiness ? "BUSINESS" : "NEWS"}</p>
        <h1>{isBusiness ? "모듈러 사업정보" : "모듈러 뉴스정보"}</h1>
        <p>{isBusiness ? "입찰공고, 발주계획, 공공기관 공모를 한 화면에서 구분해 확인합니다." : "원문 링크가 확인된 모듈러 관련 뉴스를 제공합니다."}</p>
      </section>
      {isBusiness && businessSummary && (
        <section className="summary-strip" aria-label="사업정보 요약">
          <SummaryItem label="전체" value={businessSummary.total} />
          <SummaryItem label="진행 중" value={businessSummary.active} />
          <SummaryItem label="마감 임박" value={businessSummary.urgent} />
          <SummaryItem label="발주계획" value={businessSummary.procurementPlan} />
          <SummaryItem label="공공기관 공모" value={businessSummary.contest} />
        </section>
      )}
      <div className="content-layout">
        {isBusiness ? (
          <BusinessFilters
            query={query}
            setQuery={setQuery}
            typeFilter={typeFilter}
            setTypeFilter={setTypeFilter}
            agencyFilter={agencyFilter}
            setAgencyFilter={setAgencyFilter}
            statusFilter={statusFilter}
            setStatusFilter={setStatusFilter}
            filteredCount={filtered.length}
            onReset={resetBusinessFilters}
          />
        ) : (
          <NewsFilters
            query={query}
            setQuery={setQuery}
            source={source}
            setSource={setSource}
            sources={sources}
            newsDays={newsDays}
            setNewsDays={setNewsDays}
            filteredCount={filtered.length}
          />
        )}
        <section className="results" aria-live="polite">
          {isBusiness && businessSummary && (
            <div className="source-status lifecycle-summary">
              <p>전체 {businessSummary.total.toLocaleString("ko-KR")}건 · 진행 중 {businessSummary.active}건 · 마감 {businessSummary.closed}건 · 상태 미확인 {businessSummary.unknown}건</p>
            </div>
          )}
          {loading && <div className="state">데이터를 불러오는 중입니다.</div>}
          {error && <div className="state error">{error}</div>}
          {!loading && !error && filtered.length === 0 && <div className="state">{isBusiness ? emptyMessage : "조건에 맞는 뉴스가 없습니다."}</div>}
          {filtered.map((item) => (isBusiness ? <BusinessCard key={item.id} item={item} /> : <NewsCard key={item.id} item={item} />))}
        </section>
      </div>
    </Layout>
  );
}

function DetailPage({ type }) {
  const { id } = useParams();
  const isBusiness = type === "business";
  const { loading, error, data } = useDataset(type);
  const item = getItems(data).find((entry) => String(entry.id) === String(id));
  if (loading) return <Layout><div className="state">상세정보를 불러오는 중입니다.</div></Layout>;
  if (error || !item) return <Layout><div className="state error">해당 정보를 찾을 수 없습니다.</div></Layout>;

  const official = isBusiness ? originalUrl(item) : item.original_url;
  const isContest = isBusiness && item.source_type === "public_agency_contest";
  const status = isBusiness ? getBusinessStatus(item) : "";
  const noticeStatus = isBusiness ? displayNoticeStatus(item) : "";
  const attachments = Array.isArray(item.attachments) ? item.attachments : [];
  const modularLabel = item.modular_relevance === "confirmed" ? "모듈러 명시" : (
    item.modular_relevance === "review_candidate" ? "모듈러 적용 검토 대상" : ""
  );

  return (
    <Layout>
      <article className="detail-page">
        <Link className="back" to={`/${type}`}><ArrowLeft size={17} />목록으로</Link>
        <div className="badge-row">
          <span>{isBusiness ? displayAgency(item) : item.media || item.source || "뉴스"}</span>
          <span>{isBusiness ? businessKind(item) : "뉴스"}</span>
          {isBusiness && <span className={`status-badge ${status}`}>{getBusinessStatusLabel(item)}</span>}
          {isBusiness && noticeStatus && <span>{noticeStatus}</span>}
        </div>
        <h1>{item.title}</h1>
        <dl className="detail-grid">
          <div><dt>기관</dt><dd>{(isBusiness ? item.organization : item.media) || "-"}</dd></div>
          <div><dt>게시일</dt><dd>{formatDate(isBusiness ? item.posted_at : item.published_at)}</dd></div>
          <div><dt>{isBusiness ? "마감일" : "출처"}</dt><dd>{isBusiness ? formatDate(item.due_at || item.deadline_at) : (item.source || "네이버뉴스")}</dd></div>
          {isBusiness && <div><dt>수요기관</dt><dd>{item.demand_org || "-"}</dd></div>}
          {isBusiness && <div><dt>업무구분</dt><dd>{[item.business_type, item.business_subtype].filter(Boolean).join(" / ") || "-"}</dd></div>}
          {isBusiness && <div><dt>금액</dt><dd>{formatAmount(item.amount)}</dd></div>}
          {isBusiness && <div><dt>공고/판단/계획번호</dt><dd>{item.source_record_id || item.plan_no || item.bid_no || "-"}</dd></div>}
          {isBusiness && <div><dt>진행 상태</dt><dd>{getBusinessStatusLabel(item)}</dd></div>}
          {isContest && <div><dt>대상지구/블록</dt><dd>{projectLocation(item) || "공고문 확인 필요"}</dd></div>}
          {isContest && <div><dt>모듈러 관련성</dt><dd>{modularLabel || "확인 필요"}</dd></div>}
        </dl>
        <section className="summary"><h2>내용</h2><p>{item.summary || "상세 요약이 없습니다."}</p></section>
        {isContest && <section className="summary"><h2>공모 일정</h2><p>{item.application_schedule_text || "공모 일정은 첨부 공고문 확인"}</p></section>}
        {isContest && attachments.length > 0 && (
          <section className="summary">
            <h2>첨부파일</h2>
            <ul className="attachment-list">
              {attachments.map((file) => <li key={`${file.url}-${file.name}`}><a href={file.url} target="_blank" rel="noreferrer">{file.name || "첨부파일"}{file.file_type ? ` (${file.file_type})` : ""}</a></li>)}
            </ul>
          </section>
        )}
        <div className="detail-actions">
          {official && <a className="button primary" href={official} target="_blank" rel="noreferrer">{isContest ? "공식 원문" : "원문 열기"} <ExternalLink size={16} /></a>}
          {isBusiness && item.manual_check?.site_url && <a className="button secondary" href={item.manual_check.site_url} target="_blank" rel="noreferrer">공식 확인 사이트 <ExternalLink size={16} /></a>}
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
      <Route path="/business" element={<ListingPage type="business" />} />
      <Route path="/business/:id" element={<DetailPage type="business" />} />
      <Route path="/news" element={<ListingPage type="news" />} />
      <Route path="/news/:id" element={<DetailPage type="news" />} />
      <Route path="*" element={<Layout><div className="state"><Home size={22} />페이지를 찾을 수 없습니다.</div></Layout>} />
    </Routes>
  );
}
