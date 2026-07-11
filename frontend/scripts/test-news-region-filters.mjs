import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { compareNewsItems, getNewsRegionLabel, getNewsRegionType, newsRegionCounts, newsRegionMatches, OVERSEAS_RSS_SOURCE } from "../src/newsRegion.js";

const items = [
  {
    id: 1,
    source: "Naver News",
    media: "Domestic Daily",
    title: "Domestic modular housing news",
    summary: "Domestic article",
    published_at: "2026-07-02T00:00:00+09:00",
    relevance_score: 0,
    publisher_region: "domestic",
    collection_pipeline: "domestic_pipeline",
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
    publisher_region: "overseas",
    collection_pipeline: "rss_overseas_pipeline",
  },
  {
    id: 3,
    source: OVERSEAS_RSS_SOURCE,
    media: "news.sbs.co.kr",
    title: "Prefabricated school building approved",
    summary: "Factory-built school",
    published_at: "",
    relevance_score: "not-a-number",
    original_url: "https://news.google.com/rss/articles/sbs",
    publisher_region: "domestic",
    collection_pipeline: "rss_overseas_pipeline",
    publisher_domain: "news.sbs.co.kr",
  },
  {
    id: 4,
    source: OVERSEAS_RSS_SOURCE,
    media: "Unmapped Publisher",
    title: "Modular housing project",
    summary: "Factory-built housing",
    published_at: "2026-07-01T00:00:00Z",
    relevance_score: 80,
    original_url: "https://news.google.com/rss/articles/unknown",
    publisher_region: "unknown",
    collection_pipeline: "rss_overseas_pipeline",
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
assert.equal(getNewsRegionType(items[2]), "domestic");
assert.equal(getNewsRegionType(items[3]), "unknown");
assert.equal(getNewsRegionLabel(items[3]), "지역 미확인");

assert.deepEqual(newsRegionCounts(items), { all: 4, domestic: 2, overseas: 1, unknown: 1 });
assert.equal(filterByRegionAndQuery("all", "").length, 4);
assert.deepEqual(filterByRegionAndQuery("domestic", "").map((item) => item.id), [1, 3]);
assert.deepEqual(filterByRegionAndQuery("overseas", "").map((item) => item.id), [2]);
assert.deepEqual(filterByRegionAndQuery("overseas", "school").map((item) => item.id), []);
assert.deepEqual(filterByRegionAndQuery("all", "school").map((item) => item.id), [3]);

const sorted = [...items].sort(compareNewsItems);
assert.equal(sorted[0].id, 2);
assert.equal(sorted.at(-1).id, 3);
assert.doesNotThrow(() => [...items].sort(compareNewsItems), "missing published_at and zero relevance must be safe");

const appSource = readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
assert.match(appSource, /overseas-badge/);
assert.match(appSource, /getNewsRegionLabel/);
assert.match(appSource, /original_url/);
assert.match(appSource, /noopener noreferrer/);
assert.match(appSource, /getNewsTopic/);
assert.match(appSource, /FavoriteButton/);

const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
assert.match(styles, /segmented-filter/);
assert.match(styles, /active-filter-chips/);
assert.match(styles, /@media \(max-width: 760px\)/);

console.log("NEWS REGION FILTER TESTS PASSED");
