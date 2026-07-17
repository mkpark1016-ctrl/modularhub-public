# Company Verified Baseline Audit

- Valid: `True`
- Public companies: 10 / allowlist 10
- V1 ids: yuchang-enc, kumkang-kind, planm, sungji-steel, geogwang-enterprise, nrb, gs-ec, hyundai-engineering, samsung-ct-construction, dl-enc
- V2 ids: yuchang-enc, kumkang-kind, planm, sungji-steel, geogwang-enterprise, nrb, gs-ec, hyundai-engineering, samsung-ct-construction, dl-enc
- Critical issues: 0
- Warnings: 74

## Issue Counts

- UI_NOT_RENDERED: 70
- UI_TRUNCATED: 4

## Company Summary

| company_id | name | source projects | V1 projects | V2 project events | source tech | V1 tech | UI hidden | severity |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| gs-ec | GS건설 | 3 | 3 | 3 | 3 | 3 | 0 | warning |
| hyundai-engineering | 현대엔지니어링 | 3 | 3 | 3 | 14 | 14 | 6 | warning |
| samsung-ct-construction | 삼성물산 건설부문 | 1 | 1 | 1 | 7 | 7 | 0 | warning |
| dl-enc | DL이앤씨 | 2 | 2 | 2 | 21 | 21 | 13 | warning |
| yuchang-enc | 유창이앤씨 | 10 | 10 | 10 | 7 | 7 | 0 | warning |
| kumkang-kind | 금강공업 | 10 | 10 | 10 | 4 | 4 | 0 | warning |
| nrb | 엔알비 | 7 | 7 | 7 | 16 | 16 | 8 | warning |
| planm | 플랜엠 | 17 | 17 | 17 | 10 | 10 | 2 | warning |
| geogwang-enterprise | 거광기업 | 1 | 1 | 1 | 0 | 0 | 0 | warning |
| sungji-steel | 성지제강 | 1 | 1 | 1 | 2 | 2 | 0 | warning |

## Findings

- `warning` `UI_NOT_RENDERED` gs-ec established_at: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` gs-ec representative: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` gs-ec employee_count: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` gs-ec major_businesses: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` gs-ec financials.gross_profit: Gross profit for 2025 exists but is not rendered
- `warning` `UI_NOT_RENDERED` gs-ec financials.gross_profit: Gross profit for 2024 exists but is not rendered
- `warning` `UI_NOT_RENDERED` gs-ec financials.gross_profit: Gross profit for 2023 exists but is not rendered
- `warning` `UI_NOT_RENDERED` hyundai-engineering established_at: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` hyundai-engineering representative: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` hyundai-engineering employee_count: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` hyundai-engineering major_businesses: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` hyundai-engineering financials.gross_profit: Gross profit for 2025 exists but is not rendered
- `warning` `UI_NOT_RENDERED` hyundai-engineering financials.gross_profit: Gross profit for 2024 exists but is not rendered
- `warning` `UI_NOT_RENDERED` hyundai-engineering financials.gross_profit: Gross profit for 2023 exists but is not rendered
- `warning` `UI_TRUNCATED` hyundai-engineering technology: 6 technology records are hidden by slice(0, 8)
- `warning` `UI_NOT_RENDERED` samsung-ct-construction established_at: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` samsung-ct-construction representative: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` samsung-ct-construction employee_count: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` samsung-ct-construction major_businesses: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` samsung-ct-construction financials.gross_profit: Gross profit for 2025 exists but is not rendered
- `warning` `UI_NOT_RENDERED` samsung-ct-construction financials.gross_profit: Gross profit for 2024 exists but is not rendered
- `warning` `UI_NOT_RENDERED` samsung-ct-construction financials.gross_profit: Gross profit for 2023 exists but is not rendered
- `warning` `UI_NOT_RENDERED` dl-enc established_at: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` dl-enc representative: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` dl-enc employee_count: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` dl-enc major_businesses: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` dl-enc financials.gross_profit: Gross profit for 2025 exists but is not rendered
- `warning` `UI_NOT_RENDERED` dl-enc financials.gross_profit: Gross profit for 2024 exists but is not rendered
- `warning` `UI_NOT_RENDERED` dl-enc financials.gross_profit: Gross profit for 2023 exists but is not rendered
- `warning` `UI_TRUNCATED` dl-enc technology: 13 technology records are hidden by slice(0, 8)
- `warning` `UI_NOT_RENDERED` yuchang-enc established_at: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` yuchang-enc representative: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` yuchang-enc employee_count: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` yuchang-enc major_businesses: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` yuchang-enc financials.gross_profit: Gross profit for 2025 exists but is not rendered
- `warning` `UI_NOT_RENDERED` yuchang-enc financials.gross_profit: Gross profit for 2024 exists but is not rendered
- `warning` `UI_NOT_RENDERED` yuchang-enc financials.gross_profit: Gross profit for 2023 exists but is not rendered
- `warning` `UI_NOT_RENDERED` kumkang-kind established_at: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` kumkang-kind representative: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` kumkang-kind employee_count: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` kumkang-kind major_businesses: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` kumkang-kind financials.gross_profit: Gross profit for 2025 exists but is not rendered
- `warning` `UI_NOT_RENDERED` kumkang-kind financials.gross_profit: Gross profit for 2024 exists but is not rendered
- `warning` `UI_NOT_RENDERED` kumkang-kind financials.gross_profit: Gross profit for 2023 exists but is not rendered
- `warning` `UI_NOT_RENDERED` nrb established_at: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` nrb representative: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` nrb employee_count: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` nrb major_businesses: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` nrb financials.gross_profit: Gross profit for 2025 exists but is not rendered
- `warning` `UI_NOT_RENDERED` nrb financials.gross_profit: Gross profit for 2024 exists but is not rendered
- `warning` `UI_NOT_RENDERED` nrb financials.gross_profit: Gross profit for 2023 exists but is not rendered
- `warning` `UI_TRUNCATED` nrb technology: 8 technology records are hidden by slice(0, 8)
- `warning` `UI_NOT_RENDERED` planm established_at: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` planm representative: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` planm employee_count: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` planm major_businesses: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` planm financials.gross_profit: Gross profit for 2025 exists but is not rendered
- `warning` `UI_NOT_RENDERED` planm financials.gross_profit: Gross profit for 2024 exists but is not rendered
- `warning` `UI_NOT_RENDERED` planm financials.gross_profit: Gross profit for 2023 exists but is not rendered
- `warning` `UI_TRUNCATED` planm technology: 2 technology records are hidden by slice(0, 8)
- `warning` `UI_NOT_RENDERED` geogwang-enterprise established_at: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` geogwang-enterprise representative: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` geogwang-enterprise employee_count: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` geogwang-enterprise major_businesses: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` geogwang-enterprise financials.gross_profit: Gross profit for 2025 exists but is not rendered
- `warning` `UI_NOT_RENDERED` geogwang-enterprise financials.gross_profit: Gross profit for 2024 exists but is not rendered
- `warning` `UI_NOT_RENDERED` geogwang-enterprise financials.gross_profit: Gross profit for 2023 exists but is not rendered
- `warning` `UI_NOT_RENDERED` sungji-steel established_at: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` sungji-steel representative: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` sungji-steel employee_count: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` sungji-steel major_businesses: Field exists in companies.json but App.jsx does not render it
- `warning` `UI_NOT_RENDERED` sungji-steel financials.gross_profit: Gross profit for 2025 exists but is not rendered
- `warning` `UI_NOT_RENDERED` sungji-steel financials.gross_profit: Gross profit for 2024 exists but is not rendered
- `warning` `UI_NOT_RENDERED` sungji-steel financials.gross_profit: Gross profit for 2023 exists but is not rendered

## Recommendations

- Remove the technology detail slice limit or add pagination so all source technology records are reachable.
- Add profile rows for establishment date, representative, employee count, and major businesses.
- Add gross profit and margin display to the three-year financial table while keeping original KRW values unchanged.
