import assert from "node:assert/strict";
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

const urgent = {
  id: 1,
  title: "Urgent school equipment",
  opportunity_status: "active",
  posted_at: "2026-07-01",
  due_at: "2026-07-08",
  days_until_deadline: 3,
  source_type: "bid",
};

const important = { ...urgent, id: 2, days_until_deadline: 20, due_at: "2026-07-25", is_known_important: true };
const recent = { ...urgent, id: 3, title: "Routine school equipment", days_until_deadline: 15, due_at: "2026-07-20", posted_at: "2026-07-03" };
const recentDirect = { ...recent, id: 7, title: "모듈러 교실 제작 설치", posted_at: "2026-07-04" };
const contest = { ...urgent, id: 4, days_until_deadline: 15, due_at: "2026-07-20", posted_at: "2026-06-01", source_type: "public_agency_contest" };
const watch = { ...urgent, id: 5, days_until_deadline: 40, due_at: "2026-08-20", posted_at: "2026-06-01" };
const closed = { ...urgent, id: 6, opportunity_status: "closed", posted_at: "2026-06-01", days_until_deadline: -1, due_at: "2026-07-01" };
const closedImportant = { ...important, id: 8, opportunity_status: "closed", posted_at: "2026-05-11", days_until_deadline: -55, due_at: "2026-05-11" };
const canceledUrgent = { ...urgent, id: 9, notice_status: "취소공고", days_until_deadline: 3 };
const highValueDirect = { ...watch, id: 10, title: "모듈러 주택 공급 사업", amount: 2_000_000_000 };
const futureHighPriority = { ...highValueDirect, id: 11, is_known_important: true, days_until_deadline: 30 };
const unknownFutureHigh = { ...highValueDirect, id: 12, opportunity_status: "unknown", due_at: "2026-08-15", days_until_deadline: 41 };
const unknownWithoutDeadline = { ...contest, id: 13, opportunity_status: "unknown", due_at: "", days_until_deadline: 0 };

assert.equal(getBusinessPriority(urgent, now), "immediate");
assert.equal(getBusinessPriority(important, now), "immediate");
assert.equal(getBusinessPriority(recent, now), "this_week");
assert.equal(getBusinessPriority(contest, now), "this_week");
assert.equal(getBusinessPriority(watch, now), "watch");
assert.equal(getBusinessPriority(closed, now), "archived");

assert.equal(isBusinessActionable(urgent, now), true);
assert.equal(isBusinessActionable(closedImportant, now), false);
assert.equal(isBusinessActionable(canceledUrgent, now), false);

assert.equal(isImportantBusiness(urgent, now), true);
assert.equal(isImportantBusiness(important, now), true);
assert.equal(isImportantBusiness(closedImportant, now), false);
assert.equal(isImportantBusiness(canceledUrgent, now), false);
assert.equal(isImportantBusiness(recentDirect, now), true);
assert.equal(isImportantBusiness(recent, now), false);
assert.equal(isImportantBusiness(highValueDirect, now), true);
assert.equal(isImportantBusiness(futureHighPriority, now), true);
assert.equal(isImportantBusiness(unknownFutureHigh, now), true);
assert.equal(isBusinessActionable(unknownWithoutDeadline, now), false);

assert.ok(getBusinessPriorityReasons(urgent, now).includes("마감 D-3"));
assert.ok(getBusinessPriorityReasons(important, now).includes("중요공고 후보"));
assert.ok(getBusinessPriorityReasons(recent, now).includes("최근 공고"));
assert.ok(getBusinessPriorityReasons(contest, now).includes("공공기관 공모"));
assert.ok(getBusinessPriorityReasons(watch, now).length > 0);
assert.ok(!getBusinessPriorityReasons(closedImportant, now).includes("중요공고 후보"));

assert.equal(isRecentlyPosted(recent, 7, now), true);
assert.equal(isDeadlineWithin(urgent, 7, now), true);

const sorted = [watch, closed, recent, urgent].sort((a, b) => compareBusinessBySort(a, b, "priority", now));
assert.deepEqual(sorted.map((item) => item.id), [1, 3, 5, 6]);

const scoreSorted = [highValueDirect, urgent].sort((a, b) => compareBusinessBySort(a, b, "priority", now));
assert.deepEqual(scoreSorted.map((item) => item.id), [1, 10]);
assert.ok(getBusinessPriorityInfo(urgent, now).score > getBusinessPriorityInfo(watch, now).score);

const deadlineSorted = [watch, recent, urgent].sort((a, b) => compareBusinessBySort(a, b, "deadline", now));
assert.deepEqual(deadlineSorted.map((item) => item.id), [1, 3, 5]);

const fixtureItems = [urgent, important, recent, recentDirect, contest, watch, closed, closedImportant, canceledUrgent];
const summary = getBusinessSummary(fixtureItems, now);
const quickFilterImportantCount = fixtureItems.filter((item) => isImportantBusiness(item, now)).length;
assert.equal(summary.active, 6);
assert.equal(summary.dueWithin7, 1);
assert.equal(summary.recentlyPosted7, 5);
assert.equal(summary.important, quickFilterImportantCount);
assert.equal(summary.important, 3);

console.log("BUSINESS INSIGHT TESTS PASSED");
