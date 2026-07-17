import { useMemo, useState } from "react";
import { detailModel, formatDate, labelValue } from "./companyDetailHelpers";

const PAGE_SIZE = 8;

function normalize(value) {
  return String(value || "").normalize("NFC").toLowerCase();
}

export default function CompanyTechnologyTab({ company }) {
  const model = detailModel(company);
  const items = model.technologyItems;
  const [query, setQuery] = useState("");
  const [recordType, setRecordType] = useState("all");
  const [status, setStatus] = useState("all");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const recordTypes = useMemo(() => [...new Set(items.map((item) => item.record_type || item.group).filter(Boolean))], [items]);
  const statuses = useMemo(() => [...new Set(items.map((item) => item.status).filter(Boolean))], [items]);
  const filtered = useMemo(() => {
    const term = normalize(query);
    return items.filter((item) => {
      if (recordType !== "all" && (item.record_type || item.group) !== recordType) return false;
      if (status !== "all" && item.status !== status) return false;
      if (!term) return true;
      return normalize([
        item.name,
        item.registration_number,
        item.application_number,
        item.technology_area,
        item.summary,
      ].join(" ")).includes(term);
    });
  }, [items, query, recordType, status]);
  const visible = filtered.slice(0, visibleCount);

  const resetPaging = (setter) => (value) => {
    setter(value);
    setVisibleCount(PAGE_SIZE);
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
          </div>
          <div className="company-section-list technology-list">
            {visible.map((item, index) => (
              <div key={item.technology_id || item.registration_number || item.application_number || `${item.name}-${index}`}>
                <strong>{item.name || item.registration_number || item.application_number || "기술명 확인 중"}</strong>
                <span>{[
                  labelValue(item.record_type || item.group, null),
                  item.registration_number || item.application_number,
                  labelValue(item.status, null),
                  labelValue(item.technology_area, null),
                ].filter(Boolean).join(" · ") || "세부 정보 확인 중"}</span>
                <span>출원일 {formatDate(item.application_date)} · 등록일 {formatDate(item.registration_date)}</span>
                {item.summary && <span>{item.summary}</span>}
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
        <p>현재 공개자료를 추가 조사 중입니다.</p>
      )}
    </section>
  );
}
