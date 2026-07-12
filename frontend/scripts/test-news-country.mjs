import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  countryOptionLabel,
  getNewsCountryBadgeLabel,
  getNewsCountryFilterValue,
  getNewsDetailCountryLabel,
  getOverseasCountryOptions,
  getPublisherCountryCode,
  getPublisherCountryLabel,
  getPublisherCountryName,
  newsCountryMatches,
} from "../src/newsCountry.js";
import { getNewsDisplayRegion, getNewsDisplayRegionReason, newsRegionCounts } from "../src/newsRegion.js";

const domestic = {
  publisher_country_code: "KR",
  publisher_country_name: "대한민국",
};
const unknown = {
  publisher_country_code: "",
  publisher_country_name: "국가 미확인",
};

assert.equal(getPublisherCountryCode(domestic), "KR");
assert.equal(getPublisherCountryName(domestic), "대한민국");
assert.equal(getPublisherCountryLabel(domestic), "대한민국 (KR)");
assert.equal(getPublisherCountryCode(unknown), "");
assert.equal(getPublisherCountryLabel(unknown), "국가 미확인");
assert.equal(getPublisherCountryLabel({}), "국가 미확인");
assert.equal(getNewsCountryFilterValue({ publisher_country_code: "US", publisher_country_name: "미국", publisher_country_confidence: "high" }), "US");
assert.equal(getNewsCountryFilterValue({ publisher_country_code: "", publisher_country_name: "국가 미확인", publisher_country_confidence: "unknown" }), "unknown");
assert.equal(getNewsCountryFilterValue({ publisher_country_code: "KR", publisher_country_name: "대한민국", publisher_country_confidence: "high" }), "unknown");
assert.equal(getNewsCountryBadgeLabel({ publisher_country_code: "US", publisher_country_name: "미국", publisher_country_confidence: "high" }, "overseas"), "미국");
assert.equal(getNewsCountryBadgeLabel({}, "overseas"), "해외");
assert.equal(getNewsCountryBadgeLabel({}, "domestic"), "국내");
assert.equal(getNewsDetailCountryLabel(unknown), "확인되지 않음");
assert.equal(newsCountryMatches({ publisher_country_code: "AU", publisher_country_name: "호주", publisher_country_confidence: "high" }, "AU"), true);
assert.equal(newsCountryMatches({ publisher_country_code: "AU", publisher_country_name: "호주", publisher_country_confidence: "high" }, "US"), false);

const fixture = [
  { id: 1, publisher_region: "domestic", collection_pipeline: "domestic_pipeline", publisher_country_code: "KR", publisher_country_name: "대한민국", publisher_country_confidence: "high" },
  { id: 2, publisher_region: "overseas", collection_pipeline: "rss_overseas_pipeline", publisher_country_code: "US", publisher_country_name: "미국", publisher_country_confidence: "high" },
  { id: 3, publisher_region: "overseas", collection_pipeline: "rss_overseas_pipeline", publisher_country_code: "AU", publisher_country_name: "호주", publisher_country_confidence: "high" },
  { id: 4, publisher_region: "unknown", collection_pipeline: "rss_overseas_pipeline", publisher_country_code: "", publisher_country_name: "국가 미확인", publisher_country_confidence: "unknown" },
  { id: 5, publisher_region: "unknown", collection_pipeline: "rss_overseas_pipeline", publisher_country_code: "KR", publisher_country_name: "대한민국", publisher_country_confidence: "high" },
  { id: 6, publisher_region: "domestic", collection_pipeline: "rss_overseas_pipeline", publisher_country_code: "KR", publisher_country_name: "대한민국", publisher_country_confidence: "high" },
  { id: 7, publisher_region: "unknown", collection_pipeline: "domestic_pipeline", publisher_country_code: "US", publisher_country_name: "US", publisher_country_confidence: "high" },
  { id: 8, publisher_region: "domestic", collection_pipeline: "rss_overseas_pipeline", publisher_country_code: "", publisher_country_name: "unknown", publisher_country_confidence: "unknown" },
  { id: 9, publisher_region: "unknown", collection_pipeline: "domestic_pipeline", publisher_country_code: "", publisher_country_name: "unknown", publisher_country_confidence: "unknown" },
];
const options = getOverseasCountryOptions(fixture, getNewsDisplayRegion);
assert.deepEqual(options.map((option) => option.value), ["US", "AU", "unknown"]);
assert.equal(options.reduce((sum, option) => sum + option.count, 0), 4);
assert.equal(options[0].count, 2);
assert.match(countryOptionLabel(options[0]), /2$/);
assert.equal(fixture.filter((item) => getNewsDisplayRegion(item) === "overseas" && newsCountryMatches(item, "unknown")).length, 1);
assert.equal(getNewsDisplayRegion(fixture[4]), "domestic");
assert.equal(getNewsDisplayRegionReason(fixture[4]).reason, "publisher_country_code");
assert.equal(getNewsDisplayRegion(fixture[6]), "overseas");
assert.equal(getNewsDisplayRegionReason(fixture[6]).reason, "publisher_country_code");
assert.equal(getNewsDisplayRegion(fixture[7]), "domestic");
assert.equal(getNewsDisplayRegionReason(fixture[7]).reason, "publisher_region");
assert.equal(getNewsDisplayRegion(fixture[8]), "domestic");
assert.equal(getNewsDisplayRegionReason(fixture[8]).reason, "collection_pipeline");

const liveNews = JSON.parse(readFileSync(new URL("../../frontend/public/data/news.json", import.meta.url), "utf8")).items || [];
const liveCounts = newsRegionCounts(liveNews);
const liveOptions = getOverseasCountryOptions(liveNews, getNewsDisplayRegion);
const liveOptionTotal = liveOptions.reduce((sum, option) => sum + option.count, 0);
assert.equal(liveCounts.all, liveCounts.domestic + liveCounts.overseas);
assert.equal(liveOptionTotal, liveCounts.overseas);
assert.equal(liveOptions.some((option) => option.value === "KR"), false);

console.log("NEWS COUNTRY TESTS PASSED");
