import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  compareCompanies,
  companyMatchesFilters,
  formatKrwReadable,
  getCompanyDataStatus,
  getCompanyDomainStatuses,
  getCompanyEvents,
  getCompanyItems,
  getCompanySummary,
  getCompanyTypeLabel,
  getCompetitiveRoleLabel,
  getLatestFinancial,
  getProductionCapacityLabel,
  getProductionModelLabel,
  getTierLabel,
  hasConfirmedProductionFacility,
  matchesCompanySearch,
  metricSourceValue,
  formatProductionArea,
  productionFacilities,
  technologyCount,
} from "../src/companyInsights.js";

const payload = JSON.parse(readFileSync(new URL("../public/data/companies/companies.json", import.meta.url), "utf8"));
const companies = getCompanyItems(payload);

assert.equal(companies.length, payload.companies.length);
assert.equal(companies.length, 17);

const summary = getCompanySummary(companies);
assert.equal(summary.total, 17);
assert.equal(summary.directCompetitors, companies.filter((company) => company.competitive_role === "direct_competitor").length);
assert.equal(summary.coreVerified, companies.filter((company) => getCompanyDataStatus(company) === "core_verified").length);
assert.equal(summary.coreVerified, 1);
assert.equal(summary.facilityConfirmed, companies.filter((company) => hasConfirmedProductionFacility(company)).length);
assert.equal(summary.facilityConfirmed, 2);

const wave1 = ["yuchang-enc", "kumkang-kind", "planm", "daeseung-engineering"].map((id) => companies.find((company) => company.company_id === id));
assert.equal(wave1.every(Boolean), true);
for (const company of wave1) {
  assert.equal(company.dart_identity.identity_status, "confirmed");
  assert.equal(company.financials.length, 3);
  assert.ok(metricSourceValue(getLatestFinancial(company).revenue) !== null);
  assert.equal(getCompanyDomainStatuses(company).financial_status, "official_verified");
}
assert.equal(getCompanyDataStatus(companies.find((company) => company.company_id === "kumkang-kind")), "core_verified");
assert.equal(getCompanyDataStatus(companies.find((company) => company.company_id === "yuchang-enc")), "partially_verified");

const remainingTier1 = ["sungji-steel", "geogwang-enterprise", "m3-systems", "jinwoo-inc"].map((id) => companies.find((company) => company.company_id === id));
assert.equal(remainingTier1.every(Boolean), true);
assert.equal(getCompanyDataStatus(companies.find((company) => company.company_id === "sungji-steel")), "partially_verified");
assert.equal(getCompanyDataStatus(companies.find((company) => company.company_id === "geogwang-enterprise")), "partially_verified");
assert.equal(getCompanyDataStatus(companies.find((company) => company.company_id === "m3-systems")), "partially_verified");
assert.equal(companies.find((company) => company.company_id === "jinwoo-inc").dart_identity.identity_status, "manual_review_required");

const direct = companies.filter((company) => companyMatchesFilters(company, { q: "", role: "all", relationship: "direct_competitor", tier: "all", status: "all" }));
assert.equal(direct.length, summary.directCompetitors);
const tier1 = companies.filter((company) => companyMatchesFilters(company, { q: "", role: "all", relationship: "all", tier: "tier_1", status: "all" }));
assert.equal(tier1.length, 8);
const verified = companies.filter((company) => companyMatchesFilters(company, { q: "", role: "all", relationship: "all", tier: "all", status: "core_verified" }));
assert.equal(verified.length, summary.coreVerified);
const manufacturers = companies.filter((company) => companyMatchesFilters(company, { q: "", role: "specialist_manufacturer", relationship: "all", tier: "all", status: "all" }));
assert.ok(manufacturers.length > 0);

assert.equal(matchesCompanySearch(companies.find((company) => company.company_id === "planm"), "PlanM"), true);
assert.equal(matchesCompanySearch(companies.find((company) => company.company_id === "kumkang-kind"), "Jang Bogo"), true);
assert.equal(matchesCompanySearch(companies.find((company) => company.company_id === "kumkang-kind"), "Modular Unit System"), true);
assert.equal(matchesCompanySearch(companies.find((company) => company.company_id === "kumkang-kind"), "steel_modular_units"), true);
assert.equal(matchesCompanySearch(companies.find((company) => company.company_id === "yuchang-enc"), "YOOCHANG E&C Factory"), true);
assert.equal(matchesCompanySearch(companies.find((company) => company.company_id === "sungji-steel"), "not-a-real-company-term"), false);

assert.equal(productionFacilities(companies.find((company) => company.company_id === "yuchang-enc")).length, 1);
assert.equal(productionFacilities(companies.find((company) => company.company_id === "kumkang-kind")).length, 1);
assert.equal(hasConfirmedProductionFacility(companies.find((company) => company.company_id === "planm")), false);
assert.equal(hasConfirmedProductionFacility(companies.find((company) => company.company_id === "daeseung-engineering")), false);
assert.equal(getProductionModelLabel(companies.find((company) => company.company_id === "planm")), "공개자료상 생산시설 미확인");
assert.equal(getProductionModelLabel(companies.find((company) => company.company_id === "kumkang-kind")), "자체 생산 확인");
assert.equal(getProductionCapacityLabel(productionFacilities(companies.find((company) => company.company_id === "kumkang-kind"))[0]), "공개자료에서 공식 생산능력 수치가 확인되지 않았습니다.");
assert.equal(formatProductionArea(productionFacilities(companies.find((company) => company.company_id === "yuchang-enc"))[0].site_area, "m2"), "60,427.8 m2");
assert.equal(productionFacilities(companies.find((company) => company.company_id === "yuchang-enc"))[0].capacity_value, null);

assert.equal(getCompanyTypeLabel(companies.find((company) => company.company_id === "kumkang-kind")), "전문 제작사");
assert.equal(getCompetitiveRoleLabel(companies.find((company) => company.company_id === "gs-ec")), "내부 기준");
assert.equal(getTierLabel(companies.find((company) => company.company_id === "haean-architecture")), "장기 관찰");
assert.equal(technologyCount(companies.find((company) => company.company_id === "kumkang-kind")) > 0, true);
const yuchangEvents = getCompanyEvents(companies.find((company) => company.company_id === "yuchang-enc"));
assert.equal(yuchangEvents.length, 1);
assert.equal(yuchangEvents[0].event_type, "partnership");
assert.equal(yuchangEvents[0].project_credit, false);
assert.equal(formatKrwReadable(null), "확인되지 않음");
assert.equal(formatKrwReadable(0), "0원");
assert.match(formatKrwReadable(307_684_467_052), /억원$/);
assert.ok([...companies].sort((a, b) => compareCompanies(a, b, "tier"))[0].analysis_tier.startsWith("tier_1"));

console.log("COMPANY INSIGHT TESTS PASSED");
