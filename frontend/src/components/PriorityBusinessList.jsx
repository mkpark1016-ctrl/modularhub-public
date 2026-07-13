import { Link } from "react-router-dom";
import { dDayLabel, getBusinessPriorityInfo } from "../businessInsights";
import FavoriteButton from "./FavoriteButton";

export default function PriorityBusinessList({
  items,
  formatDate,
  businessKind,
  displayAgency,
  isFavorite,
  onToggleFavorite,
  referenceDate,
}) {
  return (
    <section className="dashboard-section">
      <div className="section-heading">
        <h2>지금 확인할 사업</h2>
          <Link to="/business?priority=important&sort=priority">전체 보기</Link>
      </div>
      <div className="priority-list">
        {items.length === 0 && <p className="empty-inline">현재 즉시 확인할 진행 중 사업이 없습니다.</p>}
        {items.map((item) => {
          const info = getBusinessPriorityInfo(item, referenceDate);
          const reasons = info.priorityReasons;
          return (
            <article key={item.id} className="priority-item">
              <div className="priority-item-main">
                <div className="badge-row">
                  <span>{displayAgency(item)}</span>
                  <span>{businessKind(item)}</span>
                  {info.important && <span className="important">우선 검토</span>}
                  <span className={`priority-badge ${info.reviewBadgeClass}`}>{info.reviewLabel}</span>
                </div>
                <h3><Link to={`/business/${item.id}`}>{item.title}</Link></h3>
                <p>{formatDate(item.posted_at)} · {formatDate(item.due_at || item.deadline_at)} · {dDayLabel(item, referenceDate) || "일정 확인 필요"}</p>
                <div className="reason-list">{reasons.slice(0, 2).map((reason) => <span key={reason}>{reason}</span>)}</div>
              </div>
              <div className="priority-actions">
                <FavoriteButton active={isFavorite(item.id)} onClick={() => onToggleFavorite(item.id)} />
                <Link className="text-button" to={`/business/${item.id}`}>상세보기</Link>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
