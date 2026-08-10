import assert from "node:assert/strict";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import {
  getCompanySummary,
  getCompetitiveRoleLabel,
  getStrategicCompetitiveRole,
  isModularSpecialistCompany,
} from "../src/companyInsights.js";
import {
  applyCompanyStrategy,
  validateCompanyStrategyPayload,
} from "../src/companyStrategy.js";

const companiesPath = fileURLToPath(new URL("../public/data/companies/companies.json", import.meta.url));
const strategyPath = fileURLToPath(new URL("../public/data/companies/company_strategy.json", import.meta.url));
const companyPayload = JSON.parse(fs.readFileSync(companiesPath, "utf8"));
const strategyPayload = JSON.parse(fs.readFileSync(strategyPath, "utf8"));
const rawCompanies = Array.isArray(companyPayload) ? companyPayload : companyPayload.companies;
assert.equal(rawCompanies.length, 11, "public company universe must remain 11");

const validation = validateCompanyStrategyPayload(strategyPayload, rawCompanies);
assert.equal(validation.valid, true, validation.errors.join("\n"));
assert.equal(strategyPayload.records.length, 11);
assert.equal(strategyPayload.records.filter((record) => record.strategic_role === "direct_competitor").length, 7);
assert.equal(strategyPayload.records.filter((record) => record.strategic_role === "inherit").length, 4);

const rawSummary = getCompanySummary(rawCompanies);
assert.equal(rawSummary.directCompetitors, 6, "raw source classification must remain unchanged without strategy overlay");

const companies = applyCompanyStrategy(rawCompanies, strategyPayload);
const summary = getCompanySummary(companies);
assert.equal(summary.total, 11);
assert.equal(summary.generalContractors, 4);
assert.equal(summary.modularSpecialists, 7);
assert.equal(summary.directModularCompetitors, 7);
assert.equal(summary.directCompetitors, 7);
assert.equal(summary.coreVerified, 10, "verification status must remain evidence-based");
assert.equal(summary.roleCounts.find((row) => row.value === "general_contractor")?.count, 4);
assert.equal(summary.roleCounts.find((row) => row.value === "modular_specialist")?.count, 7);
assert.equal(summary.relationshipCounts.find((row) => row.value === "direct_competitor")?.count, 7);

const modularSpecialists = companies.filter(isModularSpecialistCompany);
assert.equal(modularSpecialists.length, 7);
assert.ok(modularSpecialists.every((company) => getStrategicCompetitiveRole(company) === "direct_competitor"));

const rawNrb = rawCompanies.find((company) => company.company_id === "nrb");
const nrb = companies.find((company) => company.company_id === "nrb");
assert.ok(rawNrb && nrb, "NRB must exist");
assert.equal(rawNrb.competitive_role, "substitute_competitor", "raw source-backed classification must remain untouched");
assert.equal(rawNrb.strategy_override, undefined);
assert.equal(nrb.strategy_override.strategic_role, "direct_competitor");
assert.equal(getStrategicCompetitiveRole(nrb), "direct_competitor");
assert.equal(getCompetitiveRoleLabel(nrb), "직접 경쟁사");

const duplicatePayload = structuredClone(strategyPayload);
duplicatePayload.records[1].company_id = duplicatePayload.records[0].company_id;
assert.equal(validateCompanyStrategyPayload(duplicatePayload, rawCompanies).valid, false);

const unknownPayload = structuredClone(strategyPayload);
unknownPayload.records[0].company_id = "unknown-company";
assert.equal(validateCompanyStrategyPayload(unknownPayload, rawCompanies).valid, false);

const appSource = fs.readFileSync(fileURLToPath(new URL("../src/App.jsx", import.meta.url)), "utf8");
assert.ok(appSource.includes('useDataset("companies/company_strategy")'));
assert.ok(appSource.includes("applyCompanyStrategy(getCompanyItems(companyState.data), strategyState.data)"));
assert.ok(appSource.includes("applyCompanyStrategy(getCompanyItems(data), strategyState.data)"));
assert.ok(appSource.includes("직접 경쟁 모듈러 업체 {companySummary.directModularCompetitors}개사"));
assert.ok(appSource.includes('monitoringAt={activityState.data?.generatedAt || ""}'));

const cardSource = fs.readFileSync(fileURLToPath(new URL("../src/components/company/CompanyComparisonMvp.jsx", import.meta.url)), "utf8");
assert.ok(cardSource.includes("최근 모니터링 {latestMonitoringAt} · 최근 검증 {latestVerifiedAt}"));

const cssSource = fs.readFileSync(fileURLToPath(new URL("../src/companyUiOverrides.css", import.meta.url)), "utf8");
assert.ok(cssSource.includes("flex-wrap: nowrap"));
assert.ok(cssSource.includes("min-height: 46px"));

console.log("Company strategy and monitoring UI test passed.");
