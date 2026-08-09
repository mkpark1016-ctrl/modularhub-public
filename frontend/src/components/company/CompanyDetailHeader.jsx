import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";
import { detailModel, formatDate } from "./companyDetailHelpers";
import { buildCompanyDecisionModel } from "../../companyDecisionModel";

export default function CompanyDetailHeader({ company, activeTab = "overview", reportInsight = null }) {
  const model = detailModel(company);
  const compact = activeTab !== "overview";
  const decision = buildCompanyDecisionModel(company, { reportInsight });
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
          {!compact && (
            <div className="company-detail-keyword-panel" aria-label="기업 의사결정 키워드">
              <div className="company-chip-row">
                {decision.positionKeywords.slice(0, 4).map((item) => <span key={item}>{item}</span>)}
              </div>
              <div className="company-chip-row subtle">
                {decision.targetMarkets.slice(0, 4).map((item) => <span key={`market-${item}`}>{item}</span>)}
                {decision.modularMethods.slice(0, 3).map((item) => <span key={`method-${item}`}>{item}</span>)}
              </div>
            </div>
          )}
        </div>
        <p className="finance-note">
          검증 수준 {model.header.verificationLevelLabel} · 최신 검증일 {formatDate(model.header.latestVerifiedAt)} · 데이터 신뢰도 {model.header.confidenceLabel}
        </p>
      </div>
      {!compact && (
        <details className="company-summary-disclosure">
          <summary>요약 설명 보기</summary>
          <p className="company-position-summary">{model.header.summary}</p>
        </details>
      )}
      {!compact && (
        <dl className="company-kpi-grid" aria-label="기업 핵심 지표">
          {decision.metrics.map((item) => (
            <div key={item.key}>
              <dt>{item.label}</dt>
              <dd>{item.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </header>
  );
}
