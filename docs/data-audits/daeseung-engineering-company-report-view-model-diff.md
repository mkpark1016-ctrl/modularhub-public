# Daeseung Engineering Company Report View Model Diff

## Added Public View Model Entry

`frontend/public/data/companies/company_report_insights.json` includes `daeseung-engineering` alongside the existing `kumkang-kind` and `yuchang-enc` entries. The common builder discovers the source JSON from `data/company_reports/daeseung-engineering/audit_financials_2023_2025.json`; no company-specific frontend loader or JSX branch was added.

## Public Metrics

- Latest year: 2025.
- Latest revenue: 616.6 eok KRW in the public UI display unit.
- Latest operating profit: 63.7 eok KRW.
- Latest operating cash flow: -3.5 eok KRW.
- Latest total borrowings: 531.6 eok KRW.
- Latest receivables total: 34.2 eok KRW.
- 2025 rental revenue share: 40.7%.

## Source Priority Impact

- FY2023 public `source_priority_by_year.cross_check_source_refs` now includes only the 2024-09-19 report.
- FY2025 is excluded from FY2023 cross-checks because its `covered_years` are FY2025 and FY2024.
- FY2024 still uses the 2025-09-17 report as a valid cross-check.

## Industrial Property Rights Impact

The source schema and builder now support explicit disclosure status semantics. Daeseung has no `not_disclosed` industrial property rights records after the PDF re-check:

- FY2023: reported zero.
- FY2024: reported zero, supported by the 2025 comparative balance sheet.
- FY2025: reported 3,417,840 KRW.

Actual zero values remain zero in the source JSON and View Model plumbing. Future null values are represented as `raw_krw: null`, `display_text: "제공되지 않음"`, and are not converted to zero.

## Source Quality

- Source locations: 84.
- Verified source locations: 84.
- Pending manual page checks: 0.
- Auditor report dates are present for all three source documents.

## Existing Company Preservation

The generated `yuchang-enc` and `kumkang-kind` View Model entries are tested against `origin/main` so the Daeseung corrections and common schema additions do not change existing public financial insight payloads.

## UI Expectations

The existing `CompanyAuditFinancialPanel` renders Daeseung automatically because it reads `company_report_insights.json` by `company_id`. Companies without report insights, such as `gs-ec`, continue to use the legacy financial fallback.
