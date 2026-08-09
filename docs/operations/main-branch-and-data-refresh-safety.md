# Main Branch And Data Refresh Safety

## Current Structure

The repository currently contains `Update public data`:

- Workflow file: `.github/workflows/update-public-data.yml`
- Triggers: daily schedule and `workflow_dispatch`
- Permissions: `contents: write`, `actions: read`, `issues: write`
- Concurrency: `update-public-data-${{ github.ref }}`, `cancel-in-progress: false`
- Commit target: the checked-out branch, normally `main`
- Commit paths:
  - `frontend/public/data/business.json`
  - `frontend/public/data/news.json`
  - `frontend/public/data/meta.json`

The workflow runs collectors, exports public JSON, audits shrinkage and
contracts, builds the frontend, then commits public data changes directly with
`github-actions[bot]` when there is a diff.

## Existing Guards

The workflow includes several useful guards:

- backs up currently published public JSON before collection
- isolates several collector failures with warnings so one source does not wipe
  out other sources
- runs public JSON security and contract tests
- runs frontend build before commit
- refuses suspicious cumulative public data shrinkage and restores the backup
  JSON before failing

## Risks

Direct main data refresh can still race with long-lived PRs:

- Open PRs can become stale when scheduled public JSON commits land on main.
- Guarded company-report onboarding preview hashes can change when protected
  public files are refreshed, even when audit source files are unchanged.
- Branch protection appears not to be the only control plane; the workflow has
  write permission and can push if the repository rules allow it.
- Scheduled commits can create repeated rebase work for data-only or
  audit-promotion PRs.

## Relationship To Guarded Onboarding

Guarded onboarding protects audit promotion by hashing protected public files
and requiring a fresh preview SHA before write. This remains effective, but
scheduled public JSON refreshes can invalidate an older preview. The expected
safe behavior is:

1. Refresh the PR branch from latest main.
2. Re-run validate and preview.
3. Use the new preview SHA for controlled promotion.
4. Confirm protected public JSON files are not part of the PR diff unless the
   PR is explicitly a public-data refresh.

## Transition Options

### A. Keep Direct Main With Stricter Guards

Keep the current workflow shape, but tighten validation and summaries.

Benefits:

- Least operational change
- Current schedule continues

Tradeoffs:

- Open PRs can still be invalidated by public-data commits
- Requires reviewers to keep checking protected public diff drift

### B. Automation Branch Plus PR

Collectors write public JSON to a deterministic automation branch and open a
data-only PR.

Benefits:

- Reviewable public-data diffs
- No silent direct-main changes during long-lived PRs
- Easier rollback and audit trail

Tradeoffs:

- Requires PR review/merge process for data freshness
- Needs duplicate-run and empty-diff handling

### C. GitHub Ruleset With Bot Bypass

Enable branch protection/rulesets and permit only the data-refresh workflow or
bot identity to bypass targeted rules.

Benefits:

- Stronger default protection
- Can preserve direct automation when truly needed

Tradeoffs:

- Requires careful ruleset management outside code
- Misconfiguration can block scheduled refreshes or allow overly broad bypass

## Recommendation

Prefer option B for public data once operational latency is acceptable. Until
then, keep option A with explicit summaries, protected-file diff checks, and
fresh preview SHA validation for every guarded audit-promotion PR.

This document is advisory only. Phase 7C-1 does not change repository settings,
branch protection, workflow triggers, or the direct-main publishing model.
