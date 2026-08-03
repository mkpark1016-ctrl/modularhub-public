import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  compareBusinessBySort,
  getBusinessPriority,
  getBusinessPriorityInfo,
  getBusinessPriorityReasons,
  getBusinessSummary,
  isBusinessActionable,
  isDeadlineWithin,
  isImportantBusiness,
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

const businessPath = fileURLToPath(new URL("../public/data/business.json", import.meta.url));
const businessItems = JSON.parse(readFileSync(businessPath, "utf8")).items || [];
const asOf = new Date("2026-07-13T07:40:40+09:00");
const byId = new Map(businessItems.map((item) => [String(item.id), item]));

const jeju = byId.get("54");
const busan = byId.get("5772");
const icheon = byId.get("208");
assert.ok(jeju && busan && icheon, "expected live business fixtures are missing");
assert.deepEqual(
  [jeju, busan, icheon].map((item) => {
    const info = getBusinessPriorityInfo(item, asOf);
    return [String(item.id), info.actionable, info.important, info.reviewTiming, info.reviewLabel];
  }),
  [
    ["54", false, false, "closed", "마감"],
    ["5772", true, true, "immediate", "즉시 검토"],
    ["208", true, true, "long_term", "중장기 검토"],
  ],
);

const liveSummary = getBusinessSummary(businessItems, asOf);
const liveImportant = businessItems.filter((item) => isImportantBusiness(item, asOf));
assert.equal(liveSummary.important, liveImportant.length);
assert.equal(liveImportant.some((item) => String(item.source_record_id || item.bid_no) === "R26BK01510994"), false);

console.log("BUSINESS INSIGHT TESTS PASSED");
