from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {count}")
    return text.replace(old, new, 1)


builder_path = Path("scripts/build_company_report_insights.py")
builder = builder_path.read_text(encoding="utf-8")
builder = replace_once(
    builder,
    "def build_financial_health(latest_year: int, latest_metrics: dict[str, Any], derived: dict[str, Any], source_summary: dict[str, Any], attribution: dict[str, Any]) -> dict[str, Any]:",
    "def build_financial_health(latest_year: int, latest_metrics: dict[str, Any], latest_series_metrics: dict[str, Any], derived: dict[str, Any], source_summary: dict[str, Any], attribution: dict[str, Any]) -> dict[str, Any]:",
    "financial health signature",
)
builder = replace_once(
    builder,
    '    receivables = latest_metrics.get("receivables_total")\n'
    '    receivables_ratio = latest_derived.get("receivables_to_revenue_pct")\n'
    '    liabilities_ratio = latest_derived.get("liabilities_to_equity_pct")\n'
    '    source_ids = metric_source_refs(revenue) + metric_source_refs(operating_profit)\n'
    '    profitability_status = "additional_confirmation_required" if metric_raw(operating_margin) is None else "watch" if metric_raw(operating_margin) < 0 else "info"\n'
    '    cash_status = "additional_confirmation_required" if metric_raw(operating_cash_flow) is None else "watch" if metric_raw(operating_cash_flow) < 0 and metric_raw(operating_profit) and metric_raw(operating_profit) > 0 else "info"\n'
    '    leverage_status = "additional_confirmation_required" if metric_raw(liabilities_ratio) is None else "watch" if metric_raw(liabilities_ratio) > 200 else "info"\n'
    '    working_capital_status = "additional_confirmation_required" if metric_raw(receivables_ratio) is None else "watch" if metric_raw(receivables_ratio) > 30 else "info"\n'
    '    coverage_status = "watch" if source_summary.get("pending_location_count") else "info"',
    '    receivables = latest_metrics.get("receivables_total")\n'
    '    receivables_ratio = latest_derived.get("receivables_to_revenue_pct")\n'
    '    current_assets = latest_series_metrics.get("current_assets")\n'
    '    current_liabilities = latest_series_metrics.get("current_liabilities")\n'
    '    current_ratio = latest_derived.get("current_ratio_pct")\n'
    '    liabilities_ratio = latest_derived.get("liabilities_to_equity_pct")\n'
    '    source_ids = metric_source_refs(revenue) + metric_source_refs(operating_profit)\n'
    '    profitability_status = "additional_confirmation_required" if metric_raw(operating_margin) is None else "watch" if metric_raw(operating_margin) < 0 else "info"\n'
    '    cash_status = "additional_confirmation_required" if metric_raw(operating_cash_flow) is None else "watch" if metric_raw(operating_cash_flow) < 0 and metric_raw(operating_profit) and metric_raw(operating_profit) > 0 else "info"\n'
    '    leverage_status = "additional_confirmation_required" if metric_raw(liabilities_ratio) is None else "watch" if metric_raw(liabilities_ratio) > 200 else "info"\n'
    '    working_capital_status = "additional_confirmation_required" if metric_raw(current_ratio) is None else "watch" if metric_raw(current_ratio) < 100 else "info"\n'
    '    receivables_burden_status = "additional_confirmation_required" if metric_raw(receivables_ratio) is None else "watch" if metric_raw(receivables_ratio) > 30 else "info"\n'
    '    coverage_status = "watch" if source_summary.get("pending_location_count") else "info"',
    "financial health status split",
)
old_working = '''        "working_capital": health_item(
            working_capital_status,
            "운전자본",
            f"{latest_year}년 채권/매출 비율은 {receivables_ratio.get('display_text') if receivables_ratio else '확인되지 않음'}입니다.",
            ["receivables_total", "receivables_to_revenue_pct"],
            metric_source_refs(receivables),
            rule_id="receivables_to_revenue_observation",
            operator=">",
            threshold=30,
            actual_value=metric_raw(receivables_ratio),
            interpretation_scope="채권/매출 비율이 관찰 기준을 넘는지 표시하며 회수 위험을 단정하지 않습니다.",
            limitation="채권은 감사보고서 주석의 매출채권과 공사미수금 등 공개 항목 합계입니다.",
        ),
'''
new_working = '''        "working_capital": health_item(
            working_capital_status,
            "운전자본",
            f"{latest_year}년 유동비율은 {current_ratio.get('display_text') if current_ratio else '확인되지 않음'}입니다.",
            ["current_assets", "current_liabilities", "current_ratio_pct"],
            metric_source_refs(current_assets) + metric_source_refs(current_liabilities),
            rule_id="current_ratio_liquidity_observation",
            operator="<",
            threshold=100,
            actual_value=metric_raw(current_ratio),
            interpretation_scope="유동자산과 유동부채를 이용해 단기 유동성을 관찰하는 규칙이며 지급능력이나 신용등급을 단정하지 않습니다.",
            limitation="순운전자본은 유동자산에서 유동부채를 차감한 값이며 유동비율과 함께 봅니다.",
        ),
        "receivables_burden": health_item(
            receivables_burden_status,
            "매출채권 부담",
            f"{latest_year}년 채권/매출 비율은 {receivables_ratio.get('display_text') if receivables_ratio else '확인되지 않음'}입니다.",
            ["receivables_total", "receivables_to_revenue_pct"],
            metric_source_refs(receivables),
            rule_id="receivables_to_revenue_observation",
            operator=">",
            threshold=30,
            actual_value=metric_raw(receivables_ratio),
            interpretation_scope="확정된 영업채권/매출 비율을 별도 보조지표로 관찰하며 회수 위험을 단정하지 않습니다.",
            limitation="복합 채권 계정은 주석 분해 전까지 합계에 포함하지 않으며, 정확히 검증된 매출채권·공사미수금만 사용합니다.",
        ),
'''
builder = replace_once(builder, old_working, new_working, "working capital health item")
builder = replace_once(
    builder,
    '''        "financial_health": build_financial_health(
            latest_year,
            latest_metrics,
            derived,
            source_summary,
            source_payload["entity_attribution"],
        ),''',
    '''        "financial_health": build_financial_health(
            latest_year,
            latest_metrics,
            financial_series[-1]["metrics"],
            derived,
            source_summary,
            source_payload["entity_attribution"],
        ),''',
    "financial health call",
)
builder_path.write_text(builder, encoding="utf-8")

panel_path = Path("frontend/src/components/company/CompanyAuditFinancialPanel.jsx")
panel = panel_path.read_text(encoding="utf-8")
panel = replace_once(
    panel,
    '''const KPI_CARDS = [
  { key: "revenue", label: "최근 매출" },
  { key: "operating_profit", label: "영업이익", ratioKey: "operating_margin_pct", ratioLabel: "영업이익률" },
  { key: "operating_cash_flow", label: "영업현금흐름" },
  { key: "total_borrowings", label: "총차입금" },
];''',
    '''const KPI_CARDS = [
  { key: "revenue", label: "최근 매출" },
  { key: "operating_profit", label: "영업이익", ratioKey: "operating_margin_pct", ratioLabel: "영업이익률" },
  { key: "operating_cash_flow", label: "영업현금흐름" },
  { key: "total_borrowings", label: "총차입금" },
];

const FINANCIAL_DECISION_KEYS = [
  "cash_generation",
  "profitability",
  "leverage",
  "working_capital",
];''',
    "explicit decision keys",
)
panel = replace_once(
    panel,
    "function metricDisplayLabel(row, title) {",
    '''function workingCapitalDisplay(insight) {
  const latestYear = insight.latest_year;
  const currentAssets = metricNumber(reportMetricByYear(insight, latestYear, "current_assets"));
  const currentLiabilities = metricNumber(reportMetricByYear(insight, latestYear, "current_liabilities"));
  if (!Number.isFinite(currentAssets) || !Number.isFinite(currentLiabilities)) return "확인되지 않음";
  const value = currentAssets - currentLiabilities;
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString("ko-KR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}억원`;
}

function metricDisplayLabel(row, title) {''',
    "working capital display helper",
)
panel = replace_once(
    panel,
    '''  if (key === "working_capital") return [
    { label: "채권/매출", value: ratio("receivables_to_revenue_pct") },
    { label: "채권", value: amount("receivables_total") },
  ];''',
    '''  if (key === "working_capital") return [
    { label: "순운전자본", value: workingCapitalDisplay(insight) },
    { label: "유동비율", value: ratio("current_ratio_pct") },
  ];
  if (key === "receivables_burden") return [
    { label: "채권/매출", value: ratio("receivables_to_revenue_pct") },
    { label: "채권", value: amount("receivables_total") },
  ];''',
    "working capital rows",
)
panel = replace_once(
    panel,
    '  if (key === "working_capital") return `채권/매출 ${item.threshold ?? 30}% ${item.status === "watch" ? "초과" : "이하"}`;',
    '  if (key === "working_capital") return `유동비율 ${item.threshold ?? 100}% ${item.status === "watch" ? "미만" : "이상"}`;\n  if (key === "receivables_burden") return `채권/매출 ${item.threshold ?? 30}% ${item.status === "watch" ? "초과" : "이하"}`;',
    "working capital criterion",
)
panel = replace_once(
    panel,
    '''          <span><b>운전자본</b><em>채권/매출 비율 30% 초과 → 관찰 필요</em></span>
          <span><b>공시 범위</b><em>수동 확인 필요 출처 1건 이상 → 관찰 필요</em></span>''',
    '''          <span><b>운전자본</b><em>유동비율 100% 미만 → 관찰 필요</em></span>''',
    "status guide rules",
)
panel = replace_once(
    panel,
    "        <p>본 상태는 감사재무를 빠르게 관찰하기 위한 규칙이며 신용등급, 부실판정 또는 투자의견을 의미하지 않습니다.</p>",
    "        <p>본 상태는 감사재무를 빠르게 관찰하기 위한 규칙이며 신용등급, 부실판정 또는 투자의견을 의미하지 않습니다. 매출채권 부담은 별도 보조지표로 표시합니다.</p>",
    "status guide note",
)
panel = replace_once(
    panel,
    '''  const healthItems = Object.entries(insight.financial_health || {});
  const trendItems = Object.values(insight.trends || {}).slice(0, 4);''',
    '''  const healthItems = FINANCIAL_DECISION_KEYS.map((key) => [key, insight.financial_health?.[key]]).filter(([, item]) => item);
  const receivablesBurden = insight.financial_health?.receivables_burden || null;
  const trendItems = Object.values(insight.trends || {}).slice(0, 4);''',
    "decision summary selection",
)
panel = replace_once(
    panel,
    '''      <FinancialStatusGuide />
      <div className="company-intelligence-trend-strip" aria-label="최근 추세 신호">''',
    '''      <FinancialStatusGuide />
      {receivablesBurden && (
        <div className={`company-peer-availability-note ${decisionStatusTone(receivablesBurden.status)}`} role="note" aria-label="매출채권 부담 보조지표">
          <strong>매출채권 부담 · {decisionStatusLabel(receivablesBurden.status)}</strong>
          <span>
            {financialHealthRows(insight, "receivables_burden", receivablesBurden).map((row) => `${row.label} ${row.value}`).join(" · ")}
            {` · ${financialHealthCriterion("receivables_burden", receivablesBurden)}`}
          </span>
          {onShowEvidence && (
            <button type="button" className="text-button evidence-inline-button" onClick={() => onShowEvidence(healthEvidence(insight, receivablesBurden))}>
              계산 근거 보기
            </button>
          )}
        </div>
      )}
      <div className="company-intelligence-trend-strip" aria-label="최근 추세 신호">''',
    "receivables burden auxiliary panel",
)
panel_path.write_text(panel, encoding="utf-8")

test_path = Path("tests/test_company_report_insights.py")
test_text = test_path.read_text(encoding="utf-8")
test_text = replace_once(
    test_text,
    '    assert working_capital["threshold"] == 30\n    assert "단정하지 않습니다" in working_capital["interpretation_scope"]',
    '    assert working_capital["rule_id"] == "current_ratio_liquidity_observation"\n'
    '    assert working_capital["threshold"] == 100\n'
    '    assert "단정하지 않습니다" in working_capital["interpretation_scope"]\n'
    '    receivables_burden = company["financial_health"]["receivables_burden"]\n'
    '    assert receivables_burden["rule_id"] == "receivables_to_revenue_observation"\n'
    '    assert receivables_burden["threshold"] == 30',
    "existing financial health regression",
)
test_path.write_text(test_text, encoding="utf-8")
