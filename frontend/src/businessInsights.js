export const PRIORITY_ORDER = {
  immediate: 0,
  this_week: 1,
  watch: 2,
  archived: 3,
};

export const PRIORITY_LABELS = {
  immediate: "즉시 검토",
  this_week: "이번 주 검토",
  watch: "관찰",
  archived: "마감",
};

export function parseDate(value) {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function startOfDay(value = new Date()) {
  const date = parseDate(value) || new Date();
  date.setHours(0, 0, 0, 0);
  return date;
}

export function daysBetween(from, to) {
  const start = startOfDay(from);
  const end = startOfDay(to);
  return Math.round((end.getTime() - start.getTime()) / 86400000);
}

export function getBusinessStatus(item) {
  if (item?.lifecycle_status) return item.lifecycle_status;
  if (item?.opportunity_status) return item.opportunity_status;
  if (item?.is_closed === true) return "closed";
  const due = parseDate(item?.due_at || item?.deadline_at);
  if (!due) return "unknown";
  return daysBetween(new Date(), due) >= 0 ? "active" : "closed";
}

export function isBusinessActive(item) {
  return getBusinessStatus(item) === "active";
}

export function getDeadlineDate(item) {
  return parseDate(item?.due_at || item?.deadline_at);
}

export function getPostedDate(item) {
  return parseDate(item?.posted_at);
}

export function getDaysUntilDeadline(item, now = new Date()) {
  const explicit = Number(item?.days_until_deadline);
  if (Number.isFinite(explicit)) return explicit;
  const deadline = getDeadlineDate(item);
  return deadline ? daysBetween(now, deadline) : null;
}

export function isRecentlyPosted(item, days = 7, now = new Date()) {
  const posted = getPostedDate(item);
  if (!posted) return false;
  const diff = daysBetween(posted, now);
  return diff >= 0 && diff <= days;
}

export function isDeadlineWithin(item, days = 7, now = new Date()) {
  if (!isBusinessActive(item)) return false;
  const diff = getDaysUntilDeadline(item, now);
  return diff !== null && diff >= 0 && diff <= days;
}

export function getBusinessPriority(item, now = new Date()) {
  if (getBusinessStatus(item) === "closed") return "archived";
  if (isDeadlineWithin(item, 7, now) || item?.is_known_important === true) return "immediate";
  if (
    isBusinessActive(item) &&
    (
      isRecentlyPosted(item, 7, now) ||
      item?.modular_relevance === "confirmed" ||
      item?.source_type === "public_agency_contest"
    )
  ) {
    return "this_week";
  }
  if (isBusinessActive(item)) return "watch";
  return "archived";
}

export function getBusinessPriorityLabel(item, now = new Date()) {
  return PRIORITY_LABELS[getBusinessPriority(item, now)];
}

export function getBusinessPriorityReasons(item, now = new Date()) {
  const reasons = [];
  const deadline = getDaysUntilDeadline(item, now);
  if (getBusinessStatus(item) === "closed") reasons.push("마감 사업");
  if (deadline !== null && deadline >= 0 && deadline <= 7) {
    reasons.push(deadline === 0 ? "마감 D-Day" : `마감 D-${deadline}`);
  }
  if (item?.is_known_important === true) reasons.push("중요공고");
  if (isRecentlyPosted(item, 7, now)) reasons.push("최근 등록");
  if (item?.modular_relevance === "confirmed") reasons.push("모듈러 명시");
  if (isBusinessActive(item) && item?.source_type === "public_agency_contest") reasons.push("공공기관 공모");
  if (!reasons.length && isBusinessActive(item)) reasons.push("진행 중 사업");
  if (!reasons.length) reasons.push("보관 대상");
  return reasons;
}

export function dDayLabel(item, now = new Date()) {
  const diff = getDaysUntilDeadline(item, now);
  if (diff === null) return "";
  if (diff === 0) return "D-Day";
  if (diff > 0) return `D-${diff}`;
  return `마감 ${Math.abs(diff)}일 경과`;
}

export function compareBusinessByPriority(a, b, now = new Date()) {
  const priorityDelta = PRIORITY_ORDER[getBusinessPriority(a, now)] - PRIORITY_ORDER[getBusinessPriority(b, now)];
  if (priorityDelta !== 0) return priorityDelta;
  const aDeadline = getDeadlineDate(a)?.getTime();
  const bDeadline = getDeadlineDate(b)?.getTime();
  if (aDeadline && bDeadline && aDeadline !== bDeadline) return aDeadline - bDeadline;
  if (aDeadline && !bDeadline) return -1;
  if (!aDeadline && bDeadline) return 1;
  const aPosted = getPostedDate(a)?.getTime() || 0;
  const bPosted = getPostedDate(b)?.getTime() || 0;
  if (aPosted !== bPosted) return bPosted - aPosted;
  return String(a?.title || "").localeCompare(String(b?.title || ""), "ko-KR");
}

export function compareBusinessBySort(a, b, sort, now = new Date(), getAgency = () => "") {
  if (sort === "deadline") {
    const aDeadline = getDeadlineDate(a)?.getTime();
    const bDeadline = getDeadlineDate(b)?.getTime();
    if (aDeadline && bDeadline && aDeadline !== bDeadline) return aDeadline - bDeadline;
    if (aDeadline && !bDeadline) return -1;
    if (!aDeadline && bDeadline) return 1;
    return compareBusinessByPriority(a, b, now);
  }
  if (sort === "newest" || sort === "oldest") {
    const aPosted = getPostedDate(a)?.getTime() || 0;
    const bPosted = getPostedDate(b)?.getTime() || 0;
    if (aPosted !== bPosted) return sort === "newest" ? bPosted - aPosted : aPosted - bPosted;
    return compareBusinessByPriority(a, b, now);
  }
  if (sort === "agency") {
    const agencyDelta = getAgency(a).localeCompare(getAgency(b), "ko-KR");
    return agencyDelta || compareBusinessByPriority(a, b, now);
  }
  return compareBusinessByPriority(a, b, now);
}

export function getBusinessSummary(items, now = new Date()) {
  const activeItems = items.filter(isBusinessActive);
  const sourceCounts = new Map();
  activeItems.forEach((item) => {
    const name = item.source_name || item.source || item.organization || "기타";
    sourceCounts.set(name, (sourceCounts.get(name) || 0) + 1);
  });
  return {
    total: items.length,
    active: activeItems.length,
    closed: items.filter((item) => getBusinessStatus(item) === "closed").length,
    unknown: items.filter((item) => getBusinessStatus(item) === "unknown").length,
    dueWithin7: items.filter((item) => isDeadlineWithin(item, 7, now)).length,
    dueWithin30: items.filter((item) => isDeadlineWithin(item, 30, now)).length,
    dueLater: activeItems.filter((item) => {
      const days = getDaysUntilDeadline(item, now);
      return days === null || days > 30;
    }).length,
    recentlyPosted7: items.filter((item) => isRecentlyPosted(item, 7, now)).length,
    important: items.filter((item) => item.is_known_important === true).length,
    sourceCounts: [...sourceCounts.entries()].sort((a, b) => b[1] - a[1]),
  };
}
