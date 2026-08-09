import {
  getCompanyDataGapCount,
  getCompanyResearchGapCount,
  getCompanyEvents,
  getCompanyVerificationLevel,
  getVerificationLevelLabel,
  productionSummary,
} from "./companyInsights.js";
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
} from "./components/company/companyDetailHelpers.js";
import {
  decisionStatusLabel,
  financialScopeLabel,
  latestSnapshotMetric,
  metricDisplayText,
  reportMetricByYear,
  reportRatioByYear,
  reportYears,
} from "./companyReportInsights.js";

const UNKNOWN = "확인되지 않음";

const POSITION_EVENT_TYPES = new Set(["business_strategy", "facility_investment", "policy_signal", "product_launch"]);

const POSITION_EVENT_STATUS = new Set([
  "completed",
  "in_progress",
  "contract_signed",
  "award_confirmed",
  "planned",
]);

const MARKET_POSITION_LABELS = {
  public_housing: "공공주택 정비",
  school: "학교 모듈러 중심",
  education: "학교 모듈러 중심",
  dormitory: "기숙사 모듈러 중심",
  military: "군시설 모듈러 중심",
  office: "업무시설 정비",
  industrial: "산업시설 정비",
  data_center: "데이터센터 정비",
  research_facility: "연구시설 정비",
};

const METHOD_POSITION_LABELS = {
  steel_volumetric: "스틸 볼류메트릭",
  steel_panelized: "스틸 패널",
  steel_modular_units: "스틸 모듈러 유닛",
  container: "컨테이너형 모듈러",
  hybrid: "하이브리드 공법",
};

const MANUFACTURING_POSITION_LABELS = {
  own_manufacturing: "생산기반 정비",
  contract_manufacturing: "위탁 생산 기반",
  hybrid_manufacturing: "복합 생산 기반",
};

const FORBIDDEN_POSITION_LABELS = new Set([
  "건설사",
  "모듈러 제작 전문 업체",
  "직접 경쟁사",
  "대체 경쟁사",
  "전략 벤치마크",
  "최우선 분석",
  "우선 분석",
  "감사재무 적용",
  "기존 재무 표시",
]);

const WATCH_SIGNAL_LABELS = {
  operating_cash_flow_negative: "영업현금흐름 유출",
  operating_cash_flow_declined: "영업현금흐름 하락",
  operating_margin_declined: "영업이익률 하락",
  revenue_decreased: "매출 감소",
  borrowings_increased: "차입금 증가",
  liabilities_to_equity_increased: "부채비율 상승",
};

const WARNING_LABELS = {
  modular_segment_revenue_not_disclosed: "모듈러 매출 미공시",
  verification_pending_total_equity: "검증 보류",
  pending_manual_page_check: "페이지 확인 필요",
};

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function labelList(values, max = 3) {
  const labels = unique((Array.isArray(values) ? values : []).map((value) => labelValue(value, "")));
  const visible = labels.slice(0, max);
  if (labels.length > max) visible.push(`+${labels.length - max}`);
  return visible;
}

function shortEventTitle(event) {
  const title = String(event?.title || "").trim();
  if (!title || title.length > 18) return "";
  return title;
}

function positionKeywords(company) {
  const summary = productionSummary(company);
  const events = getCompanyEvents(company);
  const eventSignals = events
    .filter((event) => POSITION_EVENT_TYPES.has(event.event_type) && POSITION_EVENT_STATUS.has(event.event_status))
    .map(shortEventTitle);
  const marketSignals = (company.target_markets || []).map((market) => MARKET_POSITION_LABELS[market]).filter(Boolean);
  const methodSignals = (company.modular_methods || []).map((method) => METHOD_POSITION_LABELS[method]).filter(Boolean);
  const productionSignal = MANUFACTURING_POSITION_LABELS[summary.manufacturing_model];
  return unique([
    ...eventSignals,
    productionSignal,
    ...marketSignals,
    ...methodSignals,
  ]).filter((item) => !FORBIDDEN_POSITION_LABELS.has(item)).slice(0, 5);
}

function capabilityKeywords(company, model) {
  const summary = productionSummary(company);
  const facilities = Array.isArray(company.production_facilities) ? company.production_facilities : [];
  const events = model.events || [];
  const technology = model.technologyItems || [];
  const verifiedProjectMarkets = unique(events
    .filter((event) => event.event_type === "project" && event.project_credit)
    .map((event) => event.market_segment)
    .map((market) => labelValue(market, "")))
    .map((label) => `${label} 실적`);
  const hasOwnedFacility = facilities.some((facility) => ["owned", "subsidiary_owned", "affiliate_owned"].includes(facility.ownership_type))
    || summary.own_facility_status === "confirmed_own_facility";
  const hasCapacity = summary.reported_capacity_available === true
    || facilities.some((facility) => facility.reported_capacity !== null && facility.reported_capacity !== undefined);
  const hasPatent = technology.some((item) => ["patent", "patents", "patent_application"].includes(item.record_type || item.group));
  const hasNewTechnology = technology.some((item) => item.record_type === "construction_new_technology" || item.group === "new_construction_technologies");
  const hasCertification = technology.some((item) => ["certification", "innovative_product", "innovative_procurement_products"].includes(item.record_type || item.group));
  return unique([
    hasOwnedFacility ? "자체 생산" : "",
    hasOwnedFacility ? "자체 공장" : "",
    hasCapacity ? "생산능력 공개" : "",
    ...verifiedProjectMarkets,
    hasPatent ? "등록특허" : "",
    hasNewTechnology ? "건설신기술" : "",
    hasCertification ? "공업화주택 인증" : "",
    (company.modular_methods || []).includes("hybrid") ? "하이브리드 공법" : "",
  ]).slice(0, 5);
}

function watchLabelFromSignal(signal) {
  if (WATCH_SIGNAL_LABELS[signal?.code]) return WATCH_SIGNAL_LABELS[signal.code];
  const code = String(signal?.code || "");
  if (code.includes("operating_margin") && code.includes("declin")) return "영업이익률 하락";
  if (code.includes("cash_flow") && (code.includes("negative") || code.includes("declin"))) return "영업현금흐름 유출";
  return "";
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
  const summary = productionSummary(company);
  for (const signal of reportInsight?.trend_signals || []) {
    const label = watchLabelFromSignal(signal);
    if (label && (signal.level === "watch" || label.includes("하락") || label.includes("증가"))) signals.push(label);
  }
  for (const warning of reportInsight?.disclosure_warnings || []) {
    const label = WARNING_LABELS[warning.code];
    if (label) signals.push(label);
  }
  if (summary.reported_capacity_available === false || summary.verification_status === "research_exhausted") {
    signals.push("생산능력 미확인");
  }
  if (gapCount > 0 && signals.length === 0) signals.push(`보완 필요 ${formatNumber(gapCount, "건")}`);
  if (researchGapCount > 0 && signals.length < 3) signals.push(`조사 공백 ${formatNumber(researchGapCount, "건")}`);
  if (reportInsight?.source_summary?.pending_location_count > 0) {
    signals.push("페이지 확인 필요");
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
  const position = positionKeywords(company);
  const capabilities = capabilityKeywords(company, model);
  return {
    name: company.company_name,
    englishName: company.company_name_en,
    summary: model.header.summary,
    badges: [
      { key: "type", label: model.header.typeLabel },
      { key: "relation", label: model.header.relationshipLabel },
      { key: "status", label: model.header.dataStatusLabel, className: `company-status ${model.header.dataStatus}` },
    ],
    positionKeywords: position,
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
