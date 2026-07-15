import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  getCompanyItems,
  getCompanyProjectSummary,
  getProjectRoleLabel,
  getProjectStatusLabel,
  getStructureTypeLabel,
  matchesCompanySearch,
  representativeProject,
  verifiedCompanyProjects,
} from "../src/companyInsights.js";

const payload = JSON.parse(readFileSync(new URL("../public/data/companies/companies.json", import.meta.url), "utf8"));
const companies = getCompanyItems(payload);
const byId = (id) => companies.find((company) => company.company_id === id);

const direct = companies.filter((company) => company.competitive_role === "direct_competitor");
assert.equal(direct.length, 8);

const kumkang = byId("kumkang-kind");
assert.ok(kumkang);
assert.equal(kumkang.project_portfolio.length, 3);
assert.equal(verifiedCompanyProjects(kumkang).length, 3);
assert.equal(getCompanyProjectSummary(kumkang).verified, 3);
assert.ok(getCompanyProjectSummary(kumkang).latestYear >= 2026);
assert.equal(representativeProject(kumkang).project_id, "kumkang-jangbogo-antarctic-station");

for (const project of kumkang.project_portfolio) {
  assert.ok(project.source_ids.length > 0);
  assert.notEqual(project.company_role, "unknown");
  assert.match(getProjectRoleLabel(project), /모듈러|제작/);
  assert.match(getStructureTypeLabel(project), /스틸 모듈러/);
  assert.notEqual(getProjectStatusLabel(project), "");
  assert.equal(project.contract_amount, null);
}

assert.equal(matchesCompanySearch(kumkang, "장보고"), true);
assert.equal(matchesCompanySearch(kumkang, "평창 조직위원회"), true);
assert.equal(matchesCompanySearch(kumkang, "고령군 모듈러 주거단지"), true);
assert.equal(matchesCompanySearch(kumkang, "스틸 모듈러"), true);

const jinwoo = byId("jinwoo-inc");
assert.ok(jinwoo);
assert.equal(jinwoo.dart_identity.identity_status, "manual_review_required");
assert.equal((jinwoo.project_portfolio || []).length, 0);

const projectIds = companies.flatMap((company) => (company.project_portfolio || []).map((project) => project.project_id));
assert.equal(projectIds.length, new Set(projectIds).size);

console.log("COMPANY PROJECT FRONTEND TESTS PASSED");
