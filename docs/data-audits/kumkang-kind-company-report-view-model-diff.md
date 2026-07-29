# Kumkang Kind Company Report View Model Diff

## Summary

- Input companies before change: 1
- Input companies after change: 2
- Generated companies before change: 1
- Generated companies after change: 2
- Added company: `kumkang-kind`
- Existing company preserved: `yuchang-enc`

## Reuse Checks

- Source schema changed: no
- Validator changed: no
- Builder changed: no
- UI JSX changed: no
- CSS changed: no
- Company-specific UI branch added: no
- Existing fallback financial UI changed: no

## Generated Public Data

Changed public View Model:

- `frontend/public/data/companies/company_report_insights.json`

Protected public data unchanged:

- `frontend/public/data/companies/companies.json`
- `frontend/public/data/companies/company_intelligence_v2.json`
- `frontend/public/data/news.json`
- `frontend/public/data/business.json`
- `frontend/public/data/meta.json`

## YooChang Regression

Semantic comparison of the `yuchang-enc` item in `company_report_insights.json` before and after generation: 0 changes.

## Kumkang Kind View Model

- Company ID: `kumkang-kind`
- Available years: 2023, 2024, 2025
- Financial scope: consolidated
- Latest revenue: 802,156,014,802 KRW, displayed as 8,021.6억원
- 2025 operating margin: 1.3%
- 2025 net income: -37,353,541,440 KRW
- Operating cash flow sign: positive for 2023, 2024, and 2025
- Source locations: 84
- Verified source locations: 0
- Pending manual page checks: 84

## Generalization Result

The existing `company_audit_financials_v1` source schema, validator, `company_report_insights_v1` builder, and company financial tab loader generated and consumed a second company without company-specific UI code. No JSX or CSS changes were required for this data addition.
