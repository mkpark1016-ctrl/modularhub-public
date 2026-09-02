import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  MAX_COMPARISON_COMPANIES,
  compareCompaniesForMvp,
  getComparisonMetric,
  getConfirmedProductionFacilityCount,
  getLatestFinancialYear,
  getLatestOperatingProfit,
  getLatestRevenue,
  getOperatingMargin,
  getPipelineProjectCount,
  getPlannedProductionFacilityCount,
  getTechnologyCount,
  getVerifiedProjectCount,
  normalizeComparisonSelection,
} from "../src/companyComparison.js";
import { compareCompanies, companyMatchesFilters, getCompanyItems, getCompanyProjectSummary, getCompanyTypeLabel, isModularSpecialistCompany } from "../src/companyInsights.js";

const payload = JSON.parse(readFileSync(new URL("../public/data/companies/companies.json", import.meta.url), "utf8"));
const companies = getCompanyItems(payload);
const byId = (id) => companies.find((company) => company.company_id === id);

assert.equal(companies.length, 11);
assert.equal(companies.filter((company) => company.company_type === "general_contractor").length, 4);
assert.equal(companies.filter(isModularSpecialistCompany).length, 7);
assert.equal(getCompanyTypeLabel(byId("nrb")), "모듈러 제작 전문 업체");

const gs = byId("gs-ec");
assert.equal(getLatestFinancialYear(gs), 2025);
assert.equal(getLatestRevenue(gs), 12_450_000_000_000);
assert.equal(getLatestOperatingProfit(gs), 438_000_000_000);
assert.equal(Number(getOperatingMargin(gs).toFixed(1)), 3.5);

const zeroRevenueCompany = { financials: [{ year: 2025, revenue: { source_value: 0 }, operating_profit: { source_value: 100 } }] };
assert.equal(getOperatingMargin(zeroRevenueCompany), null);
assert.equal(getLatestRevenue({ financials: [] }), null);

assert.equal(getConfirmedProductionFacilityCount(byId("dl-enc")), 0);
assert.equal(getPlannedProductionFacilityCount(byId("dl-enc")), 0);
assert.ok(getConfirmedProductionFacilityCount(byId("yuchang-enc")) > 0);

const yuchang = byId("yuchang-enc");
const yuchangMetric = getComparisonMetric(yuchang);
assert.equal(yuchangMetric.latestFinancialYear, 2025);
assert.ok(yuchangMetric.revenue > 0);
assert.ok(yuchangMetric.operatingMargin !== null);
assert.equal(yuchangMetric.technologyCount, getTechnologyCount(yuchang));

assert.equal(getVerifiedProjectCount(yuchang), getCompanyProjectSummary(yuchang).verified);
assert.ok(getPipelineProjectCount(yuchang) > 0);

const producerGroup = companies.filter((company) => companyMatchesFilters(company, { q: "", role: "modular_specialist", relationship: "all", tier: "all", status: "all" }));
assert.equal(producerGroup.length, 7);
assert.equal(companies.filter((company) => companyMatchesFilters(company, { q: "", role: "producer_group", relationship: "all", tier: "all", status: "all" })).length, 7);

const normalized = normalizeComparisonSelection(["gs-ec", "bad-id", "gs-ec", "yuchang-enc", "nrb", "planm", "dl-enc"], companies);
assert.deepEqual(normalized, ["gs-ec", "yuchang-enc", "nrb", "planm"]);
assert.equal(normalized.length, MAX_COMPARISON_COMPANIES);

const revenueSorted = [...companies].sort((a, b) => compareCompaniesForMvp(a, b, "revenue", compareCompanies));
for (let index = 1; index < revenueSorted.length; index += 1) {
  assert.ok(getLatestRevenue(revenueSorted[index - 1]) >= getLatestRevenue(revenueSorted[index]));
}
const technologySorted = [...companies].sort((a, b) => compareCompaniesForMvp(a, b, "technology", compareCompanies));
assert.equal(technologySorted[0].company_id, "hyundai-engineering");

console.log("COMPANY COMPARISON TESTS PASSED");
