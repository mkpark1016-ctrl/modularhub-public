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

assert.equal(kumkang.peer_benchmarks.some((item) => item.comparable), false, "Kumkang peer metrics should remain comparison-pending");
assert.equal(yuchang.peer_benchmarks.every((item) => item.comparable), true, "Yuchang peer metrics should remain comparable");

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

assert.match(panelSource, /company-peer-availability-note/);
assert.match(panelSource, /company-peer-keywords/);
assert.match(panelSource, /비교 데이터 부족/);
assert.match(panelSource, /일부 지표 비교 준비 중/);
assert.match(panelSource, /동일 조건에서 최소/);
assert.match(panelSource, /중앙값 \{item\.median_display/);
assert.doesNotMatch(panelSource, /<p>\{item\.comparable \? benchmarkRankText\(item\) : item\.not_comparable_reason\}<\/p>/);

assert.match(panelSource, /financial-signal-grid/);
assert.match(panelSource, /financial-signal-keywords/);
assert.match(panelSource, /signalKeywordValue/);
assert.match(panelSource, /↑ 증가/);
assert.match(panelSource, /↓ 감소/);
assert.match(panelSource, /↑ 개선/);
assert.match(panelSource, /영업현금흐름/);
assert.doesNotMatch(panelSource, /<p key=\{signal\.code\}>\{signal\.description\}<\/p>/);

assert.match(overridesSource, /company-intelligence-summary\.compact\.financial-decision-grid/);
assert.match(overridesSource, /display: flex/);
assert.match(overridesSource, /flex-wrap: wrap/);
assert.match(overridesSource, /\.company-report-kpi-grid \{\s*grid-template-columns: repeat\(4, minmax\(0, 1fr\)\)/);
assert.match(overridesSource, /financial-status-guide-items/);
assert.match(overridesSource, /financial-status-rule-grid/);
assert.match(overridesSource, /company-peer-availability-note/);
assert.match(overridesSource, /company-peer-keywords/);
assert.match(overridesSource, /company-report-signal-grid\.financial-signal-grid/);
assert.match(overridesSource, /financial-signal-keyword/);

console.log("COMPANY FINANCIAL DASHBOARD TESTS PASSED");
