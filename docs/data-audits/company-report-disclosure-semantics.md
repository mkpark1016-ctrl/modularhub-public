# Company Report Disclosure Semantics

This note defines how audit-report financial amounts distinguish an explicit reported zero from unavailable or inapplicable disclosure.

| reported | disclosure_status | Meaning | Calculation | UI |
| --- | --- | --- | --- | --- |
| integer | reported | Reported numeric amount | Included | Actual amount |
| 0 | reported | Explicit reported zero | Included | 0.0억원 |
| null | not_disclosed | The source does not disclose the amount | Combined metric is unknown | 공시되지 않음 |
| null | not_applicable | The component does not apply to the entity or year | Excluded from combined metrics | 해당 없음 |

## Derived Ratios

Derived ratios keep unavailable values as JSON `null`. The validator must not emit the strings `"None"`, `"NaN"`, or `"Infinity"` for unavailable percentages or ratios.

Examples:

- If the numerator is `null`, the ratio is `null`.
- If the denominator is `null` or `0`, the ratio is `null`.
- If a reported value is exactly `0`, the ratio is calculated normally when the denominator allows it.

## Combined Metrics

The same aggregation rule applies to `total_borrowings` and `receivables_total`.

- Reported integer components are summed, including explicit zero.
- If any component is `not_disclosed`, the combined metric is `null` with `disclosure_status=not_disclosed`.
- `not_applicable` components are excluded from the sum.
- If every component is `not_applicable`, the combined metric is `null` with `disclosure_status=not_applicable`.

## Source Requirements

When `reported` is `null`, the record must include:

- `disclosure_status`
- `notes`
- `source_locations`

When `reported` is an integer, an optional `disclosure_status` must be `reported`.

## UI Requirements

The public financial UI uses `display_text` first. If it is missing, the fallback labels are:

- `not_disclosed`: 공시되지 않음
- `not_applicable`: 해당 없음
- otherwise: 확인되지 않음

Unavailable metrics must not render chart bars as zero-length values. Explicit `0` must remain visible as `0.0억원`.
