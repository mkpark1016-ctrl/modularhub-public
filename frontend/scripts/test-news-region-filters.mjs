import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  compareNewsItems,
  getNewsCollectionLabel,
  getNewsPublisherDomain,
  getNewsPublisherLabel,
  getNewsRegionLabel,
  getNewsRegionType,
  newsRegionCounts,
  newsRegionMatches,
  OVERSEAS_RSS_SOURCE,
} from "../src/newsRegion.js";

const items = [
  {
    id: 1,
    source: "Naver News",
    media: "Domestic Daily",
    publisher_name: "Domestic Publisher",
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
    publisher_name: "Assembly Magazine",
    publisher_domain: "assemblymag.com",
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
    publisher_name: "SBS",
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
  {
    id: 5,
    source: "legacy rss label",
    title: "Legacy overseas RSS without publisher region",
    published_at: "2026-07-01T00:00:00Z",
  },
];

function filterByRegionAndQuery(region, query) {
  const text = query.toLowerCase();
  return items.filter((item) => {
    if (!newsRegionMatches(item, region)) return false;
    return !text || `${item.title || ""} ${getNewsPublisherLabel(item)} ${item.source || ""} ${item.summary || ""}`.toLowerCase().includes(text);
  });
}

assert.equal(OVERSEAS_RSS_SOURCE, "해외 모듈러 RSS");
assert.equal(getNewsRegionType(items[0]), "domestic");
assert.equal(getNewsRegionType(items[1]), "overseas");
assert.equal(getNewsRegionType(items[2]), "domestic");
assert.equal(getNewsRegionType(items[3]), "unknown");
assert.equal(getNewsRegionType(items[4]), "overseas");
assert.equal(getNewsRegionLabel(items[3]), "지역 미확인");
assert.equal(getNewsPublisherLabel(items[0]), "Domestic Publisher");
assert.equal(getNewsPublisherLabel({ media: "Media", source_name: "Source Name", source: "Source" }), "Media");
assert.equal(getNewsPublisherLabel({ source_name: "Source Name", source: "Source" }), "Source Name");
assert.equal(getNewsPublisherLabel({}), "출처 미확인");
assert.equal(getNewsPublisherDomain({ publisher_domain: "news.google.com" }), "");
assert.equal(getNewsPublisherDomain(items[1]), "assemblymag.com");
assert.equal(getNewsCollectionLabel(items[2]), "해외 RSS 수집");
assert.equal(getNewsCollectionLabel(items[0]), "국내 뉴스 검색 수집");

const counts = newsRegionCounts(items);
assert.deepEqual(counts, { all: 5, domestic: 2, overseas: 2, unknown: 1 });
assert.equal(counts.all, counts.domestic + counts.overseas + counts.unknown);
assert.equal(filterByRegionAndQuery("all", "").length, 5);
assert.deepEqual(filterByRegionAndQuery("domestic", "").map((item) => item.id), [1, 3]);
assert.deepEqual(filterByRegionAndQuery("overseas", "").map((item) => item.id), [2, 5]);
assert.deepEqual(filterByRegionAndQuery("unknown", "").map((item) => item.id), [4]);
assert.deepEqual(filterByRegionAndQuery("domestic", "sbs").map((item) => item.id), [3]);
assert.deepEqual(filterByRegionAndQuery("overseas", "school").map((item) => item.id), []);
assert.deepEqual(filterByRegionAndQuery("all", "school").map((item) => item.id), [3]);

const sorted = [...items].sort(compareNewsItems);
assert.equal(sorted[0].id, 2);
assert.equal(sorted.at(-1).id, 3);
assert.doesNotThrow(() => [...items].sort(compareNewsItems), "missing published_at and zero relevance must be safe");

const appSource = readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
assert.match(appSource, /overseas-badge/);
assert.match(appSource, /getNewsRegionLabel/);
assert.match(appSource, /getNewsPublisherLabel/);
assert.match(appSource, /getNewsCollectionLabel/);
assert.match(appSource, /region.*unknown/s);
assert.match(appSource, /original_url/);
assert.match(appSource, /noopener noreferrer/);
assert.match(appSource, /getNewsTopic/);
assert.match(appSource, /FavoriteButton/);

const config = readFileSync(new URL("../../config/news_publisher_regions.json", import.meta.url), "utf8");
const newsRegionSource = readFileSync(new URL("../src/newsRegion.js", import.meta.url), "utf8");
const replacementCharacter = String.fromCharCode(0xfffd);
assert.doesNotThrow(() => JSON.parse(config));
assert.equal(config.includes(replacementCharacter), false);
assert.equal(newsRegionSource.includes(replacementCharacter), false);
assert.match(config, /아시아경제/);
assert.match(config, /연합뉴스/);

const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
assert.match(styles, /segmented-filter/);
assert.match(styles, /active-filter-chips/);
assert.match(styles, /ratio-bar em/);
assert.match(styles, /@media \(max-width: 760px\)/);

console.log("NEWS REGION FILTER TESTS PASSED");
