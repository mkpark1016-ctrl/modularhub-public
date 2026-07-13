# OpenDART Setup for Company Research

This repository does not store OpenDART credentials.

## API Key

Set the key in the shell before running DART research scripts:

```powershell
$env:OPENDART_API_KEY = "your-key"
```

or on POSIX shells:

```sh
export OPENDART_API_KEY="your-key"
```

Do not commit `.env`, tokens, downloaded reports, or `.cache/opendart`.

## Cache

OpenDART downloads are cached under:

```text
.cache/opendart/
```

This directory is git-ignored. The scripts store only extracted metadata,
source references, and verified numeric facts in `companies.json`.

## Manual Filing Fallback

If the API key is unavailable, or if a filing must be selected manually, add
verified receipt numbers to:

```text
config/companies/dart_manual_filings.json
```

Each entry should include:

- `company_id`
- `fiscal_year`
- `report_type`
- `receipt_number`
- `report_title`
- `filed_at`
- `source_url`
- `note`

Do not enter a receipt number unless the DART page confirms the legal entity.

## Unit Policy

Financial statement values should preserve the original source unit and also
store normalized values. The comparison unit for ModularHub company research is
KRW million (`KRW_MILLION`) because Korean audit reports commonly publish
financial statement tables in won, thousand won, or million won. Every stored
numeric financial value must include:

- `source_value`
- `source_unit`
- `normalized_value`
- `normalized_unit`
- `normalization_factor`

If the source unit is unknown, leave the value null and record a research gap.

## Scope Policy

Company-total financials and modular-segment financials must never be mixed.
If an audit report does not disclose a modular segment:

- `modular_segment_available=false`
- `modular_segment_revenue=null`
- `modular_segment_operating_profit=null`

Whole-company sales must not be labeled as modular sales.
