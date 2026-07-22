import {
  detailModel,
  formatKrw,
  formatPercent,
  labelValue,
  metricMargin,
  metricValue,
} from "./companyDetailHelpers";

export default function CompanyFinancialTab({ company }) {
  const model = detailModel(company);
  const { financials, latestAudit } = model;
  const extraRows = financials.filter((item) => metricValue(item.net_income) !== null || metricValue(item.operating_cash_flow) !== null);
  const modularRows = financials.filter((item) => item.modular_segment_available && metricValue(item.modular_segment_revenue) !== null);
  const financialUnit = financials[0]?.revenue?.source_unit || financials[0]?.currency || "KRW";
  const auditedLabel = latestAudit?.receipt_number || financials.some((item) => item.audited === true)
    ? "감사보고서 근거 확인"
    : "감사보고서 원문 확인 중";

  return (
    <section className="summary company-tab-panel" id="company-tab-panel-financial" role="tabpanel" aria-labelledby="company-tab-financial">
      <h2>최근 3개년 재무</h2>
      {financials.length ? (
        <>
          <p className="finance-note">
            회사 전체 재무 · {labelValue(latestAudit?.reporting_scope || financials[0]?.reporting_scope || financials[0]?.scope)}
            {" · "}
            {labelValue(latestAudit?.accounting_standard || financials[0]?.accounting_standard)}
            {" · 단위 "}
            {labelValue(financialUnit, financialUnit)}
            {" · "}
            {auditedLabel}
            {latestAudit?.audit_opinion && <> · 감사의견 {labelValue(latestAudit.audit_opinion)}</>}
          </p>
          <div className="company-table-wrap">
            <table className="company-financial-table">
              <thead>
                <tr>
                  <th>연도</th>
                  <th>매출액</th>
                  <th>매출총이익</th>
                  <th>매출총이익률</th>
                  <th>영업이익</th>
                  <th>영업이익률</th>
                </tr>
              </thead>
              <tbody>
                {financials.map((item) => (
                  <tr key={item.year}>
                    <th>{item.year}</th>
                    <td>{formatKrw(metricValue(item.revenue))}</td>
                    <td>{formatKrw(metricValue(item.gross_profit))}</td>
                    <td>{formatPercent(metricMargin(item.gross_profit, item.revenue))}</td>
                    <td>{formatKrw(metricValue(item.operating_profit))}</td>
                    <td>{formatPercent(metricMargin(item.operating_profit, item.revenue))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {extraRows.length > 0 && (
            <div className="company-subsection">
              <h3>추가 재무정보</h3>
              <div className="company-table-wrap">
                <table className="company-financial-table">
                  <thead><tr><th>연도</th><th>순이익</th><th>영업활동현금흐름</th></tr></thead>
                  <tbody>
                    {extraRows.map((item) => (
                      <tr key={`extra-${item.year}`}>
                        <th>{item.year}</th>
                        <td>{formatKrw(metricValue(item.net_income))}</td>
                        <td>{formatKrw(metricValue(item.operating_cash_flow))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {modularRows.length > 0 ? (
            <div className="company-subsection">
              <h3>모듈러 부문 재무</h3>
              <div className="company-section-list">
                {modularRows.map((item) => (
                  <div key={`modular-${item.year}`}>
                    <strong>{item.year}년 모듈러 부문 매출</strong>
                    <span>{formatKrw(metricValue(item.modular_segment_revenue))}</span>
                    {item.modular_segment_revenue_ratio !== null && item.modular_segment_revenue_ratio !== undefined && <span>매출 비중 {formatPercent(item.modular_segment_revenue_ratio)}</span>}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="finance-note">모듈러 부문 별도 재무는 공개자료에서 확인되지 않았습니다.</p>
          )}
        </>
      ) : (
        <p>공개자료에서 확인된 재무정보가 없습니다.</p>
      )}
    </section>
  );
}
