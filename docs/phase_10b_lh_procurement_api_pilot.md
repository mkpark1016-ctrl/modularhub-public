# Phase 10B LH Procurement API Pilot

Phase 10B adds a read-only staging pilot for three LH e-procurement APIs. It reuses the Phase 10A external integration foundation and does not publish records into `frontend/public/data/business.json`.

## Resources

| LH resource | Canonical source_record_type | Default endpoint |
| --- | --- | --- |
| Order plan | `procurement_plan` | `https://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenOrdergPlanList.dev` |
| Pre-specification disclosure | `pre_spec` | `https://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenAdvcinfoReqList.dev` |
| Bid notice | `bid_notice` | `https://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev` |

All three resources use only `LH_SERVICE_KEY`.

## Local Dry Run

The runner refuses to call external APIs unless both live opt-in flags are present.

```powershell
python -m scripts.integrations.business.run_lh_pilot
```

This writes a guarded dry-run summary to `artifacts/lh/lh_summary.json`.

## Local Live Pilot

Use a narrow date window and avoid printing credential-bearing URLs.

```powershell
python -m scripts.integrations.business.run_lh_pilot `
  --resources procurement_plan,pre_spec,bid_notice `
  --from-date 2026-08-01 `
  --to-date 2026-08-18 `
  --page-size 5 `
  --max-pages 2 `
  --output-dir artifacts/lh `
  --live `
  --acknowledge-live
```

Outputs:

- `artifacts/lh/lh_records.json`
- `artifacts/lh/lh_summary.json`

The `artifacts/` path is gitignored. Raw API responses are not written.

## GitHub Actions Smoke

Workflow:

- `.github/workflows/lh-procurement-api-pilot.yml`

Trigger:

- `workflow_dispatch` only

Required secret:

- `LH_SERVICE_KEY`

The workflow runs the foundation and LH pilot tests, executes a narrow live smoke, verifies protected public data remains unchanged, and uploads only sanitized staging artifacts.

## Canonical Contract

The pilot emits Phase 10A `NormalizedBusinessRecord` fields only:

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

## Failure Policy

- Missing amounts remain `null`.
- Invalid dates are reported as invalid records.
- API errors are recorded per resource and do not delete existing public data.
- The runner never falls back to another key name.
- The frontend never calls LH APIs directly.
