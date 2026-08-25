# Multi-company KIPRIS expansion readiness

## Scope and controls

- Base: `730027b73026447ec5a804eee2dab48037f0ca30`
- Cohort order: GS E&C (`gs-ec`), Hyundai Engineering (`hyundai-engineering`), DL E&C (`dl-enc`)
- Inputs: tracked ModularHub company baseline and identity policy only
- External requests: KIPRIS 0, KAIA 0, D2B 0, LLM 0
- Public writes: none
- Runtime artifacts: `artifacts/company-technology/multi-company-live/<company-id>/` (covered by `artifacts/` in `.gitignore`)

The executable alias, inventory, identity-readiness, collision, and request-budget contract is in
`config/company_technology/kipris_expansion_readiness.json` and
`scripts/integrations/technology/readiness.py`. Titles are descriptive metadata and are never an
official identity.

## Readiness meanings

| Decision | Meaning |
| --- | --- |
| `READY_EXACT_IDENTITY` | A valid application number is present. |
| `READY_VERIFIED_REGISTRATION_IDENTITY` | A valid registration or patent number is present and can be reconciled without title identity. |
| `NEEDS_EXACT_LOOKUP` | An identifier is present but cannot yet be used as a canonical exact identity. |
| `IDENTITY_INSUFFICIENT` | No official identifier is present. |
| `KAIA_MANUAL_BASELINE` | Construction new technology, not a KIPRIS patent identity. |

All 37 cohort patent records have a registration number and no application number. They are
`READY_VERIFIED_REGISTRATION_IDENTITY`; no pre-live exact lookup is required. Broad applicant
results must still reconcile by official number before any future publication.

## Company identities and aliases

### GS E&C

- Company ID/type: `gs-ec` / `general_contractor`
- Canonical applicant: `지에스건설 주식회사`
- Approved order: `지에스건설 주식회사`, `지에스건설`, `GS건설`
- Excluded: `GS리테일`, `GS칼텍스`, `GS글로벌`
- Ambiguous: `GS`
- Historical candidates: none

### Hyundai Engineering

- Company ID/type: `hyundai-engineering` / `general_contractor`
- Canonical applicant: `현대엔지니어링 주식회사`
- Approved order: `현대엔지니어링 주식회사`, `현대엔지니어링`, `Hyundai Engineering`
- Excluded: `현대건설`, `현대자동차`, `현대엔지니어링서비스`
- Ambiguous: `현대`, `현대ENG`
- Historical candidates: none

### DL E&C

- Company ID/type: `dl-enc` / `general_contractor`
- Canonical applicant: `디엘이앤씨 주식회사`
- Approved order: `디엘이앤씨 주식회사`, `디엘이앤씨`, `DL이앤씨`
- Excluded: `DL건설`, `DL케미칼`
- Ambiguous: `DL`, `대림`
- Historical candidates: `대림산업 주식회사`, `대림산업`
- Historical policy: explicit-only and disabled for broad live collection. The repository records
  `대림산업` as a former name, but pre-split rights still require entity-level adjudication.

Approved normalized alias collisions across the cohort are 0. Historical normalized collisions
are 0. Group-only tokens are never sent to KIPRIS.

## Baseline statistics

| Company | Total | Patents | Construction new technology | Application no. | Registration no. | Patent no. | Missing official ID | Duplicate title groups | Duplicate official identity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| GS E&C | 3 | 3 | 0 | 0 | 3 | 0 | 0 | 0 | 0 |
| Hyundai Engineering | 14 | 13 | 1 | 0 | 14 | 0 | 0 | 1 | 0 |
| DL E&C | 21 | 21 | 0 | 0 | 21 | 0 | 0 | 0 | 0 |

Hyundai Engineering has two records titled `모듈러 유닛 접합부 구조`, with registration
numbers `10-1233559` and `10-1233537`. They remain distinct official identities.

## GS E&C inventory

All records are `registered`, have no application/patent number or recorded application/registration
date, and use source `manual-verified-gs-ec-20260716`.

| Technology ID | Type | Registration number | Title | Readiness |
| --- | --- | --- | --- | --- |
| `tech-gs-001` | patent | `10-2511945` | 내화성능이 확보된 건축용 모듈 및 이를 이용한 모듈러 건축물의 시공방법 | verified registration identity |
| `tech-gs-002` | patent | `10-2767044` | 패스닝 없이 결합되는 모듈러 건축물의 접합 구조 | verified registration identity |
| `tech-gs-003` | patent | `10-2949624` | 인접 기둥의 거푸집형 내화 구조 및 이를 이용한 내화성능이 확보된 모듈러 구조물의 시공방법 | verified registration identity |

## Hyundai Engineering inventory

Patent records are `registered`; the construction new technology is `expired`. Application number,
patent number, recorded dates, and technology area are absent. Source is
`manual-verified-hyundai-engineering-20260716`.

| Technology ID | Type | Registration number | Title | Readiness |
| --- | --- | --- | --- | --- |
| `tech-hyeng-001` | construction new technology | `건설신기술 제770호` | 천장보 브래킷을 이용하여 단위 유닛 상호간을 연결플레이트와 고력볼트로 접합한 철골 모멘트골조 모듈러 공법 | KAIA manual baseline |
| `tech-hyeng-002` | patent | `10-1233559` | 모듈러 유닛 접합부 구조 | verified registration identity |
| `tech-hyeng-003` | patent | `10-1266737` | 모듈러 유닛 구조체와 기초 콘크리트의 결합용 연결부재 및 이를 이용한 기초 시공방법 | verified registration identity |
| `tech-hyeng-004` | patent | `10-1233537` | 모듈러 유닛 접합부 구조 | verified registration identity |
| `tech-hyeng-005` | patent | `10-1534443` | 변단면 천정보를 갖는 모듈러 유닛 및 이를 이용한 모듈러 유닛 구조물 | verified registration identity |
| `tech-hyeng-006` | patent | `10-1798704` | 모듈러 유닛, 하중전달 브라켓을 갖는 모듈러 구조물 및 그 시공방법 | verified registration identity |
| `tech-hyeng-007` | patent | `10-1878607` | 보 단부에 웨브 개구부를 갖는 모듈러 유닛 및 이를 이용한 내진 모듈러 구조 시스템 | verified registration identity |
| `tech-hyeng-008` | patent | `10-1907747` | 확장형 기둥 구조를 갖는 모듈러 유닛과 트랜스퍼 거더를 이용한 초고층형 모듈러 건축물 | verified registration identity |
| `tech-hyeng-009` | patent | `10-1907746` | 확장형 기둥 구조를 갖는 초고층형 모듈러 유닛 및 이를 이용한 구조물 | verified registration identity |
| `tech-hyeng-010` | patent | `10-1907748` | 기둥 수직 결합용 브라켓을 갖는 모듈러 유닛과 하중전달 기둥을 이용한 초고층형 모듈러 건축물 | verified registration identity |
| `tech-hyeng-011` | patent | `10-1226778` | 내진성능이 향상된 철골 보와 철골 기둥의 접합부 구조 | verified registration identity |
| `tech-hyeng-012` | patent | `10-2558649` | 모듈러 유닛 사이의 외벽 조인트 슬라이딩 수평 접합부 구조 | verified registration identity |
| `tech-hyeng-013` | patent | `10-2558651` | 모듈러 유닛 사이의 외단열 외벽 조인트 슬라이딩 수평 및 상부 커버형 수직 접합부 하향식 시공방법 | verified registration identity |
| `tech-hyeng-014` | patent | `10-2742252` | 층간 차음을 위한 차음판 시공 방법 | verified registration identity |

## DL E&C inventory

All records are `registered`, have no application/patent number or recorded application/registration
date, and use source `manual-verified-dl-enc-20260716`.

| Technology ID | Registration number | Title |
| --- | --- | --- |
| `tech-dl-001` | `10-2307324` | 내부 결합형 모듈러 유닛의 접합 구조 |
| `tech-dl-002` | `10-2307325` | 수평부재 결합형 무용접 모듈러 구조물 |
| `tech-dl-003` | `10-2307326` | 바닥판이 구비된 수평부재 결합형 무용접 모듈러 구조물 |
| `tech-dl-004` | `10-2426681` | 무용접 모듈러 유닛 |
| `tech-dl-005` | `10-2485293` | 끼움 결합형 모듈러 구조물 |
| `tech-dl-006` | `10-2485294` | 모듈러 유닛 |
| `tech-dl-007` | `10-2528425` | 연결바 결합형 모듈러 구조물 |
| `tech-dl-008` | `10-2559032` | 수평부재 연결형 모듈러 구조물 |
| `tech-dl-009` | `10-2594589` | 무하지 프리패브 패널 시스템 |
| `tech-dl-010` | `10-2612044` | 모듈러 유닛용 HPC 접합구 |
| `tech-dl-011` | `10-2638239` | 가이드핀을 이용한 모듈러 유닛의 접합 구조 |
| `tech-dl-012` | `10-2643101` | 유닛 조합형 옥탑 모듈러 구조 |
| `tech-dl-013` | `10-2650777` | 철골 모듈러 커넥터용 초고성능 섬유보강 시멘트계 복합재료 |
| `tech-dl-014` | `10-2703610` | 무하지 단열·차수 일체형 중량 마감 외장 시스템 |
| `tech-dl-015` | `10-2703611` | 복합 내화피복이 구비된 모듈러 유닛의 시공방법 |
| `tech-dl-016` | `10-2703613` | 접합플레이트가 구비된 모듈러 유닛용 커넥터 |
| `tech-dl-017` | `10-2703614` | 접합구가 구비된 모듈러 유닛용 커넥터 |
| `tech-dl-018` | `10-2703615` | 정착플레이트와 커플러가 구비된 모듈러 유닛용 커넥터 |
| `tech-dl-019` | `10-2709990` | 전단연결핀을 이용한 모듈러 유닛의 내화 접합 구조 |
| `tech-dl-020` | `10-2744334` | 옥탑 기계실 모듈러 구조물 |
| `tech-dl-021` | `30-1246316` | 모듈러 건축물용 연결구 |

All DL records are patents with verified registration identity. `30-1246316` is preserved exactly
as supplied by the baseline; the record type is not inferred from the title or number prefix.

## Relevance and false-positive review

| Company | Risk domain | Existing coverage | Additional rule now? |
| --- | --- | --- | --- |
| GS E&C | GS group energy, retail, electronics inventions | Exact approved aliases; group companies excluded | No |
| Hyundai Engineering | Hyundai construction/automotive entities and software/equipment modules | Exact aliases plus construction-context relevance | No |
| DL E&C | DL Construction, DL Chemical, and predecessor-company rights | Modern exact aliases; historical aliases disabled | No |

The existing deterministic rule produces `DIRECT`, `ADJACENT`, or `IRRELEVANT`. Electronic,
communication, semiconductor, battery, and generic software module examples remain irrelevant when
construction context is absent. No broad relevance term is added in this phase.

## Identity collision audit

- Same application number across cohort and Samsung: 0
- Same registration number across cohort and Samsung: 0
- Same patent number across cohort and Samsung: 0
- Approved alias collision: 0
- Ambiguous joint ownership policy: retain as ambiguous; never force attribution to one company

## Bounded live request plan

The Samsung pagination contract is reused: one page per approved alias, page size 100, and a global
200-record cap per company run.

| Company | Approved aliases | Maximum broad requests | Maximum records | Exact lookup candidates | Maximum exact requests |
| --- | ---: | ---: | ---: | ---: | ---: |
| GS E&C | 3 | 3 | 200 | 0 | 0 |
| Hyundai Engineering | 3 | 3 | 200 | 0 | 0 |
| DL E&C | 3 | 3 | 200 | 0 | 0 |

The next phase runs GS E&C only. Hyundai Engineering follows after GS candidate review, then DL E&C.
Historical DL aliases are outside this budget and require a separate approved exact-attribution plan.

## Publication isolation

No public write occurs in readiness or live acceptance. Future controlled publication uses one PR
per company in the configured order, with production acceptance between PRs. Sanitized artifacts
must not contain access keys, credential-bearing URLs, or raw responses with credentials.
