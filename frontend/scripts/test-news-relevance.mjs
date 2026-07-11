import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  compareNewsByRelevance,
  compareNewsBySort,
  getNewsRelevance,
  getNewsRelevanceLabel,
  getNewsSummary,
  newsScore,
  selectHomeBriefingNews,
} from "../src/newsInsights.js";
import { buildDashboardSummary } from "../src/dashboardSummary.js";

function item(title, summary = "", extra = {}) {
  return {
    id: title,
    title,
    summary,
    media: "Fixture",
    published_at: extra.published_at || "2026-07-05T00:00:00+09:00",
    keywords: extra.keywords || [],
    relevance_score: extra.relevance_score ?? 80,
    ...extra,
  };
}

const directFixtures = [
  item("[시사금융용어] 모듈러 주택"),
  item("정부, 모듈러 주택 공급 확대"),
  item("Modular housing factory opens in Cleveland"),
];

for (const fixture of directFixtures) {
  assert.equal(getNewsRelevance(fixture), "direct", `${fixture.title} should be direct`);
  assert.equal(getNewsRelevanceLabel(fixture), "직접 관련");
}

const adjacent = item("Modular hospital wing project advances", "A healthcare facility construction project uses modular units.");
assert.equal(getNewsRelevance(adjacent), "adjacent");

const aiDataCenter = item("[단독] 삼성, 춘천에 AI데이터센터 짓는다");
const aiDataCenterWithKeyword = item(
  "[단독]삼성, 춘천에 AI데이터센터 짓는다",
  "건축허가를 신청했고 일부 모듈러 기술을 활용한다.",
  { keywords: "모듈러 건축" },
);
const homeAi = item("산업 하프타임, 공간·로봇 품은 홈 AI");
const smartConstruction = item("전문건설의 미래, 스마트 건설기술이 좌우");
assert.notEqual(getNewsRelevance(aiDataCenter), "direct");
assert.equal(getNewsRelevance(aiDataCenterWithKeyword), "reference");
assert.notEqual(getNewsRelevance(homeAi), "direct");
assert.notEqual(getNewsRelevance(smartConstruction), "direct");
assert.equal(getNewsRelevance(homeAi), "excluded");
assert.equal(getNewsRelevance(smartConstruction), "reference");

assert.equal(getNewsRelevance(item("Software module gets security update", "software component release")), "excluded");
assert.equal(getNewsRelevance(item("Small modular reactor investment announced")), "excluded");
assert.equal(getNewsRelevance(item("Legacy text fallback", "", { relevance_level: "direct" })), "direct");
assert.equal(newsScore(item("Oversized score", "", { relevance_score: 123 })), 100);
assert.equal(newsScore(item("Negative score", "", { relevance_score: -5 })), 0);

const pool = [
  smartConstruction,
  homeAi,
  item("General investment story", "A company announces AI products."),
  item("Modular building project starts", "", { published_at: "2026-07-06T00:00:00+09:00" }),
  adjacent,
];
const home = selectHomeBriefingNews(pool, 5);
assert.ok(home.length >= 2);
assert.ok(home.every((entry) => ["direct", "adjacent"].includes(getNewsRelevance(entry))));
assert.ok(!home.some((entry) => ["reference", "excluded"].includes(getNewsRelevance(entry))));
assert.equal([...pool].sort(compareNewsByRelevance)[0].title, "Modular building project starts");

const relevanceSorted = [
  item("Adjacent high score", "", { relevance_level: "adjacent", relevance_score: 80, published_at: "2026-07-06T00:00:00+09:00" }),
  item("Direct lower score", "", { relevance_level: "direct", relevance_score: 60, published_at: "2026-07-01T00:00:00+09:00" }),
  item("Direct higher score", "", { relevance_level: "direct", relevance_score: 70, published_at: "2026-07-01T00:00:00+09:00" }),
  item("Direct newer same score", "", { relevance_level: "direct", relevance_score: 70, published_at: "2026-07-05T00:00:00+09:00" }),
].sort((a, b) => compareNewsBySort(a, b, "relevance"));
assert.deepEqual(
  relevanceSorted.map((entry) => entry.title),
  ["Direct newer same score", "Direct higher score", "Direct lower score", "Adjacent high score"],
);

const summaryAsOf = new Date("2026-07-06T12:00:00+09:00");
const summaryFixtures = [
  item("정부, 모듈러 주택 공급 확대", "", { published_at: "2026-07-06T09:00:00+09:00" }),
  item("Modular housing factory opens in Cleveland", "", { published_at: "2026-07-05T09:00:00+09:00" }),
  item("Modular hospital wing project advances", "A healthcare facility construction project uses modular units.", { published_at: "2026-07-04T09:00:00+09:00" }),
  item("Modular construction project from last month", "", { published_at: "2026-06-20T09:00:00+09:00" }),
  item("전문건설의 미래, 스마트 건설기술이 좌우", "", { published_at: "2026-06-20T09:00:00+09:00" }),
  item("Software module gets security update", "software component release", { published_at: "2026-06-20T09:00:00+09:00" }),
];
const newsSummary = getNewsSummary(summaryFixtures, summaryAsOf);
assert.equal(newsSummary.recent7, 3);
assert.equal(newsSummary.recentDirect7, 2);
assert.equal(newsSummary.recentAdjacent7, 1);

const dashboardSummary = buildDashboardSummary({
  businessSummary: {
    total: 167,
    active: 10,
    dueWithin7: 2,
    recentlyPosted7: 3,
    important: 1,
  },
  newsSummary: {
    total: 977,
    recent7: 3,
    recentDirect7: 2,
    recentAdjacent7: 1,
  },
});
assert.deepEqual(dashboardSummary, {
  active: 10,
  dueWithin7: 2,
  recentlyPosted7: 3,
  important: 1,
  recentNews7: 3,
  recentDirect7: 2,
  recentAdjacent7: 1,
});
assert.equal(Object.hasOwn(dashboardSummary, "total"), false, "business/news total fields must not collide");

const appSource = readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
const dashboardSummarySource = readFileSync(new URL("../src/components/DashboardSummary.jsx", import.meta.url), "utf8");
assert.match(appSource, /relevance/);
assert.match(appSource, /오늘 확인할 사업과/);
assert.match(appSource, /모듈러 시장 뉴스/);
assert.match(appSource, /NEWS_RELEVANCE_FILTERS/);
assert.match(appSource, /buildDashboardSummary/);
assert.match(dashboardSummarySource, /data-kpi/);
assert.match(dashboardSummarySource, /recent-direct-news/);

console.log("NEWS RELEVANCE TESTS PASSED");
