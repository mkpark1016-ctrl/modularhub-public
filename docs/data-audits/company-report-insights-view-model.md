# Company Report Insights View Model

## 목적

`company_report_insights_v1`은 `company_audit_financials_v1` 원천 데이터를 공개 대시보드가 읽기 쉬운 재무 인사이트 구조로 변환한 View Model이다.

UI는 감사보고서 원천 JSON을 직접 읽지 않는다. 원천 데이터는 감사·검증용이고, 공개 View Model은 표시 단위, 파생 지표, 경고, 출처 요약, 데이터 품질 정보를 포함한 읽기 전용 공개 계약이다.

## 데이터 흐름

1. `data/company_reports/<company_id>/*.json`에 원 단위 reported 값을 저장한다.
2. `scripts/validate_company_audit_financials.py`가 원천 데이터의 회계식, 출처, 정책, 보호 파일 변경 여부를 검증한다.
3. `scripts/build_company_report_insights.py`가 검증 통과 파일만 자동 탐색한다.
4. 생성기는 원 단위 값을 억원 표시값과 파생 지표로 변환한다.
5. 결과는 `frontend/public/data/companies/company_report_insights.json`에 저장된다.

## 원 단위와 억원 표시

- 계산은 항상 원 단위 `raw_krw`를 사용한다.
- `display_eok`은 `raw_krw / 100,000,000`을 소수점 1자리로 반올림한 값이다.
- `display_text`는 천 단위 구분을 적용한 억원 표기다.
- 표시용 억원 값은 다시 계산 입력으로 사용하지 않는다.

## 파생 지표

파생 지표는 원천 JSON에 저장하지 않는다. 생성기는 Validator의 계산 규칙을 재사용해 다음 값을 만든다.

- 매출 전년 대비 증감률
- 매출총이익률, 영업이익률, 순이익률
- 유동비율, 부채자본비율, 차입금자본비율
- 매출채권·재고자산 대비 매출 비율
- 영업현금흐름 대비 순이익
- 매출 구성 비중

## 경고와 Attribution

감사보고서가 모듈러 사업부문 별도 매출을 공시하지 않는 경우 View Model은 명확한 경고를 유지한다. 제품매출과 공사매출은 전체 금액을 모듈러 매출로 표현하지 않는다.

법인 귀속 주의사항은 `entity_attribution`과 `disclosure_warnings`에 유지한다. 유창이앤씨의 경우 유창엠앤씨 등 관계사 프로젝트·생산·매출을 유창이앤씨 별도 실적으로 자동 합산하지 않는다는 경고가 포함된다.

## Source Section 코드

`source_locations.section`은 인코딩에 안전한 표준 코드로 저장한다. 허용 코드는 `statement.income_statement`, `statement.balance_sheet`, `statement.cash_flow`, `note.revenue_breakdown`, `note.working_capital`, `note.borrowings`, `note.investment_signals`이다.

한국어 표시명은 후속 UI에서 코드 매핑으로 제공한다. `pending_manual_page_check`는 정확한 페이지 수동 확인이 남아 있다는 뜻이며, section 분류가 미확인이라는 뜻은 아니다.

## 새 기업 추가

새 기업 감사보고서 원천 파일을 `company_audit_financials_v1` 구조로 추가하고 Validator를 통과하면, 별도 코드 수정 없이 `build_company_report_insights.py`가 자동 탐색해 View Model에 포함한다.

검증 명령:

```powershell
python scripts\validate_company_audit_financials.py --base-ref origin/main
python scripts\build_company_report_insights.py
python scripts\build_company_report_insights.py --check
```

## 제한사항

이번 단계는 공개 View Model 생성까지만 수행한다. React 기업정보 UI는 아직 이 파일을 읽지 않는다. 기존 `companies.json`과 `company_intelligence_v2.json`은 직접 수정하지 않는다.
