# Company Intelligence V2 Contract

Company Intelligence V2 separates durable facts, time-bound events, supporting evidence, and corrections. The canonical file is `data/companies/company_intelligence_v2.json`. The public materializer writes a visibility-filtered copy and a backward-compatible `companies.json`.

## Grain and ownership

- `companies`: one row per stable `company_id`.
- `facts`: one observed value at a company, domain, field, and period/as-of grain.
- `events`: one real-world occurrence. Multiple articles about one occurrence remain one event with multiple evidence records.
- `evidence`: one source document or article. Evidence count is never a project count.
- `corrections`: explicit, auditable changes to a fact, event, or evidence classification.
- `materialized_summaries`: UI-ready derived statuses and counts. They are rebuildable and are not the source of truth.

## Fact rules

Facts use the domains `identity`, `financial`, `production`, `technology`, `organization`, `market`, and `strategy`. Numeric facts retain their unit, period, source IDs, and verification state. Missing values are omitted instead of converted to zero.

## Event and project credit rules

Events use controlled `event_type` and `event_status` values. A project receives `project_credit=true` only when all of the following hold:

1. `event_type=project`.
2. Status is `completed`, `in_progress`, `contract_signed`, or `award_confirmed`.
3. The company's delivery role is identified.
4. At least one Tier A or Tier B source supports the event.
5. The event is not a duplicate.

Preferred bidder, bid participation, plans, MOU, partnership discussions, R&D, exhibitions, cancelled items, unsigned items, and unconfirmed items never receive project credit.

## Evidence tiers

- Tier A: DART, procurement awards/contracts, owner or public-agency originals, patent/new-technology originals, laws, and public documents.
- Tier B: company official websites, press releases, brochures, and IR.
- Tier C: reliable media, trade media, and industry analysis.
- Tier D: blogs, recruitment posts, promotional secondary material, and search snippets.

Tier C or D evidence alone cannot promote a project to verified credit.

## Corrections and visibility

Public corrections live in `config/companies/manual_corrections.public.json`. A local private file may be placed at `config/companies/manual_corrections.private.json`; Git ignores it. Private correction metadata may affect a public materialization, but the private correction record itself is never exported.

Only records with `visibility=public` enter `frontend/public/data/companies/company_intelligence_v2.json`. API keys, cache paths, private notes, and full non-public source text are forbidden.

## Domain and overall status

The UI shows six independent domain states: identity, financial, production, project, technology, and recent signals. `overall_data_status` is a summary, not a replacement for domain states.

- `core_verified`: identity and financial domains are officially/cross verified and at least two additional domains have verified or partial support.
- `partially_verified`: meaningful official data exists, but the core and supporting domains do not meet the core threshold.
- `research_in_progress`: research records or evidence exist but verified coverage is limited.
- `watchlist`: reserved for an explicit watchlist company.
- `insufficient_public_data`: no meaningful public evidence is available.

The UI labels are Korean and never display raw enum values or snake_case.

## YooChang and Samsung correction

The Samsung AI modular-home media cluster is not a verified YooChang project or signed MOU. V2 classifies it as a `partnership` event with `event_status=not_signed`, `project_credit=false`, and `verification_status=not_verified`. Article records remain evidence only and do not contribute to project counts.
