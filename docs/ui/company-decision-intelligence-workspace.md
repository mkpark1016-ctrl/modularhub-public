# Company Decision Intelligence Workspace

기업 상세 화면은 공개 기업 데이터를 단순 나열하지 않고 의사결정에 필요한 질문을 빠르게 확인하는 구조로 표시한다.

## 구성

- 종합분석: Executive Summary, 최신 감사재무 스냅샷, 3개년 변화, 동료 비교 가능성을 표시한다.
- 재무: 감사보고서 View Model이 있는 기업은 의사결정 요약, 핵심 지표, 재무 추세, 동료 비교, 상세 표, 해석 범위와 출처를 표시한다.
- 근거·출처: Data Trust Center에서 영역별 검증 상태, 보류 수, 미공시 수, 출처 수를 보여준다.

감사보고서 View Model이 없는 기업은 기존 재무 UI를 유지하고, 임의 순위나 추정 문구를 만들지 않는다.

## View Model

`frontend/public/data/companies/company_report_insights.json`은 다음 파생 필드를 포함한다.

- `latest_snapshot`: 최신 연도 핵심 지표 묶음이다. 원천 금액은 기존 `latest_metrics`의 값을 그대로 참조한다.
- `trends`: 직전 연도 대비 변화 신호다. 변화 방향과 계산 근거만 표시한다.
- `financial_health`: 수익성, 현금창출력, 재무안정성, 운전자본, 공시 범위를 규칙 기반으로 요약한다.
- `evidence_health`: 재무와 공시 범위의 검증 위치, 수동 확인 필요, 미공시 상태를 분리한다.
- `peer_benchmarks`: 감사재무 기업 사이의 제한적 동료 비교 결과다.

## Peer Comparison Rules

동료 비교는 다음 조건을 모두 충족할 때만 `comparable=true`가 된다.

- 같은 metric definition
- 같은 currency/unit
- 같은 financial scope
- 같은 latest year
- 값이 있는 비교 대상 3개 이상

조건을 충족하지 못하면 `rank`는 `null`이며 `not_comparable_reason`을 표시한다. 사용자 임의 경쟁력 순위나 종합점수는 생성하지 않는다.

## Financial Health Rules

`financial_health`는 신용등급, 투자 판단, 안전기업 판정이 아니라 감사재무 수치를 빠르게 읽기 위한 관찰 규칙이다. 각 항목은 `rule_id`, `operator`, `threshold`, `actual_value`, `calculation_basis`, `interpretation_scope`를 함께 제공해야 한다.

| rule_id | Metric | Operator / Threshold | Meaning |
| --- | --- | --- | --- |
| `profitability_negative_margin` | `operating_margin_pct` | `< 0` | 영업이익률이 음수인지 관찰한다. |
| `positive_profit_negative_operating_cash_flow` | `operating_profit`, `operating_cash_flow` | `operating_profit > 0 and operating_cash_flow < 0` | 이익과 영업현금흐름 방향이 엇갈리는지 관찰한다. |
| `liabilities_to_equity_observation` | `liabilities_to_equity_pct` | `> 200` | 부채비율이 관찰 기준을 넘는지 표시한다. |
| `receivables_to_revenue_observation` | `receivables_to_revenue_pct` | `> 30` | 채권/매출 비율이 관찰 기준을 넘는지 표시한다. |
| `source_location_coverage_observation` | `source_locations` | `pending_location_count > 0` | 수동 출처 위치 확인이 남아 있는지 표시한다. |

허용 문구는 “관찰 필요”, “추가 확인 필요”, “공시 범위 확인 필요”처럼 검증 데이터의 해석 범위를 설명하는 표현이다. 금지 문구는 “우량기업”, “부실기업”, “안전기업”, “투자 추천”, “위험등급”, “종합 경쟁력 순위”처럼 평가·추천·등급으로 오인될 수 있는 표현이다.

## Data Trust Counts

Data Trust Center는 문자열 라벨을 분해해 출처 수를 추정하지 않는다. `distinct_source_count`는 고유 출처 기준, `source_type_counts`는 출처 유형별 분포 기준, `verified_item_count`·`pending_item_count`·`not_disclosed_item_count`·`not_applicable_item_count`·`verification_pending_item_count`는 항목 상태 기준으로 별도 표시한다.

`not_disclosed`는 검증 완료와 다르다. 예를 들어 모듈러 부문 별도 매출이 공시되지 않은 기업은 해당 항목을 “미공시”로 표시하고 `verified_item_count`에 더하지 않는다.

## Data Insufficiency

`latest_snapshot`은 존재하지 않는 metric key를 합성 `null` 값으로 채우지 않는다. UI는 키가 없거나 값이 `null`인 항목을 “확인되지 않음”, “공시되지 않음”, “해당 없음”, “검증 보류” 중 View Model의 명시 상태에 맞게 표시한다.

추세 카드에는 최신값, 직전값, 변화 금액 또는 변화율, 계산 불가 사유를 함께 표시한다. 분모가 0이거나 직전값이 없으면 `change_pct_unavailable_reason`을 표시하고 임의의 0% 변화율을 만들지 않는다.

## Null Semantics

- `0`: 유효한 보고값이며 화면에 표시한다.
- `null`: 값이 확인되지 않았거나 공시되지 않았다는 의미를 유지한다.
- `not_disclosed`: 공시되지 않은 항목이다.
- `not_applicable`: 해당하지 않는 항목이다.
- `verification_pending`: 수동 검증 보류 상태다.

UI는 위 값을 0으로 대체하지 않는다.

## QA

전용 브라우저 QA는 다음 명령으로 실행한다.

```powershell
cd frontend
npm.cmd run qa:company-intelligence-workspace
```

검증 범위는 `yuchang-enc`, `kumkang-kind`, `daeseung-engineering`, `planm`, `nrb`, `gs-ec`의 종합분석·재무·근거 탭이며 1440px, 390px, 320px 뷰포트를 확인한다.
