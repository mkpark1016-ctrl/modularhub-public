import { useEffect, useMemo, useState } from "react";
import { ExternalLink, RotateCcw } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import {
  REVIEW_PAGE_SIZES,
  REVIEW_SORT_OPTIONS,
  REVIEW_STATUS_LABELS,
  filterReviewItems,
  formatReviewDate,
  getReviewFilterOptions,
  getReviewQueueKpis,
  getReviewSourceLabel,
  getReviewStatusLabel,
  isValidHttpUrl,
  normalizeReviewQueuePayload,
  paginateReviewItems,
  sortReviewItems,
} from "../../companyIntelligenceReviewQueue";

const DEFAULT_DATA_URL = "/data/company-intelligence/review-queue.json";
const DEFAULT_MANIFEST_URL = "/data/company-intelligence/manifest.json";
const DATA_URL = import.meta.env.VITE_COMPANY_INTELLIGENCE_DATA_URL || DEFAULT_DATA_URL;
const ALLOW_FIXTURE = import.meta.env.DEV || import.meta.env.MODE === "test";

function setQueryParam(searchParams, setSearchParams, key, value) {
  const next = new URLSearchParams(searchParams);
  if (!value) next.delete(key);
  else next.set(key, value);
  if (!["page", "pageSize"].includes(key)) next.delete("page");
  setSearchParams(next, { replace: true });
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function useReviewQueueData() {
  const [state, setState] = useState({ loading: true, error: "", notPublished: false, invalid: false, data: null });

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [queuePayload, manifestPayload] = await Promise.all([
          fetchJson(DATA_URL),
          fetchJson(DEFAULT_MANIFEST_URL).catch(() => null),
        ]);
        const normalized = normalizeReviewQueuePayload(queuePayload, manifestPayload);
        if (!normalized.valid) {
          if (active) setState({ loading: false, error: normalized.reason, notPublished: false, invalid: true, data: null });
          return;
        }
        if (active) setState({ loading: false, error: "", notPublished: false, invalid: false, data: normalized });
      } catch (error) {
        if (ALLOW_FIXTURE) {
          const fixture = await import("../../fixtures/company-intelligence-review-queue.json");
          const normalized = normalizeReviewQueuePayload(fixture.default);
          if (active) setState({ loading: false, error: "", notPublished: false, invalid: false, data: { ...normalized, fixture: true } });
          return;
        }
        if (active) {
          setState({
            loading: false,
            error: error.message || "데이터를 불러오지 못했습니다.",
            notPublished: error.status === 404,
            invalid: false,
            data: null,
          });
        }
      }
    }
    load();
    return () => {
      active = false;
    };
  }, []);

  return state;
}

function KpiCard({ label, value, helper, textValue = "" }) {
  return (
    <div className="monitor-kpi">
      <span>{label}</span>
      <strong>{textValue || Number(value || 0).toLocaleString("ko-KR")}</strong>
      {helper && <small>{helper}</small>}
    </div>
  );
}

function StatusBadge({ status }) {
  return <span className={`monitor-status ${status || "unknown"}`}>{getReviewStatusLabel(status)}</span>;
}

function SourceCounts({ kpis }) {
  const sourceCounts = kpis.sourceCounts || {};
  const rows = [
    ["dart", sourceCounts.dart || 0],
    ["naver_search", sourceCounts.naver_search || sourceCounts.naver || 0],
  ];
  return (
    <div className="source-status monitor-source-status">
      <p>Source 현황</p>
      <div>
        {rows.map(([source, count]) => (
          <span key={source}>{getReviewSourceLabel(source)} {Number(count || 0).toLocaleString("ko-KR")}건</span>
        ))}
      </div>
    </div>
  );
}

function ReviewFilters({ values, options, setParam, reset }) {
  return (
    <section className="monitor-controls" aria-label="기업 모니터링 필터">
      <label>
        기업
        <select value={values.company} onChange={(event) => setParam("company", event.target.value)}>
          <option value="">전체 기업</option>
          {options.companies.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      <label>
        Source
        <select value={values.source} onChange={(event) => setParam("source", event.target.value)}>
          <option value="">전체 Source</option>
          {options.sources.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      <label>
        상태
        <select value={values.status} onChange={(event) => setParam("status", event.target.value)}>
          <option value="">전체 상태</option>
          {Object.entries(REVIEW_STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label>
        게시일 시작
        <input type="date" value={values.startDate} onChange={(event) => setParam("start", event.target.value)} />
      </label>
      <label>
        게시일 종료
        <input type="date" value={values.endDate} onChange={(event) => setParam("end", event.target.value)} />
      </label>
      <label>
        검색어
        <input value={values.query} onChange={(event) => setParam("query", event.target.value)} placeholder="제목, 기업명, 키워드, Alias" />
      </label>
      <label>
        정렬
        <select value={values.sort} onChange={(event) => setParam("sort", event.target.value)}>
          {REVIEW_SORT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      <button type="button" className="reset-button" onClick={reset}><RotateCcw size={16} />필터 초기화</button>
    </section>
  );
}

function OriginalLink({ item }) {
  if (!isValidHttpUrl(item.originalUrl)) return <span className="monitor-link-disabled">원문 없음</span>;
  return (
    <a className="text-button" href={item.originalUrl} target="_blank" rel="noopener noreferrer">
      원문 <ExternalLink size={14} />
    </a>
  );
}

function ReviewTable({ items, onSelect }) {
  return (
    <div className="monitor-table-wrap">
      <table className="monitor-table">
        <thead>
          <tr>
            <th>상태</th>
            <th>기업</th>
            <th>제목</th>
            <th>Source</th>
            <th>게시일</th>
            <th>매칭 키워드</th>
            <th>원문</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.candidateId}>
              <td><StatusBadge status={item.status} /></td>
              <td>{item.companyName}</td>
              <td>
                <button type="button" className="monitor-title-button" onClick={() => onSelect(item)}>{item.title || "제목 없음"}</button>
              </td>
              <td>{getReviewSourceLabel(item.source)}</td>
              <td>{formatReviewDate(item.publishedAt)}</td>
              <td>{item.matchedKeyword || "확인되지 않음"}</td>
              <td><OriginalLink item={item} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReviewCards({ items, onSelect }) {
  return (
    <div className="monitor-card-list">
      {items.map((item) => (
        <article className="monitor-card" key={item.candidateId}>
          <div className="badge-row">
            <StatusBadge status={item.status} />
            <span>{item.companyName}</span>
            <span>{getReviewSourceLabel(item.source)}</span>
          </div>
          <button type="button" className="monitor-title-button" onClick={() => onSelect(item)}>{item.title || "제목 없음"}</button>
          <dl>
            <div><dt>게시일</dt><dd>{formatReviewDate(item.publishedAt)}</dd></div>
            <div><dt>매칭 키워드</dt><dd>{item.matchedKeyword || "확인되지 않음"}</dd></div>
          </dl>
          <OriginalLink item={item} />
        </article>
      ))}
    </div>
  );
}

function DetailPanel({ item, onClose }) {
  if (!item) return null;
  const rows = [
    ["후보 ID", item.candidateId],
    ["기업명", item.companyName],
    ["Source", getReviewSourceLabel(item.source)],
    ["상태", getReviewStatusLabel(item.status)],
    ["게시일", formatReviewDate(item.publishedAt)],
    ["수집일", formatReviewDate(item.collectedAt)],
    ["매칭 키워드", item.matchedKeyword],
    ["매칭 Alias", item.matchedAlias],
    ["매칭 사유", item.matchReason],
    ["중복 유형", item.duplicateType],
    ["duplicateOf", item.duplicateOf],
    ["제외 사유", item.rejectionReason],
  ];
  return (
    <aside className="monitor-detail-panel" aria-label="후보 상세 정보">
      <div className="comparison-panel-header">
        <div>
          <p className="eyebrow">READ ONLY DETAIL</p>
          <h2>{item.title || "제목 없음"}</h2>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="상세 닫기">×</button>
      </div>
      <dl className="detail-grid compact-detail-grid">
        {rows.map(([label, value]) => (
          <div key={label}><dt>{label}</dt><dd>{value || "확인되지 않음"}</dd></div>
        ))}
      </dl>
      <div className="detail-actions">
        <OriginalLink item={item} />
      </div>
    </aside>
  );
}

function Pagination({ page, pageCount, pageSize, setParam }) {
  return (
    <div className="monitor-pagination" aria-label="페이지 이동">
      <button type="button" className="text-button" disabled={page <= 1} onClick={() => setParam("page", String(page - 1))}>이전</button>
      <span>{page.toLocaleString("ko-KR")} / {pageCount.toLocaleString("ko-KR")}</span>
      <button type="button" className="text-button" disabled={page >= pageCount} onClick={() => setParam("page", String(page + 1))}>다음</button>
      <label>
        페이지 크기
        <select value={pageSize} onChange={(event) => setParam("pageSize", event.target.value)}>
          {REVIEW_PAGE_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}
        </select>
      </label>
    </div>
  );
}

export default function CompanyIntelligenceReviewQueuePage() {
  const { loading, error, notPublished, invalid, data } = useReviewQueueData();
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedCandidateId, setSelectedCandidateId] = useState("");
  const filters = useMemo(() => ({
    company: searchParams.get("company") || "",
    source: searchParams.get("source") || "",
    status: searchParams.get("status") || "pending",
    startDate: searchParams.get("start") || "",
    endDate: searchParams.get("end") || "",
    query: searchParams.get("query") || "",
    sort: searchParams.get("sort") || "published_desc",
    page: Number(searchParams.get("page") || 1),
    pageSize: Number(searchParams.get("pageSize") || 20),
  }), [searchParams]);
  const setParam = (key, value) => setQueryParam(searchParams, setSearchParams, key, value);
  const reset = () => setSearchParams({}, { replace: true });

  const items = useMemo(() => data?.items || [], [data?.items]);
  const options = useMemo(() => getReviewFilterOptions(items, data?.manifest), [data?.manifest, items]);
  const kpis = useMemo(() => getReviewQueueKpis(items, data?.manifest), [data?.manifest, items]);
  const filtered = useMemo(() => sortReviewItems(filterReviewItems(items, filters), filters.sort), [filters, items]);
  const page = paginateReviewItems(filtered, filters.page, filters.pageSize);
  const selectedItem = useMemo(
    () => items.find((item) => item.candidateId === selectedCandidateId) || null,
    [items, selectedCandidateId],
  );

  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">COMPANY MONITORING</p>
        <h1>기업 정보 검토 대기열</h1>
        <p>GitHub Actions가 수집한 DART·NAVER 후보를 운영 데이터와 분리해 읽기 전용으로 확인합니다.</p>
      </section>
      <div className="monitor-readonly-note">현재 화면은 수집 후보를 조회하는 읽기 전용 화면입니다. 승인, 반려, 운영 데이터 반영 기능은 아직 제공하지 않습니다.</div>

      {loading && <div className="state">기업 모니터링 데이터를 불러오는 중입니다.</div>}
      {notPublished && <div className="state">데이터가 아직 게시되지 않았습니다. 최신 수집 결과를 확인해주세요.</div>}
      {invalid && <div className="state error">기업 모니터링 데이터 Schema가 올바르지 않습니다. {error}</div>}
      {!loading && error && !notPublished && !invalid && <div className="state error">기업 모니터링 데이터를 불러오지 못했습니다. {error}</div>}

      {!loading && !error && data && (
        <section className="monitor-dashboard">
          {data.fixture && <div className="source-status">개발·테스트 Fixture 데이터가 표시되고 있습니다. Production에서는 Fixture fallback을 사용하지 않습니다.</div>}
          <section className="monitor-kpi-grid" aria-label="기업 모니터링 요약">
            <KpiCard label="전체 후보" value={kpis.total} />
            <KpiCard label="검토 대기" value={kpis.pending} />
            <KpiCard label="중복" value={kpis.duplicate} />
            <KpiCard label="품질 제외" value={kpis.qualityRejected} />
            <KpiCard label="마지막 생성" textValue={formatReviewDate(kpis.generatedAt)} />
          </section>
          <SourceCounts kpis={kpis} />
          <ReviewFilters values={filters} options={options} setParam={setParam} reset={reset} />
          {items.length === 0 && <div className="state">검토 후보가 없습니다.</div>}
          {items.length > 0 && filtered.length === 0 && <div className="state">현재 필터에 맞는 후보가 없습니다.</div>}
          {filtered.length > 0 && (
            <>
              <div className="monitor-result-summary">
                <span>필터 결과 {filtered.length.toLocaleString("ko-KR")}건</span>
                <span>기본 표시: 검토 대기 후보</span>
              </div>
              <ReviewTable items={page.items} onSelect={(item) => setSelectedCandidateId(item.candidateId)} />
              <ReviewCards items={page.items} onSelect={(item) => setSelectedCandidateId(item.candidateId)} />
              <Pagination page={page.page} pageCount={page.pageCount} pageSize={page.pageSize} setParam={setParam} />
            </>
          )}
          <DetailPanel item={selectedItem} onClose={() => setSelectedCandidateId("")} />
        </section>
      )}
    </>
  );
}
