import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { matchesNewsSearch } from "../src/newsInsights.js";
import { normalizeSearchCommitValue, shouldCommitSearchValue } from "../src/searchInput.js";

const decomposed = "사상초등학교 모듈러 교실";
const composed = "사상초등학교 모듈러 교실";
assert.equal(normalizeSearchCommitValue(decomposed), composed);
assert.equal(normalizeSearchCommitValue("서울 모듈러 기숙사"), "서울 모듈러 기숙사");
assert.equal(normalizeSearchCommitValue('"modular housing" factory'), '"modular housing" factory');
assert.equal(normalizeSearchCommitValue(composed).includes(String.fromCharCode(0xfffd)), false);
assert.equal(shouldCommitSearchValue(composed, composed), false);
assert.equal(shouldCommitSearchValue("국내 모듈러 주택", composed), true);

const fixture = {
  title: "사상초등학교 모듈러 교실 설치",
  summary: "서울 모듈러 기숙사와 국내 모듈러 주택 사례",
  publisher_name: "아시아경제",
  publisher_domain: "view.asiae.co.kr",
  collection_source: "해외 모듈러 RSS",
  keywords: ["modular housing", "factory"],
};
assert.equal(matchesNewsSearch(fixture, "사상초등학교 모듈러 교실"), true);
assert.equal(matchesNewsSearch(fixture, "서울 모듈러 기숙사"), true);
assert.equal(matchesNewsSearch(fixture, "아시아경제"), true);
assert.equal(matchesNewsSearch(fixture, "view.asiae.co.kr"), true);
assert.equal(matchesNewsSearch(fixture, '"modular housing" factory'), true);

const appSource = readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
assert.match(appSource, /onCompositionStart/);
assert.match(appSource, /onCompositionEnd/);
assert.match(appSource, /onKeyDown/);
assert.match(appSource, /onBlur/);
assert.match(appSource, /isComposing/);
assert.match(appSource, /debounceMs = 300/);
assert.match(appSource, /skipNextChangeRef/);
assert.match(appSource, /next\.toString\(\) === before/);
assert.doesNotMatch(appSource, /<label>출처/);

console.log("NEWS SEARCH IME TESTS PASSED");
