import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const reportPayload = JSON.parse(
  readFileSync(new URL("../public/data/companies/company_report_insights.json", import.meta.url), "utf8"),
);
const overridesSource = readFileSync(new URL("../src/companyUiOverrides.css", import.meta.url), "utf8");

const sourceHealthKeys = [
  "profitability",
  "cash_generation",
  "leverage",
  "working_capital",
  "disclosure_coverage",
];

const companiesWithHealth = reportPayload.companies.filter((company) => company.financial_health);
assert.ok(companiesWithHealth.length > 0, "at least one company financial_health payload must exist");

for (const company of companiesWithHealth) {
  assert.deepEqual(
    Object.keys(company.financial_health),
    sourceHealthKeys,
    `${company.company_id}: builder financial_health order/shape must remain stable for the presentation contract`,
  );
  assert.ok(
    company.financial_health.disclosure_coverage,
    `${company.company_id}: disclosure coverage must remain available in source data/evidence even when omitted from decision cards`,
  );
}

const byId = (companyId) => reportPayload.companies.find((company) => company.company_id === companyId);
const kumkang = byId("kumkang-kind");
const yuchang = byId("yuchang-enc");
assert.ok(kumkang, "Kumkang financial payload must exist");
assert.ok(yuchang, "Yuchang financial payload must exist");

assert.deepEqual(
  [
    kumkang.financial_health.cash_generation.status,
    kumkang.financial_health.profitability.status,
    kumkang.financial_health.leverage.status,
    kumkang.financial_health.working_capital.status,
  ],
  ["info", "info", "info", "info"],
  "Kumkang four-factor decision states must remain all reference/info",
);

assert.deepEqual(
  [
    yuchang.financial_health.cash_generation.status,
    yuchang.financial_health.profitability.status,
    yuchang.financial_health.leverage.status,
    yuchang.financial_health.working_capital.status,
  ],
  ["watch", "info", "watch", "watch"],
  "Yuchang four-factor decision states must retain the current observation results",
);

assert.match(
  overridesSource,
  /company-intelligence-summary\.compact\.financial-decision-grid\s*\{[\s\S]*?display:\s*grid;[\s\S]*?grid-template-columns:\s*repeat\(4, minmax\(0, 1fr\)\)/,
  "desktop decision summary must be a deterministic four-column grid",
);
assert.match(overridesSource, /financial-decision-card:nth-child\(2\)\s*\{\s*order:\s*1;/, "cash generation must render first");
assert.match(overridesSource, /financial-decision-card:nth-child\(1\)\s*\{\s*order:\s*2;/, "profitability must render second");
assert.match(overridesSource, /financial-decision-card:nth-child\(3\)\s*\{\s*order:\s*3;/, "financial stability must render third");
assert.match(overridesSource, /financial-decision-card:nth-child\(4\)\s*\{\s*order:\s*4;/, "working capital must render fourth");
assert.match(overridesSource, /financial-decision-card:nth-child\(5\)\s*\{\s*display:\s*none;/, "disclosure coverage must be excluded from the visible decision cards");

assert.match(
  overridesSource,
  /financial-status-rule-grid\s*\{[\s\S]*?grid-template-columns:\s*repeat\(4, minmax\(0, 1fr\)\)/,
  "detailed decision thresholds must use the same four-factor structure",
);
assert.match(overridesSource, /financial-status-rule-grid span:nth-child\(5\)\s*\{\s*display:\s*none;/, "disclosure coverage threshold must be omitted from the financial decision guide");
assert.match(overridesSource, /@media \(max-width:\s*1023px\)[\s\S]*?financial-decision-grid[\s\S]*?repeat\(2, minmax\(0, 1fr\)\)/, "tablet decision summary must collapse to two columns");
assert.match(overridesSource, /@media \(max-width:\s*599px\)[\s\S]*?financial-decision-grid[\s\S]*?grid-template-columns:\s*1fr/, "mobile decision summary must collapse to one column");

console.log("COMPANY FINANCIAL FOUR-FACTOR SUMMARY TESTS PASSED");
