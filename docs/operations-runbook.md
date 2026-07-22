# ModularHub Operations Runbook

This runbook covers the public data automation that keeps ModularHub business, news, and company information current.

## Public Automation

Workflow: `.github/workflows/update-public-data.yml`

Triggers:
- `schedule`: every day at 22:00 UTC, which is 07:00 KST on the following day.
- `workflow_dispatch`: emergency or operator-initiated runs.

The workflow uses concurrency group `update-public-data-${{ github.ref }}` with `cancel-in-progress: false`, so two runs on the same branch do not publish at the same time. The job timeout is 30 minutes.

## Dataset SLA

Policy file: `config/operations/data_freshness_policy.json`

Storage and comparisons use UTC. User-facing timestamps are shown in Asia/Seoul.

Initial thresholds:
- News: warning after 48 hours, critical after 72 hours.
- Business: warning after 24 hours, critical after 48 hours.
- Companies: warning after 30 days, critical after 90 days.

Missing or unparsable timestamps are not treated as healthy. They are reported as `unknown`.

## Source Health States

Source status is normalized before reporting:
- `healthy`: source ran successfully or has current data.
- `no_new_items`: source responded but no new eligible items were found.
- `rate_limited`: remote service returned a rate-limit response.
- `auth_error`: credentials are invalid.
- `permission_error`: credentials exist but the source is not permitted.
- `timeout`: request timed out.
- `parse_error`: response shape changed or could not be parsed.
- `source_unavailable`: source failed or is down.
- `stale`: source data is older than the SLA.
- `disabled`: intentionally disabled source.

Public UI may show a simple status badge and safe message. It must not show API keys, authorization headers, raw responses, stack traces, Review Queue candidates, or local file paths.

## Count Drop Protection

The publish guard compares the new public JSON with the previous published data.

Critical blocks:
- News count drops by more than the configured threshold.
- Business count drops by more than the configured threshold.
- Runtime public company count falls below 11.
- Public JSON schema is unreadable.
- Secret indicators appear in generated operations reports.

When a critical guard fails, the workflow restores the backed-up public JSON and blocks the commit. Last Known Good public data remains in production.

## GitHub Issue Alerts

Script: `scripts/operations_issue_alert.py`

Alerts are fingerprinted by dataset, source id, and error category. If an open issue already exists for the fingerprint, the workflow comments on that issue instead of creating a duplicate.

Labels:
- `data-pipeline`
- `operations`
- `freshness-alert`

If issue write permission is missing, the workflow records a warning in the job summary and continues safely.

## Safe Manual Run

Use `workflow_dispatch` only when a scheduled run missed or an operator needs a controlled refresh. Do not repeatedly re-run a failing source before reading the job summary and artifacts.

Check these artifacts:
- `operations-freshness-*`
- `public-news-freshness-*`
- `unified-news-audit-*`
- `business-collection-impact-audit-*`

## Production Smoke Test

Script:

```powershell
cd frontend
$env:PRODUCTION_BASE_URL = "https://modularhub-public.vercel.app"
npm.cmd run qa:production
```

The smoke test checks:
- Home, news, business, companies, Daeseung Engineering detail, and not-found routes.
- Public JSON fetches.
- Latest news date is parseable.
- Public company UI shows 11 companies.
- The public Review Queue route is not exposed.
- Mobile width has no horizontal overflow.
- Browser console errors are absent.

## Rollback

If the workflow publishes bad data despite guards:
1. Confirm the latest Vercel Production deployment and main commit.
2. Revert the data commit or use the previous known-good commit.
3. Let Vercel redeploy from Git, then run `npm.cmd run qa:production`.
4. Inspect operations freshness and source health artifacts before re-running collection.

Never paste Repository Secrets, API keys, authorization headers, or raw API responses into issues, PRs, or documentation.
