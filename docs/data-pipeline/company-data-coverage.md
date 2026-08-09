# Company Data Coverage & Freshness Control Plane

## Purpose

The company data coverage control plane measures how complete and fresh the
current ModularHub company data is. It recommends data-maintenance work, not
company quality, creditworthiness, investment merit, or competitive ranking.

The builder reads:

- `frontend/public/data/companies/companies.json`
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

- `P0`: public data conflicts, verified value conflicts, or stale critical
  source issues. The current builder reserves this level for future conflict
  gates.
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

## CLI

```powershell
python scripts\build_company_data_coverage.py --as-of-date 2026-08-09
python scripts\build_company_data_coverage.py --as-of-date 2026-08-09 --check
python scripts\build_company_data_coverage.py --as-of-date 2026-08-09 --company-id yuchang-enc
python scripts\build_company_data_coverage.py --as-of-date 2026-08-09 --priority P1
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
- Audit records present outside the `companies.json` universe are reported as a
  consistency signal but are not automatically promoted or removed.
