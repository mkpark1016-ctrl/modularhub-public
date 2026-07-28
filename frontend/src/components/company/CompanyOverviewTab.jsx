import { ExternalLink } from "lucide-react";
import CompanyActivityTimeline from "./CompanyActivityTimeline";
import {
  detailModel,
  formatDate,
  formatNumber,
  labelValue,
  profileValue,
  recentSignalEvents,
} from "./companyDetailHelpers";

function Field({ label, children }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children || "확인되지 않음"}</dd>
    </div>
  );
}

function TagList({ items }) {
  const values = (Array.isArray(items) ? items : []).filter(Boolean);
  if (!values.length) return "확인되지 않음";
  return (
    <div className="company-tag-list">
      {values.map((item) => <span key={item}>{labelValue(item, item)}</span>)}
    </div>
  );
}

export default function CompanyOverviewTab({ company, activities = [] }) {
  const model = detailModel(company);
  const profile = company.company_profile || {};
  const recentSignals = recentSignalEvents(model.events);
  const latestSignal = recentSignals[0];

  return (
    <section className="summary company-tab-panel" id="company-tab-panel-overview" role="tabpanel" aria-labelledby="company-tab-overview">
      <h2>기업 개요</h2>
      <dl className="detail-grid compact-detail-grid">
        <Field label="영문명">{company.company_name_en || "확인되지 않음"}</Field>
        <Field label="설립일">{formatDate(profile.established_at)}</Field>
        <Field label="대표이사">{profile.representative || "확인되지 않음"}</Field>
        <Field label="임직원 수">
          {profile.employee_count ? `${formatNumber(profile.employee_count)}명${profile.employee_count_as_of ? ` · ${profile.employee_count_as_of} 기준` : ""}` : "확인되지 않음"}
        </Field>
        <Field label="본사">{company.headquarters || (profile.offices || [])[0] || "확인되지 않음"}</Field>
        <Field label="회사 유형">{model.header.typeLabel}</Field>
        <Field label="모듈러 공법"><TagList items={company.modular_methods} /></Field>
        <Field label="목표 시장"><TagList items={company.target_markets} /></Field>
        <Field label="공식 웹사이트">
          {company.website_url ? <a className="inline-link" href={company.website_url} target="_blank" rel="noopener noreferrer">공식 웹사이트 <ExternalLink size={13} /></a> : "확인되지 않음"}
        </Field>
      </dl>

      <div className="company-subsection">
        <h3>주요사업</h3>
        <TagList items={profileValue(profile.major_businesses)} />
      </div>

      <div className="company-subsection">
        <h3>경쟁 포지션</h3>
        <p>{model.header.summary}</p>
        {profile.modular_business_model && <p className="finance-note">모듈러 사업 모델: {profile.modular_business_model}</p>}
      </div>

      <div className="company-subsection">
        <h3>최근 주요 전략·동향</h3>
        {latestSignal ? (
          <div className="company-section-list">
            <div>
              <strong>{latestSignal.title || "최근 동향"}</strong>
              <span>{[labelValue(latestSignal.event_type), labelValue(latestSignal.event_status), formatDate(latestSignal.announced_at || latestSignal.updated_at)].filter(Boolean).join(" · ")}</span>
            </div>
          </div>
        ) : (
          <p>현재 공개자료를 추가 조사 중입니다.</p>
        )}
      </div>

      <CompanyActivityTimeline activities={activities} />
    </section>
  );
}
