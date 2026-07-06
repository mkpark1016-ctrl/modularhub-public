import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  compareNewsByRelevance,
  getNewsRelevance,
  getNewsRelevanceLabel,
  selectHomeBriefingNews,
} from "../src/newsInsights.js";

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

const appSource = readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
assert.match(appSource, /relevance/);
assert.match(appSource, /오늘 확인할 사업과/);
assert.match(appSource, /모듈러 시장 뉴스/);
assert.match(appSource, /NEWS_RELEVANCE_FILTERS/);

console.log("NEWS RELEVANCE TESTS PASSED");
