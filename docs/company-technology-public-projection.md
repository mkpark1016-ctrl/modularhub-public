# Company-generic technology public projection

The technology projection layer has a company-generic core. Company behavior is selected through `CompanyProjectionPolicy`; the core does not infer a company from a title and does not assign Samsung identifiers to other companies.

## Stable identity

New technology IDs use the normalized tuple `company_id + source + official_identity`. A title change therefore does not change identity, while the same official record projected for two companies cannot collide. The Samsung compatibility wrapper supplies its historical `samsung` namespace so existing `tech-samsung-kipris-*` identifiers remain unchanged.

Technology collection and public evidence use three deliberately separate identities:

- The live transport `external_id` is collection provenance. For KIPRIS it can be a result `SerialNumber`, so pagination or query changes can change it.
- The official patent identity is application-number based, such as `patent:1020220067854`.
- The public evidence source ID is derived from source, record type, and official identity, such as `official:kipris:patent:1020220067854`.

KIPRIS `SerialNumber`, applicant query, pagination position, timestamps, company display names, and patent titles are never public evidence identity inputs. Upstream artifacts retain their transport-based source IDs for provenance, while the public projection report records the mapping from `upstream_source_ids` to `public_source_ids`.

Existing Samsung production records keep their legacy source IDs and evidence registry. The Samsung compatibility policy does not migrate those IDs.

## Projection policy

The policy explicitly controls allowed new record types, allowed lifecycle statuses, safe enrichment fields, status-update permission, and treatment of published applications. Existing non-empty fields are never overwritten: disagreement with official evidence makes the whole record enrichment a conflict and rolls it back.

GS E&C uses registered-only Policy A:

- `patent` is the only new public record type.
- `registered` is the only accepted new status.
- application-only `published` records are retained in a review-only artifact and are not projected publicly.
- only empty `application_number`, `patent_number`, `application_date`, and `registration_date` fields may be enriched.
- status updates are disabled.
- adjacent records and wrong-applicant records are review/exclusion artifacts only.

Company matching is reconstructed from `config/company_technology/kipris_expansion_readiness.json`. The approved legal-name aliases are re-matched before projection, and cross-company alias collisions are blocking errors.

## GS offline dry-run

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m scripts.integrations.technology.gs_public_projection
```

The runner consumes only the accepted Phase 11B-3B final-reconciliation JSON artifacts. It performs no KIPRIS, KAIA, ST27, or LLM request and does not write public JSON. Its accepted contract is baseline 3, enriched existing 3, registered new 4, published review 3, adjacent review 186, wrong-applicant exclusion 3, and final candidate total 7.

Outputs are written beneath `artifacts/company-technology/gs-public-projection-dry-run/` and include candidate, diff, registered, published-review, adjacent-review, excluded-applicant, summary, report, and security-audit artifacts. Protected public file hashes are captured before and after the run and must remain identical.

The GS dry-run also emits public-safe evidence source candidates and an evidence-resolution report. Each registered patent source uses the credential-free KIPRIS portal URL plus its accepted title and application number as display metadata. The runner resolves these sources against an in-memory company candidate; it does not write `companies.json`.

## Samsung compatibility

`build_samsung_public_projection` and `run_public_projection` remain the supported Samsung entry points. They preserve the seven-record baseline requirement, one manual KAIA record, historical schema version, historical ID namespace, result keys, and status-adjudication behavior. The generic core is an implementation detail beneath that compatibility contract.
