import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  COMPANY_DETAIL_TABS,
  formatPercent,
  metricMargin,
  metricValue,
  sortedFinancials,
  technologyItems,
} from "../src/components/company/companyDetailHelpers.js";
import { getCompanyItems, getCompanyEvents } from "../src/companyInsights.js";

const payload = JSON.parse(readFileSync(new URL("../public/data/companies/companies.json", import.meta.url), "utf8"));
const companies = getCompanyItems(payload);
const byId = (id) => companies.find((company) => company.company_id === id);
const componentFiles = [
  "../src/App.jsx",
  "../src/components/company/CompanyDetailView.jsx",
  "../src/components/company/CompanyDetailHeader.jsx",
  "../src/components/company/CompanyDetailTabs.jsx",
  "../src/components/company/CompanyOverviewTab.jsx",
  "../src/components/company/CompanyFinancialTab.jsx",
  "../src/components/company/CompanyProductionTab.jsx",
  "../src/components/company/CompanyProjectTab.jsx",
  "../src/components/company/CompanyTechnologyTab.jsx",
  "../src/components/company/CompanyEvidenceTab.jsx",
  "../src/components/company/companyDetailHelpers.js",
].map((path) => readFileSync(new URL(path, import.meta.url), "utf8")).join("\n");

assert.equal(companies.length, 10);
assert.deepEqual(COMPANY_DETAIL_TABS.map((tab) => tab.value), ["overview", "financial", "production", "projects", "technology", "evidence"]);
assert.ok(componentFiles.includes("normalizeCompanyTab(searchParams.get(\"tab\")"));
assert.ok(componentFiles.includes("role=\"tablist\""));
assert.ok(componentFiles.includes("role=\"tab\""));
assert.ok(componentFiles.includes("ArrowRight"));
assert.ok(componentFiles.includes("검증 수준"), "company detail should render verification level");
assert.ok(componentFiles.includes("감사보고서 근거 확인"), "financial tab should distinguish audit evidence");
assert.ok(componentFiles.includes("단위"), "financial tab should show source unit/currency");

for (const required of ["established_at", "representative", "employee_count", "major_businesses", "gross_profit"]) {
  assert.ok(componentFiles.includes(required), `${required} must be rendered by company detail components`);
}
assert.equal(componentFiles.includes(".slice(0, 8)"), false);
assert.equal(componentFiles.includes("source.url || source.source_url"), true);

for (const company of companies) {
  const profile = company.company_profile || {};
  assert.ok(profile.established_at || profile.representative || profile.employee_count || profile.major_businesses, `${company.company_id} profile fields missing`);
  const financials = sortedFinancials(company);
  assert.equal(financials.length, 3, `${company.company_id} needs three financial years`);
  for (const row of financials) {
    assert.notEqual(metricValue(row.gross_profit), null, `${company.company_id} ${row.year} gross profit missing`);
    const grossMargin = metricMargin(row.gross_profit, row.revenue);
    const operatingMargin = metricMargin(row.operating_profit, row.revenue);
    assert.doesNotThrow(() => formatPercent(grossMargin));
    assert.doesNotThrow(() => formatPercent(operatingMargin));
  }
}

const expectedTechnologyCounts = {
  "hyundai-engineering": 14,
  "dl-enc": 21,
  nrb: 16,
  planm: 10,
};
for (const [id, expected] of Object.entries(expectedTechnologyCounts)) {
  assert.equal(technologyItems(byId(id)).length, expected, `${id} technology records must all be accessible`);
}

for (const company of companies) {
  const verified = getCompanyEvents(company).filter((event) => event.event_type === "project" && event.project_credit);
  const pipeline = getCompanyEvents(company).filter((event) => event.event_type === "project" && !event.project_credit);
  assert.equal(verified.some((event) => ["mou_signed", "partnership_discussion", "pre_con", "r_and_d", "exhibition", "not_signed"].includes(event.event_status)), false);
  assert.equal(pipeline.some((event) => event.project_credit), false);
}

console.log("COMPANY DETAIL UI TESTS PASSED");
