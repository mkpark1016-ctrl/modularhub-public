import {
  getCompanyDataGapCount,
  getCompanyResearchGapCount,
  getCompanyVerificationLevel,
  getVerificationLevelLabel,
} from "./companyInsights";
import {
  detailModel,
  eventDate,
  eventStatusLabel,
  formatDate,
  formatKrw,
  formatNumber,
  formatPercent,
  labelValue,
  metricMargin,
} from "./components/company/companyDetailHelpers";
import {
  decisionStatusLabel,
  financialScopeLabel,
  latestSnapshotMetric,
  metricDisplayText,
  reportMetricByYear,
  reportRatioByYear,
  reportYears,
} from "./companyReportInsights";

const UNKNOWN = "확인되지 않음";

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function labelList(values, max = 3) {
  const labels = unique((Array.isArray(values) ? values : []).map((value) => labelValue(value, "")));
  const visible = labels.slice(0, max);
  if (labels.length > max) visible.push(`+${labels.length - max}`);
  return visible;
}

function reportMetricText(insight, key) {
  const metric = latestSnapshotMetric(insight, key) || insight?.latest_metrics?.[key] || null;
  return metricDisplayText(metric);
}

function legacyMetricText(model, key) {
  const latest = model.financials[0] || {};
  if (key === "revenue") {
    return model.kpis.latestRevenueYear ? `${model.kpis.latestRevenueYear}년 ${formatKrw(model.kpis.latestRevenue)}` : UNKNOWN;
  }
  if (key === "operating_margin_pct") {
    return formatPercent(metricMargin(latest.operating_profit, latest.revenue));
  }
  if (key === "operating_cash_flow") {
    return formatKrw(latest.operating_cash_flow);
  }
  return UNKNOWN;
}

function metricItems(company, model, reportInsight) {
  return [
    {
      key: "revenue",
      label: "최근 매출",
      value: reportInsight ? reportMetricText(reportInsight, "revenue") : legacyMetricText(model, "revenue"),
    },
    {
      key: "operating_margin",
      label: "영업이익률",
      value: reportInsight
        ? metricDisplayText(reportRatioByYear(reportInsight, reportInsight.latest_year, "operating_margin_pct"))
        : legacyMetricText(model, "operating_margin_pct"),
    },
    {
      key: "operating_cash_flow",
      label: "영업현금흐름",
      value: reportInsight ? reportMetricText(reportInsight, "operating_cash_flow") : legacyMetricText(model, "operating_cash_flow"),
    },
    {
      key: "production",
      label: "생산시설",
      value: formatNumber(model.kpis.productionFacilities, "건"),
    },
    {
      key: "verified_projects",
      label: "검증 프로젝트",
      value: formatNumber(model.kpis.verifiedProjects, "건"),
    },
    {
      key: "technology",
      label: "기술·특허",
      value: formatNumber(model.kpis.technologyCount, "건"),
    },
  ];
}

function recentSignal(activities = [], model) {
  const activity = activities[0];
  if (activity) {
    return {
      title: activity.title,
      meta: formatDate(activity.publishedAt),
    };
  }
  const recentEvent = [...model.events]
    .filter((event) => eventDate(event))
    .sort((a, b) => String(eventDate(b)).localeCompare(String(eventDate(a))))[0];
  if (recentEvent) {
    return {
      title: recentEvent.title || eventStatusLabel(recentEvent),
      meta: formatDate(eventDate(recentEvent)),
    };
  }
  return {
    title: "최근 공개 활동 확인 중",
    meta: "신규 수집 신호 없음",
  };
}

function watchSignals(company, reportInsight) {
  const signals = [];
  const gapCount = getCompanyDataGapCount(company, reportInsight);
  const researchGapCount = getCompanyResearchGapCount(company);
  const reportWatch = (reportInsight?.trend_signals || []).find((signal) => signal.level === "watch");
  if (reportWatch?.description) signals.push(reportWatch.description);
  if (gapCount > 0) signals.push(`보완 필요 ${formatNumber(gapCount, "건")}`);
  if (researchGapCount > 0) signals.push(`조사 공백 ${formatNumber(researchGapCount, "건")}`);
  if (reportInsight?.source_summary?.pending_location_count > 0) {
    signals.push(`수동 페이지 확인 ${formatNumber(reportInsight.source_summary.pending_location_count, "건")}`);
  }
  return unique(signals).slice(0, 3);
}

function financialSignals(reportInsight) {
  if (!reportInsight) return [];
  const years = reportYears(reportInsight);
  if (years.length === 0) return [];
  const latestYear = years[years.length - 1];
  const previousYear = years[years.length - 2];
  const trends = Object.values(reportInsight.trends || {}).slice(0, 3).map((trend) => ({
    title: trend.headline,
    body: trend.explanation,
    meta: [decisionStatusLabel(trend.status), trend.change_display || trend.change_pct_unavailable_reason].filter(Boolean).join(" · "),
  }));
  const fallback = [
    {
      title: "최근 매출",
      body: `${latestYear}년 ${metricDisplayText(reportMetricByYear(reportInsight, latestYear, "revenue"))}`,
      meta: previousYear ? `${previousYear}년 대비 추이 확인` : "단일 연도 기준",
    },
    {
      title: "영업현금흐름",
      body: `${latestYear}년 ${metricDisplayText(reportMetricByYear(reportInsight, latestYear, "operating_cash_flow"))}`,
      meta: "현금흐름표 기준",
    },
  ];
  return trends.length ? trends : fallback;
}

export function buildCompanyDecisionModel(company, { reportInsight = null, activities = [] } = {}) {
  const model = detailModel(company);
  const targetMarkets = labelList(company.target_markets, 4);
  const modularMethods = labelList(company.modular_methods, 3);
  const positionKeywords = unique([
    model.header.typeLabel,
    model.header.relationshipLabel,
    model.header.tierLabel,
    reportInsight ? "감사재무 적용" : "기존 재무 표시",
  ]);
  const capabilities = unique([
    model.kpis.productionFacilities > 0 ? `생산시설 ${formatNumber(model.kpis.productionFacilities, "건")}` : "생산시설 확인 중",
    model.kpis.verifiedProjects > 0 ? `검증 프로젝트 ${formatNumber(model.kpis.verifiedProjects, "건")}` : "검증 프로젝트 확인 중",
    model.kpis.technologyCount > 0 ? `기술·특허 ${formatNumber(model.kpis.technologyCount, "건")}` : "기술·특허 확인 중",
  ]);
  return {
    name: company.company_name,
    englishName: company.company_name_en,
    summary: model.header.summary,
    badges: [
      { key: "type", label: model.header.typeLabel },
      { key: "relation", label: model.header.relationshipLabel },
      { key: "status", label: model.header.dataStatusLabel, className: `company-status ${model.header.dataStatus}` },
    ],
    positionKeywords,
    targetMarkets,
    modularMethods,
    capabilities,
    watchSignals: watchSignals(company, reportInsight),
    metrics: metricItems(company, model, reportInsight),
    cardMetrics: metricItems(company, model, reportInsight).slice(0, 4),
    recentSignal: recentSignal(activities, model),
    financialSignals: financialSignals(reportInsight),
    trust: {
      verificationLevel: getVerificationLevelLabel(getCompanyVerificationLevel(company)),
      verifiedAt: formatDate(model.header.latestVerifiedAt),
      confidence: model.header.confidenceLabel,
      financialScope: reportInsight ? financialScopeLabel(reportInsight.financial_scope || reportInsight.attribution?.financial_scope) : UNKNOWN,
      sourceCount: reportInsight?.source_summary?.verified_location_count ?? null,
      pendingSourceCount: reportInsight?.source_summary?.pending_location_count ?? null,
    },
  };
}

