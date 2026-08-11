import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const reportPayload = JSON.parse(readFileSync(new URL("../public/data/companies/company_report_insights.json", import.meta.url), "utf8"));
const panelSource = readFileSync(new URL("../src/components/company/CompanyAuditFinancialPanel.jsx", import.meta.url), "utf8");
const overridesSource = readFileSync(new URL("../src/companyUiOverrides.css", import.meta.url), "utf8");
const byId = (companyId) => reportPayload.companies.find((company) => company.company_id === companyId);

const kumkang = byId("kumkang-kind");
const yuchang = byId("yuchang-enc");
assert.ok(kumkang, "kumkang financial insight must exist");
assert.ok(yuchang, "yuchang financial insight must exist");

assert.deepEqual(
  Object.fromEntries(Object.entries(kumkang.financial_health).map(([key, item]) => [key, item.status])),
  {
    profitability: "info",
    cash_generation: "info",
    leverage: "info",
    working_capital: "info",
    disclosure_coverage: "info",
  },
  "Kumkang should remain all-reference under the current observation rules",
);

assert.deepEqual(
  Object.fromEntries(Object.entries(yuchang.financial_health).map(([key, item]) => [key, item.status])),
  {
    profitability: "info",
    cash_generation: "watch",
    leverage: "watch",
    working_capital: "watch",
    disclosure_coverage: "watch",
  },
  "Yuchang observation states must remain unchanged by the UI refactor",
);

assert.match(panelSource, /financial-decision-grid/);
assert.match(panelSource, /financial-decision-metrics/);
assert.match(panelSource, /financial-status-guide/);
assert.match(panelSource, /상세 판단기준 보기/);
assert.match(panelSource, /영업이익률 0% 미만 → 관찰 필요/);
assert.match(panelSource, /영업이익 양수 \+ 영업현금흐름 음수 → 관찰 필요/);
assert.match(panelSource, /부채비율 200% 초과 → 관찰 필요/);
assert.match(panelSource, /채권\/매출 비율 30% 초과 → 관찰 필요/);
assert.match(panelSource, /수동 확인 필요 출처 1건 이상 → 관찰 필요/);
assert.match(panelSource, /신용등급, 부실판정 또는 투자의견을 의미하지 않습니다/);
assert.match(panelSource, /amount\("operating_cash_flow"\)/);
assert.match(panelSource, /ratio\("liabilities_to_equity_pct"\)/);
assert.match(panelSource, /ratio\("receivables_to_revenue_pct"\)/);
assert.doesNotMatch(panelSource, /<p>\{item\.explanation\}<\/p>/);
assert.doesNotMatch(panelSource, /<div><dt>상태<\/dt><dd>\{decisionStatusLabel\(item\.status\)\}<\/dd><\/div>/);

assert.match(overridesSource, /company-intelligence-summary\.compact\.financial-decision-grid/);
assert.match(overridesSource, /display: flex/);
assert.match(overridesSource, /flex-wrap: wrap/);
assert.match(overridesSource, /\.company-report-kpi-grid \{\s*grid-template-columns: repeat\(4, minmax\(0, 1fr\)\)/);
assert.match(overridesSource, /financial-status-guide-items/);
assert.match(overridesSource, /financial-status-rule-grid/);

console.log("COMPANY FINANCIAL DASHBOARD TESTS PASSED");
