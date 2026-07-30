# PlanM Audit Financials Staging Contract

This note records why PlanM audit financials are stored as a staged common-contract payload before they are allowed into the public `company_report_insights.json` view model.

## Why Staging Is Used

The PlanM source reconciliation matrix is complete enough to validate against `company_audit_financials_v1`, but one 2023 balance-sheet value remains blocked for public application.

The staged file is stored at:

`data/company_reports/planm/staging/audit_financials_2023_2025.json`

The public builder discovers only `data/company_reports/*/*.json`, so this nested staging path is intentionally excluded from the public View Model build.

## `verification_pending`

`verification_pending` means:

- A related amount or comparative value exists in the source documents.
- Additional restatement scope or page-level verification is still required.
- The value is different from `0`, `not_disclosed`, and `not_applicable`.
- The value must remain `reported: null`.
- Derived public calculations must treat the value as unavailable.

The validator allows `verification_pending` only with `reported: null`, `notes`, `source_refs`, and `source_locations`.

## 2023 Total Equity Block

The 2025-04-24 audit report gives 2023 total equity of `20,467,046,841` KRW in the first restated comparative financial statements.

The 2026-06-25 audit report note 23 also includes an additional `777,851,000` KRW opening equity correction for 2024. Until that correction is manually reconciled against the final 2023 closing equity basis, 2023 `total_equity` is stored as:

- `reported: null`
- `disclosure_status: verification_pending`

This prevents the value from being used in public leverage ratios, equity ratios, or trend calculations.

## Source Priority

| Year | Primary Source | Basis | Cross-checks |
| --- | --- | --- | --- |
| 2023 | `planm_audit_report_2025_04_24` | comparative financial statements | 2024-04-15 original report, 2026-06-25 later restatement note |
| 2024 | `planm_audit_report_2026_06_25` | comparative financial statements | 2025-04-24 original 2024 report |
| 2025 | `planm_audit_report_2026_06_25` | current-year financial statements | none |

## Restatement Selection Rules

- 2023 uses the first restated comparative values from the 2025-04-24 audit report.
- 2024 uses the latest restated comparative values from the 2026-06-25 audit report.
- 2025 uses current-year values from the 2026-06-25 audit report.
- The 2024 net asset error correction is `4,306,868,000` KRW decrease to equity.
- The 2024 net income error correction is `3,529,017,000` KRW decrease to net income.
- The requested `3,529,782,000` KRW amount has not been located in the attached PDF text and remains unresolved.

## Tax Effect Treatment

Tax effects are not separately verified from the current PlanM source matrix. Events that need this caveat use:

`tax_effect_status: not_separately_verified`

This must not be interpreted as proof that there is no tax effect.

## Public Application Conditions

PlanM can be moved from staging into the public build only after:

- 2023 `total_equity` is manually reconciled with the 2026-06-25 opening equity correction.
- The unresolved `3,529,782,000` KRW request is resolved or formally rejected.
- Tax effect handling is reviewed and either separately verified or explicitly documented.
- The staged payload passes `scripts/validate_company_audit_financials.py`.
- `scripts/build_company_report_insights.py --check` remains unchanged for existing public companies.

