import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const panelSource = readFileSync(new URL("../src/components/company/CompanyAuditFinancialPanel.jsx", import.meta.url), "utf8");
const overridesSource = readFileSync(new URL("../src/companyUiOverrides.css", import.meta.url), "utf8");

assert.match(panelSource, /Object\.values\(insight\.trends \|\| \{\}\)\.slice\(0, 4\)/);
assert.match(panelSource, /aria-label="최근 추세 신호"/);

assert.match(
  overridesSource,
  /company-intelligence-trend-strip\[aria-label="최근 추세 신호"\][\s\S]*?display: grid;[\s\S]*?grid-template-columns: repeat\(4, minmax\(0, 1fr\)\)/,
  "desktop financial trends must use a deterministic four-column grid",
);
assert.match(
  overridesSource,
  /@media \(max-width: 1023px\)[\s\S]*?company-intelligence-trend-strip\[aria-label="최근 추세 신호"\][\s\S]*?grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/,
  "tablet financial trends must collapse to two columns",
);
assert.match(
  overridesSource,
  /@media \(max-width: 599px\)[\s\S]*?company-intelligence-trend-strip\[aria-label="최근 추세 신호"\][\s\S]*?grid-template-columns: 1fr/,
  "mobile financial trends must collapse to one column",
);
assert.match(overridesSource, /grid-template-rows: auto 1fr auto/);
assert.match(overridesSource, /overflow-wrap: anywhere/);
assert.match(overridesSource, /\.evidence-inline-button[\s\S]*?align-self: end/);

console.log("COMPANY FINANCIAL TREND GRID TESTS PASSED");
