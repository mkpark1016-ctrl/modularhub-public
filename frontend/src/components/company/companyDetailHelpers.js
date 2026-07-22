import {
  getCompanyDataStatus,
  getCompanyDataStatusLabel,
  getCompanyDomainStatuses,
  getCompanyEvents,
  getCompanyProjectSummary,
  getCompanySourceGroups,
  getCompanyTypeLabel,
  getCompanyVerificationLevel,
  getCompetitiveRoleLabel,
  getConfidenceLabel,
  getDomainStatusLabel,
  getKoreanCompanySummary,
  getLatestFinancial,
  getLatestVerifiedAt,
  getProductionCapacityLabel,
  getProductionModelLabel,
  getVerificationLevelLabel,
  getTierLabel,
  metricSourceValue,
  productionFacilities,
  productionSummary,
  technologyCount,
} from "../../companyInsights.js";

export const COMPANY_DETAIL_TABS = [
  { value: "overview", label: "개요" },
  { value: "financial", label: "재무" },
  { value: "production", label: "생산시설" },
  { value: "projects", label: "프로젝트" },
  { value: "technology", label: "기술·특허" },
  { value: "evidence", label: "근거·출처" },
];

export const DEFAULT_COMPANY_TAB = "overview";
export const VALID_COMPANY_TABS = new Set(COMPANY_DETAIL_TABS.map((tab) => tab.value));

export function normalizeCompanyTab(value) {
  return VALID_COMPANY_TABS.has(value) ? value : DEFAULT_COMPANY_TAB;
}

const VALUE_LABELS = {
  specialist_manufacturer: "모듈러 제작 전문 업체",
  modular_integrator: "모듈러 제작 전문 업체",
  modular_specialist: "모듈러 제작 전문 업체",
  producer_group: "모듈러 제작 전문 업체",
  design_firm: "설계사",
  engineering_firm: "엔지니어링사",
  material_supplier: "자재 공급사",
  solution_provider: "솔루션 기업",
  direct_competitor: "직접 경쟁사",
  substitute_competitor: "대체 경쟁사",
  strategic_benchmark: "전략 벤치마크",
  design_influencer: "설계 영향사",
  internal_baseline: "내부 기준",
  watchlist: "관찰 대상",
  tier_1: "최우선 분석",
  tier_1b: "우선 분석",
  tier_2: "일반 분석",
  tier_3: "장기 관찰",
  core_verified: "핵심 정보 검증",
  partially_verified: "부분 검증",
  research_in_progress: "조사 중",
  insufficient_public_data: "공개자료 부족",
  official_verified: "공식 검증",
  cross_verified: "교차 검증",
  company_claimed: "회사 자료 확인",
  third_party_reported: "제3자 자료 확인",
  internally_confirmed: "내부 검증",
  not_verified: "미확인",
  unavailable: "공개자료 없음",
  verified: "검증 완료",
  high: "높은 신뢰도",
  medium: "보통 신뢰도",
  low: "낮은 신뢰도",
  unknown: "확인되지 않음",
  general_korean_gaap: "일반기업회계기준",
  "K-IFRS": "한국채택국제회계기준",
  separate: "별도",
  consolidated: "연결",
  completed: "완료",
  in_progress: "진행 중",
  contract_signed: "계약 체결",
  award_confirmed: "수주 확인",
  under_construction: "공사 중",
  contracted: "계약",
  awarded: "수주",
  preferred_bidder: "우선협상·우선대상",
  bid_participation: "입찰 참여",
  planned: "계획",
  unconfirmed: "미확인",
  cancelled: "취소",
  mou_signed: "MOU 체결",
  partnership_discussion: "협력 논의",
  r_and_d: "R&D",
  exhibition: "전시",
  pre_con: "Pre-Con",
  not_signed: "미체결",
  project: "프로젝트",
  partnership: "협력",
  mou: "MOU",
  acquisition: "인수",
  facility_investment: "시설 투자",
  product_launch: "제품 출시",
  organization_change: "조직 변화",
  policy_signal: "정책 신호",
  business_strategy: "사업 전략",
  modular_manufacturer: "모듈러 제작",
  modular_installer: "모듈러 설치",
  general_contractor_role: "종합 시공",
  general_contractor_project: "종합 시공",
  general_contractor_event: "종합 시공",
  general_contractor_company: "건설사",
  general_contractor: "건설사",
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
  structural_engineer: "구조 엔지니어링",
  role_unknown: "수행 역할 미확인",
  military_modular: "군 모듈러",
  large_scale_modular: "대형 모듈러",
  school: "학교",
  military: "군 시설",
  office: "업무시설",
  public_housing: "공공주택",
  private_housing: "민간주택",
  dormitory: "기숙사",
  industrial: "산업시설",
  overseas: "해외",
  senior_housing: "시니어 주거",
  hotel: "호텔",
  hospital: "의료시설",
  temporary_facility: "임시시설",
  temporary_building: "임시건축물",
  industrial_support: "산업 지원시설",
  data_center: "데이터센터",
  other: "기타",
  steel_volumetric: "스틸 볼류메트릭",
  steel_modular: "스틸 모듈러",
  steel_frame_panelized: "스틸 패널",
  steel_panelized: "스틸 패널",
  pc_volumetric: "PC 볼류메트릭",
  pc_ramen: "PC 라멘",
  wood_volumetric: "목조 볼류메트릭",
  wood_panelized: "목조 패널",
  precast_concrete_modular: "PC 모듈러",
  precast_concrete: "PC",
  timber_modular: "목조 모듈러",
  container: "컨테이너",
  hybrid: "하이브리드",
  owned: "자체 소유",
  subsidiary_owned: "자회사 소유",
  affiliate_owned: "관계사 소유",
  leased: "임차",
  partner_owned: "협력사 소유",
  contract_manufacturing: "위탁 생산",
  active: "운영 중",
  partially_active: "부분 운영",
  under_expansion: "증설 중",
  suspended: "중단",
  closed: "운영 종료",
  modular_factory: "모듈러 공장",
  steel_fabrication_factory: "철골 가공 공장",
  pc_factory: "PC 공장",
  timber_modular_factory: "목조 모듈러 공장",
  interior_assembly_factory: "내장 조립 시설",
  general_material_factory: "일반 자재 공장",
  research_facility: "연구 시설",
  official_confirmed: "공식 확인",
  company_claimed_capacity: "회사 주장",
  third_party_reported_capacity: "제3자 자료",
  derived: "계산값",
  unavailable_capacity: "공식 생산능력 미공개",
  not_applicable: "비대상",
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
  dart: "DART 감사·사업보고서",
  company_official: "기업 공식자료",
  public_official: "공공기관 자료",
  public_procurement: "공공 조달자료",
  factory_database: "공장정보 DB",
  company_information: "기업정보 플랫폼",
  media_and_research: "언론 및 전문자료",
  internal_verified: "내부 검증 기준",
  verified_primary: "공식자료 검증",
  verified_cross_source: "교차 검증",
  secondary_only: "2차 자료 기준",
  conflicting: "자료 상충",
  stale: "최신성 확인 필요",
  research_required: "추가 확인 필요",
  not_publicly_available: "공식자료 없음",
};

export function labelValue(value, fallback = "확인되지 않음") {
  if (value === null || value === undefined || value === "") return fallback;
  const text = String(value);
  if (text.includes(",")) {
    return text.split(",").map((item) => labelValue(item.trim(), item.trim())).join(", ");
  }
  return VALUE_LABELS[text] || (text.includes("_") ? fallback : text);
}

export function profileValue(value) {
  if (Array.isArray(value)) return value.length ? value : null;
  return value === null || value === undefined || value === "" ? null : value;
}

export function formatDate(value) {
  if (!value) return "확인되지 않음";
  const text = String(value);
  if (/^\d{4}(-\d{2})?(-\d{2})?$/.test(text)) return text;
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return text.slice(0, 10);
  return new Intl.DateTimeFormat("ko-KR").format(date);
}

export function formatNumber(value, suffix = "") {
  if (value === null || value === undefined || value === "") return "확인되지 않음";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return `${number.toLocaleString("ko-KR")}${suffix}`;
}

export function formatKrw(value) {
  if (value === null || value === undefined || value === "") return "확인되지 않음";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "확인되지 않음";
  if (amount === 0) return "0원";
  const abs = Math.abs(amount);
  const sign = amount < 0 ? "-" : "";
  if (abs >= 100_000_000) return `${sign}${(abs / 100_000_000).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}억원`;
  if (abs >= 1_000_000) return `${sign}${(abs / 1_000_000).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}백만원`;
  return `${sign}${abs.toLocaleString("ko-KR")}원`;
}

export function formatPercent(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "계산 불가";
  return `${Number(value).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}%`;
}

export function metricValue(record) {
  return metricSourceValue(record);
}

export function metricMargin(numerator, denominator) {
  const top = metricValue(numerator);
  const bottom = metricValue(denominator);
  if (top === null || bottom === null || bottom === 0) return null;
  return (top / bottom) * 100;
}

export function sortedFinancials(company) {
  return [...(Array.isArray(company?.financials) ? company.financials : [])]
    .sort((a, b) => Number(b.year || 0) - Number(a.year || 0))
    .slice(0, 3);
}

export function latestAudit(company) {
  return [...(Array.isArray(company?.audit_information) ? company.audit_information : [])]
    .sort((a, b) => Number(b.fiscal_year || 0) - Number(a.fiscal_year || 0))[0] || null;
}

export function technologyItems(company) {
  const technology = company?.technology && typeof company.technology === "object" ? company.technology : {};
  return Object.entries(technology).flatMap(([group, value]) => (
    Array.isArray(value)
      ? value.filter((item) => item && typeof item === "object").map((item) => ({ ...item, group }))
      : []
  ));
}

export function sourceGroups(company) {
  return getCompanySourceGroups(company);
}

export function detailModel(company) {
  const domainStatuses = getCompanyDomainStatuses(company);
  const events = getCompanyEvents(company);
  const financials = sortedFinancials(company);
  const latest = getLatestFinancial(company);
  const revenue = metricValue(latest?.revenue);
  const production = productionFacilities(company);
  const projectSummary = getCompanyProjectSummary(company);
  return {
    domainStatuses,
    events,
    financials,
    latestAudit: latestAudit(company),
    production,
    productionSummary: productionSummary(company),
    projectSummary,
    technologyItems: technologyItems(company),
    sourceGroups: sourceGroups(company),
    header: {
      typeLabel: getCompanyTypeLabel(company),
      relationshipLabel: getCompetitiveRoleLabel(company),
      tierLabel: getTierLabel(company),
      dataStatus: getCompanyDataStatus(company),
      dataStatusLabel: getCompanyDataStatusLabel(company),
      verificationLevel: getCompanyVerificationLevel(company),
      verificationLevelLabel: getVerificationLevelLabel(getCompanyVerificationLevel(company)),
      confidenceLabel: getConfidenceLabel(company),
      latestVerifiedAt: getLatestVerifiedAt(company),
      summary: getKoreanCompanySummary(company),
    },
    kpis: {
      verifiedProjects: projectSummary.verified,
      productionFacilities: production.length,
      technologyCount: technologyCount(company),
      latestRevenue: revenue,
      latestRevenueYear: latest?.year || null,
    },
  };
}

export function verifiedProjectEvents(events) {
  return events.filter((event) => event.event_type === "project" && event.project_credit);
}

export function pipelineEvents(events) {
  return events.filter((event) => (
    event.event_type === "project" && !event.project_credit
  ) || ["partnership", "mou", "r_and_d", "exhibition"].includes(event.event_type));
}

export function recentSignalEvents(events) {
  return events.filter((event) => !["project", "partnership", "mou", "r_and_d", "exhibition"].includes(event.event_type));
}

export function eventDate(event) {
  return event.completed_at || event.contracted_at || event.started_at || event.announced_at || event.updated_at || "";
}

export function eventStatusLabel(event) {
  return labelValue(event.event_status, "상태 미확인");
}

export function eventTypeLabel(event) {
  return labelValue(event.event_type, "사건");
}

export function eventRoleLabel(event) {
  const role = event.project_role || event.company_role;
  if (role === "general_contractor") return "종합 시공";
  return labelValue(role, "수행 역할 미확인");
}

export function productionCapacityLabel(facility) {
  const value = facility?.reported_capacity ?? facility?.capacity_value;
  if (value === null || value === undefined || value === "") {
    if (facility?.capacity_status === "not_applicable") return "생산능력 비대상";
    return "공식 생산능력 미공개";
  }
  const unit = facility.capacity_unit || "";
  const period = facility.capacity_period ? `/${labelValue(facility.capacity_period, facility.capacity_period)}` : "";
  const scope = facility.capacity_scope ? ` · ${labelValue(facility.capacity_scope, facility.capacity_scope)}` : "";
  const basis = facility.capacity_status && facility.capacity_status !== "official_confirmed" ? ` · ${labelValue(facility.capacity_status, facility.capacity_status)}` : "";
  return `${Number(value).toLocaleString("ko-KR")} ${unit}${period}${scope}${basis}`.trim();
}

export function fallbackProductionCapacityLabel(facility) {
  const label = productionCapacityLabel(facility);
  if (label === "공식 생산능력 미공개") return label;
  return label || getProductionCapacityLabel(facility);
}

export function productionModelLabel(company) {
  return labelValue(productionSummary(company).manufacturing_model, getProductionModelLabel(company));
}

export function domainStatusRows(company) {
  const statuses = getCompanyDomainStatuses(company);
  return [
    ["법인 식별", statuses.identity_status],
    ["재무", statuses.financial_status],
    ["생산", statuses.production_status],
    ["프로젝트", statuses.project_status],
    ["기술", statuses.technology_status],
    ["최근 신호", statuses.recent_signal_status],
  ].map(([label, value]) => ({ label, value: getDomainStatusLabel(value) === value ? labelValue(value) : getDomainStatusLabel(value) }));
}
