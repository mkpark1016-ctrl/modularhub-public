export const COMPANY_ACTIVITY_FILTERS = [
  { value: "all", label: "전체" },
  { value: "projects", label: "프로젝트·수주" },
  { value: "investment_factory", label: "투자·공장" },
  { value: "technology_financial", label: "기술·재무" },
  { value: "general", label: "일반뉴스" },
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

export function isValidActivity(activity) {
  if (!activity || typeof activity !== "object") return false;
  if (!["high", "medium"].includes(activity.confidence)) return false;
  if (activity.sourceUrl && !getActivitySourceUrl(activity)) return false;
  return Boolean(activity.companyId && activity.activityId && activity.title && activity.publishedAt);
}
