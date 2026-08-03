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
## Phase 7A-1A Drawer Stability Scope

### Completed In PR #44

- 생산시설 table 내부의 row-level `<details>`를 제거하고 `CompanyEntityDrawer`로 상세 정보를 이동했다.
- 생산시설, 프로젝트, 기술·특허 상세 패널은 같은 drawer interaction foundation을 공유한다.
- 기업 목록에는 감사재무 적용 여부와 확인 생산시설 보유 여부를 탐색하는 필터를 추가했다.
- 종합분석 탭의 최근 활동 표현은 기회 결론이 아니라 검증 데이터 기반 signal로 낮추어 표시한다.
- `browser-qa-sales.mjs`는 최신 business fixture에서 실제 `getBusinessPriorityInfo`가 산출한 review label을 검증하도록 조정했다. 중요 항목 label set이 비어 있으면 실패한다.

### Deferred To Phase 7A-2

- 종합분석 탭의 투자/영업 의사결정용 deep synthesis.
- 재무 탭의 cross-company audit insight 비교와 위험 요약 고도화.
- 근거·출처 탭의 source graph, confidence breakdown, unresolved field workflow.
- 기업 수 자체를 11개로 확장하는 source data 작업.

### Focus And Isolation Policy

- `CompanyEntityDrawer`는 `createPortal`로 `document.body` 아래에 렌더링한다.
- Drawer open 동안 React app root `#root`에는 `inert=true`와 `aria-hidden=true`를 적용하고 close cleanup에서 기존 값을 복원한다.
- body scroll lock은 open 동안 `document.body.style.overflow = "hidden"`으로 적용하고 cleanup에서 기존 overflow 값을 복원한다.
- 초기 focus는 close button이 아니라 drawer title `h2[tabIndex="-1"]`로 이동한다.
- `Tab`과 `Shift+Tab`은 drawer 내부 focusable element 사이에서 순환한다.
- `Escape`, backdrop click, close button으로 닫을 수 있고 close 후 최초 상세보기 trigger로 focus를 복원한다.
- Drawer 내부 `근거보기`를 누르면 entity drawer를 먼저 닫고 `EvidenceDrawer`만 열어 중첩 modal DOM을 남기지 않는다.

### Browser QA Command

```powershell
cd frontend
npm.cmd run qa:company-drawers
```

검사 범위:

- viewport: 1440x900, 390x844, 320x800
- 생산시설: tab 이동, 첫 상세보기, dialog semantics, inert, body scroll lock, focus trap, ESC, backdrop, focus restore
- 프로젝트/기술: detail drawer, evidence drawer transition, body overflow restore, focus restore
- 레이아웃: page/drawer horizontal overflow 없음, `word-break: break-all` 미사용, close button visible
- diagnostics: console error 0, React warning 0
