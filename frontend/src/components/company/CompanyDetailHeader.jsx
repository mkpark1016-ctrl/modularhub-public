import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";
import { detailModel, formatDate, formatKrw, formatPercent, metricMargin } from "./companyDetailHelpers";
import { metricDisplayText } from "../../companyReportInsights";

export default function CompanyDetailHeader({ company, activeTab = "overview", reportInsight = null }) {
  const model = detailModel(company);
  const compact = activeTab !== "overview";
  const latestRevenue = reportInsight?.latest_metrics?.revenue;
  const latestOperatingMargin = reportInsight?.derived_metrics?.[String(reportInsight.latest_year)]?.operating_margin_pct;
  const fallbackOperatingMargin = metricMargin(model.financials[0]?.operating_profit, model.financials[0]?.revenue);
  return (
    <header className={compact ? "company-detail-header compact-company-detail-header" : "company-detail-header"}>
      <Link className="back" to="/companies"><ArrowLeft size={17} />목록으로</Link>
      <div className="company-detail-title-row">
        <div>
          <div className="badge-row">
            <span>{model.header.typeLabel}</span>
            <span>{model.header.relationshipLabel}</span>
            <span className={`company-status ${model.header.dataStatus}`}>{model.header.dataStatusLabel}</span>
          </div>
          <h1>{company.company_name}</h1>
          {company.company_name_en && <p className="company-name-en">{company.company_name_en}</p>}
        </div>
        <p className="finance-note">
          검증 수준 {model.header.verificationLevelLabel} · 최신 검증일 {formatDate(model.header.latestVerifiedAt)} · 데이터 신뢰도 {model.header.confidenceLabel}
        </p>
      </div>
      {!compact && <p className="company-position-summary">{model.header.summary}</p>}
      <dl className="company-kpi-grid" aria-label="기업 핵심 지표">
        <div>
          <dt>최근 매출</dt>
          <dd>{latestRevenue ? metricDisplayText(latestRevenue) : (model.kpis.latestRevenueYear ? `${model.kpis.latestRevenueYear}년 ${formatKrw(model.kpis.latestRevenue)}` : "확인되지 않음")}</dd>
        </div>
        <div>
          <dt>영업이익률</dt>
          <dd>{latestOperatingMargin ? metricDisplayText(latestOperatingMargin) : formatPercent(fallbackOperatingMargin)}</dd>
        </div>
        <div>
          <dt>생산시설</dt>
          <dd>{model.kpis.productionFacilities.toLocaleString("ko-KR")}건</dd>
        </div>
        <div>
          <dt>검증 프로젝트</dt>
          <dd>{model.kpis.verifiedProjects.toLocaleString("ko-KR")}건</dd>
        </div>
      </dl>
    </header>
  );
}
