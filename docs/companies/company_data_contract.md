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

Field-level verification uses `field_sources`, a map from a master field name
to one or more `source_id` values. Structured research records such as
production facilities, projects, bidding records, technology records,
financials, and recent signals use `source_ids`, `verified_at`, `confidence`,
and optional `verification_note` fields. Facts and numbers without source
links must not be stored as verified data.

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

### Production Facility Standardization

Production records distinguish facility existence, ownership or operating
relationship, modular system type, and production capacity. Missing production
data is not equivalent to a confirmed absence of facilities.

Company-level `production_summary` should use:

- `research_status`
- `verification_status`
- `manufacturing_model`
- `own_facility_status`
- `facility_count`
- `own_facility_count`
- `official_capacity_available`
- `summary`
- `source_ids`
- `verified_at`
- `data_confidence`

Each production facility should support:

- `facility_id`
- `facility_name`
- `company_id`
- `facility_type`
- `modular_system_type`
- `ownership_type`
- `operator_name`
- `operation_status`
- `address`, `region`, and `city`
- `site_area` plus `site_area_unit`
- `building_area` plus `building_area_unit`
- `production_scope`
- `production_processes`
- `line_count`
- `automation_level`
- `major_equipment`
- `capacity_value`
- `capacity_unit`
- `capacity_period`
- `capacity_scope`
- `capacity_basis`
- `capacity_status`
- `source_ids`
- `verified_at`
- `data_confidence`
- `notes`

Allowed production facility meanings:

- `facility_type`: `modular_factory`, `steel_fabrication_factory`,
  `pc_factory`, `timber_modular_factory`, `interior_assembly_factory`,
  `general_material_factory`, `research_facility`, `unknown`
- `modular_system_type`: `steel_volumetric`, `steel_panelized`,
  `pc_modular`, `timber_modular`, `hybrid`, `multiple`, `unknown`
- `ownership_type`: `owned`, `subsidiary_owned`, `affiliate_owned`,
  `leased`, `partner_owned`, `contract_manufacturing`, `planned`, `unknown`
- `operation_status`: `active`, `partially_active`, `under_expansion`,
  `under_construction`, `planned`, `suspended`, `closed`, `unknown`
- `capacity_status`: `official_confirmed`, `company_claimed`,
  `third_party_reported`, `derived`, `unavailable`, `not_applicable`,
  `unknown`

Capacity values may only be stored when the source provides a value, a unit,
a period, and the scope of the capacity. Annual module count and annual
square-meter output are different units and must not be converted into one
another. General steel fabrication capacity must not be recast as modular unit
production capacity. Planned expansion targets are separate from current
capacity.

If a facility is confirmed but capacity is not publicly disclosed:

- `capacity_value` is `null`
- `capacity_status` is `unavailable`
- `capacity_basis` is `not_publicly_disclosed`

If no source-backed facility is confirmed:

- `production` remains an empty array
- `facility_count` remains `null` when the count is unknown
- the research gap explains the reviewed source range
- the UI must not render this as `0` facilities or `0` capacity

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

The same `source_url` should not be duplicated inside a Wave research set.
When the same source supports multiple facts, reuse the same `source_id`.

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
