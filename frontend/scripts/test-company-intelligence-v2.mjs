import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  getCompanyDataStatusLabel,
  getCompanyDomainStatuses,
  getCompanyEvents,
  getCompanyItems,
  getCompanyProjectSummary,
  getCompanySourceGroups,
  getKoreanCompanySummary,
} from "../src/companyInsights.js";

const companiesPayload = JSON.parse(readFileSync(new URL("../public/data/companies/companies.json", import.meta.url), "utf8"));
const v2 = JSON.parse(readFileSync(new URL("../public/data/companies/company_intelligence_v2.json", import.meta.url), "utf8"));
const companies = getCompanyItems(companiesPayload);

assert.equal(v2.schema_version, "2.0.0");
assert.equal(companies.length, 17);
assert.equal(v2.companies.length, 17);
assert.equal(companies.every((company) => company.intelligence_v2?.domain_statuses), true);
assert.equal(companies.every((company) => /[가-힣]/.test(getKoreanCompanySummary(company))), true);
assert.equal(companies.every((company) => !getCompanyDataStatusLabel(company).includes("_")), true);
assert.equal(v2.facts.every((record) => record.visibility === "public"), true);
assert.equal(v2.events.every((record) => record.visibility === "public"), true);
assert.equal(v2.evidence.every((record) => record.visibility === "public"), true);
assert.equal(v2.corrections.every((record) => record.visibility === "public"), true);

const yuchang = companies.find((company) => company.company_id === "yuchang-enc");
const yuchangEvents = getCompanyEvents(yuchang);
assert.equal(yuchangEvents.length, 1);
assert.equal(yuchangEvents[0].event_type, "partnership");
assert.equal(yuchangEvents[0].event_status, "not_signed");
assert.equal(yuchangEvents[0].project_credit, false);
assert.equal(getCompanyProjectSummary(yuchang).verified, 0);
assert.equal(getCompanyProjectSummary(yuchang).partnerships, 1);
assert.equal(getCompanyProjectSummary(yuchang).rawArticleCount, 35);
assert.equal(getCompanyDomainStatuses(yuchang).project_status, "unavailable");

const kumkang = companies.find((company) => company.company_id === "kumkang-kind");
assert.ok(getCompanyProjectSummary(kumkang).verified >= 1);
assert.ok(getCompanyProjectSummary(kumkang).candidates >= 0);
assert.equal(getCompanySourceGroups(kumkang).some((group) => group.group_type === "dart" && group.count >= 3), true);

const credited = v2.events.filter((event) => event.project_credit);
assert.ok(credited.length >= 1);
assert.equal(credited.every((event) => event.event_type === "project"), true);
assert.equal(v2.evidence.filter((item) => item.source_type === "media_article").length, 35);

console.log("COMPANY INTELLIGENCE V2 FRONTEND TESTS PASSED");
