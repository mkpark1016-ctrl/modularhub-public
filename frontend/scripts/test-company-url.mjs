import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { getCompanyItems } from "../src/companyInsights.js";
import { COMPANY_SORT_VALUES, sanitizeCompanySearchParams } from "../src/companyUrlParams.js";

const payload = JSON.parse(readFileSync(new URL("../public/data/companies/companies.json", import.meta.url), "utf8"));
const companies = getCompanyItems(payload);
const validValues = {
  roles: ["general_contractor", "modular_specialist"],
  companyIds: companies.map((company) => company.company_id),
};

assert.deepEqual(COMPANY_SORT_VALUES, ["name", "recent_activity", "revenue", "verified_projects"]);

let result = sanitizeCompanySearchParams(new URLSearchParams("role=specialist_manufacturer&relationship=direct_competitor&tier=tier_1&status=core_verified&audit=applied&facility=confirmed&sort=name&q=PlanM"), validValues);
assert.equal(result.changed, true);
assert.equal(result.params.get("role"), "modular_specialist");
assert.equal(result.params.get("q"), "PlanM");
for (const key of ["relationship", "tier", "status", "audit", "facility"]) assert.equal(result.params.has(key), false);

result = sanitizeCompanySearchParams(new URLSearchParams("role=bad&sort=bad&q=PlanM"), validValues);
assert.equal(result.changed, true);
assert.equal(result.params.get("q"), "PlanM");
assert.equal(result.params.has("role"), false);
assert.equal(result.params.has("sort"), false);

result = sanitizeCompanySearchParams(new URLSearchParams("country=US&source=SBS&role=general_contractor"), validValues);
assert.equal(result.changed, true);
assert.equal(result.params.get("role"), "general_contractor");
assert.equal(result.params.has("country"), false);
assert.equal(result.params.has("source"), false);

result = sanitizeCompanySearchParams(new URLSearchParams("role=producer_group&sort=revenue&compare=gs-ec,bad,gs-ec,yuchang-enc,nrb,planm,dl-enc"), validValues);
assert.equal(result.changed, true);
assert.equal(result.params.get("role"), "modular_specialist");
assert.equal(result.params.get("sort"), "revenue");
assert.equal(result.params.get("compare"), "gs-ec,yuchang-enc,nrb,planm");

console.log("COMPANY URL TESTS PASSED");
