import { ExternalLink } from "lucide-react";
import CompanyActivityTimeline from "./CompanyActivityTimeline";
import CompanyDataGaps from "./CompanyDataGaps";
import {
  detailModel,
  eventDate,
  eventStatusLabel,
  eventTypeLabel,
  formatDate,
  formatKrw,
  formatNumber,
  labelValue,
  profileValue,
  recentSignalEvents,
} from "./companyDetailHelpers";
import { companyDataGapRows } from "../../companyDataGaps";
import { metricDisplayText } from "../../companyReportInsights";

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

function DecisionCards({ company, model, reportInsight, activities, onTabChange }) {
  const revenue = reportInsight?.latest_metrics?.revenue
    ? metricDisplayText(reportInsight.latest_metrics.revenue)
    : formatKrw(model.kpis.latestRevenue);
  const watchSignal = reportInsight?.trend_signals?.find((signal) => signal.level === "watch");
  const latestActivity = activities[0];
  const gapCount = companyDataGapRows(company, reportInsight).length;
  const cards = [
    {
      key: "position",
      title: "시장 포지션",
      body: model.header.summary,
      action: "핵심 경쟁력 보기",
      tab: "production",
    },
    {
      key: "opportunity",
      title: "사업 기회",
      body: latestActivity ? latestActivity.title : "최근 활동 데이터 기준으로 사업 기회를 계속 관찰합니다.",
      action: "최근 활동 보기",
      tab: "overview",
    },
    {
      key: "financial",
      title: "재무 판단",
      body: `최근 매출 ${revenue}. ${watchSignal ? watchSignal.description : "상세 재무 탭에서 이익률과 현금흐름을 함께 확인하세요."}`,
      action: "재무 보기",
      tab: "financial",
    },
    {
      key: "watch",
      title: "관찰 포인트",
      body: gapCount ? `데이터 보완 필요 ${formatNumber(gapCount, "건")}. 확정되지 않은 항목은 별도 공백으로 관리합니다.` : "현재 구조화 데이터에서 큰 공백은 확인되지 않았습니다.",
      action: "근거 보기",
      tab: "evidence",
    },
  ];
  return (
    <div className="company-decision-grid" aria-label="한눈에 보는 판단">
      {cards.map((card) => (
        <article key={card.key}>
          <span>규칙 기반 요약</span>
          <strong>{card.title}</strong>
          <p>{card.body}</p>
          {onTabChange && (
            <button type="button" className="text-button" onClick={() => onTabChange(card.tab)}>
              {card.action}
            </button>
          )}
        </article>
      ))}
    </div>
  );
}

export default function CompanyOverviewTab({ company, activities = [], reportInsight = null, onTabChange }) {
  const model = detailModel(company);
  const profile = company.company_profile || {};
  const recentSignals = recentSignalEvents(model.events);
  const strategicSignals = recentSignals.slice(0, 3);

  return (
    <section className="summary company-tab-panel" id="company-tab-panel-overview" role="tabpanel" aria-labelledby="company-tab-overview">
      <h2>종합분석</h2>
      <DecisionCards company={company} model={model} reportInsight={reportInsight} activities={activities} onTabChange={onTabChange} />

      <div className="company-subsection">
        <div className="company-subsection-heading">
          <h3>핵심 경쟁력</h3>
          <span>상세 탭으로 이동</span>
        </div>
        <div className="company-strength-grid">
          <button type="button" onClick={() => onTabChange?.("production")}>
            <span>생산시설</span>
            <strong>{formatNumber(model.kpis.productionFacilities, "건")}</strong>
          </button>
          <button type="button" onClick={() => onTabChange?.("projects")}>
            <span>검증 프로젝트</span>
            <strong>{formatNumber(model.kpis.verifiedProjects, "건")}</strong>
          </button>
          <button type="button" onClick={() => onTabChange?.("technology")}>
            <span>기술·특허</span>
            <strong>{formatNumber(model.kpis.technologyCount, "건")}</strong>
          </button>
          <button type="button" onClick={() => onTabChange?.("evidence")}>
            <span>주요 시장</span>
            <strong>{(company.target_markets || []).slice(0, 2).map((item) => labelValue(item, item)).join(", ") || "확인 중"}</strong>
          </button>
        </div>
      </div>

      <div className="company-subsection">
        <h3>기업 기본정보</h3>
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
          {company.website_url ? <a className="inline-link" href={company.website_url} target="_blank" rel="noopener noreferrer">원문 열기 <ExternalLink size={13} /></a> : "확인되지 않음"}
        </Field>
      </dl>
      </div>

      <div className="company-subsection">
        <h3>주요사업</h3>
        <TagList items={profileValue(profile.major_businesses)} />
      </div>

      <div className="company-subsection">
        <h3>최근 주요 전략·동향</h3>
        {strategicSignals.length ? (
          <div className="company-section-list">
            {strategicSignals.map((signal) => (
              <div key={signal.event_id || signal.title}>
                <strong>{signal.title || "최근 동향"}</strong>
                <span>{[eventTypeLabel(signal), eventStatusLabel(signal), formatDate(eventDate(signal))].filter(Boolean).join(" · ")}</span>
              </div>
            ))}
          </div>
        ) : (
          <p>최근 전략 이벤트는 공개자료 확인 중입니다.</p>
        )}
      </div>

      <CompanyActivityTimeline activities={activities} />
      <CompanyDataGaps company={company} reportInsight={reportInsight} />
    </section>
  );
}
