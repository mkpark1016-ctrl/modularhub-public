import { useMemo, useState } from "react";
import {
  detailModel,
  eventDate,
  eventRoleLabel,
  eventStatusLabel,
  eventTypeLabel,
  formatDate,
  formatKrw,
  labelValue,
  pipelineEvents,
  verifiedProjectEvents,
} from "./companyDetailHelpers";

const PAGE_SIZE = 5;

function EventTable({ events, emptyText, candidate = false }) {
  const [statusFilter, setStatusFilter] = useState("all");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const statusOptions = useMemo(() => [...new Set(events.map((event) => event.event_status).filter(Boolean))], [events]);
  const filtered = statusFilter === "all" ? events : events.filter((event) => event.event_status === statusFilter);
  const visible = filtered.slice(0, visibleCount);

  if (!events.length) return <p>{emptyText}</p>;

  return (
    <div className={candidate ? "company-event-group candidate-event-group" : "company-event-group"}>
      <label className="compact-control">상태 필터
        <select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setVisibleCount(PAGE_SIZE); }}>
          <option value="all">전체 상태</option>
          {statusOptions.map((status) => <option key={status} value={status}>{labelValue(status)}</option>)}
        </select>
      </label>
      <div className="company-table-wrap">
        <table className="company-financial-table company-project-table">
          <thead>
            <tr>
              <th>프로젝트명</th>
              <th>상태</th>
              <th>발주처·협력기관</th>
              <th>지역</th>
              <th>용도</th>
              <th>수행 역할</th>
              <th>규모·금액</th>
              <th>계약·준공일</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((event) => {
              const articleCount = (event.source_ids || []).filter((sourceId) => String(sourceId).startsWith("article-")).length;
              return (
                <tr key={event.event_id}>
                  <th>
                    {event.title || "프로젝트명 확인 중"}
                    {candidate && <span className="mini-status-badge">검증 실적 아님</span>}
                    {articleCount > 0 && <small>기사 근거 {articleCount.toLocaleString("ko-KR")}건</small>}
                  </th>
                  <td>{eventTypeLabel(event)} · {eventStatusLabel(event)}</td>
                  <td>{event.client || event.counterparties?.join(", ") || "확인되지 않음"}</td>
                  <td>{event.location || "확인되지 않음"}</td>
                  <td>{labelValue(event.market_segment, "확인되지 않음")}</td>
                  <td>{eventRoleLabel(event)}</td>
                  <td>{event.amount !== null && event.amount !== undefined ? formatKrw(event.amount) : "확인되지 않음"}</td>
                  <td>{eventDate(event) ? formatDate(eventDate(event)) : "확인되지 않음"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {visible.length < filtered.length && (
        <button className="text-button company-more-button" type="button" onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}>
          더 보기 ({visible.length}/{filtered.length})
        </button>
      )}
      {candidate && <p className="finance-note">후보, MOU, Pre-Con, R&D, 전시는 검증 프로젝트 실적 수에 합산하지 않습니다.</p>}
    </div>
  );
}

export default function CompanyProjectTab({ company }) {
  const model = detailModel(company);
  const verified = verifiedProjectEvents(model.events);
  const pipeline = pipelineEvents(model.events);

  return (
    <section className="summary company-tab-panel" id="company-tab-panel-projects" role="tabpanel" aria-labelledby="company-tab-projects">
      <h2>프로젝트</h2>
      <div className="company-highlight-grid">
        <span>검증 실적 {verified.length.toLocaleString("ko-KR")}건</span>
        <span>파이프라인·기타 활동 {pipeline.length.toLocaleString("ko-KR")}건</span>
      </div>
      <div className="company-subsection">
        <h3>검증 실적</h3>
        <EventTable events={verified} emptyText="공식 근거와 수행 역할이 확인된 모듈러 프로젝트 실적이 없습니다." />
      </div>
      <div className="company-subsection">
        <h3>파이프라인 및 기타 활동</h3>
        <EventTable events={pipeline} candidate emptyText="현재 공개자료에서 확인된 후보·협력·R&D 활동이 없습니다." />
      </div>
    </section>
  );
}
