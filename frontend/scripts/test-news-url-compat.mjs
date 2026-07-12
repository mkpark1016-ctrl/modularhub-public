import assert from "node:assert/strict";
import { NEWS_REGION_VALUES, sanitizeNewsSearchParams } from "../src/newsUrlParams.js";

function sanitize(query) {
  return sanitizeNewsSearchParams(new URLSearchParams(query));
}

assert.deepEqual(NEWS_REGION_VALUES, ["all", "domestic", "overseas"]);

let result = sanitize("");
assert.equal(result.changed, false);
assert.equal(result.params.toString(), "");

result = sanitize("region=domestic");
assert.equal(result.changed, false);
assert.equal(result.params.get("region"), "domestic");

result = sanitize("region=overseas");
assert.equal(result.changed, false);
assert.equal(result.params.get("region"), "overseas");

result = sanitize("region=unknown");
assert.equal(result.changed, true);
assert.equal(result.params.has("region"), false);

result = sanitize("source=SBS");
assert.equal(result.changed, true);
assert.equal(result.params.has("source"), false);

result = sanitize("source=SBS&days=30&sort=relevance");
assert.equal(result.changed, true);
assert.equal(result.params.has("source"), false);
assert.equal(result.params.get("days"), "30");
assert.equal(result.params.get("sort"), "relevance");

result = sanitize("region=unknown&q=모듈러&topic=주거·주택");
assert.equal(result.changed, true);
assert.equal(result.params.has("region"), false);
assert.equal(result.params.get("q"), "모듈러");
assert.equal(result.params.get("topic"), "주거·주택");

result = sanitize("region=overseas&q=modular");
assert.equal(result.changed, false);
assert.equal(result.params.get("region"), "overseas");
assert.equal(result.params.get("q"), "modular");

result = sanitize("region=overseas&country=us&q=modular");
assert.equal(result.changed, true);
assert.equal(result.params.get("country"), "US");
assert.equal(result.params.get("q"), "modular");

result = sanitize("region=overseas&country=unknown&days=30");
assert.equal(result.changed, false);
assert.equal(result.params.get("country"), "unknown");
assert.equal(result.params.get("days"), "30");

result = sanitize("region=domestic&country=US&q=모듈러");
assert.equal(result.changed, true);
assert.equal(result.params.get("region"), "domestic");
assert.equal(result.params.has("country"), false);
assert.equal(result.params.get("q"), "모듈러");

result = sanitize("country=US&q=modular");
assert.equal(result.changed, true);
assert.equal(result.params.has("country"), false);
assert.equal(result.params.get("q"), "modular");

result = sanitize("region=overseas&country=USA");
assert.equal(result.changed, true);
assert.equal(result.params.has("country"), false);

result = sanitize("region=invalid&q=모듈러");
assert.equal(result.changed, true);
assert.equal(result.params.has("region"), false);
assert.equal(result.params.get("q"), "모듈러");

console.log("NEWS URL COMPAT TESTS PASSED");
