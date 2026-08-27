import { useMemo, useState } from "react";
import { detailModel, formatDate, labelValue } from "./companyDetailHelpers";
import { buildCompanyItemEvidence } from "../../companyEvidence";
import {
  filterTechnologyItems,
  formatPatentClassification,
  isKiprisLinkedTechnology,
  isPatentClassificationCode,
  resolvedTechnologySources,
  technologyField,
  technologyFieldDistribution,
  technologyOverview,
  technologyPrimaryNumber,
} from "../../technologyDashboard";
import CompanyEntityDrawer from "./CompanyEntityDrawer";

const PAGE_SIZE = 8;

function technologyDate(item, key) {
  return key === "filed"
    ? formatDate(item.application_date || item.filed_at || item.filed_date)
    : formatDate(item.registration_date || item.registered_at);
}

function TechnologyDetail({ company, item, onShowEvidence }) {
  const primaryNumber = technologyPrimaryNumber(item);
  const title = item.name || primaryNumber.value;
  const humanField = technologyField(item);
  const classification = isPatentClassificationCode(item.technology_area)
    ? formatPatentClassification(item.technology_area)
    : "";
  return (
    <dl className="detail-grid compact-detail-grid">
      <div><dt>유형</dt><dd>{labelValue(item.record_type || item.group, "확인되지 않음")}</dd></div>
      <div><dt>상태</dt><dd>{labelValue(item.status, "확인되지 않음")}</dd></div>
      {item.registration_number && <div><dt>등록번호</dt><dd className="technical-token">{item.registration_number}</dd></div>}
      {item.application_number && <div><dt>출원번호</dt><dd className="technical-token">{item.application_number}</dd></div>}
      {item.patent_number && <div><dt>특허번호</dt><dd className="technical-token">{item.patent_number}</dd></div>}
      <div><dt>기술 분야</dt><dd>{humanField}</dd></div>
      {classification && classification !== humanField && <div><dt>IPC/CPC 분류</dt><dd className="technical-token">{classification}</dd></div>}
      <div><dt>출원일</dt><dd>{technologyDate(item, "filed")}</dd></div>
      <div><dt>등록일</dt><dd>{technologyDate(item, "registered")}</dd></div>
      {item.summary && <div className="technology-detail-summary"><dt>기술 효과 · 상세 내용</dt><dd>{item.summary}</dd></div>}
      {onShowEvidence && (
        <div><dt>근거</dt><dd><button type="button" className="text-button evidence-inline-button" onClick={() => onShowEvidence(buildCompanyItemEvidence(company, title, primaryNumber.value, item.source_ids, humanField))}>근거보기</button></dd></div>
      )}
    </dl>
  );
}

export default function CompanyTechnologyTab({ company, onShowEvidence }) {
  const model = detailModel(company);
  const items = model.technologyItems;
  const [query, setQuery] = useState("");
  const [recordType, setRecordType] = useState("all");
  const [status, setStatus] = useState("all");
  const [field, setField] = useState("all");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [selectedTechnology, setSelectedTechnology] = useState(null);

  const recordTypes = useMemo(() => [...new Set(items.map((item) => item.record_type || item.group).filter(Boolean))], [items]);
  const statuses = useMemo(() => [...new Set(items.map((item) => item.status).filter(Boolean))], [items]);
  const overview = useMemo(() => technologyOverview(company, items), [company, items]);
  const fieldDistribution = useMemo(() => technologyFieldDistribution(items), [items]);
  const filtered = useMemo(() => filterTechnologyItems(items, {
    query,
    recordType,
    status,
    field,
  }), [field, items, query, recordType, status]);
  const visible = filtered.slice(0, visibleCount);

  const resetPaging = (setter) => (value) => {
    setter(value);
    setVisibleCount(PAGE_SIZE);
  };
  const showEvidenceFromDrawer = (evidence) => {
    setSelectedTechnology(null);
    window.setTimeout(() => onShowEvidence?.(evidence), 0);
  };
  const resetFilters = () => {
    setQuery("");
    setRecordType("all");
    setStatus("all");
    setField("all");
    setVisibleCount(PAGE_SIZE);
  };

  return (
    <section className="summary company-tab-panel" id="company-tab-panel-technology" role="tabpanel" aria-labelledby="company-tab-technology">
      <div className="technology-dashboard-header">
        <h2>기술·특허</h2>
        <p>공식 특허·건설신기술과 검증 근거를 한눈에 확인합니다.</p>
      </div>
      {items.length ? (
        <>
          <div className="summary-strip technology-overview-grid" aria-label="기술·특허 현황">
            <div className="summary-chip technology-kpi" data-technology-metric="total"><span>전체 기술·특허</span><strong>{overview.total.toLocaleString("ko-KR")}</strong></div>
            <div className="summary-chip technology-kpi" data-technology-metric="registered"><span>등록</span><strong>{overview.registered.toLocaleString("ko-KR")}</strong></div>
            <div className="summary-chip technology-kpi" data-technology-metric="kipris"><span>KIPRIS 공식 연동</span><strong>{overview.kipris.toLocaleString("ko-KR")}</strong></div>
            <div className="summary-chip technology-kpi" data-technology-metric="evidence"><span>근거 연결</span><strong>{overview.evidenceLinked.toLocaleString("ko-KR")} / {overview.total.toLocaleString("ko-KR")}</strong></div>
          </div>
          <p className="technology-data-note">
            {overview.kipris > 0 ? "KIPRIS 공식 연동 및 내부 검증 기준" : "등록된 근거 출처 및 내부 검증 기준"}
          </p>
          <div className="technology-field-section">
            <span>기술 분야 분포</span>
            <div className="technology-field-chips" role="group" aria-label="기술 분야 필터">
              <button type="button" aria-pressed={field === "all"} onClick={() => resetPaging(setField)("all")}>전체 <strong>{items.length}</strong></button>
              {fieldDistribution.map((entry) => (
                <button key={entry.field} type="button" aria-pressed={field === entry.field} onClick={() => resetPaging(setField)(entry.field)}>
                  {entry.field} <strong>{entry.count}</strong>
                </button>
              ))}
            </div>
          </div>
          <div className="company-toolbar technology-toolbar">
            <label>기술명 검색
              <input value={query} onChange={(event) => resetPaging(setQuery)(event.target.value)} placeholder="기술명·등록번호·출원번호 검색" />
            </label>
            <label>기록 유형
              <select value={recordType} onChange={(event) => resetPaging(setRecordType)(event.target.value)}>
                <option value="all">전체 유형</option>
                {recordTypes.map((type) => <option key={type} value={type}>{labelValue(type, type)}</option>)}
              </select>
            </label>
            <label>상태
              <select value={status} onChange={(event) => resetPaging(setStatus)(event.target.value)}>
                <option value="all">전체 상태</option>
                {statuses.map((itemStatus) => <option key={itemStatus} value={itemStatus}>{labelValue(itemStatus, itemStatus)}</option>)}
              </select>
            </label>
          </div>
          <p className="finance-note technology-result-count">전체 {items.length.toLocaleString("ko-KR")}건 중 {filtered.length.toLocaleString("ko-KR")}건</p>
          <div className="company-section-list technology-list">
            {visible.map((item, index) => {
              const primaryNumber = technologyPrimaryNumber(item);
              const sources = resolvedTechnologySources(company, item);
              const title = item.name || primaryNumber.value || "기술명 확인 중";
              const filedDate = item.application_date || item.filed_at || item.filed_date;
              const registeredDate = item.registration_date || item.registered_at;
              return (
                <div className="technology-card" key={item.technology_id || item.registration_number || item.application_number || `${item.name}-${index}`}>
                  <div className="technology-card-heading">
                    <strong title={title}>{title}</strong>
                    <div className="technology-card-chip-row" aria-label="기술 요약 키워드">
                      {[labelValue(item.record_type || item.group, null), labelValue(item.status, null), technologyField(item)]
                        .filter(Boolean)
                        .map((keyword) => <span key={keyword}>{keyword}</span>)}
                    </div>
                  </div>
                  <div className="technology-card-metadata">
                    <span><b>{primaryNumber.label}</b> <span className="technical-token">{primaryNumber.value}</span></span>
                    {filedDate && <span><b>출원</b> {technologyDate(item, "filed")}</span>}
                    {registeredDate && <span><b>등록</b> {technologyDate(item, "registered")}</span>}
                    {(!filedDate || !registeredDate) && <span className="technology-missing-note">정보 보완 필요</span>}
                  </div>
                  {item.summary && <p className="technology-card-summary">{item.summary}</p>}
                  <div className="technology-card-footer">
                    <div className="technology-evidence-meta">
                      {isKiprisLinkedTechnology(item) && <span className="technology-provenance">KIPRIS 공식 연동</span>}
                      {!isKiprisLinkedTechnology(item) && <span>{sources.length ? "검증 근거 연결" : "근거 정리 중"}</span>}
                    </div>
                    <div className="technology-card-actions">
                      {onShowEvidence && (
                        <button type="button" className="text-button technology-evidence-button" onClick={() => onShowEvidence(buildCompanyItemEvidence(company, title, primaryNumber.value, item.source_ids, technologyField(item)))}>
                          {sources.length ? `근거 ${sources.length}건` : "근거 정리 중"}
                        </button>
                      )}
                      <button type="button" className="text-button entity-detail-button" onClick={() => setSelectedTechnology(item)}>상세보기</button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          {!filtered.length && (
            <div className="technology-empty-state">
              <p>조건에 맞는 기술·특허가 없습니다.</p>
              <button type="button" className="text-button" onClick={resetFilters}>필터 초기화</button>
            </div>
          )}
          {visible.length < filtered.length && (
            <button className="text-button company-more-button" type="button" onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}>
              더 보기 ({visible.length}/{filtered.length})
            </button>
          )}
        </>
      ) : (
        <p>검증 가능한 기술·특허 자료가 없습니다.</p>
      )}
      <CompanyEntityDrawer
        eyebrow="TECHNOLOGY"
        title={selectedTechnology?.name || technologyPrimaryNumber(selectedTechnology || {}).value}
        subtitle={selectedTechnology ? `${labelValue(selectedTechnology.record_type || selectedTechnology.group, "기술")} · ${labelValue(selectedTechnology.status, "상태 확인 중")}` : ""}
        open={Boolean(selectedTechnology)}
        onClose={() => setSelectedTechnology(null)}
      >
        {selectedTechnology && <TechnologyDetail company={company} item={selectedTechnology} onShowEvidence={showEvidenceFromDrawer} />}
      </CompanyEntityDrawer>
    </section>
  );
}
