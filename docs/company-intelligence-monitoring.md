# Company Intelligence Monitoring

This pipeline collects automatic company-intelligence candidates without
modifying the verified company baseline or public frontend JSON.

## Data Flow

1. Monitoring configuration is read from `config/company_monitoring/`.
2. Source collectors write raw responses under `artifacts/company_monitoring/raw/`.
3. Raw records are normalized into Fact/Event/Evidence candidates.
4. Candidates are classified with conservative rule-based logic.
5. Duplicate candidates are marked with `review_status=duplicate`.
6. Only `review_status=pending` records are written to
   `data/company_monitoring/review_queue.json`.
7. A digest is written to `reports/company_monitoring/latest_digest.*`.

The verified baseline remains unchanged. Promotion into verified data is a
separate human review workflow.

## Source Tiers

- Tier A: OpenDART, procurement/agency official records, patents, public
  certification records.
- Tier B: company official pages, official press releases, official brochures.
- Tier C: NAVER API HUB search results, trusted media, trade press.
- Tier D: blogs, snippets, promotional secondary material.

Tier C or D evidence never promotes a project into verified credit by itself.

## Secrets

The workflow reads these values only from GitHub Actions Secrets or local
environment variables:

- `DART_API_KEY`
- `NAVER_API_HUB_CLIENT_ID`
- `NAVER_API_HUB_CLIENT_SECRET`
- `NAVER_API_HUB_NEWS_ENDPOINT` optional, defaults to
  `https://naverapihub.apigw.ntruss.com/search/v1/news`

Collectors only report whether required secrets are configured. They never
print raw values, partial values, or secret lengths. Do not commit `.env`
files.

The company monitoring NAVER adapter uses the NAVER API HUB contract only:

- Host: `naverapihub.apigw.ntruss.com`
- Path: `/search/v1/news`
- Client ID header: `X-NCP-APIGW-API-KEY-ID`
- Client secret header: `X-NCP-APIGW-API-KEY`

It does not fall back to `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, or
`openapi.naver.com`; those legacy settings may still be used by other
collectors.

## Local Execution

```bash
python scripts/company_monitoring/collect_dart.py --companies kumkang-kind,yuchang-enc --days 30 --live --acknowledge-live
python scripts/company_monitoring/collect_naver_search.py --preflight --live --acknowledge-live
python scripts/company_monitoring/collect_naver_search.py --companies kumkang-kind,yuchang-enc --days 30 --live --acknowledge-live
python scripts/company_monitoring/build_review_queue.py
python scripts/company_monitoring/validate_review_queue.py
python scripts/company_monitoring/summarize_live_pilot.py
python -m pytest tests/company_monitoring
```

Without `--live --acknowledge-live`, collectors do not call external APIs.
Without secrets, live collectors record source-level errors and continue.
Fixture tests do not call live APIs.

## GitHub Actions

Run `Company Intelligence Monitor` manually with:

- `companies`: comma-separated company IDs, default `kumkang-kind,yuchang-enc`
- `sources`: comma-separated source IDs, default `dart,naver`
- `lookback_days`: lookback window, default `30`
- `acknowledge_live`: must be `true` for external API calls
- `publish`: must remain `false`

The workflow is `workflow_dispatch` only. It has no schedule, push, or
pull_request trigger. The live acceptance workflow is guarded to run only from
the repository default branch.

Artifacts:

- `company-intelligence-raw`
- `company-intelligence-review-queue`
- `company-intelligence-digest`
- `company-intelligence-live-pilot`
- `company-intelligence-audit`

Raw source responses are uploaded as artifacts only and are not committed. The
digest artifact also includes `live-pilot-summary.json` and
`live-pilot-report.md`.

## Read-Only Review Queue Dashboard

The dashboard route is `/company-intelligence` and appears in the main
navigation as `기업 모니터링`. It is read-only: candidates can be searched,
filtered, sorted, paginated, and inspected, but the UI does not accept,
reject, mutate, or publish candidates.

The public dashboard data is a sanitized projection of the internal review
queue:

- `frontend/public/data/company-intelligence/review-queue.json`
- `frontend/public/data/company-intelligence/manifest.json`

Export command:

```powershell
python scripts\company_monitoring\export_review_queue_public.py --input data\company_monitoring\review_queue.json --output frontend\public\data\company-intelligence\review-queue.json --manifest-output frontend\public\data\company-intelligence\manifest.json
```

The same command in POSIX-style shells:

```bash
python scripts/company_monitoring/export_review_queue_public.py \
  --input data/company_monitoring/review_queue.json \
  --output frontend/public/data/company-intelligence/review-queue.json \
  --manifest-output frontend/public/data/company-intelligence/manifest.json
```

The dashboard loads data from `VITE_COMPANY_INTELLIGENCE_DATA_URL` when that
public URL is configured. Otherwise it loads
`/data/company-intelligence/review-queue.json`. This environment variable must
only contain a public JSON URL; do not put DART, NAVER, GitHub, or other
secrets into any `VITE_` variable.

Development and tests may use
`frontend/src/fixtures/company-intelligence-review-queue.json` when the public
JSON is missing. Production does not silently fall back to the fixture; it
shows `데이터가 아직 게시되지 않았습니다. 최신 수집 결과를 확인해주세요.`
instead.

The public contract intentionally excludes raw responses, auth headers,
environment variables, local paths, stack traces, evidence hashes, source IDs,
and internal review metadata that is not needed for the dashboard.

Next step: add authenticated review actions and state persistence after the
read-only dashboard is accepted.

## Candidate Review

Reviewers inspect `review_queue.json` and decide whether a candidate is:

- accepted
- rejected
- duplicate
- superseded

Initial automatic output is always `pending` unless it is a duplicate.

## Duplicate Rules

Candidates are linked as duplicates when they share one of:

- canonical source URL
- DART receipt number
- evidence hash
- same company, normalized title, and published date

Duplicate candidates are not deleted; they keep `duplicate_of`.

## Project Credit Rules

Automatic candidates do not receive verified project credit. The following
statuses must remain `project_credit=false`:

- preferred bidder
- planned
- unconfirmed
- cancelled
- MOU or partnership discussion
- R&D
- exhibition
- Pre-Con
- not signed

## Adding a Source Adapter

1. Add the source policy in `config/company_monitoring/source_policy.json`.
2. Create a collector under `scripts/company_monitoring/`.
3. Emit raw records to `artifacts/company_monitoring/raw/`.
4. Normalize into the candidate schema.
5. Add fixture tests under `tests/company_monitoring/`.
6. Add the collector step to `.github/workflows/company-intelligence-monitor.yml`.

## Failure Handling

Source failures are isolated. DART can fail while NAVER continues, and vice
versa. Rate limits use retries/backoff in collectors. Secrets and full response
bodies are not printed in logs.
