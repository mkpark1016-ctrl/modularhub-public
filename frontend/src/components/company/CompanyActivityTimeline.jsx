import { useMemo, useState } from "react";
import { ExternalLink, Search } from "lucide-react";
import {
  COMPANY_ACTIVITY_FILTERS,
  COMPANY_ACTIVITY_PERIOD_FILTERS,
  COMPANY_ACTIVITY_SORT_OPTIONS,
  filterCompanyActivities,
  filterCompanyActivitiesByPeriod,
  getActivitySourceName,
  getActivitySourceUrl,
  getActivityTypeLabel,
  getCompanyActivityFilterCounts,
  isValidActivity,
  searchCompanyActivities,
  sortCompanyActivities,
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
  const [period, setPeriod] = useState("all");
  const [sortOrder, setSortOrder] = useState("newest");
  const [query, setQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE_COUNT);

  const validActivities = useMemo(
    () => activities.filter((activity) => isValidActivity(activity)),
    [activities],
  );
  const periodFiltered = useMemo(
    () => filterCompanyActivitiesByPeriod(validActivities, period),
    [period, validActivities],
  );
  const searched = useMemo(
    () => searchCompanyActivities(periodFiltered, query),
    [periodFiltered, query],
  );
  const filterCounts = useMemo(
    () => getCompanyActivityFilterCounts(searched),
    [searched],
  );
  const filtered = useMemo(
    () => filterCompanyActivities(searched, filter),
    [filter, searched],
  );
  const sorted = useMemo(
    () => sortCompanyActivities(filtered, sortOrder),
    [filtered, sortOrder],
  );
  const visible = sorted.slice(0, visibleCount);
  const remaining = Math.max(0, sorted.length - visible.length);
  const nextBatch = Math.min(INITIAL_VISIBLE_COUNT, remaining);

  const resetVisibleCount = () => setVisibleCount(INITIAL_VISIBLE_COUNT);

  return (
    <div className="company-subsection company-activity-timeline">
      <div className="company-subsection-heading">
        <h3>기업 활동 타임라인</h3>
        <span>확인된 활동 {validActivities.length.toLocaleString("ko-KR")}건</span>
      </div>

      <div className="company-toolbar company-activity-toolbar" aria-label="기업 활동 검색 및 정렬">
        <label>
          활동 검색
          <span className="search-input-wrap">
            <Search size={15} aria-hidden="true" />
            <input
              type="search"
              value={query}
              placeholder="제목·요약·출처 검색"
              onChange={(event) => {
                setQuery(event.target.value);
                resetVisibleCount();
              }}
            />
          </span>
        </label>
        <label>
          기간
          <select
            value={period}
            onChange={(event) => {
              setPeriod(event.target.value);
              resetVisibleCount();
            }}
          >
            {COMPANY_ACTIVITY_PERIOD_FILTERS.map((option) => (
              <option value={option.value} key={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
        <label>
          정렬
          <select
            value={sortOrder}
            onChange={(event) => {
              setSortOrder(event.target.value);
              resetVisibleCount();
            }}
          >
            {COMPANY_ACTIVITY_SORT_OPTIONS.map((option) => (
              <option value={option.value} key={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="company-activity-filters" aria-label="기업 활동 유형 필터">
        {COMPANY_ACTIVITY_FILTERS.map((option) => (
          <button
            key={option.value}
            type="button"
            className={filter === option.value ? "active" : ""}
            aria-pressed={filter === option.value}
            onClick={() => {
              setFilter(option.value);
              resetVisibleCount();
            }}
          >
            {option.label} {Number(filterCounts[option.value] || 0).toLocaleString("ko-KR")}
          </button>
        ))}
      </div>

      <p className="finance-note company-activity-result-count">
        검색·필터 결과 {sorted.length.toLocaleString("ko-KR")}건
      </p>

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
        <p>{validActivities.length ? "검색·필터 조건에 맞는 활동이 없습니다." : "확인된 공개 활동이 없습니다."}</p>
      )}

      {remaining > 0 && (
        <button
          type="button"
          className="button secondary company-activity-more"
          onClick={() => setVisibleCount((count) => count + INITIAL_VISIBLE_COUNT)}
        >
          {nextBatch}건 더 보기 · {remaining}건 남음
        </button>
      )}
    </div>
  );
}
