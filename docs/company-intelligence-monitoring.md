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

Collectors only report whether required secrets are configured. They never
print raw values, partial values, or secret lengths. Do not commit `.env`
files.

## Local Execution

```bash
python scripts/company_monitoring/collect_dart.py --companies kumkang-kind,yuchang-enc --days 30 --live --acknowledge-live
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
- `days`: lookback window, default `30`

The workflow also runs once per weekday at 09:00 KST.

Artifacts:

- `company-intelligence-raw`
- `company-intelligence-review-queue`
- `company-intelligence-digest`

Raw source responses are uploaded as artifacts only and are not committed. The
digest artifact also includes `live-pilot-summary.json` and
`live-pilot-report.md`.

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
