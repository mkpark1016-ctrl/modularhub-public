import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";
import { detailModel, formatDate, formatKrw } from "./companyDetailHelpers";

export default function CompanyDetailHeader({ company }) {
  const model = detailModel(company);
  return (
    <header className="company-detail-header">
      <Link className="back" to="/companies"><ArrowLeft size={17} />목록으로</Link>
      <div className="badge-row">
        <span>{model.header.typeLabel}</span>
        <span>{model.header.relationshipLabel}</span>
        <span>{model.header.tierLabel}</span>
        <span className={`company-status ${model.header.dataStatus}`}>{model.header.dataStatusLabel}</span>
      </div>
      <h1>{company.company_name}</h1>
      <p className="company-position-summary">{model.header.summary}</p>
      <dl className="company-kpi-grid" aria-label="기업 핵심 지표">
        <div>
          <dt>검증 프로젝트</dt>
          <dd>{model.kpis.verifiedProjects.toLocaleString("ko-KR")}건</dd>
        </div>
        <div>
          <dt>생산시설</dt>
          <dd>{model.kpis.productionFacilities.toLocaleString("ko-KR")}건</dd>
        </div>
        <div>
          <dt>기술·특허</dt>
          <dd>{model.kpis.technologyCount.toLocaleString("ko-KR")}건</dd>
        </div>
        <div>
          <dt>최근 매출</dt>
          <dd>{model.kpis.latestRevenueYear ? `${model.kpis.latestRevenueYear}년 ${formatKrw(model.kpis.latestRevenue)}` : "확인되지 않음"}</dd>
        </div>
      </dl>
      <p className="finance-note">최신 검증일 {formatDate(model.header.latestVerifiedAt)} · 데이터 신뢰도 {model.header.confidenceLabel}</p>
    </header>
  );
}
