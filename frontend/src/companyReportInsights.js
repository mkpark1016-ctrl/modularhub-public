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
  { key: "receivables_total", label: "채권 합계" },
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
  { key: "receivables_to_revenue_pct", label: "채권/매출 비율" },
  { key: "inventory_to_revenue_pct", label: "재고/매출 비율" },
];

export const REPORT_REVENUE_BREAKDOWN_ROWS = [
  { key: "product_revenue", label: "제품매출" },
  { key: "rental_revenue", label: "임대매출" },
  { key: "service_revenue", label: "용역매출" },
  { key: "construction_revenue", label: "공사매출" },
  { key: "other_revenue", label: "기타매출" },
];

export function reportRevenueShareKey(metricKey) {
  return `${metricKey}_share_pct`;
}

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
  if (metric?.display_text) return metric.display_text;
  if (metric?.disclosure_status === "not_disclosed") return "공시되지 않음";
  if (metric?.disclosure_status === "not_applicable") return "해당 없음";
  return "확인되지 않음";
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
  if (status === "not_disclosed") return "공시되지 않음";
  if (status === "not_applicable") return "해당 없음";
  if (status === "verification_pending") return "검증 보류";
  return "검증 상태 확인 필요";
}

export const DECISION_STATUS_LABELS = {
  increased: "증가",
  decreased: "감소",
  flat: "변화 없음",
  unknown: "확인 필요",
  additional_confirmation_required: "추가 확인 필요",
  info: "참고",
  watch: "관찰 필요",
};

export const EVIDENCE_DOMAIN_LABELS = {
  financial: "재무",
  disclosure_scope: "공시 범위",
  identity: "법인정보",
  production: "생산시설",
  project: "프로젝트",
  technology: "기술·특허",
  recent_signal: "최근 활동",
};

export const PEER_BENCHMARK_LABELS = {
  revenue: "매출",
  operating_margin_pct: "영업이익률",
  operating_cash_flow: "영업현금흐름",
  total_borrowings: "총차입금",
  liabilities_to_equity_pct: "부채비율",
  receivables_to_revenue_pct: "채권/매출 비율",
};

export function decisionStatusLabel(status) {
  return DECISION_STATUS_LABELS[status] || "확인 필요";
}

export function decisionStatusTone(status) {
  if (status === "watch" || status === "additional_confirmation_required") return "watch";
  if (status === "decreased") return "neutral";
  if (status === "unknown") return "pending";
  return "info";
}

export function evidenceDomainLabel(domain) {
  return EVIDENCE_DOMAIN_LABELS[domain] || "검증 영역";
}

export function peerBenchmarkLabel(metricId) {
  return PEER_BENCHMARK_LABELS[metricId] || metricId;
}

export function latestSnapshotMetric(insight, metricKey) {
  return insight?.latest_snapshot?.[metricKey] || null;
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
