import {
  getCompanyDataStatus,
  getCompanyDataStatusLabel,
  getCompanyEvents,
  getCompanyProjectSummary,
  getCompanyTypeLabel,
  getCompetitiveRoleLabel,
  getLatestFinancial,
  getTierLabel,
  isModularSpecialistCompany,
  isConfirmedProductionFacility,
  metricSourceValue,
  MODULAR_SPECIALIST_ROLE,
  MODULAR_SPECIALIST_COMPANY_TYPES,
  productionFacilities,
  productionSummary,
  technologyCount,
} from "./companyInsights.js";

export const PRODUCER_GROUP_ROLE = MODULAR_SPECIALIST_ROLE;
export const PRODUCER_COMPANY_TYPES = MODULAR_SPECIALIST_COMPANY_TYPES;
export const MAX_COMPARISON_COMPANIES = 4;
export const MIN_COMPARISON_COMPANIES = 2;

export const COMPANY_COMPARISON_SORT_OPTIONS = [
  { value: "tier", label: "분석 우선순위" },
  { value: "name", label: "기업명" },
  { value: "revenue", label: "최근 매출 높은 순" },
  { value: "operating_margin", label: "영업이익률 높은 순" },
  { value: "production", label: "생산시설 많은 순" },
  { value: "verified_projects", label: "검증 프로젝트 많은 순" },
  { value: "technology", label: "기술·특허 많은 순" },
  { value: "verified", label: "최신 검증순" },
];

const CREDIT_EVENT_STATUSES = new Set(["completed", "under_construction", "contracted", "award_confirmed", "awarded", "contract_signed", "in_progress"]);

export function getLatestFinancialYear(company) {
  const latest = getLatestFinancial(company);
  const year = Number(latest?.year || latest?.fiscal_year);
  return Number.isFinite(year) ? year : null;
}

export function getLatestRevenue(company) {
  return metricSourceValue(getLatestFinancial(company)?.revenue);
}

export function getLatestOperatingProfit(company) {
  return metricSourceValue(getLatestFinancial(company)?.operating_profit);
}

export function getOperatingMargin(company) {
  const revenue = getLatestRevenue(company);
  const operatingProfit = getLatestOperatingProfit(company);
  if (revenue === null || operatingProfit === null || revenue === 0) return null;
  return (operatingProfit / revenue) * 100;
}

export function getConfirmedProductionFacilityCount(company) {
  const facilities = productionFacilities(company);
  const summary = productionSummary(company);
  if (!facilities.length && !summary?.confirmed_facility_count && !summary?.own_facility_status && !summary?.verification_status) return null;
  return facilities.filter(isConfirmedProductionFacility).length;
}

export function getPlannedProductionFacilityCount(company) {
  return productionFacilities(company).filter((facility) => (
    facility?.operation_status === "planned" ||
    facility?.operation_status === "under_construction" ||
    facility?.ownership_type === "planned" ||
    facility?.own_facility_status === "planned_facility"
  )).length;
}

export function getVerifiedProjectCount(company) {
  const events = getCompanyEvents(company, "project");
  if (events.length) {
    return events.filter((event) => (
      event.project_credit === true &&
      CREDIT_EVENT_STATUSES.has(event.event_status)
    )).length;
  }
  return getCompanyProjectSummary(company).verified;
}

export function getPipelineProjectCount(company) {
  const summary = getCompanyProjectSummary(company);
  return Number(summary.candidates || 0) + Number(summary.partnerships || 0) + Number(summary.researchAndExhibition || 0);
}

export function getTechnologyCount(company) {
  return technologyCount(company);
}

export function getPrimaryTargetMarkets(company, limit = 3) {
  return Array.isArray(company?.target_markets) ? company.target_markets.filter(Boolean).slice(0, limit) : [];
}

export function getModularMethodLabels(company, limit = 2) {
  return Array.isArray(company?.modular_methods) ? company.modular_methods.filter(Boolean).slice(0, limit) : [];
}

export function getComparisonMetric(company) {
  const revenue = getLatestRevenue(company);
  const operatingProfit = getLatestOperatingProfit(company);
  const operatingMargin = getOperatingMargin(company);
  const productionConfirmed = getConfirmedProductionFacilityCount(company);
  const productionPlanned = getPlannedProductionFacilityCount(company);
  const verifiedProjects = getVerifiedProjectCount(company);
  const pipelineProjects = getPipelineProjectCount(company);
  const techCount = getTechnologyCount(company);
  return {
    company_id: company.company_id,
    company_name: company.company_name,
    company_name_en: company.company_name_en || "",
    typeLabel: getCompanyTypeLabel(company),
    relationshipLabel: getCompetitiveRoleLabel(company),
    tierLabel: getTierLabel(company),
    dataStatus: getCompanyDataStatus(company),
    dataStatusLabel: getCompanyDataStatusLabel(company),
    latestFinancialYear: getLatestFinancialYear(company),
    revenue,
    operatingProfit,
    operatingMargin,
    productionConfirmed,
    productionPlanned,
    verifiedProjects,
    pipelineProjects,
    technologyCount: techCount,
    targetMarkets: getPrimaryTargetMarkets(company),
    modularMethods: getModularMethodLabels(company),
    comparisonStatus: getComparisonReadiness({
      revenue,
      operatingMargin,
      productionConfirmed,
      verifiedProjects,
      techCount,
    }),
  };
}

export function getComparisonReadiness(metric) {
  const missing = [];
  if (metric.revenue === null) missing.push("재무");
  if (metric.productionConfirmed === null || metric.productionConfirmed === 0) missing.push("생산시설");
  if (metric.verifiedProjects === 0) missing.push("검증 실적");
  if (metric.techCount === 0) missing.push("기술·특허");
  if (!missing.length) return "비교 가능";
  if (missing.length === 1 && missing[0] === "재무") return "재무 미확인";
  if (missing.length === 1 && missing[0] === "생산시설") return "생산시설 미확인";
  return "일부 항목 미확인";
}

export function isProducerCompany(company) {
  return isModularSpecialistCompany(company);
}

export function matchesComparisonRole(company, role) {
  if (role === PRODUCER_GROUP_ROLE || role === "producer_group") return isProducerCompany(company);
  return company?.company_type === role;
}

function nullLastNumber(value) {
  return value === null || value === undefined || Number.isNaN(Number(value)) ? null : Number(value);
}

function compareNumberDesc(aValue, bValue) {
  const a = nullLastNumber(aValue);
  const b = nullLastNumber(bValue);
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return b - a;
}

export function compareCompaniesForMvp(a, b, sort, fallbackCompare) {
  const aMetric = getComparisonMetric(a);
  const bMetric = getComparisonMetric(b);
  let delta = 0;
  if (sort === "revenue") delta = compareNumberDesc(aMetric.revenue, bMetric.revenue);
  if (sort === "operating_margin") delta = compareNumberDesc(aMetric.operatingMargin, bMetric.operatingMargin);
  if (sort === "production") delta = compareNumberDesc(aMetric.productionConfirmed, bMetric.productionConfirmed);
  if (sort === "verified_projects") delta = compareNumberDesc(aMetric.verifiedProjects, bMetric.verifiedProjects);
  if (sort === "technology") delta = compareNumberDesc(aMetric.technologyCount, bMetric.technologyCount);
  if (delta !== 0) return delta;
  return fallbackCompare(a, b, sort === "tier" || sort === "verified" || sort === "name" ? sort : "name");
}

export function normalizeComparisonSelection(ids, companies) {
  const allowed = new Set((Array.isArray(companies) ? companies : []).map((company) => company.company_id));
  const output = [];
  for (const id of Array.isArray(ids) ? ids : []) {
    if (!allowed.has(id) || output.includes(id)) continue;
    output.push(id);
    if (output.length === MAX_COMPARISON_COMPANIES) break;
  }
  return output;
}

export function parseCompareParam(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function serializeCompareSelection(ids) {
  return (Array.isArray(ids) ? ids : []).join(",");
}
