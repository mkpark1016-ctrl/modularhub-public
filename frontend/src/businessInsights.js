export const REVIEW_TIMING_ORDER = {
  immediate: 0,
  this_week: 1,
  scheduled: 2,
  long_term: 3,
  closed: 4,
  archived: 4,
  watch: 3,
};

export const PRIORITY_ORDER = REVIEW_TIMING_ORDER;

export const REVIEW_TIMING_LABELS = {
  immediate: "즉시 검토",
  this_week: "이번 주 검토",
  scheduled: "검토 예정",
  long_term: "중장기 검토",
  closed: "마감",
  archived: "마감",
  watch: "중장기 검토",
};

export const PRIORITY_LABELS = REVIEW_TIMING_LABELS;

const KST_OFFSET_MS = 9 * 60 * 60 * 1000;
const DAY_MS = 24 * 60 * 60 * 1000;

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

function kstDayStamp(value = new Date()) {
  const date = parseDate(value) || new Date();
  const shifted = new Date(date.getTime() + KST_OFFSET_MS);
  return Date.UTC(shifted.getUTCFullYear(), shifted.getUTCMonth(), shifted.getUTCDate());
}

export function startOfDay(value = new Date()) {
  return new Date(kstDayStamp(value) - KST_OFFSET_MS);
}

export function daysBetween(from, to) {
  return Math.round((kstDayStamp(to) - kstDayStamp(from)) / DAY_MS);
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

function reviewTimingForDays(actionable, daysRemaining) {
  if (!actionable) return "closed";
  if (daysRemaining === null) return "scheduled";
  if (daysRemaining <= 3) return "immediate";
  if (daysRemaining <= 7) return "this_week";
  if (daysRemaining <= 30) return "scheduled";
  return "long_term";
}

function priorityBadgeClass(reviewTiming) {
  return reviewTiming === "closed" ? "archived" : reviewTiming;
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
  const daysRemaining = getDaysUntilDeadline(item, now);
  const dueWithin7 = daysRemaining !== null && daysRemaining >= 0 && daysRemaining <= 7;
  const dueWithin3 = daysRemaining !== null && daysRemaining >= 0 && daysRemaining <= 3;
  const recent = isRecentlyPosted(item, 7, now);
  const direct = hasDirectModularSignal(item);
  const knownImportant = item?.is_known_important === true;
  const urgentSignal = hasUrgentSignal(item);
  const highValue = isHighValueBusiness(item);
  const publicAgencyContest = item?.source_type === "public_agency_contest";
  const priorityReasons = [];
  const reviewTiming = reviewTimingForDays(actionable, daysRemaining);
  const reviewLabel = REVIEW_TIMING_LABELS[reviewTiming];

  if (!actionable) {
    return {
      actionable: false,
      important: false,
      priorityScore: 0,
      priorityLevel: "watch",
      priorityReasons: ["마감 사업"],
      daysRemaining,
      reviewTiming,
      reviewLabel,
      reviewBadgeClass: priorityBadgeClass(reviewTiming),
      score: 0,
      priority: reviewTiming,
      level: "watch",
      reasons: ["마감 사업"],
    };
  }

  let priorityScore = 20;
  if (dueWithin7) {
    priorityScore += 35;
    priorityReasons.push(daysRemaining === 0 ? "마감 D-Day" : `마감 D-${daysRemaining}`);
  }
  if (knownImportant) {
    priorityScore += 25;
    priorityReasons.push("기존 중요 사업");
  }
  if (urgentSignal) {
    priorityScore += 10;
    priorityReasons.push("긴급");
  }
  if (recent) {
    priorityScore += 15;
    priorityReasons.push("최근 등록");
  }
  if (direct) {
    priorityScore += 15;
    priorityReasons.push("직접 관련");
  }
  if (publicAgencyContest) {
    priorityScore += 10;
    priorityReasons.push("공공기관 공모");
  }
  if (highValue) {
    priorityScore += 10;
    priorityReasons.push("고액 사업");
  }

  const priorityLevel = dueWithin3 || knownImportant
    ? "critical"
    : (dueWithin7 || (recent && direct) || (direct && highValue) || priorityScore >= 55 ? "high" : (direct || publicAgencyContest ? "normal" : "watch"));
  const important = actionable && (
    dueWithin7 ||
    knownImportant ||
    priorityLevel === "critical" ||
    priorityLevel === "high" ||
    (recent && direct) ||
    (direct && highValue)
  );

  if (!priorityReasons.length) priorityReasons.push("진행 가능");

  const normalizedScore = Math.min(100, priorityScore);
  return {
    actionable,
    important,
    priorityScore: normalizedScore,
    priorityLevel,
    priorityReasons,
    daysRemaining,
    reviewTiming,
    reviewLabel,
    reviewBadgeClass: priorityBadgeClass(reviewTiming),
    score: normalizedScore,
    priority: reviewTiming,
    level: priorityLevel,
    reasons: priorityReasons,
  };
}

export function isImportantBusiness(item, now = new Date()) {
  return getBusinessPriorityInfo(item, now).important;
}

export function getBusinessPriority(item, now = new Date()) {
  return getBusinessPriorityInfo(item, now).reviewTiming;
}

export function getBusinessPriorityLabel(item, now = new Date()) {
  return getBusinessPriorityInfo(item, now).reviewLabel;
}

export function getBusinessPriorityReasons(item, now = new Date()) {
  return getBusinessPriorityInfo(item, now).priorityReasons;
}

export function dDayLabel(item, now = new Date()) {
  const diff = getDaysUntilDeadline(item, now);
  if (diff === null) return "";
  if (diff === 0) return "D-Day";
  if (diff > 0) return `D-${diff}`;
  return `마감 ${Math.abs(diff)}일 경과`;
}

function stableId(value) {
  return String(value?.id || value?.source_record_id || value?.bid_no || value?.plan_no || "");
}

export function compareBusinessByPriority(a, b, now = new Date()) {
  const aInfo = getBusinessPriorityInfo(a, now);
  const bInfo = getBusinessPriorityInfo(b, now);
  const timingDelta = REVIEW_TIMING_ORDER[aInfo.reviewTiming] - REVIEW_TIMING_ORDER[bInfo.reviewTiming];
  if (timingDelta !== 0) return timingDelta;
  const scoreDelta = bInfo.priorityScore - aInfo.priorityScore;
  if (scoreDelta !== 0) return scoreDelta;
  const aDeadline = getDeadlineDate(a)?.getTime();
  const bDeadline = getDeadlineDate(b)?.getTime();
  if (aDeadline && bDeadline && aDeadline !== bDeadline) return aDeadline - bDeadline;
  if (aDeadline && !bDeadline) return -1;
  if (!aDeadline && bDeadline) return 1;
  const aPosted = getPostedDate(a)?.getTime() || 0;
  const bPosted = getPostedDate(b)?.getTime() || 0;
  if (aPosted !== bPosted) return bPosted - aPosted;
  return stableId(a).localeCompare(stableId(b), "ko-KR", { numeric: true });
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
