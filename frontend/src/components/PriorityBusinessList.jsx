import { Link } from "react-router-dom";
import { dDayLabel, getBusinessPriority, getBusinessPriorityLabel, getBusinessPriorityReasons } from "../businessInsights";
import FavoriteButton from "./FavoriteButton";

export default function PriorityBusinessList({
  items,
  formatDate,
  businessKind,
  displayAgency,
  isFavorite,
  onToggleFavorite,
}) {
  return (
    <section className="dashboard-section">
      <div className="section-heading">
        <h2>지금 확인할 사업</h2>
        <Link to="/business?priority=immediate&sort=priority">전체 보기</Link>
      </div>
      <div className="priority-list">
        {items.length === 0 && <p className="empty-inline">현재 즉시 확인할 진행 중 사업이 없습니다.</p>}
        {items.map((item) => {
          const reasons = getBusinessPriorityReasons(item);
          const priority = getBusinessPriority(item);
          return (
            <article key={item.id} className="priority-item">
              <div className="priority-item-main">
                <div className="badge-row">
                  <span>{displayAgency(item)}</span>
                  <span>{businessKind(item)}</span>
                  <span className={`priority-badge ${priority}`}>{getBusinessPriorityLabel(item)}</span>
                </div>
                <h3><Link to={`/business/${item.id}`}>{item.title}</Link></h3>
                <p>{formatDate(item.posted_at)} · {formatDate(item.due_at || item.deadline_at)} · {dDayLabel(item) || "일정 확인 필요"}</p>
                <div className="reason-list">{reasons.map((reason) => <span key={reason}>{reason}</span>)}</div>
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
