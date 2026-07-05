import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { compareNewsItems, getNewsRegionType, newsRegionCounts, newsRegionMatches, OVERSEAS_RSS_SOURCE } from "../src/newsRegion.js";

const items = [
  {
    id: 1,
    source: "네이버뉴스",
    media: "domestic.example",
    title: "국내 모듈러 뉴스",
    summary: "국내 기사",
    published_at: "2026-07-02T00:00:00+09:00",
    relevance_score: 0,
  },
  {
    id: 2,
    source: OVERSEAS_RSS_SOURCE,
    media: "Construction Dive",
    title: "Modular housing project opens",
    summary: "Overseas modular construction item",
    published_at: "2026-07-03T00:00:00Z",
    relevance_score: 90,
    original_url: "https://publisher.example/news",
  },
  {
    id: 3,
    source: OVERSEAS_RSS_SOURCE,
    media: "Construction Index",
    title: "Prefabricated school building approved",
    summary: "Factory-built school",
    published_at: "",
    relevance_score: "not-a-number",
    original_url: "https://publisher.example/school",
  },
];

function filterByRegionAndQuery(region, query) {
  const text = query.toLowerCase();
  return items.filter((item) => {
    if (!newsRegionMatches(item, region)) return false;
    return !text || `${item.title || ""} ${item.media || ""} ${item.source || ""} ${item.summary || ""}`.toLowerCase().includes(text);
  });
}

assert.equal(getNewsRegionType(items[0]), "domestic");
assert.equal(getNewsRegionType(items[1]), "overseas");

assert.deepEqual(newsRegionCounts(items), { all: 3, domestic: 1, overseas: 2 });
assert.equal(filterByRegionAndQuery("all", "").length, 3);
assert.deepEqual(filterByRegionAndQuery("domestic", "").map((item) => item.id), [1]);
assert.deepEqual(filterByRegionAndQuery("overseas", "").map((item) => item.id), [2, 3]);
assert.deepEqual(filterByRegionAndQuery("overseas", "school").map((item) => item.id), [3]);
assert.deepEqual(filterByRegionAndQuery("overseas", "국내").map((item) => item.id), []);

const sorted = [...items].sort(compareNewsItems);
assert.equal(sorted[0].id, 2);
assert.equal(sorted.at(-1).id, 3);
assert.doesNotThrow(() => [...items].sort(compareNewsItems), "missing published_at and zero relevance must be safe");

const appSource = readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
assert.match(appSource, /overseas-badge/);
assert.match(appSource, /original_url/);
assert.match(appSource, /noopener noreferrer/);
assert.match(appSource, /현재 조건에 맞는 해외 모듈러 뉴스가 없습니다\./);
assert.match(appSource, /getNewsTopic/);
assert.match(appSource, /FavoriteButton/);

const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
assert.match(styles, /segmented-filter/);
assert.match(styles, /active-filter-chips/);
assert.match(styles, /@media \(max-width: 760px\)/);

console.log("NEWS REGION FILTER TESTS PASSED");
