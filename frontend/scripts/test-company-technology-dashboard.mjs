import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { technologyItems } from "../src/components/company/companyDetailHelpers.js";
import {
  filterTechnologyItems,
  formatPatentClassification,
  isKiprisLinkedTechnology,
  isPatentClassificationCode,
  resolvedTechnologySources,
  technologyField,
  technologyFieldDistribution,
  technologyOverview,
  technologyPrimaryNumber,
} from "../src/technologyDashboard.js";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(scriptDir, "..");
const payload = JSON.parse(readFileSync(resolve(frontendRoot, "public/data/companies/companies.json"), "utf8"));
const componentSource = readFileSync(resolve(frontendRoot, "src/components/company/CompanyTechnologyTab.jsx"), "utf8");
const byId = (companyId) => payload.companies.find((company) => company.company_id === companyId);

const gs = byId("gs-ec");
const gsItems = technologyItems(gs);
const gsOverview = technologyOverview(gs, gsItems);
assert.deepEqual(gsOverview, { total: 7, registered: 7, kipris: 4, evidenceLinked: 7 });
assert.equal(gsItems.filter(isKiprisLinkedTechnology).length, 4);
assert.equal(gsItems.every((item) => resolvedTechnologySources(gs, item).length === 1), true);

const fieldDistribution = technologyFieldDistribution(gsItems);
assert.equal(fieldDistribution.reduce((total, entry) => total + entry.count, 0), 7);
assert.equal(new Set(fieldDistribution.map((entry) => entry.field)).size, fieldDistribution.length);
for (const entry of fieldDistribution) {
  assert.equal(filterTechnologyItems(gsItems, { field: entry.field }).length, entry.count);
}

const kiprisPatent = gsItems.find((item) => item.technology_id === "tech-gs-ec-kipris-1020220119658");
assert.ok(kiprisPatent);
assert.equal(isPatentClassificationCode(kiprisPatent.technology_area), true);
assert.notEqual(technologyField(kiprisPatent), kiprisPatent.technology_area);
assert.equal(technologyField(kiprisPatent), "구조·접합");
assert.equal(technologyField(kiprisPatent).startsWith("E04"), false);
assert.equal(formatPatentClassification(kiprisPatent.technology_area).includes(" · "), true);
assert.equal(formatPatentClassification(kiprisPatent.technology_area).includes("|"), false);

assert.equal(filterTechnologyItems(gsItems, { query: "10-2767025" }).length, 1);
assert.equal(filterTechnologyItems(gsItems, { query: "10-2022-0119658" }).length, 1);
assert.equal(filterTechnologyItems(gsItems, { recordType: "patent" }).length, 7);
assert.equal(filterTechnologyItems(gsItems, { status: "registered" }).length, 7);
assert.equal(filterTechnologyItems(gsItems, { query: "definitely-no-result" }).length, 0);

assert.deepEqual(technologyPrimaryNumber(kiprisPatent), { label: "등록번호", value: "10-2767025" });
assert.deepEqual(technologyPrimaryNumber({ application_number: "10-2024-0000001" }), { label: "출원번호", value: "10-2024-0000001" });
assert.deepEqual(technologyPrimaryNumber({ patent_number: "1029999999999" }), { label: "특허번호", value: "1029999999999" });
assert.deepEqual(technologyPrimaryNumber({}), { label: "번호", value: "번호 확인 중" });

const pendingItem = { ...kiprisPatent, source_ids: ["official:kipris:patent:missing"] };
assert.equal(resolvedTechnologySources(gs, pendingItem).length, 0);
assert.equal(technologyOverview(gs, [pendingItem]).evidenceLinked, 0);

const hyundai = byId("hyundai-engineering");
const hyundaiItems = technologyItems(hyundai);
const hyundaiTypes = new Set(hyundaiItems.map((item) => item.record_type || item.group));
assert.deepEqual(hyundaiTypes, new Set(["construction_new_technology", "patent"]));
assert.equal(filterTechnologyItems(hyundaiItems, { recordType: "construction_new_technology" }).length, 1);
assert.equal(filterTechnologyItems(hyundaiItems, { recordType: "patent" }).length, 23);
assert.deepEqual(technologyOverview(hyundai, hyundaiItems), { total: 24, registered: 23, kipris: 10, evidenceLinked: 24 });
assert.equal(hyundaiItems.filter(isKiprisLinkedTechnology).length, 10);

for (const applicationNumber of [
  "10-2012-0156169",
  "10-2023-0112193",
  "10-2024-0081248",
  "10-2025-0019265",
]) {
  const patent = hyundaiItems.find((item) => item.application_number === applicationNumber);
  assert.ok(patent);
  assert.equal(patent.record_type, "patent");
  assert.equal(patent.status, "registered");
  assert.equal(isKiprisLinkedTechnology(patent), true);
  assert.equal(resolvedTechnologySources(hyundai, patent).length, 1);
}

assert.match(componentSource, /const PAGE_SIZE = 8/);
assert.match(componentSource, /filtered\.slice\(0, visibleCount\)/);
assert.match(componentSource, /setVisibleCount\(PAGE_SIZE\)/);
assert.match(componentSource, /aria-pressed=\{field === entry\.field\}/);
assert.match(componentSource, /조건에 맞는 기술·특허가 없습니다/);
assert.match(componentSource, /필터 초기화/);
assert.match(componentSource, /IPC\/CPC 분류/);
assert.match(componentSource, /technology-evidence-button/);
assert.equal(componentSource.includes("item.technology_area ? labelValue(item.technology_area"), false);

console.log("COMPANY TECHNOLOGY DASHBOARD TESTS PASSED");
