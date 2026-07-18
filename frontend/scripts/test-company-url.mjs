import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { getCompanyItems } from "../src/companyInsights.js";
import { sanitizeCompanySearchParams } from "../src/companyUrlParams.js";

const payload = JSON.parse(readFileSync(new URL("../public/data/companies/companies.json", import.meta.url), "utf8"));
const companies = getCompanyItems(payload);
const validValues = {
  roles: [...new Set(companies.map((company) => company.company_type).filter(Boolean)), "producer_group"],
  relationships: [...new Set(companies.map((company) => company.competitive_role).filter(Boolean))],
  tiers: [...new Set(companies.map((company) => company.analysis_tier).filter(Boolean))],
  companyIds: companies.map((company) => company.company_id),
};

let result = sanitizeCompanySearchParams(new URLSearchParams("role=specialist_manufacturer&relationship=direct_competitor&tier=tier_1&status=core_verified&sort=name&q=PlanM"), validValues);
assert.equal(result.changed, false);
assert.equal(result.params.get("q"), "PlanM");

result = sanitizeCompanySearchParams(new URLSearchParams("status=verified&q=PlanM"), validValues);
assert.equal(result.changed, true);
assert.equal(result.params.get("status"), "core_verified");

result = sanitizeCompanySearchParams(new URLSearchParams("role=bad&relationship=bad&tier=bad&status=bad&sort=bad&q=PlanM"), validValues);
assert.equal(result.changed, true);
assert.equal(result.params.get("q"), "PlanM");
assert.equal(result.params.has("role"), false);
assert.equal(result.params.has("relationship"), false);
assert.equal(result.params.has("tier"), false);
assert.equal(result.params.has("status"), false);
assert.equal(result.params.has("sort"), false);

result = sanitizeCompanySearchParams(new URLSearchParams("country=US&source=SBS&role=general_contractor"), validValues);
assert.equal(result.params.get("role"), "general_contractor");
assert.equal(result.params.get("country"), "US");
assert.equal(result.params.get("source"), "SBS");

result = sanitizeCompanySearchParams(new URLSearchParams("role=producer_group&sort=revenue&compare=gs-ec,bad,gs-ec,yuchang-enc,nrb,planm,dl-enc"), validValues);
assert.equal(result.changed, true);
assert.equal(result.params.get("role"), "producer_group");
assert.equal(result.params.get("sort"), "revenue");
assert.equal(result.params.get("compare"), "gs-ec,yuchang-enc,nrb,planm");

console.log("COMPANY URL TESTS PASSED");
