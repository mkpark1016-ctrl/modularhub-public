export const COMPANY_TYPE_LABELS = {
  general_contractor: "건설사",
  specialist_manufacturer: "모듈러 제작 전문 업체",
  modular_integrator: "모듈러 제작 전문 업체",
  modular_specialist: "모듈러 제작 전문 업체",
  producer_group: "모듈러 제작 전문 업체",
  design_firm: "설계사",
  engineering_firm: "엔지니어링사",
  material_supplier: "자재 공급사",
  solution_provider: "솔루션 기업",
};

export const MODULAR_SPECIALIST_ROLE = "modular_specialist";
export const LEGACY_PRODUCER_GROUP_ROLE = "producer_group";
export const CANONICAL_COMPANY_ROLE_VALUES = ["general_contractor", MODULAR_SPECIALIST_ROLE];
export const MODULAR_SPECIALIST_COMPANY_TYPES = new Set(["specialist_manufacturer", "modular_integrator", MODULAR_SPECIALIST_ROLE, LEGACY_PRODUCER_GROUP_ROLE]);
export const LEGACY_MODULAR_SPECIALIST_SEARCH_LABELS = ["전문 제작사", "모듈러 통합사", "전문 제작·통합사", "전문 제작·통합업체"];

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
  core_verified: "핵심 정보 검증",
  partially_verified: "부분 검증",
  research_in_progress: "조사 중",
  watchlist: "관찰 대상",
  insufficient_public_data: "공개자료 부족",
};

export const DOMAIN_STATUS_LABELS = {
  official_verified: "공식 검증",
  cross_verified: "교차 검증",
  company_claimed: "회사 공식자료 확인",
  third_party_reported: "외부자료 확인",
  internally_confirmed: "내부 기준 확인",
  partially_verified: "부분 검증",
  not_verified: "미확인",
  unavailable: "공개자료 없음",
};

export const EVENT_TYPE_LABELS = {
  project: "프로젝트",
  partnership: "협력",
  mou: "MOU",
  acquisition: "인수",
  facility_investment: "시설 투자",
  r_and_d: "R&D",
  exhibition: "전시",
  product_launch: "제품 출시",
  organization_change: "조직 변화",
  policy_signal: "정책 신호",
  business_strategy: "사업 전략",
};

export const EVENT_STATUS_LABELS = {
  completed: "완료",
  in_progress: "진행 중",
  contract_signed: "계약 체결",
  award_confirmed: "수주 확인",
  preferred_bidder: "우선협상대상",
  bid_participation: "입찰 참여",
  planned: "계획",
  mou_signed: "MOU 체결",
  partnership_discussion: "협력 논의",
  r_and_d: "연구개발",
  exhibition: "전시",
  cancelled: "취소",
  not_signed: "미체결",
  unconfirmed: "미확인",
};

export const CONFIDENCE_LABELS = {
  high: "높은 신뢰도",
  medium: "보통 신뢰도",
  low: "낮은 신뢰도",
  review: "검토 필요",
  unknown: "확인 중",
  verified_manual: "수동 검증",
};

export const VERIFICATION_LEVEL_LABELS = {
  verified_primary: "공식자료 검증",
  verified_cross_source: "교차 검증",
  official_verified: "공식자료 검증",
  cross_verified: "교차 검증",
  partially_verified: "부분 검증",
  secondary_only: "2차 자료 기준",
  third_party_reported: "2차 자료 기준",
  conflicting: "자료 상충",
  stale: "최신성 확인 필요",
  unverified: "미확인",
  research_required: "추가 확인 필요",
  not_publicly_available: "공식자료 없음",
  not_applicable: "해당 없음",
  core_verified: "교차 검증",
  verified: "교차 검증",
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
  modular_installer: "모듈러 설치",
  structural_engineer: "구조 엔지니어링",
  material_supplier: "자재 공급",
  role_unknown: "수행 역할 미확인",
  unknown: "역할 확인 중",
};

export const SOURCE_GROUP_LABELS = {
  dart: "DART 감사·사업보고서",
  company_official: "기업 공식자료",
  public_official: "발주·공공기관 공식자료",
  media_and_research: "언론 및 전문자료",
  other: "기타 공개자료",
};

export const DISPLAY_VALUE_LABELS = {
  owned: "자체 소유",
  subsidiary_owned: "자회사 소유",
  affiliate_owned: "관계사 소유",
  leased: "임차",
  partner_owned: "협력사 소유",
  contract_manufacturing: "위탁 생산",
  active: "운영 중",
  partially_active: "부분 운영",
  under_expansion: "증설 중",
  under_construction: "건설 중",
  planned: "계획",
  suspended: "중단",
  closed: "운영 종료",
  steel_cutting: "철골 절단",
  steel_frame_fabrication: "철골 프레임 제작",
  welding: "용접",
  blasting: "표면 처리",
  painting: "도장",
  fireproofing: "내화 처리",
  floor_assembly: "바닥 조립",
  wall_assembly: "벽체 조립",
  ceiling_assembly: "천장 조립",
  mep_prefabrication: "MEP 사전 제작",
  interior_fitout: "내부 마감",
  window_door_installation: "창호 설치",
  bathroom_pod: "욕실 모듈",
  final_assembly: "최종 조립",
  factory_inspection: "공장 검사",
  packaging: "포장",
  logistics_loading: "출하 적재",
  proprietary_system: "자체 시스템",
  claimed: "회사 주장",
  steel_modular_units: "스틸 모듈러 유닛",
  steel_volumetric: "스틸 볼류메트릭",
  public_housing: "공공주택",
  private_housing: "민간주택",
  overseas_research_facility: "해외 연구시설",
  temporary_office: "임시 업무시설",
  patent: "특허",
  patent_application: "특허 출원",
  construction_new_technology: "건설신기술",
  certification: "인증",
  innovative_product: "혁신제품",
  design_award: "디자인 수상",
  research_project: "연구과제",
  registered: "등록",
  filed: "출원",
  granted: "등록",
  expired: "만료",
  unmodified: "적정",
  qualified: "한정",
  adverse: "부적정",
  disclaimer: "의견거절",
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

export function getCanonicalCompanyRole(company) {
  const type = typeof company === "string" ? company : company?.company_type;
  if (type === "general_contractor") return "general_contractor";
  if (MODULAR_SPECIALIST_COMPANY_TYPES.has(type)) return MODULAR_SPECIALIST_ROLE;
  return type || "unknown";
}

export function getCanonicalCompanyRoleLabel(companyOrRole) {
  const role = getCanonicalCompanyRole(companyOrRole);
  return labelFromMap(COMPANY_TYPE_LABELS, role);
}

export function isModularSpecialistCompany(company) {
  return getCanonicalCompanyRole(company) === MODULAR_SPECIALIST_ROLE;
}

export function getCompanyTypeLabel(company) {
  return getCanonicalCompanyRoleLabel(company);
}

export function getStrategicCompetitiveRole(company) {
  if (isModularSpecialistCompany(company)) return "direct_competitor";
  return company?.competitive_role || "unknown";
}

export function getCompetitiveRoleLabel(company) {
  return labelFromMap(COMPETITIVE_ROLE_LABELS, getStrategicCompetitiveRole(company));
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

export function getVerificationLevelLabel(value) {
  return labelFromMap(VERIFICATION_LEVEL_LABELS, value || "research_required", "추가 확인 필요");
}

export function getCompanyVerificationLevel(company) {
  const status = getCompanyIntelligence(company).overall_data_status || company?.review_status;
  if (status === "core_verified") return "verified_cross_source";
  if (status === "verified" && company?.data_confidence === "high") return "verified_cross_source";
  if (status === "verified") return "partially_verified";
  return status || "research_required";
}

export function getCompanyResearchGapCount(company) {
  return Array.isArray(company?.research_gaps) ? company.research_gaps.length : 0;
}

export function getCompanyDataGapCount(company, reportInsight = null) {
  let count = getCompanyResearchGapCount(company);
  const summary = productionSummary(company);
  if (summary.reported_capacity_available === false || summary.verification_status === "research_exhausted") count += 1;
  if (reportInsight?.data_quality?.manual_page_check_required) count += 1;
  if (reportInsight?.attribution?.modular_segment_revenue_disclosed === false) count += 1;
  if (!company?.website_url) count += 1;
  return count;
}

export function getCompanyCompactSummary(company) {
  const summary = getKoreanCompanySummary(company);
  if (summary && !summary.includes("추가 조사 중")) return summary;
  const highlights = getCompanyHighlights(company);
  return highlights.length ? highlights.join(" · ") : "공개자료 기준 핵심 정보 정리 중";
}

export function getProjectRoleLabel(project) {
  return labelFromMap(PROJECT_ROLE_LABELS, project?.company_role || "unknown");
}

export function getProjectStatusLabel(project) {
  return labelFromMap(PROJECT_STATUS_LABELS, project?.project_status || "unknown");
}

export function getEventTypeLabel(event) {
  return labelFromMap(EVENT_TYPE_LABELS, event?.event_type, "사업 사건");
}

export function getEventStatusLabel(event) {
  return labelFromMap(EVENT_STATUS_LABELS, event?.event_status, "미확인");
}

export function getDomainStatusLabel(value) {
  return labelFromMap(DOMAIN_STATUS_LABELS, value, "미확인");
}

export function getDisplayValue(value, fallback = "확인 중") {
  if (!value) return fallback;
  if (DISPLAY_VALUE_LABELS[value]) return DISPLAY_VALUE_LABELS[value];
  if (String(value).includes("_")) return fallback;
  return String(value);
}

export function hasKoreanText(value) {
  return /[가-힣]/.test(String(value || ""));
}

export function getCompanyIntelligence(company) {
  return company?.intelligence_v2 && typeof company.intelligence_v2 === "object" ? company.intelligence_v2 : {};
}

export function getCompanyDomainStatuses(company) {
  return getCompanyIntelligence(company).domain_statuses || {};
}

export function getCompanyEvents(company, eventTypes = null) {
  const events = Array.isArray(getCompanyIntelligence(company).events) ? getCompanyIntelligence(company).events : [];
  if (!eventTypes) return events;
  const allowed = new Set(Array.isArray(eventTypes) ? eventTypes : [eventTypes]);
  return events.filter((event) => allowed.has(event.event_type));
}

export function getCompanySourceGroups(company) {
  return Array.isArray(getCompanyIntelligence(company).source_groups) ? getCompanyIntelligence(company).source_groups : [];
}

export function getKoreanCompanySummary(company) {
  const summary = getCompanyIntelligence(company).summary_ko;
  if (hasKoreanText(summary)) return summary;
  return "현재 공개자료를 영역별로 추가 조사 중입니다.";
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
  const materialized = getCompanyIntelligence(company).overall_data_status;
  if (DATA_STATUS_LABELS[materialized]) return materialized;
  const reviewStatus = company?.review_status;
  if (reviewStatus === "verified") return "partially_verified";
  if (isDartIdentityConfirmed(company) || financialYears(company).length > 0 || (company?.sources || []).length > 0) return "partially_verified";
  return "research_in_progress";
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
  const v2Events = getCompanyEvents(company);
  return normalizeCompanyText([
    company?.company_name,
    company?.company_name_en,
    ...(Array.isArray(company?.aliases) ? company.aliases : []),
    getCompanyTypeLabel(company),
    ...(isModularSpecialistCompany(company) ? LEGACY_MODULAR_SPECIALIST_SEARCH_LABELS : []),
    getCompetitiveRoleLabel(company),
    getTierLabel(company),
    ...(Array.isArray(company?.modular_methods) ? company.modular_methods : []),
    ...(Array.isArray(company?.target_markets) ? company.target_markets : []),
    getKoreanCompanySummary(company),
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
      item.canonical_project_name,
      ...(Array.isArray(item.aliases) ? item.aliases : []),
      item.matched_alias,
      item.matched_context,
      item.possible_client,
      item.possible_location,
      item.possible_role,
      item.possible_company_role,
      item.possible_method,
      item.verification_status,
      item.source_dataset,
      item.review_status,
    ]),
    ...technologyValues.map((item) => {
      if (item && typeof item === "object") return [item.name, item.summary, item.technology_area, item.status].join(" ");
      return item;
    }),
    ...signals.flatMap((item) => [item.title, item.summary, item.signal_type]),
    ...v2Events.flatMap((item) => [item.title, item.client, item.location, item.market_segment, item.method, getEventTypeLabel(item), getEventStatusLabel(item), getProjectRoleLabel({ company_role: item.project_role })]),
  ].join(" "));
}

export function matchesCompanySearch(company, query) {
  const terms = normalizeCompanyText(query).split(" ").filter(Boolean);
  if (!terms.length) return true;
  const text = companySearchText(company);
  return terms.every((term) => text.includes(term));
}

export function companyMatchesFilters(company, values) {
  if ([MODULAR_SPECIALIST_ROLE, LEGACY_PRODUCER_GROUP_ROLE].includes(values.role) && !isModularSpecialistCompany(company)) return false;
  if (values.role !== "all" && ![MODULAR_SPECIALIST_ROLE, LEGACY_PRODUCER_GROUP_ROLE].includes(values.role) && getCanonicalCompanyRole(company) !== values.role) return false;
  if (values.relationship !== "all" && getStrategicCompetitiveRole(company) !== values.relationship) return false;
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
  const roleDelta = ROLE_SORT_ORDER.indexOf(getStrategicCompetitiveRole(a)) - ROLE_SORT_ORDER.indexOf(getStrategicCompetitiveRole(b));
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

export function companyRoleOptions(companies) {
  const list = Array.isArray(companies) ? companies : [];
  return CANONICAL_COMPANY_ROLE_VALUES
    .map((value) => ({
      value,
      label: COMPANY_TYPE_LABELS[value],
      count: list.filter((company) => getCanonicalCompanyRole(company) === value).length,
    }))
    .filter((option) => option.count > 0);
}

export function statusOptions(companies) {
  const counts = new Map();
  for (const company of companies) {
    const status = getCompanyDataStatus(company);
    counts.set(status, (counts.get(status) || 0) + 1);
  }
  return ["core_verified", "partially_verified", "research_in_progress", "watchlist", "insufficient_public_data"]
    .filter((value) => counts.has(value))
    .map((value) => ({ value, label: DATA_STATUS_LABELS[value], count: counts.get(value) }));
}

export function getCompanySummary(companies) {
  const list = Array.isArray(companies) ? companies : [];
  const roleCounts = companyRoleOptions(list);
  const strategicRelationshipRows = list.map((company) => ({
    ...company,
    competitive_role: getStrategicCompetitiveRole(company),
  }));
  return {
    total: list.length,
    generalContractors: list.filter((company) => getCanonicalCompanyRole(company) === "general_contractor").length,
    modularSpecialists: list.filter(isModularSpecialistCompany).length,
    directModularCompetitors: list.filter(isModularSpecialistCompany).length,
    directCompetitors: list.filter((company) => getStrategicCompetitiveRole(company) === "direct_competitor").length,
    coreVerified: list.filter((company) => getCompanyDataStatus(company) === "core_verified").length,
    facilityConfirmed: list.filter((company) => hasConfirmedProductionFacility(company)).length,
    roleCounts,
    relationshipCounts: optionCounts(strategicRelationshipRows, "competitive_role", COMPETITIVE_ROLE_LABELS),
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
  if (summary.own_facility_status === "confirmed_own_facility" || model === "own_manufacturing") return "자체 생산 확인";
  if (summary.own_facility_status === "confirmed_leased_facility" || model === "leased_facility") return "임차 생산 확인";
  if (summary.own_facility_status === "confirmed_partner_manufacturing" || model === "partner_manufacturing") return "협력 제작 확인";
  if (model === "outsourced_manufacturing") return "위탁 생산 확인";
  if (summary.verification_status === "not_applicable") return "생산시설 비대상";
  if (summary.verification_status === "research_exhausted") return "공개자료상 생산시설 미확인";
  return "생산정보 조사 중";
}

export function getProductionCapacityLabel(facility) {
  if (!facility || typeof facility !== "object") return "공개자료에서 공식 생산능력 수치가 확인되지 않았습니다.";
  const value = facility.reported_capacity ?? facility.capacity_value;
  if (value === null || value === undefined || value === "") {
    if (facility.capacity_status === "not_applicable") return "생산능력 비대상";
    return "공개자료에서 공식 생산능력 수치가 확인되지 않았습니다.";
  }
  const unit = facility.capacity_unit || "";
  const period = facility.capacity_period ? `/${facility.capacity_period}` : "";
  const scope = facility.capacity_scope ? ` · ${facility.capacity_scope}` : "";
  return `공식 생산능력 ${Number(value).toLocaleString("ko-KR")} ${unit}${period}${scope}`.trim();
}

export function formatProductionArea(value, unit = "m2") {
  if (value === null || value === undefined || value === "") return null;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return null;
  return `${numeric.toLocaleString("ko-KR")} ${unit || "m2"}`;
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
  return candidates.filter((item) => (item?.candidate_title || item?.canonical_project_name) && item?.review_status !== "verified" && item?.verification_status !== "verified");
}

export function getCompanyProjectSummary(company) {
  const materialized = getCompanyIntelligence(company);
  if (materialized.event_counts) {
    const eventYears = getCompanyEvents(company, "project")
      .flatMap((event) => [event.completed_at, event.started_at, event.contracted_at, event.announced_at, event.updated_at])
      .filter(Boolean)
      .map((value) => Number(String(value).slice(0, 4)))
      .filter((year) => Number.isFinite(year))
      .sort((a, b) => b - a);
    return {
      total: Number(materialized.event_counts.verified_projects || 0) + Number(materialized.event_counts.project_candidates || 0),
      verified: Number(materialized.event_counts.verified_projects || 0),
      candidates: Number(materialized.event_counts.project_candidates || 0),
      partnerships: Number(materialized.event_counts.partnerships_mou || 0),
      researchAndExhibition: Number(materialized.event_counts.r_and_d_exhibition || 0),
      otherEvents: Number(materialized.event_counts.other_events || 0),
      rawArticleCount: Number(materialized.article_evidence_count || 0),
      rejectedCandidateCount: Number(company?.project_research_status?.rejected_candidate_count || 0),
      officialSourceCount: Number(company?.project_research_status?.official_source_count || 0),
      researchStatus: company?.project_research_status?.research_status || "",
      researchGapCount: Number(company?.project_research_status?.research_gap_count || 0),
      researchWave: company?.project_research_status?.research_wave || "",
      sectors: [],
      roles: [],
      latestYear: eventYears[0] || null,
    };
  }
  const projects = Array.isArray(company?.project_portfolio) ? company.project_portfolio : [];
  const verified = verifiedCompanyProjects(company);
  const candidates = projectCandidates(company);
  const researchStatus = company?.project_research_status || {};
  const candidateCount = Number(researchStatus.candidate_project_count ?? candidates.length) || 0;
  const rawArticleCount = Number(researchStatus.raw_candidate_article_count ?? 0) || 0;
  const rejectedCandidateCount = Number(researchStatus.rejected_candidate_count ?? 0) || 0;
  const officialSourceCount = Number(researchStatus.official_source_count ?? 0) || 0;
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
    partnerships: 0,
    researchAndExhibition: 0,
    otherEvents: 0,
    candidateSamples: candidates.length,
    rawArticleCount,
    rejectedCandidateCount,
    officialSourceCount,
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
  const projectSummary = getCompanyProjectSummary(company);
  if (projectSummary.verified > 0) highlights.push(`검증 프로젝트 ${projectSummary.verified}건`);
  else if (projectSummary.candidates > 0) highlights.push(`프로젝트 후보 ${projectSummary.candidates}건`);
  else if (projectSummary.partnerships > 0) highlights.push(`협력·MOU ${projectSummary.partnerships}건`);
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
