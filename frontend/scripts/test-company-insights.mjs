import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  compareCompanies,
  companyRoleOptions,
  companyMatchesFilters,
  formatKrwReadable,
  formatProductionArea,
  getCompanyDataStatus,
  getCompanyDomainStatuses,
  getCompanyEvents,
  getCompanyItems,
  getCompanyResearchGapCount,
  getCompanySummary,
  getCompanyTypeLabel,
  getCompanyVerificationLevel,
  getCompetitiveRoleLabel,
  getLatestFinancial,
  getProductionCapacityLabel,
  getProductionModelLabel,
  getTierLabel,
  getVerificationLevelLabel,
  hasConfirmedProductionFacility,
  isModularSpecialistCompany,
  matchesCompanySearch,
  metricSourceValue,
  productionFacilities,
  technologyCount,
} from "../src/companyInsights.js";
import { DAESEUNG_ENGINEERING_COMPANY } from "../src/data/daeseungEngineeringCompany.js";

const payload = JSON.parse(readFileSync(new URL("../public/data/companies/companies.json", import.meta.url), "utf8"));
const companies = [...getCompanyItems(payload), DAESEUNG_ENGINEERING_COMPANY];
const byId = (id) => companies.find((company) => company.company_id === id);
const verifiedIds = [
  "gs-ec", "hyundai-engineering", "samsung-ct-construction", "dl-enc",
  "yuchang-enc", "kumkang-kind", "nrb", "planm", "geogwang-enterprise", "sungji-steel",
];

assert.equal(companies.length, 11);
const summary = getCompanySummary(companies);
assert.equal(summary.total, 11);
assert.equal(summary.directCompetitors, 6);
assert.equal(summary.coreVerified, 10);
assert.equal(summary.facilityConfirmed, 8);
assert.deepEqual(summary.roleCounts.map((option) => [option.value, option.label, option.count]), [
  ["general_contractor", "건설사", 4],
  ["modular_specialist", "모듈러 제작 전문 업체", 7],
]);
assert.deepEqual(companyRoleOptions(companies).map((option) => [option.value, option.label, option.count]), [
  ["general_contractor", "건설사", 4],
  ["modular_specialist", "모듈러 제작 전문 업체", 7],
]);

for (const id of verifiedIds) {
  const company = byId(id);
  assert.ok(company, `missing ${id}`);
  assert.equal(getCompanyDataStatus(company), "core_verified");
  assert.equal(company.review_status, "verified");
  assert.equal(company.data_confidence, "high");
  assert.equal(company.financials.length, 3);
  assert.ok(metricSourceValue(getLatestFinancial(company).revenue) !== null);
  assert.equal(getCompanyDomainStatuses(company).financial_status, "cross_verified");
}

assert.equal(getCompanyTypeLabel(byId("dl-enc")), "건설사");
assert.equal(getCompanyTypeLabel(byId("planm")), "모듈러 제작 전문 업체");
assert.equal(getCompanyTypeLabel(byId("daeseung-engineering")), "모듈러 제작 전문 업체");
assert.equal(getVerificationLevelLabel(getCompanyVerificationLevel(byId("yuchang-enc"))), "교차 검증");
assert.equal(getVerificationLevelLabel(getCompanyVerificationLevel(byId("daeseung-engineering"))), "부분 검증");
assert.ok(getCompanyResearchGapCount(byId("daeseung-engineering")) > 0);
assert.equal(getCompetitiveRoleLabel(byId("gs-ec")), "내부 기준");
assert.equal(getTierLabel(byId("nrb")), "우선 분석");
assert.equal(matchesCompanySearch(byId("planm"), "인디애나 L7 호텔"), true);
assert.equal(matchesCompanySearch(byId("kumkang-kind"), "장보고"), true);
assert.equal(matchesCompanySearch(byId("yuchang-enc"), "당진 석문 1공장"), true);
assert.equal(matchesCompanySearch(byId("dl-enc"), "구례 돌오마을"), true);
assert.equal(matchesCompanySearch(byId("sungji-steel"), "FAC기둥"), true);
assert.equal(matchesCompanySearch(byId("daeseung-engineering"), "전문 제작사"), true);
assert.equal(matchesCompanySearch(byId("planm"), "모듈러 통합사"), true);

assert.equal(productionFacilities(byId("gs-ec")).length, 3);
assert.equal(productionFacilities(byId("yuchang-enc")).length, 4);
assert.equal(productionFacilities(byId("nrb")).length, 2);
assert.equal(productionFacilities(byId("dl-enc")).length, 0);
assert.equal(hasConfirmedProductionFacility(byId("planm")), true);
assert.equal(hasConfirmedProductionFacility(byId("dl-enc")), false);
assert.equal(getProductionModelLabel(byId("gs-ec")), "자체 생산 확인");
assert.equal(getProductionModelLabel(byId("dl-enc")), "위탁 생산 확인");
assert.match(getProductionCapacityLabel(productionFacilities(byId("kumkang-kind"))[0]), /8,000/);
assert.equal(formatProductionArea(productionFacilities(byId("yuchang-enc"))[0].site_area, "m2"), "36,363.64 m2");

assert.ok(technologyCount(byId("hyundai-engineering")) >= 14);
assert.ok(technologyCount(byId("dl-enc")) >= 21);
assert.ok(technologyCount(byId("nrb")) >= 16);

const yuchangEvents = getCompanyEvents(byId("yuchang-enc"));
const legacySamsung = yuchangEvents.find((event) => event.event_id === "event-yuchang-enc-samsung-ai-modular-home");
assert.ok(legacySamsung);
assert.equal(legacySamsung.event_type, "partnership");
assert.equal(legacySamsung.project_credit, false);
assert.ok(yuchangEvents.some((event) => event.event_id === "event-yuchang-poscoac-acquisition"));

const direct = companies.filter((company) => companyMatchesFilters(company, { q: "", role: "all", relationship: "direct_competitor", tier: "all", status: "all" }));
assert.equal(direct.length, 6);
const modularSpecialists = companies.filter((company) => companyMatchesFilters(company, { q: "", role: "modular_specialist", relationship: "all", tier: "all", status: "all" }));
assert.equal(modularSpecialists.length, 7);
assert.equal(modularSpecialists.every(isModularSpecialistCompany), true);
const verified = companies.filter((company) => companyMatchesFilters(company, { q: "", role: "all", relationship: "all", tier: "all", status: "core_verified" }));
assert.equal(verified.length, 10);
assert.equal(formatKrwReadable(null), "확인되지 않음");
assert.equal(formatKrwReadable(0), "0원");
assert.match(formatKrwReadable(12_450_000_000_000), /억원$/);
assert.ok([...companies].sort((a, b) => compareCompanies(a, b, "tier"))[0].analysis_tier.startsWith("tier_1"));

console.log("COMPANY INSIGHT TESTS PASSED");
