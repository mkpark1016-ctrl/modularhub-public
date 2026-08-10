import { useMemo, useState } from "react";
import { ExternalLink } from "lucide-react";
import {
  COMPANY_ACTIVITY_FILTERS,
  filterCompanyActivities,
  getActivitySourceName,
  getActivitySourceUrl,
  getActivityTypeLabel,
  isValidActivity,
} from "../../companyActivities";
import { formatDate } from "./companyDetailHelpers";

const INITIAL_VISIBLE_COUNT = 10;

function ActivityMeta({ activity }) {
  const meta = [
    formatDate(activity.publishedAt),
    getActivitySourceName(activity),
    activity.sourceType === "news" ? "관련 보도" : activity.sourceType === "business" ? "사업정보" : "",
  ].filter(Boolean);
  return <span>{meta.join(" · ")}</span>;
}

export default function CompanyActivityTimeline({ activities = [] }) {
  const [filter, setFilter] = useState("all");
  const [expanded, setExpanded] = useState(false);
  const validActivities = useMemo(
    () => [...activities]
      .filter((activity) => isValidActivity(activity))
      .sort((a, b) => String(b.publishedAt || "").localeCompare(String(a.publishedAt || ""))),
    [activities],
  );
  const filtered = useMemo(
    () => filterCompanyActivities(validActivities, filter),
    [filter, validActivities],
  );
  const visible = expanded ? filtered : filtered.slice(0, INITIAL_VISIBLE_COUNT);

  return (
    <div className="company-subsection company-activity-timeline">
      <div className="company-subsection-heading">
        <h3>기업 활동 타임라인</h3>
        <span>확인된 활동 {validActivities.length.toLocaleString("ko-KR")}건</span>
      </div>
      <div className="company-activity-filters" aria-label="기업 활동 필터">
        {COMPANY_ACTIVITY_FILTERS.map((option) => (
          <button
            key={option.value}
            type="button"
            className={filter === option.value ? "active" : ""}
            aria-pressed={filter === option.value}
            onClick={() => {
              setFilter(option.value);
              setExpanded(false);
            }}
          >
            {option.label}
          </button>
        ))}
      </div>
      {visible.length ? (
        <div className="company-section-list company-activity-list">
          {visible.map((activity) => {
            const sourceUrl = getActivitySourceUrl(activity);
            const sourceName = getActivitySourceName(activity);
            return (
              <div key={activity.activityId} className="company-activity-item">
                <div className="company-activity-title-row">
                  <span className="mini-status-badge">{getActivityTypeLabel(activity.activityType)}</span>
                  <strong>{activity.title}</strong>
                </div>
                <ActivityMeta activity={activity} />
                {activity.summary && <p>{activity.summary}</p>}
                <div className="company-activity-actions">
                  {sourceUrl ? (
                    <a className="inline-link" href={sourceUrl} target="_blank" rel="noopener noreferrer" aria-label={`${sourceName} 원문 열기`}>
                      {sourceName} 원문 보기 <ExternalLink size={13} />
                    </a>
                  ) : (
                    <span>{sourceName} · 원문 링크 미공개</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p>확인된 공개 활동이 없습니다.</p>
      )}
      {filtered.length > INITIAL_VISIBLE_COUNT && (
        <button type="button" className="button secondary company-activity-more" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "접기" : `더 보기 ${filtered.length - INITIAL_VISIBLE_COUNT}건`}
        </button>
      )}
    </div>
  );
}
