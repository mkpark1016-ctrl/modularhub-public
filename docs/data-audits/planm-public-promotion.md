# PlanM Public Financial Promotion

## Purpose

This document records the controlled public promotion of PlanM audit-report financial data from the staging contract into the public company report insight pipeline.

## Public Years

PlanM is now included in `frontend/public/data/companies/company_report_insights.json` with:

- 2023
- 2024
- 2025

The source input is:

- `data/company_reports/planm/audit_financials_2023_2025.json`

The previous staging-only path is no longer used as the public builder input.

## Published Metrics

Verified financial statement metrics are published through the common audit financial View Model. The public UI uses the same company detail financial tab used for Yuchang E&C, Kumkang Kind, and Daeseung Engineering.

PlanM 2024 and 2025 verified metrics are available for normal trend and ratio display. PlanM 2023 revenue, profit, cash-flow, borrowings, receivables, inventory, and related verified metrics remain available where directly supported by the source contract.

## Verification Pending Item

PlanM 2023 `balance_sheet.total_equity` remains:

- `reported`: `null`
- `disclosure_status`: `verification_pending`
- public display: `검증 보류`

Reason:

The 2026 audit report note 23 shows a 2024 opening equity cross-check adjustment, but it does not independently disclose a final 2023 closing total equity table after that cross-check. The public View Model therefore keeps the value visible as pending rather than deriving a new number.

## Derived Metrics Excluded From Calculation

Because 2023 total equity is verification-pending, these PlanM 2023 derived metrics remain `null`:

- `liabilities_to_equity_pct`
- `borrowings_to_equity_pct`

The public JSON and UI must not display these as:

- `0%`
- `Infinity`
- `NaN`
- a literal `None` string

## Restatement Cautions

The public disclosure warnings preserve these limits:

- The 2023 financial statements have restatement history.
- The 2023 total equity connection remains verification-pending.
- `3,529,017,000 KRW` is retained as the 2024 net income error-correction component total supported by PDF components.
- Accounting policy change effects and error-correction effects are separated.
- Tax effects are not separately verified.
- `3,529,782,000 KRW` is not used in public JSON, UI display, or calculation because it was not found in the reviewed PDF evidence.

## Modular Revenue Disclosure Limit

PlanM financial information is standalone financial-statement data. The audit reports do not separately disclose modular segment revenue.

The public UI must state that:

- product revenue is not automatically modular revenue
- rental revenue is not automatically modular revenue
- service and F&B revenue are not automatically modular revenue

## Source Drawer

PlanM financial metrics keep source locations for the common evidence drawer. For 2023 total equity, the drawer must show both:

- `planm_audit_report_2025_04_24`, page range `7-8`, `statement.balance_sheet`
- `planm_audit_report_2026_06_25`, page range `48,50`, `note.restatement`

These locations are displayed as evidence for the pending status and cross-check basis, not as a completed final public total equity amount.

## Existing Company Impact

No amounts are changed for:

- `yuchang-enc`
- `kumkang-kind`
- `daeseung-engineering`

Companies without audit report insights continue to use the legacy financial fallback UI.

## Public View Model Changes

Expected public View Model change:

- PlanM is added as one additional company in `frontend/public/data/companies/company_report_insights.json`.

Expected unchanged files:

- `frontend/public/data/companies/companies.json`
- `frontend/public/data/companies/company_intelligence_v2.json`
- `frontend/public/data/news.json`
- `frontend/public/data/business.json`
- `frontend/public/data/meta.json`

## Remaining Unresolved Items

| Item | Status | Public behavior |
| --- | --- | --- |
| 2023 final closing total equity after the 2026 note 23 cross-check | `verification_pending` | Display as pending and exclude equity-based ratios. |
| Requested `3,529,782,000 KRW` amount | `unsupported_requested_amount` | Do not expose or calculate from it. |
| Restatement tax effect | `not_separately_verified` | Do not infer or zero-fill. |

