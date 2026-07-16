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

assert.equal(companies.length, 18);
assert.equal(companies.filter((company) => company.competitive_role === "direct_competitor").length, 8);

const expected = {
  "gs-ec": [3, 0],
  "hyundai-engineering": [3, 0],
  "samsung-ct-construction": [1, 0],
  "dl-enc": [1, 1],
  "yuchang-enc": [10, 0],
  "kumkang-kind": [9, 1],
  "nrb": [7, 0],
  "planm": [13, 4],
  "geogwang-enterprise": [1, 0],
  "sungji-steel": [1, 0],
};

for (const [id, [verified, candidates]] of Object.entries(expected)) {
  const company = byId(id);
  assert.ok(company, `missing ${id}`);
  const summary = getCompanyProjectSummary(company);
  assert.equal(summary.verified, verified, `${id} verified count`);
  assert.equal(summary.candidates, candidates, `${id} candidate count`);
  for (const project of company.project_portfolio || []) {
    assert.ok(project.source_ids.length > 0);
    assert.notEqual(project.company_role, "unknown");
    assert.notEqual(getProjectRoleLabel(project), "역할 확인 중");
    assert.notEqual(getProjectStatusLabel(project), "");
    assert.notEqual(getStructureTypeLabel(project), "");
  }
}

const kumkang = byId("kumkang-kind");
assert.equal(kumkang.project_portfolio.length, 10);
assert.equal(verifiedCompanyProjects(kumkang).length, 10);
assert.equal(representativeProject(kumkang).project_id, "kumkang-jangbogo-antarctic-station");
assert.equal(matchesCompanySearch(kumkang, "고령군 작은정원"), true);
assert.equal(matchesCompanySearch(byId("nrb"), "의왕초평 22층"), true);
assert.equal(matchesCompanySearch(byId("planm"), "APEC 현장진료소"), true);
assert.equal(matchesCompanySearch(byId("dl-enc"), "부여동남"), true);
assert.equal(matchesCompanySearch(byId("sungji-steel"), "정선우체국"), true);

const projectIds = companies.flatMap((company) => (company.project_portfolio || []).map((project) => project.project_id));
assert.equal(projectIds.length, new Set(projectIds).size);

console.log("COMPANY PROJECT FRONTEND TESTS PASSED");
