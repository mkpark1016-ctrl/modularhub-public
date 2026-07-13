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

const CLOSED_STATUS_VALUES = new Set([
  "closed",
  "canceled",
  "cancelled",
  "ended",
  "terminated",
  "completed",
  "awarded",
]);

const CLOSED_TEXT_PATTERNS = [
  /마감/,
  /취소/,
  /종료/,
  /유찰/,
  /계약\s*완료/,
  /closed/i,
  /cancel(?:ed|led|lation)?/i,
  /terminated/i,
  /completed/i,
  /awarded/i,
];

const URGENT_TEXT_PATTERNS = [/긴급/, /urgent/i];
const DIRECT_MODULAR_PATTERNS = [
  /모듈러/,
  /modular/i,
  /프리패브/,
  /프리팹/,
  /조립식/,
  /prefab/i,
  /prefabricated/i,
  /off-?site/i,
];
const HIGH_VALUE_THRESHOLD = 1_000_000_000;

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

function statusText(item) {
  return [
    item?.lifecycle_status,
    item?.opportunity_status,
    item?.notice_status,
    item?.bid_status,
    item?.status,
  ].filter(Boolean).join(" ");
}

function hasClosedSignal(item) {
  const status = String(getBusinessStatus(item) || "").toLowerCase();
  if (CLOSED_STATUS_VALUES.has(status)) return true;
  return CLOSED_TEXT_PATTERNS.some((pattern) => pattern.test(statusText(item)));
}

function hasUrgentSignal(item) {
  return URGENT_TEXT_PATTERNS.some((pattern) => pattern.test(`${item?.title || ""} ${statusText(item)}`));
}

function hasDirectModularSignal(item) {
  if (item?.modular_relevance === "confirmed") return true;
  const text = [
    item?.title,
    item?.summary,
    item?.business_type,
    item?.business_subtype,
    item?.keywords,
  ].filter(Boolean).join(" ");
  return DIRECT_MODULAR_PATTERNS.some((pattern) => pattern.test(text));
}

function getAmountValue(item) {
  const value = Number(item?.amount || item?.estimated_amount || item?.budget_amount);
  return Number.isFinite(value) ? value : 0;
}

function isHighValueBusiness(item) {
  return getAmountValue(item) >= HIGH_VALUE_THRESHOLD;
}

export function isBusinessActionable(item, now = new Date()) {
  if (hasClosedSignal(item)) return false;
  const days = getDaysUntilDeadline(item, now);
  const deadline = getDeadlineDate(item);
  if (days !== null && days < 0) return false;
  const status = getBusinessStatus(item);
  if (status === "active") return true;
  if (deadline && days !== null && days >= 0) return true;
  return false;
}

export function isDeadlineWithin(item, days = 7, now = new Date()) {
  if (!isBusinessActionable(item, now)) return false;
  const diff = getDaysUntilDeadline(item, now);
  return diff !== null && diff >= 0 && diff <= days;
}

export function getBusinessPriorityInfo(item, now = new Date()) {
  const actionable = isBusinessActionable(item, now);
  const deadline = getDaysUntilDeadline(item, now);
  const dueWithin7 = deadline !== null && deadline >= 0 && deadline <= 7;
  const recent = isRecentlyPosted(item, 7, now);
  const direct = hasDirectModularSignal(item);
  const knownImportant = item?.is_known_important === true;
  const urgentSignal = hasUrgentSignal(item);
  const highValue = isHighValueBusiness(item);
  const publicAgencyContest = item?.source_type === "public_agency_contest";
  const reasons = [];

  if (!actionable) {
    return {
      actionable: false,
      score: 0,
      priority: "archived",
      level: "archived",
      important: false,
      reasons: ["마감 사업"],
    };
  }

  let score = 20;
  if (dueWithin7) {
    score += 35;
    reasons.push(deadline === 0 ? "마감 D-Day" : `마감 D-${deadline}`);
  }
  if (knownImportant) {
    score += 25;
    reasons.push("중요공고 후보");
  }
  if (urgentSignal) {
    score += 10;
    reasons.push("긴급");
  }
  if (recent) {
    score += 15;
    reasons.push("최근 공고");
  }
  if (direct) {
    score += 15;
    reasons.push("직접 관련");
  }
  if (publicAgencyContest) {
    score += 10;
    reasons.push("공공기관 공모");
  }
  if (highValue) {
    score += 10;
    reasons.push("고액 사업");
  }

  const priority = dueWithin7 || knownImportant ? "immediate" : (recent || direct || publicAgencyContest ? "this_week" : "watch");
  const level = dueWithin7 || knownImportant
    ? "urgent"
    : ((recent && direct) || (direct && highValue) || score >= 55 ? "high" : (priority === "this_week" ? "normal" : "watch"));
  const important = actionable && (
    dueWithin7 ||
    priority === "immediate" ||
    level === "urgent" ||
    level === "high" ||
    (recent && direct) ||
    (direct && highValue)
  );

  if (!reasons.length) reasons.push("진행 가능");

  return {
    actionable,
    score: Math.min(100, score),
    priority,
    level,
    important,
    reasons,
  };
}

export function isImportantBusiness(item, now = new Date()) {
  return getBusinessPriorityInfo(item, now).important;
}

export function getBusinessPriority(item, now = new Date()) {
  return getBusinessPriorityInfo(item, now).priority;
}

export function getBusinessPriorityLabel(item, now = new Date()) {
  return PRIORITY_LABELS[getBusinessPriority(item, now)];
}

export function getBusinessPriorityReasons(item, now = new Date()) {
  return getBusinessPriorityInfo(item, now).reasons;
}

export function dDayLabel(item, now = new Date()) {
  const diff = getDaysUntilDeadline(item, now);
  if (diff === null) return "";
  if (diff === 0) return "D-Day";
  if (diff > 0) return `D-${diff}`;
  return `마감 ${Math.abs(diff)}일 경과`;
}

export function compareBusinessByPriority(a, b, now = new Date()) {
  const aInfo = getBusinessPriorityInfo(a, now);
  const bInfo = getBusinessPriorityInfo(b, now);
  const priorityDelta = PRIORITY_ORDER[aInfo.priority] - PRIORITY_ORDER[bInfo.priority];
  if (priorityDelta !== 0) return priorityDelta;
  const scoreDelta = bInfo.score - aInfo.score;
  if (scoreDelta !== 0) return scoreDelta;
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
  const activeItems = items.filter((item) => isBusinessActionable(item, now));
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
    important: items.filter((item) => isImportantBusiness(item, now)).length,
    sourceCounts: [...sourceCounts.entries()].sort((a, b) => b[1] - a[1]),
  };
}
