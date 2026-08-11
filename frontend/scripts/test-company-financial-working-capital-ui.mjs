import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const panel = fs.readFileSync(path.join(root, 'src/components/company/CompanyAuditFinancialPanel.jsx'), 'utf8');
const payload = JSON.parse(fs.readFileSync(path.join(root, 'public/data/companies/company_report_insights.json'), 'utf8'));

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(panel.includes('const FINANCIAL_DECISION_KEYS = ['), 'financial decision keys must be explicit');
for (const key of ['cash_generation', 'profitability', 'leverage', 'working_capital']) {
  assert(panel.includes(`"${key}"`), `decision key missing: ${key}`);
}
assert(panel.includes('순운전자본'), 'working-capital card must show net working capital');
assert(panel.includes('유동비율'), 'working-capital card must show current ratio');
assert(panel.includes('receivables_burden'), 'receivables burden must remain as auxiliary insight');
assert(panel.includes('유동비율 100% 미만 → 관찰 필요'), 'status guide must describe the current-ratio rule');
assert(!panel.includes('<span><b>공시 범위</b><em>수동 확인 필요 출처 1건 이상 → 관찰 필요</em></span>'), 'disclosure coverage must not appear as a primary financial decision criterion');

const byId = new Map(payload.companies.map((company) => [company.company_id, company]));
const gs = byId.get('gs-ec');
const hyundai = byId.get('hyundai-engineering');
assert(gs?.financial_health?.working_capital?.rule_id === 'current_ratio_liquidity_observation', 'GS working capital must use current-ratio semantics');
assert(gs?.financial_health?.receivables_burden?.status === 'additional_confirmation_required', 'GS composite receivables must remain pending');
const hyundaiBurden = hyundai?.financial_health?.receivables_burden?.actual_value;
assert(Number.isFinite(hyundaiBurden) && Math.round(hyundaiBurden * 10) / 10 === 28.7, 'Hyundai reconciled receivables burden should display as 28.7%');

console.log('company financial working-capital UI contract: PASS');
