import assert from "node:assert/strict";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import {
  getCompanySummary,
  getCompetitiveRoleLabel,
  getStrategicCompetitiveRole,
  isModularSpecialistCompany,
} from "../src/companyInsights.js";

const companiesPath = fileURLToPath(new URL("../public/data/companies/companies.json", import.meta.url));
const payload = JSON.parse(fs.readFileSync(companiesPath, "utf8"));
const companies = Array.isArray(payload) ? payload : payload.companies;
assert.equal(companies.length, 11, "public company universe must remain 11");

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

const nrb = companies.find((company) => company.company_id === "nrb");
assert.ok(nrb, "NRB must exist");
assert.equal(nrb.competitive_role, "substitute_competitor", "raw source-backed classification must remain untouched");
assert.equal(getStrategicCompetitiveRole(nrb), "direct_competitor");
assert.equal(getCompetitiveRoleLabel(nrb), "직접 경쟁사");

const appSource = fs.readFileSync(fileURLToPath(new URL("../src/App.jsx", import.meta.url)), "utf8");
assert.ok(appSource.includes("직접 경쟁 모듈러 업체 {companySummary.directModularCompetitors}개사"));
assert.ok(appSource.includes('monitoringAt={activityState.data?.generatedAt || ""}'));

const cardSource = fs.readFileSync(fileURLToPath(new URL("../src/components/company/CompanyComparisonMvp.jsx", import.meta.url)), "utf8");
assert.ok(cardSource.includes("최근 모니터링 {latestMonitoringAt} · 최근 검증 {latestVerifiedAt}"));

const cssSource = fs.readFileSync(fileURLToPath(new URL("../src/companyUiOverrides.css", import.meta.url)), "utf8");
assert.ok(cssSource.includes("flex-wrap: nowrap"));
assert.ok(cssSource.includes("min-height: 46px"));

console.log("Company strategy and monitoring UI test passed.");
