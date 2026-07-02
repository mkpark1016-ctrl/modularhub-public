# GDELT Shadow Multi-Timestamp Sampling

This project keeps the GDELT Web NGrams live workflow as a single-timestamp,
manual, read-only verification. Multi-timestamp evaluation is performed only
after each timestamp has been approved and run separately.

## Why Multiple Timestamps

A single GDELT batch can prove transport and parsing, but it cannot describe
candidate quality over time. The shadow evaluator combines downloaded workflow
artifacts to measure pipeline stability, duplicate behavior, relevant candidate
yield, and manual-label precision across a sample set.

## Execution Contract

- Run `Verify GDELT Web NGrams live` manually for one approved timestamp at a
  time.
- Keep `acknowledge_single_run=true` only for that one execution.
- The live workflow remains limited to one Web NGrams request and one GAL
  request.
- Do not add schedule, retry, fallback timestamp search, DOC API calls, or a
  multi-timestamp workflow.
- Do not publish shadow candidates to `news.json`.

## Artifact Preparation

Download each workflow artifact and unpack it under a local ignored directory,
for example:

```text
artifacts/gdelt_shadow_samples/baseline-20211215000100/
```

The evaluator reads the probe and review artifacts already produced by the live
workflow, including:

- `report.json`
- `run_control.json`
- `download_manifest.json`
- `candidates.json`
- `manual_review.csv`
- `live_review_report.json`
- `live_review_report.md`

## Manifest

Copy `config/gdelt_shadow_sample_manifest.example.json` to a local manifest such
as `config/gdelt_shadow_sample_manifest.json` and point each sample at its
artifact directory. Timestamp values come from the manifest, not from code.

## Aggregation

Run the evaluator without network access:

```bash
python scripts/aggregate_gdelt_shadow_samples.py \
  --manifest config/gdelt_shadow_sample_manifest.json \
  --output-dir artifacts/gdelt_shadow_evaluation
```

Optional manual labels can be supplied:

```bash
python scripts/aggregate_gdelt_shadow_samples.py \
  --manifest config/gdelt_shadow_sample_manifest.json \
  --labels artifacts/gdelt_shadow_evaluation/manual_labels.csv
```

## Manual Labels

The evaluator writes `manual_labels_template.csv` with these labels:

- `relevant_building_modular`
- `irrelevant`
- `uncertain`
- `duplicate`
- `inaccessible`

Manual labels evaluate candidate-pool precision and candidate-pool recall only.
They do not measure source-level recall because the full GDELT source rows are
not manually labeled.

## Evaluation States

- `insufficient_sample`: fewer than six successful samples or fewer than twenty
  labeled candidates.
- `technical_shadow_pass`: transport and quality contracts pass, but the sample
  set is not yet enough for publication decisions.
- `quality_review_required`: labels reveal false positives, false negatives, or
  insufficient precision.
- `candidate_rules_hold`: the technical run completed, but rules need revision.
- `shadow_evaluation_pass`: sample and label thresholds are met, technical
  contracts pass, precision thresholds are met, and no severe false negatives
  are present.

Initial precision thresholds are:

- relevant precision: `0.90`
- irrelevant precision: `0.95`

`production_publish_allowed` remains `false` in every evaluator output. Public
JSON publication, scheduled collection, translation, summarization, and
dashboard exposure require a later explicit approval step.
