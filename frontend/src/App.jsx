import { useEffect, useState } from "react";
import { ArrowLeft, Building2, ExternalLink, Home, Newspaper, Search } from "lucide-react";
import { Link, NavLink, Route, Routes, useParams } from "react-router-dom";

const DATA_BASE = import.meta.env.VITE_DATA_BASE_URL || "/data";

function useDataset(name) {
  const [state, setState] = useState({ loading: true, error: "", data: null });
  useEffect(() => {
    let active = true;
    fetch(`${DATA_BASE}/${name}.json`)
      .then((response) => {
        if (!response.ok) throw new Error(`데이터를 불러오지 못했습니다 (${response.status})`);
        return response.json();
      })
      .then((data) => active && setState({ loading: false, error: "", data }))
      .catch((error) => active && setState({ loading: false, error: error.message, data: null }));
    return () => { active = false; };
  }, [name]);
  return state;
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value).slice(0, 10) : new Intl.DateTimeFormat("ko-KR").format(date);
}

function formatAmount(value) {
  const amount = Number(value);
  return Number.isFinite(amount) && amount > 0 ? `${new Intl.NumberFormat("ko-KR").format(amount)}원` : "금액 미공개";
}

function displaySource(value) {
  return value === "D2B" ? "국방조달" : value;
}

function businessKind(item) {
  return item.source_type === "procurement_plan" ? "발주계획" : "입찰공고";
}

function sourceTypeForKind(kind) {
  if (kind === "입찰공고") return "bid";
  if (kind === "발주계획") return "procurement_plan";
  return "";
}

function isOpenBusiness(item) {
  if (!item.due_at) return false;
  const due = new Date(item.due_at);
  return !Number.isNaN(due.getTime()) && due >= new Date(new Date().toDateString());
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
      <footer>공식 OpenAPI와 뉴스 검색 결과를 정리한 정보 서비스입니다. 최종 판단 전 출처를 확인하세요.</footer>
    </div>
  );
}

function HomePage() {
  const { data } = useDataset("meta");
  return (
    <Layout>
      <section className="intro">
        <p className="eyebrow">모듈러 건축 정보 플랫폼</p>
        <h1>사업기회와 시장 뉴스를<br />한 흐름으로 확인하세요.</h1>
        <p>나라장터와 D2B의 모듈러 사업정보, 네이버 뉴스 원문을 한곳에 정리합니다.</p>
        <div className="intro-actions">
          <Link className="button primary" to="/business">사업정보 보기</Link>
          <Link className="button secondary" to="/news">뉴스정보 보기</Link>
        </div>
      </section>
      <section className="category-grid" aria-label="서비스 카테고리">
        <Link className="category-panel" to="/business">
          <Building2 size={26} />
          <div><strong>사업정보</strong><span>나라장터 입찰, D2B 입찰·조달계획</span></div>
          <b>{data?.business_count ?? "-"}건</b>
        </Link>
        <Link className="category-panel" to="/news">
          <Newspaper size={26} />
          <div><strong>뉴스정보</strong><span>모듈러 산업·정책·기업 뉴스 원문</span></div>
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
  return <label className="search"><Search size={18} /><input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} /></label>;
}

function BusinessCard({ item }) {
  const kind = businessKind(item);
  return (
    <article className="result-card">
      <div className="badge-row"><span>{displaySource(item.source)}</span><span>{kind}</span>{item.business_type && <span>{item.business_type}</span>}{item.notice_status && <span>{item.notice_status}</span>}{item.is_known_important && <span className="important">중요공고</span>}</div>
      <h2><Link to={`/business/${item.id}`}>{item.title}</Link></h2>
      <dl className="metadata"><div><dt>기관</dt><dd>{item.organization || "-"}</dd></div><div><dt>게시일</dt><dd>{formatDate(item.posted_at)}</dd></div><div><dt>마감일</dt><dd>{formatDate(item.due_at)}</dd></div><div><dt>금액</dt><dd>{formatAmount(item.amount)}</dd></div></dl>
      <div className="card-footer"><span>{item.plan_no || item.bid_no || "출처번호 미확인"}</span><Link to={`/business/${item.id}`}>상세보기</Link></div>
    </article>
  );
}

function NewsCard({ item }) {
  return (
    <article className="result-card news-card">
      <div className="badge-row"><span>뉴스</span><span>{formatDate(item.published_at)}</span></div>
      <h2><Link to={`/news/${item.id}`}>{item.title}</Link></h2>
      <p>{item.summary || "요약이 없습니다."}</p>
      <div className="card-footer"><span>{item.media || item.source || "네이버뉴스"}</span><div className="card-actions"><a href={item.original_url} target="_blank" rel="noreferrer">원문 보기</a><Link to={`/news/${item.id}`}>상세보기</Link></div></div>
    </article>
  );
}

function ListingPage({ type }) {
  const isBusiness = type === "business";
  const { loading, error, data } = useDataset(type);
  const { data: meta } = useDataset("meta");
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("전체");
  const [kind, setKind] = useState("전체");
  const [openOnly, setOpenOnly] = useState(false);
  const [newsDays, setNewsDays] = useState("전체");
  const items = data?.items || [];
  const selectedSourceType = sourceTypeForKind(kind);
  const procurementPlanCount = items.filter((item) => item.source_type === "procurement_plan").length;
  const procurementPlanStatus = data?.procurement_plan_collection_status || meta?.procurement_plan_collection_status;
  const g2bOrderPlanStatus = data?.g2b_order_plan_status || meta?.g2b_order_plan_status;
  const g2bOrderPlanMessage = data?.g2b_order_plan_message || meta?.g2b_order_plan_message;
  const sources = ["전체", ...new Set(items.map((item) => item.source).filter(Boolean))];
  const filtered = items.filter((item) => {
    const text = `${item.title || ""} ${item.organization || item.media || ""} ${item.summary || ""} ${item.plan_no || ""} ${item.bid_no || ""}`.toLowerCase();
    const sourceMatches = source === "전체" || item.source === source;
    const kindMatches = !isBusiness || !selectedSourceType || item.source_type === selectedSourceType;
    const openMatches = !isBusiness || !openOnly || isOpenBusiness(item);
    let dateMatches = true;
    if (!isBusiness && newsDays !== "전체") {
      const published = new Date(item.published_at);
      const threshold = new Date();
      threshold.setDate(threshold.getDate() - Number(newsDays));
      dateMatches = !Number.isNaN(published.getTime()) && published >= threshold;
    }
    return (!query || text.includes(query.toLowerCase())) && sourceMatches && kindMatches && openMatches && dateMatches;
  });
  let emptyMessage = "조건에 맞는 정보가 없습니다.";
  if (isBusiness && kind === "발주계획") {
    if (procurementPlanCount === 0 && g2bOrderPlanStatus === "failed") {
      emptyMessage = "나라장터 발주계획 API 호출에 실패했습니다. 활용신청/인증키/endpoint를 확인하세요.";
    } else if (procurementPlanCount === 0 && g2bOrderPlanStatus === "success_no_match") {
      emptyMessage = "현재 조회기간 내 모듈러 발주계획 데이터가 없습니다.";
    } else if (procurementPlanCount === 0 && ["not_collected", undefined].includes(procurementPlanStatus)) {
      emptyMessage = "발주계획 수집 데이터가 아직 생성되지 않았습니다.";
    } else if (procurementPlanCount === 0 && ["failed", "partial_warning"].includes(procurementPlanStatus)) {
      emptyMessage = "발주계획 수집 중 일부 출처에 오류가 발생했습니다. 최신 수집 상태를 확인한 뒤 다시 시도해 주세요.";
    } else if (procurementPlanCount === 0) {
      emptyMessage = "현재 조회기간 내 모듈러 발주계획 데이터가 없습니다. 입찰공고는 발주계획 없이도 등록될 수 있으므로 입찰공고도 함께 확인하세요.";
    } else {
      emptyMessage = "선택한 조건에 맞는 발주계획이 없습니다. 출처 또는 검색어를 넓혀보세요.";
    }
  }
  return (
    <Layout>
      <section className="page-heading"><p className="eyebrow">{isBusiness ? "BUSINESS" : "NEWS"}</p><h1>{isBusiness ? "모듈러 사업정보" : "모듈러 뉴스정보"}</h1><p>{isBusiness ? "나라장터와 D2B에서 공고명 또는 사업명에 모듈러가 포함된 정보를 제공합니다." : "원문 링크가 확인된 모듈러 관련 뉴스를 제공합니다."}</p></section>
      <div className="content-layout">
        <aside className="filters"><h2>검색 조건</h2><SearchBar value={query} onChange={setQuery} placeholder={isBusiness ? "공고명, 기관, 공고번호" : "뉴스 제목, 요약"} /><label>출처<select value={source} onChange={(event) => setSource(event.target.value)}>{sources.map((name) => <option key={name} value={name}>{displaySource(name)}</option>)}</select></label>{isBusiness ? <><label>유형<select value={kind} onChange={(event) => setKind(event.target.value)}><option>전체</option><option>입찰공고</option><option>발주계획</option></select></label><label className="check-row"><input type="checkbox" checked={openOnly} onChange={(event) => setOpenOnly(event.target.checked)} />마감 전 공고만</label></> : <label>기간<select value={newsDays} onChange={(event) => setNewsDays(event.target.value)}><option>전체</option><option value="7">최근 7일</option><option value="30">최근 30일</option><option value="90">최근 90일</option></select></label>}<p className="filter-note">총 {filtered.length}건</p></aside>
        <section className="results" aria-live="polite">
          {isBusiness && kind === "발주계획" && !loading && !error && <div className="source-status">
            <p><strong>나라장터</strong> {g2bOrderPlanMessage || "발주계획 수집 상태를 확인 중입니다."}</p>
            {meta?.workflow_last_run_status === "warning" && <p>일부 수집원은 일시적으로 제외되었으며 기존 검증 데이터는 유지됩니다.</p>}
          </div>}
          {loading && <div className="state">데이터를 불러오는 중입니다.</div>}
          {error && <div className="state error">{error}</div>}
          {!loading && !error && filtered.length === 0 && <div className="state">{emptyMessage}</div>}
          {filtered.map((item) => isBusiness ? <BusinessCard key={item.id} item={item} /> : <NewsCard key={item.id} item={item} />)}
        </section>
      </div>
    </Layout>
  );
}

function DetailPage({ type }) {
  const { id } = useParams();
  const isBusiness = type === "business";
  const { loading, error, data } = useDataset(type);
  const item = data?.items?.find((entry) => String(entry.id) === String(id));
  if (loading) return <Layout><div className="state">상세정보를 불러오는 중입니다.</div></Layout>;
  if (error || !item) return <Layout><div className="state error">해당 정보를 찾을 수 없습니다.</div></Layout>;
  const originalUrl = isBusiness ? item.external_original_url : item.original_url;
  const manualUrl = item.manual_check?.site_url;
  return (
    <Layout>
      <article className="detail-page">
        <Link className="back" to={`/${type}`}><ArrowLeft size={17} />목록으로</Link>
        <div className="badge-row"><span>{displaySource(item.source)}</span><span>{isBusiness ? businessKind(item) : "뉴스"}</span>{isBusiness && item.notice_status && <span>{item.notice_status}</span>}</div>
        <h1>{item.title}</h1>
        <dl className="detail-grid"><div><dt>기관</dt><dd>{(isBusiness ? item.organization : item.media) || "-"}</dd></div><div><dt>게시일</dt><dd>{formatDate(isBusiness ? item.posted_at : item.published_at)}</dd></div><div><dt>{isBusiness ? "마감일" : "출처"}</dt><dd>{isBusiness ? formatDate(item.due_at) : (item.source || "네이버뉴스")}</dd></div>{isBusiness && <div><dt>수요기관</dt><dd>{item.demand_org || "-"}</dd></div>}{isBusiness && <div><dt>업무구분</dt><dd>{[item.business_type, item.business_subtype].filter(Boolean).join(" / ") || "-"}</dd></div>}{isBusiness && <div><dt>금액</dt><dd>{formatAmount(item.amount)}</dd></div>}{isBusiness && <div><dt>공고/판단/계획번호</dt><dd>{item.plan_no || item.bid_no || "-"}</dd></div>}{isBusiness && <div><dt>공고차수</dt><dd>{item.bid_order || "-"}</dd></div>}{isBusiness && <div><dt>공고상태</dt><dd>{item.notice_status || "-"}</dd></div>}</dl>
        <section className="summary"><h2>내용</h2><p>{item.summary || "상세 요약이 없습니다."}</p></section>
        <div className="detail-actions">
          {originalUrl && <a className="button primary" href={originalUrl} target="_blank" rel="noreferrer">원문 열기 <ExternalLink size={16} /></a>}
          {isBusiness && manualUrl && <a className="button secondary" href={manualUrl} target="_blank" rel="noreferrer">공식 확인 사이트 <ExternalLink size={16} /></a>}
        </div>
        {isBusiness && item.detail && <details className="api-detail"><summary>공식 API 상세 정보</summary><pre>{JSON.stringify(item.detail, null, 2)}</pre></details>}
        {isBusiness && <div className="manual-note"><strong>{originalUrl ? "공식 사이트 수동 확인" : "정확한 상세 원문 링크 미확인"}</strong><p>{item.manual_check?.guide_text}</p><label>공고/계획번호<input readOnly value={item.plan_no || item.bid_no || ""} onFocus={(event) => event.target.select()} /></label><label>공고명<input readOnly value={item.title || ""} onFocus={(event) => event.target.select()} /></label><label>검색 조합<input readOnly value={item.manual_check?.search_text || ""} onFocus={(event) => event.target.select()} /></label></div>}
      </article>
    </Layout>
  );
}

export default function App() {
  return <Routes><Route path="/" element={<HomePage />} /><Route path="/business" element={<ListingPage type="business" />} /><Route path="/business/:id" element={<DetailPage type="business" />} /><Route path="/news" element={<ListingPage type="news" />} /><Route path="/news/:id" element={<DetailPage type="news" />} /><Route path="*" element={<Layout><div className="state"><Home size={22} />페이지를 찾을 수 없습니다.</div></Layout>} /></Routes>;
}
