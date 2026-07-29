# Company Information UX Restructure

## Purpose

Phase 6A-4 reorganizes the public company information experience around decision support. The data layer remains unchanged; the UI now separates judgement, detailed analysis, and evidence so users can scan a company quickly and open supporting sources only when needed.

## Existing Structure Reviewed

- Main route: `CompanyListingPage` in `frontend/src/App.jsx`
- Card and comparison UI: `frontend/src/components/company/CompanyComparisonMvp.jsx`
- Detail route and tab orchestration: `frontend/src/components/company/CompanyDetailView.jsx`
- Shared tabs and formatters: `frontend/src/components/company/companyDetailHelpers.js`
- Audit-report financial UI: `frontend/src/components/company/CompanyAuditFinancialPanel.jsx`
- Activity loader: `frontend/src/companyActivities.js`
- Breakpoints: 760px and 520px in `frontend/src/styles.css`

## Final Information Structure

1. Judgement: company list KPI, compact cards, compressed detail header, and the `종합분석` tab.
2. Detail: financials, production facilities, projects, technology and recent activities.
3. Evidence: reusable evidence drawer, verification matrix, and consolidated source list.

## Main Cards

Each company card now prioritizes:

- Company name and English name
- Role, competitive relation, and data status
- One-line competitive summary
- Four KPIs: latest revenue, operating margin, production facilities, verified projects
- One recent activity
- One data-gap or caution line when present
- Detail link and comparison selection

Repeated neutral messages such as “핵심 공백 없음” and “비교 가능” are not shown.

## Detail Tabs

- `overview` remains the URL value, but the tab label is `종합분석`.
- The common header is compact on non-overview tabs.
- Production and project tables switch to card lists on mobile.
- Financial tables are inside a collapsible details section.
- Evidence navigation is centralized through `EvidenceDrawer`.

## Data Gaps

Missing or unverified values are not converted to zero. Broader gaps are collected in the `데이터 공백` section. Detail tables keep local status text short and use drawer evidence when available.

## Evidence Display

The evidence drawer shows:

- Field or metric title
- Current displayed value
- Source title and publisher
- Document date
- Page or section when available
- Verification status
- Public source link only when a valid URL exists

## Responsive Rules

- 1440px: company cards stay in a two-column grid.
- 1024px: content may wrap but the page itself should not scroll horizontally.
- 768px and below: filters can collapse, tabs use one horizontal row, and production/project rows become cards.
- 390px: KPI and chart grids collapse; evidence drawer becomes a bottom sheet.

## Reuse Scope

The audit-report financial panel is still driven by `company_report_insights.json` when a company has report data. Companies without report insight data continue to use the legacy financial fallback.

## Remaining Data Work

This PR does not add new facts, sources, projects, facilities, or financial values. Companies with incomplete public evidence continue to show data gaps until the source data is reviewed in a future data PR.
