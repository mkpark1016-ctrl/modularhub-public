# NRB audit financial public promotion

Phase 6E-1B promotes NRB's 2023-2025 standalone audit financial contract into the public company report insight View Model.

## Promotion path

- From: `data/company_reports/nrb/staging/audit_financials_2023_2025.json`
- To: `data/company_reports/nrb/audit_financials_2023_2025.json`
- Public View Model: `frontend/public/data/companies/company_report_insights.json`

The staging input file is removed after promotion so the public builder discovers exactly one NRB audit-financial source.

## Public company count

The public audit-financial View Model now includes five companies:

- `daeseung-engineering`
- `kumkang-kind`
- `nrb`
- `planm`
- `yuchang-enc`

Existing four public audit-financial company outputs are preserved byte-for-byte.

## Audited 2025 NRB values

NRB is shown on a standalone financial-statement basis.

- Revenue: `59,481,544,678` KRW
- Operating profit: `4,461,258,309` KRW
- Net income: `-563,349,199` KRW
- Operating cash flow: `3,068,742,998` KRW
- Operating margin: `7.5%`

The previous public company summary rounded revenue and operating profit, producing an operating margin of about `7.6%`. NRB's public summary financials now use the audited standalone values from the structured audit financial contract, and the financial detail tab uses the same View Model.

## `service_revenue` handling

NRB has a standalone revenue breakdown with product, rental, service, construction, and other revenue captions. The public builder emits:

- `service_revenue`
- `service_revenue_share_pct`

Only companies with a `service_revenue` source field receive the optional service revenue fields. Existing public audit-financial companies without that source field are not backfilled with null service revenue metrics.

`goods_revenue` remains `not_applicable` for NRB. Construction revenue is `not_applicable` for 2023 and 2024 and is not displayed as zero.

## Retrospective presentation and classification notes

NRB's public UI includes source-backed interpretation notes for:

- 2023 current-liability retrospective classification under K-IFRS 1001.
- 2024 operating cash-flow retrospective presentation change under K-IFRS 1008.
- Standalone revenue breakdown amounts disclosed in thousand KRW and converted to integer KRW.
- Revenue breakdown captions not being interpreted as separate modular segment revenue.

## Protected data diff

Intentional public data changes:

- `frontend/public/data/companies/company_report_insights.json`
- `frontend/public/data/companies/companies.json` NRB financial summary only

Unchanged public data:

- `frontend/public/data/companies/company_intelligence_v2.json`
- `frontend/public/data/news.json`
- `frontend/public/data/business.json`
- `frontend/public/data/meta.json`

PDF source files are not copied into the repository or public build.
