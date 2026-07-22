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

## Phase 4D 품질 감사

기업정보는 값 자체와 함께 검증 상태를 관리한다. 감사 기준은 법인·기본정보, 재무, 생산시설, 프로젝트, 기술·특허, 최근 동향, 출처, 검증 메타데이터로 나뉜다.

- `verified_primary`: 공식자료 검증
- `verified_cross_source`: 교차 검증
- `partially_verified`: 부분 검증
- `secondary_only`: 2차 자료 기준
- `conflicting`: 자료 상충
- `research_required`: 추가 확인 필요
- `not_publicly_available`: 공식자료 없음
- `not_applicable`: 해당 없음

재무는 회사 전체 재무와 모듈러 부문 재무를 구분하며, 연결·별도, 감사 여부, 통화·단위를 함께 표시한다. 모듈러 부문 매출이 공식적으로 분리되지 않으면 별도 재무가 공개자료에서 확인되지 않았다고 표시한다.

생산시설은 운영·계획·중단 상태와 자체 소유·임차·협력 관계를 구분한다. 계획 시설은 운영시설 KPI에 포함하지 않는다. 공식 생산능력이 없으면 숫자로 추정하지 않는다.

프로젝트는 검토, 제안, 우선협상, 입찰, MOU를 완료 실적으로 표시하지 않는다. 동일 프로젝트가 여러 기업에 연결될 수 있지만 각 기업의 역할을 분리해 기록한다.

특허는 출원번호와 등록번호를 구분하고, 권리자·출원인을 법인 Identity와 대조한다. 모듈러 직접 관련성이 불명확한 기술은 공개 모듈러 기술 count에 넣지 않는다.

품질 감사와 운영 보고서는 다음 파일로 생성한다.

- `research/company-enrichment/company-quality-audit.json`
- `research/company-enrichment/company-quality-audit.md`
- `research/company-enrichment/sources.json`
- `research/company-enrichment/conflict-report.md`
- `research/company-enrichment/research-gaps.md`
- `research/company-enrichment/change-report.json`
- `research/company-enrichment/change-report.md`

실행 명령:

```powershell
python scripts\audit_company_data_quality.py
```

## 공개 Review Queue 제거

`frontend/public/data/company-intelligence/`의 Review Queue와 Manifest는 공개 배포 대상에서 제외한다. `/company-intelligence` 직접 접근은 Not Found 화면으로 처리한다.
