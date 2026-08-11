import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const component = fs.readFileSync(path.join(root, "src/components/company/CompanyAuditFinancialPanel.jsx"), "utf8");
const css = fs.readFileSync(path.join(root, "src/companyUiOverrides.css"), "utf8");
const insights = JSON.parse(fs.readFileSync(path.join(root, "public/data/companies/company_report_insights.json"), "utf8"));

const expected = [
  ["cash_generation", "현금창출력"],
  ["profitability", "수익성"],
  ["leverage", "재무안정성"],
  ["working_capital", "운전자본"],
];

const configStart = component.indexOf("const FINANCIAL_DECISION_CONFIG = [");
assert.ok(configStart >= 0, "financial decision config must exist");
const configEnd = component.indexOf("];", configStart);
const configBlock = component.slice(configStart, configEnd + 2);
let previous = -1;
for (const [key, label] of expected) {
  const index = configBlock.indexOf(`key: \"${key}\", label: \"${label}\"`);
  assert.ok(index >= 0, `${key}/${label} must exist in decision config`);
  assert.ok(index > previous, `${key} must preserve the standard decision order`);
  previous = index;
}
assert.ok(!configBlock.includes("receivables_burden"), "receivables burden must stay outside the four core cards");
assert.ok(!configBlock.includes("disclosure_coverage"), "disclosure coverage must stay outside the four core cards");

assert.match(component, /FINANCIAL_DECISION_CONFIG\.map\(\(\{ key, label \}\) =>/);
assert.match(component, /status: \"additional_confirmation_required\"/);
assert.match(component, /data-financial-factor=\{key\}/);
assert.ok(!component.includes(".filter(([, item]) => item)"), "missing factor data must not remove a core card");

assert.match(css, /\.company-intelligence-summary\.compact\.financial-decision-grid\s*\{[\s\S]*?grid-template-columns:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\)/);
assert.ok(!/financial-decision-card:nth-child/.test(css), "card ordering/hiding must not depend on nth-child");
assert.ok(!/financial-status-rule-grid span:nth-child/.test(css), "status-guide ordering/hiding must not depend on nth-child");

const requiredCompanies = ["gs-ec", "samsung-ct-construction", "dl-enc", "hyundai-engineering"];
for (const companyId of requiredCompanies) {
  const company = insights.companies.find((row) => row.company_id === companyId);
  assert.ok(company, `${companyId} report insight must exist`);
  for (const [key] of expected) {
    assert.ok(company.financial_health?.[key], `${companyId} must provide ${key}`);
  }
}

console.log("PASS: financial decision summary is locked to four ordered core cards");
