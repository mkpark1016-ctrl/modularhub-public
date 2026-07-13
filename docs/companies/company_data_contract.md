# ModularHub Company Data Contract

This contract defines the seed company universe for future competitor intelligence. It does not introduce UI routes, collectors, or automatic crawling.

## Scope

The first universe covers 17 Korean companies relevant to steel modular competition:

- Tier 1: direct steel modular competitors
- Tier 1-B: substitute-method competitor and technical benchmark
- Tier 2: strategic benchmark general contractors
- Tier 3: modular design influencers

GS E&C is stored as `internal_baseline`; it is excluded from competitor counts but remains available for future comparison matrices.

## Stable Identity

- `company_id` is lowercase kebab-case.
- `company_id` must not change when a company name changes.
- Legal names, English names, old names, and abbreviations belong in `aliases`.

## Master Fields

Each company must include:

- `schema_version`
- `company_id`
- `company_name`
- `company_name_en`
- `aliases`
- `country_code`
- `company_type`
- `competitive_role`
- `analysis_tier`
- `business_status`
- `modular_methods`
- `target_markets`
- `headquarters`
- `website_url`
- `listed_market`
- `ticker`
- `summary`
- `last_verified_at`
- `data_confidence`
- `review_status`

Unverified numeric values must remain `null`. Unverified collections must remain empty arrays.

## Enums

`competitive_role`:

- `direct_competitor`
- `substitute_competitor`
- `strategic_benchmark`
- `design_influencer`
- `internal_baseline`
- `watchlist`

`company_type`:

- `general_contractor`
- `specialist_manufacturer`
- `modular_integrator`
- `design_firm`
- `engineering_firm`
- `material_supplier`
- `solution_provider`

`modular_methods`:

- `steel_volumetric`
- `steel_panelized`
- `pc_volumetric`
- `pc_ramen`
- `wood_volumetric`
- `wood_panelized`
- `hybrid`
- `bathroom_pod`
- `unknown`

`target_markets`:

- `public_housing`
- `private_housing`
- `school`
- `dormitory`
- `hotel`
- `senior_housing`
- `office`
- `military`
- `hospital`
- `industrial`
- `data_center`
- `temporary_building`
- `overseas`
- `unknown`

`review_status`:

- `unresearched`
- `collecting`
- `partially_verified`
- `verified`
- `update_required`

`data_confidence`:

- `high`
- `medium`
- `low`
- `review`
- `unknown`

## Analysis Data Areas

`company_profile` separates business scope from general company identity:

- modular business start year
- modular business status
- design, manufacturing, construction, and integration scope

`production` records factory-level facts:

- facility name
- location
- owned or leased
- production lines
- capacity value
- capacity unit
- operating status
- expansion plan
- outsourcing status

Capacity values must not be converted across units unless the source provides the conversion.

`project_portfolio` records verified project examples:

- project name
- client
- building use
- modular method
- company role
- floors
- households
- module count
- contract date
- completion date
- contract amount
- project status

`bidding_performance` records period-based procurement performance:

- analysis period
- participation count
- win count
- win rate
- education facility count
- housing facility count
- rental-type count
- average bid amount
- average award amount
- average award price per area
- major procuring agencies

`technology` records evidence-backed technical signals:

- structural systems
- connection technologies
- fire resistance certifications
- seismic technologies
- high-rise track record
- construction new technologies
- patents
- innovative procurement products
- factory completion rate

`financials` must separate whole-company financials from modular-segment financials:

- year
- revenue
- gross profit
- operating profit
- net income
- operating cash flow
- debt ratio
- consolidated or separate basis
- modular segment flag

`recent_signals` records timely market signals:

- new awards
- factory expansion
- investment
- MOU
- technology development
- acquisition
- business downsizing
- quality or defect signals
- overseas expansion

`sources` records verification evidence:

- source id
- source type
- source name
- source URL
- published date
- accessed date
- confidence
- verification note

## List Card View Model

Future company list cards should use only:

- `company_id`
- `company_name`
- `company_type_label`
- `competitive_role_label`
- `modular_method_labels`
- `target_market_labels`
- `primary_facility_summary`
- `representative_project`
- `bid_participation_count`
- `bid_win_count`
- `recent_signal`
- `last_verified_at`
- `data_confidence`

Long financial, patent, and project details must stay out of list cards.

## Detail Page View Model

Future detail pages should support these sections:

- Competitive position
- Business overview
- Production facilities
- Projects
- Bidding competitiveness
- Technology
- Financials
- Recent signals
- Sources

## Validation Policy

The validation scripts must fail on:

- wrong company count
- duplicate `company_id`
- exact alias collisions
- invalid enum values
- missing required fields
- references to unknown companies
- unverified numeric values in seed data
- production capacity values without units
- financial records without scope

The initial seed is intentionally `unresearched`; Tier 1 companies are the first research priority.
