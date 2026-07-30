# PlanM 2023 Equity And Restatement Reconciliation

## Purpose

This note manually reconciles the PlanM 2023 total equity staging block against the three attached audit reports without copying the PDFs into the repository. The goal is to decide whether `data/company_reports/planm/staging/audit_financials_2023_2025.json` can be promoted to public View Model input, and whether the requested `3,529,782,000 KRW` restatement difference is supported by the PDF text.

## Source Priority

| Source ref | Attached PDF | Role in this reconciliation |
| --- | --- | --- |
| `planm_audit_report_2024_04_15` | `[플랜엠]감사보고서(2024.04.15).pdf` | Original 2023 financial statements and cross-check only. |
| `planm_audit_report_2025_04_24` | `[플랜엠]감사보고서(2025.04.24).pdf` | Primary source for the first restated 2023 comparative financial statements. |
| `planm_audit_report_2026_06_25` | `[플랜엠]감사보고서(2026.06.25).pdf` | Latest source for 2024/2025 and note 23 cross-check evidence affecting 2024 opening equity. |

## 2023 Total Equity Reconciliation

| Category | Source report | Page or page range | Note | Original line item | Original amount | Unit | Sign | Applies to | Opening or closing amount | Error correction or accounting policy | Included in final 2023 closing total equity | Determination | Verification status |
| --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- |
| Original 2023 total equity | `planm_audit_report_2024_04_15` | p.8, p.11 | Financial statements | Total equity / capital change table closing total | 28,620,984,386 | KRW | positive | 2023 | Closing | Original reported amount | No, superseded by first restated comparative statements | Historical baseline only | verified section range |
| First restated 2023 total equity | `planm_audit_report_2025_04_24` | p.8, p.11, p.43 | Restated comparative financial statements and restatement note | Total equity | 20,467,046,841; p.43 rounds to 20,467,047 thousand KRW | KRW / thousand KRW | positive | 2023 | Closing and 2024 opening comparison | Error correction already reflected in first restated statements | Candidate basis, but public application remains blocked | Keep staging `reported: null`, `disclosure_status: verification_pending` | verified section range |
| 2024 opening equity cross-check | `planm_audit_report_2026_06_25` | p.11, p.48, p.50 | Note 23 | 2024 opening retained earnings / total equity adjustments | 768,975 thousand KRW + 8,876 thousand KRW = 777,851,000 KRW | thousand KRW components, normalized to KRW | negative | 2024 opening, related to 2023 closing cross-check | Opening adjustment | Error correction effect; separated from accounting policy effect | Not directly applied to 2023 closing total equity without an explicit final 2023 table | Preserve as blocking unresolved cross-check item | verified section range |
| 2024 opening accounting policy effect | `planm_audit_report_2026_06_25` | p.48, p.50 | Note 23 | 2024 opening retained earnings / total equity policy change | 11,995,176 thousand KRW | thousand KRW | positive | 2024 opening | Opening adjustment | Accounting policy change, not an error correction | Not included in 2023 total equity calculation | Keep separate from error correction | verified section range |

## Determination On 777,851,000 KRW

The `777,851,000 KRW` amount is supported only as the sum of two explicit note 23 error-correction components in the 2026 report:

- `768,975 thousand KRW`
- `8,876 thousand KRW`

The same note also shows a separate `11,995,176 thousand KRW` accounting policy change effect. Because the 2026 report presents these as 2024 opening retained earnings / equity adjustments, not as an explicit final 2023 closing total equity table, the staging data must not add or subtract `777,851,000 KRW` from `20,467,046,841 KRW` to create a new public 2023 total equity amount.

Final status for `financial_years.2023.balance_sheet.total_equity`:

- `reported`: `null`
- `disclosure_status`: `verification_pending`
- Public View Model eligibility: blocked
- Reason: the final 2023 closing total equity basis is not independently disclosed after the 2026 note 23 cross-check components.

## Determination On 3,529,782,000 KRW

The requested `3,529,782,000 KRW` amount was searched as:

- `3,529,782`
- `3529782`
- KRW and thousand-KRW interpretations
- comma and no-comma forms
- targeted pages for note 23 and the restatement tables
- the full text extraction of the three attached PDFs

The amount was not found. Its status remains `unsupported_requested_amount`, and public application is blocked.

The PDF-supported 2024 net income error correction remains:

- `3,497,470 thousand KRW`
- `31,547 thousand KRW`
- combined explicit component value: `3,529,017,000 KRW`

This value is retained as the source-supported restatement amount. It must not be replaced by `3,529,782,000 KRW` unless a later source directly supports that number.

## Tax Effect Handling

The reviewed pages do not separately disclose a tax effect for these restatement components. The staging status remains:

- `tax_effect_status`: `not_separately_verified`

No tax effect is inferred, calculated, or stored as zero.

## Public Application

This reconciliation does not change:

- `frontend/public/data/companies/company_report_insights.json`
- `frontend/public/data/companies/companies.json`
- `frontend/public/data/companies/company_intelligence_v2.json`
- `frontend/public/data/news.json`
- `frontend/public/data/business.json`
- any UI route or component

The current staging decision is:

- PlanM 2023 total equity stays `verification_pending`.
- `777,851,000 KRW` stays a blocking cross-check item, not an automatic adjustment.
- `3,529,782,000 KRW` stays unsupported.
- `3,529,017,000 KRW` stays the PDF-supported 2024 net income error-correction amount.
- Accounting policy change effects and error-correction effects remain separated.

## Remaining Unresolved Items

| Item | Status | Public blocker | Next check |
| --- | --- | --- | --- |
| Final 2023 closing total equity after 2026 note 23 cross-check | `verification_pending` | Yes | Locate an explicit final 2023 closing total equity table or official restated 2023 statement. |
| Requested `3,529,782,000 KRW` | `unsupported_requested_amount` | No, because it is not applied | Locate a direct source if this number came from another document. |
| Tax effect by restatement component | `not_separately_verified` | No | Use only if separately disclosed in source. |

