# Company Intelligence Workspace Redesign

## 변경 전 문제

- 생산시설 상세정보가 desktop table의 첫 번째 `th` 안에서 `<details>`로 펼쳐져 시설명 열 폭에 갇혔다.
- 생산시설 상세를 열면 한국어 본문이 한 글자 단위로 줄바꿈되고 table row 높이가 비정상적으로 커질 수 있었다.
- 프로젝트와 기술 상세 정보가 목록 안에서 바로 펼쳐져 desktop/mobile 모두 정보 위계가 약했다.
- 종합분석 카드의 `규칙 기반 요약` 문구가 내부 구현처럼 보였고, 최신 활동 제목이 사업 기회 결론처럼 읽힐 수 있었다.
- 기업 목록 필터에 감사재무 적용 여부와 생산시설 보유 여부가 분리되어 있지 않았다.

## 목표 정보구조

- Level 1: 기업 목록과 상세 헤더에서 시장 포지션, 최근 매출, 영업이익률, 생산시설, 검증 프로젝트를 빠르게 확인한다.
- Level 2: 종합분석, 재무, 생산시설, 프로젝트, 기술 탭에서 추세와 항목별 상세를 확인한다.
- Level 3: Drawer와 근거·출처 탭에서 원문 위치, 검증 방식, 데이터 공백을 확인한다.

## 공통 컴포넌트

- `CompanyEntityDrawer`: 생산시설, 프로젝트, 기술 상세를 위한 공통 drawer 패턴이다.
- 기존 `EvidenceDrawer`: 근거 확인 전용으로 유지하되 body scroll lock과 focus restore를 유지한다.
- 목록 필터는 기존 URL query 구조를 유지하면서 `audit`, `facility` 필터를 추가했다.

## 반응형 정책

- Desktop table은 요약 행만 표시하고 상세정보는 side drawer에서 표시한다.
- Mobile은 table을 억지로 축소하지 않고 기존 responsive card 목록과 full-width drawer를 사용한다.
- 일반 한국어 본문은 `word-break: keep-all` 흐름을 유지하고, 긴 코드·URL만 별도 token 스타일에서 줄바꿈한다.

## 접근성 정책

- 공통 Drawer는 `role="dialog"`, `aria-modal="true"`, visible title, close button을 제공한다.
- ESC, backdrop close, Tab focus trap, Shift+Tab reverse trap, 호출 버튼 focus restore를 제공한다.
- 상세 버튼은 table row 내부의 작동 가능한 control로 유지하고, nested drawer는 만들지 않는다.

## 변경 후 검증 결과

- 생산시설 상세는 더 이상 table `th` 또는 `td` 내부에 렌더링되지 않는다.
- 생산시설, 프로젝트, 기술 상세는 공통 Drawer에서 확인한다.
- source URL이 없는 항목은 Evidence/Source UI에서 작동하지 않는 원문 버튼을 만들지 않는 기존 정책을 유지한다.
- 감사재무 적용 5개 기업의 `company_report_insights.json` 값은 변경하지 않는다.

## 알려진 제한

- 현재 `origin/main`의 공개 `companies.json` 기준 기업 수는 10개다. 지시서의 11개 기업 목표와 다르지만, 이번 PR은 데이터 변경 금지 원칙에 따라 UI/derived presentation만 수정한다.
- 경쟁력 프로필은 임의 점수화하지 않고 기존 검증 지표와 데이터 공백 신호를 기반으로 표현한다.
- 브라우저 캡처 이미지는 저장소에 커밋하지 않고 QA 결과만 PR에 기록한다.
