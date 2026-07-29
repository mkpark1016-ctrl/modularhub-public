import { fallbackProductionCapacityLabel, formatNumber } from "./components/company/companyDetailHelpers.js";

export function companyDataGapRows(company, reportInsight = null) {
  const rows = [];
  if (reportInsight?.attribution?.modular_segment_revenue_disclosed === false) {
    rows.push({
      key: "modular-revenue",
      domain: "financial",
      title: "모듈러 부문 매출 미공시",
      description: "회사 전체 재무와 모듈러 부문 재무를 분리해 표시할 수 없습니다.",
    });
  }
  if (reportInsight?.data_quality?.manual_page_check_required) {
    rows.push({
      key: "manual-page-check",
      domain: "financial",
      title: `감사보고서 페이지 수동 확인 필요 ${formatNumber(reportInsight.data_quality.pending_manual_page_check_count || 0, "건")}`,
      description: "수치 출처 위치는 보존했지만 일부 주석 페이지는 사람이 추가 확인해야 합니다.",
    });
  }
  for (const gap of Array.isArray(company?.research_gaps) ? company.research_gaps : []) {
    rows.push({
      key: gap.gap_id || gap.field || gap.title,
      domain: gap.domain || gap.area || null,
      title: gap.title || gap.field || "추가 확인 필요",
      description: gap.description || gap.note || "공개자료 추가 확인이 필요합니다.",
    });
  }
  for (const facility of Array.isArray(company?.production) ? company.production : []) {
    const missingCapacity = fallbackProductionCapacityLabel(facility) === "공식 생산능력 미공개";
    const missingProcess = !Array.isArray(facility.production_processes) || facility.production_processes.length === 0;
    if (missingCapacity || missingProcess) {
      rows.push({
        key: `facility-${facility.facility_id || facility.facility_name}`,
        domain: "production",
        title: `${facility.display_name || facility.facility_name || "생산시설"} 세부정보 보완 필요`,
        description: missingCapacity ? "공식 현재 생산능력이 공개자료에서 확인되지 않았습니다." : "주요 공정 정보가 구조화 데이터에 없습니다.",
      });
    }
  }
  return rows;
}

export function dataGapSummaryForDomain(gapRows, domain) {
  const rows = Array.isArray(gapRows) ? gapRows : [];
  const explicitRows = rows.filter((row) => row.domain === domain);
  if (explicitRows.length) return formatNumber(explicitRows.length, "건");
  const unknownRows = rows.filter((row) => !row.domain);
  return unknownRows.length ? "확인 필요" : "연결 공백 없음";
}
