# ModularHub

## 10.0 공개 웹서비스 방향

ModularHub는 기존 로컬 Streamlit 대시보드에서 **사업정보와 뉴스정보에 집중한 공개 웹서비스**로 전환합니다. 공개 화면은 Netlify에 배포 가능한 Vite React 정적 앱이며, Python 수집기와 SQLite는 서버/수집 단계에 그대로 남습니다.

공개 범위는 다음 두 가지입니다.

- **사업정보:** 나라장터 입찰공고, D2B 입찰공고, D2B 조달계획 중 공고명 또는 사업명에 `모듈러`가 포함된 실제 데이터
- **뉴스정보:** 네이버 뉴스 검색 API로 수집했으며 정확한 원문 URL이 확인된 모듈러 관련 뉴스

R&D, 특허, 트렌드, 블로그, 커뮤니티, 즐겨찾기, 로그인, AI 요약, 개발자 로그는 공개 앱에서 제거했습니다. 기존 Python 코드와 Streamlit 화면은 수집·운영 점검 및 회귀 테스트를 위해 유지합니다.

### 역할 분리

- `src/`, `scripts/`, `data/`: API Key를 사용하는 Python 수집 및 SQLite 저장
- `scripts/export_public_site_data.py`: 공개 가능한 필드만 정적 JSON으로 내보내기
- `frontend/`: API Key 없이 정적 JSON만 읽는 Vite React 공개 앱
- `netlify.toml`: Netlify 빌드와 SPA 라우팅 설정

프론트엔드에는 `DATA_GO_KR_SERVICE_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`을 넣지 않습니다. `source_detail_api_url`처럼 인증키가 포함될 가능성이 있는 값도 공개 JSON에서 제외됩니다.

### 공개 앱 로컬 실행

먼저 Python 수집 결과를 공개용 JSON으로 내보내고 보안 계약을 검사합니다.

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\export_public_json.py
.\.venv\Scripts\python.exe scripts\test_public_json_export.py
```

공개 JSON 파일:

- `frontend/public/data/business.json`: 나라장터·D2B의 모듈러 입찰/조달계획과 known important bid
- `frontend/public/data/news.json`: 원문 URL이 있는 모듈러 뉴스
- `frontend/public/data/meta.json`: 생성 시각, 건수, 출처, 마지막 수집 시각, 경고 수

공개 exporter는 mock/sample/test, R&D, 특허, 트렌드, 즐겨찾기 데이터를 포함하지 않습니다. `serviceKey`, 네이버 인증정보, 내부 DB 경로, 인증키가 포함된 상세 API URL도 제거합니다. 사업정보의 검증되지 않은 외부 URL은 `null`로 두고 `manual_check` 안내를 제공합니다.

권장 전체 실행 순서:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\collect_all.py
.\.venv\Scripts\python.exe scripts\collect_g2b_modular_scope.py
.\.venv\Scripts\python.exe scripts\collect_known_g2b_bids.py
.\.venv\Scripts\python.exe scripts\export_public_json.py
.\.venv\Scripts\python.exe scripts\test_public_json_export.py
```

그다음 프론트엔드를 실행합니다. PowerShell 실행 정책의 영향을 피하려면 `npm.cmd`를 사용합니다.

```bat
cd /d "D:\backup01\Documents\New project 2\frontend"
npm.cmd install
npm.cmd run dev
```

Vite가 출력한 로컬 주소에서 다음 경로를 확인합니다.

- `/`: 공개 홈
- `/business`: 모듈러 사업정보
- `/business/:id`: 사업정보 상세
- `/news`: 모듈러 뉴스정보
- `/news/:id`: 뉴스 상세

프로덕션 빌드:

```bat
cd /d "D:\backup01\Documents\New project 2\frontend"
npm.cmd run build
```

### Netlify 배포

1. 이 프로젝트를 GitHub 저장소에 push합니다.
2. Netlify에서 해당 저장소를 연결합니다.
3. 루트의 `netlify.toml` 설정을 사용해 배포합니다.
4. 새 데이터를 공개할 때 Python 수집기를 실행한 뒤 `scripts/export_public_site_data.py`를 실행하고, 변경된 `frontend/public/data/*.json`을 GitHub에 반영합니다.

Netlify 설정은 `frontend`를 base directory로, `npm run build`를 build command로, `frontend/dist`를 publish 결과로 사용합니다. SPA redirect가 설정되어 있어 상세 URL을 직접 열어도 React 라우터가 처리합니다.

> 현재 MVP는 **로컬 수집 → 정적 JSON export → GitHub push → Netlify 배포** 방식입니다. API Key는 Netlify나 브라우저에 배포되지 않습니다.

### Netlify 배포 전 브라우저 QA

Chrome이 설치된 환경에서 개발 서버를 실행한 후 실제 브라우저 자동 검사를 수행합니다.

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\export_public_json.py
.\.venv\Scripts\python.exe scripts\test_public_json_export.py

cd frontend
npm.cmd install
npm.cmd run lint
npm.cmd run build
npm.cmd run dev
```

다른 CMD 창에서:

```bat
cd /d "D:\backup01\Documents\New project 2\frontend"
npm.cmd run qa:browser
```

브라우저 QA는 다음을 자동 확인합니다.

- `/data/business.json`, `/data/news.json`, `/data/meta.json` 로딩과 건수 일치
- 홈의 사업정보·뉴스정보 CTA와 현재 공개 건수
- `/business` 검색, 유형 필터, 카드 렌더링
- `/business/:id` 직접 접속과 새로고침, 기관·공고번호·금액·확인 사이트·복사용 검색어
- `/news` 검색, 뉴스 카드와 원문 링크
- `/news/:id` 직접 접속과 새로고침, 매체·게시일·요약·원문 링크
- 공개 JSON의 API Key 관련 문자열 미포함

검사 스크린샷은 로컬 `frontend/qa-artifacts/`에 생성되며 Git에는 포함되지 않습니다.

Netlify SPA fallback은 `frontend/public/_redirects`와 `frontend/netlify.toml`에 모두 설정되어 있습니다.

```text
/* /index.html 200
```

Netlify 배포 후에도 `/business/{id}`와 `/news/{id}`를 주소창에 직접 입력하고 새로고침해 404가 발생하지 않는지 최종 확인합니다.

### 기존 로컬 대시보드

아래 내용은 수집 상태 확인과 내부 운영용 Streamlit 대시보드 안내입니다.

# 한국 모듈러 정보 대시보드

한국 모듈러, OSC, 프리패브, 공업화주택 관련 입찰·조달·뉴스·R&D·특허 정보를 한 곳에서 확인하기 위한 로컬 Streamlit 대시보드입니다.

1단계 버전은 외부 API를 연결하지 않고 `data/sample_items.csv` 샘플 데이터를 SQLite DB에 적재해 화면 구조와 실행 흐름을 먼저 검증합니다.

## 가장 권장하는 실행 방법

Windows PowerShell 실행 정책 때문에 `.venv\Scripts\activate` 또는 `run_local.ps1` 실행이 차단될 수 있습니다. 이 프로젝트에서는 PowerShell 스크립트 대신 BAT 파일 실행을 우선 권장합니다.

```bat
cd "D:\backup01\Documents\New project 2"
run_local.bat
```

실행 창을 닫지 않은 상태에서 브라우저로 아래 주소를 엽니다.

```text
http://127.0.0.1:8501
```

CMD 또는 PowerShell 창을 닫으면 Streamlit 서버도 종료됩니다.

## 8501 포트가 안 될 때

8501 포트가 충돌하거나 접속이 안 되면 8502 포트용 BAT 파일을 실행합니다.

```bat
cd "D:\backup01\Documents\New project 2"
run_local_8502.bat
```

브라우저 주소:

```text
http://127.0.0.1:8502
```

## PowerShell에서 직접 실행하는 방법

PowerShell 실행 정책을 바꾸지 않고도 아래처럼 가상환경 Python을 직접 호출할 수 있습니다.

```powershell
cd "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

## 실행 전 점검

샘플 데이터와 DB 상태를 확인합니다.

```powershell
cd "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

포트 상태를 확인합니다.

```bat
cd "D:\backup01\Documents\New project 2"
scripts\check_port.bat
```

## 2단계 수집 흐름 실행

2단계에서는 실제 외부 API를 호출하지 않고 `mock_collector`로 공통 수집 흐름을 검증합니다.

DB 테이블을 최신화합니다.

```powershell
cd "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe db\init_db.py
```

mock 수집기를 실행합니다.

```powershell
.\.venv\Scripts\python.exe scripts\collect_all.py
```

수집, 정규화, 중복 제거, 수집 로그 기록을 한 번에 점검합니다.

```powershell
.\.venv\Scripts\python.exe scripts\test_collector_flow.py
```

대시보드를 실행합니다.

```bat
run_local.bat
```

대시보드 하단의 “최근 수집 로그”에서 수집 결과를 확인할 수 있습니다.

## 3단계 나라장터 수집기 실행

나라장터 수집기는 공공데이터포털의 `조달청_나라장터 입찰공고정보서비스`를 사용합니다. 이 서비스는 물품, 용역, 공사 등 업무구분별 오퍼레이션이 나뉘어 있으므로 현재 버전에서는 공사와 용역 입찰공고 목록만 조회합니다.

먼저 공공데이터포털에서 API 활용신청 후 서비스키를 발급받고, 프로젝트 루트에 `.env` 파일을 만듭니다.

```text
DATA_GO_KR_SERVICE_KEY=발급받은_서비스키
G2B_LOOKBACK_DAYS=90
G2B_PAGE_SIZE=100
G2B_CONSTRUCTION_ENDPOINT=
G2B_SERVICE_ENDPOINT=
G2B_DETAIL_BASE_ENDPOINT=https://apis.data.go.kr/1230000/ad/BidPublicInfoService
G2B_DETAIL_USE_API_LINK=true
```

`G2B_CONSTRUCTION_ENDPOINT`, `G2B_SERVICE_ENDPOINT`는 기본값을 사용하면 비워 둡니다. 공공데이터포털 명세의 요청 URL이 계정별로 다르게 보이면 해당 값을 `.env`에서 덮어쓸 수 있습니다.

DB 테이블을 최신화합니다.

```powershell
.\.venv\Scripts\python.exe db\init_db.py
```

나라장터 수집기만 단독 실행합니다.

```powershell
.\.venv\Scripts\python.exe scripts\collect_g2b.py
```

나라장터 수집기 테스트를 실행합니다.

```powershell
.\.venv\Scripts\python.exe scripts\test_g2b_collector.py
```

전체 수집을 실행합니다. API Key가 없으면 G2B는 건너뛰고 mock 수집기만 실행됩니다.

```powershell
.\.venv\Scripts\python.exe scripts\collect_all.py
```

대시보드를 실행합니다.

```bat
run_local.bat
```

브라우저 주소:

```text
http://127.0.0.1:8501
```

API Key가 없으면 `DATA_GO_KR_SERVICE_KEY가 설정되어 있지 않습니다`라는 메시지가 출력됩니다. `.env`에 키를 추가한 뒤 다시 실행하세요. 공공데이터포털 호출 제한이 있으므로 너무 짧은 주기로 반복 실행하지 마세요.

## 4단계 LH 수집기 실행

이 프로젝트는 공공데이터포털 `DATA_GO_KR_SERVICE_KEY` 하나로 나라장터와 LH OpenAPI를 호출합니다. `LH_SERVICE_KEY`는 사용하지 않습니다.

LH 수집 전 공공데이터포털에서 “한국토지주택공사 입찰공고정보” OpenAPI 활용신청이 승인되어 있어야 합니다. 활용신청을 하지 않았거나 승인 반영 전이면 `30 SERVICE KEY IS NOT REGISTERED ERROR`가 발생할 수 있습니다.

`.env` 예시:

```text
DATA_GO_KR_SERVICE_KEY=공공데이터포털_일반_인증키
G2B_LOOKBACK_DAYS=90
G2B_PAGE_SIZE=100
LH_LOOKBACK_DAYS=180
LH_PAGE_SIZE=100
LH_OPENBID_ENDPOINT=https://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev
```

공식 API 요청 URL이 달라진 경우 `LH_OPENBID_ENDPOINT`에 입력해 기본 endpoint를 덮어쓸 수 있습니다.
현재 포털 화면 기준 LH endpoint는 아래입니다.

```text
https://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev
```

DB 테이블을 최신화합니다.

```powershell
.\.venv\Scripts\python.exe db\init_db.py
```

환경변수 상태를 확인합니다. 인증키 전체 값은 출력하지 않습니다.

```powershell
.\.venv\Scripts\python.exe scripts\check_env.py
```

LH 공식 샘플 날짜로 API 인증 상태를 진단합니다.

```powershell
.\.venv\Scripts\python.exe scripts\probe_lh_api.py
```

`probe_lh_api.py`는 HTTPS/HTTP와 `requests.get(params=...)`/수동 URL 조립 방식을 모두 비교합니다. `resultCode=00` 또는 `NORMAL SERVICE`가 나오면 해당 호출 방식이 정상입니다. 네 방식 모두 `resultCode=30`이면 공공데이터포털 키 반영 지연, 인증키 복사 오류, 활용신청 반영 지연, Encoding/Decoding 키 선택 문제를 확인하세요.

LH 수집기만 단독 실행합니다.

```powershell
.\.venv\Scripts\python.exe scripts\collect_lh.py
```

LH 수집기 테스트를 실행합니다.

```powershell
.\.venv\Scripts\python.exe scripts\test_lh_collector.py
```

전체 수집을 실행합니다.

```powershell
.\.venv\Scripts\python.exe scripts\collect_all.py
```

대시보드를 실행합니다.

```bat
run_local.bat
```

수집 결과가 0건이면 먼저 키가 해당 LH OpenAPI에 승인되어 있는지 확인하세요. 정상 승인된 키인데도 결과가 적으면 조회 기간을 늘려 테스트할 수 있습니다.

```text
LH_LOOKBACK_DAYS=180
```

API 호출 제한이 있으므로 너무 짧은 주기로 반복 실행하지 마세요.

## 5단계 D2B 조달계획 수집기 실행

D2B 조달계획 수집기는 방위사업청 군수품조달정보 조달계획 OpenAPI를 사용해 발주예정월, 대표품목명, 판단번호, 집행유형, 계약방법, 입찰방법, 발주기관, 예산금액, 진행상태를 수집합니다.

공공데이터포털에서 “방위사업청_군수품조달정보 조달계획” 활용신청이 필요합니다. 이 프로젝트는 `DATA_GO_KR_SERVICE_KEY` 하나로 G2B, LH, D2B를 호출합니다.

`.env` 예시:

```text
DATA_GO_KR_SERVICE_KEY=공공데이터포털_일반_인증키
D2B_LOOKAHEAD_MONTHS=12
D2B_PAGE_SIZE=50
D2B_PLAN_BASE_ENDPOINT=https://openapi.d2b.go.kr/openapi/service/PrcurePlanInfoService
D2B_PLAN_DOMESTIC_ENDPOINT=http://openapi.d2b.go.kr/openapi/service/PrcurePlanInfoService/getDmstcPrcurePlanList
D2B_PLAN_FACILITY_ENDPOINT=
```

D2B 진단을 실행합니다.

```powershell
.\.venv\Scripts\python.exe scripts\probe_d2b_plan_api.py
```

D2B 조달계획만 단독 수집합니다.

```powershell
.\.venv\Scripts\python.exe scripts\collect_d2b_plan.py
```

D2B 수집기 테스트를 실행합니다.

```powershell
.\.venv\Scripts\python.exe scripts\test_d2b_plan_collector.py
```

전체 수집을 실행합니다.

```powershell
.\.venv\Scripts\python.exe scripts\collect_all.py
```

대시보드를 실행합니다.

```bat
run_local.bat
```

권장 실행 순서:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\check_env.py
.\.venv\Scripts\python.exe scripts\probe_d2b_plan_api.py
.\.venv\Scripts\python.exe scripts\collect_d2b_plan.py
.\.venv\Scripts\python.exe scripts\test_d2b_plan_collector.py
.\.venv\Scripts\python.exe scripts\collect_all.py
run_local.bat
```

개발계정 트래픽이 작으므로 짧은 간격으로 반복 실행하지 마세요. 초기 버전은 최대 3페이지까지만 조회하고, 기간 중심으로 수집한 뒤 코드 내부에서 모듈러·시설·숙소 관련 키워드를 필터링합니다.

## 6단계 D2B 입찰공고 수집기 실행

D2B 입찰공고 수집기는 방위사업청 군수품조달정보 입찰공고 OpenAPI를 사용해 공고일자, 공고번호, 입찰명, 발주기관, 입찰참가등록 마감일시, 입찰서제출 마감일시, 개찰일시, 계약방법, 입찰방법, 업무구분을 수집합니다.

공공데이터포털에서 “방위사업청_군수품조달정보 입찰공고” 활용신청이 필요합니다. 이 프로젝트는 `DATA_GO_KR_SERVICE_KEY` 하나로 G2B, LH, D2B 조달계획, D2B 입찰공고를 호출합니다. 별도 D2B 입찰공고 전용 키는 사용하지 않습니다.

D2B 입찰공고 endpoint는 공공데이터포털 화면에서 서비스 기본 경로로만 보일 수 있으므로, 먼저 `probe_d2b_bid_api.py`로 정상 호출되는 상세기능 endpoint와 날짜 파라미터를 확인합니다.

`.env` 예시:

```text
DATA_GO_KR_SERVICE_KEY=공공데이터포털_일반_인증키
D2B_BID_LOOKBACK_DAYS=90
D2B_BID_PAGE_SIZE=50
D2B_BID_BASE_ENDPOINT=https://openapi.d2b.go.kr/openapi/service/BidPblancInfoService
D2B_BID_DOMESTIC_ENDPOINT=
D2B_BID_FOREIGN_ENDPOINT=
D2B_BID_PUBLIC_PRIVATE_ENDPOINT=
```

권장 실행 순서:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\check_env.py
.\.venv\Scripts\python.exe scripts\probe_d2b_bid_api.py
.\.venv\Scripts\python.exe scripts\collect_d2b_bid.py
.\.venv\Scripts\python.exe scripts\test_d2b_bid_collector.py
.\.venv\Scripts\python.exe scripts\collect_all.py
run_local.bat
```

개발계정 트래픽이 작을 수 있으므로 짧은 간격으로 반복 실행하지 마세요. 수집 결과가 0건이면 최근 30일/90일 내 키워드 매칭 공고가 없을 수 있으므로 `.env`의 `D2B_BID_LOOKBACK_DAYS=180`으로 늘려 테스트할 수 있습니다.

## 7단계 네이버 뉴스 수집기 실행

네이버 뉴스 수집기는 네이버 검색 API의 뉴스 검색 결과를 사용해 모듈러 건축, OSC, 공업화주택, 프리패브, 스마트건설, 공공기관, 경쟁사 관련 시장 뉴스를 수집합니다. 뉴스 본문 크롤링은 하지 않고 네이버 뉴스 검색 API가 제공하는 제목, 요약, 게시일, 링크만 저장합니다.

네이버 개발자센터에서 애플리케이션을 등록하고 검색 API 사용 신청을 한 뒤, `NAVER_CLIENT_ID`와 `NAVER_CLIENT_SECRET`을 `.env`에 넣어야 합니다. 두 값은 코드에 하드코딩하지 않습니다.

`.env` 예시:

```text
NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=
NAVER_NEWS_LOOKBACK_DAYS=14
NAVER_NEWS_DISPLAY=50
NAVER_NEWS_SORT=date
NAVER_NEWS_ENDPOINT=https://openapi.naver.com/v1/search/news.json
```

권장 실행 순서:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\check_env.py
.\.venv\Scripts\python.exe scripts\probe_naver_news_api.py
.\.venv\Scripts\python.exe scripts\collect_naver_news.py
.\.venv\Scripts\python.exe scripts\test_naver_news_collector.py
.\.venv\Scripts\python.exe scripts\collect_all.py
run_local.bat
```

네이버 뉴스 API 호출량을 줄이기 위해 너무 짧은 간격으로 반복 실행하지 마세요. `collect_all.py`는 네이버 키가 없으면 뉴스 수집만 건너뛰고 기존 공공데이터포털 기반 수집은 계속 실행합니다.

## 7.5단계 데이터 신뢰성 보정

운영 대시보드는 기본적으로 실제 수집 데이터만 표시합니다. `mock_collector`는 개발 테스트용으로 남아 있지만 `collect_all.py` 기본 실행에서는 제외되며, 필요한 경우에만 아래처럼 명시적으로 실행합니다.

```bat
.\.venv\Scripts\python.exe scripts\collect_all.py --include-mock
```

기존 DB에 들어간 mock/sample/test 데이터는 아래 명령으로 삭제할 수 있습니다.

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe db\init_db.py
.\.venv\Scripts\python.exe scripts\purge_mock_data.py
.\.venv\Scripts\python.exe scripts\audit_data_quality.py
```

링크 유형:

- `exact`: API 응답 또는 뉴스 `originallink` 기준 실제 원문으로 판단되는 링크
- `search`: 직접 상세 URL이 없어 공고번호 등으로 찾아야 하는 검색 성격 링크
- `portal`: 출처 포털 상위 페이지
- `unknown`: 원문 또는 검색 링크를 판단할 수 없음

링크 상태:

- `ok`: `check_links.py` 점검 결과 HTTP 200~399
- `broken`: 요청 실패 또는 HTTP 400 이상
- `unchecked`: 아직 점검하지 않음
- `unknown`: 상태를 알 수 없음

정확 원문이 아닌 `search`/`portal` 링크는 운영 대시보드에서 클릭 가능하게 표시하지 않습니다. 뉴스는 `originallink`를 우선 원문 링크로 사용하고, 없을 때는 정확 원문 링크 미확인으로 둡니다.

링크 일부 점검:

```bat
.\.venv\Scripts\python.exe scripts\check_links.py --limit 30
```

운영 권장 실행 순서:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe db\init_db.py
.\.venv\Scripts\python.exe scripts\purge_mock_data.py
.\.venv\Scripts\python.exe scripts\audit_data_quality.py
.\.venv\Scripts\python.exe scripts\collect_all.py
.\.venv\Scripts\python.exe scripts\check_links.py --limit 30
run_local.bat
```

R&D·특허 수집기는 다음 단계에서 구현합니다. 준비 환경변수는 `.env.example`의 `NTIS_API_KEY`, `KIPRIS_API_KEY`, `RND_LOOKBACK_DAYS`, `PATENT_LOOKBACK_DAYS`를 사용합니다.

## 7.6단계 정확 원문 링크 표시 정책

운영 대시보드는 정확 원문 링크만 표시합니다. 검색 페이지, 포털 상위 페이지, 임의로 조합한 URL은 클릭 가능한 링크로 제공하지 않습니다. LH/D2B/일부 G2B처럼 API에서 브라우저로 바로 열 수 있는 상세 URL이 검증되지 않은 항목은 “정확 원문 링크 미확인”으로 표시하고, 공고번호와 기관명을 함께 보여줍니다.

표시 정책:

- `link_type=exact` 또는 `exact_api`이고 `original_url`이 있으며 `link_status=ok` 또는 `unchecked`: 원문 열기
- `link_status=broken`: 링크 오류
- `link_type=search`, `portal`, `unknown`, `sample`, `mock`: 클릭 링크 표시 안 함
- `original_url` 없음: 정확 원문 링크 미확인

뉴스는 네이버 뉴스 API의 `originallink`를 원문 링크로 사용합니다. `check_links.py --clear-invalid` 실행 시 오류 페이지, 세션 오류, 본문 불일치가 감지된 뉴스 링크는 원문 링크에서 제거됩니다.

실행 순서:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe db\init_db.py
.\.venv\Scripts\python.exe scripts\clear_non_exact_links.py
.\.venv\Scripts\python.exe scripts\check_links.py --limit 50 --clear-invalid
.\.venv\Scripts\python.exe scripts\audit_data_quality.py
run_local.bat
```

## 8.0단계 상세 원문 링크 검증 기반

나라장터, LH, D2B의 상세 원문 링크는 출처별 URL 구조가 안정적으로 검증되기 전까지 대시보드에 표시하지 않습니다. `resolve_deep_links.py`는 출처번호와 후보 URL을 기준으로 상세 링크 후보를 검증하고, 성공한 경우에만 `original_url`, `link_type=exact`, `link_status=ok`, `exact_url_verified=1`로 저장합니다.

현재 기본 후보 생성 정책은 보수적으로 동작합니다.

- 뉴스: 네이버 `originallink`를 후보로 사용
- 나라장터/LH/D2B: 검증된 상세 URL 패턴 또는 `source_detail_api_url`이 없으면 후보 없음
- 검증 실패 또는 후보 없음: `original_url` 비움, 대시보드에는 정확 원문 링크 미확인 표시

실행 명령:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe db\init_db.py
.\.venv\Scripts\python.exe scripts\audit_deep_links.py
.\.venv\Scripts\python.exe scripts\resolve_deep_links.py --source G2B --limit 10 --dry-run
run_local.bat
```

후보 검증을 실제 DB에 반영하려면 `--apply`를 사용합니다.

```bat
.\.venv\Scripts\python.exe scripts\resolve_deep_links.py --source LH --limit 50 --apply
```

## 8.1단계 나라장터 상세 API 링크

나라장터 항목은 공고번호(`bidNtceNo`)와 공고차수(`bidNtceOrd`)를 `source_record_id`, `source_record_no`로 저장합니다. 브라우저에서 바로 열리는 상세 원문 URL은 검증 전까지 표시하지 않고, 공공데이터포털 상세 API 호출이 검증된 경우에만 `source_detail_api_url`에 저장해 `link_type=exact_api`로 구분합니다.

대시보드 표시 정책:

- 검증된 브라우저 상세 URL: `원문 열기`
- 검증된 나라장터 상세 API URL: `상세 API 보기`
- 검증되지 않은 검색/포털/상위 페이지: 표시하지 않음
- 정확 링크가 없는 항목: `정확 원문 링크 미확인`

`.env` 예시:

```text
DATA_GO_KR_SERVICE_KEY=공공데이터포털_일반_인증키
G2B_DETAIL_BASE_ENDPOINT=https://apis.data.go.kr/1230000/ad/BidPublicInfoService
G2B_DETAIL_USE_API_LINK=true
```

실행 명령:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\probe_g2b_detail_link.py
.\.venv\Scripts\python.exe scripts\resolve_g2b_detail_links.py --limit 30 --dry-run
.\.venv\Scripts\python.exe scripts\resolve_g2b_detail_links.py --limit 30 --apply
.\.venv\Scripts\python.exe scripts\audit_deep_links.py
run_local.bat
```

## 8.1-R단계 나라장터 실제 재수집과 API 상세 보기

나라장터 데이터가 없으면 먼저 진단과 재수집을 실행합니다. 목록 API는 조회 기간 제한이 있어 수집기는 7일 단위로 나눠 호출하고, 윈도우별 최대 3페이지까지만 처리합니다.

나라장터는 브라우저 상세 URL이 검증되지 않은 경우에도 공공데이터포털 API 응답을 공식 원문 근거로 사용할 수 있습니다. `resolve_g2b_detail_links.py --apply`는 상세 API 후보가 404인 경우 목록 조회 API를 공고번호와 게시일 기준으로 다시 호출해 단건 근거 응답을 `source_details` 테이블에 저장합니다. 검증된 API 응답은 `link_type=exact_api`, `api_detail_verified=1`로 표시되며, 대시보드 상세 보기에서 `API 상세 보기`로 확인할 수 있습니다.

실행 명령:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\diagnose_g2b_records.py
.\.venv\Scripts\python.exe scripts\collect_g2b.py
.\.venv\Scripts\python.exe scripts\diagnose_g2b_records.py
.\.venv\Scripts\python.exe scripts\resolve_g2b_detail_links.py --limit 20 --dry-run
.\.venv\Scripts\python.exe scripts\resolve_g2b_detail_links.py --limit 20 --apply
.\.venv\Scripts\python.exe scripts\audit_deep_links.py
run_local.bat
```

## 8.2단계 LH 상세 URL 검증

LH 전자조달은 세션과 포털 화면 구조 때문에 공고번호만으로 만든 URL이 오류 페이지로 이동할 수 있습니다. 이 프로젝트는 LH 목록 페이지나 포털 상위 페이지를 운영 대시보드 링크로 표시하지 않습니다. `probe_lh_deep_link.py`와 `resolve_lh_deep_links.py`는 공고번호(`source_record_id`, `bidNum`) 기반 상세 URL 후보를 requests로 검증하고, 응답 본문에서 공고번호 또는 제목 일부가 확인된 경우에만 `original_url`, `link_type=exact`, `link_status=ok`, `exact_url_verified=1`로 저장합니다.

`.env` 예시:

```text
LH_PORTAL_BASE_URL=https://ebid.lh.or.kr
LH_BID_LIST_URL=https://ebid.lh.or.kr/ebid.et.tp.cmd.BidMasterListCmd.dev
LH_DEEP_LINK_PROBE_ENABLED=true
```

표시 정책:

- 검증 성공한 LH 상세 URL: `원문 열기`
- 검증 실패 또는 오류 페이지: `정확 원문 링크 미확인`
- LH 목록 페이지: 클릭 링크로 표시하지 않음
- 정확 링크가 없는 항목: 공고번호와 기관명을 기준으로 LH e-Bid에서 수동 확인

실행 명령:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\probe_lh_deep_link.py
.\.venv\Scripts\python.exe scripts\resolve_lh_deep_links.py --limit 30 --dry-run
.\.venv\Scripts\python.exe scripts\resolve_lh_deep_links.py --limit 30 --apply
.\.venv\Scripts\python.exe scripts\audit_deep_links.py
run_local.bat
```

## 8.2-R단계 LH OpenAPI 상세 보기와 수동 확인

LH 상세 브라우저 URL은 SSL 인증서 체인, 세션, 포털 화면 구조 때문에 requests 검증이 실패할 수 있습니다. 이 경우 `original_url`은 비워 두고 오류 페이지 링크도 표시하지 않습니다. 대신 `resolve_lh_deep_links.py --apply`가 현재 `items`에 저장된 LH OpenAPI 메타데이터를 `source_details`에 저장하며, 대시보드 상세 화면에서 `API 상세 보기`로 공고번호, 공고명, 담당지역, 추정가격/금액, 게시일, 마감일, 원본 API 응답을 확인할 수 있습니다.

LH 항목에 정확 원문 링크가 없으면 대시보드는 `원문 열기` 대신 `수동 확인 가이드`를 표시합니다. 가이드에는 `LH 전자조달`, 공고번호, 공고명, 담당지역, 게시일, 마감일이 표시되며, `확인 사이트 열기` 버튼은 원문 링크가 아니라 사용자가 공고번호 또는 공고명으로 직접 조회할 사이트 링크입니다.

실행 명령:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\resolve_lh_deep_links.py --limit 30 --apply
.\.venv\Scripts\python.exe scripts\audit_deep_links.py
run_local.bat
```

## 8.3단계 D2B 상세 URL 검증

D2B 조달계획과 입찰공고는 판단번호 또는 공고번호를 `source_record_id`로 표시합니다. D2B 포털 상세 URL은 내부 파라미터, 세션, 화면 경로에 의존할 수 있으므로 메인/목록/통합검색 링크는 운영 대시보드에 표시하지 않습니다. 후보 URL은 `probe_d2b_deep_link.py`와 `resolve_d2b_deep_links.py`로 검증하고, 응답 본문에서 출처번호 또는 제목 일부가 확인된 경우에만 원문 링크로 승격합니다.

`.env` 예시:

```text
D2B_PORTAL_BASE_URL=https://www.d2b.go.kr
D2B_DEEP_LINK_PROBE_ENABLED=true
D2B_PLAN_DEEP_LINK_CANDIDATES=
D2B_BID_DEEP_LINK_CANDIDATES=
```

표시 정책:

- 검증 성공한 D2B 상세 URL: `원문 열기`
- 검증 실패 또는 404/로그인/세션 페이지: `정확 원문 링크 미확인`
- D2B 메인/목록/통합검색 링크: 표시하지 않음
- 정확 링크가 없는 항목: 판단번호 또는 공고번호로 D2B에서 수동 확인

실행 명령:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\probe_d2b_deep_link.py
.\.venv\Scripts\python.exe scripts\resolve_d2b_deep_links.py --source-type bid --limit 30 --dry-run
.\.venv\Scripts\python.exe scripts\resolve_d2b_deep_links.py --source-type bid --limit 30 --apply
.\.venv\Scripts\python.exe scripts\resolve_d2b_deep_links.py --source-type procurement_plan --limit 30 --apply
.\.venv\Scripts\python.exe scripts\audit_deep_links.py
run_local.bat
```

## 8.3-R단계 D2B OpenAPI 상세 보기와 수동 확인

D2B 포털 상세 URL 후보가 404 또는 세션/화면 구조 문제로 실패하면 해당 URL은 `original_url`에 저장하지 않습니다. D2B 메인, 목록, 통합검색 링크도 운영 대시보드에서 원문 링크로 표시하지 않습니다. 대신 `resolve_d2b_deep_links.py --apply`가 현재 `items`에 저장된 D2B 조달계획/입찰공고 OpenAPI 메타데이터를 `source_details`에 저장하고, 대시보드 상세 화면에서 `API 상세 보기`로 확인할 수 있게 합니다.

D2B 조달계획은 판단번호, 발주예정월, 대표품목명, 발주기관, 예산금액, 계약방법, 입찰방법, 진행상태를 확인합니다. D2B 입찰공고는 공고번호, 입찰명, 발주기관, 계약방법, 입찰방법, 업무구분, 입찰참가등록 마감, 입찰서제출 마감, 개찰일시를 확인합니다.

정확 원문 링크가 없는 D2B 항목은 `원문 열기` 대신 `수동 확인 가이드`를 표시합니다. `D2B 국방전자조달 열기`는 원문 링크가 아니라 판단번호, 공고번호 또는 제목으로 직접 조회하기 위한 `확인 사이트 열기` 버튼입니다.

실행 명령:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\resolve_d2b_deep_links.py --source-type bid --limit 30 --apply
.\.venv\Scripts\python.exe scripts\resolve_d2b_deep_links.py --source-type procurement_plan --limit 30 --apply
.\.venv\Scripts\python.exe scripts\audit_deep_links.py
run_local.bat
```

## 8단계 대시보드 고도화

대시보드는 “한국 모듈러 정보 데일리 브리핑” 형태로 구성되어 매일 아침 입찰·공고, 조달계획, 뉴스 데이터를 빠르게 훑고 우선순위를 판단할 수 있게 합니다. DB 저장값은 그대로 두고 화면에서만 `bid`는 입찰·공고, `procurement_plan`은 조달계획, `news`는 뉴스로 표시합니다.

화면 구성:

- 상단 KPI: 전체 데이터, 최근 24시간 신규, 입찰·공고, 조달계획, 뉴스, 마감 7일 이내, 관련도 8점 이상
- 오늘의 우선 확인: 마감임박 입찰, 고관련도 항목, D2B 조달계획, 최근 뉴스, 경쟁사 관련 뉴스를 우선 표시
- 사이드바 필터: 검색어, source_type, source_name, 게시일 기간, 마감일 범위, 최소 관련도, 키워드, 빠른 보기 체크박스
- 탭: 전체, 입찰·공고, 조달계획, 뉴스, 마감임박, 고관련도, 수집로그
- 차트: source_type별 건수, source_name별 건수, 최근 14일 게시일 기준 추이, 관련도 구간별 건수
- 상세 보기: 테이블 선택 또는 선택 상자로 제목, 출처, 기관, 게시일, 마감일, 금액, 지역, 관련도, 키워드, 요약, 원문 링크 확인
- CSV 다운로드: 현재 필터가 적용된 결과를 `modular_dashboard_filtered_YYYYMMDD.csv` 형식으로 다운로드

실행 명령:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\collect_all.py
run_local.bat
```

## 8.4단계 출처 확인 UX

대시보드는 출처 확인 방식을 네 가지로 구분합니다.

- `원문 확인됨`: 검증된 exact URL이 있어 `원문 열기`를 제공합니다.
- `API 상세 있음`: 외부 상세 URL은 없지만 공공데이터 OpenAPI 응답을 `API 상세` 탭에서 확인할 수 있습니다.
- `수동 확인 필요`: 공고번호, 판단번호, 공고명 등으로 해당 사이트에서 직접 조회합니다.
- `링크 없음`: 원문 또는 수동 확인 정보가 부족한 항목입니다.

상세 보기 패널은 `요약`, `API 상세`, `수동 확인`, `원본 Raw` 탭으로 구성됩니다. 뉴스는 검증된 원문 링크가 있으면 `원문 열기`만 표시합니다. 나라장터, LH, D2B는 검증된 원문 링크가 없더라도 `API 상세` 탭에서 수집된 공식 OpenAPI 응답을 확인하고, `수동 확인` 탭에서 공고번호/판단번호와 확인 사이트를 확인할 수 있습니다.

수동 확인 기준:

- 나라장터: 나라장터에서 공고번호, 공고차수, 공고명, 공고기관으로 검색
- LH: LH 전자조달 입찰공고 조회에서 공고번호, 공고명, 담당지역으로 검색
- D2B: D2B 통합검색 또는 입찰공고/조달계획 메뉴에서 판단번호, 공고번호, 입찰명, 발주기관으로 검색

## 8.5-1단계 탭별 상세 보기 선택

전체, 입찰·공고, 조달계획, 뉴스, 마감임박, 고관련도 탭의 테이블 행을 클릭하면 하단 공통 상세 보기 영역에 같은 `items.id` 기준으로 상세 정보가 표시됩니다. 선택이 잘 되지 않으면 상세 보기의 선택 상자에서 항목을 고를 수 있으며, 이 경우에도 같은 `selected_item_id`를 사용합니다.

선택 상태를 확인하려면 사이드바에서 `선택 상태 디버그 보기`를 켜세요. `selected_item_id`, `selected_tab_key`, `last_selection_source`, `last_selected_row_index`, `last_selected_table_key`, 탭별 dataframe 건수를 확인할 수 있습니다. 이 기능은 `st.dataframe` 행 선택 기능이 있는 Streamlit 1.35.0 이상에서 사용하세요.

테스트 명령:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\test_dashboard_selection_logic.py
run_local.bat
```

## 8.6단계 나라장터 중요 공고 누락 점검

나라장터 수집기는 공사, 용역, 물품 입찰공고를 함께 조회합니다. 취소공고와 정정공고는 수집 단계에서 버리지 않고 `공고상태`, `공고차수`, `업무구분`으로 표시합니다. 나라장터 중복 판단은 제목이 아니라 `공고번호 + 공고차수 + 업무구분`을 우선 사용합니다.

중요 공고는 [config/known_important_bids.json](/D:/backup01/Documents/New%20project%202/config/known_important_bids.json)에 회귀 테스트 대상으로 등록합니다. 예를 들어 `R26BK01510994` 성의여자고등학교 임시교사(모듈러교실) 공고는 `001` 차수, `용역`, `취소공고` 상태로 확인됩니다.

누락 점검 명령:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\diagnose_missing_g2b_bid.py --bid-no R26BK01510994 --title-keyword 성의여자고등학교
.\.venv\Scripts\python.exe scripts\probe_g2b_known_bid.py --bid-no R26BK01510994
.\.venv\Scripts\python.exe scripts\collect_g2b.py --lookback-days 30 --include-cancelled --debug-bid-no R26BK01510994
.\.venv\Scripts\python.exe scripts\test_known_important_bids.py
run_local.bat
```

대시보드에서는 `입찰·공고` 탭에서 공고번호, 공고차수, 공고상태, 업무구분을 확인할 수 있습니다. 검색창에는 공고번호 `R26BK01510994` 또는 학교명 `성의여자고등학교`를 입력해 찾을 수 있습니다.

## 8.6-A단계 나라장터 모듈러 물품 운영 수집

운영 기본 기준은 `나라장터 + 물품 + 공고명 모듈러 포함`입니다. 모든 나라장터 공고를 넓게 가져오면 업무 검토량이 커지므로, `collect_g2b_modular_items.py`는 물품 입찰공고 목록 API만 호출하고 제목에 `모듈러`가 포함된 항목만 저장합니다. 공백 차이는 무시하므로 `모듈러교실`, `모듈러 교실`, `모듈러주택`, `모듈러 주택`처럼 붙거나 띄어진 제목을 함께 잡습니다.

성의여자고등학교처럼 용역 성격의 중요 공고는 운영 물품 필터에서는 제외될 수 있습니다. 이런 예외는 `config/known_important_bids.json`에 등록하고 `test_known_important_bids.py`로 별도 회귀 테스트합니다.

환경변수 예시:

```text
G2B_MODULAR_ITEM_ONLY=true
G2B_MODULAR_TITLE_KEYWORD=모듈러
G2B_BUSINESS_TYPE=물품
G2B_ITEM_LOOKBACK_DAYS=90
G2B_ITEM_PAGE_SIZE=100
G2B_INCLUDE_CANCELLED=true
G2B_INCLUDE_CORRECTION=true
```

실행 명령:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\check_env.py
.\.venv\Scripts\python.exe scripts\collect_g2b_modular_items.py
.\.venv\Scripts\python.exe scripts\diagnose_g2b_modular_item_coverage.py
.\.venv\Scripts\python.exe scripts\test_known_important_bids.py
run_local.bat
```

대시보드에서는 사이드바에서 `나라장터 모듈러 물품만 보기`, `공고명 모듈러 포함`, `업무구분=물품` 필터를 사용해 운영 기준 데이터를 확인합니다.

## 8.6-B단계 중요 모듈러 공고 회귀 테스트

운영 기본 수집 범위가 `나라장터 + 물품 + 공고명 모듈러 포함`으로 좁아져도, 사용자가 지정한 중요 공고는 별도 회귀 테스트로 추적합니다. 중요 공고 목록은 `config/known_important_bids.json`에 등록합니다.

현재 등록된 중요 공고:

- `R26BK01510994-001`: 성의여자고등학교 임시교사(모듈러교실) 제작·설치 및 임차용역
- 업무구분: 용역 또는 확인 필요
- 비고: 운영 물품 필터에서는 제외될 수 있으므로 별도 추적

대시보드는 중요 공고 전체 수, DB 존재 수, 누락 수를 표시합니다. 누락이 있으면 `collect_known_g2b_bids.py` 실행을 안내합니다. 사이드바의 `중요공고만 보기`와 `운영 필터 외 중요공고 포함` 필터로 중요 공고를 확인할 수 있습니다.

실행 명령:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\probe_g2b_known_bid.py --bid-no R26BK01510994
.\.venv\Scripts\python.exe scripts\collect_known_g2b_bids.py
.\.venv\Scripts\python.exe scripts\test_known_important_bids.py
run_local.bat
```

브라우저에서 아래 주소를 엽니다.

```text
http://127.0.0.1:8501
```

## 최초 설치

```powershell
cd "D:\backup01\Documents\New project 2"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe db\init_db.py
.\.venv\Scripts\python.exe scripts\load_sample_data.py
```

환경변수 예시는 `.env.example`에 있습니다. 실제 API 키나 비밀번호를 넣은 `.env` 파일은 커밋하지 않습니다.

## 화면에서 확인할 수 있는 항목

- 전체 건수 KPI
- 최근 24시간 신규 KPI
- 입찰·공고 건수 KPI
- 조달계획 건수 KPI
- 뉴스 건수 KPI
- 마감 7일 이내 KPI
- 관련도 8점 이상 KPI
- R&D/특허 건수 KPI
- 오늘의 우선 확인
- 검색창
- 출처 유형 필터
- 출처명 필터
- 기간/마감일/관련도/키워드 필터
- 전체/입찰·공고/조달계획/뉴스/마감임박/고관련도/수집로그 탭
- source_type/source_name/최근 14일/관련도 차트
- 키워드 필터
- 데이터 테이블
- 선택한 행의 상세 정보
- 클릭 가능한 원문 링크
- 필터 적용 결과 CSV 다운로드

## 오류 해결

### PSSecurityException 또는 UnauthorizedAccess

PowerShell 실행 정책 때문에 `.ps1` 파일이 막힌 상태입니다. 실행 정책을 바꾸지 말고 BAT 파일을 사용하세요.

```bat
run_local.bat
```

### ERR_CONNECTION_REFUSED

Streamlit 서버가 실행 중이 아니거나 실행 창이 닫힌 상태입니다.

```bat
run_local.bat
```

실행 창을 닫지 않은 채 `http://127.0.0.1:8501`에 접속하세요.

### 포트 충돌

포트 상태를 확인합니다.

```bat
scripts\check_port.bat
```

8501이 사용 중이면 8502로 실행합니다.

```bat
run_local_8502.bat
```

### 모듈 없음

패키지를 다시 설치합니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### DB 파일 없음 또는 데이터 없음

DB 생성과 샘플 데이터 적재를 다시 실행합니다.

```powershell
.\.venv\Scripts\python.exe db\init_db.py
.\.venv\Scripts\python.exe scripts\load_sample_data.py
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

## 폴더 구조

```text
modular-info-dashboard/
├─ app.py
├─ run_local.bat
├─ run_local_8502.bat
├─ run_local.ps1
├─ requirements.txt
├─ README.md
├─ .gitignore
├─ .env.example
├─ .streamlit/
│  └─ config.toml
├─ data/
│  └─ sample_items.csv
├─ db/
│  └─ init_db.py
├─ src/
│  ├─ __init__.py
│  ├─ collector_runner.py
│  ├─ config.py
│  ├─ database.py
│  ├─ dedup.py
│  ├─ dashboard_data.py
│  ├─ keywords.py
│  ├─ link_resolver.py
│  ├─ models.py
│  ├─ normalizer.py
│  ├─ sample_loader.py
│  ├─ utils.py
│  └─ collectors/
│     ├─ __init__.py
│     ├─ base.py
│     ├─ d2b_bid.py
│     ├─ d2b_plan.py
│     ├─ g2b.py
│     ├─ lh.py
│     ├─ mock_collector.py
│     └─ naver_news.py
└─ scripts/
   ├─ check_port.bat
   ├─ check_port.ps1
   ├─ check_env.py
   ├─ check_links.py
   ├─ collect_all.py
   ├─ collect_d2b_bid.py
   ├─ collect_d2b_plan.py
   ├─ collect_g2b.py
   ├─ collect_lh.py
   ├─ collect_naver_news.py
   ├─ load_sample_data.py
   ├─ audit_data_quality.py
   ├─ purge_mock_data.py
   ├─ probe_d2b_bid_api.py
   ├─ probe_d2b_plan_api.py
   ├─ probe_lh_api.py
   ├─ probe_naver_news_api.py
   ├─ smoke_test.py
   ├─ test_d2b_bid_collector.py
   ├─ test_d2b_plan_collector.py
   ├─ test_g2b_collector.py
   ├─ test_lh_collector.py
   ├─ test_naver_news_collector.py
   └─ test_collector_flow.py
```

## 다음 단계

1. 나라장터, LH, D2B, 뉴스, R&D, 특허 수집기를 `src/collectors/` 구조로 추가합니다.
2. 각 수집 결과를 `items` 테이블 스키마에 맞게 정규화합니다.
3. `unique_hash` 기준 중복 제거 규칙을 실제 수집 데이터에도 적용합니다.
4. 로컬 MVP가 안정화된 뒤 클라우드 배포와 Notion 임베드를 진행합니다.
## 8.6-C 나라장터 모듈러 물품·용역 운영 수집

나라장터 운영 기본 수집 범위는 `공고명에 모듈러가 포함된 물품·용역 공고`입니다. 용역은 세부구분이 확인되면 일반용역으로 표시하고, 세부구분이 없으면 용역 후보로 관리합니다. 성의여자고등학교 `R26BK01510994`처럼 운영 필터 밖에 있을 수 있는 중요 공고는 known important bid 회귀 테스트로 계속 추적합니다.

`.env` 예시:

```env
G2B_MODULAR_SCOPE_ENABLED=true
G2B_MODULAR_TITLE_KEYWORD=모듈러
G2B_BUSINESS_TYPES=물품,용역
G2B_SERVICE_SUBTYPE=일반용역
G2B_MODULAR_LOOKBACK_DAYS=180
G2B_MODULAR_PAGE_SIZE=100
G2B_INCLUDE_CANCELLED=true
G2B_INCLUDE_CORRECTION=true
```

실행 순서:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe db\init_db.py
.\.venv\Scripts\python.exe scripts\probe_g2b_modular_scope_api.py
.\.venv\Scripts\python.exe scripts\collect_g2b_modular_scope.py
.\.venv\Scripts\python.exe scripts\diagnose_g2b_modular_scope.py
.\.venv\Scripts\python.exe scripts\test_known_important_bids.py
run_local.bat
```
## 9.0 ModularHub 정보 구조

대시보드는 Streamlit 기반을 유지하면서 `랜딩 페이지 + 앱 페이지` 구조로 정리했습니다.

페이지 역할:

- LandingPage: ModularHub 소개, 앱 열기 CTA, 카테고리 카드
- AppPage: 입찰공고, 뉴스, R&D, 특허, 트렌드, 블로그, 커뮤니티, 즐겨찾기 섹션

앱 섹션:

- `bid`: 입찰공고
- `news`: 모듈러 뉴스
- `rnd-announce`: R&D 공고
- `rnd-outcome`: R&D 성과·보고서
- `patent`: 특허
- `trend`: 트렌드
- `blog`: 블로그 placeholder
- `community`: 커뮤니티 placeholder
- `favorites`: 즐겨찾기 placeholder

Streamlit 실행:

```bat
cd /d "D:\backup01\Documents\New project 2"
run_local.bat
```

접속:

- 홈: `http://127.0.0.1:8501`
- 앱: `http://127.0.0.1:8501/?page=app&section=bid#bid`
- 뉴스: `http://127.0.0.1:8501/?page=app&section=news#news`
- R&D 공고: `http://127.0.0.1:8501/?page=app&section=rnd-announce#rnd-announce`
- R&D 성과: `http://127.0.0.1:8501/?page=app&section=rnd-outcome#rnd-outcome`
- 특허: `http://127.0.0.1:8501/?page=app&section=patent#patent`

참고: Streamlit은 브라우저 hash를 서버에서 직접 읽기 어렵기 때문에, 앱 내부에서는 `page`와 `section` query parameter를 기준으로 섹션을 열고 URL hash를 함께 보존합니다. `/app#bid` 접근은 클라이언트 보정 스크립트가 `/?page=app&section=bid#bid` 형태로 전환합니다.

## 9.1 카드형 결과 화면

입찰공고, 모듈러 뉴스, R&D 공고, R&D 성과, 특허 섹션은 기본 표시를 카드형 결과 리스트로 정리했습니다. 기존 테이블은 각 섹션의 `보조 테이블 보기` 접기 영역에 유지됩니다.

화면 구조:

- 좌측 사이드바: 섹션별 키워드 버튼, 기간, 업무구분, 포함/제외 단어, IPC 코드 등 필터
- 우측 본문: KPI/요약 카드, 결과 카드 리스트, CSV 내보내기, 보조 테이블
- 카드 액션: 상세보기, 원문 보기, API 상세 보기, 확인 사이트 열기, 즐겨찾기

입찰공고 섹션:

- 나라장터 운영 scope는 `공고명 모듈러 포함 + 물품/용역`을 유지합니다.
- known important bid는 `중요공고` 배지로 구분됩니다.
- G2B/LH/D2B는 검증된 원문이 없으면 `API 상세 보기` 또는 `확인 사이트 열기`로 표시됩니다.
- `현재 입찰공고 결과 전체 즐겨찾기 추가` 버튼으로 표시 결과를 한 번에 저장할 수 있습니다.

뉴스 섹션:

- 네이버 뉴스 원문 링크는 `원문 보기`로 유지됩니다.
- AI 요약은 placeholder 단계이며, 실제 요약 생성은 후속 단계에서 연결합니다.

R&D/특허 섹션:

- 현재 수집 데이터가 없으면 placeholder로 표시됩니다.
- 이후 NTIS/KIPRIS 수집기가 연결되면 같은 카드 구조로 표시됩니다.

즐겨찾기:

- SQLite `favorites` 테이블에 로컬 저장합니다.
- 각 카드의 `☆ 즐겨찾기` / `★ 즐겨찾기 해제` 버튼으로 저장·해제합니다.
- `favorites` 섹션에서 저장한 항목을 모아볼 수 있습니다.

실행:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe db\init_db.py
run_local.bat
```

## 9.2 데이터 API와 배포 준비

데이터 계약은 `src/api_contract.py`에 정리되어 있습니다. Streamlit 화면과 선택형 FastAPI 서버가 같은 DTO를 사용합니다.

API endpoints:

- `GET /api/health`
- `GET /api/bids`
- `GET /api/news`
- `GET /api/rnd-announces`
- `GET /api/rnd-outcomes`
- `GET /api/patents`
- `GET /api/trends`
- `GET /api/favorites`
- `POST /api/favorites`
- `DELETE /api/favorites/{id}`

CommonItem DTO:

- `id`, `source_type`, `source_name`, `title`, `organization`
- `posted_at`, `due_at`, `amount`, `region`, `keywords`
- `relevance_score`, `source_record_id`, `source_record_no`
- `business_type`, `business_subtype`, `notice_status`
- `operating_scope`, `is_operating_scope`, `is_known_important`
- `original_url`, `source_detail_api_url`, `manual_check_site`, `summary`

선택형 FastAPI 실행:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe -m uvicorn src.api_server:app --host 127.0.0.1 --port 8000
```

API 계약 테스트:

```bat
.\.venv\Scripts\python.exe scripts\test_api_contract.py
```

## 9.3 상세보기·출처확인·섹션별 필터 안정화

카드의 `상세보기`는 항상 `items.id` 기준으로 동작합니다. 제목이나 행 번호로 상세 데이터를 찾지 않습니다.

상세 패널 구성:

- 요약: 제목, 출처, 기관, 게시일, 마감일, 금액, 공고번호, 공고차수, 업무구분, 공고상태
- API 상세: `source_details`에 저장된 OpenAPI 응답. `detail_api_url`의 인증키는 화면/API에서 마스킹됩니다.
- 수동 확인: 공식 사이트명, 확인 사이트, 공고번호/공고명/기관명 복사용 텍스트
- 원본 Raw: 정규화된 DTO와 저장된 상세 payload

버튼 의미:

- `원문 보기`: 검증된 원문 URL 또는 뉴스 originallink에만 사용합니다.
- `API 상세 보기`: 외부 API URL을 새 창으로 열지 않고 내부 상세 패널에서 저장된 응답을 보여줍니다.
- `확인 사이트 열기`: 나라장터/LH/D2B 공식 사이트를 여는 수동 확인 기능입니다. 특정 공고 상세 원문 링크가 아니므로 공고번호 또는 공고명으로 검색해야 합니다.

섹션별 필터:

- 기본 모드에서는 `bid`, `news`, `rnd-announce`, `rnd-outcome`, `patent` 섹션이 각각 자기 source_type/source_name으로 자동 제한됩니다.
- 사이드바의 `고급 source_type/source_name 필터 직접 적용`을 켠 경우에만 전역 source 필터를 직접 조정합니다.
- 검색어, 날짜, 관련도 필터는 섹션별 데이터에 적용됩니다.

테스트:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\test_api_contract.py
.\.venv\Scripts\python.exe scripts\test_item_detail_api.py
.\.venv\Scripts\python.exe scripts\test_detail_panel_data.py
```

FastAPI 상세 endpoint 확인:

```bat
.\.venv\Scripts\python.exe -m uvicorn src.api_server:app --reload --port 8000
```

확인 URL:

- `http://127.0.0.1:8000/api/health`
- `http://127.0.0.1:8000/api/bids?limit=1`
- `http://127.0.0.1:8000/api/items/1`

정적 JSON export:

```bat
.\.venv\Scripts\python.exe scripts\export_api_json.py
```

생성 위치:

```text
exports/api/health.json
exports/api/bids.json
exports/api/news.json
exports/api/rnd-announces.json
exports/api/rnd-outcomes.json
exports/api/patents.json
exports/api/trends.json
exports/api/favorites.json
```

즐겨찾기:

- 로그인 전 UX는 브라우저 `localStorage` 키 `modularhub_favorites`를 기준으로 미러링합니다.
- 현재 Streamlit 앱은 SQLite `favorites` 테이블을 서버 저장소로 사용합니다.
- Next.js 전환 시 `modularhub_favorites`를 우선 읽고, 로그인 후 DB favorites API로 동기화하는 방식을 권장합니다.

Vercel 배포 전 주의사항:

- Python collector는 Vercel 서버리스에서 장시간 실행하지 않습니다.
- 수집은 로컬, GitHub Actions, Render, Railway, 별도 서버 중 하나에서 수행합니다.
- Vercel은 프론트 표시와 가벼운 API에 집중합니다.
- SQLite 로컬 DB는 배포용 영구 저장소로 적합하지 않으므로 Supabase/PostgreSQL 또는 정적 JSON export 방식 전환을 고려합니다.
- API Key는 서버 환경변수에만 저장하고 클라이언트에 노출하지 않습니다.

배포 시나리오 A: 로컬 수집 + 정적 JSON export + Vercel 프론트

1. 로컬 또는 배치 서버에서 `scripts/collect_all.py` 실행
2. `scripts/export_api_json.py`로 `exports/api/*.json` 생성
3. JSON 파일을 프론트의 public/static 데이터로 배포
4. Vercel 프론트는 JSON만 읽고 API Key를 보유하지 않음

배포 시나리오 B: Render/Railway FastAPI + PostgreSQL + Vercel 프론트

1. collector는 Render/Railway/Cron에서 실행
2. DB는 PostgreSQL/Supabase로 이전
3. FastAPI `src.api_server:app`가 `/api/*` 제공
4. Vercel 프론트는 FastAPI를 호출
5. API Key는 FastAPI/collector 서버 환경변수에만 저장

회귀 테스트:

```bat
.\.venv\Scripts\python.exe scripts\test_known_important_bids.py
.\.venv\Scripts\python.exe scripts\diagnose_g2b_modular_scope.py
.\.venv\Scripts\python.exe scripts\test_api_contract.py
```

## 10.5 발주계획과 매일 자동 갱신

공개 사업정보는 `source_type`으로 입찰공고와 발주계획을 구분합니다.

- `bid`: 나라장터·D2B 입찰공고
- `procurement_plan`: 나라장터 발주계획·D2B 조달계획
- 프론트의 `입찰공고`/`발주계획` 필터는 `type` 문자열이 아니라 `source_type`을 사용합니다.

발주계획 로컬 수집 및 진단:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\collect_g2b_procurement_plans.py
.\.venv\Scripts\python.exe scripts\collect_d2b_procurement_plans.py
.\.venv\Scripts\python.exe scripts\export_public_json.py
.\.venv\Scripts\python.exe scripts\diagnose_procurement_plan_gap.py
.\.venv\Scripts\python.exe scripts\test_public_json_export.py
.\.venv\Scripts\python.exe scripts\test_procurement_plan_pipeline.py
```

`diagnose_procurement_plan_gap.py`는 다음 상태를 구분합니다.

- 수집기 미실행
- DB에는 있으나 공개 JSON에서 누락
- JSON에는 있으나 프론트 필터 불일치
- 정상 수집 후 조회기간 내 모듈러 발주계획 0건

나라장터 발주계획 API가 `403`을 반환하면 공공데이터포털에서 해당 발주계획현황서비스 활용신청과 `.env`의 `G2B_PLAN_*_ENDPOINT` 값을 확인합니다. 실제 수집이 성공했지만 모듈러 매칭이 0건이면 공개 화면은 오류 대신 조회기간 내 데이터가 없다는 안내를 표시합니다.

### GitHub Actions 자동 갱신

워크플로 파일은 `.github/workflows/update-public-data.yml`입니다. 저장소 `mkpark1016-ctrl/modularhub-public`에서 매일 한국시간 오전 7시(`0 22 * * *`, UTC)에 실행되며, GitHub의 `Actions` 탭에서 `Update public data`를 선택해 수동 실행할 수도 있습니다.

GitHub 저장소의 `Settings > Secrets and variables > Actions`에 다음 Repository secrets를 등록합니다.

- `DATA_GO_KR_SERVICE_KEY`
- `NAVER_CLIENT_ID`
- `NAVER_CLIENT_SECRET`

자동 실행 순서:

1. 입찰공고와 뉴스 수집
2. 나라장터·D2B 발주계획 수집
3. known important bid 수집
4. `business.json`, `news.json`, `meta.json` 생성
5. 공개 JSON 보안·계약·발주계획 테스트
6. 사업정보와 뉴스정보가 모두 비어 있지 않을 때만 `frontend/public/data/*.json` commit/push
7. Netlify가 GitHub push를 감지해 자동 재배포

일부 수집기가 실패해도 다른 수집은 계속되며 실패 기록은 `meta.json`의 warning과 발주계획 수집 상태에 반영됩니다. JSON이 비어 있거나 API Key 노출 테스트가 실패하면 Actions는 commit하지 않습니다.

Netlify 공개 화면에서 발주계획이 0건이면 먼저 GitHub Actions 실행 로그를 확인하고, 로컬에서는 아래 명령으로 DB·export·프론트 연결 지점을 한 번에 진단합니다.

```bat
.\.venv\Scripts\python.exe scripts\diagnose_procurement_plan_gap.py
```
## GitHub Actions 실패 복구 및 중지 API 정책

- 나라장터 발주계획은 공공데이터포털 공식 Swagger의 base endpoint `https://apis.data.go.kr/1230000/ao/OrderPlanSttusService`를 사용합니다. `StusService`가 아니라 `SttusService`인 점에 주의합니다.
- 상세 operation과 인증키 전달 방식은 아래 probe로 먼저 확인합니다.

```bat
.\.venv\Scripts\python.exe scripts\probe_g2b_order_plan.py
```

probe 결과는 다음처럼 구분합니다.

- HTTP 2xx 및 정상 resultCode, 0건: 정상 호출이지만 조회기간 내 모듈러 매칭 0건
- HTTP 403 또는 resultCode 30: 활용신청, 인증키 권한, Encoding/Decoding 키 확인 필요
- HTTP 404: base endpoint가 아니라 업무별 상세 operation 경로 확인 필요

방위사업청 기존 군수품조달정보 입찰공고·조달계획 API는 공공데이터포털에서 중지 상태이므로 기본 자동 수집에서 제외합니다. `D2B_LEGACY_API_ENABLED=false`가 기본이며, 공개 `meta.json`에는 `d2b_status=disabled_stopped` 경고가 기록됩니다. D2B GW API 전환은 별도 후속 단계로 진행합니다.

`meta.json` 공개 상태 필드:

- `g2b_order_plan_status`, `g2b_order_plan_message`
- `d2b_status`, `d2b_message`
- `workflow_last_run_status`
- `warnings`

GitHub Actions 실패 확인 방법:

1. GitHub 저장소 `Actions` 탭에서 `Update public data` workflow를 엽니다.
2. 실패한 `collect-export-publish` run을 선택합니다.
3. 붉게 표시된 step을 열고 `command=... exit_code=...` 줄을 확인합니다.
4. exit code `1` 또는 `2` 앞에 출력된 정확한 Python 명령과 API 오류 메시지를 확인합니다.

2026년 6월 13일 확인한 workflow run `27448578723`의 실제 실패 step은 `Diagnose procurement plan pipeline`이었습니다. 해당 run의 커밋 `70ee8330b057cab8624e53ab296125951271a66e`에는 `scripts/diagnose_procurement_plan_gap.py`가 없어 Python이 스크립트 파일을 열지 못한 것이 원인이며, 이 경우 일반적으로 exit code `2`가 발생합니다. 현재 workflow는 파일 존재 여부를 확인하고 진단 실패를 warning으로 기록한 뒤 계속 진행합니다.

collector 단계는 optional 처리되어 exit code를 warning으로 남기고 다음 단계로 진행합니다. 최종 성공 기준은 `business.json`과 `news.json`이 비어 있지 않고 공개 JSON 보안 및 계약 테스트를 통과하는 것입니다.

새 export가 비어 있으면 workflow는 checkout 시점의 기존 공개 JSON을 복원하고 commit을 건너뜁니다. 따라서 일부 API 실패로 Netlify의 정상 데이터가 빈 파일로 교체되지 않습니다.

## 나라장터 발주계획 operation 검증

공식 문서: [조달청_나라장터 발주계획현황서비스](https://www.data.go.kr/data/15129462/openapi.do)

공식 Swagger에 등록된 operation은 다음과 같습니다.

- 일반조회: `getOrderPlanSttusListThng`, `getOrderPlanSttusListServc`, `getOrderPlanSttusListCnstwk`, `getOrderPlanSttusListFrgcpt`
- 검색조회: `getOrderPlanSttusListThngPPSSrch`, `getOrderPlanSttusListServcPPSSrch`, `getOrderPlanSttusListCnstwkPPSSrch`, `getOrderPlanSttusListFrgcptPPSSrch`

일반조회 필수 파라미터는 `serviceKey`, `pageNo`, `numOfRows`, `inqryDiv`입니다. 검색조회 필수 파라미터는 `serviceKey`, `pageNo`, `numOfRows`, `orderBgnYm`, `orderEndYm`, `inqryBgnDt`, `inqryEndDt`이며 `bizNm=모듈러`를 선택 조건으로 사용합니다.

```bat
.\.venv\Scripts\python.exe scripts\probe_g2b_order_plan.py
.\.venv\Scripts\python.exe scripts\collect_g2b_procurement_plans.py
.\.venv\Scripts\python.exe scripts\export_public_json.py
.\.venv\Scripts\python.exe scripts\test_public_json_export.py
```

probe는 operation별 결과를 `SUCCESS`, `EMPTY_RESULT`, `AUTH_ERROR`, `NOT_FOUND_OPERATION`, `PARAM_ERROR`, `PARSE_ERROR`로 분류합니다. `EMPTY_RESULT`는 API 오류가 아니라 정상 호출 후 조회 결과가 0건인 상태입니다. 수집기는 `PPSSrch` 검색조회로 먼저 모듈러 사업명을 조회하고 결과가 없으면 공식 일반조회 operation에서 클라이언트 키워드 필터를 수행합니다.

## 공개 JSON 누적 보존 정책

공개 데이터는 `cumulative_verified` 정책을 사용합니다. `export_public_json.py`는 현재 DB 결과만으로 파일을 교체하지 않고 기존 `business.json`, `news.json`을 먼저 읽어 신규 수집 결과와 병합합니다.

- 사업정보: 공고번호 또는 계획번호를 우선 식별자로 사용하며, 번호가 없으면 출처·제목·기관·게시일/마감일 조합을 사용합니다.
- 뉴스정보: 원문 URL을 우선 사용하고, URL이 없으면 네이버 링크 또는 제목·매체·게시일 조합을 사용합니다.
- 기존 중요공고는 항상 유지합니다.
- 기존 입찰·발주계획과 검증 뉴스는 기본 180일 동안 유지합니다.
- 중복 항목은 기존 공개 ID를 보존하면서 신규 필드로 갱신합니다.
- 일부 API가 실패하거나 0건을 반환해도 기존 검증 데이터는 즉시 삭제되지 않습니다.

로컬 진단 및 검증:

```bat
.\.venv\Scripts\python.exe scripts\diagnose_public_json_counts.py
.\.venv\Scripts\python.exe scripts\export_public_json.py
.\.venv\Scripts\python.exe scripts\diagnose_public_json_counts.py
.\.venv\Scripts\python.exe scripts\refuse_suspicious_public_data_shrink.py
.\.venv\Scripts\python.exe scripts\test_public_json_export.py
```

감소 가드는 사업정보가 이전 기준보다 20% 이상, 뉴스정보가 30% 이상 줄어들면 commit을 차단합니다. 누적 병합 최종 결과가 이전 공개 건수 이상이면 신규 수집 건수가 일시적으로 적어도 통과합니다. 의도적인 정리 작업에 한해서만 `ALLOW_PUBLIC_DATA_SHRINK=true`를 설정할 수 있으며 기본값은 `false`입니다.

GitHub Actions는 export 후 건수 진단과 감소 가드를 실행합니다. 가드가 실패하면 checkout 시점의 공개 JSON 백업을 복원하고 workflow를 실패 처리하므로 GitHub와 Netlify의 정상 데이터는 유지됩니다. 보안·계약 테스트는 JSON을 다시 생성하지 않고 생성된 결과를 읽기 전용으로 검사합니다.

`meta.json`에는 다음 보호 상태가 기록됩니다.

- `previous_business_count`, `current_business_count`, `merged_business_count`
- `previous_news_count`, `current_news_count`, `merged_news_count`
- `public_data_guard_status`, `public_data_guard_message`
- `data_policy=cumulative_verified`
- `d2b_legacy_status`, `d2b_gw_migration_required`

D2B 기존 API 중지 상태는 내부 meta warning으로 유지합니다. `probe_d2b_gw.py`, `d2b_gw_bid.py`, `d2b_gw_procurement_plan.py`는 후속 GW API 전환을 위한 자리만 마련했으며 현재 수집 및 공개 JSON에는 연결하지 않습니다.

## Dual Deployment: Netlify + Vercel

ModularHub 공개 프론트는 Netlify 운영 배포를 유지하면서 Vercel에도 같은 GitHub `main` 브랜치를 연결해 병행 배포할 수 있습니다. Netlify 설정 파일은 삭제하지 않으며, 기존 Netlify URL은 Notion 임베드나 백업 접속용 운영 URL로 계속 유지합니다. Vercel은 추가 검증용 배포 채널로 붙입니다.

두 플랫폼 모두 `frontend/public/data/business.json`, `frontend/public/data/news.json`, `frontend/public/data/meta.json`을 사용합니다. 데이터 수집과 JSON 갱신은 GitHub Actions가 담당하고, Netlify와 Vercel은 GitHub `main` 변경을 감지해 정적 프론트만 배포합니다.

주의 사항:

- Vercel에는 API Key를 등록하지 않습니다.
- `DATA_GO_KR_SERVICE_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`은 GitHub Repository Secrets에만 둡니다.
- Vercel Cron은 사용하지 않습니다.
- GitHub Actions 데이터 갱신 구조는 그대로 유지합니다.
- Netlify 자동 배포를 끊거나 프로젝트를 삭제하지 않습니다.
- Netlify 크레딧 소모가 우려되면 코드가 아니라 Netlify 관리자 화면에서 auto publishing, deploy 상태, repository 연결 상태를 별도로 조정합니다.

Vercel 프로젝트 생성 설정:

- Import Git Repository: `mkpark1016-ctrl/modularhub-public`
- Framework Preset: `Vite`
- Root Directory: `frontend`
- Install Command: `npm install`
- Build Command: `npm run build`
- Output Directory: `dist`
- Production Branch: `main`
- Environment Variables: 없음

SPA 라우팅:

- Vercel은 `frontend/vercel.json`의 rewrite 설정으로 `/business`, `/news`, `/business/:id`, `/news/:id` 직접 접속과 새로고침을 `index.html`로 연결합니다.
- Netlify는 기존 `frontend/netlify.toml` 설정을 유지합니다.

운영 전환 기준:

- Netlify는 Vercel 안정화 전까지 인터넷 접속 가능한 기존 배포 URL로 유지합니다.
- Vercel이 2~3일 이상 정상 갱신되면 Notion 임베드 URL을 Vercel로 교체할 수 있습니다.
- Netlify 프로젝트 삭제는 Vercel 안정화 이후 별도 판단합니다.

로컬 검증:

```bat
cd /d "D:\backup01\Documents\New project 2\frontend"
npm install
npm run build

cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\diagnose_public_json_counts.py
.\.venv\Scripts\python.exe scripts\refuse_suspicious_public_data_shrink.py
.\.venv\Scripts\python.exe scripts\test_public_json_export.py
```

배포 흐름:

1. GitHub Actions가 매일 데이터를 수집합니다.
2. 공개 JSON을 누적 병합하고 축소 방지 검사를 통과한 경우에만 commit/push합니다.
3. Netlify와 Vercel이 같은 `main` 브랜치 변경을 각각 감지해 재배포합니다.

## 10.8-A Public Agency Housing Contest Source Probe

이번 단계는 LH, GH, iH, SH 공식 홈페이지에 게시되는 민간참여 공공주택건설사업 민간사업자 공모를 향후 안정적으로 수집하기 위한 진단 단계입니다. DB 저장, 공개 JSON export, 프론트 표시 변경은 하지 않습니다.

대상 소스:

- LH 공모안내: `https://www.lh.or.kr/board.es?mid=a10601020000&bid=0034`
- GH 공모 관련사항: `https://www.gh.or.kr/gh/bid-announcement.do`
- iH 공지사항: `https://www.ih.co.kr/main/customer/notification/notice.jsp`
- SH 사업발주 공고 게시판: `https://www.i-sh.co.kr/main/lay2/program/S1T1C222/subMain4.do?menu=instOpenResultCdList`

진단 원칙:

- 각 기관 요청 사이에는 최소 1초 간격을 둡니다.
- `User-Agent`를 명시합니다.
- CAPTCHA, 로그인, 접근 제한은 우회하지 않습니다.
- requests로 확인이 어려우면 `playwright_required` 또는 `manual_only` 후보로 분류합니다.
- PDF, HWP, HWPX, ZIP 첨부파일은 파일명과 URL만 추출하고 대량 다운로드하지 않습니다.
- 기관 하나의 실패가 다른 기관 진단을 중단하지 않습니다.

원문 링크 검증 정책:

- 상세 URL은 기관별 `allowed_domains` 안에 있어야 합니다.
- 목록 URL은 정확 원문 링크로 통과하지 않습니다.
- 상세 URL에는 LH `list_no`, GH `articleNo`, iH `msg_seq` 같은 고유 ID가 포함되어야 합니다.
- 상세 페이지 제목 또는 본문이 목록 제목/known title과 유사해야 합니다.
- 검증 실패 시 `original_url` 후보로 확정하지 않고 `detail_unverified` 또는 실패 사유를 남깁니다.

공모 단계 구분:

- 사업기회 단계: `pre_notice`, `main_notice`, `re_notice`, `correction`
- 정보 업데이트: `update`
- 결과 공고: `result`

결과 공고는 신규 사업기회 목록에 혼입하지 않습니다. 단, 이번 단계에서는 공개 JSON 필터를 실제로 적용하지 않습니다.

모듈러 관련성 구분:

- `confirmed`: 제목, 본문, 첨부파일명에 `모듈러`, `OSC`, `Off-Site`, `공업화주택`, `프리패브`, `PC 모듈러`, `스틸 모듈러`, `공장제작`, `DfMA` 등 명시 근거가 있는 경우
- `review_candidate`: 민간참여 공공주택 공모이지만 모듈러 적용 근거가 명시되지 않은 경우
- `unconfirmed`: 관련 근거가 없는 일반 공지

근거 없는 민간참여 공모를 `confirmed`로 표시하지 않습니다. 화면 적용 단계에서는 `review_candidate`를 “모듈러 적용 검토 대상, 공고상 모듈러 적용 확정 아님”으로 안내합니다.

실행:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\probe_public_housing_contest_sources.py
.\.venv\Scripts\python.exe scripts\test_public_housing_contest_probe.py
.\.venv\Scripts\python.exe -m compileall src scripts
```

출력:

- `logs/public_housing_contest_probe.json`
- `logs/public_housing_contest_probe.md`

`logs` 폴더는 진단 산출물 보관용이며 commit 대상이 아닙니다.

## 10.8-B LH 민간참여 공공주택 공모 수집

LH 공식 공모안내 게시판의 민간참여 공공주택건설사업 민간사업자 공모를 사업정보에 통합합니다.

대상 게시판:

- LH 공모안내: `https://www.lh.or.kr/board.es?mid=a10601020000&bid=0034`

수집 기준:

- 제목 또는 본문이 `민간참여 공공주택건설사업`, `민간참여 공공주택사업`, `민간사업자 공모/재공모` 조건과 공공주택 문맥을 함께 만족해야 합니다.
- 사업기회 기본 노출 단계는 `pre_notice`, `main_notice`, `re_notice`, `correction`입니다.
- `result`와 `update` 단계는 DB에는 보존할 수 있지만 기본 공개 사업기회 목록에는 노출하지 않습니다.
- 공고에 모듈러, OSC, Off-Site, 공업화주택, 프리패브, DfMA 등의 직접 근거가 없으면 `review_candidate`로 표시합니다.
- `review_candidate`는 “모듈러 적용 검토 대상”이며, 공고상 모듈러 적용 확정이 아닙니다.

원문 링크와 첨부파일:

- LH 상세 URL은 `lh.or.kr` 도메인, `act=view`, `list_no` 포함, HTTP 200, 제목 유사도 조건을 만족할 때만 공식 원문으로 저장합니다.
- 목록 페이지나 파일 다운로드 URL을 원문 링크로 표시하지 않습니다.
- PDF, HWP, HWPX, ZIP 첨부파일은 파일명, 파일 형식, 공식 다운로드 URL만 수집합니다.
- 첨부파일 본문은 이번 단계에서 파싱하지 않습니다.

로컬 실행:

```bat
cd /d "D:\backup01\Documents\New project 2"
.\.venv\Scripts\python.exe scripts\collect_lh_public_housing_contests.py --dry-run
.\.venv\Scripts\python.exe scripts\test_lh_public_housing_contest_collector.py
.\.venv\Scripts\python.exe scripts\collect_lh_public_housing_contests.py --apply
.\.venv\Scripts\python.exe scripts\export_public_json.py
.\.venv\Scripts\python.exe scripts\test_public_json_export.py
.\.venv\Scripts\python.exe scripts\refuse_suspicious_public_data_shrink.py
.\.venv\Scripts\python.exe scripts\diagnose_public_json_counts.py
```

프론트 검증:

```bat
cd /d "D:\backup01\Documents\New project 2\frontend"
npm run lint
npm run build
```

GitHub Actions:

- `update-public-data.yml`에서 기존 나라장터/D2B/뉴스 수집 후 LH 민간참여 공공주택 공모 수집을 실행합니다.
- LH 수집에는 별도 Secret이 필요하지 않습니다.
- LH 수집 실패는 workflow 전체 실패로 처리하지 않고 `meta.json` warning 상태로 반영합니다.
- 공개 JSON export, 보안 테스트, 축소 방지 테스트가 통과할 때만 JSON 변경분을 commit/push합니다.
- Netlify와 Vercel은 동일한 `frontend/public/data/*.json`을 배포합니다.
