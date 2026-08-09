import { useMemo, useState } from "react";
import { detailModel, formatDate, labelValue } from "./companyDetailHelpers";
import { buildCompanyItemEvidence } from "../../companyEvidence";
import CompanyEntityDrawer from "./CompanyEntityDrawer";

const PAGE_SIZE = 8;

function normalize(value) {
  return String(value || "").normalize("NFC").toLowerCase();
}

function technologyField(item) {
  const text = normalize([item.name, item.technology_area, item.summary].join(" "));
  if (/(접합|체결|연결|구조)/.test(text)) return "구조·접합";
  if (/(고층|적층|층간)/.test(text)) return "고층화";
  if (/(시공|안전|고소작업|공기)/.test(text)) return "시공성·안전";
  if (/(외장|기밀|수밀|단열)/.test(text)) return "외장·기밀";
  if (/(신기술|공법|인증)/.test(text)) return "공법·건설신기술";
  return "기타";
}

function technologyNumber(item) {
  return item.registration_number || item.application_number || item.patent_number || "번호 확인 중";
}

function technologyDate(item, key) {
  return key === "filed"
    ? formatDate(item.application_date || item.filed_at || item.filed_date)
    : formatDate(item.registration_date || item.registered_at);
}

function TechnologyDetail({ company, item, onShowEvidence }) {
  const title = item.name || technologyNumber(item);
  return (
    <dl className="detail-grid compact-detail-grid">
      <div><dt>유형</dt><dd>{labelValue(item.record_type || item.group, "확인되지 않음")}</dd></div>
      <div><dt>등록·출원번호</dt><dd className="technical-token">{technologyNumber(item)}</dd></div>
      <div><dt>상태</dt><dd>{labelValue(item.status, "확인되지 않음")}</dd></div>
      <div><dt>기술 분야</dt><dd>{item.technology_area ? labelValue(item.technology_area, item.technology_area) : technologyField(item)}</dd></div>
      <div><dt>출원일</dt><dd>{technologyDate(item, "filed")}</dd></div>
      <div><dt>등록일</dt><dd>{technologyDate(item, "registered")}</dd></div>
      {item.summary && <div><dt>기술 효과</dt><dd>{item.summary}</dd></div>}
      {onShowEvidence && (
        <div><dt>근거</dt><dd><button type="button" className="text-button evidence-inline-button" onClick={() => onShowEvidence(buildCompanyItemEvidence(company, title, technologyNumber(item), item.source_ids, technologyField(item)))}>근거보기</button></dd></div>
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
  const fields = useMemo(() => [...new Set(items.map((item) => technologyField(item)))], [items]);
  const filtered = useMemo(() => {
    const term = normalize(query);
    return items.filter((item) => {
      if (recordType !== "all" && (item.record_type || item.group) !== recordType) return false;
      if (status !== "all" && item.status !== status) return false;
      if (field !== "all" && technologyField(item) !== field) return false;
      if (!term) return true;
      return normalize([
        item.name,
        item.registration_number,
        item.application_number,
        item.patent_number,
        item.technology_area,
        item.summary,
      ].join(" ")).includes(term);
    });
  }, [field, items, query, recordType, status]);
  const visible = filtered.slice(0, visibleCount);

  const resetPaging = (setter) => (value) => {
    setter(value);
    setVisibleCount(PAGE_SIZE);
  };
  const showEvidenceFromDrawer = (evidence) => {
    setSelectedTechnology(null);
    window.setTimeout(() => onShowEvidence?.(evidence), 0);
  };

  return (
    <section className="summary company-tab-panel" id="company-tab-panel-technology" role="tabpanel" aria-labelledby="company-tab-technology">
      <h2>기술·특허</h2>
      <p className="finance-note">전체 {items.length.toLocaleString("ko-KR")}건 중 {filtered.length.toLocaleString("ko-KR")}건</p>
      {items.length ? (
        <>
          <div className="company-toolbar">
            <label>기술명 검색
              <input value={query} onChange={(event) => resetPaging(setQuery)(event.target.value)} placeholder="기술명, 번호, 분야 검색" />
            </label>
            <label>기록 유형
              <select value={recordType} onChange={(event) => resetPaging(setRecordType)(event.target.value)}>
                <option value="all">전체 유형</option>
                {recordTypes.map((type) => <option key={type} value={type}>{labelValue(type, type)}</option>)}
              </select>
            </label>
            <label>등록·출원 상태
              <select value={status} onChange={(event) => resetPaging(setStatus)(event.target.value)}>
                <option value="all">전체 상태</option>
                {statuses.map((itemStatus) => <option key={itemStatus} value={itemStatus}>{labelValue(itemStatus, itemStatus)}</option>)}
              </select>
            </label>
            <label>기술 분야
              <select value={field} onChange={(event) => resetPaging(setField)(event.target.value)}>
                <option value="all">전체 분야</option>
                {fields.map((itemField) => <option key={itemField} value={itemField}>{itemField}</option>)}
              </select>
            </label>
          </div>
          <div className="company-section-list technology-list">
            {visible.map((item, index) => (
              <div key={item.technology_id || item.registration_number || item.application_number || `${item.name}-${index}`}>
                <strong>{item.name || item.registration_number || item.application_number || "기술명 확인 중"}</strong>
                {(!item.application_date && !item.filed_at) || (!item.registration_date && !item.registered_at) ? <span className="mini-status-badge">정보 보완 필요</span> : null}
                <div className="technology-card-chip-row" aria-label="기술 요약 키워드">
                  {[
                    labelValue(item.record_type || item.group, null),
                    labelValue(item.status, null),
                    item.technology_area ? labelValue(item.technology_area, item.technology_area) : technologyField(item),
                  ].filter(Boolean).slice(0, 3).map((keyword) => <span key={keyword}>{keyword}</span>)}
                </div>
                {item.summary && <p className="technology-card-summary">{item.summary}</p>}
                <button type="button" className="text-button entity-detail-button" onClick={() => setSelectedTechnology(item)}>
                  상세보기
                </button>
              </div>
            ))}
          </div>
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
        title={selectedTechnology?.name || technologyNumber(selectedTechnology || {})}
        subtitle={selectedTechnology ? `${labelValue(selectedTechnology.record_type || selectedTechnology.group, "기술")} · ${labelValue(selectedTechnology.status, "상태 확인 중")}` : ""}
        open={Boolean(selectedTechnology)}
        onClose={() => setSelectedTechnology(null)}
      >
        {selectedTechnology && <TechnologyDetail company={company} item={selectedTechnology} onShowEvidence={showEvidenceFromDrawer} />}
      </CompanyEntityDrawer>
    </section>
  );
}
