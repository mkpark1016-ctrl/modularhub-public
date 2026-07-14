import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  compareCompanies,
  companyMatchesFilters,
  formatKrwReadable,
  getCompanyDataStatus,
  getCompanyItems,
  getCompanySummary,
  getCompanyTypeLabel,
  getCompetitiveRoleLabel,
  getLatestFinancial,
  getTierLabel,
  matchesCompanySearch,
  metricSourceValue,
  technologyCount,
} from "../src/companyInsights.js";

const payload = JSON.parse(readFileSync(new URL("../public/data/companies/companies.json", import.meta.url), "utf8"));
const companies = getCompanyItems(payload);

assert.equal(companies.length, payload.companies.length);
assert.equal(companies.length, 17);

const summary = getCompanySummary(companies);
assert.equal(summary.total, 17);
assert.equal(summary.directCompetitors, companies.filter((company) => company.competitive_role === "direct_competitor").length);
assert.equal(summary.verified, 4);

const wave1 = ["yuchang-enc", "kumkang-kind", "planm", "daeseung-engineering"].map((id) => companies.find((company) => company.company_id === id));
assert.equal(wave1.every(Boolean), true);
for (const company of wave1) {
  assert.equal(getCompanyDataStatus(company), "verified");
  assert.equal(company.dart_identity.identity_status, "confirmed");
  assert.equal(company.financials.length, 3);
  assert.ok(metricSourceValue(getLatestFinancial(company).revenue) !== null);
}

const direct = companies.filter((company) => companyMatchesFilters(company, { q: "", role: "all", relationship: "direct_competitor", tier: "all", status: "all" }));
assert.equal(direct.length, summary.directCompetitors);
const tier1 = companies.filter((company) => companyMatchesFilters(company, { q: "", role: "all", relationship: "all", tier: "tier_1", status: "all" }));
assert.equal(tier1.length, 8);
const verified = companies.filter((company) => companyMatchesFilters(company, { q: "", role: "all", relationship: "all", tier: "all", status: "verified" }));
assert.equal(verified.length, 4);
const manufacturers = companies.filter((company) => companyMatchesFilters(company, { q: "", role: "specialist_manufacturer", relationship: "all", tier: "all", status: "all" }));
assert.ok(manufacturers.length > 0);

assert.equal(matchesCompanySearch(companies.find((company) => company.company_id === "planm"), "PlanM"), true);
assert.equal(matchesCompanySearch(companies.find((company) => company.company_id === "kumkang-kind"), "Jang Bogo"), true);
assert.equal(matchesCompanySearch(companies.find((company) => company.company_id === "kumkang-kind"), "Modular Unit System"), true);
assert.equal(matchesCompanySearch(companies.find((company) => company.company_id === "sungji-steel"), "not-a-real-company-term"), false);

assert.equal(getCompanyTypeLabel(companies.find((company) => company.company_id === "kumkang-kind")), "전문 제작사");
assert.equal(getCompetitiveRoleLabel(companies.find((company) => company.company_id === "gs-ec")), "내부 기준");
assert.equal(getTierLabel(companies.find((company) => company.company_id === "haean-architecture")), "장기 관찰");
assert.equal(technologyCount(companies.find((company) => company.company_id === "kumkang-kind")) > 0, true);
assert.equal(formatKrwReadable(null), "확인되지 않음");
assert.equal(formatKrwReadable(0), "0원");
assert.match(formatKrwReadable(307_684_467_052), /억원$/);
assert.ok([...companies].sort((a, b) => compareCompanies(a, b, "tier"))[0].analysis_tier.startsWith("tier_1"));

console.log("COMPANY INSIGHT TESTS PASSED");
