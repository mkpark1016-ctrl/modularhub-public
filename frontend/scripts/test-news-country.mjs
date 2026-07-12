import assert from "node:assert/strict";
import { getPublisherCountryCode, getPublisherCountryLabel, getPublisherCountryName } from "../src/newsCountry.js";

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

console.log("NEWS COUNTRY TESTS PASSED");
