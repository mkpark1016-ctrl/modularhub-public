import { ExternalLink } from "lucide-react";
import CompanyDataGaps from "./CompanyDataGaps";
import {
  detailModel,
  eventDate,
  eventStatusLabel,
  eventTypeLabel,
  formatDate,
  formatNumber,
  labelValue,
  profileValue,
  recentSignalEvents,
} from "./companyDetailHelpers";
import {
  decisionStatusLabel,
  decisionStatusTone,
  financialScopeLabel,
  latestSnapshotMetric,
  metricDisplayText,
  peerBenchmarkLabel,
} from "../../companyReportInsights";
import { buildReportAnalysisEvidence } from "../../companyEvidence";
import { buildCompanyDecisionModel } from "../../companyDecisionModel";

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

function DecisionSnapshotPanel({ decision }) {
  const groups = [
    { key: "position", title: "포지션", items: decision.positionKeywords },
    { key: "capability", title: "역량", items: decision.capabilities },
    { key: "watch", title: "관찰", items: decision.watchSignals.length ? decision.watchSignals : ["추가 관찰 신호 없음"] },
  ];
  return (
    <div className="company-decision-snapshot" aria-label="기업 의사결정 스냅샷">
      {groups.map((group) => (
        <article key={group.key}>
          <span>{group.title}</span>
          <div className="company-chip-row">
            {group.items.slice(0, 4).map((item) => <b key={item}>{item}</b>)}
          </div>
        </article>
      ))}
    </div>
  );
}

function KeyFinancialSnapshot({ reportInsight, onTabChange, onShowEvidence }) {
  if (!reportInsight) {
    return (
      <div className="company-subsection compact-company-section">
        <div className="company-subsection-heading">
          <h3>핵심 재무 스냅샷</h3>
          <span>감사재무 View Model 없음</span>
        </div>
        <p className="finance-note">이 기업은 기존 재무 탭의 공개자료 기준 정보를 유지합니다.</p>
      </div>
    );
  }
  const rows = [
    ["revenue", "최근 매출"],
    ["operating_profit", "영업이익"],
    ["operating_cash_flow", "영업현금흐름"],
    ["total_borrowings", "총차입금"],
    ["receivables_total", "채권 합계"],
  ];
  return (
    <div className="company-subsection compact-company-section">
      <div className="company-subsection-heading">
        <h3>핵심 재무 스냅샷</h3>
        <button type="button" className="text-button" onClick={() => onTabChange?.("financial")}>재무 상세</button>
      </div>
      <dl className="company-compact-metric-grid" aria-label="핵심 재무 스냅샷">
        {rows.map(([key, label]) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>{metricDisplayText(latestSnapshotMetric(reportInsight, key))}</dd>
          </div>
        ))}
      </dl>
      {onShowEvidence && (
        <button
          type="button"
          className="text-button evidence-inline-button"
          onClick={() => onShowEvidence(buildReportAnalysisEvidence(reportInsight, "핵심 재무 스냅샷", {
            value: `${reportInsight.latest_year}년 기준`,
            metricIds: rows.map(([key]) => key),
            basisYear: reportInsight.latest_year,
            dataStatus: financialScopeLabel(reportInsight.financial_scope),
            note: "개별 수치의 원문 위치는 재무 탭과 근거 탭에서 확인합니다.",
          }))}
        >
          섹션 근거 보기
        </button>
      )}
    </div>
  );
}

function ThreeYearSignalRows({ reportInsight }) {
  const rows = Object.values(reportInsight?.trends || {}).slice(0, 4);
  if (!rows.length) return null;
  return (
    <div className="company-subsection compact-company-section">
      <div className="company-subsection-heading">
        <h3>3개년 신호</h3>
        <span>설명은 재무 탭에서 확인</span>
      </div>
      <div className="company-compact-row-list" aria-label="3개년 신호">
        {rows.map((trend) => (
          <div className={`decision-status ${decisionStatusTone(trend.status)}`} key={trend.headline}>
            <b>{trend.headline}</b>
            <span>{decisionStatusLabel(trend.status)}</span>
            <em>{trend.previous_display || "이전값 없음"} → {trend.latest_display || "최신값 없음"}</em>
          </div>
        ))}
      </div>
    </div>
  );
}

function PeerPositionRows({ reportInsight, onTabChange }) {
  const rows = (reportInsight?.peer_benchmarks || []).slice(0, 3);
  if (!rows.length) return null;
  const groupLabel = reportInsight?.comparison_context?.group_label || "동일 유형";
  return (
    <div className="company-subsection compact-company-section">
      <div className="company-subsection-heading">
        <div>
          <h3>동일 유형 기업 대비 재무 위치</h3>
          <span className="comparison-group-label">비교 그룹 · {groupLabel}</span>
        </div>
        <button type="button" className="text-button" onClick={() => onTabChange?.("financial")}>재무 비교 자세히</button>
      </div>
      <p className="finance-note">같은 기업유형·연도·통화·재무제표 기준의 감사재무를 비교합니다.</p>
      <div className="company-peer-compact-list" aria-label="동일 유형 기업 대비 재무 위치">
        {rows.map((item) => (
          <div key={item.metric_id}>
            <strong>{peerBenchmarkLabel(item.metric_id)}</strong>
            <span>{item.company_display || "확인되지 않음"}</span>
            <span>{item.comparable ? `${item.comparison_universe_count ?? item.peer_count}개 중 ${item.rank}위` : "비교 준비 중"}</span>
            <small>같은 유형 중앙값 {item.median_display || "확인되지 않음"}</small>
            {item.median_difference_display && <small>{item.median_difference_display}</small>}
          </div>
        ))}
      </div>
    </div>
  );
}

function RecentActivityPreview({ activities }) {
  const visible = (activities || []).slice(0, 3);
  return (
    <div className="company-subsection compact-company-section">
      <div className="company-subsection-heading">
        <h3>최근 활동</h3>
        <span>최대 3건</span>
      </div>
      {visible.length ? (
        <div className="company-compact-row-list">
          {visible.map((activity) => (
            <div key={activity.activityId || activity.url || activity.title}>
              <b>{activity.title}</b>
              <span>{activity.source || activity.publisher || "공개자료"}</span>
              <em>{formatDate(activity.publishedAt)}</em>
            </div>
          ))}
        </div>
      ) : (
        <p className="finance-note">최근 공개 활동 신호가 확인되지 않았습니다.</p>
      )}
    </div>
  );
}

export default function CompanyOverviewTab({ company, activities = [], reportInsight = null, onShowEvidence, onTabChange }) {
  const model = detailModel(company);
  const decision = buildCompanyDecisionModel(company, { reportInsight, activities });
  const profile = company.company_profile || {};
  const recentSignals = recentSignalEvents(model.events);
  const strategicSignals = recentSignals.slice(0, 3);

  return (
    <section className="summary company-tab-panel" id="company-tab-panel-overview" role="tabpanel" aria-labelledby="company-tab-overview">
      <h2>종합분석</h2>
      <DecisionSnapshotPanel decision={decision} />
      <KeyFinancialSnapshot reportInsight={reportInsight} onTabChange={onTabChange} onShowEvidence={onShowEvidence} />
      <ThreeYearSignalRows reportInsight={reportInsight} />
      <PeerPositionRows reportInsight={reportInsight} onTabChange={onTabChange} />
      <RecentActivityPreview activities={activities} />

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

      <CompanyDataGaps company={company} reportInsight={reportInsight} />
    </section>
  );
}
