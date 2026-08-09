import {
  formatNumber,
} from "./companyDetailHelpers";
import {
  decisionStatusLabel,
  decisionStatusTone,
  financialScopeLabel,
  latestAuditOpinion,
  metricDisplayText,
  metricToneClass,
  peerBenchmarkLabel,
  REPORT_AMOUNT_ROWS,
  REPORT_RATIO_ROWS,
  REPORT_REVENUE_BREAKDOWN_ROWS,
  reportMetricByYear,
  reportRatioByYear,
  reportRevenueShareKey,
  reportSectionLabel,
  reportYears,
  sourceSectionCounts,
  verificationStatusLabel,
} from "../../companyReportInsights";
import { buildReportAnalysisEvidence, buildReportMetricEvidence } from "../../companyEvidence";

const KPI_CARDS = [
  { key: "revenue", label: "최근 매출" },
  { key: "operating_profit", label: "영업이익", ratioKey: "operating_margin_pct", ratioLabel: "영업이익률" },
  { key: "operating_cash_flow", label: "영업현금흐름" },
  { key: "total_borrowings", label: "총차입금" },
];

function latestRatio(insight, key) {
  return insight?.derived_metrics?.[String(insight.latest_year)]?.[key] || null;
}

function formatDate(value) {
  return value || "확인되지 않음";
}

function metricNumber(metric) {
  if (metric?.display_eok !== null && metric?.display_eok !== undefined) return Number(metric.display_eok);
  if (metric?.raw_krw !== null && metric?.raw_krw !== undefined) return Number(metric.raw_krw) / 100_000_000;
  if (metric?.value !== null && metric?.value !== undefined) return Number(metric.value);
  return null;
}

function metricDisplayLabel(row, title) {
  return `${row.year}년 ${title} ${metricDisplayText(row.metric)}`;
}

function metricWidth(value, max) {
  return Number.isFinite(value) ? Math.max(8, Math.min(100, (Math.abs(value) / max) * 100)) : 0;
}

function cashFlowWidth(value, max) {
  if (!Number.isFinite(value) || value === 0) return 0;
  return Math.max(8, Math.min(100, (Math.abs(value) / max) * 100));
}

function signedMetricDisplayText(metric) {
  const value = metricNumber(metric);
  const text = metricDisplayText(metric);
  if (!Number.isFinite(value) || value <= 0 || text.startsWith("+") || text.startsWith("-")) {
    return text;
  }
  return `+${text}`;
}

function SingleMetricTrend({ title, rows, variant = "primary", subtitle = "공식 공시문서의 감사받은 재무제표 금액" }) {
  const values = rows.map((row) => metricNumber(row.metric)).filter((value) => Number.isFinite(value));
  const max = Math.max(...values.map((value) => Math.abs(value)), 1);
  return (
    <article className={`financial-mini-chart ${variant}`} aria-label={`${title}: ${rows.map((row) => metricDisplayLabel(row, title)).join(", ")}`}>
      <div className="financial-chart-header">
        <strong>{title}</strong>
        <span>{subtitle}</span>
      </div>
      <div className="financial-chart-bars">
        {rows.map((row) => {
          const value = metricNumber(row.metric);
          const isAvailable = Number.isFinite(value);
          return (
            <span className={`financial-chart-row ${isAvailable ? "" : "is-unavailable"}`} key={`${title}-${row.metricKey || "metric"}-${row.year}`} aria-label={metricDisplayLabel(row, title)}>
              <b>{row.year}</b>
              {isAvailable && <i className={`financial-chart-bar ${variant} ${value < 0 ? "negative" : ""}`} style={{ width: `${metricWidth(value, max)}%` }} aria-hidden="true" />}
              <em>{metricDisplayText(row.metric)}</em>
            </span>
          );
        })}
      </div>
    </article>
  );
}

function CashFlowTrend({ rows }) {
  const values = rows.map((row) => metricNumber(row.metric)).filter((value) => Number.isFinite(value));
  const max = Math.max(...values.map((value) => Math.abs(value)), 1);
  return (
    <article className="financial-mini-chart cash-flow" aria-label={`영업현금흐름 추이: ${rows.map((row) => metricDisplayLabel(row, "영업현금흐름")).join(", ")}`}>
      <div className="financial-chart-header">
        <strong>영업현금흐름</strong>
        <span>0 기준선 기준 양수·음수 구분</span>
      </div>
      <div className="financial-cash-flow-bars">
        {rows.map((row) => {
          const value = metricNumber(row.metric);
          const negative = Number.isFinite(value) && value < 0;
          const positive = Number.isFinite(value) && value > 0;
          const zero = Number.isFinite(value) && value === 0;
          const directionClass = negative
            ? "cash-flow-direction-negative"
            : positive
              ? "cash-flow-direction-positive"
              : zero
                ? "cash-flow-direction-zero"
                : "cash-flow-direction-unknown";
          const displayText = signedMetricDisplayText(row.metric);
          return (
            <span className={`financial-cash-flow-row ${directionClass}`} key={`cash-flow-${row.year}`} aria-label={`${row.year}년 영업현금흐름 ${displayText}`}>
              <b>{row.year}</b>
              <span className="financial-cash-flow-zone negative" aria-hidden="true">
                {negative && <i className="financial-cash-flow-bar negative" style={{ width: `${cashFlowWidth(value, max)}%` }} />}
              </span>
              <span className="financial-zero-line" aria-hidden="true">
                {zero && <i className="financial-zero-marker" />}
              </span>
              <span className="financial-cash-flow-zone positive" aria-hidden="true">
                {positive && <i className="financial-cash-flow-bar positive" style={{ width: `${cashFlowWidth(value, max)}%` }} />}
              </span>
              <em>{displayText}</em>
            </span>
          );
        })}
      </div>
    </article>
  );
}

function groupedSignals(signals = []) {
  const groups = [
    { key: "growth", title: "성장성", match: ["revenue", "receivables", "inventory"] },
    { key: "profitability", title: "수익성", match: ["margin", "profit"] },
    { key: "stability", title: "재무안정성", match: ["cash_flow", "borrowings", "ratio"] },
  ];
  return groups.map((group) => ({
    ...group,
    signals: signals.filter((signal) => group.match.some((token) => String(signal.code || "").includes(token))),
  })).filter((group) => group.signals.length);
}

function healthDisplayValue(insight, item) {
  const metricId = Array.isArray(item.metric_ids) ? item.metric_ids[0] : null;
  if (!metricId) return item.actual_value ?? "확인되지 않음";
  const metric = metricId.endsWith("_pct")
    ? reportRatioByYear(insight, insight.latest_year, metricId)
    : reportMetricByYear(insight, insight.latest_year, metricId);
  return metricDisplayText(metric);
}

function hasRevenueBreakdownRows(insight, years) {
  return REPORT_REVENUE_BREAKDOWN_ROWS.some((row) => years.some((year) => reportMetricByYear(insight, year, row.key)));
}

function SourceLocationList({ metric }) {
  const locations = Array.isArray(metric?.source_locations) ? metric.source_locations : [];
  if (!locations.length) return <span>출처 위치 확인 필요</span>;
  return (
    <span>
      {locations.map((location, index) => (
        <span className="audit-source-location" key={`${location.source_ref || "source"}-${index}`}>
          {reportSectionLabel(location.section)}
          {location.page_range ? ` ${location.page_range}쪽` : ""}
          {" · "}
          {verificationStatusLabel(location.verification_status)}
        </span>
      ))}
    </span>
  );
}

function healthEvidence(insight, item) {
  return buildReportAnalysisEvidence(insight, item.headline, {
    value: decisionStatusLabel(item.status),
    metricIds: item.metric_ids,
    latestValue: item.actual_value ?? "확인되지 않음",
    calculationValue: `${item.operator || "operator 확인 필요"} ${item.threshold ?? "threshold 확인 필요"}`,
    calculationBasis: item.calculation_basis,
    basisYear: insight.latest_year,
    dataStatus: "감사재무 관찰 규칙",
    limitation: item.interpretation_scope || item.limitation,
    sourceIds: item.source_ids,
    note: item.explanation,
  });
}

function trendEvidence(insight, trend) {
  return buildReportAnalysisEvidence(insight, trend.headline, {
    value: decisionStatusLabel(trend.status),
    metricIds: trend.metric_ids,
    latestValue: `${trend.latest_year ?? "확인되지 않음"}년 ${trend.latest_display || "확인되지 않음"}`,
    previousValue: `${trend.previous_year ?? "확인되지 않음"}년 ${trend.previous_display || "확인되지 않음"}`,
    calculationValue: trend.change_display || trend.change_pct_unavailable_reason || "확인되지 않음",
    calculationBasis: trend.calculation_basis,
    basisYear: trend.latest_year || insight.latest_year,
    dataStatus: trend.change_pct_unavailable_reason || "변화율 계산 가능",
    limitation: "최근 연도와 직전 연도의 감사재무 지표 변화만 표시하며 미래 성과를 예측하지 않습니다.",
    sourceIds: trend.source_ids,
    note: trend.explanation,
  });
}

function peerEvidence(insight, item) {
  return buildReportAnalysisEvidence(insight, peerBenchmarkLabel(item.metric_id), {
    value: item.company_display,
    metricIds: [item.metric_id],
    latestValue: item.company_display,
    peerValue: item.median_display,
    calculationValue: item.comparable ? item.comparison_label : item.not_comparable_reason,
    calculationBasis: item.calculation_basis,
    basisYear: insight.latest_year,
    dataStatus: item.comparable ? "비교 가능" : "비교 불가",
    limitation: "같은 기업유형·연도·통화·재무제표 범위에서 최소 3개 기업 값이 있을 때만 상대 위치를 표시하며 종합 경쟁력 점수가 아닙니다.",
    sourceIds: item.source_ids,
    note: `비교 모집단 ${item.comparison_universe_count ?? 0}개, 현재 기업 포함 ${item.current_company_included ? "예" : "아니오"}`,
  });
}

function FinancialDecisionSummary({ insight, onShowEvidence }) {
  const healthItems = Object.entries(insight.financial_health || {});
  const trendItems = Object.values(insight.trends || {}).slice(0, 4);
  if (!healthItems.length && !trendItems.length) return null;
  return (
    <div className="company-subsection">
      <div className="company-subsection-heading">
        <h3>의사결정 요약</h3>
        <span>공식 공시문서에 포함된 감사받은 재무제표 기준 정보</span>
      </div>
      <div className="company-intelligence-summary compact" aria-label="재무 의사결정 요약">
        {healthItems.map(([key, item]) => (
          <article className={`company-intelligence-card ${decisionStatusTone(item.status)}`} key={key}>
            <span>{decisionStatusLabel(item.status)}</span>
            <strong>{item.headline}</strong>
            <p>{item.explanation}</p>
            <dl className="company-mini-detail-list">
              <div><dt>관찰값</dt><dd>{healthDisplayValue(insight, item)}</dd></div>
              <div><dt>상태</dt><dd>{decisionStatusLabel(item.status)}</dd></div>
            </dl>
            {item.limitation && <small>{item.limitation}</small>}
            {item.interpretation_scope && <small>{item.interpretation_scope}</small>}
            {onShowEvidence && (
              <button type="button" className="text-button evidence-inline-button" onClick={() => onShowEvidence(healthEvidence(insight, item))}>
                계산 근거 보기
              </button>
            )}
          </article>
        ))}
      </div>
      <div className="company-intelligence-trend-strip" aria-label="최근 추세 신호">
        {trendItems.map((trend) => (
          <span className={`decision-status ${decisionStatusTone(trend.status)}`} key={trend.headline}>
            <b>{trend.headline}</b>
            <em>{decisionStatusLabel(trend.status)} · {trend.previous_display || "이전값 없음"} → {trend.latest_display || "최신값 없음"} · {trend.change_display || trend.change_pct_unavailable_reason || "변화율 확인 필요"}</em>
            {onShowEvidence && (
              <button type="button" className="text-button evidence-inline-button" onClick={() => onShowEvidence(trendEvidence(insight, trend))}>
                계산 근거
              </button>
            )}
          </span>
        ))}
      </div>
    </div>
  );
}

function benchmarkRankText(item) {
  if (!item.comparable || !item.rank) return "비교 준비 중";
  const count = item.comparison_universe_count ?? item.peer_count;
  return `${count}개 중 ${item.rank}위`;
}

function comparisonGroupLabel(insight, item) {
  return item.comparison_group_label || insight?.comparison_context?.group_label || "동일 유형";
}

function PeerBenchmarkPanel({ insight, benchmarks = [], onShowEvidence }) {
  if (!benchmarks.length) return null;
  return (
    <div className="company-subsection">
      <div className="company-subsection-heading">
        <div>
          <h3>동일 유형 기업 재무 비교</h3>
          <span>같은 기업유형·연도·통화·재무제표 범위에서만 비교합니다.</span>
        </div>
        <span className="comparison-group-label">비교 그룹 · {insight?.comparison_context?.group_label || "확인 중"}</span>
      </div>
      <div className="company-peer-grid" aria-label="동일 유형 기업 재무 비교">
        {benchmarks.map((item) => (
          <article className={`company-peer-card ${item.comparable ? "is-comparable" : "is-not-comparable"}`} key={item.metric_id}>
            <span>{peerBenchmarkLabel(item.metric_id)}</span>
            <strong>{item.company_display}</strong>
            <p>{item.comparable ? benchmarkRankText(item) : item.not_comparable_reason}</p>
            <dl className="company-mini-detail-list">
              <div><dt>현재</dt><dd>{item.company_display}</dd></div>
              <div><dt>같은 유형 중앙값</dt><dd>{item.median_display || "확인되지 않음"}</dd></div>
              <div><dt>위치</dt><dd>{benchmarkRankText(item)}</dd></div>
              <div><dt>중앙값과의 차이</dt><dd>{item.median_difference_display || "비교 준비 중"}</dd></div>
            </dl>
            <small>{item.comparable ? `${comparisonGroupLabel(insight, item)} 그룹 · ${item.comparison_direction === "higher_is_larger" ? "값이 큰 순" : "값이 낮은 순"}` : "다른 기업유형으로 대체 비교하지 않습니다."}</small>
            <details className="comparison-basis-details">
              <summary>비교 기준 보기</summary>
              <dl className="company-mini-detail-list">
                <div><dt>기업 유형</dt><dd>{comparisonGroupLabel(insight, item)}</dd></div>
                <div><dt>기준 연도</dt><dd>{item.comparison_year || insight.latest_year}</dd></div>
                <div><dt>재무제표 범위</dt><dd>{financialScopeLabel(item.comparison_financial_scope || insight.financial_scope)}</dd></div>
                <div><dt>통화</dt><dd>{item.comparison_currency || insight.currency}</dd></div>
                <div><dt>비교 가능 기업 수</dt><dd>{formatNumber(item.comparison_universe_count ?? item.peer_count, "개")}</dd></div>
                <div><dt>최소 비교 기준</dt><dd>{formatNumber(insight.comparison_context?.minimum_peer_count || 3, "개")}</dd></div>
                <div><dt>현재 기업 포함</dt><dd>{item.current_company_included ? "예" : "아니오"}</dd></div>
              </dl>
            </details>
            {onShowEvidence && (
              <button type="button" className="text-button evidence-inline-button" onClick={() => onShowEvidence(peerEvidence(insight, item))}>
                근거 보기
              </button>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}

export default function CompanyAuditFinancialPanel({ insight, onShowEvidence }) {
  const years = reportYears(insight);
  const sourceSummary = insight.source_summary || {};
  const latestOpinion = latestAuditOpinion(insight);
  const sectionCounts = sourceSectionCounts(insight).filter((item) => item.count > 0);
  const chartRows = (metricKey) => years.map((year) => ({ year, metricKey, metric: reportMetricByYear(insight, year, metricKey) }));
  const ratioRows = (metricKey) => years.map((year) => ({ year, metricKey, metric: reportRatioByYear(insight, year, metricKey) }));
  const warningCount = insight.disclosure_warnings?.length || 0;
  const hasRevenueBreakdown = hasRevenueBreakdownRows(insight, years);
  const specialEvents = Array.isArray(insight.attribution?.special_events) ? insight.attribution.special_events : [];
  const visibleDisclosureWarnings = (insight.disclosure_warnings || []).filter((warning) => (
    String(warning.code || "").startsWith("verification_pending") || warning.code === "modular_segment_revenue_not_disclosed"
  ));

  return (
    <>
      <p className="finance-note">
        공식 공시문서에 포함된 감사받은 재무제표 기준 정보입니다. 모듈러 부문 별도 매출 공개 여부에 따라 회사 전체 재무와 구분해 해석합니다.
      </p>

      <FinancialDecisionSummary insight={insight} onShowEvidence={onShowEvidence} />

      {visibleDisclosureWarnings.length > 0 && (
        <div className="company-report-pending-callouts" aria-label="검증 보류 및 공시 한계 안내">
          {visibleDisclosureWarnings.map((warning) => (
            <p key={warning.code}>
              <strong>{warning.level === "warning" ? "공시 한계" : "검증 보류"}</strong>
              <span>{warning.message}</span>
            </p>
          ))}
        </div>
      )}

      <div className="company-report-kpi-grid" aria-label="감사보고서 핵심 재무 지표">
        {KPI_CARDS.map((item) => {
          const metric = insight.latest_metrics?.[item.key] || null;
          const ratio = item.ratioKey ? latestRatio(insight, item.ratioKey) : null;
          return (
            <div className="company-report-kpi" key={item.key}>
              <span>{item.label}</span>
              <strong className={metricToneClass(metric)}>{metricDisplayText(metric)}</strong>
              {ratio && <small>{item.ratioLabel} {metricDisplayText(ratio)}</small>}
              <small>{insight.latest_year}년 기준</small>
              {onShowEvidence && (
                <button
                  type="button"
                  className="text-button evidence-inline-button"
                  onClick={() => onShowEvidence(buildReportMetricEvidence(insight, `${insight.latest_year}년 ${item.label}`, metric))}
                >
                  근거보기
                </button>
              )}
            </div>
          );
        })}
      </div>

      <div className="company-subsection">
        <h3>재무 추세</h3>
        <div className="financial-mini-chart-grid">
          <SingleMetricTrend title="매출 추이" rows={chartRows("revenue")} variant="revenue" />
          <SingleMetricTrend title="영업이익률" rows={ratioRows("operating_margin_pct")} variant="operating-margin" subtitle="감사보고서 기반 파생 비율" />
          <CashFlowTrend rows={chartRows("operating_cash_flow")} />
          <SingleMetricTrend title="총차입금 추이" rows={chartRows("total_borrowings")} variant="borrowings" />
        </div>
      </div>

      <PeerBenchmarkPanel insight={insight} benchmarks={insight.peer_benchmarks} onShowEvidence={onShowEvidence} />

      {hasRevenueBreakdown && (
        <div className="company-subsection">
          <div className="company-subsection-heading">
            <h3>매출 구성</h3>
            <span>공시 주석 금액을 원 단위로 환산한 값이며 별도 사업부문 매출로 과도하게 해석하지 않습니다.</span>
          </div>
          <div className="company-table-wrap">
            <table className="company-financial-table company-report-table company-revenue-breakdown-table">
              <thead>
                <tr>
                  <th scope="col">항목</th>
                  {years.map((year) => <th scope="col" key={year}>{year}</th>)}
                  {onShowEvidence && <th scope="col">근거</th>}
                </tr>
              </thead>
              <tbody>
                {REPORT_REVENUE_BREAKDOWN_ROWS.map((row) => (
                  <tr key={row.key}>
                    <th scope="row">{row.label}</th>
                    {years.map((year) => {
                      const metric = reportMetricByYear(insight, year, row.key);
                      const share = reportRatioByYear(insight, year, reportRevenueShareKey(row.key));
                      return (
                        <td className={metricToneClass(metric)} key={`${row.key}-${year}`}>
                          <span>{metricDisplayText(metric)}</span>
                          {share?.value !== null && share?.value !== undefined && (
                            <small className="finance-ratio-note">{metricDisplayText(share)}</small>
                          )}
                        </td>
                      );
                    })}
                    {onShowEvidence && (
                      <td>
                        <button
                          type="button"
                          className="text-button evidence-inline-button"
                          onClick={() => onShowEvidence(buildReportMetricEvidence(insight, `${insight.latest_year} ${row.label}`, reportMetricByYear(insight, insight.latest_year, row.key)))}
                        >
                          근거보기
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {specialEvents.length > 0 && (
        <div className="company-subsection">
          <div className="company-report-interpretation-card">
            <strong>해석 범위 안내</strong>
            <ul>
              <li>{financialScopeLabel(insight.financial_scope || insight.attribution?.financial_scope)} 기준입니다.</li>
              {specialEvents.map((event) => <li key={`${event.event_type}-${event.effective_date}`}>{event.description}</li>)}
              {hasRevenueBreakdown && <li>매출구성 주석은 천원 단위 공시값을 원 단위로 환산했습니다.</li>}
              {hasRevenueBreakdown && <li>제품, 임대, 용역, 공사, 기타 매출 캡션은 별도 사업부문 매출로 자동 해석하지 않습니다.</li>}
            </ul>
          </div>
        </div>
      )}

      <div className="company-subsection">
        <details className="company-report-details">
          <summary>상세 재무표 보기</summary>
          <div className="company-table-wrap">
            <table className="company-financial-table company-report-table">
              <thead>
                <tr>
                  <th scope="col">항목</th>
                  {years.map((year) => <th scope="col" key={year}>{year}</th>)}
                </tr>
              </thead>
              <tbody>
                {REPORT_AMOUNT_ROWS.map((row) => (
                  <tr key={row.key}>
                    <th scope="row">{row.label}</th>
                    {years.map((year) => {
                      const metric = reportMetricByYear(insight, year, row.key);
                      return <td className={metricToneClass(metric)} key={`${row.key}-${year}`}>{metricDisplayText(metric)}</td>;
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h3>핵심 재무비율</h3>
          <div className="company-table-wrap">
            <table className="company-financial-table company-report-table">
              <thead>
                <tr>
                  <th scope="col">항목</th>
                  {years.map((year) => <th scope="col" key={year}>{year}</th>)}
                </tr>
              </thead>
              <tbody>
                {REPORT_RATIO_ROWS.map((row) => (
                  <tr key={row.key}>
                    <th scope="row">{row.label}</th>
                    {years.map((year) => {
                      const metric = reportRatioByYear(insight, year, row.key);
                      return <td className={metricToneClass(metric)} key={`${row.key}-${year}`}>{metricDisplayText(metric)}</td>;
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </div>

      <div className="company-subsection">
        <h3>재무 인사이트</h3>
        <div className="company-report-signal-grid">
          {groupedSignals(insight.trend_signals).map((group) => (
            <article className={`company-report-signal ${group.signals.some((signal) => signal.level === "watch") ? "watch" : "info"}`} key={group.key}>
              <span>{group.signals.some((signal) => signal.level === "watch") ? "관찰 필요" : "참고"}</span>
              <strong>{group.title}</strong>
              {group.signals.slice(0, 2).map((signal) => <p key={signal.code}>{signal.description}</p>)}
            </article>
          ))}
        </div>
      </div>

      <div className="company-subsection">
        <h3>재무 해석 범위</h3>
        <dl className="company-report-source-summary">
          <div><dt>재무제표 기준</dt><dd>{financialScopeLabel(insight.financial_scope || insight.attribution?.financial_scope)}</dd></div>
          <div><dt>감사의견</dt><dd>{latestOpinion?.opinion_label_ko || "확인되지 않음"}</dd></div>
          <div><dt>감사인</dt><dd>{latestOpinion?.auditor || sourceSummary.auditors?.join(", ") || "확인되지 않음"}</dd></div>
          <div><dt>최신 보고서 기준일</dt><dd>{formatDate(sourceSummary.latest_report_date)}</dd></div>
          <div><dt>검증된 출처 위치</dt><dd>{sourceSummary.verified_location_count ?? insight.data_quality?.source_location_count ?? "확인되지 않음"}건</dd></div>
          <div><dt>페이지 수동 확인 필요</dt><dd>{sourceSummary.pending_location_count ?? insight.data_quality?.pending_manual_page_check_count ?? "확인되지 않음"}건</dd></div>
        </dl>
        <p className="finance-note">
          {insight.attribution?.attribution_warning}
        </p>
        {warningCount > 0 && (
          <details className="company-report-details">
            <summary>공시 해석 주의사항 {warningCount}건</summary>
            <div className="company-section-list">
              {(insight.disclosure_warnings || []).map((warning) => (
                <div className="company-report-warning" key={warning.code}>
                  <strong>{warning.message}</strong>
                  <span>{warning.level === "warning" ? "해석상 주의가 필요한 공시 제약" : "검증 보조 안내"}</span>
                </div>
              ))}
            </div>
          </details>
        )}
      </div>

      {sectionCounts.length > 0 && <div className="company-subsection">
        <div className="company-subsection-heading">
          <h3>출처 섹션 표시</h3>
          <span>코드는 UI에서 한국어로 변환됩니다.</span>
        </div>
        <div className="company-report-section-tags">
          {sectionCounts.map((item) => (
            <span key={item.section}>{item.label} <small>{item.count}건</small></span>
          ))}
        </div>
      </div>}

      <div className="company-subsection">
        <h3>주요 수치 출처</h3>
        <div className="company-section-list">
          {KPI_CARDS.map((item) => {
            const metric = insight.latest_metrics?.[item.key] || null;
            return (
              <div key={`source-${item.key}`}>
                <strong>{item.label} · {metricDisplayText(metric)}</strong>
                <SourceLocationList metric={metric} />
                {onShowEvidence && (
                  <button
                    type="button"
                    className="text-button evidence-inline-button"
                    onClick={() => onShowEvidence(buildReportMetricEvidence(insight, `${insight.latest_year}년 ${item.label}`, metric))}
                  >
                    근거보기
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
