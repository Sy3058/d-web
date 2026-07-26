# 작품 목록/상세 페이지 (M2 그룹 E)

| 항목 | 내용 |
|------|------|
| 모듈 | Frontend / Catalog (독자 공개 읽기 경로) |
| 관련 마일스톤 | [M2](../../../milestones/M2_foundation.md) 그룹 E (E1+E2, WORK-01·02·03) |
| 작성 시점 | M2 E (2026-07-22) |
| 상태 | 구현 + workflow `/code-review` xhigh(확정6+개연1+반증1, 오탐 2건 기각, 실수정 5+1 반영) 완료. `astro check` 0 errors + `vitest` 12/12 + `build` 통과 + 로컬 dev 런타임 스모크 |
| 관련 문서 | M2_foundation.md 그룹 E·결정 3, IMPLEMENTATION_PUBLIC_CATALOG_API.md(BE 계약 원본), DESIGN.md(컴포넌트 스펙), GUIDE_ASTRO.md(버전 델타) |

비로그인 독자가 `/works`에서 공개 작품 목록(태그 필터·페이지네이션)을 보고, `/works/{id}`에서 작품 메타 + 회차 목록(무료/잠금 배지·뷰어 링크)을 보는 첫 독자용 카탈로그 화면. FE의 첫 `docs/MODULES/FE` 문서다. 회차 본문 렌더(뷰어)는 그룹 F 소관.

---

## 1. 산출물

E 그룹은 4개 커밋으로 나눠 올렸다(리팩터 → ui 프리미티브 → API 클라이언트 → 페이지).

| 파일 | 내용 | 커밋 |
|------|------|------|
| `frontend/src/components/ui/forms.tsx` | `auth/ui.tsx`를 도메인 무관 위치로 이관(내용 무변경, `git mv`). auth 3파일 import 경로 수정 | 9518b9b |
| `frontend/src/styles/globals.css` | DESIGN.md 타이포 스케일 7종을 Tailwind v4 컴파운드 토큰(`--text-{n}--line-height`/`--letter-spacing`/`--font-weight`)으로 추가 | 4711da5 |
| `frontend/src/components/ui/{Button,Card,Chip,Badge}.astro` | 도메인 무관 프리미티브(DESIGN.md 스펙 - 무액센트·그림자 금지·1px 보더) | 4711da5 |
| `frontend/src/lib/catalog.ts` | `catalog.py` 계약 손 타이핑(WorkListItem/WorkListResponse/EpisodeSummary/PublicTag/WorkDetail/Tag) + `getWorks`/`getTags`/`getWorkDetail` + 순수 로직(`totalPages`/`buildWorksUrl`/`formatPrice`/`statusLabel`) | 935885d, 26961d9 |
| `frontend/src/lib/catalog.test.ts` | vitest 12케이스(totalPages/buildWorksUrl/formatPrice 순수 로직) | 935885d |
| `frontend/vitest.config.ts` + `package.json` | vitest ^4.1.10(`environment: node`) + `test` 스크립트 | 935885d |
| `frontend/src/components/works/CoverImage.astro` | 3:4 표지 + placeholder 배경 레이어 + `onerror` 폴백 | 26961d9 |
| `frontend/src/components/works/WorkCard.astro` | 목록 카드(표지·제목·상태 배지·태그 칩) | 26961d9 |
| `frontend/src/components/works/TagFilterBar.astro` | 태그 필터 칩 바(전체 + 태그별 work_count) | 26961d9 |
| `frontend/src/components/works/Pagination.astro` | 이전/다음 + `page / totalPages` | 26961d9 |
| `frontend/src/components/works/EpisodeRow.astro` | 회차 행(번호·제목·부제목·썸네일·무료/잠금 배지·가격) | 26961d9 |
| `frontend/src/pages/works/index.astro` | E1 작품 목록(SSR) | 26961d9 |
| `frontend/src/pages/works/[id].astro` | E2 작품 상세 + 회차 목록(SSR) | 26961d9 |
| `frontend/src/lib/http.ts` | `applyCatalogCache()` - 결정 3 캐시 정책 단일 출처 | 26961d9 |

새 의존성: `vitest`(devDep)만. DB 마이그레이션: 없음(읽기 전용 FE).

---

## 2. 주요 결정

### 결정 3 캐시 정책 = `lib/http.ts` 단일 출처
성공 → `public, max-age=60`, 5xx·404 → `no-store`. 이 판단이 `index.astro`·`[id].astro`에 복제돼 있던 걸 `applyCatalogCache(response, { error, notFound })` 한 함수로 모았다. 페이지가 늘어도(그룹 F 뷰어 셸이 같은 정책) 규칙이 갈라지지 않는다. `no-store`의 두 근거: 일시 장애가 60초 캐시로 눌러붙는 것 방지 + 예약 공개 전 404가 캐시돼 공개 후에도 404를 보는 것 방지(백엔드 `works.py`와 동일 이유).

### fail-closed 로딩 분류 (5xx는 "없음"으로 위장 금지)
`my/index.astro`의 선례를 따라 "예상된 빈 상태"(404/401 → `null`)와 "예상 못한 실패"(5xx → `loadError`)를 분리한다. 삼키면 장애가 "작품 없음"으로 위장돼 no-store 대신 캐시에 실릴 수 있다. `getWorkDetail`은 404·422를 `null`로 매핑(422 = 무효 UUID 등 경로 파라미터 검증 실패 = "이 id로는 못 찾음"이라 404와 동치), 그 외는 rethrow → 페이지 `catch`가 `loadError`로 승격.

### 목록/태그 로드는 독립 처리(`Promise.allSettled`)
`Promise.all`이면 보조 UI인 태그 필터(`/tags`)의 단독 5xx가 핵심 카탈로그 전체를 에러 페이지로 무너뜨린다. `allSettled`로 분리해 작품 로드 실패만 `loadError`로 승격, 태그 실패는 빈 배열로 degrade(태그 바만 사라짐).

### 범위 밖 페이지 정규화(리다이렉트)
`?page=9999`(2페이지 카탈로그)는 백엔드가 `items=[], total=30`을 정상 반환하므로 "빈 카탈로그" 거짓 안내 + "9999 / 2" 깨진 페이저가 된다. 로드 후 `page > lastPage`면 마지막 페이지로 302. `works.total > 0` 조건을 걸어 진짜 빈 카탈로그·태그 무매칭(정상 빈 상태)과 구분.

### `page` 파라미터 = `Number.isSafeInteger` 가드
`Number.isInteger(1e21)`은 `true`라 통과하지만 `String(1e21)='1e+21'`가 백엔드 `int` 파싱에서 422를 낸다. `isSafeInteger`는 1e21을 거부(> MAX_SAFE_INTEGER)해 fallback-to-1이 실제로 동작한다.

### WorkCard 태그는 링크 아님, 상세 페이지 태그는 링크
카드 전체가 `<a href="/works/{id}">`라 그 안의 태그 칩에 `href`를 주면 **중첩 앵커(무효 HTML)**가 된다 → 카드 태그는 `<span>`. 상세 페이지 태그는 앵커에 감싸이지 않아 `/works?tag=X` 링크로 활성화.

### 회차 링크 = F1 라우트 계획값 `/works/{id}/{episode_no}`
M2_foundation F1 산출물이 `pages/works/[id]/[episodeNo].astro`(episode_no 기반)로 확정돼 있어 그 경로를 선점한다. 뷰어 페이지 자체는 그룹 F(다음)에서 생기므로 **E 단계에서 회차 클릭 시 404는 의도된 상태**. 잠금 회차도 링크 활성(경계 이전 미리보기가 있음 - 배지로 유료 구간 존재만 표시).

### `statusLabel` 폴백
`WORK_STATUS_LABEL[status]`는 백엔드가 미러링 안 된 새 `WorkStatus`(예: 예약공개)를 보내면 `undefined` → 빈 배지. `statusLabel(status) = WORK_STATUS_LABEL[status] ?? status`로 원값이라도 노출.

#### 미러 갱신은 상태 추가 때마다 수동 (2026-07-26, `preparing` 추가 - #84)
`catalog.ts`의 `WorkStatus` union은 `catalog.py`를 손으로 옮긴 계약이라 **컴파일러가 백엔드와의 어긋남을 잡아주지 못한다**. union에 값을 안 늘리면 `Record<WorkStatus, string>` 완전성 검사 자체가 발화하지 않아서, 라벨 누락이 조용히 통과하고 독자 배지에 원시 영문값(`preparing`)이 뜬다 - 위 폴백은 배지가 통째로 비는 것만 막을 뿐 한국어 라벨을 만들어주진 않는다.

그래서 **백엔드에 `WorkStatus` 값을 추가하면 이 파일도 같은 PR에서 고친다**(union + `WORK_STATUS_LABEL` 두 곳). `preparing`이 그 첫 사례이며, 이를 강제하는 테스트·CI 가드는 아직 없다(현재는 이 문서와 `catalog.ts` 상단 주석이 유일한 방어선). 어드민 쪽 경위와 배지 색 결정은 [ADMIN IMPLEMENTATION_WORK_CRUD_SCREENS.md](../../ADMIN/Works/IMPLEMENTATION_WORK_CRUD_SCREENS.md) §7 참조.

### 표지 = placeholder 배경 레이어 + `onerror`
`cover_image_url`은 `null` 가능(D1 base 미설정 시). placeholder("표지 준비 중")를 항상 배경에 깔고 `<img>`를 그 위에 얹어, 이미지가 없거나 로드 실패(`onerror`)면 placeholder가 드러난다.

---

## 3. 구현 중 발견 (함정)

### CSS 주석 안의 `*/` 조기 종료
`globals.css` 주석에 `leading-*/tracking-*` 같은 문자열을 쓰면 `-*` 뒤 `/`가 `*/`(주석 종료 토큰)로 읽혀 주석이 조기 종료 → 남은 텍스트가 CSS로 파싱되며 `Missing opening (` 에러(스택트레이스가 tailwindcss 내부라 원인 추적이 어렵다). 이분 탐색(토큰 전량 제거 → 하나씩 복원)으로 주석이 원인임을 확인, 슬래시를 쉼표로 교체해 해결. → MISTAKES.md 기록.

### Tailwind v4는 `.flex`가 `[hidden]`을 안 덮는다 (v3와 다름)
리뷰가 "`hidden` 속성 + `flex` 유틸리티 → placeholder가 표지 위에 항상 겹친다"(v3의 유명한 함정)를 확정으로 올렸으나 **오탐**. v4 preflight는 `[hidden]:where(...) { display: none !important }`로 `!important`를 부여해 utilities 레이어의 일반 `display:flex`를 이긴다. 스크린샷(표지 위 텍스트 없음) + 빌드된 CSS(`node_modules/tailwindcss/preflight.css:391`) 양쪽으로 확인해 기각.

---

## 4. 코드 리뷰 (workflow /code-review xhigh)

파인더 6 → 후보 20 → 검증 15 에이전트 → 확정 6 + 개연 1 + 반증 1.

| # | 결함 | 처리 |
|---|------|------|
| 1 | 표지 위 placeholder 오버레이 | **오탐 기각** - v4 `[hidden]` `!important`(§3) |
| 2 | 회차 링크가 존재X 라우트 | **수정 불요** - F1 계획값과 일치(§2), 뷰어는 그룹 F |
| 3 | 범위 밖 페이지 → 거짓 빈 카탈로그 + 깨진 페이저 | **반영** - 마지막 페이지 302 |
| 4 | 무효 UUID(422) → "재시도" 위장 + HTTP 200 | **반영** - `getWorkDetail` 422→null→404 |
| 5 | `/tags` 실패가 카탈로그 전체 다운(`Promise.all`) | **반영** - `allSettled` 분리 |
| 6 | `page=1e21` 지수표기 누출 → 422 | **반영** - `isSafeInteger` |
| 7 | 상태 라벨 폴백 없음(개연) | **반영** - `statusLabel` |
| - | fail-closed 3파일 복붙 드리프트 | **반증** - 실제 드리프트 없음 |

---

## 5. 검증

- `pnpm --filter frontend astro check`: 0 errors / 0 warnings / 1 hint. hint(`buildWorksUrl` ts6133 미사용)는 리다이렉트에서 실사용됨을 런타임으로 확인한 Astro check 오탐.
- `pnpm --filter frontend test`(vitest run): 12 passed
- `pnpm --filter frontend build`: 성공
- 로컬 dev 런타임 스모크: `?page=9999` → 302 `/works`, `/works/not-a-uuid` → 404 + no-store, 정상 목록 → 200 + `public, max-age=60`, 목록→상세 네비, 잠금 배지 + 가격 표기, 표지 렌더
- 테스트 데이터 한계로 미확인(코드/단위테스트로만 보장): 2페이지 이상 페이지네이션 UI, 무료 배지(`is_free=true`) 렌더 - dev 시드에 무료 회차·다페이지 데이터가 없었음

---

## 6. 후속

- 그룹 F(뷰어)가 `/works/{id}/{episode_no}` 라우트를 실제로 만들면 회차 링크가 살아난다 - F1 착수 시 이 라우트명 재확인.
- FE CI job(`astro check` + `build` + `vitest run`)은 별도 `[INFRA]` PR(그룹 E 머지 후).
