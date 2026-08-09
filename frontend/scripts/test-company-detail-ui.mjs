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
  decisionStatusLabel,
  evidenceDomainLabel,
  financialScopeLabel,
  getCompanyReportInsight,
  latestSnapshotMetric,
  metricDisplayText,
  metricToneClass,
  peerBenchmarkLabel,
  reportFinancialHeading,
  reportMetricByYear,
  reportRatioByYear,
  reportRevenueShareKey,
  reportSectionLabel,
  reportYears,
  sourceSectionCounts,
  verificationStatusLabel,
} from "../src/companyReportInsights.js";
import { getCompanyItems, getCompanyEvents } from "../src/companyInsights.js";
import {
  buildCompanyItemEvidence,
  buildReportAnalysisEvidence,
  buildSourceRows,
  distinctSourceRows,
  hasEvidenceDisplayValue,
  sourceSummaryForDomain,
  sourceTypeSummaryForDomain,
  sourcesForDomain,
} from "../src/companyEvidence.js";
import { companyDataGapRows, dataGapSummaryForDomain } from "../src/companyDataGaps.js";
import { buildCompanyDecisionModel } from "../src/companyDecisionModel.js";

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
  "../src/components/company/CompanyComparisonMvp.jsx",
  "../src/components/company/CompanyDataGaps.jsx",
  "../src/components/company/EvidenceDrawer.jsx",
  "../src/components/company/CompanyEntityDrawer.jsx",
  "../src/components/company/CompanyOverviewTab.jsx",
  "../src/components/company/CompanyFinancialTab.jsx",
  "../src/components/company/CompanyProductionTab.jsx",
  "../src/components/company/CompanyProjectTab.jsx",
  "../src/components/company/CompanyTechnologyTab.jsx",
  "../src/components/company/CompanyEvidenceTab.jsx",
  "../src/components/company/companyDetailHelpers.js",
  "../src/companyEvidence.js",
  "../src/companyDecisionModel.js",
  "../src/companyReportInsights.js",
].map((path) => readFileSync(new URL(path, import.meta.url), "utf8")).join("\n");
const productionTabSource = readFileSync(new URL("../src/components/company/CompanyProductionTab.jsx", import.meta.url), "utf8");
const projectTabSource = readFileSync(new URL("../src/components/company/CompanyProjectTab.jsx", import.meta.url), "utf8");
const stylesheet = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
const reportBackedMasterFinancialGapIds = new Set(["daeseung-engineering"]);

assert.equal(companies.length, 11);
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
assert.equal(componentFiles.includes("Executive Summary"), false, "overview should not duplicate legacy executive summary copy");
assert.equal(componentFiles.includes("CompanyIntelligenceSummary"), false, "overview should use the consolidated decision-first snapshot");
assert.equal(componentFiles.includes("DecisionCards"), false, "overview should not render duplicate legacy decision cards");
assert.ok(componentFiles.includes("company-decision-snapshot"), "overview should include a compact decision snapshot");
assert.ok(componentFiles.includes("compact-company-section"), "overview should consolidate decision-first sections");
assert.ok(componentFiles.includes("Data Trust Center"), "evidence tab should expose a data trust center");
assert.ok(componentFiles.includes("상세 근거 보기"), "data trust cards should expose evidence drawer actions");
assert.equal(componentFiles.includes("sourceTypes.split"), false, "data trust center should not infer counts from source type labels");
assert.ok(componentFiles.includes("distinct_source_count"), "data trust center should use actual distinct source counts");
assert.ok(componentFiles.includes("source_type_counts"), "data trust center should display source type counts separately");
assert.ok(componentFiles.includes("동료 비교"), "financial tab should expose peer comparison");
assert.ok(componentFiles.includes("not_comparable_reason"), "peer comparison should render non-comparable reasons instead of forced ranks");
assert.ok(componentFiles.includes("comparison_universe_count"), "peer comparison should show the comparison universe size");
assert.ok(componentFiles.includes("current_company_included"), "peer comparison should disclose whether the current company is included");
assert.ok(componentFiles.includes("median_display"), "peer comparison should show the benchmark median");
assert.ok(componentFiles.includes("reference_value_label"), "peer comparison should show the reference max/min label");
assert.ok(componentFiles.includes("같은 연도·통화·재무제표 범위"), "peer comparison copy should explain comparability constraints");
assert.equal(componentFiles.includes("<dt>rule_id</dt>"), false, "financial health cards should hide raw rule identifiers by default");
assert.ok(componentFiles.includes("관찰값"), "financial health cards should show observation values first");
assert.ok(componentFiles.includes("interpretation_scope"), "financial health cards should show interpretation scope");
assert.ok(componentFiles.includes("company-detail-keyword-panel"), "detail header should expose decision keywords");
assert.ok(componentFiles.includes("!compact &&") && componentFiles.includes("company-detail-keyword-panel"), "full keyword panel should only render on the overview header");
assert.ok(componentFiles.includes("company-decision-chip-stack"), "company list cards should use scan-first decision chips");
assert.ok(componentFiles.includes("계산 근거 보기"), "decision cards should open calculation evidence");
assert.ok(componentFiles.includes("evidence-detail-list"), "evidence drawer should render structured calculation details");
assert.ok(componentFiles.includes("CompanyEntityDrawer"), "entity detail panels should share a common drawer");
assert.ok(componentFiles.includes("company-entity-drawer") && componentFiles.includes("aria-modal=\"true\""), "entity drawer should expose modal semantics");
assert.ok(componentFiles.includes("createPortal"), "entity drawer should render outside the React root for modal isolation");
assert.ok(componentFiles.includes("appRoot.inert = true"), "entity drawer should inert the background app while open");
assert.ok(componentFiles.includes("titleRef.current?.focus"), "entity drawer should focus the title/content start on open");
assert.ok(componentFiles.includes("preventScroll"), "entity drawer initial focus should avoid unwanted scroll jumps");
assert.equal(productionTabSource.includes("<details"), false, "production facility details must not render inside table cells");
assert.equal(productionTabSource.includes("company-row-detail"), false, "production facility details should use drawer, not row expansion");
assert.ok(productionTabSource.includes("상세보기") && productionTabSource.includes("setSelectedFacility"), "production facilities should open a detail drawer");
assert.ok(productionTabSource.includes("hasProductionValue"), "production facility missing checks should use explicit value presence");
assert.equal(productionTabSource.includes("!facility.site_area && !facility.site_area_m2"), false, "production facility missing checks must preserve numeric zero");
assert.equal(componentFiles.includes("<h3>2023~2025년 재무 추이</h3>"), false, "financial report heading should come from available years");
assert.ok(componentFiles.includes("공식 공시문서에 포함된 감사받은 재무제표 기준 정보"), "financial report copy should describe the common disclosure basis");
assert.ok(componentFiles.includes("attribution_warning"), "financial tab should render per-company attribution warnings from data");
assert.equal(componentFiles.includes("제품매출과 공사매출은 모듈러 매출로 자동 해석하지 않으며"), false, "financial tab should not hardcode product/construction attribution warnings");
assert.equal(componentFiles.includes("유창엠앤씨 등 관계사 실적도 유창이앤씨 별도 실적으로 합산하지 않습니다"), false, "financial tab should not hardcode Yuchang related-entity wording");
assert.ok(stylesheet.includes(".company-report-table { min-width: 760px; }"), "financial report tables should use contained horizontal scrolling");
assert.ok(stylesheet.includes(".company-report-kpi-grid") && stylesheet.includes("grid-template-columns: 1fr"), "financial report layout should collapse on mobile");
assert.equal(productionTabSource.includes("responsive-table-wrap"), false, "production facilities should use card-first layout on every viewport");
assert.ok(productionTabSource.includes("facility-card-list"), "production facilities should render responsive cards");
assert.equal(projectTabSource.includes("company-project-table"), false, "projects should not render a desktop data table");
assert.equal(projectTabSource.includes("responsive-table-wrap"), false, "projects should use card-first layout on every viewport");
assert.ok(projectTabSource.includes("project-card-list"), "projects should render responsive cards");
assert.ok(stylesheet.includes(".facility-card-list, .project-card-list") && stylesheet.includes("grid-template-columns: repeat(2"), "facility/project cards should use a two-column desktop grid");
assert.ok(stylesheet.includes(".facility-card-list, .project-card-list { grid-template-columns: 1fr; }"), "facility/project cards should collapse to one column on mobile");
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
assert.ok(componentFiles.includes("매출 추이"), "revenue trend should render as a separate chart");
assert.equal(componentFiles.includes("영업이익 추이"), false, "finance tab should not add a fifth operating-profit chart");
assert.equal(componentFiles.includes("title=\"매출과 영업이익\""), false, "revenue and operating profit should not share one mini-chart title");
assert.equal(componentFiles.includes("GroupedMetricTrend"), false, "finance tab should not use grouped second-level charts");
assert.ok(componentFiles.includes("총차입금 추이"), "borrowings should render as a dedicated first-level chart");
assert.ok(componentFiles.includes("영업이익률"), "operating margin should render as a dedicated first-level chart");
assert.ok(componentFiles.includes("financial-zero-line"), "cash-flow chart should render an explicit zero baseline");
assert.ok(componentFiles.includes("financial-cash-flow-zone negative"), "cash-flow chart should include a negative value lane");
assert.ok(componentFiles.includes("financial-cash-flow-zone positive"), "cash-flow chart should include a positive value lane");
assert.ok(componentFiles.includes("cash-flow-direction-positive"), "cash-flow chart should mark positive rows");
assert.ok(componentFiles.includes("cash-flow-direction-negative"), "cash-flow chart should mark negative rows");
assert.ok(componentFiles.includes("financial-zero-marker"), "cash-flow chart should preserve a visible zero-value marker");
assert.ok(componentFiles.includes("REPORT_REVENUE_BREAKDOWN_ROWS"), "audit financial panel should support revenue breakdown rows");
assert.ok(componentFiles.includes("용역매출"), "audit financial panel should label service revenue");
assert.ok(componentFiles.includes("해석 범위 안내"), "audit financial panel should show interpretation scope callouts");
assert.ok(componentFiles.includes("isAvailable && <i"), "null financial metrics should not render zero-width chart bars");
assert.ok(componentFiles.includes("is-unavailable"), "unavailable financial metrics should have a non-chart display state");
assert.ok(stylesheet.includes("grid-template-columns: 44px minmax(0, 1fr) 2px minmax(0, 1fr)"), "cash-flow chart should place the zero line between symmetric lanes");
assert.ok(stylesheet.includes("justify-content: flex-end"), "negative cash-flow bars should extend left toward the zero line");
assert.ok(stylesheet.includes("justify-content: flex-start"), "positive cash-flow bars should extend right from the zero line");
assert.ok(componentFiles.includes("aria-hidden=\"true\""), "decorative financial chart marks should be hidden from assistive tech");
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
  if (reportBackedMasterFinancialGapIds.has(company.company_id)) continue;
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
const kumkangReport = getCompanyReportInsight(reportPayload, "kumkang-kind");
assert.ok(kumkangReport, "kumkang-kind report insight must load");
const daeseungReport = getCompanyReportInsight(reportPayload, "daeseung-engineering");
assert.ok(daeseungReport, "daeseung-engineering report insight must load");
const planmReport = getCompanyReportInsight(reportPayload, "planm");
assert.ok(planmReport, "planm report insight must load after controlled public promotion");
const nrbReport = getCompanyReportInsight(reportPayload, "nrb");
assert.ok(nrbReport, "nrb report insight must load after controlled public promotion");
assert.equal(getCompanyReportInsight(reportPayload, "gs-ec"), null, "companies without report insights should fall back to legacy financial UI");
assert.equal(hasEvidenceDisplayValue(0), true);
assert.equal(hasEvidenceDisplayValue(-1), true);
assert.equal(hasEvidenceDisplayValue("0"), true);
assert.equal(hasEvidenceDisplayValue("확인값"), true);
assert.equal(hasEvidenceDisplayValue(null), false);
assert.equal(hasEvidenceDisplayValue(undefined), false);
assert.equal(hasEvidenceDisplayValue(""), false);
assert.equal(metricDisplayText({ display_text: "0.0억원", raw_krw: 0, disclosure_status: "reported" }), "0.0억원");
assert.equal(metricDisplayText({ raw_krw: null, disclosure_status: "not_disclosed" }), "공시되지 않음");
assert.equal(metricDisplayText({ raw_krw: null, disclosure_status: "not_applicable" }), "해당 없음");
assert.equal(metricDisplayText({ raw_krw: null }), "확인되지 않음");
const yuchang = byId("yuchang-enc");
const sungji = byId("sungji-steel");
const sungjiReport = getCompanyReportInsight(reportPayload, "sungji-steel");
const sungjiDecision = buildCompanyDecisionModel(sungji, { reportInsight: sungjiReport });
const forbiddenPositionKeywords = new Set([
  "모듈러 제작 전문 업체",
  "직접 경쟁사",
  "대체 경쟁사",
  "최우선 분석",
  "우선 분석",
  "감사재무 적용",
]);
assert.equal(sungjiDecision.positionKeywords.some((keyword) => forbiddenPositionKeywords.has(keyword)), false, "position keywords should not reuse metadata labels");
assert.ok(sungjiDecision.positionKeywords.length > 0, "position keywords should be derived from business position signals");
assert.ok(sungjiDecision.capabilities.includes("자체 생산") || sungjiDecision.capabilities.includes("자체 공장"), "capability keywords should expose source-backed manufacturing capability");
assert.equal(sungjiDecision.capabilities.some((keyword) => /^\d/.test(keyword) || keyword.includes("건 보유")), false, "capability keywords should not be count duplicates");
assert.ok(sungjiDecision.watchSignals.every((keyword) => keyword.length <= 14), "watch chips should use short semantic labels");
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
assert.equal(decisionStatusLabel("watch"), "관찰 필요");
assert.equal(decisionStatusLabel("additional_confirmation_required"), "추가 확인 필요");
assert.equal(evidenceDomainLabel("financial"), "재무");
assert.equal(peerBenchmarkLabel("operating_cash_flow"), "영업현금흐름");
assert.equal(latestSnapshotMetric(yuchangReport, "revenue").raw_krw, yuchangReport.latest_metrics.revenue.raw_krw);
assert.equal(yuchangReport.latest_snapshot.latest_year, 2025);
assert.equal(Object.hasOwn(yuchangReport.latest_snapshot, "gross_profit"), false, "latest snapshot should omit missing metrics instead of synthetic null keys");
assert.equal(yuchangReport.financial_health.profitability.metric_ids.includes("operating_margin_pct"), true);
assert.equal(yuchangReport.financial_health.profitability.rule_id, "profitability_negative_margin");
assert.equal(yuchangReport.financial_health.profitability.threshold, 0);
assert.equal(yuchangReport.financial_health.leverage.threshold, 200);
assert.equal(yuchangReport.financial_health.working_capital.threshold, 30);
assert.match(yuchangReport.financial_health.profitability.interpretation_scope, /투자 판단이 아닙니다/);
assert.equal(yuchangReport.evidence_health.some((row) => row.domain === "financial"), true);
const yuchangFinancialEvidence = yuchangReport.evidence_health.find((row) => row.domain === "financial");
assert.equal(yuchangFinancialEvidence.distinct_source_count, 2);
assert.deepEqual(yuchangFinancialEvidence.source_type_counts, { audit_report: 2 });
const yuchangDisclosureEvidence = yuchangReport.evidence_health.find((row) => row.domain === "disclosure_scope");
assert.equal(yuchangDisclosureEvidence.verification_status, "not_disclosed");
assert.equal(yuchangDisclosureEvidence.verified_item_count, 0);
assert.equal(yuchangDisclosureEvidence.not_disclosed_item_count, 1);
assert.equal(yuchangReport.peer_benchmarks.some((item) => item.comparable === true), true);
const yuchangRevenuePeer = yuchangReport.peer_benchmarks.find((item) => item.metric_id === "revenue");
assert.equal(yuchangRevenuePeer.comparison_universe_count, 5);
assert.equal(yuchangRevenuePeer.other_peer_count, 4);
assert.equal(yuchangRevenuePeer.current_company_included, true);
assert.equal(yuchangRevenuePeer.median_display, "616.6억원");
assert.equal(yuchangRevenuePeer.reference_value_label, "비교 범위 최대값");
assert.equal(yuchangRevenuePeer.reference_value_display, "3,076.8억원");
assert.equal(kumkangReport.peer_benchmarks.every((item) => item.comparable === false), true);
assert.ok(kumkangReport.peer_benchmarks.every((item) => item.not_comparable_reason), "single consolidated company should not receive peer ranks");
const duplicateSourceRows = [yuchangSources[0], { ...yuchangSources[0] }, ...yuchangSources.slice(1)];
assert.equal(distinctSourceRows(duplicateSourceRows).length, yuchangSources.length, "source counts should dedupe equivalent source rows");
assert.equal(sourceSummaryForDomain(yuchangSources, "financial").sourceCount, 2, "financial source count should use real audit sources");
const analysisEvidence = buildReportAnalysisEvidence(yuchangReport, "영업이익률 관찰 규칙", {
  value: 0,
  latestValue: 0,
  calculationValue: 0,
  metricIds: ["operating_margin_pct"],
  sourceIds: [],
});
assert.equal(analysisEvidence.value, 0, "analysis evidence should preserve numeric zero payloads");
assert.ok(analysisEvidence.note.includes("직접 연결된 출처 없음"), "analysis evidence should disclose missing direct sources");
assert.ok(analysisEvidence.details.some((row) => row[0] === "해석 한계"), "analysis evidence should carry interpretation limits");
assert.equal(metricDisplayText(reportMetricByYear(yuchangReport, 2025, "revenue")), "3,076.8억원");
assert.equal(metricDisplayText(reportRatioByYear(yuchangReport, 2025, "operating_margin_pct")), "4.8%");
assert.equal(metricDisplayText(reportMetricByYear(yuchangReport, 2025, "operating_cash_flow")), "-308.3억원");
assert.equal(metricToneClass(reportMetricByYear(yuchangReport, 2025, "operating_cash_flow")), "is-negative");
assert.equal(metricDisplayText(reportMetricByYear(yuchangReport, 2025, "total_borrowings")), "1,121.3억원");
assert.equal(metricDisplayText(reportMetricByYear(yuchangReport, 2025, "receivables_total")), "1,157.9억원");
assert.equal(metricDisplayText(reportMetricByYear(kumkangReport, 2025, "revenue")), "8,021.6억원");
assert.equal(kumkangReport.source_summary.verified_location_count, 84);
assert.equal(kumkangReport.source_summary.pending_location_count, 0);
assert.equal(kumkangReport.source_summary.audit_opinions.every((opinion) => opinion.auditor_report_date === null), true);
assert.equal(kumkangReport.disclosure_warnings.some((warning) => warning.code === "modular_segment_revenue_not_disclosed"), false);
assert.ok(kumkangReport.disclosure_warnings.some((warning) => warning.code === "product_revenue_not_modular_revenue"));
assert.deepEqual(reportYears(daeseungReport), [2023, 2024, 2025]);
assert.equal(daeseungReport.financial_scope, "standalone");
assert.equal(metricDisplayText(reportMetricByYear(daeseungReport, 2025, "revenue")), "616.6억원");
assert.equal(metricDisplayText(reportMetricByYear(daeseungReport, 2025, "operating_cash_flow")), "-3.5억원");
assert.equal(metricToneClass(reportMetricByYear(daeseungReport, 2025, "operating_cash_flow")), "is-negative");
assert.equal(metricDisplayText(reportMetricByYear(daeseungReport, 2025, "total_borrowings")), "531.6억원");
assert.equal(metricDisplayText(reportRatioByYear(daeseungReport, 2025, "rental_revenue_share_pct")), "40.7%");
assert.equal(daeseungReport.source_summary.verified_location_count, 84);
assert.equal(daeseungReport.source_summary.pending_location_count, 0);
assert.equal(daeseungReport.source_summary.audit_opinions.at(-1).auditor_report_date, "2025-09-16");
assert.equal(daeseungReport.attribution.modular_segment_revenue_disclosed, true);
assert.equal(daeseungReport.disclosure_warnings.some((warning) => warning.code === "modular_segment_revenue_not_disclosed"), false);
assert.ok(daeseungReport.disclosure_warnings.some((warning) => warning.code === "product_revenue_not_modular_revenue"));
assert.deepEqual(reportYears(planmReport), [2023, 2024, 2025]);
assert.equal(planmReport.financial_scope, "standalone");
assert.equal(metricDisplayText(reportMetricByYear(planmReport, 2023, "total_equity")), "검증 보류");
assert.equal(reportMetricByYear(planmReport, 2023, "total_equity").raw_krw, null);
assert.equal(reportRatioByYear(planmReport, 2023, "liabilities_to_equity_pct").value, null);
assert.equal(reportRatioByYear(planmReport, 2023, "borrowings_to_equity_pct").value, null);
assert.equal(metricDisplayText(reportMetricByYear(planmReport, 2025, "revenue")), "592.2억원");
assert.equal(planmReport.disclosure_warnings.some((warning) => warning.code === "verification_pending_total_equity"), true);
assert.equal(planmReport.disclosure_warnings.some((warning) => warning.code === "modular_segment_revenue_not_disclosed"), true);
assert.equal(JSON.stringify(planmReport).includes("3,529,782,000"), false);
assert.equal(JSON.stringify(planmReport).includes("3529782000"), false);
assert.deepEqual(reportYears(nrbReport), [2023, 2024, 2025]);
assert.equal(nrbReport.financial_scope, "standalone");
assert.equal(metricDisplayText(reportMetricByYear(nrbReport, 2025, "revenue")), "594.8억원");
assert.equal(metricDisplayText(reportMetricByYear(nrbReport, 2025, "operating_profit")), "44.6억원");
assert.equal(metricDisplayText(reportMetricByYear(nrbReport, 2025, "net_income")), "-5.6억원");
assert.equal(metricToneClass(reportMetricByYear(nrbReport, 2025, "net_income")), "is-negative");
assert.equal(metricDisplayText(reportRatioByYear(nrbReport, 2025, "operating_margin_pct")), "7.5%");
assert.equal(metricDisplayText(reportMetricByYear(nrbReport, 2025, "service_revenue")), "122.7억원");
assert.equal(metricDisplayText(reportRatioByYear(nrbReport, 2025, reportRevenueShareKey("service_revenue"))), "20.6%");
assert.equal(metricDisplayText(reportMetricByYear(nrbReport, 2023, "construction_revenue")), "해당 없음");
assert.equal(reportMetricByYear(nrbReport, 2023, "construction_revenue").raw_krw, null);
assert.equal(JSON.stringify(nrbReport).includes("current_liability_policy_reclassification"), true);
assert.equal(JSON.stringify(nrbReport).includes("cash_flow_presentation_policy_change"), true);
assert.equal(nrbReport.disclosure_warnings.some((warning) => warning.code === "modular_segment_revenue_not_disclosed"), false);
for (const year of [2023, 2024, 2025]) {
  for (const metricKey of ["revenue", "operating_profit", "operating_cash_flow", "total_borrowings", "receivables_total"]) {
    assert.notEqual(metricDisplayText(reportMetricByYear(yuchangReport, year, metricKey)), "확인되지 않음", `${metricKey} ${year} should have a direct label`);
  }
  assert.notEqual(metricDisplayText(reportRatioByYear(yuchangReport, year, "operating_margin_pct")), "확인되지 않음", `operating margin ${year} should have a direct label`);
}
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
