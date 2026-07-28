import {
  financialScopeLabel,
  latestAuditOpinion,
  metricDisplayText,
  metricToneClass,
  REPORT_AMOUNT_ROWS,
  REPORT_RATIO_ROWS,
  reportFinancialHeading,
  reportMetricByYear,
  reportRatioByYear,
  reportSectionLabel,
  reportYears,
  sourceSectionCounts,
  verificationStatusLabel,
} from "../../companyReportInsights";

const KPI_CARDS = [
  { key: "revenue", label: "최근 매출" },
  { key: "operating_profit", label: "영업이익", ratioKey: "operating_margin_pct", ratioLabel: "영업이익률" },
  { key: "operating_cash_flow", label: "영업현금흐름" },
  { key: "total_borrowings", label: "총차입금" },
  { key: "receivables_total", label: "매출채권 합계" },
];

function latestRatio(insight, key) {
  return insight?.derived_metrics?.[String(insight.latest_year)]?.[key] || null;
}

function formatDate(value) {
  return value || "확인되지 않음";
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

export default function CompanyAuditFinancialPanel({ insight }) {
  const years = reportYears(insight);
  const sourceSummary = insight.source_summary || {};
  const latestOpinion = latestAuditOpinion(insight);
  const sectionCounts = sourceSectionCounts(insight);

  return (
    <>
      <p className="finance-note">
        감사보고서 View Model 기준 3개년 재무입니다. 금액 계산은 `raw_krw`를 기준으로 하고, 화면에는 공개 View Model의 `display_text`를 표시합니다.
      </p>

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
            </div>
          );
        })}
      </div>

      <div className="company-subsection">
        <h3>{reportFinancialHeading(insight)}</h3>
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
      </div>

      <div className="company-subsection">
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
      </div>

      <div className="company-subsection">
        <h3>자동 인사이트</h3>
        <div className="company-report-signal-grid">
          {(insight.trend_signals || []).map((signal) => (
            <article className={`company-report-signal ${signal.level || "info"}`} key={signal.code}>
              <span>{signal.level === "watch" ? "관찰 필요" : "참고"}</span>
              <strong>{signal.title}</strong>
              <p>{signal.description}</p>
            </article>
          ))}
        </div>
      </div>

      <div className="company-subsection">
        <h3>공시 해석 주의사항</h3>
        <div className="company-section-list">
          {(insight.disclosure_warnings || []).map((warning) => (
            <details className="company-report-warning" key={warning.code}>
              <summary>{warning.message}</summary>
              <p>
                이 항목은 {warning.level === "warning" ? "해석상 주의가 필요한 공시 제약" : "검증 보조 안내"}입니다.
                제품매출과 공사매출은 모듈러 매출로 자동 해석하지 않으며, 유창엠앤씨 등 관계사 실적도 유창이앤씨 별도 실적으로 합산하지 않습니다.
              </p>
            </details>
          ))}
        </div>
      </div>

      <div className="company-subsection">
        <h3>출처 요약</h3>
        <dl className="company-report-source-summary">
          <div><dt>재무제표 기준</dt><dd>{financialScopeLabel(insight.financial_scope || insight.attribution?.financial_scope)}</dd></div>
          <div><dt>감사의견</dt><dd>{latestOpinion?.opinion_label_ko || "확인되지 않음"}</dd></div>
          <div><dt>감사인</dt><dd>{latestOpinion?.auditor || sourceSummary.auditors?.join(", ") || "확인되지 않음"}</dd></div>
          <div><dt>최신 보고서 기준일</dt><dd>{formatDate(sourceSummary.latest_report_date)}</dd></div>
          <div><dt>검증된 출처 위치</dt><dd>{sourceSummary.verified_location_count ?? insight.data_quality?.source_location_count ?? "확인되지 않음"}건</dd></div>
          <div><dt>페이지 수동 확인 필요</dt><dd>{sourceSummary.pending_location_count ?? insight.data_quality?.pending_manual_page_check_count ?? "확인되지 않음"}건</dd></div>
        </dl>
        <p className="finance-note">{insight.attribution?.attribution_warning}</p>
      </div>

      <div className="company-subsection">
        <div className="company-subsection-heading">
          <h3>출처 섹션 표시</h3>
          <span>코드는 UI에서 한국어로 변환됩니다.</span>
        </div>
        <div className="company-report-section-tags">
          {sectionCounts.map((item) => (
            <span key={item.section}>{item.label} <small>{item.count}건</small></span>
          ))}
        </div>
      </div>

      <div className="company-subsection">
        <h3>주요 수치 출처</h3>
        <div className="company-section-list">
          {KPI_CARDS.map((item) => {
            const metric = insight.latest_metrics?.[item.key] || null;
            return (
              <div key={`source-${item.key}`}>
                <strong>{item.label} · {metricDisplayText(metric)}</strong>
                <SourceLocationList metric={metric} />
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
