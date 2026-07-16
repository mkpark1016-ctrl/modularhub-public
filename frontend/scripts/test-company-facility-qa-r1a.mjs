import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const companiesPayload = JSON.parse(
  readFileSync(new URL("../public/data/companies/companies.json", import.meta.url), "utf8"),
);
const v2Payload = JSON.parse(
  readFileSync(new URL("../public/data/companies/company_intelligence_v2.json", import.meta.url), "utf8"),
);
const appSource = readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");

const company = companiesPayload.companies.find((item) => item.company_id === "kumkang-kind");
assert.ok(company, "Kumkang Kind company record is required");

const facilities = company.production.filter((item) => item.facility_id?.startsWith("kumkang-kind-"));
const byId = new Map(facilities.map((item) => [item.facility_id, item]));
assert.equal(byId.size, facilities.length, "facility_id values must be unique");

const jincheon = byId.get("kumkang-kind-jincheon-factory");
const boeun1 = byId.get("kumkang-kind-boeun-factory");
const boeun2 = byId.get("kumkang-kind-boeun-2-factory");
assert.ok(jincheon && boeun1 && boeun2, "all three pilot facilities are required");

assert.equal(jincheon.facility_name, "진천공장");
assert.equal(jincheon.data_confidence, "low");
assert.match(jincheon.verification_basis_label, /내부 조사/);
assert.equal(jincheon.reported_capacity ?? jincheon.capacity_value, null);

assert.equal(boeun1.facility_name, "보은 제1공장");
assert.equal(boeun2.facility_name, "보은 제2공장");
assert.notEqual(boeun1.address, boeun2.address, "Boeun facilities must have distinct addresses");
assert.ok(boeun1.facility_aliases.includes("보은공장"));
assert.ok(boeun2.facility_aliases.includes("보은2공장"));
assert.equal(
  boeun1.facility_aliases.filter((alias) => boeun2.facility_aliases.includes(alias)).length,
  0,
  "Boeun facility aliases must not collide",
);
assert.match(boeun1.identity_note, /동일 시설/);
assert.match(boeun2.identity_note, /별도 주소/);
assert.equal(boeun1.reported_capacity ?? boeun1.capacity_value, null);
assert.equal(boeun2.reported_capacity ?? boeun2.capacity_value, null);

for (const facility of [jincheon, boeun1, boeun2]) {
  const field = `facility_${facility.facility_id}`;
  const fact = v2Payload.facts.find(
    (item) => item.company_id === "kumkang-kind" && item.domain === "production" && item.field === field,
  );
  assert.ok(fact, `V2 production fact missing: ${field}`);
  assert.equal(fact.value.facility_name, facility.facility_name);
  assert.equal(fact.value.address, facility.address);
  assert.equal(fact.value.verification_basis_label, facility.verification_basis_label);
}

assert.match(appSource, /item\.display_name \|\| item\.facility_name/);
assert.match(appSource, /주소: \{item\.address\}/);
assert.match(appSource, /근거 기준: \{item\.verification_basis_label\}/);
assert.match(appSource, /신뢰도:/);
assert.doesNotMatch(appSource, /<span>검증 상태: \{getConfidenceLabel/);

console.log("QA-R1A KUMKANG FACILITY TESTS PASSED");
