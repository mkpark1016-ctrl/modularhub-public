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
import {
  decisionStatusLabel,
  decisionStatusTone,
  financialScopeLabel,
  latestSnapshotMetric,
  metricDisplayText,
  peerBenchmarkLabel,
} from "../../companyReportInsights";
import { buildReportAnalysisEvidence, buildReportMetricEvidence } from "../../companyEvidence";
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

function trendEvidence(reportInsight, trend) {
  return buildReportAnalysisEvidence(reportInsight, trend.headline, {
    value: decisionStatusLabel(trend.status),
    metricIds: trend.metric_ids,
    latestValue: `${trend.latest_year ?? "확인되지 않음"}년 ${trend.latest_display || "확인되지 않음"}`,
    previousValue: `${trend.previous_year ?? "확인되지 않음"}년 ${trend.previous_display || "확인되지 않음"}`,
    calculationValue: trend.change_display || trend.change_pct_unavailable_reason || "확인되지 않음",
    calculationBasis: trend.calculation_basis,
    basisYear: trend.latest_year || reportInsight.latest_year,
    dataStatus: trend.change_pct_unavailable_reason || "변화율 계산 가능",
    limitation: "최근 연도와 직전 연도의 감사재무 지표 변화만 표시하며 미래 성과를 예측하지 않습니다.",
    sourceIds: trend.source_ids,
    note: trend.explanation,
  });
}

function peerEvidence(reportInsight, item) {
  return buildReportAnalysisEvidence(reportInsight, peerBenchmarkLabel(item.metric_id), {
    value: item.company_display,
    metricIds: [item.metric_id],
    latestValue: item.company_display,
    peerValue: item.median_display,
    calculationValue: item.comparable ? item.comparison_label : item.not_comparable_reason,
    calculationBasis: item.calculation_basis,
    basisYear: reportInsight.latest_year,
    dataStatus: item.comparable ? "비교 가능" : "비교 불가",
    limitation: "동일 연도·통화·재무제표 범위에서 최소 3개 기업 값이 있을 때만 순위를 표시하며 종합 경쟁력 점수가 아닙니다.",
    sourceIds: item.source_ids,
    note: `비교 모집단 ${item.comparison_universe_count ?? 0}개, 중앙값 ${item.median_display || "확인되지 않음"}`,
  });
}

function CompanyIntelligenceSummary({ model, reportInsight, onShowEvidence }) {
  if (!reportInsight) {
    return (
      <div className="company-intelligence-summary" aria-label="의사결정 요약">
        <article className="company-intelligence-card muted">
          <span>감사재무 비교 데이터 없음</span>
          <strong>{model.header.name}</strong>
          <p>현재 기업은 감사보고서 기반 공통 View Model이 없어 기존 기업정보와 공개 출처 중심으로 확인합니다.</p>
        </article>
      </div>
    );
  }

  const snapshotRows = [
    { key: "revenue", label: "최근 매출" },
    { key: "operating_profit", label: "영업이익" },
    { key: "operating_cash_flow", label: "영업현금흐름" },
    { key: "total_borrowings", label: "총차입금" },
    { key: "trade_receivables", label: "채권 합계" },
  ];
  const trendRows = Object.values(reportInsight.trends || {}).slice(0, 4);
  const peerRows = (reportInsight.peer_benchmarks || []).slice(0, 3);

  return (
    <div className="company-intelligence-summary" aria-label="의사결정 요약">
      <article className="company-intelligence-card wide">
        <span>Executive Summary</span>
        <strong>{reportInsight.latest_year}년 감사재무 기준 핵심 스냅샷</strong>
        <p>
          {financialScopeLabel(reportInsight.financial_scope)} · {reportInsight.available_years?.[0]}~{reportInsight.latest_year}년 ·
          검증 위치 {reportInsight.source_summary?.verified_location_count ?? 0}건
          {reportInsight.source_summary?.pending_location_count ? ` · 페이지 수동 확인 ${reportInsight.source_summary.pending_location_count}건` : ""}
        </p>
        <dl className="company-intelligence-kpi-list">
          {snapshotRows.map((row) => (
            <div key={row.key}>
              <dt>{row.label}</dt>
              <dd>{metricDisplayText(latestSnapshotMetric(reportInsight, row.key))}</dd>
              {onShowEvidence && (
                <button
                  type="button"
                  className="text-button evidence-inline-button"
                  onClick={() => onShowEvidence(buildReportMetricEvidence(reportInsight, `${reportInsight.latest_year}년 ${row.label}`, latestSnapshotMetric(reportInsight, row.key)))}
                >
                  근거
                </button>
              )}
            </div>
          ))}
        </dl>
      </article>

      <article className="company-intelligence-card">
        <span>3개년 변화</span>
        <strong>최근 추세 신호</strong>
        <div className="company-intelligence-list">
          {trendRows.map((trend) => (
            <p className={`decision-status ${decisionStatusTone(trend.status)}`} key={trend.headline}>
              <b>{trend.headline}</b>
              <span>{decisionStatusLabel(trend.status)} · {trend.explanation}</span>
              <small>{trend.previous_display || "이전값 없음"} → {trend.latest_display || "최신값 없음"} · {trend.change_display || trend.change_pct_unavailable_reason || "변화율 확인 필요"}</small>
              {onShowEvidence && (
                <button type="button" className="text-button evidence-inline-button" onClick={() => onShowEvidence(trendEvidence(reportInsight, trend))}>
                  계산 근거
                </button>
              )}
            </p>
          ))}
        </div>
      </article>

      <article className="company-intelligence-card">
        <span>동료 비교</span>
        <strong>감사재무 기업 내 비교 가능성</strong>
        <div className="company-intelligence-list">
          {peerRows.map((item) => (
            <p className={`decision-status ${item.comparable ? "info" : "pending"}`} key={item.metric_id}>
              <b>{peerBenchmarkLabel(item.metric_id)}</b>
              <span>
                {item.comparable ? `${item.comparison_label} · ${item.company_display}` : item.not_comparable_reason}
              </span>
              <small>모집단 {item.comparison_universe_count ?? item.peer_count}개 · 중앙값 {item.median_display || "확인되지 않음"}</small>
              {onShowEvidence && (
                <button type="button" className="text-button evidence-inline-button" onClick={() => onShowEvidence(peerEvidence(reportInsight, item))}>
                  계산 근거
                </button>
              )}
            </p>
          ))}
        </div>
      </article>
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
      title: "최근 변화",
      body: latestActivity ? `최근 활동 신호: ${latestActivity.title}` : "최근 활동 데이터 기준으로 변화 신호를 계속 관찰합니다.",
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
          <span>검증 데이터 기반 해석</span>
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
      <CompanyIntelligenceSummary model={model} reportInsight={reportInsight} onShowEvidence={onShowEvidence} />
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
