import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { getCompanyItems } from "../src/companyInsights.js";
import { sanitizeCompanySearchParams } from "../src/companyUrlParams.js";

const payload = JSON.parse(readFileSync(new URL("../public/data/companies/companies.json", import.meta.url), "utf8"));
const companies = getCompanyItems(payload);
const validValues = {
  roles: ["general_contractor", "modular_specialist"],
  relationships: [...new Set(companies.map((company) => company.competitive_role).filter(Boolean))],
  tiers: [...new Set(companies.map((company) => company.analysis_tier).filter(Boolean))],
  companyIds: companies.map((company) => company.company_id),
};

let result = sanitizeCompanySearchParams(new URLSearchParams("role=specialist_manufacturer&relationship=direct_competitor&tier=tier_1&status=core_verified&sort=name&q=PlanM"), validValues);
assert.equal(result.changed, true);
assert.equal(result.params.get("role"), "modular_specialist");
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
assert.equal(result.params.has("audit"), false);
assert.equal(result.params.has("facility"), false);

result = sanitizeCompanySearchParams(new URLSearchParams("audit=applied&facility=confirmed&sort=production"), validValues);
assert.equal(result.changed, false);
assert.equal(result.params.get("audit"), "applied");
assert.equal(result.params.get("facility"), "confirmed");

result = sanitizeCompanySearchParams(new URLSearchParams("audit=legacy&facility=maybe"), validValues);
assert.equal(result.changed, true);
assert.equal(result.params.has("audit"), false);
assert.equal(result.params.has("facility"), false);

result = sanitizeCompanySearchParams(new URLSearchParams("country=US&source=SBS&role=general_contractor"), validValues);
assert.equal(result.params.get("role"), "general_contractor");
assert.equal(result.params.get("country"), "US");
assert.equal(result.params.get("source"), "SBS");

result = sanitizeCompanySearchParams(new URLSearchParams("role=producer_group&sort=revenue&compare=gs-ec,bad,gs-ec,yuchang-enc,nrb,planm,dl-enc"), validValues);
assert.equal(result.changed, true);
assert.equal(result.params.get("role"), "modular_specialist");
assert.equal(result.params.get("sort"), "revenue");
assert.equal(result.params.get("compare"), "gs-ec,yuchang-enc,nrb,planm");

console.log("COMPANY URL TESTS PASSED");
