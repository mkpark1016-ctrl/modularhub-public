# Company Data Coverage & Freshness Control Plane

## Purpose

The company data coverage control plane measures how complete and fresh the
current ModularHub company data is. It recommends data-maintenance work, not
company quality, creditworthiness, investment merit, or competitive ranking.

The builder reads:

- `frontend/public/data/companies/companies.json`
- `frontend/src/data/publicCompanySupplements.json`
- `frontend/public/data/companies/company_report_insights.json`
- existing public audit source JSON files under `data/company_reports/*/`

It does not modify source audit values, public company data, business data, news
data, or metadata.

## Coverage Domains

The coverage model records these domains for each company:

- Identity: master record, profile, headquarters, representative, website
- Financial: audit-backed availability, years, scope, standard, source count,
  required metric coverage, optional metric coverage
- Operations: production, project, and technology coverage
- Evidence: source counts, verified source counts, disclosure limitations, and
  manual page checks
- Freshness: profile, production, project, technology, and audit dates

## State Contract

The control plane uses state labels rather than a numeric company score.

Audit coverage:

- `complete`: at least three audit years, current latest fiscal year, no missing
  required metrics, and no verification-pending required metric signals
- `partial`: audit data exists but years, latest year, or required metric
  coverage is incomplete
- `verification_pending`: audit data exists but source locations or required
  metrics still require verification
- `unavailable`: no audit-backed public financial view model is available

Operational coverage:

- `sufficiently_covered`: at least two operational domains have verified records
- `partial`: one operational domain has verified records
- `sparse`: operational records exist but verified coverage is weak
- `unavailable`: no operational records are present

Evidence coverage:

- `verified`: verified source coverage exists and no pending evidence flag is
  present
- `mixed`: verified sources exist alongside pending evidence
- `pending`: evidence is present but requires review
- `sparse`: no source or verified-source coverage is available

Freshness:

- `current`
- `aging`
- `stale`
- `unknown`

## Freshness Rules

Freshness is calculated from `--as-of-date`; tests use a fixed date for
deterministic output.

Initial thresholds:

- Company profile: current within 12 months, aging within 24 months
- Production: current within 12 months, aging within 18 months
- Projects: current within 18 months, aging within 24 months
- Technology: current within 24 months, aging within 36 months
- Audit financials: current when latest fiscal year is no more than one year
  behind the as-of year; aging when two years behind; stale otherwise

Patent registration age alone is not treated as stale. The freshness rule only
tracks whether the technology status itself has been recently verified.

## Priority Queue

Priority is a data-maintenance priority, not a company risk score.

- `P0`: cross-source referential integrity or public-data consistency work that
  should be reconciled before downstream data maintenance. Examples include an
  audit-backed View Model record without a `companies.json` master row,
  an audit insight without a public audit source, a public audit source without
  an audit insight, or a future-dated public verification timestamp. P0 is not
  a company risk rating.
- `P1`: gaps that significantly limit dashboard analysis, such as missing audit
  financials, incomplete audit years, stale audit data, or excessive
  verification-pending items.
- `P2`: useful follow-up gaps that do not block dashboard use, such as missing
  borrowings, missing receivables, unknown production capacity, project evidence
  sparsity, stale production verification, stale profile data, or sparse source
  coverage.
- `P3`: low-risk enrichment work.

Reason codes include:

- `missing_audit_financials`
- `audit_years_incomplete`
- `audit_data_stale`
- `financial_scope_unknown`
- `missing_operating_cash_flow`
- `missing_borrowings`
- `missing_receivables`
- `production_capacity_unknown`
- `production_verification_stale`
- `project_evidence_sparse`
- `technology_evidence_sparse`
- `company_profile_stale`
- `excessive_verification_pending`
- `source_coverage_sparse`
- `supplemental_profile_not_canonicalized`
- `audit_record_without_company_master`
- `audit_insight_without_public_source`
- `public_source_without_audit_insight`
- `future_verification_date`

The JSON separates:

- `company_priority_counts`: all public companies grouped by their company data
  maintenance priority, including monitor-only P3 companies
- `work_item_priority_counts`: actual queue work items, including consistency
  issues

`priority_counts` remains as a backward-compatible alias of
`work_item_priority_counts`.

## Public Universe And Audit Records

The canonical public company universe is discovered from `companies.json`.
The current public universe contains 11 canonical companies. Daeseung
Engineering was migrated from the legacy runtime supplement into canonical
`companies.json`, so the supplemental public company count is currently 0.

The generic supplemental contract is still retained in
`frontend/src/data/publicCompanySupplements.json` for future temporary public
profiles. If supplemental rows are added later, the effective public universe is
canonical companies plus supplemental public companies, de-duplicated by
`company_id`; canonical records win if an ID appears in both sources.

Audit-backed records are discovered from `company_report_insights.json`.

The control plane reports both views:

- `canonical_company_count`: canonical `companies.json` records
- `supplemental_public_company_count`: supplemental public records not already
  present in the canonical company list
- `effective_public_company_count`: browser-visible public universe used for
  coverage evaluation
- `audit_record_count`: all audit-backed records in the audit View Model
- `audit_backed_in_canonical_universe_count`: audit-backed records that also
  exist in the canonical company list
- `audit_backed_in_universe_count`: backward-compatible alias for
  audit-backed records in the effective public universe
- `audit_backed_in_effective_universe_count`: audit-backed records that also
  exist in the effective public universe
- `full_three_year_audit_record_count`: all three-year audit-backed records
- `full_three_year_audit_in_canonical_universe_count`: three-year audit-backed
  records in the canonical company list
- `full_three_year_audit_in_universe_count`: backward-compatible alias for
  three-year audit-backed records in the effective public universe
- `full_three_year_audit_in_effective_universe_count`: three-year audit-backed
  records in the effective public universe

Each company coverage row includes `company_record_source`:

- `canonical`: source record came from `companies.json`
- `supplemental`: source record came from the supplemental public profile file

If an audit-backed record exists in neither canonical nor supplemental public
data, the record is not deleted or promoted. It becomes a `P0`
`consistency_issue` with `audit_record_without_company_master`.

If a company is browser-visible only through the supplemental profile contract,
it remains in the effective universe and is not treated as a P0 orphan. Instead,
it receives a nonblocking `P2` `maintenance_issue` with
`supplemental_profile_not_canonicalized`, `recommended_next_domain =
consistency`, and `recommended_next_action = canonical_company_migration`.
This maintenance item is not expected for Daeseung Engineering after the
canonical migration.

## Audit Source Discovery

Public audit source discovery is filename-range agnostic. It searches
`data/company_reports/<company-id>/` for `audit_financials_*.json` files whose
`schema_version` is `company_audit_financials_v1`.

Excluded files and directories:

- `onboarding/`
- `staging/`
- `artifacts/`
- candidate files

If multiple public candidates exist, the builder uses a deterministic ordering:

1. latest maximum financial year
2. earliest minimum financial year
3. filename

If multiple files cover the same year span, the selected path is deterministic
but the discovery result is marked ambiguous for consistency review.

## Date Parsing

Supported date inputs:

- `YYYY-MM-DD`
- `YYYY-MM`, interpreted as the first day of the month
- `YYYY`, interpreted as January 1
- ISO datetime
- ISO datetime with `Z`
- ISO datetime with timezone

Invalid, empty, or missing values parse as unknown. Future verification dates
remain freshness-current for display purposes but generate
`future_verification_date` as a P0 consistency signal.

## CLI

```powershell
python scripts\build_company_data_coverage.py --as-of-date 2026-08-09
python scripts\build_company_data_coverage.py --as-of-date 2026-08-09 --check
python scripts\build_company_data_coverage.py --as-of-date 2026-08-09 --company-id yuchang-enc
python scripts\build_company_data_coverage.py --as-of-date 2026-08-09 --priority P1
python scripts\build_company_data_coverage.py --as-of-date 2026-08-09 --supplements frontend\src\data\publicCompanySupplements.json
```

## Artifacts

Default outputs:

- `artifacts/company-data-coverage/company-data-coverage.json`
- `artifacts/company-data-coverage/company-data-coverage.md`
- `data/company_reports/company_data_coverage_snapshot.json`

The `artifacts/` directory is ignored by Git. The lightweight snapshot keeps
only CI-friendly state labels, priority reason codes, counts, and company IDs.
It intentionally excludes raw KRW values and source-location payloads.

## Audit Coverage

Required audit metric coverage tracks each metric by status:

- `reported`
- `not_disclosed`
- `not_applicable`
- `verification_pending`
- `missing`

Reported zero is preserved as `reported`, not treated as missing.

## Onboarding Linkage

The control plane can operate from existing public audit source files and the
public audit View Model alone. Company-report onboarding artifacts are not
required for coverage generation.

Companies without audit financials receive:

- `recommended_next_action = audit_report_onboarding`

Companies with stale or incomplete audit data receive:

- `recommended_next_action = audit_report_refresh`

## OpenDART Monitoring Preparation

This phase does not add live OpenDART network collection. The control plane is
designed so future monitoring can add corp-code, receipt-number, latest report
date, and reporting-entity metadata without requiring `DART_API_KEY` during
tests.

## Limitations

- Coverage states are only as reliable as the current public JSON and audit
  View Model.
- The builder does not infer unreported values.
- The builder does not determine company quality or rank companies.
- Audit records present outside the effective public universe are reported as a
  consistency signal but are not automatically promoted or removed.
- Supplemental public profiles are a compatibility bridge. They should be
  migrated into the canonical company list in a later data PR after review.
