import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  compareNewsItems,
  getNewsCollectionLabel,
  getNewsDisplayRegion,
  getNewsDisplayRegionReason,
  getNewsDisplayRegionLabel,
  getNewsPublisherDomain,
  getNewsPublisherLabel,
  getNewsRegionLabel,
  getNewsRegionType,
  newsDisplayRegionDiagnostics,
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
    source: "Naver News",
    title: "Unknown publisher from domestic pipeline",
    published_at: "2026-07-01T00:00:00Z",
    publisher_region: "unknown",
    collection_pipeline: "domestic_pipeline",
  },
  {
    id: 6,
    collection_source: OVERSEAS_RSS_SOURCE,
    title: "Missing region but overseas RSS source",
    published_at: "2026-07-01T00:00:00Z",
  },
  {
    id: 7,
    collection_source: "국내 뉴스 검색 수집",
    title: "Missing region but domestic search source",
    published_at: "2026-07-01T00:00:00Z",
  },
  {
    id: 8,
    title: "No region metadata",
    published_at: "2026-07-01T00:00:00Z",
  },
  {
    id: 9,
    title: "Korean publisher through overseas RSS",
    publisher_name: "Chosunbiz",
    publisher_country_code: "KR",
    publisher_country_name: "대한민국",
    publisher_country_confidence: "high",
    publisher_region: "unknown",
    collection_pipeline: "rss_overseas_pipeline",
  },
  {
    id: 10,
    title: "US publisher through domestic pipeline",
    publisher_name: "US Publisher",
    publisher_country_code: "US",
    publisher_country_name: "미국",
    publisher_country_confidence: "high",
    publisher_region: "unknown",
    collection_pipeline: "domestic_pipeline",
  },
  {
    id: 11,
    title: "Unknown country explicit domestic publisher region",
    publisher_country_code: "",
    publisher_country_confidence: "unknown",
    publisher_region: "domestic",
    collection_pipeline: "rss_overseas_pipeline",
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
assert.equal(getNewsDisplayRegion(items[0]), "domestic");
assert.equal(getNewsDisplayRegion(items[1]), "overseas");
assert.equal(getNewsDisplayRegion(items[2]), "domestic");
assert.equal(getNewsDisplayRegion(items[3]), "overseas");
assert.equal(getNewsDisplayRegion(items[4]), "domestic");
assert.equal(getNewsDisplayRegion(items[5]), "overseas");
assert.equal(getNewsDisplayRegion(items[6]), "domestic");
assert.equal(getNewsDisplayRegion(items[7]), "domestic");
assert.equal(getNewsDisplayRegion(items[8]), "domestic");
assert.equal(getNewsDisplayRegionReason(items[8]).reason, "publisher_country_code");
assert.equal(getNewsDisplayRegion(items[9]), "overseas");
assert.equal(getNewsDisplayRegionReason(items[9]).reason, "publisher_country_code");
assert.equal(getNewsDisplayRegion(items[10]), "domestic");
assert.equal(getNewsDisplayRegionReason(items[10]).reason, "publisher_region");
assert.equal(items[3].publisher_region, "unknown");
assert.equal(getNewsRegionType(items[3]), "overseas");
assert.equal(getNewsRegionLabel(items[3]), "해외");
assert.equal(getNewsDisplayRegionLabel(items[0]), "국내");
assert.equal(getNewsPublisherLabel(items[0]), "Domestic Publisher");
assert.equal(getNewsPublisherLabel({ media: "Media", source_name: "Source Name", source: "Source" }), "Media");
assert.equal(getNewsPublisherLabel({ source_name: "Source Name", source: "Source" }), "Source Name");
assert.equal(getNewsPublisherLabel({}), "출처 미확인");
assert.equal(getNewsPublisherDomain({ publisher_domain: "news.google.com" }), "");
assert.equal(getNewsPublisherDomain(items[1]), "assemblymag.com");
assert.equal(getNewsCollectionLabel(items[2]), "해외 RSS 수집");
assert.equal(getNewsCollectionLabel(items[0]), "국내 뉴스 검색 수집");

const counts = newsRegionCounts(items);
assert.deepEqual(counts, { all: 11, domestic: 7, overseas: 4 });
assert.equal(counts.all, counts.domestic + counts.overseas);
assert.equal(Object.hasOwn(counts, "unknown"), false);
assert.equal(filterByRegionAndQuery("all", "").length, 11);
assert.deepEqual(filterByRegionAndQuery("domestic", "").map((item) => item.id), [1, 3, 5, 7, 8, 9, 11]);
assert.deepEqual(filterByRegionAndQuery("overseas", "").map((item) => item.id), [2, 4, 6, 10]);
assert.deepEqual(filterByRegionAndQuery("unknown", "").map((item) => item.id), []);
assert.deepEqual(filterByRegionAndQuery("domestic", "sbs").map((item) => item.id), [3]);
assert.deepEqual(filterByRegionAndQuery("overseas", "school").map((item) => item.id), []);
assert.deepEqual(filterByRegionAndQuery("all", "school").map((item) => item.id), [3]);

const diagnostics = newsDisplayRegionDiagnostics(items);
assert.equal(diagnostics.publisher_country_code, 2);
assert.equal(diagnostics.publisher_region, 4);
assert.equal(diagnostics.collection_pipeline, 2);
assert.equal(diagnostics.collection_source, 2);
assert.equal(diagnostics.fallback_default_domestic, 1);

const sorted = [...items].sort(compareNewsItems);
assert.equal(sorted[0].id, 2);
assert.doesNotThrow(() => [...items].sort(compareNewsItems), "missing published_at and zero relevance must be safe");

const appSource = readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
assert.match(appSource, /overseas-badge/);
assert.match(appSource, /getNewsRegionLabel/);
assert.match(appSource, /getNewsPublisherLabel/);
assert.match(appSource, /getNewsCollectionLabel/);
assert.match(appSource, /countryOptions/);
assert.match(appSource, /getOverseasCountryOptions\(enriched, getNewsRegionType\)/);
assert.match(appSource, /values\.region === "overseas"/);
assert.match(appSource, /<label>국가/);
assert.match(appSource, /sanitizeNewsSearchParams/);
assert.doesNotMatch(appSource, /values\.source/);
assert.doesNotMatch(appSource, /<label>출처/);
assert.match(appSource, /onCompositionStart/);
assert.match(appSource, /onCompositionEnd/);
assert.match(appSource, /normalizeSearchCommitValue/);
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
assert.doesNotMatch(styles, /ratio-bar em/);
assert.match(styles, /@media \(max-width: 760px\)/);

console.log("NEWS REGION FILTER TESTS PASSED");
