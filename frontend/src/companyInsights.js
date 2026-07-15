export const COMPANY_TYPE_LABELS = {
  general_contractor: "건설사",
  specialist_manufacturer: "전문 제작사",
  modular_integrator: "모듈러 통합사",
  design_firm: "설계사",
  engineering_firm: "엔지니어링사",
  material_supplier: "자재 공급사",
  solution_provider: "솔루션 기업",
};

export const COMPETITIVE_ROLE_LABELS = {
  direct_competitor: "직접 경쟁사",
  substitute_competitor: "대체 경쟁사",
  strategic_benchmark: "전략 벤치마크",
  design_influencer: "설계 영향사",
  internal_baseline: "내부 기준",
  watchlist: "관찰 대상",
};

export const TIER_LABELS = {
  tier_1: "최우선 분석",
  tier_1b: "우선 분석",
  tier_2: "일반 분석",
  tier_3: "장기 관찰",
};

export const REVIEW_STATUS_LABELS = {
  verified: "검증 완료",
  partially_verified: "부분 검증",
  collecting: "조사 중",
  unresearched: "조사 중",
  update_required: "확인 필요",
  manual_review_required: "확인 필요",
  unknown: "조사 중",
};

export const DATA_STATUS_LABELS = {
  verified: "검증 완료",
  partial: "부분 검증",
  collecting: "조사 중",
};

export const CONFIDENCE_LABELS = {
  high: "높은 신뢰도",
  medium: "보통 신뢰도",
  low: "낮은 신뢰도",
  review: "검토 필요",
  unknown: "확인 중",
  verified_manual: "수동 검증",
};

export const PROJECT_ROLE_LABELS = {
  modular_manufacturer: "모듈러 제작",
  general_contractor: "종합 시공",
  specialist_contractor: "전문 시공",
  designer: "설계",
  engineering: "엔지니어링",
  supplier: "자재 공급",
  installer: "설치",
  developer: "개발",
  consortium_member: "공동 참여",
  manufacturer: "제작",
  structural_supplier: "구조 공급",
  rental_provider: "임대",
  technology_provider: "기술 제공",
  unknown: "역할 확인 중",
};

export const PROJECT_STATUS_LABELS = {
  planned: "계획",
  bidding: "입찰",
  bid: "입찰",
  awarded: "수주",
  contracted: "계약",
  under_construction: "진행 중",
  completed: "완료",
  suspended: "중단",
  cancelled: "취소",
  unknown: "상태 확인 중",
};

export const STRUCTURE_TYPE_LABELS = {
  steel_modular: "스틸 모듈러",
  steel_volumetric: "스틸 모듈러",
  steel_frame_panelized: "스틸 패널",
  precast_concrete_modular: "PC 모듈러",
  precast_concrete: "PC",
  timber_modular: "목조 모듈러",
  container: "컨테이너",
  hybrid: "하이브리드",
  unknown: "공법 확인 중",
};

const ROLE_SORT_ORDER = ["direct_competitor", "substitute_competitor", "strategic_benchmark", "design_influencer", "internal_baseline", "watchlist"];
const TIER_SORT_ORDER = ["tier_1", "tier_1b", "tier_2", "tier_3"];

export function getCompanyItems(data) {
  if (!data) return [];
  if (Array.isArray(data)) return data;
  return Array.isArray(data.companies) ? data.companies : [];
}

export function normalizeCompanyText(value) {
  return String(value || "")
    .normalize("NFC")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

export function labelFromMap(map, value, fallback = "확인 중") {
  return map[value] || fallback;
}

export function getCompanyTypeLabel(company) {
  return labelFromMap(COMPANY_TYPE_LABELS, company?.company_type);
}

export function getCompetitiveRoleLabel(company) {
  return labelFromMap(COMPETITIVE_ROLE_LABELS, company?.competitive_role);
}

export function getTierLabel(company) {
  return labelFromMap(TIER_LABELS, company?.analysis_tier);
}

export function getReviewStatusLabel(company) {
  return labelFromMap(REVIEW_STATUS_LABELS, company?.review_status || "unknown");
}

export function getConfidenceLabel(company) {
  return labelFromMap(CONFIDENCE_LABELS, company?.data_confidence || "unknown");
}

export function getProjectRoleLabel(project) {
  return labelFromMap(PROJECT_ROLE_LABELS, project?.company_role || "unknown");
}

export function getProjectStatusLabel(project) {
  return labelFromMap(PROJECT_STATUS_LABELS, project?.project_status || "unknown");
}

export function getStructureTypeLabel(project) {
  return labelFromMap(STRUCTURE_TYPE_LABELS, project?.structure_type || project?.modular_method || project?.modular_type || "unknown");
}

export function financialYears(company) {
  return (Array.isArray(company?.financials) ? company.financials : [])
    .map((item) => Number(item?.year))
    .filter((year) => Number.isFinite(year))
    .sort((a, b) => b - a);
}

export function isDartIdentityConfirmed(company) {
  return company?.dart_identity?.identity_status === "confirmed" && Boolean(company?.dart_identity?.dart_corp_code);
}

export function getCompanyDataStatus(company) {
  const reviewStatus = company?.review_status;
  if (reviewStatus === "verified") return "verified";
  if (isDartIdentityConfirmed(company) && financialYears(company).length >= 3) return "verified";
  if (reviewStatus === "partially_verified" || financialYears(company).length > 0 || (company?.sources || []).length > 0) return "partial";
  return "collecting";
}

export function getCompanyDataStatusLabel(company) {
  return DATA_STATUS_LABELS[getCompanyDataStatus(company)] || "조사 중";
}

export function getLatestVerifiedAt(company) {
  const dates = [
    company?.last_verified_at,
    company?.financial_summary?.verified_at,
    ...(Array.isArray(company?.sources) ? company.sources.map((source) => source.accessed_at || source.published_at) : []),
  ].filter(Boolean);
  return dates.sort().at(-1) || "";
}

export function companySearchText(company) {
  const projects = Array.isArray(company?.project_portfolio) ? company.project_portfolio : [];
  const candidates = projectCandidates(company);
  const technology = company?.technology && typeof company.technology === "object" ? company.technology : {};
  const technologyValues = Object.values(technology).flatMap((value) => {
    if (Array.isArray(value)) return value;
    if (value && typeof value === "object") return Object.values(value);
    return [value];
  });
  const production = Array.isArray(company?.production) ? company.production : [];
  const productionInfo = productionSummary(company);
  const signals = Array.isArray(company?.recent_signals) ? company.recent_signals : [];
  return normalizeCompanyText([
    company?.company_name,
    company?.company_name_en,
    ...(Array.isArray(company?.aliases) ? company.aliases : []),
    getCompanyTypeLabel(company),
    getCompetitiveRoleLabel(company),
    getTierLabel(company),
    ...(Array.isArray(company?.modular_methods) ? company.modular_methods : []),
    ...(Array.isArray(company?.target_markets) ? company.target_markets : []),
    company?.summary,
    productionInfo.summary,
    productionInfo.manufacturing_model,
    productionInfo.own_facility_status,
    ...production.flatMap((item) => [
      item.facility_name,
      ...(Array.isArray(item.facility_aliases) ? item.facility_aliases : []),
      item.location,
      item.region,
      item.city,
      item.address,
      item.capacity_unit,
      item.capacity_basis,
      ...(Array.isArray(item.production_scope) ? item.production_scope : []),
    ]),
    ...projects.flatMap((item) => [
      item.project_name,
      ...(Array.isArray(item.aliases) ? item.aliases : []),
      item.client,
      item.client_name,
      item.ordering_agency,
      item.location,
      item.sector,
      item.building_use,
      item.structure_type,
      item.modular_type,
      item.modular_method,
      item.company_role,
      getProjectRoleLabel(item),
      getProjectStatusLabel(item),
      getStructureTypeLabel(item),
      item.role_detail,
      item.project_summary,
      item.significance,
    ]),
    ...candidates.flatMap((item) => [
      item.candidate_title,
      item.matched_alias,
      item.matched_context,
      item.possible_client,
      item.possible_location,
      item.possible_role,
      item.source_dataset,
      item.review_status,
    ]),
    ...technologyValues.map((item) => {
      if (item && typeof item === "object") return [item.name, item.summary, item.technology_area, item.status].join(" ");
      return item;
    }),
    ...signals.flatMap((item) => [item.title, item.summary, item.signal_type]),
  ].join(" "));
}

export function matchesCompanySearch(company, query) {
  const terms = normalizeCompanyText(query).split(" ").filter(Boolean);
  if (!terms.length) return true;
  const text = companySearchText(company);
  return terms.every((term) => text.includes(term));
}

export function companyMatchesFilters(company, values) {
  if (values.role !== "all" && company.company_type !== values.role) return false;
  if (values.relationship !== "all" && company.competitive_role !== values.relationship) return false;
  if (values.tier !== "all" && company.analysis_tier !== values.tier) return false;
  if (values.status !== "all" && getCompanyDataStatus(company) !== values.status) return false;
  return matchesCompanySearch(company, values.q);
}

export function compareCompanies(a, b, sort = "tier") {
  if (sort === "verified") {
    return String(getLatestVerifiedAt(b)).localeCompare(String(getLatestVerifiedAt(a))) || compareCompanies(a, b, "tier");
  }
  if (sort === "name") {
    return String(a.company_name || "").localeCompare(String(b.company_name || ""), "ko-KR");
  }
  const tierDelta = TIER_SORT_ORDER.indexOf(a.analysis_tier) - TIER_SORT_ORDER.indexOf(b.analysis_tier);
  if (tierDelta !== 0) return tierDelta;
  const roleDelta = ROLE_SORT_ORDER.indexOf(a.competitive_role) - ROLE_SORT_ORDER.indexOf(b.competitive_role);
  if (roleDelta !== 0) return roleDelta;
  return String(a.company_name || "").localeCompare(String(b.company_name || ""), "ko-KR");
}

export function optionCounts(companies, field, labelMap) {
  const counts = new Map();
  for (const company of companies) {
    const value = company?.[field];
    if (!value) continue;
    counts.set(value, (counts.get(value) || 0) + 1);
  }
  return [...counts.entries()]
    .sort(([a], [b]) => String(labelMap[a] || a).localeCompare(String(labelMap[b] || b), "ko-KR"))
    .map(([value, count]) => ({ value, label: labelMap[value] || value, count }));
}

export function statusOptions(companies) {
  const counts = new Map();
  for (const company of companies) {
    const status = getCompanyDataStatus(company);
    counts.set(status, (counts.get(status) || 0) + 1);
  }
  return ["verified", "partial", "collecting"]
    .filter((value) => counts.has(value))
    .map((value) => ({ value, label: DATA_STATUS_LABELS[value], count: counts.get(value) }));
}

export function getCompanySummary(companies) {
  const list = Array.isArray(companies) ? companies : [];
  return {
    total: list.length,
    directCompetitors: list.filter((company) => company.competitive_role === "direct_competitor").length,
    verified: list.filter((company) => getCompanyDataStatus(company) === "verified").length,
    facilityConfirmed: list.filter((company) => hasConfirmedProductionFacility(company)).length,
    roleCounts: optionCounts(list, "company_type", COMPANY_TYPE_LABELS),
    relationshipCounts: optionCounts(list, "competitive_role", COMPETITIVE_ROLE_LABELS),
    statusCounts: statusOptions(list),
  };
}

export const CONFIRMED_FACILITY_STATUSES = new Set([
  "confirmed_own_facility",
  "confirmed_leased_facility",
  "confirmed_partner_manufacturing",
]);

export const EXCLUDED_FACILITY_STATUSES = new Set([
  "not_publicly_confirmed",
  "research_in_progress",
  "historical_facility",
  "planned_facility",
  "ceased_operation",
]);

export function productionSummary(company) {
  return company?.production_summary && typeof company.production_summary === "object" ? company.production_summary : {};
}

export function productionFacilities(company) {
  return Array.isArray(company?.production) ? company.production : [];
}

export function isConfirmedProductionFacility(facility) {
  if (!facility || typeof facility !== "object") return false;
  const status = facility.own_facility_status || facility.verification_status || facility.operation_status;
  if (EXCLUDED_FACILITY_STATUSES.has(status)) return false;
  if (CONFIRMED_FACILITY_STATUSES.has(status)) return true;
  return Boolean(facility.facility_name && Array.isArray(facility.source_ids) && facility.source_ids.length);
}

export function hasConfirmedProductionFacility(company) {
  const summary = productionSummary(company);
  if (EXCLUDED_FACILITY_STATUSES.has(summary.own_facility_status)) return false;
  if (summary.own_facility_status === "confirmed_partner_manufacturing" && !productionFacilities(company).some(isConfirmedProductionFacility)) return false;
  if (CONFIRMED_FACILITY_STATUSES.has(summary.own_facility_status)) return true;
  return productionFacilities(company).some(isConfirmedProductionFacility);
}

export function getProductionModelLabel(company) {
  const summary = productionSummary(company);
  const model = summary.manufacturing_model;
  if (summary.own_facility_status === "confirmed_own_facility" || model === "own_manufacturing") return "자체 공장 확인";
  if (summary.own_facility_status === "confirmed_leased_facility" || model === "leased_facility") return "임차 생산 확인";
  if (summary.own_facility_status === "confirmed_partner_manufacturing" || model === "partner_manufacturing") return "협력 제작 확인";
  if (model === "outsourced_manufacturing") return "위탁 생산 확인";
  return "생산정보 조사 중";
}

export function getLatestFinancial(company) {
  const financials = Array.isArray(company?.financials) ? company.financials : [];
  return [...financials].sort((a, b) => Number(b.year || 0) - Number(a.year || 0))[0] || null;
}

export function metricSourceValue(record) {
  if (!record || typeof record !== "object") return null;
  const value = Number(record.source_value);
  return Number.isFinite(value) ? value : null;
}

export function formatKrwReadable(value) {
  if (value === null || value === undefined || value === "") return "확인되지 않음";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "확인되지 않음";
  if (amount === 0) return "0원";
  const abs = Math.abs(amount);
  const sign = amount < 0 ? "-" : "";
  if (abs >= 100_000_000) {
    return `${sign}${(abs / 100_000_000).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}억원`;
  }
  if (abs >= 1_000_000) {
    return `${sign}${(abs / 1_000_000).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}백만원`;
  }
  return `${sign}${abs.toLocaleString("ko-KR")}원`;
}

export function formatCompanyDate(value) {
  if (!value) return "확인 중";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10);
  return new Intl.DateTimeFormat("ko-KR").format(date);
}

export function representativeProject(company) {
  const projects = Array.isArray(company?.project_portfolio) ? company.project_portfolio : [];
  return projects.find((item) => item.project_name && ["verified", "partially_verified"].includes(item.evidence_status)) || projects.find((item) => item.project_name) || null;
}

export function verifiedCompanyProjects(company) {
  const projects = Array.isArray(company?.project_portfolio) ? company.project_portfolio : [];
  return projects.filter((item) => item?.project_name && item?.source_ids?.length && ["verified", "partially_verified"].includes(item.evidence_status));
}

export function projectCandidates(company) {
  const candidates = Array.isArray(company?.project_candidates) ? company.project_candidates : [];
  return candidates.filter((item) => item?.candidate_title && item?.review_status !== "verified");
}

export function getCompanyProjectSummary(company) {
  const projects = Array.isArray(company?.project_portfolio) ? company.project_portfolio : [];
  const verified = verifiedCompanyProjects(company);
  const candidates = projectCandidates(company);
  const researchStatus = company?.project_research_status || {};
  const candidateCount = Number(researchStatus.candidate_project_count ?? candidates.length) || 0;
  const researchGapCount = Number(researchStatus.research_gap_count ?? 0) || 0;
  const sectors = [...new Set(verified.map((item) => item.sector || item.building_use).filter(Boolean))].slice(0, 2);
  const roles = [...new Set(verified.map((item) => item.company_role).filter(Boolean))].slice(0, 2);
  const years = verified
    .map((item) => item.completion_date || item.contract_date || item.construction_start_date || item.verified_at)
    .filter(Boolean)
    .map((value) => Number(String(value).slice(0, 4)))
    .filter((year) => Number.isFinite(year))
    .sort((a, b) => b - a);
  return {
    total: projects.length,
    verified: verified.length,
    candidates: candidateCount,
    candidateSamples: candidates.length,
    researchStatus: researchStatus.research_status || "",
    researchGapCount,
    researchWave: researchStatus.research_wave || "",
    sectors,
    roles,
    latestYear: years[0] || null,
  };
}

export function technologyCount(company) {
  const technology = company?.technology && typeof company.technology === "object" ? company.technology : {};
  return Object.values(technology).reduce((sum, value) => sum + (Array.isArray(value) ? value.length : 0), 0);
}

export function getCompanyHighlights(company) {
  const highlights = [];
  const production = productionFacilities(company).find((item) => item.facility_name || item.capacity_value);
  const summary = productionSummary(company);
  if (hasConfirmedProductionFacility(company)) highlights.push(getProductionModelLabel(company));
  if (production?.facility_name) highlights.push(production.facility_name);
  if (production?.reported_capacity && production?.capacity_unit) highlights.push(`${production.reported_capacity} ${production.capacity_unit}`);
  else if (production?.capacity_value && production?.capacity_unit) highlights.push(`${production.capacity_value} ${production.capacity_unit}`);
  else if (summary.reported_capacity_available === false && hasConfirmedProductionFacility(company)) highlights.push("공식 생산능력 미공개");
  const project = representativeProject(company);
  const projectSummary = getCompanyProjectSummary(company);
  if (projectSummary.verified > 0) highlights.push(`검증 프로젝트 ${projectSummary.verified}건`);
  else if (projectSummary.candidates > 0) highlights.push(`프로젝트 후보 ${projectSummary.candidates}건`);
  else if (project?.project_name) highlights.push(project.project_name);
  const latest = getLatestFinancial(company);
  const revenue = metricSourceValue(latest?.revenue);
  if (latest && revenue !== null) highlights.push(`최근 확인 매출 ${formatKrwReadable(revenue)}`);
  const techCount = technologyCount(company);
  if (techCount > 0) highlights.push(`기술·특허 ${techCount}건`);
  return highlights.slice(0, 3);
}

export function sourceHasUrl(source) {
  return Boolean(source?.source_url && !String(source.source_url).includes(".cache"));
}
