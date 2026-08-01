# NRB Audit Financials Staging Contract

This staging contract keeps NRB's 2023-2025 standalone audit financial values in an internal validation path while the remaining source mismatches are reviewed.

## Staging Path

`data/company_reports/nrb/staging/audit_financials_2023_2025.json`

The public builder discovers `data/company_reports/*/*.json`. The nested `staging` directory is intentionally outside that discovery pattern, so NRB is not added to `company_report_insights.json`.

## Contract Guarantees

- Source values are stored as integer KRW won.
- Derived ratios are calculated by validators/builders, not stored in the source JSON.
- Null values are not converted to zero.
- Consolidated statement values are excluded from `financial_years`.
- The consolidated revenue breakdown table is not copied into standalone `revenue_breakdown`.
- Public JSON files are unchanged in this phase.

## Audit Opinion and Report Dates

The 2024 and 2025 audit reports have verified independent auditor report dates:

- 2024-03-27
- 2025-03-21

The 2026 business report identifies the auditor and opinion in the auditor table, but the independent auditor report date was not separately located in the attached PDF. The business report filing date is not copied into `auditor_report_date`.

## Staging Mismatch Policy

The staging payload may include cross-check differences only through:

`validation_metadata.validation_policy.allowed_cross_check_year_mismatches`

For NRB this is used for:

- 2023 current-liability classification difference,
- 2024 operating cash-flow difference.

The 2024 operating cash-flow difference remains a blocker for public promotion.

## Public Promotion Rule

This file is valid for internal review and tests, but public promotion requires a later phase. Until then:

- do not add `nrb` to public `company_report_insights.json`,
- do not change `companies.json` financial summaries from this staging file,
- do not show NRB audit financial cards in the frontend,
- do not treat consolidated revenue categories as modular segment revenue.

## Validation

The staging payload must pass:

```powershell
python scripts/validate_company_audit_financials.py --input data/company_reports/nrb/staging/audit_financials_2023_2025.json --expected-years 2023 2024 2025 --base-ref origin/main
```

The expected validator result is `valid: true` with revenue-breakdown availability warnings only.
