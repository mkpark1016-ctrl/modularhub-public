# Kumkang Kind 2023-2025 Company Report Financial Audit

## Scope

This audit adds consolidated financial statement data for `kumkang-kind` using the existing `company_audit_financials_v1` schema. The source documents are business reports containing audited financial statements, not standalone audit reports.

## Source Documents

- `[금강공업]사업보고서(2026.03.12).pdf`: 47th period, primary source for 2025 and cross-check source for comparative 2024/2023 values.
- `[금강공업][정정]사업보고서(2025.03.19).pdf`: 46th period corrected business report, primary source for 2024 and cross-check source for 2023.
- `[금강공업]사업보고서(2024.03.14).pdf`: 45th period business report, primary source for 2023.

The PDF files were not copied into the repository. The local attachment paths were not available in this worktree during implementation, so page-level locations remain `pending_manual_page_check`. Official KRX/DART HTML disclosures were used to cross-check the reported won amounts and auditor tables where accessible.

## Financial Statement Basis

- Financial scope: consolidated financial statements.
- Accounting standard: K-IFRS.
- Currency and unit: KRW integer won.
- 2024 source priority: the corrected 2025-03-19 business report is preferred over the original 2025-03-13 filing.
- 2023 source priority: the 2024-03-14 business report is primary; later comparative disclosures are cross-checks.

## Metrics Entered

- Income statement: revenue, gross profit, operating profit, net income.
- Balance sheet: total assets, current assets, total liabilities, current liabilities, total equity.
- Cash flow: operating, investing, financing cash flow, ending cash.
- Revenue breakdown: customer-contract revenue and rental revenue are preserved within existing generic fields.
- Working capital: trade receivables gross, other receivables gross for the common receivables total calculation, inventory, work in progress.
- Borrowings: short-term borrowings, current portion of long-term borrowings and bonds, non-current borrowings including bonds and convertible bonds.
- Investment signals: construction in progress, other intangible assets, research and development expense.

## Checkpoints

| Year | Revenue | Gross Profit | Operating Profit | Net Income | Operating Cash Flow | Total Borrowings | Trade Receivables Gross | Receivables Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2023 | 856,892,700,510 | 158,067,345,706 | 66,582,089,210 | 44,788,076,295 | 49,382,174,440 | 465,321,329,651 | 142,670,856,935 | 194,543,903,760 |
| 2024 | 801,352,012,454 | 126,755,039,109 | 33,048,202,059 | 16,844,230,742 | 13,010,958,488 | 502,257,459,579 | 154,093,751,180 | 212,687,664,676 |
| 2025 | 802,156,014,802 | 122,216,321,060 | 10,497,395,028 | -37,353,541,440 | 21,874,636,165 | 513,762,323,953 | 150,430,873,249 | 185,921,585,924 |

## Audit Information

| Year | Auditor | Opinion | Key Audit Matter |
| --- | --- | --- | --- |
| 2023 | 안경회계법인 | 적정의견 | 매출채권의 손상 |
| 2024 | 안경회계법인 | 적정의견 | 매출채권의 손상 |
| 2025 | 안경회계법인 | 적정의견 | 현금창출단위 손상검사 |

## Receivables Distinction

`trade_receivables_gross` stores gross trade receivables before allowance. The public View Model's `receivables_total` is calculated separately from trade receivables plus the other receivables gross amount needed by the current common schema. This prevents treating the broader receivables total as trade receivables.

## Modular Disclosure Limits

The business reports disclose modular revenue and Jincheon modular production performance amounts, but the existing schema has no generic supplemental metric slot for those values. They were not stored as financial statement metrics.

- 2023 modular revenue: 8,855,591,531 KRW, about 1.0% of revenue.
- 2024 modular revenue: 7,549,989,904 KRW, about 0.9% of revenue.
- 2025 modular revenue: 13,810,025,029 KRW, about 1.7% of revenue.
- Jincheon modular production performance disclosed amount: 11,591 million KRW in 2023, 9,764 million KRW in 2024, and 15,909 million KRW in 2025.

These are not module counts. Product and service revenue, rental revenue, and consolidated revenue are not modular revenue.

## Pending Manual Page Checks

All 84 source locations are present but marked `pending_manual_page_check` because the local PDFs named in the task were not readable from the workspace. The values were cross-checked against official disclosure HTML, but page numbers should be confirmed from the PDFs before upgrading any location to `verified` or `verified_section_range`.

## Deferred Items

- Cost of sales, profit before tax, non-current assets, non-current liabilities, cash and short-term financial assets, net debt, debt ratio, gearing ratio, and allowance for doubtful accounts are not represented as source metrics because the current `company_audit_financials_v1` schema does not expose those fields.
- Modular production capacity and production performance are documented above but not stored in the source JSON because the current schema has no supplemental metric container.
- The Boeun factory purchase contract is recorded only as a post-balance-sheet special event and is not treated as an operating modular production facility.
