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
const byId = (id) => companies.find((company) => company.company_id === id);
const verifiedIds = new Set([
  "gs-ec", "hyundai-engineering", "samsung-ct-construction", "dl-enc",
  "yuchang-enc", "kumkang-kind", "nrb", "planm", "geogwang-enterprise", "sungji-steel",
]);

assert.equal(v2.schema_version, "2.0.0");
assert.equal(companies.length, 11);
assert.equal(companies.filter((company) => company.company_id === "daeseung-engineering").length, 1);
assert.equal(v2.companies.length, 10);
assert.equal(v2.materialized_summaries.length, 10);
assert.equal(companies.every((company) => company.intelligence_v2?.domain_statuses), true);
assert.equal(companies.every((company) => /[가-힣]/.test(getKoreanCompanySummary(company))), true);
assert.equal(companies.every((company) => !getCompanyDataStatusLabel(company).includes("_")), true);
assert.equal(v2.facts.every((record) => record.visibility === "public"), true);
assert.equal(v2.events.every((record) => record.visibility === "public"), true);
assert.equal(v2.evidence.every((record) => record.visibility === "public"), true);
assert.equal(v2.corrections.every((record) => record.visibility === "public"), true);

for (const id of verifiedIds) {
  assert.equal(byId(id).intelligence_v2.overall_data_status, "core_verified");
  assert.equal(getCompanyDomainStatuses(byId(id)).identity_status, "cross_verified");
  assert.ok(getCompanySourceGroups(byId(id)).some((group) => group.sources.some((source) => source.source_id === `manual-verified-${id}-20260716`)));
}

const yuchang = byId("yuchang-enc");
const legacySamsung = getCompanyEvents(yuchang).find((event) => event.event_id === "event-yuchang-enc-samsung-ai-modular-home");
assert.equal(legacySamsung.event_type, "partnership");
assert.equal(legacySamsung.event_status, "not_signed");
assert.equal(legacySamsung.project_credit, false);
assert.equal(getCompanyProjectSummary(yuchang).verified, 9);
assert.equal(getCompanyProjectSummary(yuchang).partnerships, 1);

const planmEvents = getCompanyEvents(byId("planm"));
assert.equal(planmEvents.find((event) => event.event_id === "event-planm-jindo-baseball-precon").project_credit, false);
assert.equal(planmEvents.find((event) => event.event_id === "event-planm-indiana-l7-precon").project_credit, false);
assert.equal(getCompanyProjectSummary(byId("planm")).verified, 10);
assert.equal(getCompanyProjectSummary(byId("planm")).candidates, 7);

const credited = v2.events.filter((event) => event.project_credit);
assert.ok(credited.length >= 40);
assert.equal(credited.every((event) => event.event_type === "project"), true);
assert.equal(v2.evidence.filter((item) => item.source_type === "manual_verified_research").length, 10);
assert.equal(v2.evidence.filter((item) => item.source_type === "media_article").length, 35);

const factIds = v2.facts.map((item) => item.fact_id);
const eventIds = v2.events.map((item) => item.event_id);
const evidenceIds = v2.evidence.map((item) => item.source_id);
assert.equal(factIds.length, new Set(factIds).size);
assert.equal(eventIds.length, new Set(eventIds).size);
assert.equal(evidenceIds.length, new Set(evidenceIds).size);

console.log("COMPANY INTELLIGENCE V2 FRONTEND TESTS PASSED");
