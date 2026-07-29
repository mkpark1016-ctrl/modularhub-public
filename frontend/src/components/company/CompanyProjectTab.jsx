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
import { buildCompanyItemEvidence } from "../../companyEvidence";

const PAGE_SIZE = 5;

function projectMeta(event) {
  return {
    title: event.title || "프로젝트명 확인 중",
    client: event.client || event.counterparties?.join(", ") || "확인되지 않음",
    location: event.location || "확인되지 않음",
    segment: labelValue(event.market_segment, "확인되지 않음"),
    role: eventRoleLabel(event),
    amount: event.amount !== null && event.amount !== undefined ? formatKrw(event.amount) : "확인되지 않음",
    date: eventDate(event) ? formatDate(eventDate(event)) : "확인되지 않음",
    articleCount: (event.source_ids || []).filter((sourceId) => String(sourceId).startsWith("article-")).length,
  };
}

function ProjectCard({ company, event, candidate, onShowEvidence }) {
  const meta = projectMeta(event);
  return (
    <article className={candidate ? "responsive-data-card candidate-card" : "responsive-data-card"}>
      <div className="responsive-card-heading">
        <strong>{meta.title}</strong>
        <span className="mini-status-badge">{eventStatusLabel(event)}</span>
      </div>
      <dl>
        <div><dt>용도</dt><dd>{meta.segment}</dd></div>
        <div><dt>지역</dt><dd>{meta.location}</dd></div>
        <div><dt>발주처·협력기관</dt><dd>{meta.client}</dd></div>
        <div><dt>수행 역할</dt><dd>{meta.role}</dd></div>
      </dl>
      <details className="company-row-detail">
        <summary>상세정보</summary>
        <dl>
          <div><dt>유형·상태</dt><dd>{eventTypeLabel(event)} · {eventStatusLabel(event)}</dd></div>
          <div><dt>규모·금액</dt><dd>{meta.amount}</dd></div>
          <div><dt>계약·준공일</dt><dd>{meta.date}</dd></div>
          <div><dt>관련 보도</dt><dd>{meta.articleCount.toLocaleString("ko-KR")}건</dd></div>
          {candidate && <div><dt>실적 집계</dt><dd>검증 실적 아님</dd></div>}
          {onShowEvidence && (
            <div><dt>근거</dt><dd><button type="button" className="text-button evidence-inline-button" onClick={() => onShowEvidence(buildCompanyItemEvidence(company, meta.title, `${eventTypeLabel(event)} · ${eventStatusLabel(event)}`, event.source_ids, candidate ? "파이프라인·기타 활동은 검증 실적으로 합산하지 않습니다." : "검증 프로젝트 실적 근거입니다."))}>근거보기</button></dd></div>
          )}
        </dl>
      </details>
    </article>
  );
}

function EventTable({ company, events, emptyText, candidate = false, onShowEvidence }) {
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
      <div className="company-table-wrap responsive-table-wrap">
        <table className="company-financial-table company-project-table">
          <thead>
            <tr>
              <th>프로젝트명</th>
              <th>상태</th>
              <th>발주처·협력기관</th>
              <th>지역</th>
              <th>용도</th>
              <th>수행 역할</th>
              <th>근거</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((event) => {
              const meta = projectMeta(event);
              return (
                <tr key={event.event_id}>
                  <th>
                    {meta.title}
                    {candidate && <span className="mini-status-badge">검증 실적 아님</span>}
                    {meta.articleCount > 0 && <small>관련 보도 {meta.articleCount.toLocaleString("ko-KR")}건</small>}
                  </th>
                  <td>{eventTypeLabel(event)} · {eventStatusLabel(event)}</td>
                  <td>{meta.client}</td>
                  <td>{meta.location}</td>
                  <td>{meta.segment}</td>
                  <td>{meta.role}<small>{meta.date}</small></td>
                  <td>{onShowEvidence ? <button type="button" className="text-button evidence-inline-button" onClick={() => onShowEvidence(buildCompanyItemEvidence(company, meta.title, `${eventTypeLabel(event)} · ${eventStatusLabel(event)}`, event.source_ids, candidate ? "파이프라인·기타 활동은 검증 실적으로 합산하지 않습니다." : "검증 프로젝트 실적 근거입니다."))}>근거보기</button> : meta.amount}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="responsive-card-list project-card-list">
        {visible.map((event) => <ProjectCard key={`card-${event.event_id}`} company={company} event={event} candidate={candidate} onShowEvidence={onShowEvidence} />)}
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

export default function CompanyProjectTab({ company, onShowEvidence }) {
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
        <EventTable company={company} events={verified} emptyText="공식 근거와 수행 역할이 확인된 모듈러 프로젝트 실적이 없습니다." onShowEvidence={onShowEvidence} />
      </div>
      <div className="company-subsection">
        <h3>파이프라인 및 기타 활동</h3>
        <EventTable company={company} events={pipeline} candidate emptyText="현재 공개자료에서 확인된 후보·협력·R&D 활동이 없습니다." onShowEvidence={onShowEvidence} />
      </div>
    </section>
  );
}
