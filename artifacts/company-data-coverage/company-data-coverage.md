# Company Data Coverage & Freshness

- As of date: `2026-08-10`
- Canonical companies: 11
- Supplemental public companies: 0
- Effective public companies: 11
- Audit records: 7
- Effective public universe audit-backed: 7 / 11
- Full three-year audit records: 7
- Full three-year audit records in effective public universe: 7
- Non-audit companies in public universe: 4
- Consistency status: clean (0 issues)
- Company priority counts P0/P1/P2/P3: 0 / 6 / 3 / 2
- Work-item priority counts P0/P1/P2/P3: 0 / 6 / 3 / 0

This artifact is a data-work priority control plane. It is not a company score, credit rating, investment recommendation, or ranking.

## Priority Queue

| Priority | Type | Company | Domain | Next action | Reason codes |
| --- | --- | --- | --- | --- | --- |
| P1 | company_data_gap | dl-enc | financial | audit_report_onboarding | missing_audit_financials |
| P1 | company_data_gap | gs-ec | financial | audit_report_onboarding | missing_audit_financials, production_capacity_unknown |
| P1 | company_data_gap | hyundai-engineering | financial | audit_report_onboarding | missing_audit_financials |
| P1 | company_data_gap | planm | evidence | monitor | excessive_verification_pending |
| P1 | company_data_gap | samsung-ct-construction | financial | audit_report_onboarding | missing_audit_financials, production_capacity_unknown |
| P1 | company_data_gap | yuchang-enc | evidence | monitor | excessive_verification_pending |
| P2 | company_data_gap | daeseung-engineering | evidence | source_registry_review | source_coverage_sparse |
| P2 | company_data_gap | geogwang-enterprise | production | production_source_refresh | production_capacity_unknown, technology_evidence_sparse |
| P2 | company_data_gap | nrb | production | production_source_refresh | production_capacity_unknown |

## Company Coverage

| Company | Audit | Operations | Evidence | Freshness | Next action |
| --- | --- | --- | --- | --- | --- |
| daeseung-engineering | complete | sufficiently_covered | sparse | current | source_registry_review |
| dl-enc | unavailable | sufficiently_covered | verified | current | audit_report_onboarding |
| geogwang-enterprise | complete | sufficiently_covered | verified | current | production_source_refresh |
| gs-ec | unavailable | sufficiently_covered | verified | current | audit_report_onboarding |
| hyundai-engineering | unavailable | sufficiently_covered | verified | current | audit_report_onboarding |
| kumkang-kind | complete | sufficiently_covered | verified | current | monitor |
| nrb | complete | sufficiently_covered | verified | current | production_source_refresh |
| planm | verification_pending | sufficiently_covered | verified | current | monitor |
| samsung-ct-construction | unavailable | sufficiently_covered | verified | current | audit_report_onboarding |
| sungji-steel | complete | sufficiently_covered | verified | current | monitor |
| yuchang-enc | verification_pending | sufficiently_covered | mixed | current | monitor |
