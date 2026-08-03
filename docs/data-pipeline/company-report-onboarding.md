# Company Report Onboarding Pipeline

This pipeline validates structured audit or business report candidate JSON before a company is staged or promoted into public financial insights.

## Scope

The pipeline starts from a manually prepared `candidate_audit_financials.json`. It does not download DART files, parse PDFs, run OCR, infer missing amounts, or replace source review. It only checks that a curated candidate is safe to validate, stage, preview, and explicitly promote.

## Directory Contract

```text
data/company_reports/<company-id>/onboarding/candidate_audit_financials.json
data/company_reports/<company-id>/onboarding/manifest.json
data/company_reports/<company-id>/staging/audit_financials_<first-year>_<last-year>.json
data/company_reports/<company-id>/audit_financials_<first-year>_<last-year>.json
artifacts/company-report-onboarding/<company-id>/
```

`artifacts/` is gitignored. Candidate and staging files are not discovered by the public builder because `build_company_report_insights.py` only scans `data/company_reports/*/*.json` one level below each company directory.

## Manifest

The manifest schema is `schemas/company_reports/company_report_onboarding_manifest_v1.schema.json`.

It defines company identity, reporting entity, financial scope, currency, unit, target years, candidate/staging/public paths, source priority, required metrics, optional metrics, allowed warning codes, and promotion policy acknowledgements.

Paths are repository-relative and must not contain `..`, absolute prefixes, or backslashes. The public path must match the manifest company ID and target year range.

## Commands

```powershell
python scripts/onboard_company_report.py validate --manifest data/company_reports/<company-id>/onboarding/manifest.json
python scripts/onboard_company_report.py stage --manifest data/company_reports/<company-id>/onboarding/manifest.json
python scripts/onboard_company_report.py preview --manifest data/company_reports/<company-id>/onboarding/manifest.json
python scripts/onboard_company_report.py promote --manifest data/company_reports/<company-id>/onboarding/manifest.json --expected-preview-sha <SHA256> --acknowledge-source-review --acknowledge-public-change --write
```

`promote` without `--write` is a dry run. `promote --write` is blocked unless the latest preview SHA matches and both acknowledgements are present.

## Verdicts

- `PASS` exits `0`.
- `REVIEW_REQUIRED` exits `2`.
- `BLOCKED` exits `3`.
- CLI usage or internal execution errors exit `4`.

`BLOCKED` covers schema errors, unsafe paths, candidate validator errors, identity/scope/unit mismatches, target year mismatches, missing primary sources, required metric problems, disallowed `verification_pending`, accounting validation errors, preview SHA mismatch, protected file changes, PDF detection, and secret-like text detection.

`REVIEW_REQUIRED` covers pending page checks, optional metrics that are not disclosed or verification pending, special events, and warnings not explicitly allowed by the manifest.

## Artifacts

Each run writes deterministic review artifacts under `artifacts/company-report-onboarding/<company-id>/`:

- `validation-report.json`
- `validation-report.md`
- `source-reconciliation.json`
- `public-diff-preview.json`
- `promotion-manifest.json`

The preview hash excludes runtime timestamps. Re-running the same input produces the same preview SHA.

## Preview and Promotion

Preview builds a temporary input root by copying current public audit JSON files and replacing only the target company with the candidate. It then reuses `build_company_report_insights.build_view_model`.

The preview separates:

- target company raw/source changes
- non-target raw/source changes
- derived peer benchmark changes
- added/removed companies
- protected file changes

Non-target raw/source changes are blocked. Peer benchmark changes caused by a new comparable company are reported separately and are not treated as source mutations.

Promotion writes only:

- `data/company_reports/<company-id>/audit_financials_<first-year>_<last-year>.json`
- `frontend/public/data/companies/company_report_insights.json`

Writes are atomic. If the second write or final builder check fails, original files are restored.

## Protected Data

The pipeline must not change:

- `frontend/public/data/companies/companies.json`
- `frontend/public/data/companies/company_intelligence_v2.json`
- `frontend/public/data/news.json`
- `frontend/public/data/business.json`
- `frontend/public/data/meta.json`

PDFs, OCR outputs, raw private documents, API keys, tokens, and credentials must not be committed.

## Existing Company Updates

For an existing company, set `replace_existing` to `true`. Preview must be reviewed before promotion. Raw KRW values, source refs, source locations, disclosure statuses, and generated peer benchmark effects should be checked in the preview artifact.

## New Company Adds

For a new company, add only the candidate and manifest first. Validate, stage, and preview before asking for public promotion. Adding a new company may change existing companies' derived peer benchmark ranks; those changes are reported separately.

## GitHub Actions

`.github/workflows/company-report-onboarding.yml` runs targeted tests and supports manual validate/stage checks. It does not expose promote mode and does not write public files.
