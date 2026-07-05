import assert from "node:assert/strict";
import {
  compareBusinessBySort,
  getBusinessPriority,
  getBusinessPriorityReasons,
  getBusinessSummary,
  isDeadlineWithin,
  isRecentlyPosted,
} from "../src/businessInsights.js";

const now = new Date("2026-07-05T00:00:00+09:00");

const urgent = {
  id: 1,
  title: "Urgent modular school",
  opportunity_status: "active",
  posted_at: "2026-07-01",
  due_at: "2026-07-08",
  days_until_deadline: 3,
  source_type: "bid",
};

const important = { ...urgent, id: 2, days_until_deadline: 20, due_at: "2026-07-25", is_known_important: true };
const recent = { ...urgent, id: 3, days_until_deadline: 15, due_at: "2026-07-20", posted_at: "2026-07-03" };
const contest = { ...urgent, id: 4, days_until_deadline: 15, due_at: "2026-07-20", posted_at: "2026-06-01", source_type: "public_agency_contest" };
const watch = { ...urgent, id: 5, days_until_deadline: 40, due_at: "2026-08-20", posted_at: "2026-06-01" };
const closed = { ...urgent, id: 6, opportunity_status: "closed", days_until_deadline: -1, due_at: "2026-07-01" };

assert.equal(getBusinessPriority(urgent, now), "immediate");
assert.equal(getBusinessPriority(important, now), "immediate");
assert.equal(getBusinessPriority(recent, now), "this_week");
assert.equal(getBusinessPriority(contest, now), "this_week");
assert.equal(getBusinessPriority(watch, now), "watch");
assert.equal(getBusinessPriority(closed, now), "archived");

assert.ok(getBusinessPriorityReasons(urgent, now).includes("마감 D-3"));
assert.ok(getBusinessPriorityReasons(important, now).includes("중요공고"));
assert.ok(getBusinessPriorityReasons(recent, now).includes("최근 등록"));
assert.ok(getBusinessPriorityReasons(contest, now).includes("공공기관 공모"));
assert.ok(getBusinessPriorityReasons(watch, now).length > 0);

assert.equal(isRecentlyPosted(recent, 7, now), true);
assert.equal(isDeadlineWithin(urgent, 7, now), true);

const sorted = [watch, closed, recent, urgent].sort((a, b) => compareBusinessBySort(a, b, "priority", now));
assert.deepEqual(sorted.map((item) => item.id), [1, 3, 5, 6]);

const deadlineSorted = [watch, recent, urgent].sort((a, b) => compareBusinessBySort(a, b, "deadline", now));
assert.deepEqual(deadlineSorted.map((item) => item.id), [1, 3, 5]);

const summary = getBusinessSummary([urgent, important, recent, contest, watch, closed], now);
assert.equal(summary.active, 5);
assert.equal(summary.dueWithin7, 1);
assert.equal(summary.recentlyPosted7, 4);
assert.equal(summary.important, 1);

console.log("BUSINESS INSIGHT TESTS PASSED");
