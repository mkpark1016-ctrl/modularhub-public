# Daeseung Engineering Company Report View Model Diff

## Added Public View Model Entry

`frontend/public/data/companies/company_report_insights.json` now includes `daeseung-engineering` alongside the existing `kumkang-kind` and `yuchang-enc` entries. The common builder discovers the new source JSON from `data/company_reports/daeseung-engineering/audit_financials_2023_2025.json`; no company-specific frontend loader or JSX branch was added.

## Public Metrics

- Latest year: 2025.
- Latest revenue: 616.6억원.
- Latest operating profit: 63.7억원.
- Latest operating cash flow: -3.5억원.
- Latest total borrowings: 531.6억원.
- Latest receivables total: 34.2억원.
- 2025 rental revenue share: 40.7%.

## Source Quality

- Source locations: 84.
- Verified source locations: 84.
- Pending manual page checks: 0.
- Auditor report dates are present for all three source documents.

## Existing Company Preservation

The generated `yuchang-enc` and `kumkang-kind` View Model entries are tested against `origin/main` so the Daeseung addition does not change existing public financial insight payloads.

## UI Expectations

The existing `CompanyAuditFinancialPanel` should render Daeseung automatically because it reads `company_report_insights.json` by `company_id`. Companies without report insights, such as `gs-ec`, continue to use the legacy financial fallback.
