# Company Source Coverage Reliability

Company Change Monitor는 11개 공개 모듈러 기업을 대상으로 `public_news`, `naver_api_hub`, `dart` 3개 source의 실행 상태를 별도로 감사한다. 이 감사는 외부 API를 다시 호출하지 않고, monitor run이 만든 `raw-summary.json`과 `review_queue.json`만 읽는다.

## Purpose

- configured source가 실제로 시도됐는지 확인한다.
- `success_empty`를 실패와 구분하고, public news snapshot의 0건 원인을 별도로 기록한다.
- 후보가 한 source에 과도하게 몰리는지 확인한다.
- DART corp_code 신원 매핑 coverage를 11개사 기준으로 추적한다.
- source coverage 실패가 public JSON 변경이나 proposal 생성으로 이어지지 않도록 운영 gate를 제공한다.

## Inputs

- `artifacts/company-change-monitor/raw-summary.json`
- `data/company_change_monitoring/review_queue.json`
- `config/company_change_monitoring/source_coverage_policy.json`
- `config/company_change_monitoring/dart_company_identity_registry.json`

## Outputs

- `artifacts/company-source-coverage/source-coverage-report.json`
- `artifacts/company-source-coverage/source-coverage-report.md`
- `artifacts/company-source-coverage/dart-mapping-report.json`
- `artifacts/company-source-coverage/public-news-empty-diagnostics.json`
- `artifacts/company-source-coverage/source-contribution-history.json`
- `artifacts/company-source-coverage/source-concentration-diagnostics.json`
- `artifacts/company-source-coverage/source-concentration-diagnostics.md`

## State Rules

`success_empty` is valid when the source was attempted and the source-specific reason is explainable. It is not treated as a transport or authentication failure.

Single-run source concentration is a warning only. Issue creation is reserved for sustained warnings or hard failures.

DART identity coverage is expected to remain below 100% until all 11 companies have verified corp_code mappings. Missing mappings are reported as identity coverage gaps, not guessed.

## Source Contribution History

`source-contribution-history.json` stores sanitized run-level and source-level counts from the current monitor run and any recent comparable successful production runs whose artifacts are still available. It records raw candidate share, unique candidate share, high-priority share, company coverage share, and independent evidence share. It never stores raw article bodies, raw API responses, review queue records, request headers, GitHub tokens, or source credentials.

`source-concentration-diagnostics.json` separates a single concentrated run from sustained source concentration:

- `history_unavailable`: previous run artifacts could not be read; the current run is preserved and the gate does not fail.
- `history_insufficient`: fewer than 3 comparable runs are available; sustained concentration is false.
- `observe`: the current run exceeds the concentration threshold, but the recent history does not show a sustained pattern.
- `warning`: at least 3 consecutive comparable runs, or at least 4 of the last 5 comparable runs, exceed the concentration threshold. This is an operations warning, not a public data mutation.
- `failed`: source coverage failures or configured-source execution failures require operator action.

Raw candidate share is based on source candidate volume. Unique candidate share counts each candidate ID once per source so duplicate-heavy sources do not overstate their durable contribution. Independent evidence share is the share of source candidates that also have evidence from another source.

## Local Audit

PowerShell:

```powershell
python scripts\audit_company_source_coverage.py
```

The command does not call DART, NAVER, or any external API.

## Read-Only Proposal Manifest

`artifacts/company-change-monitor/proposal-manifest.json` is an internal review metadata artifact. It does not modify verified company data, public JSON, or frontend-visible review queues.

The manifest is produced for every Company Change Monitor run so the artifact contract remains stable. In the default run, `create_proposal=false`, the manifest is empty with `requested=false`, `created=false`, and no items.

Proposal candidates are included only when both `create_proposal=true` and `acknowledge_proposal=true` are provided. The manifest includes at most 20 candidates, and only candidates that are pending, high confidence, non-duplicate, non-conflicting, and backed by an evidence URL or evidence key.

Proposal manifest generation and actual data promotion are separate stages. The monitor must not create patches, update public data, open pull requests, or merge changes from this artifact.
