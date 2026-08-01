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
| `nrb_audit_report_2025_04_01` | `[엔알비]감사보고서(2025.04.01).pdf` | Cross-check for 2024 and 2023 comparative values |
| `nrb_audit_report_2024_04_08` | `[엔알비]감사보고서(2024.04.08).pdf` | Cross-check for 2023 original values and K-IFRS first adoption emphasis |

## Source Priority

| Year | Primary source | Basis | Cross-checks |
| --- | --- | --- | --- |
| 2023 | `nrb_annual_report_2026_03_18` | Latest comparative standalone statements | `nrb_audit_report_2025_04_01`, `nrb_audit_report_2024_04_08` |
| 2024 | `nrb_annual_report_2026_03_18` | Latest comparative standalone statements | `nrb_audit_report_2025_04_01` |
| 2025 | `nrb_annual_report_2026_03_18` | Current-year standalone statements | none |

## 2023 Current-Liability Restatement

The staged payload uses the latest comparative 2023 current-liability value from the 2026-03-18 business report:

- `81,185,943,632` KRW

The 2024-04-08 audit report shows the earlier current-liability classification:

- `48,527,580,433` KRW

The earlier value is retained only as cross-check evidence. It is not used as the staged reported value.

## 2024 Operating Cash Flow Mismatch

The 2025-04-01 audit report shows 2024 operating cash flow as:

- `-2,611,715,083` KRW

The 2026-03-18 business report latest standalone comparative cash-flow statement shows 2024 operating cash flow as:

- `20,142,350,922` KRW

The staging file uses the latest comparative value and preserves the earlier amount in `allowed_cross_check_year_mismatches`. The source documents do not yet provide enough explanation to treat the mismatch as resolved for public promotion.

## Standalone and Consolidated Guard

The 2026-03-18 business report includes consolidated disclosures and a consolidated revenue breakdown table. Those values are not copied into `financial_years`.

The staging payload intentionally keeps standalone revenue breakdown fields as:

- `reported: null`
- `disclosure_status: not_disclosed`

This prevents product, rental, service, construction, or other revenue labels in the consolidated table from being interpreted as standalone modular revenue.

## Borrowings Scope

`total_borrowings` remains the common derived sum of:

- short-term borrowings
- current portion of long-term borrowings
- long-term borrowings

Convertible bonds, bonds, derivative liabilities, and redeemable preferred-share liabilities are not added to this borrowing total in this phase.

## Existing Public Summary Difference

The existing public company summary has an operating margin around `7.6%`. The staged standalone audited calculation for 2025 is about `7.5%`.

This phase does not change public company data. The difference is recorded as a public-promotion blocker.

## Promotion Blockers

NRB should not be promoted into `frontend/public/data/companies/company_report_insights.json` until:

- the 2024 operating cash-flow mismatch is reviewed and resolved or explicitly accepted,
- the 2023 current-liability restatement is reviewed for presentation scope,
- the standalone/consolidated revenue scope guard is accepted,
- public summary differences are reconciled or documented,
- the staged file passes `scripts/validate_company_audit_financials.py`.
