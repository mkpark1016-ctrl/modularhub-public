# Phase 10 External API Integration Foundation

## Scope

Phase 10A adds a safe adapter foundation for future LH, D2B, KEPCO, and
KIPRIS integrations. It does not call those external APIs and does not publish
live API data to `frontend/public/data/business.json` or company technology
JSON.

## Current Public Business Data Flow

The current public business pipeline is:

1. Source collectors under `src/collectors/` return raw source items.
2. `scripts/collect_all.py` selects enabled collectors and calls
   `src.collector_runner.run_collector`.
3. `src/collector_runner.py` normalizes raw items with `src.normalizer` and
   upserts records into the local SQLite database defined in `src.database`.
4. Additional source-specific scripts such as
   `scripts/collect_g2b_procurement_plans.py`,
   `scripts/collect_lh_public_housing_contests.py`,
   `scripts/collect_gh_public_housing_contests.py`, and
   `scripts/collect_ih_public_housing_contests.py` may enrich the same public
   business output path through controlled apply steps.
5. `scripts/export_public_json.py` exports sanitized public files to
   `frontend/public/data/business.json`, `frontend/public/data/news.json`, and
   `frontend/public/data/meta.json`.
6. `.github/workflows/update-public-data.yml` orchestrates collection, export,
   audits, and publication. It treats individual source failures as warnings
   where possible so a failed source does not delete existing public data.

`frontend/public/data/business.json` remains the public contract consumed by
the React/Vite frontend. Phase 10A does not modify that file.

## Current Technology And Patent Data Flow

Company technology and patent records are currently stored in:

- `frontend/public/data/companies/companies.json`
- `frontend/public/data/companies/company_intelligence_v2.json`
- curated/import source helpers under `scripts/verified_companies/` and
  `scripts/verified_import_helpers.py`

The public UI renders the technology tab through
`frontend/src/components/company/CompanyTechnologyTab.jsx`. The tab consumes
already curated company data. It does not call external APIs from the browser.

KIPRIS integration should therefore land first as an internal normalized
technology/patent candidate feed, then pass a human review or controlled public
promotion step before changing company public JSON.

## New Adapter Foundation

New code lives under `scripts/integrations/`.

Business adapter contract:

- `scripts/integrations/business/base.py`
- `scripts/integrations/business/sources.py`

Canonical business fields:

- `source`
- `source_record_type`
- `external_id`
- `title`
- `issuing_organization`
- `category`
- `region`
- `estimated_amount`
- `currency`
- `published_at`
- `deadline_at`
- `status`
- `contract_method`
- `source_url`
- `collected_at`
- `source_updated_at`

Supported `source_record_type` values:

- `procurement_plan`
- `pre_spec`
- `bid_notice`
- `bid_result`
- `contract`

The adapter also exposes `to_existing_collector_item()` so a later phase can
bridge normalized external business records into the current normalizer/DB
pipeline without leaking source-specific field names into frontend schemas.

Technology/patent adapter contract:

- `scripts/integrations/technology/base.py`

This defines a minimal `NormalizedTechnologyRecord` for future KIPRIS records.
It is intentionally not connected to company public JSON in Phase 10A.

## Source-Specific Boundaries

Source-specific XML/JSON parsing must stay inside source adapters. The public
business and company schemas should only receive normalized canonical fields.

Initial source adapter classes:

- `LHBusinessAdapter`
- `D2BBusinessAdapter`
- `KepcoBusinessAdapter`

These classes support fixture-only normalization tests. Their live
`collect_raw_records()` method intentionally raises `NotImplementedError` until
a later opt-in integration phase wires official endpoints, retry policy, and
artifact handling.

## Environment Variables

Required future Secret names:

- `LH_SERVICE_KEY`
- `D2B_SERVICE_KEY`
- `KEPCO_API_KEY`
- `KIPRIS_API_KEY`

Existing shared/public pipeline variables remain supported, including
`DATA_GO_KR_SERVICE_KEY` and the existing G2B/NAVER settings. API keys must be
read from environment variables or GitHub Actions Secrets only. They must not
be printed, written to Markdown, committed to fixtures, or exposed through
frontend `VITE_` variables.

## Fail-Safe Policy

Future external API collectors must follow these rules:

- API failure must not delete or replace existing public data.
- A failed source should produce a source-level error state and safe category.
- Raw API responses should be written only to ignored artifacts when needed,
  never committed to the repository.
- Public export should proceed only from validated normalized records.
- Empty live results must be distinguished from auth errors, transport errors,
  parse errors, and unsupported schema changes.
- Existing `business.json`, company intelligence data, and report insights
  should remain unchanged unless a later controlled promotion explicitly
  approves public data changes.

## Test Coverage

`tests/test_external_api_integration_foundation.py` verifies:

- LH fixture normalization.
- D2B procurement-plan alias normalization.
- KEPCO contract record normalization.
- `source_record_type` validation.
- Secret configured status without returning secret values.
- KIPRIS patent contract date normalization.
- No raw response, request header, or API key fields in normalized public-safe
  records.

## Recommended Next Steps

1. Add source-specific preflight commands for LH, D2B, KEPCO, and KIPRIS with
   explicit live opt-in flags.
2. Store raw responses only in ignored runtime artifacts.
3. Add schema snapshots for each official API response shape.
4. Bridge validated `NormalizedBusinessRecord` objects into the existing
   `src.collector_runner` path.
5. Add a controlled review queue before any KIPRIS technology records update
   company public JSON.
