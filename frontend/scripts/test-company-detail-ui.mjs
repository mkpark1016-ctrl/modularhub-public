import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  COMPANY_DETAIL_TABS,
  formatPercent,
  labelValue,
  metricMargin,
  metricValue,
  sortedFinancials,
  technologyItems,
} from "../src/components/company/companyDetailHelpers.js";
import {
  financialScopeLabel,
  getCompanyReportInsight,
  metricDisplayText,
  metricToneClass,
  reportFinancialHeading,
  reportMetricByYear,
  reportRatioByYear,
  reportSectionLabel,
  reportYears,
  sourceSectionCounts,
  verificationStatusLabel,
} from "../src/companyReportInsights.js";
import { getCompanyItems, getCompanyEvents } from "../src/companyInsights.js";
import {
  buildCompanyItemEvidence,
  buildSourceRows,
  hasEvidenceDisplayValue,
  sourceTypeSummaryForDomain,
  sourcesForDomain,
} from "../src/companyEvidence.js";
import { companyDataGapRows, dataGapSummaryForDomain } from "../src/companyDataGaps.js";

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
  "../src/components/company/CompanyDataGaps.jsx",
  "../src/components/company/EvidenceDrawer.jsx",
  "../src/components/company/CompanyOverviewTab.jsx",
  "../src/components/company/CompanyFinancialTab.jsx",
  "../src/components/company/CompanyProductionTab.jsx",
  "../src/components/company/CompanyProjectTab.jsx",
  "../src/components/company/CompanyTechnologyTab.jsx",
  "../src/components/company/CompanyEvidenceTab.jsx",
  "../src/components/company/companyDetailHelpers.js",
  "../src/companyEvidence.js",
  "../src/companyReportInsights.js",
].map((path) => readFileSync(new URL(path, import.meta.url), "utf8")).join("\n");
const stylesheet = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

assert.equal(companies.length, 10);
assert.deepEqual(COMPANY_DETAIL_TABS.map((tab) => tab.value), ["overview", "financial", "production", "projects", "technology", "evidence"]);
assert.equal(COMPANY_DETAIL_TABS.find((tab) => tab.value === "overview").label, "종합분석");
assert.ok(componentFiles.includes("normalizeCompanyTab(searchParams.get(\"tab\")"));
assert.ok(componentFiles.includes("role=\"tablist\""));
assert.ok(componentFiles.includes("role=\"tab\""));
assert.ok(componentFiles.includes("ArrowRight"));
assert.ok(componentFiles.includes("검증 수준"), "company detail should render verification level");
assert.ok(componentFiles.includes("감사보고서 근거 확인"), "financial tab should distinguish audit evidence");
assert.ok(componentFiles.includes("단위"), "financial tab should show source unit/currency");
assert.ok(componentFiles.includes("companies/company_report_insights"), "company detail page should load company report insights");
assert.ok(componentFiles.includes("reportInsight ?"), "financial tab should prefer audit View Model when available");
assert.equal(componentFiles.includes("감사보고서 View Model 기준"), false, "financial UI should not expose implementation terminology");
assert.equal(componentFiles.includes("display_text를 표시"), false, "financial UI should not expose internal field names");
assert.equal(componentFiles.includes("기사 근거"), false, "project UI should use user-facing article wording");
assert.ok(componentFiles.includes("관련 보도"), "project and activity UI should use related report wording");
assert.ok(componentFiles.includes("재무 해석 범위"), "financial warnings should be consolidated into an interpretation scope card");
assert.ok(componentFiles.includes("상세 재무표 보기"), "financial detailed tables should be collapsible");
assert.ok(componentFiles.includes("EvidenceDrawer"), "detail UI should provide common evidence drawer");
assert.equal(componentFiles.includes("<h3>2023~2025년 재무 추이</h3>"), false, "financial report heading should come from available years");
assert.ok(componentFiles.includes("제품매출과 공사매출은 모듈러 매출로 자동 해석하지 않으며"), "financial tab should prevent modular revenue overstatement");
assert.ok(componentFiles.includes("유창엠앤씨 등 관계사 실적도 유창이앤씨 별도 실적으로 합산하지 않습니다"), "financial tab should prevent related-entity aggregation");
assert.ok(stylesheet.includes(".company-report-table { min-width: 760px; }"), "financial report tables should use contained horizontal scrolling");
assert.ok(stylesheet.includes(".company-report-kpi-grid") && stylesheet.includes("grid-template-columns: 1fr"), "financial report layout should collapse on mobile");
assert.ok(stylesheet.includes(".responsive-card-list") && stylesheet.includes(".responsive-table-wrap { display: none; }"), "facility/project tables should switch to cards on mobile");
assert.ok(stylesheet.includes(".evidence-drawer") && componentFiles.includes("role=\"dialog\""), "evidence drawer styles and dialog markup should exist");
assert.ok(componentFiles.includes("FOCUSABLE_SELECTOR"), "evidence drawer should define focusable targets");
assert.ok(componentFiles.includes("event.key !== \"Tab\""), "evidence drawer should trap Tab navigation");
assert.ok(componentFiles.includes("event.shiftKey"), "evidence drawer should support reverse Tab navigation");
assert.ok(componentFiles.includes("previousFocus"), "evidence drawer should restore the trigger focus");
assert.equal(componentFiles.includes("evidence.value &&"), false, "evidence drawer should not hide numeric zero values with truthy checks");
assert.ok(componentFiles.includes("hasEvidenceDisplayValue(evidence.value)"), "evidence drawer should use explicit display-value checks");
assert.equal(componentFiles.includes("sourceTypeSummary(sourceRows)"), false, "evidence matrix should not repeat a global source summary for every domain");
assert.ok(componentFiles.includes("sourceTypeSummaryForDomain"), "evidence matrix should use domain-scoped source summaries");
assert.ok(componentFiles.includes("row.metricKey"), "financial mini-chart rows should use metric keys to avoid duplicate React keys");
assert.equal(labelValue("school_modular"), "학교 모듈러");
assert.equal(labelValue("large_modular"), "대형 모듈러");

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
assert.equal(hasEvidenceDisplayValue(0), true);
assert.equal(hasEvidenceDisplayValue(-1), true);
assert.equal(hasEvidenceDisplayValue("0"), true);
assert.equal(hasEvidenceDisplayValue("확인값"), true);
assert.equal(hasEvidenceDisplayValue(null), false);
assert.equal(hasEvidenceDisplayValue(undefined), false);
assert.equal(hasEvidenceDisplayValue(""), false);
const yuchang = byId("yuchang-enc");
const missingEvidence = buildCompanyItemEvidence(yuchang, "직접 출처 미정리 항목", 0, ["missing-source-id"]);
assert.equal(missingEvidence.value, 0, "zero values should be preserved in evidence payloads");
assert.equal(missingEvidence.sources.length, 0, "missing source IDs should not fall back to unrelated company sources");
assert.match(missingEvidence.note, /직접 연결된 출처/, "missing direct source should produce a clear pending-source note");
const yuchangSources = buildSourceRows(yuchang, yuchangReport);
assert.ok(sourcesForDomain(yuchangSources, "financial").length > 0, "financial matrix domain should have explicit audit sources");
assert.ok(sourceTypeSummaryForDomain(yuchangSources, "financial").includes("감사보고서"), "financial matrix domain should show audit report sources");
assert.equal(sourceTypeSummaryForDomain([], "production"), "영역별 연결 근거 확인 필요");
const yuchangGaps = companyDataGapRows(yuchang, yuchangReport);
assert.notEqual(dataGapSummaryForDomain(yuchangGaps, "financial"), "연결 공백 없음", "financial gap summary should use explicit domain mapping");
assert.deepEqual(reportYears(yuchangReport), [2023, 2024, 2025]);
assert.equal(reportFinancialHeading({ available_years: [2023, 2024, 2025] }), "2023~2025년 재무 추이");
assert.equal(reportFinancialHeading({ available_years: [2024, 2025, 2026] }), "2024~2026년 재무 추이");
assert.equal(reportFinancialHeading({ available_years: [2025] }), "2025년 재무 현황");
assert.equal(reportFinancialHeading({ available_years: [] }), "재무 추이");
assert.equal(financialScopeLabel("standalone"), "별도 재무제표");
assert.equal(financialScopeLabel("consolidated"), "연결 재무제표");
assert.equal(financialScopeLabel("standalone_and_consolidated"), "별도·연결 재무제표");
assert.equal(verificationStatusLabel("verified"), "검증 완료");
assert.equal(verificationStatusLabel("verified_section_range"), "검증된 구간");
assert.equal(verificationStatusLabel("pending_manual_page_check"), "페이지 수동 확인 필요");
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
