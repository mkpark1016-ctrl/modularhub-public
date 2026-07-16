import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  getCompanyItems,
  getCompanyProjectSummary,
  getProjectRoleLabel,
  getProjectStatusLabel,
  getStructureTypeLabel,
  matchesCompanySearch,
  projectCandidates,
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
assert.ok(kumkang.project_portfolio.length >= 3);
assert.ok(verifiedCompanyProjects(kumkang).length >= 3);
assert.ok(getCompanyProjectSummary(kumkang).verified >= 1);
assert.ok(getCompanyProjectSummary(kumkang).candidates >= 0);
assert.ok(getCompanyProjectSummary(kumkang).latestYear >= 2026);
assert.equal(representativeProject(kumkang).project_id, "kumkang-jangbogo-antarctic-station");

for (const project of kumkang.project_portfolio) {
  assert.ok(project.source_ids.length > 0);
  assert.notEqual(project.company_role, "unknown");
  assert.notEqual(getProjectRoleLabel(project), "역할 확인 중");
  assert.match(getStructureTypeLabel(project), /스틸 모듈러|PC|하이브리드/);
  assert.notEqual(getProjectStatusLabel(project), "");
  assert.equal(project.contract_amount ?? null, null);
}

assert.equal(matchesCompanySearch(kumkang, "장보고"), true);
assert.equal(matchesCompanySearch(kumkang, "평창 조직위원회"), true);
assert.equal(matchesCompanySearch(kumkang, "고령군 모듈러 주거단지"), true);
assert.equal(matchesCompanySearch(kumkang, "스틸 모듈러"), true);

const jinwoo = byId("jinwoo-inc");
assert.ok(jinwoo);
assert.equal(jinwoo.dart_identity.identity_status, "manual_review_required");
assert.equal((jinwoo.project_portfolio || []).length, 0);

const wave1Targets = companies.filter((company) => company.project_research_status?.research_wave === "wave_1");
assert.equal(wave1Targets.length, 4);
assert.deepEqual(
  wave1Targets.map((company) => company.company_id).sort(),
  ["daeseung-engineering", "planm", "sungji-steel", "yuchang-enc"],
);
assert.ok(wave1Targets.reduce((sum, company) => sum + getCompanyProjectSummary(company).verified, 0) >= 1);
assert.equal(wave1Targets.reduce((sum, company) => sum + getCompanyProjectSummary(company).candidates, 0), 0);
assert.equal(wave1Targets.reduce((sum, company) => sum + getCompanyProjectSummary(company).rawArticleCount, 0), 35);

const yuchang = byId("yuchang-enc");
const yuchangCandidates = projectCandidates(yuchang);
assert.equal(yuchangCandidates.length, 1);
assert.equal(yuchangCandidates[0].source_article_count, 35);
assert.equal(yuchangCandidates[0].possible_company_role, "role_unknown");
assert.equal(yuchangCandidates[0].verification_status, "research_exhausted_no_verified_project");
assert.equal(getCompanyProjectSummary(yuchang).researchStatus, "research_exhausted_no_verified_project");
assert.ok(getCompanyProjectSummary(yuchang).verified >= 1);
assert.equal(getCompanyProjectSummary(yuchang).partnerships, 1);
const hadaewon = yuchang.project_portfolio.find((project) => project.project_id === "yuchang-seongnam-hadaewon-happy-housing");
assert.ok(hadaewon);
assert.equal(hadaewon.project_status, "completed");
assert.equal(hadaewon.project_credit, true);
assert.equal(hadaewon.verification_status, "internally_confirmed");

assert.equal(projectCandidates(byId("planm")).length, 0);
assert.equal(getCompanyProjectSummary(byId("planm")).rawArticleCount, 0);
assert.equal(byId("planm").project_research_status.raw_candidate_article_count, 5);
assert.equal(getCompanyProjectSummary(byId("daeseung-engineering")).researchGapCount, 1);
assert.equal(getCompanyProjectSummary(byId("sungji-steel")).researchGapCount, 1);
assert.equal(matchesCompanySearch(yuchang, yuchangCandidates[0].canonical_project_name), true);

const projectIds = companies.flatMap((company) => (company.project_portfolio || []).map((project) => project.project_id));
assert.equal(projectIds.length, new Set(projectIds).size);

console.log("COMPANY PROJECT FRONTEND TESTS PASSED");
