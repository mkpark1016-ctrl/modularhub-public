# 공개 대시보드 기업정보 운영 정책

## 공개 메뉴

공개 ModularHub는 다음 3개 영역만 제공한다.

1. 사업정보
2. 뉴스정보
3. 기업정보

기업 모니터링 Review Queue는 내부 수집·검토 기능이며 공개 메뉴와 공개 Route에서 노출하지 않는다.

## 내부 모니터링

다음 기능은 내부 운영 자산으로 유지한다.

- `.github/workflows/company-intelligence-monitor.yml`
- `scripts/company_monitoring/`
- `tests/company_monitoring/`
- GitHub Actions Artifact 기반 raw/review queue/digest/audit

공개 브라우저는 DART 또는 NAVER API를 직접 호출하지 않으며 API Key를 전달받지 않는다.

## 기업정보 11개사

기존 검증 기업 10개사에 대승엔지니어링을 추가한다. 대승엔지니어링은 별도 보강 모듈로 병합되며, 동명 법인 혼입을 방지하기 위해 대표자 채윤석, 설립일 2009-04-09, 모듈러 특허 및 교육청 계약근거를 함께 사용한다.

## 데이터 신뢰도

- 공식·공공기관·특허 원문: 우선 근거
- 기업정보·채용·공장정보 플랫폼: 보조 근거
- 확인되지 않은 생산능력은 숫자로 추정하지 않는다.
- 상충 주소는 임의 통합하지 않고 조사 필요 상태로 표시한다.
- 제3자 재무는 감사보고서 대조 전까지 부분 검증으로 표시한다.

## 공개 Review Queue 제거

`frontend/public/data/company-intelligence/`의 Review Queue와 Manifest는 공개 배포 대상에서 제외한다. `/company-intelligence` 직접 접근은 Not Found 화면으로 처리한다.
