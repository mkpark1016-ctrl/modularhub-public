import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  REVIEW_TIMING_ORDER,
  compareBusinessBySort,
  getBusinessPriority,
  getBusinessPriorityInfo,
  getBusinessPriorityReasons,
  getBusinessStatus,
  getBusinessSummary,
  isBusinessActionable,
  isDeadlineWithin,
  isImportantBusiness,
  parseDate,
  isRecentlyPosted,
} from "../src/businessInsights.js";

const now = new Date("2026-07-05T00:00:00+09:00");

const d1 = {
  id: 1,
  title: "Urgent modular school",
  opportunity_status: "active",
  posted_at: "2026-07-01",
  due_at: "2026-07-06",
  source_type: "bid",
  amount: 2_000_000_000,
};

const d5 = { ...d1, id: 2, due_at: "2026-07-10" };
const d22 = { ...d1, id: 3, due_at: "2026-07-27" };
const d80 = { ...d1, id: 4, source_type: "procurement_plan", due_at: "2026-09-23" };
const recentAdjacent = { ...d1, id: 5, title: "Routine school equipment", due_at: "2026-07-20", posted_at: "2026-07-03", amount: 0 };
const contest = { ...d1, id: 6, title: "Public housing contest", due_at: "2026-07-20", posted_at: "2026-06-01", source_type: "public_agency_contest", amount: 0 };
const closed = { ...d1, id: 7, opportunity_status: "closed", posted_at: "2026-06-01", due_at: "2026-07-01" };
const closedImportant = { ...d1, id: 8, opportunity_status: "closed", posted_at: "2026-05-11", due_at: "2026-05-11", is_known_important: true };
const canceledUrgent = { ...d1, id: 9, notice_status: "취소공고", due_at: "2026-07-08" };
const knownFuture = { ...recentAdjacent, id: 10, is_known_important: true, due_at: "2026-08-04" };
const unknownWithoutDeadline = { ...contest, id: 11, opportunity_status: "unknown", due_at: "", days_until_deadline: 0 };
const noDeadlineActionable = { ...d1, id: 12, due_at: "", days_until_deadline: undefined };

function expectTiming(item, reviewTiming, reviewLabel) {
  const info = getBusinessPriorityInfo(item, now);
  assert.equal(info.reviewTiming, reviewTiming);
  assert.equal(info.reviewLabel, reviewLabel);
  assert.equal(getBusinessPriority(item, now), reviewTiming);
  return info;
}

assert.equal(expectTiming(d1, "immediate", "즉시 검토").important, true);
assert.equal(expectTiming(d5, "this_week", "이번 주 검토").important, true);
assert.equal(expectTiming(d22, "scheduled", "검토 예정").important, true);
assert.equal(expectTiming(d80, "long_term", "중장기 검토").important, true);
assert.equal(expectTiming(closed, "closed", "마감").important, false);
assert.equal(expectTiming(knownFuture, "scheduled", "검토 예정").priorityLevel, "critical");
assert.equal(getBusinessPriorityInfo(knownFuture, now).important, true);

assert.equal(isBusinessActionable(d1, now), true);
assert.equal(isBusinessActionable(closedImportant, now), false);
assert.equal(isBusinessActionable(canceledUrgent, now), false);
assert.equal(isBusinessActionable(unknownWithoutDeadline, now), false);
assert.equal(isBusinessActionable(noDeadlineActionable, now), true);

assert.equal(isImportantBusiness(d1, now), true);
assert.equal(isImportantBusiness(d22, now), true);
assert.equal(isImportantBusiness(d80, now), true);
assert.equal(isImportantBusiness(recentAdjacent, now), false);
assert.equal(isImportantBusiness(contest, now), false);
assert.equal(isImportantBusiness(closedImportant, now), false);
assert.equal(isImportantBusiness(canceledUrgent, now), false);

assert.ok(getBusinessPriorityReasons(d1, now).includes("마감 D-1"));
assert.ok(getBusinessPriorityReasons(knownFuture, now).includes("기존 중요 사업"));
assert.ok(getBusinessPriorityReasons(d80, now).includes("직접 관련"));
assert.ok(!getBusinessPriorityReasons(closedImportant, now).includes("기존 중요 사업"));

assert.equal(isRecentlyPosted(recentAdjacent, 7, now), true);
assert.equal(isDeadlineWithin(d1, 7, now), true);

const sorted = [d80, closed, d22, d5, d1].sort((a, b) => compareBusinessBySort(a, b, "priority", now));
assert.deepEqual(sorted.map((item) => item.id), [1, 2, 3, 4, 7]);

const deadlineSorted = [d80, d22, d1].sort((a, b) => compareBusinessBySort(a, b, "deadline", now));
assert.deepEqual(deadlineSorted.map((item) => item.id), [1, 3, 4]);

const fixtureItems = [d1, d5, d22, d80, recentAdjacent, contest, closed, closedImportant, canceledUrgent];
const summary = getBusinessSummary(fixtureItems, now);
const quickFilterImportantCount = fixtureItems.filter((item) => isImportantBusiness(item, now)).length;
assert.equal(summary.dueWithin7, 2);
assert.equal(summary.important, quickFilterImportantCount);
assert.equal(summary.important, 4);

const kstBoundaryNow = new Date("2026-07-12T23:30:00+09:00");
assert.equal(getBusinessPriorityInfo({ ...d1, due_at: "2026-07-13" }, kstBoundaryNow).daysRemaining, 1);

const refreshVariants = [
  [...fixtureItems, { ...d1, id: 20, title: "New refresh item", due_at: "2026-07-07" }],
  fixtureItems.filter((item) => item.id !== d5.id),
  fixtureItems.map((item) => item.id === d1.id ? { ...item, opportunity_status: "closed" } : item),
  fixtureItems.map((item) => item.id === d1.id ? { ...item, due_at: "2026-08-20" } : item),
  [...fixtureItems].reverse(),
];

for (const items of refreshVariants) {
  const variantSummary = getBusinessSummary(items, now);
  assert.equal(variantSummary.total, items.length);
  const variantSorted = [...items].sort((a, b) => compareBusinessBySort(a, b, "priority", now));
  assert.equal(variantSorted.length, items.length);
}
assert.equal(getBusinessPriorityInfo({ ...d1, opportunity_status: "closed" }, now).reviewTiming, "closed");
assert.equal(getBusinessPriorityInfo({ ...d1, due_at: "2026-08-20" }, now).reviewTiming, "long_term");

const businessPath = fileURLToPath(new URL("../public/data/business.json", import.meta.url));
const businessItems = JSON.parse(readFileSync(businessPath, "utf8")).items || [];
const asOf = new Date("2026-07-13T07:40:40+09:00");
const allowedOpportunityStatuses = new Set(["active", "closed", "unknown", "canceled", "cancelled"]);
const allowedReviewTimings = new Set(Object.keys(REVIEW_TIMING_ORDER));

assert.ok(Array.isArray(businessItems));
assert.ok(businessItems.length > 0);
assert.equal(new Set(businessItems.map((item) => String(item.id))).size, businessItems.length);

for (const item of businessItems) {
  assert.ok(item.id !== undefined && item.id !== null && String(item.id) !== "");
  assert.ok(typeof item.title === "string" && item.title.trim() !== "");
  if (item.opportunity_status) assert.ok(allowedOpportunityStatuses.has(item.opportunity_status), `unexpected opportunity_status for ${item.id}`);
  for (const field of ["posted_at", "due_at", "deadline_at"]) {
    if (item[field]) assert.ok(parseDate(item[field]), `invalid ${field} for ${item.id}`);
  }
  for (const field of ["amount", "estimated_amount", "budget_amount"]) {
    if (item[field] !== undefined && item[field] !== null && item[field] !== "") {
      assert.ok(Number.isFinite(Number(item[field])), `invalid numeric ${field} for ${item.id}`);
    }
  }
  const info = getBusinessPriorityInfo(item, asOf);
  assert.equal(typeof info.actionable, "boolean");
  assert.equal(typeof info.important, "boolean");
  assert.ok(allowedReviewTimings.has(info.reviewTiming), `unexpected reviewTiming for ${item.id}`);
  assert.ok(typeof info.reviewLabel === "string" && info.reviewLabel.trim() !== "");
  assert.ok(Array.isArray(info.reasons));
  assert.ok(Array.isArray(info.priorityReasons));
  assert.ok(Number.isFinite(info.priorityScore));
  assert.ok(Number.isFinite(info.score));
  assert.ok(info.daysRemaining === null || Number.isFinite(info.daysRemaining));
  if (["closed", "canceled", "cancelled"].includes(getBusinessStatus(item))) {
    assert.equal(info.actionable, false, `closed record should not be actionable: ${item.id}`);
  }
}

const liveSummary = getBusinessSummary(businessItems, asOf);
const liveImportant = businessItems.filter((item) => isImportantBusiness(item, asOf));
assert.equal(liveSummary.important, liveImportant.length);

console.log("BUSINESS INSIGHT TESTS PASSED");
