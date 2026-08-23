# Phase 11 company technology and patent automation foundation

## Scope

This phase is an offline, fixture-only foundation for Samsung C&T Construction. It does not call KIPRISPlus or KAIA, write public company data, add schedules, or introduce a publication path. Raw source responses must remain under gitignored `artifacts/` paths.

## Existing public contract

`frontend/public/data/companies/companies.json` is the current source consumed by `CompanyTechnologyTab`. Technology rows use `technology_id`, `name`, `record_type`, official number fields, `status`, `technology_area`, application and registration dates, `summary`, and `source_ids`. Samsung currently has one manually verified construction-new-technology row and six patent rows. Two patent rows deliberately share a title but have different registration numbers.

The fixture pipeline emits dry-run candidates in that compatible vocabulary. It never edits the public file.

## Official source contracts

### KIPRISPlus

The official KIPRISPlus catalogue describes the Patent and Utility Model Publication and Registration Gazette as a REST service returning XML search and bibliographic information, including application number, registration date, invention title, and registration status. Its item-search documentation includes applicant-name search. The existing repository secret name remains `KIPRIS_API_KEY`.

Official references:

- https://plus.kipris.or.kr/portal/search/clasList/List.do
- https://plus.kipris.or.kr/portal/popup/DBII_000000000000001/SC002/ADI_0000000000015118/apiDescriptionSearch.do

### KAIA

KAIA's official Construction New Technology Open API guide documents designation number, technology ID/name, notice date, scope/content, protection period, developer, keywords, and technology classification. This phase records the official response fields but does not add a KAIA secret or an HTTP client.

Official reference:

- https://www.kaia.re.kr/portal/bbs/view/B0000007/3494.do?menuNo=200026

Endpoint and request construction remain outside the executable foundation until the live phase verifies current access approval, transport, pagination, and credential handling. No guessed parameter is used by production code.

## Canonical model and identity

`NormalizedTechnologyRecord` supports patents and construction new technology with participant lists, official identifiers, status and dates, abstract/keywords, technology area, source metadata, and a credential-free source URL.

Identity never uses title:

- Patent: application number first; otherwise registration or patent number.
- Construction new technology: designation/new-technology number.

All official number aliases remain available for matching older manual rows that may only carry a registration number. Therefore equal titles with different official numbers remain distinct.

## Company matching

Matching uses canonical names and curated aliases from the company dataset. Corporate-form and punctuation normalization is allowed; fuzzy title or substring matching is not. Outcomes are `exact`, `normalized_alias`, `ambiguous`, or `unmatched`. A record can link to multiple companies. Ambiguous matches are never public candidates.

## Modular relevance

The classifier is deterministic. Direct modular vocabulary has priority. Construction-supporting concepts require construction context. The generic word `module`/`모듈` alone is not sufficient, and electronics, communications, semiconductor, battery, circuit, antenna, and similar contexts are explicitly rejected unless a direct modular-construction concept exists. Results include `direct`, `adjacent`, or `irrelevant`, matched terms, a reason code, and a compatible technology-area label.

## Reconciliation and publication safety

Official identities are deduplicated before reconciliation. Core disagreements in title, participants, official numbers, or status become conflicts instead of silent overwrites. Existing manually verified rows are preserved as `manual_only` when absent from source fixtures. Official matches can propose only empty-field enrichment. New relevant records become `net_new` dry-run candidates; irrelevant, unmatched, ambiguous, conflicting, or invalid records do not.

Sensitive query keys such as `accessKey`, `apiKey`, and `serviceKey`, user-info credentials, and raw request/response fields are rejected. Candidate URLs must be absolute HTTP(S) links without credentials.

## Offline dry run

```powershell
python -m scripts.integrations.technology.dry_run `
  --companies frontend/public/data/companies/companies.json `
  --fixture tests/fixtures/company_technology/samsung_official_records.json `
  --output-dir artifacts/company-technology/samsung-pilot
```

Outputs:

- `normalized_technology_records.json`
- `public_projection_candidates.json`
- `reconciliation_report.json`

The output directory is gitignored. Stable sorting and content hashes make repeated runs reproducible.

## Next live phase

1. Confirm KIPRISPlus service approval, current request/response samples, pagination, and legal-status semantics.
2. Decide a repository-reviewed KAIA secret name only after access approval; do not invent one in this phase.
3. Add bounded HTTP clients with sanitized diagnostics and raw artifacts under `artifacts/`.
4. Run a Samsung-only live acceptance and compare official identifiers with the seven-row manual baseline.
5. Keep publication disabled until identity, ambiguity, conflict, relevance, and credential gates pass.

## Phase 11A-2 live source acceptance

The Samsung-only live acceptance is implemented in
`scripts/integrations/technology/live_acceptance.py`. It retains the Phase
11A-1 canonical model and reconciliation rules, writes only to gitignored
`artifacts/company-technology/samsung-live/`, and never updates public company
data.

Verified official contracts:

- KIPRISPlus applicant search:
  `https://plus.kipris.or.kr/openapi/rest/patUtiModInfoSearchSevice/applicantNameSearchInfo`
  with `applicant`, `docsStart`, `docsCount`, `patent`, `utility`,
  `sortSpec`, `descSort`, and credential parameter `accessKey`.
- KAIA construction new technology:
  `https://www.kaia.re.kr/portal/openApi/newtecListData.xml`
  with `apiKey`, `apntNo`, `firstIndex`, and `lastIndex`.

The KIPRIS applicant response uses `PatentUtilityInfo` rows and title field
`InventionName`, while the older fixture contract used camel-case
`inventionTitle`. The live parser preserves the documented source fields and
the adapter maps only those verified names. KAIA's endpoint-specific guide
uses `apiKey`; the more general portal help text mentions `keyValue`, so the
endpoint-specific contract is authoritative for this integration.

Required environment variables:

- `KIPRIS_API_KEY`
- `KAIA_API_KEY`

Run the gated acceptance locally after both approved credentials are present:

```powershell
python -m scripts.integrations.technology.live_acceptance `
  --output-dir artifacts/company-technology/samsung-live
```

The client uses explicit connect/read timeouts, at most two attempts for
transient network and HTTP 5xx failures, bounded pages/records, credential-free
source URLs, and sanitized diagnostics. Authentication and service-denial
responses are not retried. A KAIA access failure is reported independently and
does not erase a healthy KIPRIS result.