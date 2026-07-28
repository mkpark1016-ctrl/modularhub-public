export const REPORT_SECTION_LABELS = {
  "statement.income_statement": "손익계산서",
  "statement.balance_sheet": "재무상태표",
  "statement.cash_flow": "현금흐름표",
  "note.revenue_breakdown": "매출 구성 주석",
  "note.working_capital": "운전자본 주석",
  "note.borrowings": "차입금 주석",
  "note.investment_signals": "투자 관련 주석",
};

export const REPORT_AMOUNT_ROWS = [
  { key: "revenue", label: "매출액" },
  { key: "gross_profit", label: "매출총이익" },
  { key: "operating_profit", label: "영업이익" },
  { key: "net_income", label: "순이익" },
  { key: "operating_cash_flow", label: "영업현금흐름" },
  { key: "total_borrowings", label: "총차입금" },
  { key: "receivables_total", label: "매출채권 합계" },
  { key: "inventory", label: "재고자산" },
];

export const REPORT_RATIO_ROWS = [
  { key: "revenue_yoy_pct", label: "매출 증감률" },
  { key: "gross_margin_pct", label: "매출총이익률" },
  { key: "operating_margin_pct", label: "영업이익률" },
  { key: "net_margin_pct", label: "순이익률" },
  { key: "current_ratio_pct", label: "유동비율" },
  { key: "liabilities_to_equity_pct", label: "부채비율" },
  { key: "borrowings_to_equity_pct", label: "차입금비율" },
  { key: "receivables_to_revenue_pct", label: "매출채권/매출 비율" },
  { key: "inventory_to_revenue_pct", label: "재고/매출 비율" },
];

export function getCompanyReportInsight(payload, companyId) {
  const companies = Array.isArray(payload?.companies) ? payload.companies : [];
  return companies.find((item) => item.company_id === companyId) || null;
}

export function reportYears(insight) {
  return (Array.isArray(insight?.available_years) ? insight.available_years : [])
    .map((year) => Number(year))
    .filter((year) => Number.isFinite(year))
    .sort((a, b) => a - b);
}

export function reportFinancialHeading(insight) {
  const years = reportYears(insight);
  if (years.length === 0) return "재무 추이";
  if (years.length === 1) return `${years[0]}년 재무 현황`;
  return `${years[0]}~${years[years.length - 1]}년 재무 추이`;
}

export function reportMetricByYear(insight, year, metricKey) {
  const row = (insight?.financial_series || []).find((item) => Number(item.year) === Number(year));
  return row?.metrics?.[metricKey] || null;
}

export function reportRatioByYear(insight, year, metricKey) {
  return insight?.derived_metrics?.[String(year)]?.[metricKey] || null;
}

export function metricDisplayText(metric) {
  return metric?.display_text || "확인되지 않음";
}

export function metricToneClass(metric) {
  return Number(metric?.raw_krw) < 0 || Number(metric?.value) < 0 ? "is-negative" : "";
}

export function reportSectionLabel(section) {
  return REPORT_SECTION_LABELS[section] || "출처 섹션 확인 필요";
}

export function financialScopeLabel(scope) {
  if (scope === "standalone") return "별도 재무제표";
  if (scope === "consolidated") return "연결 재무제표";
  if (scope === "standalone_and_consolidated") return "별도·연결 재무제표";
  return "재무제표 기준 확인 중";
}

export function verificationStatusLabel(status) {
  if (status === "verified") return "검증 완료";
  if (status === "verified_section_range") return "검증된 구간";
  if (status === "pending_manual_page_check") return "페이지 수동 확인 필요";
  return "검증 상태 확인 필요";
}

export function latestAuditOpinion(insight) {
  const opinions = Array.isArray(insight?.source_summary?.audit_opinions)
    ? insight.source_summary.audit_opinions
    : [];
  return [...opinions].sort((a, b) => String(b.auditor_report_date || "").localeCompare(String(a.auditor_report_date || "")))[0] || null;
}

export function sourceSectionCounts(insight) {
  const counts = new Map();
  const collect = (metric) => {
    for (const location of metric?.source_locations || []) {
      if (!location?.section) continue;
      counts.set(location.section, (counts.get(location.section) || 0) + 1);
    }
  };
  for (const row of insight?.financial_series || []) {
    for (const metric of Object.values(row.metrics || {})) collect(metric);
  }
  return Object.keys(REPORT_SECTION_LABELS)
    .map((section) => ({ section, label: reportSectionLabel(section), count: counts.get(section) || 0 }))
    .sort((a, b) => a.label.localeCompare(b.label, "ko"));
}
