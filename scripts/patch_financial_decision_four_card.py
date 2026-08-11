#!/usr/bin/env python3
from pathlib import Path

component_path = Path("frontend/src/components/company/CompanyAuditFinancialPanel.jsx")
css_path = Path("frontend/src/companyUiOverrides.css")

component = component_path.read_text(encoding="utf-8")
css = css_path.read_text(encoding="utf-8")

old_config = '''const FINANCIAL_DECISION_KEYS = [
  "cash_generation",
  "profitability",
  "leverage",
  "working_capital",
];'''
new_config = '''const FINANCIAL_DECISION_CONFIG = [
  { key: "cash_generation", label: "현금창출력" },
  { key: "profitability", label: "수익성" },
  { key: "leverage", label: "재무안정성" },
  { key: "working_capital", label: "운전자본" },
];'''
if old_config in component:
    component = component.replace(old_config, new_config, 1)
elif new_config not in component:
    raise SystemExit("decision config block not found")

old_health = '  const healthItems = FINANCIAL_DECISION_KEYS.map((key) => [key, insight.financial_health?.[key]]).filter(([, item]) => item);'
new_health = '''  const healthItems = FINANCIAL_DECISION_CONFIG.map(({ key, label }) => [
    key,
    insight.financial_health?.[key] || {
      headline: label,
      status: "additional_confirmation_required",
      actual_value: null,
      threshold: null,
      metric_ids: [],
      source_ids: [],
    },
  ]);'''
if old_health in component:
    component = component.replace(old_health, new_health, 1)
elif new_health not in component:
    raise SystemExit("healthItems block not found")

old_article = '          <article className={`company-intelligence-card financial-decision-card ${decisionStatusTone(item.status)}`} key={key}>'
new_article = '          <article className={`company-intelligence-card financial-decision-card ${decisionStatusTone(item.status)}`} data-financial-factor={key} key={key}>'
if old_article in component:
    component = component.replace(old_article, new_article, 1)
elif new_article not in component:
    raise SystemExit("decision article block not found")

old_rules = '''          <span><b>수익성</b><em>영업이익률 0% 미만 → 관찰 필요</em></span>
          <span><b>현금창출력</b><em>영업이익 양수 + 영업현금흐름 음수 → 관찰 필요</em></span>
          <span><b>재무안정성</b><em>부채비율 200% 초과 → 관찰 필요</em></span>
          <span><b>운전자본</b><em>유동비율 100% 미만 → 관찰 필요</em></span>'''
new_rules = '''          <span><b>현금창출력</b><em>영업이익 양수 + 영업현금흐름 음수 → 관찰 필요</em></span>
          <span><b>수익성</b><em>영업이익률 0% 미만 → 관찰 필요</em></span>
          <span><b>재무안정성</b><em>부채비율 200% 초과 → 관찰 필요</em></span>
          <span><b>운전자본</b><em>유동비율 100% 미만 → 관찰 필요</em></span>'''
if old_rules in component:
    component = component.replace(old_rules, new_rules, 1)
elif new_rules not in component:
    raise SystemExit("status guide block not found")

stale_cards = '''/* Serialized JSON order is cash generation, disclosure coverage, leverage, profitability, working capital. */
.financial-decision-grid .financial-decision-card:nth-child(1) { order: 1; }
.financial-decision-grid .financial-decision-card:nth-child(2) { display: none; }
.financial-decision-grid .financial-decision-card:nth-child(3) { order: 3; }
.financial-decision-grid .financial-decision-card:nth-child(4) { order: 2; }
.financial-decision-grid .financial-decision-card:nth-child(5) { order: 4; }

'''
if stale_cards in css:
    css = css.replace(stale_cards, "", 1)
elif "financial-decision-card:nth-child" in css:
    raise SystemExit("unexpected decision-card nth-child rules remain")

stale_rules = '''.financial-status-rule-grid span:nth-child(1) { order: 2; }
.financial-status-rule-grid span:nth-child(2) { order: 1; }
.financial-status-rule-grid span:nth-child(3) { order: 3; }
.financial-status-rule-grid span:nth-child(4) { order: 4; }
.financial-status-rule-grid span:nth-child(5) { display: none; }

'''
if stale_rules in css:
    css = css.replace(stale_rules, "", 1)
elif "financial-status-rule-grid span:nth-child" in css:
    raise SystemExit("unexpected status-rule nth-child rules remain")

component_path.write_text(component, encoding="utf-8")
css_path.write_text(css, encoding="utf-8")
print("patched financial four-card contract")
