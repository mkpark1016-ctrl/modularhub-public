import assert from "node:assert/strict";
import { compareNewsBySort, getNewsTopic, matchesNewsSearch, parseSearchQuery } from "../src/newsInsights.js";

const items = [
  {
    id: 1,
    title: "Government approves modular housing policy",
    summary: "New regulation for residential building",
    media: "Policy Daily",
    keywords: "modular housing",
    published_at: "2026-07-04",
    relevance_score: 70,
  },
  {
    id: 2,
    title: "Factory expands volumetric modular production",
    summary: "Manufacturer opens new plant",
    media: "Construction News",
    keywords: "factory modular",
    published_at: "2026-07-03",
    relevance_score: 85,
  },
  {
    id: 3,
    title: "Contract awarded for modular school project",
    summary: "Education campus project",
    media: "Projects Weekly",
    keywords: "school project",
    published_at: "2026-07-02",
    relevance_score: 90,
  },
  {
    id: 4,
    title: "Data center uses prefabricated building pods",
    summary: "Server hall expansion",
    media: "Tech Build",
    keywords: "data center",
    published_at: "2026-07-01",
    relevance_score: 95,
  },
];

assert.equal(getNewsTopic(items[0]), "정책·제도");
assert.equal(getNewsTopic(items[1]), "기업·공장");
assert.equal(getNewsTopic(items[2]), "프로젝트·수주");
assert.equal(getNewsTopic(items[3]), "데이터센터");

assert.deepEqual(parseSearchQuery('"modular school" project'), {
  phrases: ["modular school"],
  terms: ["project"],
});
assert.equal(matchesNewsSearch(items[2], "modular school"), true);
assert.equal(matchesNewsSearch(items[2], '"modular school"'), true);
assert.equal(matchesNewsSearch(items[2], "school contract"), true);
assert.equal(matchesNewsSearch(items[2], "school hospital"), false);
assert.equal(matchesNewsSearch(items[1], "factory plant"), true);

const relevanceSorted = [...items].sort((a, b) => compareNewsBySort(a, b, "relevance"));
assert.deepEqual(relevanceSorted.map((item) => item.id), [4, 3, 2, 1]);

const newestSorted = [...items].sort((a, b) => compareNewsBySort(a, b, "newest"));
assert.deepEqual(newestSorted.map((item) => item.id), [1, 2, 3, 4]);

const oldestSorted = [...items].sort((a, b) => compareNewsBySort(a, b, "oldest"));
assert.deepEqual(oldestSorted.map((item) => item.id), [4, 3, 2, 1]);

console.log("NEWS INSIGHT TESTS PASSED");
