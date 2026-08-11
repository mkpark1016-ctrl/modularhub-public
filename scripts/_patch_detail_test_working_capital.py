from pathlib import Path

path = Path("frontend/scripts/test-company-detail-ui.mjs")
text = path.read_text(encoding="utf-8")
old = 'assert.equal(yuchangReport.financial_health.working_capital.threshold, 30);'
new = '''assert.equal(yuchangReport.financial_health.working_capital.rule_id, "current_ratio_liquidity_observation");
assert.equal(yuchangReport.financial_health.working_capital.threshold, 100);
assert.equal(yuchangReport.financial_health.receivables_burden.rule_id, "receivables_to_revenue_observation");
assert.equal(yuchangReport.financial_health.receivables_burden.threshold, 30);'''
if text.count(old) != 1:
    raise SystemExit(f"expected exactly one stale working-capital assertion, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
