# NRB 2023-2025 Source Reconciliation

This note records the source-level reconciliation for NRB's staged standalone audit financial payload.

## Scope

- Company id: `nrb`
- Reporting entity: `주식회사 엔알비`
- Financial scope: standalone financial statements only
- Staging file: `data/company_reports/nrb/staging/audit_financials_2023_2025.json`
- Public View Model impact: none

The attached PDFs were used only as source references. They were not copied into the repository.

## Source Documents

| Source ref | File | Role |
| --- | --- | --- |
| `nrb_annual_report_2026_03_18` | `[엔알비]사업보고서(2026.03.18).pdf` | Primary source for 2025 current-year standalone values and latest 2023-2024 comparative standalone values |
| `nrb_audit_report_2025_04_01` | `[엔알비]감사보고서(2025.04.01).pdf` | Cross-check for 2024 and 2023 comparative values; source for 2023 standalone revenue breakdown |
| `nrb_audit_report_2024_04_08` | `[엔알비]감사보고서(2024.04.08).pdf` | Cross-check for 2023 original values and K-IFRS first adoption emphasis |

## Source Priority

| Year | Primary source | Basis | Cross-checks |
| --- | --- | --- | --- |
| 2023 | `nrb_annual_report_2026_03_18` | Latest comparative standalone statements | `nrb_audit_report_2025_04_01`, `nrb_audit_report_2024_04_08` |
| 2024 | `nrb_annual_report_2026_03_18` | Latest comparative standalone statements | `nrb_audit_report_2025_04_01` |
| 2025 | `nrb_annual_report_2026_03_18` | Current-year standalone statements | none |

## 2023 Current-Liability Reclassification

The 2025-04-01 audit report explains a retrospective K-IFRS 1001 liability classification change. Redeemable convertible preferred-share liabilities exercisable within 12 months after the reporting period are classified as current liabilities.

The staged payload uses the resolved latest comparative 2023 current-liability value:

- `81,185,943,632` KRW

The pre-reclassification amount was:

- `48,527,580,433` KRW

The reclassification effect was:

- `32,658,363,199` KRW

This is no longer treated as an unresolved mismatch or public-promotion blocker.

## 2024 Operating Cash Flow Presentation Change

The 2026-03-18 business report note 2.2.1 explains a retrospective K-IFRS 1008 cash-flow presentation policy change. Cash flows from modular fixed assets held for rental purposes were reclassified between operating and investing cash flows.

The note states that the change affects only the cash-flow statement and does not affect the statement of financial position, income statement, or statement of changes in equity.

For 2024, the note gives the following thousand-KRW table:

| Metric | Before | After | Effect |
| --- | ---: | ---: | ---: |
| Operating cash flow | `(2,611,715)` | `20,142,351` | `22,754,066` |
| Investing cash flow | `(2,956,754)` | `(25,710,820)` | `(22,754,066)` |

The staging file stores the after-policy-change standalone KRW values:

- `operating_cash_flow: 20,142,350,922`
- `investing_cash_flow: -25,710,819,575`

The before-policy-change amount is retained only in the event description as historical evidence. It is not listed in `allowed_cross_check_year_mismatches`.

## Standalone Revenue Breakdown

Standalone revenue breakdown is disclosed in thousand KRW:

- 2023 and 2024: 2025-04-01 audit report note 26.1, p.77
- 2024 and 2025: 2026-03-18 business report note 27.1, p.208

The staging contract converts disclosed thousand-KRW amounts to integer KRW. Because the financial statements carry source values in thousand KRW, the validator allows a maximum `999` KRW rounding difference between revenue and the sum of disclosed revenue components.

| Year | Product | Rental | Service | Construction | Other | Disclosed total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2023 | 14,334,820 | 23,313,498 | 13,381,205 | not applicable | 503,093 | 51,532,616 |
| 2024 | 9,567,358 | 31,289,418 | 11,622,765 | not applicable | 321,520 | 52,801,061 |
| 2025 | 14,800,741 | 24,586,780 | 12,270,351 | 7,667,780 | 155,893 | 59,481,545 |

The schema now allows optional `service_revenue`. Existing companies are not required to provide it.

`goods_revenue` remains `not_applicable` for NRB because no goods-revenue caption is disclosed. It is not filled with zero.

## Modular Attribution

The business description says NRB's revenue arises from modular items, but the revenue breakdown captions themselves are not a separate modular segment disclosure. Product, rental, service, construction, and other revenue are therefore not automatically interpreted as separate modular segment revenue.

## Borrowings Scope

`total_borrowings` remains the common derived sum of:

- short-term borrowings
- current portion of long-term borrowings
- long-term borrowings

Convertible bonds, bonds, derivative liabilities, and redeemable preferred-share liabilities are not added to this borrowing total in this phase.

## Public View Model

This phase does not change public company data. NRB remains excluded from `frontend/public/data/companies/company_report_insights.json`.

The existing public company summary has an operating margin around `7.6%`. The staged standalone audited calculation for 2025 is about `7.5%`. That public summary delta remains documented for a later public-promotion decision.

## Remaining Public Promotion Conditions

NRB can be considered for public financial View Model promotion only after:

- the staging contract is explicitly approved for public use,
- the public summary operating-margin delta is reconciled or documented in the UI copy,
- the standalone/modular attribution wording is approved,
- the staged file passes `scripts/validate_company_audit_financials.py`,
- `scripts/build_company_report_insights.py --check` remains unchanged for existing public companies.
