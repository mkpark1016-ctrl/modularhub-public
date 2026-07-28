import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  COMPANY_DETAIL_TABS,
  formatPercent,
  metricMargin,
  metricValue,
  sortedFinancials,
  technologyItems,
} from "../src/components/company/companyDetailHelpers.js";
import {
  getCompanyReportInsight,
  metricDisplayText,
  metricToneClass,
  reportMetricByYear,
  reportRatioByYear,
  reportSectionLabel,
  reportYears,
  sourceSectionCounts,
} from "../src/companyReportInsights.js";
import { getCompanyItems, getCompanyEvents } from "../src/companyInsights.js";

const payload = JSON.parse(readFileSync(new URL("../public/data/companies/companies.json", import.meta.url), "utf8"));
const reportPayload = JSON.parse(readFileSync(new URL("../public/data/companies/company_report_insights.json", import.meta.url), "utf8"));
const companies = getCompanyItems(payload);
const byId = (id) => companies.find((company) => company.company_id === id);
const componentFiles = [
  "../src/App.jsx",
  "../src/components/company/CompanyDetailView.jsx",
  "../src/components/company/CompanyDetailHeader.jsx",
  "../src/components/company/CompanyDetailTabs.jsx",
  "../src/components/company/CompanyAuditFinancialPanel.jsx",
  "../src/components/company/CompanyOverviewTab.jsx",
  "../src/components/company/CompanyFinancialTab.jsx",
  "../src/components/company/CompanyProductionTab.jsx",
  "../src/components/company/CompanyProjectTab.jsx",
  "../src/components/company/CompanyTechnologyTab.jsx",
  "../src/components/company/CompanyEvidenceTab.jsx",
  "../src/components/company/companyDetailHelpers.js",
  "../src/companyReportInsights.js",
].map((path) => readFileSync(new URL(path, import.meta.url), "utf8")).join("\n");
const stylesheet = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

assert.equal(companies.length, 10);
assert.deepEqual(COMPANY_DETAIL_TABS.map((tab) => tab.value), ["overview", "financial", "production", "projects", "technology", "evidence"]);
assert.ok(componentFiles.includes("normalizeCompanyTab(searchParams.get(\"tab\")"));
assert.ok(componentFiles.includes("role=\"tablist\""));
assert.ok(componentFiles.includes("role=\"tab\""));
assert.ok(componentFiles.includes("ArrowRight"));
assert.ok(componentFiles.includes("검증 수준"), "company detail should render verification level");
assert.ok(componentFiles.includes("감사보고서 근거 확인"), "financial tab should distinguish audit evidence");
assert.ok(componentFiles.includes("단위"), "financial tab should show source unit/currency");
assert.ok(componentFiles.includes("companies/company_report_insights"), "company detail page should load company report insights");
assert.ok(componentFiles.includes("reportInsight ?"), "financial tab should prefer audit View Model when available");
assert.ok(componentFiles.includes("제품매출과 공사매출은 모듈러 매출로 자동 해석하지 않으며"), "financial tab should prevent modular revenue overstatement");
assert.ok(componentFiles.includes("유창엠앤씨 등 관계사 실적도 유창이앤씨 별도 실적으로 합산하지 않습니다"), "financial tab should prevent related-entity aggregation");
assert.ok(stylesheet.includes(".company-report-table { min-width: 760px; }"), "financial report tables should use contained horizontal scrolling");
assert.ok(stylesheet.includes(".company-report-kpi-grid") && stylesheet.includes("grid-template-columns: 1fr"), "financial report layout should collapse on mobile");

for (const required of ["established_at", "representative", "employee_count", "major_businesses", "gross_profit"]) {
  assert.ok(componentFiles.includes(required), `${required} must be rendered by company detail components`);
}
assert.equal(componentFiles.includes(".slice(0, 8)"), false);
assert.equal(componentFiles.includes("source.url || source.source_url"), true);

for (const company of companies) {
  const profile = company.company_profile || {};
  assert.ok(profile.established_at || profile.representative || profile.employee_count || profile.major_businesses, `${company.company_id} profile fields missing`);
  const financials = sortedFinancials(company);
  assert.equal(financials.length, 3, `${company.company_id} needs three financial years`);
  for (const row of financials) {
    assert.notEqual(metricValue(row.gross_profit), null, `${company.company_id} ${row.year} gross profit missing`);
    const grossMargin = metricMargin(row.gross_profit, row.revenue);
    const operatingMargin = metricMargin(row.operating_profit, row.revenue);
    assert.doesNotThrow(() => formatPercent(grossMargin));
    assert.doesNotThrow(() => formatPercent(operatingMargin));
  }
}

const yuchangReport = getCompanyReportInsight(reportPayload, "yuchang-enc");
assert.ok(yuchangReport, "yuchang-enc report insight must load");
assert.equal(getCompanyReportInsight(reportPayload, "gs-ec"), null, "companies without report insights should fall back to legacy financial UI");
assert.deepEqual(reportYears(yuchangReport), [2023, 2024, 2025]);
assert.equal(metricDisplayText(reportMetricByYear(yuchangReport, 2025, "revenue")), "3,076.8억원");
assert.equal(metricDisplayText(reportRatioByYear(yuchangReport, 2025, "operating_margin_pct")), "4.8%");
assert.equal(metricDisplayText(reportMetricByYear(yuchangReport, 2025, "operating_cash_flow")), "-308.3억원");
assert.equal(metricToneClass(reportMetricByYear(yuchangReport, 2025, "operating_cash_flow")), "is-negative");
assert.equal(metricDisplayText(reportMetricByYear(yuchangReport, 2025, "total_borrowings")), "1,121.3억원");
assert.equal(metricDisplayText(reportMetricByYear(yuchangReport, 2025, "receivables_total")), "1,157.9억원");
assert.ok(yuchangReport.disclosure_warnings.some((warning) => warning.code === "pending_manual_page_check"));
assert.ok(yuchangReport.disclosure_warnings.some((warning) => warning.code === "related_entity_results_not_combined"));
assert.equal(yuchangReport.source_summary.pending_location_count, 45);
assert.equal(reportSectionLabel("statement.income_statement"), "손익계산서");
assert.equal(reportSectionLabel("statement.balance_sheet"), "재무상태표");
assert.equal(reportSectionLabel("statement.cash_flow"), "현금흐름표");
assert.equal(reportSectionLabel("note.revenue_breakdown"), "매출 구성 주석");
assert.equal(reportSectionLabel("note.working_capital"), "운전자본 주석");
assert.equal(reportSectionLabel("note.borrowings"), "차입금 주석");
assert.equal(reportSectionLabel("note.investment_signals"), "투자 관련 주석");
assert.equal(sourceSectionCounts(yuchangReport).length, 7);
assert.equal(sourceSectionCounts(yuchangReport).find((item) => item.section === "note.revenue_breakdown").count, 0);

const expectedTechnologyCounts = {
  "hyundai-engineering": 14,
  "dl-enc": 21,
  nrb: 16,
  planm: 10,
};
for (const [id, expected] of Object.entries(expectedTechnologyCounts)) {
  assert.equal(technologyItems(byId(id)).length, expected, `${id} technology records must all be accessible`);
}

for (const company of companies) {
  const verified = getCompanyEvents(company).filter((event) => event.event_type === "project" && event.project_credit);
  const pipeline = getCompanyEvents(company).filter((event) => event.event_type === "project" && !event.project_credit);
  assert.equal(verified.some((event) => ["mou_signed", "partnership_discussion", "pre_con", "r_and_d", "exhibition", "not_signed"].includes(event.event_status)), false);
  assert.equal(pipeline.some((event) => event.project_credit), false);
}

console.log("COMPANY DETAIL UI TESTS PASSED");
