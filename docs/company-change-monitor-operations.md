# Company Change Monitor Operations

Company Change Monitor is an internal, read-only workflow. It collects evidence signals for the 11 modular company universe, writes private review artifacts, audits integrity, evaluates operational health, and creates deduplicated GitHub Issues only when action is required.

It must not publish public JSON, create update proposals automatically, approve candidates, or merge data changes.

## Schedules

GitHub cron expressions are UTC.

| Run kind | UTC cron | KST time | Lookback | Companies | Sources |
| --- | --- | --- | ---: | --- | --- |
| Daily | `10 23 * * *` | Every day 08:10 KST | 2 days | blank means all 11 | `public_news,naver_api_hub,dart` |
| Weekly | `40 23 * * 6` | Every Sunday 08:40 KST | 30 days | blank means all 11 | `public_news,naver_api_hub,dart` |

The daily run uses a 2-day window to detect recent changes with low duplicate volume. The weekly run uses a 30-day window to catch slower-moving source updates and missed signals.

Manual `workflow_dispatch` remains available for controlled acceptance runs. Use:

- `mode=daily_signals`
- `companies=` blank for all 11 companies
- `sources=public_news,naver_api_hub,dart`
- `lookback_days=2` for daily acceptance or `30` for broader audit
- `acknowledge_live=true`
- `create_proposal=false`
- `acknowledge_proposal=false`

## Read-Only Policy

The workflow sets `PUBLISH=false` and has no `publish` input. It uses `contents: read`, `actions: read`, and `issues: write`. It does not request `contents: write` or `pull-requests: write`.

Protected public data must remain unchanged:

- `frontend/public/data/news.json`
- `frontend/public/data/business.json`
- `frontend/public/data/meta.json`
- `frontend/public/data/companies/**`

## Source States

`success_empty` means a source adapter was invoked and returned no accepted candidates. A single `success_empty` run is not a failure.

Failure examples:

- configured source with `attempted=false`
- `ZERO_PIPELINE_NOT_EXECUTED`
- `configured_deferred_to_source_adapter`
- missing or unparsable artifacts
- public data changed
- secret exposure detected

## Operations States

`HEALTHY` means no failure and no warning.

`WARNING` means the run is valid but needs operational attention, such as:

- pending candidates above threshold
- candidate count spike compared with previous successful run
- three consecutive empty runs for an invoked source
- three consecutive NAVER API HUB-only candidate runs
- DART identity mapping coverage below 80%
- one company contributing 60% or more of candidates
- one source contributing 95% or more of candidates

If previous run history is unavailable, consecutive-run warnings are recorded as `history_unavailable` and are not treated as failures.

`FAILED` means the run violated integrity, protection, source execution, artifact, or secret safety rules.

## Alerts

The alert script creates or updates GitHub Issues only for `FAILED` evaluations or sustained warning conditions. It uses this marker to prevent duplicates:

`<!-- company-change-monitor-alert:<alert-code> -->`

Labels:

- `operations`
- `company-monitor`
- `automated-alert`

If labels cannot be created, issue publication may proceed without blocking the monitor. If a later run is `HEALTHY`, the alert script comments on and closes the matching open issue.

Issue bodies include run metadata, source summaries, company count, candidate counts, and next actions. They intentionally omit secrets, auth headers, raw API responses, and environment dumps.

## Artifacts

Required artifact names remain stable:

- `company-change-raw-summary`
- `company-change-normalized`
- `company-change-review-queue`
- `company-change-digest`
- `company-change-audit`
- `company-change-classification-diagnostics`

Retention:

- Daily scheduled run: 14 days
- Weekly scheduled run: 30 days
- Manual run: 30 days

The `company-change-audit` artifact also includes the operations evaluation and alert summary.

## Manual Review

Download the artifacts from the workflow run and inspect:

- `review_queue.json`
- `latest_digest.md`
- `audit-summary.json`
- `classification-diagnostics.json`
- `operations-evaluation.json`

Do not copy candidate records into public JSON without a separate human-reviewed update path.

## Phase 4G Backlog

DART corp-code coverage improvements, additional source adapters, and public-source rebalancing are Phase 4G scope. They are intentionally not part of the operations automation PR.

## Source Coverage Reliability

Company Change Monitor now runs an offline source coverage audit after candidate validation. The audit verifies `public_news`, `naver_api_hub`, and `dart` attempt coverage, DART identity mapping coverage, source concentration, and public news empty-result diagnostics without recalling external APIs.

Artifacts are uploaded as `company-source-coverage`, `company-dart-identity-coverage`, and `company-public-news-diagnostics`. See `docs/company-source-coverage-reliability.md` for the policy and local command.
