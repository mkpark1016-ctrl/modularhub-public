from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one replacement target, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    insights = ROOT / "frontend/src/companyInsights.js"
    app = ROOT / "frontend/src/App.jsx"
    cards = ROOT / "frontend/src/components/company/CompanyComparisonMvp.jsx"
    main_js = ROOT / "frontend/src/main.jsx"

    replace_once(
        insights,
        '''export function getCompetitiveRoleLabel(company) {\n  return labelFromMap(COMPETITIVE_ROLE_LABELS, company?.competitive_role);\n}\n''',
        '''export function getStrategicCompetitiveRole(company) {\n  if (isModularSpecialistCompany(company)) return "direct_competitor";\n  return company?.competitive_role || "unknown";\n}\n\nexport function getCompetitiveRoleLabel(company) {\n  return labelFromMap(COMPETITIVE_ROLE_LABELS, getStrategicCompetitiveRole(company));\n}\n''',
    )

    replace_once(
        insights,
        '''  if (values.relationship !== "all" && company.competitive_role !== values.relationship) return false;\n''',
        '''  if (values.relationship !== "all" && getStrategicCompetitiveRole(company) !== values.relationship) return false;\n''',
    )

    replace_once(
        insights,
        '''  const roleDelta = ROLE_SORT_ORDER.indexOf(a.competitive_role) - ROLE_SORT_ORDER.indexOf(b.competitive_role);\n''',
        '''  const roleDelta = ROLE_SORT_ORDER.indexOf(getStrategicCompetitiveRole(a)) - ROLE_SORT_ORDER.indexOf(getStrategicCompetitiveRole(b));\n''',
    )

    replace_once(
        insights,
        '''export function getCompanySummary(companies) {\n  const list = Array.isArray(companies) ? companies : [];\n  return {\n    total: list.length,\n    directCompetitors: list.filter((company) => company.competitive_role === "direct_competitor").length,\n    coreVerified: list.filter((company) => getCompanyDataStatus(company) === "core_verified").length,\n    facilityConfirmed: list.filter((company) => hasConfirmedProductionFacility(company)).length,\n    roleCounts: companyRoleOptions(list),\n    relationshipCounts: optionCounts(list, "competitive_role", COMPETITIVE_ROLE_LABELS),\n    statusCounts: statusOptions(list),\n  };\n}\n''',
        '''export function getCompanySummary(companies) {\n  const list = Array.isArray(companies) ? companies : [];\n  const roleCounts = companyRoleOptions(list);\n  const strategicRelationshipRows = list.map((company) => ({\n    ...company,\n    competitive_role: getStrategicCompetitiveRole(company),\n  }));\n  return {\n    total: list.length,\n    generalContractors: list.filter((company) => getCanonicalCompanyRole(company) === "general_contractor").length,\n    modularSpecialists: list.filter(isModularSpecialistCompany).length,\n    directModularCompetitors: list.filter(isModularSpecialistCompany).length,\n    directCompetitors: list.filter((company) => getStrategicCompetitiveRole(company) === "direct_competitor").length,\n    coreVerified: list.filter((company) => getCompanyDataStatus(company) === "core_verified").length,\n    facilityConfirmed: list.filter((company) => hasConfirmedProductionFacility(company)).length,\n    roleCounts,\n    relationshipCounts: optionCounts(strategicRelationshipRows, "competitive_role", COMPETITIVE_ROLE_LABELS),\n    statusCounts: statusOptions(list),\n  };\n}\n''',
    )

    replace_once(
        app,
        '''          <div><strong>기업정보</strong><span>분석 대상 {companySummary.total}개사 · 직접 경쟁사 {companySummary.directCompetitors}개사 · 핵심 정보 검증 {companySummary.coreVerified}개사</span></div>\n          <b>{companySummary.coreVerified}개사 핵심 검증</b>\n''',
        '''          <div><strong>기업정보</strong><span>분석 대상 {companySummary.total}개사 · 건설사 {companySummary.generalContractors}개사 · 직접 경쟁 모듈러 업체 {companySummary.directModularCompetitors}개사</span></div>\n          <b>데이터 검증 {companySummary.coreVerified} / {companySummary.total}개사</b>\n''',
    )

    replace_once(
        app,
        '''          <CompanyCardGrid companies={filtered} selectedIds={selectedIds} onToggleCompare={toggleCompare} activitiesByCompany={activitiesByCompany} reportInsightsByCompany={reportInsightsByCompany} />\n''',
        '''          <CompanyCardGrid companies={filtered} selectedIds={selectedIds} onToggleCompare={toggleCompare} activitiesByCompany={activitiesByCompany} reportInsightsByCompany={reportInsightsByCompany} monitoringAt={activityState.data?.generatedAt || ""} />\n''',
    )

    replace_once(
        cards,
        '''export function CompanySummaryCard({ company, selected, selectionDisabled, onToggleCompare, activities = [], reportInsight = null }) {\n  const metric = getComparisonMetric(company);\n  const decision = buildCompanyDecisionModel(company, { reportInsight, activities });\n  const gapCount = getCompanyDataGapCount(company);\n  const latestVerifiedAt = formatDate(getLatestVerifiedAt(company));\n''',
        '''export function CompanySummaryCard({ company, selected, selectionDisabled, onToggleCompare, activities = [], reportInsight = null, monitoringAt = "" }) {\n  const metric = getComparisonMetric(company);\n  const decision = buildCompanyDecisionModel(company, { reportInsight, activities });\n  const gapCount = getCompanyDataGapCount(company);\n  const latestVerifiedAt = formatDate(getLatestVerifiedAt(company));\n  const latestMonitoringAt = monitoringAt ? formatDate(monitoringAt) : "확인 중";\n''',
    )

    replace_once(
        cards,
        '''      <p className="company-card-meta">최근 검증일 {latestVerifiedAt}</p>\n''',
        '''      <p className="company-card-meta">최근 모니터링 {latestMonitoringAt} · 최근 검증 {latestVerifiedAt}</p>\n''',
    )

    replace_once(
        cards,
        '''export function CompanyCardGrid({ companies, selectedIds, onToggleCompare, activitiesByCompany = new Map(), reportInsightsByCompany = new Map() }) {\n''',
        '''export function CompanyCardGrid({ companies, selectedIds, onToggleCompare, activitiesByCompany = new Map(), reportInsightsByCompany = new Map(), monitoringAt = "" }) {\n''',
    )

    replace_once(
        cards,
        '''          reportInsight={reportInsightsByCompany.get(company.company_id) || null}\n''',
        '''          reportInsight={reportInsightsByCompany.get(company.company_id) || null}\n          monitoringAt={monitoringAt}\n''',
    )

    replace_once(
        main_js,
        '''import "./styles.css";\n''',
        '''import "./styles.css";\nimport "./companyUiOverrides.css";\n''',
    )

    (ROOT / "frontend/src/companyUiOverrides.css").write_text(
        '''/* Phase 8C-1B: keep company discovery controls aligned on desktop without changing mobile behavior. */\n@media (min-width: 781px) {\n  .company-discovery-primary {\n    grid-template-columns: minmax(430px, 480px) minmax(320px, 1fr) minmax(180px, 210px);\n    gap: 16px;\n    align-items: end;\n  }\n\n  .company-discovery-primary .company-toolbar-label,\n  .company-discovery-primary .company-toolbar-search,\n  .company-discovery-primary .company-toolbar-sort {\n    min-width: 0;\n  }\n\n  .company-discovery-primary .company-type-segmented {\n    display: flex;\n    flex-wrap: nowrap;\n    align-items: stretch;\n    width: 100%;\n  }\n\n  .company-discovery-primary .company-type-segmented button,\n  .company-discovery-primary .search-field,\n  .company-discovery-primary .company-toolbar-sort select {\n    min-height: 46px;\n  }\n}\n''',
        encoding="utf-8",
    )

    (ROOT / "frontend/scripts/test-company-strategy-monitoring.mjs").write_text(
        '''import assert from "node:assert/strict";\nimport fs from "node:fs";\nimport { fileURLToPath } from "node:url";\nimport {\n  getCompanySummary,\n  getCompetitiveRoleLabel,\n  getStrategicCompetitiveRole,\n  isModularSpecialistCompany,\n} from "../src/companyInsights.js";\n\nconst companiesPath = fileURLToPath(new URL("../public/data/companies/companies.json", import.meta.url));\nconst payload = JSON.parse(fs.readFileSync(companiesPath, "utf8"));\nconst companies = Array.isArray(payload) ? payload : payload.companies;\nassert.equal(companies.length, 11, "public company universe must remain 11");\n\nconst summary = getCompanySummary(companies);\nassert.equal(summary.total, 11);\nassert.equal(summary.generalContractors, 4);\nassert.equal(summary.modularSpecialists, 7);\nassert.equal(summary.directModularCompetitors, 7);\nassert.equal(summary.directCompetitors, 7);\nassert.equal(summary.coreVerified, 10, "verification status must remain evidence-based");\nassert.equal(summary.roleCounts.find((row) => row.value === "general_contractor")?.count, 4);\nassert.equal(summary.roleCounts.find((row) => row.value === "modular_specialist")?.count, 7);\nassert.equal(summary.relationshipCounts.find((row) => row.value === "direct_competitor")?.count, 7);\n\nconst modularSpecialists = companies.filter(isModularSpecialistCompany);\nassert.equal(modularSpecialists.length, 7);\nassert.ok(modularSpecialists.every((company) => getStrategicCompetitiveRole(company) === "direct_competitor"));\n\nconst nrb = companies.find((company) => company.company_id === "nrb");\nassert.ok(nrb, "NRB must exist");\nassert.equal(nrb.competitive_role, "substitute_competitor", "raw source-backed classification must remain untouched");\nassert.equal(getStrategicCompetitiveRole(nrb), "direct_competitor");\nassert.equal(getCompetitiveRoleLabel(nrb), "직접 경쟁사");\n\nconst appSource = fs.readFileSync(fileURLToPath(new URL("../src/App.jsx", import.meta.url)), "utf8");\nassert.ok(appSource.includes("직접 경쟁 모듈러 업체 {companySummary.directModularCompetitors}개사"));\nassert.ok(appSource.includes('monitoringAt={activityState.data?.generatedAt || ""}'));\n\nconst cardSource = fs.readFileSync(fileURLToPath(new URL("../src/components/company/CompanyComparisonMvp.jsx", import.meta.url)), "utf8");\nassert.ok(cardSource.includes("최근 모니터링 {latestMonitoringAt} · 최근 검증 {latestVerifiedAt}"));\n\nconst cssSource = fs.readFileSync(fileURLToPath(new URL("../src/companyUiOverrides.css", import.meta.url)), "utf8");\nassert.ok(cssSource.includes("flex-wrap: nowrap"));\nassert.ok(cssSource.includes("min-height: 46px"));\n\nconsole.log("Company strategy and monitoring UI test passed.");\n''',
        encoding="utf-8",
    )

    print("Phase 8C-1B migration applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
