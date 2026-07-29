# Kumkang Kind 2023-2025 Company Report Financial Audit

## Scope

This audit adds consolidated financial statement data for `kumkang-kind` using the existing `company_audit_financials_v1` schema. The source documents are business reports containing audited financial statements, not standalone audit reports.

## Source Documents

- `[금강공업]사업보고서(2026.03.12).pdf`: 47th period, primary source for 2025 and cross-check source for comparative 2024/2023 values.
- `[금강공업][정정]사업보고서(2025.03.19).pdf`: 46th period corrected business report, primary source for 2024 and cross-check source for 2023.
- `[금강공업]사업보고서(2024.03.14).pdf`: 45th period business report, primary source for 2023.

The PDF files were not copied into the repository. Source page ranges were checked against the user-provided local PDFs for this follow-up pass, and all 84 source locations were upgraded to `verified_section_range` without changing reported won amounts.

## Financial Statement Basis

- Financial scope: consolidated financial statements.
- Accounting standard: K-IFRS.
- Currency and unit: KRW integer won.
- 2024 source priority: the corrected 2025-03-19 business report is preferred over the original 2025-03-13 filing.
- 2023 source priority: the 2024-03-14 business report is primary; the 2025-03-19 corrected report and 2026-03-12 report are cross-checks.

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

`report_date` is the business report submission date. A separate independent auditor report date was not located in the attached business report PDFs, so `auditor_report_date` is stored as `null` with `auditor_report_date_verification_status: not_located_in_attached_business_report_pdf`. The corrected business report submission date is not copied into `auditor_report_date`.

## Receivables Distinction

`trade_receivables_gross` stores gross trade receivables before allowance. The public View Model's `receivables_total` is calculated separately from trade receivables plus the other receivables gross amount needed by the current common schema. This prevents treating the broader receivables total as trade receivables.

## Modular Disclosure Limits

The business reports disclose modular revenue and Jincheon modular production performance amounts, but the existing schema has no generic supplemental metric slot for those values. They were not stored as financial statement metrics.

- 2023 modular revenue: 8,855,591,531 KRW, about 1.0% of revenue.
- 2024 modular revenue: 7,549,989,904 KRW, about 0.9% of revenue.
- 2025 modular revenue: 13,810,025,029 KRW, about 1.7% of revenue.
- Jincheon modular production performance disclosed amount: 11,591 million KRW in 2023, 9,764 million KRW in 2024, and 15,909 million KRW in 2025.

These are not module counts. Product and service revenue, rental revenue, and consolidated revenue are not modular revenue.

## Verified Source Page Ranges

All 84 source locations have PDF page ranges:

- 2026-03-12 business report: balance sheet pp.54-55, income statement p.56, cash flow pp.61-62, working capital pp.110-112 and pp.116-118, borrowings pp.137-140, revenue breakdown pp.159-160, investment signals pp.123-124, pp.130-131, and p.163, audit opinion summary pp.306-307.
- 2025-03-19 corrected business report: balance sheet pp.48-49, income statement p.49, cash flow pp.52-53, working capital pp.95-96 and pp.97-98, borrowings pp.119-124, revenue breakdown pp.139-140, investment signals pp.102-104, p.109, and p.142, audit opinion summary pp.281-282.
- 2024-03-14 business report: balance sheet pp.44-45, income statement p.45, cash flow pp.48-49, working capital pp.85-86 and pp.87-88, borrowings pp.102-103, revenue breakdown pp.111-112, investment signals pp.90-91, p.94, and p.113, audit opinion summary pp.219-220.

## Deferred Items

- Cost of sales, profit before tax, non-current assets, non-current liabilities, cash and short-term financial assets, net debt, debt ratio, gearing ratio, and allowance for doubtful accounts are not represented as source metrics because the current `company_audit_financials_v1` schema does not expose those fields.
- Modular production capacity and production performance are documented above but not stored in the source JSON because the current schema has no supplemental metric container.
- The Boeun factory purchase contract is recorded only as a post-balance-sheet special event and is not treated as an operating modular production facility.
