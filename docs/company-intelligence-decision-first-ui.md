# Company Intelligence Decision-First UI

This phase keeps the public company data contract unchanged and reorganizes the company experience around fast comparison and review.

## Public Scope

- The public navigation remains Business, News, and Company information.
- Company monitoring and review queue data remain internal-only.
- Browser code reads only existing public JSON files and does not call DART, NAVER, or any source API.

## Company List

- Company filters are shown as a compact scan toolbar on desktop and remain collapsible on mobile.
- Quick filters cover direct competitors, audit financial coverage, and confirmed production facilities.
- Cards prioritize decision chips, four key metrics, recent signals, and watch points.
- Long profile summaries are not the primary card content.

## Company Detail

- The detail header exposes company identity, verification metadata, decision keywords, and one KPI strip.
- The overview tab starts with a deterministic decision snapshot: position, capability, and watch signals.
- Finance cards show observations and interpretation scope first. Internal rule identifiers are not shown in the default card view.
- Production, project, technology, and evidence tabs keep their existing routes and fallback behavior.

## Data Semantics

- Missing, not disclosed, not applicable, and verification-pending values are never converted to zero.
- Keywords are derived only from existing structured fields and report view models.
- Existing comparison query parameters and tab query parameters remain unchanged.

## Responsive Contract

- Desktop: filter toolbar and two-column company cards.
- Tablet and mobile: filters collapse, cards stack, KPI and decision grids reduce without horizontal page overflow.
- Evidence and entity drawers keep keyboard/focus behavior from the existing implementation.

