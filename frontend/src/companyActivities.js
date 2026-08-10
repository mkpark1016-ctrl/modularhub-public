export const COMPANY_ACTIVITY_FILTERS = [
  { value: "all", label: "전체" },
  { value: "projects", label: "프로젝트·수주" },
  { value: "investment_factory", label: "투자·공장" },
  { value: "technology_financial", label: "기술·재무" },
  { value: "general", label: "일반뉴스" },
];

export const COMPANY_ACTIVITY_PERIOD_FILTERS = [
  { value: "all", label: "전체 기간" },
  { value: "90", label: "최근 90일" },
  { value: "180", label: "최근 6개월" },
  { value: "365", label: "최근 1년" },
];

export const COMPANY_ACTIVITY_SORT_OPTIONS = [
  { value: "newest", label: "최신순" },
  { value: "oldest", label: "오래된순" },
];

export const COMPANY_ACTIVITY_TYPE_LABELS = {
  project: "프로젝트",
  contract: "수주·계약",
  bid: "입찰",
  investment: "투자",
  factory: "공장",
  partnership: "협력",
  technology: "기술",
  financial: "재무",
  management: "경영",
  general_news: "일반뉴스",
};

export function getCompanyActivities(data, companyId) {
  if (!data || !companyId) return [];
  const rows = Array.isArray(data.companies) ? data.companies : [];
  const row = rows.find((item) => item?.companyId === companyId);
  return Array.isArray(row?.activities) ? row.activities : [];
}

export function getActivityTypeLabel(type) {
  return COMPANY_ACTIVITY_TYPE_LABELS[type] || "일반뉴스";
}

export function getActivitySourceName(activity) {
  const value = activity?.sourceName || activity?.source || activity?.publisher || "공개자료";
  return String(value).trim() || "공개자료";
}

export function getActivitySourceUrl(activity) {
  const value = String(activity?.sourceUrl || "").trim();
  if (!value) return null;
  try {
    const parsed = new URL(value);
    if (!["http:", "https:"].includes(parsed.protocol)) return null;
    return value;
  } catch {
    return null;
  }
}

export function getActivityFilterGroup(type) {
  if (["project", "contract", "bid"].includes(type)) return "projects";
  if (["investment", "factory"].includes(type)) return "investment_factory";
  if (["technology", "financial"].includes(type)) return "technology_financial";
  return "general";
}

export function filterCompanyActivities(activities, filter) {
  const rows = Array.isArray(activities) ? activities : [];
  if (!filter || filter === "all") return rows;
  return rows.filter((activity) => getActivityFilterGroup(activity.activityType) === filter);
}

function activityDay(value) {
  const text = String(value || "").trim();
  if (!text) return null;
  const date = new Date(text.length === 10 ? `${text}T00:00:00Z` : text);
  if (Number.isNaN(date.getTime())) return null;
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
}

export function filterCompanyActivitiesByPeriod(activities, period, asOf = new Date()) {
  const rows = Array.isArray(activities) ? activities : [];
  if (!period || period === "all") return rows;
  const days = Number(period);
  if (!Number.isFinite(days) || days <= 0) return rows;
  const asOfDay = activityDay(asOf);
  if (!asOfDay) return rows;
  const cutoff = new Date(asOfDay.getTime() - (days * 24 * 60 * 60 * 1000));
  return rows.filter((activity) => {
    const published = activityDay(activity?.publishedAt);
    return published && published >= cutoff && published <= asOfDay;
  });
}

export function searchCompanyActivities(activities, query) {
  const rows = Array.isArray(activities) ? activities : [];
  const terms = String(query || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return rows;
  return rows.filter((activity) => {
    const text = [
      activity?.title,
      activity?.summary,
      getActivitySourceName(activity),
      activity?.organization,
      activity?.projectName,
    ].filter(Boolean).join(" ").toLowerCase();
    return terms.every((term) => text.includes(term));
  });
}

export function sortCompanyActivities(activities, order = "newest") {
  const rows = [...(Array.isArray(activities) ? activities : [])];
  const direction = order === "oldest" ? 1 : -1;
  return rows.sort((a, b) => direction * String(a?.publishedAt || "").localeCompare(String(b?.publishedAt || "")));
}

export function getCompanyActivityFilterCounts(activities) {
  const rows = Array.isArray(activities) ? activities : [];
  const counts = Object.fromEntries(COMPANY_ACTIVITY_FILTERS.map((option) => [option.value, 0]));
  counts.all = rows.length;
  for (const activity of rows) {
    const group = getActivityFilterGroup(activity?.activityType);
    counts[group] = (counts[group] || 0) + 1;
  }
  return counts;
}

export function isValidActivity(activity) {
  if (!activity || typeof activity !== "object") return false;
  if (!["high", "medium"].includes(activity.confidence)) return false;
  if (activity.sourceUrl && !getActivitySourceUrl(activity)) return false;
  return Boolean(activity.companyId && activity.activityId && activity.title && activity.publishedAt);
}
