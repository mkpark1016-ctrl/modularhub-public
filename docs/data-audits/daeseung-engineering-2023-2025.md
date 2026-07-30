# Daeseung Engineering 2023-2025 Audit Report Financial Audit

## Scope

This audit adds standalone financial statement data for `daeseung-engineering` using the existing `company_audit_financials_v1` schema. The source documents are Daeseung Engineering audit reports. The attached PDFs were used only to verify amounts, auditor metadata, report dates, source page ranges, and entity attribution; the PDFs were not copied into the repository.

## Source Documents

- 2023-09-19 audit report: primary source for FY2023. FY2022 comparative statements are marked unaudited and are excluded.
- 2024-09-19 audit report: primary source for FY2024 and cross-check source for FY2023.
- 2025-09-17 audit report: primary source for FY2025 and cross-check source for FY2024.

FY2023 no longer uses the 2025-09-17 report as a cross-check because that report covers FY2025 and FY2024 only. The 2025 report remains in the corporate split special-event evidence list because it helps confirm continuity after the 2023-06-30 split.

## Financial Statement Basis

- Financial scope: standalone financial statements.
- Accounting standard: Korean GAAP.
- Currency and unit: KRW integer won.
- Report dates are audit report submission dates.
- Auditor report dates are independently recorded from the independent auditor report pages: 2023-09-11, 2024-09-13, and 2025-09-16.

## Checkpoints

| Year | Revenue | Gross Profit | Operating Profit | Net Income | Operating Cash Flow | Total Borrowings | Trade Receivables Gross | Receivables Total | Modular Classroom Rental Revenue |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2023 | 32,326,080,148 | 7,530,500,530 | 4,109,790,546 | 3,009,792,401 | 59,283,840,033 | 8,442,844,880 | 1,407,373,616 | 2,589,969,463 | 16,324,555,370 |
| 2024 | 84,005,687,052 | 15,685,352,450 | 10,058,636,613 | 5,203,952,176 | 26,430,939,883 | 28,842,700,552 | 1,908,992,362 | 3,632,795,139 | 66,404,136,368 |
| 2025 | 61,659,861,549 | 12,681,852,632 | 6,365,339,970 | 4,376,654,645 | -345,400,575 | 53,164,938,435 | 3,165,203,872 | 3,418,283,872 | 25,082,978,186 |

## Audit Information

| Year | Auditor | Opinion | Auditor Report Date |
| --- | --- | --- | --- |
| 2023 | Mirip Accounting Corporation | Unqualified | 2023-09-11 |
| 2024 | Mirip Accounting Corporation | Unqualified | 2024-09-13 |
| 2025 | Mirip Accounting Corporation | Unqualified | 2025-09-16 |

## Industrial Property Rights Semantics

The source JSON now distinguishes actual zero amounts from non-disclosure through `disclosure_status`.

| Year | Reported KRW | Disclosure Status | Evidence |
| --- | ---: | --- | --- |
| 2023 | 0 | reported | The 2023 audit report intangible-assets note explicitly shows the industrial property rights ending carrying amount as zero. |
| 2024 | 0 | reported | The 2024 audit report omits a separate intangible-assets line, but the 2025 audit report comparative balance sheet explicitly shows the prior-year industrial property rights carrying amount as zero. |
| 2025 | 3,417,840 | reported | The 2025 audit report balance sheet explicitly discloses industrial property rights of 3,417,840 KRW. |

No industrial property rights value is treated as `not_disclosed` after the PDF re-check. The validator now supports `reported: null` with `disclosure_status: not_disclosed` or `not_applicable` for future companies, and rejects null values marked as reported.

## Modular Disclosure Limits

The audit reports separately disclose modular classroom rental revenue. This value is stored in the existing generic `rental_revenue` field and is used to calculate rental revenue share:

- 2023: 50.5% of revenue.
- 2024: 79.0% of revenue.
- 2025: 40.7% of revenue.

Product revenue, construction revenue, service revenue, and equipment rental revenue are not treated as modular revenue. Related-company or related-party results are not combined into the standalone Daeseung Engineering series.

The reports also disclose modular classroom rental asset values and additions, but the current common schema has no dedicated modular classroom rental asset metric container. The reported modular classroom acquisition amount is preserved in `investment_signals.construction_in_progress` and the broader rental asset details remain documented here rather than adding company-specific schema fields.

## Verified Source Page Ranges

All 84 source locations are recorded as `verified_section_range`.

- 2023 audit report: balance sheet pp.5-6, income statement pp.7-8, cash flow pp.10-11, intangible-assets note p.18, modular classroom and investment notes pp.17 and 20, borrowings p.19.
- 2024 audit report: balance sheet pp.5-6, income statement pp.7-8, cash flow pp.10-11, modular classroom and operating lease notes pp.19-20, borrowings pp.18-19.
- 2025 audit report: balance sheet pp.5-6, income statement pp.7-8, cash flow pp.10-11, borrowings pp.19-20, modular classroom rental asset and operating lease notes pp.22 and 25.

## Entity Attribution

The company split effective 2023-06-30 did not transfer an operating business segment. The audit note indicates only capital stock and term deposits were transferred to Daeseung ENG, so the 2023-2025 standalone financial series is not treated as broken by the split. This is recorded as a special event but does not trigger automatic aggregation or restatement.

## Deferred Items

- FY2022 comparative values are excluded because the 2023 audit report marks them unaudited.
- Modular classroom rental asset gross/net balances, additions, and future operating lease revenue are not stored as separate source metrics because `company_audit_financials_v1` has no common fields for those supplemental disclosures.
- Product, construction, service, and equipment rental revenue are not inferred as modular revenue.
