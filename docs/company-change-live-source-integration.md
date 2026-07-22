# Company Change Monitor Live Source Integration

## Purpose

Company Change Monitor remains a read-only workflow. It may collect source signals and build an internal review queue, but it must not publish public JSON, create update proposals automatically, or modify verified company baseline data.

## Root Cause Fixed

The monitor previously executed `public_news` but recorded configured non-public sources as `configured_deferred_to_source_adapter`. That made successful workflow runs look healthy even when `naver_api_hub` and `dart` source adapters were not called.

## Source Call Graph

- `public_news`
  - Reads `frontend/public/data/news.json`
  - Filters through `config/company_change_monitoring/company_identities.json`
  - Emits read-only raw and normalized signals
- `naver_api_hub`
  - Reuses `scripts/company_monitoring/collect_naver_search.py`
  - Uses NAVER API HUB only:
    - `https://naverapihub.apigw.ntruss.com/search/v1/news`
    - `X-NCP-APIGW-API-KEY-ID`
    - `X-NCP-APIGW-API-KEY`
    - `NAVER_API_HUB_CLIENT_ID`
    - `NAVER_API_HUB_CLIENT_SECRET`
  - Does not fall back to legacy NAVER Developers credentials
- `dart`
  - Reuses `scripts/company_monitoring/collect_dart.py`
  - Uses company identity `corpCode` values when present
  - Reports `identity_mapping_missing` for companies without a DART corp code

## Status Semantics

Each selected source writes a sanitized status object:

- `configured`: required environment variables or local public data are available
- `attempted`: the source adapter was actually invoked or the local source was actually read
- `state`: `success_with_candidates`, `success_empty`, `partial_success_with_source_warning`, `source_not_configured`, `identity_mapping_missing`, or a safe error category
- `safeErrorCategory`: classified failure category without secrets or request headers

`configured_deferred_to_source_adapter` is no longer a valid terminal state.

## Read-only Guards

- Workflow has no `publish` input
- `PUBLISH=false` is fixed inside the workflow
- `create_proposal` requires explicit `acknowledge_proposal=true`
- External source execution requires `acknowledge_live=true`
- Protected public data diff checks remain in the workflow

## Manual Acceptance Inputs

Pilot run:

- Branch: `main`
- Mode: `daily_signals`
- Companies: `gs-ec,yuchang-enc,daeseung-engineering`
- Sources: `public_news,naver_api_hub,dart`
- Lookback days: `30`
- Create proposal: `false`
- Acknowledge proposal: `false`
- Acknowledge live: `true`

Full dry run:

- Branch: `main`
- Mode: `daily_signals`
- Companies: blank, which means all 11 public companies
- Sources: `public_news,naver_api_hub,dart`
- Lookback days: `30`
- Create proposal: `false`
- Acknowledge proposal: `false`
- Acknowledge live: `true`
