# 뷰어 - 콘텐츠 문서 렌더러 (M2 그룹 F1)

| 항목 | 내용 |
|------|------|
| 모듈 | Frontend / Viewer (독자 열람 경로 - 콘텐츠 문서 렌더러) |
| 관련 마일스톤 | [M2](../../../milestones/M2_foundation.md) 그룹 F (F1, WORK-05~08) |
| 작성 시점 | M2 F1 (2026-07-25), 후속 보완 (2026-07-26 - §7), 긴 블록 복원 보강 (2026-08-14 - §8), 요청 실패 복구 보강 (2026-08-17~18 - §9), 비로그인 로컬 진행도 (2026-08-18 - §10), 그룹 H 완료 검증 (2026-08-21) |
| 상태 | 구현 + 리뷰 + 그룹 H 사용자·자동 검증 완료. M2 전체 종료는 관리자 대표 이미지 후보 불변식 버그 수정 대기 |
| 관련 문서 | M2_foundation.md 그룹 F·결정 1/3/6, IMPLEMENTATION_FREE_CONTENT_API.md(B2 계약 원본), IMPLEMENTATION_VIEWER_PROGRESS.md(C1 계약), IMPLEMENTATION_CATALOG_PAGES.md(E, SSR 셸/캐시 정책 원본), IMPLEMENTATION_EPISODE_CONTENT_MODEL.md(#76, 서버 스키마 원본) |

독자가 `/works/{id}/{publicId}`에서 회차 본문(글+이미지 혼합 TipTap 문서)을 읽는 페이지. B2가 절단·presigned 치환한 무료 구간을 아일랜드가 fetch해 렌더하고, 유료 경계가 있으면 말미에 잠금 placeholder를 보여준다. 로그인은 C1 서버 진행도, 비로그인은 같은 브라우저의 localStorage에 읽은 위치(블록 인덱스 + 블록 내부 상대 위치)를 저장·복원한다. 유료 구간 반환·결제 검증은 M3.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `frontend/package.json` | `@tiptap/core`·`@tiptap/starter-kit`·`@tiptap/extension-link`·`@tiptap/pm` 3.27.4 고정(admin과 버전 통일 - 스키마 패리티), devDep `jsdom` 추가(테스트 전용 - §3) |
| `frontend/src/pages/works/[id]/[publicId].astro` | SSR 셸(`prerender = false`) - 회차 메타·이전/다음 네비만. 본문은 `client:only="react"` 아일랜드가 담당 |
| `frontend/src/components/viewer/Viewer.tsx` | 아일랜드 - B2 fetch, 최상위 블록 분할 렌더(image는 React `<img>` 직접 제어, 나머지는 `generateHTML` 조각), 잠금 placeholder, 진행도 저장·복원, 콘텐츠 보호 |
| `frontend/src/components/viewer/extensions.ts` | 뷰어 전용 TipTap 렌더 스키마(서버 화이트리스트·admin 에디터와 1:1, image attrs만 `src` 예외) |
| `frontend/src/components/viewer/extensions.test.ts` | `getSchema` 스키마 대조 테스트 + `generateHTML` 렌더 동작 테스트(rel/target 강제 확인) |
| `frontend/src/lib/viewer.ts` | B2/C1 계약 타입 + API 함수 + 이미지 우선순위, 블록 인덱스·내부 오프셋 계산 순수 로직 |
| `frontend/src/lib/viewer.test.ts` | vitest 순수 로직 테스트 |
| `frontend/src/lib/guestProgress.ts` | 비로그인 진행도 검증·저장·최근 100개 정리와 공개 회차 최근 기록 선택 |
| `frontend/src/lib/guestProgress.test.ts` | 손상·범위·storage 예외·정리·공개 회차 필터 단위 테스트 |

새 의존성: `@tiptap/*` 4종(런타임) + `jsdom`(devDep, 테스트 전용). DB 마이그레이션: 없음(읽기 전용 FE).

---

## 2. 주요 결정

### 렌더 방식 - 최상위 노드별 분할 렌더

문서를 통째로 `generateHTML`해서 하나의 `dangerouslySetInnerHTML`에 넣지 않고, 최상위 노드 하나씩 개별 렌더한다. image 노드는 React `<img>`로 직접 그려 `fetchPriority`·`draggable`·`onError`를 컴포넌트가 직접 제어하고(결정 6), 나머지는 `generateHTML({type:'doc', content:[node]}, extensions)` 조각을 `dangerouslySetInnerHTML`로 삽입한다. 각 블록을 `data-block-index` wrapper로 감싸 진행도 추적(IntersectionObserver)의 단위로도 재사용한다 - 렌더 방식과 진행도 추적 단위가 자연히 일치한다.

### image attrs = `src` (저장 스키마 `key`와 의도적 불일치)

B2 계약(#76 "서버·에디터·뷰어 3곳 동일 스키마"의 의도된 예외)에 따라 뷰어 스키마의 image 노드는 `attrs={src}`만 받는다. R2 key를 그대로 넘기면 인증·서명 없이 원본 접근 경로가 열리므로, 뷰어는 서버가 이미 presigned URL로 치환한 값만 다룬다. `extensions.test.ts`가 `getSchema`로 이 스키마가 정확히 `{src}` 하나뿐임을 회귀 검사한다.

### `dangerouslySetInnerHTML`의 안전성 = 저장 시점 서버 검증에 의존

뷰어 스키마(`extensions.ts`)가 서버 화이트리스트(`lib/content_doc.py`)와 정확히 일치해야만 성립하는 안전성이다. `getSchema(buildViewerExtensions())`로 노드/마크 화이트리스트를 직접 비교하는 회귀 테스트를 둬서, 두 스키마가 갈라지는 순간(#76 규칙 위반) 테스트가 실패하게 만들었다.

### 결정 6 렌더 방어 - 중첩(비-최상위) image 경로도 동일 원칙 적용

서버 `_validate_node`는 paragraph 자식으로 image가 오는 것을 막지 않는다(admin 에디터는 이 모양을 만들지 않지만 이론상 가능). 이 경로는 `generateHTML` 조각을 타므로 React `<img>` 직접 제어를 못 받는다 - 그래도 결정 6(즉시 전량 요청)이 이 경로에도 적용돼야 하므로 `ViewerImage.renderHTML`에 `loading:'lazy'`를 주지 않는다(최초 구현의 모순을 Opus 리뷰가 발견, 수정 완료 - §4). 드래그 차단도 컨테이너 레벨 `onDragStart`로 두 경로의 보호 수준을 맞췄다.

### 진행도 = "보이는 블록 중 최솟값"

여러 블록이 동시에 뷰포트에 걸쳐 있을 때 IntersectionObserver가 관측한 인덱스 중 최댓값이 아니라 최솟값을 저장 위치로 삼는다. 최댓값을 쓰면 아직 안 읽은 블록이 뷰포트에 살짝 걸치자마자 진행도가 그리로 넘어가, 다음 방문 때 안 읽은 내용을 건너뛰는 문제가 생긴다. 이미 본 내용을 살짝 다시 보는 정도의 사소한 중복을 감수하는 보수적 선택이다.

긴 블록이 뷰포트 상단을 포함할 때는 그 블록을 활성 블록으로 선택하고 내부 상대 위치를 함께 저장한다. 자세한 근거와 알고리즘은 §8에 기록한다.

### `client:only="react"` (client:load 아님)

`@tiptap/core`의 `generateHTML`은 ProseMirror `DOMSerializer`가 실제 DOM을 요구해 브라우저 전용이다(공식 문서 명시 + 테스트 환경에서 `window is not defined`로 실제 재현 - §3). `client:load`는 서버에서 먼저 렌더를 시도하다 이 제약에 걸리고, 결정 1의 "본문 HTML이 SSR 응답에 부재해야 한다"는 요구사항도 위반한다. `client:only="react"`는 서버 렌더를 건너뛰므로 두 문제를 동시에 해결한다.

### 로그인 판별 = `login_hint` 쿠키(비-HttpOnly)

진행도 저장소를 고르는 게이트. `login_hint`가 있으면 기존 서버 GET/PUT만 사용하고 localStorage를 읽거나 쓰지 않는다. 없으면 진행도 API를 호출하지 않고 localStorage만 사용한다. `Navbar.astro`의 네비 로그인 표시와 동일한 판별 원천(`lib/auth.py:90 LOGIN_HINT_COOKIE_NAME`)을 재사용한다. stale `login_hint`로 서버가 401을 반환해도 로컬로 폴백하지 않아 두 저장소를 자동 병합하지 않는다.

---

## 3. 구현 중 발견

### `generateHTML`이 Node(vitest) 환경에서 DOM을 요구

`@tiptap/core`의 `generateHTML`을 vitest 기본 환경(`node`)에서 호출하면 `ReferenceError: window is not defined`로 실패한다. ProseMirror `DOMSerializer.serializeFragment`가 실제 DOM을 필요로 한다는 사실이 이 프로젝트에서 실측으로 확인됐다(공식 문서의 "browser-only" 서술과 일치). 전역 `vitest.config.ts`의 "순수 로직은 node 환경" 원칙은 유지하고, `extensions.test.ts` 파일에만 `// @vitest-environment jsdom`을 지정 + devDep `jsdom` 추가로 해결했다. 이 실패는 역으로 `client:only="react"` 선택(브라우저 실행 보장)이 맞았음을 방증한다.

### dev `dweb` 버킷 드리프트 (B2 스모크에서 발견된 사실 재확인)

로컬 dev의 옛 시드 회차는 원고가 R2에 없어(D1 표지 이관 시 정리된 것으로 추정) 이미지가 전부 404난다. 새로 발행한 회차로만 수동 확인이 가능 - 사용자 인계 시 이 주의사항을 별도로 전달했다.

---

## 4. 코드 리뷰 (Opus, CODE_REVIEW_FE + GUIDE_REVIEW)

| 심각도 | 내용 | 처리 |
|--------|------|------|
| Major | `ViewerImage.renderHTML`(중첩 image 경로)에 `loading:'lazy'`가 걸려 결정 6과 자기모순 - 이 경로는 `onError` 재발급 폴백도 없어 presigned 만료(600초) 403에 무방비 | **반영** - `lazy` 제거 |
| FYI | 컨테이너에 드래그 차단이 없어 중첩 image 경로가 개별 핸들러를 못 받음 | **반영** - 컨테이너 레벨 `onDragStart` 추가 |
| FYI | `visibilitychange` flush가 한 번도 관측 안 된 상태에서도 `page_no=0`을 실제 위치로 오인해 쏨 | **반영** - `hasObservedRef` 가드 추가 |
| FYI | 이미지 `src`가 문자열이 아니면 빈 `src`로 렌더돼 현재 페이지 URL을 재요청하는 `<img>`가 생김 | **반영** - `src` non-string이면 렌더 자체 스킵 |

Critical 0. `dangerouslySetInnerHTML`의 XSS 면적을 서버 화이트리스트와 실제 대조 확인(§2), `client:only` 선택의 근거도 함께 검증됨.

---

## 5. 검증

- `pnpm --filter frontend lint`: 통과
- `pnpm --filter frontend astro check`: 0 errors / 0 warnings / 1 hint(기존, 무관)
- `pnpm --filter frontend test`(vitest run): 13 files, 132 passed
- `pnpm --filter frontend build`: 통과(Sentry token·sourcemap 경고는 기존 비차단 경고)
- PR #123 CI: backend/frontend/admin 3 jobs 성공
- 사용자 브라우저: 전체 무료·부분 유료 회차, 잠금 placeholder, 진행도 복원, 보호 동작, SSR 본문 부재, 이미지 즉시 요청·우선순위와 스크롤 중 재요청 부재를 확인했다.
- 본문 이미지 8장 회차의 DevTools 실측: `8 / 83 requests`, `55.9 kB / 5,911 kB transferred`, `53.6 kB / 5,918 kB resources`, Finish 7.88s, DOMContentLoaded 595ms, Load 853ms. 5MB를 크게 초과한 것으로 보지 않아 결정 6을 유지한다.

---

## 6. 이연 / 후속

| 항목 | 이동처 | 근거 |
|------|--------|------|
| `scrollIntoView` 복원 오차(이미지 로딩 중 레이아웃 성장) 개선 | **대폭 완화 (2026-07-26, §7)** | 이미지 로드 대기 + 상시 재-앵커로 완화. **완전 해결은 아님** - 아래 잔여 항목 참조 |
| `visibilitychange` flush의 keepalive 미보장 유실 | 후속 | C1 결정(저장 실패 조용히 무시)상 허용 범위 |
| `onerror` 복구가 이미지 1장이 아니라 문서 전체를 재요청·치환(다른 이미지도 재요청됨) | 후속 | 정상 경로에선 안 타는 폴백이라 낮은 우선순위(2026-07-26 재검토에서 발견, 이번 보완 범위 밖) |
| `episodeNo` 파싱이 `Number()` 그대로라 `"05"`·`"0x5"`·`"5e0"` 등 비정규 문자열도 통과(정규 URL 하나 원칙과 어긋남, 보안 영향 없음) | 후속 | 2026-07-26 재검토에서 발견, 이번 보완 범위 밖 |
| `login_hint` 쿠키가 세션 만료 후에도 남아있으면 진행도 저장이 매번 조용히 실패·반복(네트워크 낭비만) | 후속 | 2026-07-26 재검토에서 발견, 이번 보완 범위 밖 |
| `handleImageError`의 콘텐츠 전체 재요청 도중 복원 effect가 캡처해둔 `target`/`imagesAbove`가 stale해질 수 있음(블록 배열이 바뀌면 이미 unmount된 DOM을 참조) | 후속 | xhigh 리뷰 PLAUSIBLE - 발생 시 복원이 조용히 no-op(에러 없음), 2026-07-26 재검토에서 발견 |
| 초기 `scrollToTarget()`이 이미지 로드 완료 전(2초 타임아웃)에 실행되면 IntersectionObserver 진행도 저장 effect가 그 순간의 위치를 진행도로 저장해, 다음 방문 시 한 블록 앞으로 되돌아갈 수 있음 | 후속 | xhigh 리뷰 PLAUSIBLE, 2026-07-26 재검토에서 발견 |
| `programmaticScrollRef` 해제가 단일 `requestAnimationFrame`이라 `scrollIntoView`의 비동기 `scroll` 이벤트 도착 타이밍과 어긋나면 자기 스크롤을 사용자 스크롤로 오인해 재-앵커가 영구 무력화될 수 있음 | 후속 | xhigh 리뷰 PLAUSIBLE, 2026-07-26 재검토에서 발견 |
| `wheel`/`touchmove`도 `programmaticScrollRef` 게이트를 타 좁은 시간창에서 실제 사용자 입력이 무시될 수 있음(`scroll`만 비동기라 게이트가 필요, wheel/touchmove는 애초에 불필요) | 후속 | xhigh 리뷰 PLAUSIBLE, 2026-07-26 재검토에서 발견 |
| 유료 구간(경계 뒤) 렌더·구매 검증 | M3 | B2와 동일 이연 사유 |

---

## 7. 후속 보완 (2026-07-26)

F1(PR #101)이 이미 머지된 상태에서 별도 세션이 F1 계획을 처음부터 재검증하며 두 가지 갭을 발견해 좁게 보완했다. 나머지 발견(§6 표의 `onerror` 범위·`episodeNo` 파싱·`login_hint` stale)은 이번 스코프에서 의도적으로 제외했다(우선순위 낮음, 별도 후속으로 이연).

### 이전/다음 화 링크에 `data-astro-reload`

`Viewer`는 `client:only="react"` 아일랜드다. `<BaseLayout>`의 전역 `<ClientRouter />`가 이전/다음 화 `<a>` 클릭을 클라이언트 사이드 라우팅(DOM morph)으로 가로챌 경우, 이 자리의 `astro-island`가 제거·재생성되지 않고 `episodeId` 등 attrs만 갈아 끼워질 위험이 실측 전에는 배제되지 않았다(Astro 공식 문서: `data-astro-reload`는 `<a>`/`<form>`에 붙이면 ClientRouter를 무시하고 전체 페이지 새로고침을 강제한다). React 루트가 재생성되지 않으면 이전 화 상태(스크롤 위치·observer·pending 저장 등)가 새 회차로 넘어가는 사고가 날 수 있다 - 흔한 경로(연속 정주행)라 전체 새로고침이라는 가장 값싼 방법으로 이 위험 자체를 구조적으로 없앴다(트레이드오프: 다음 화 이동이 SPA 전환보다 느려진다).

### 진행도 복원 - 이미지 로드 대기 + 재-앵커

기존 로직은 `restoredIndex`가 정해지면 `scrollIntoView`를 즉시 호출해, 복원 위치보다 위쪽 이미지가 아직 로드되지 않았으면(레이아웃이 덜 자란 상태) 스크롤이 실제 위치보다 위쪽에서 멈췄다(§6에 알려진 한계로 기록돼 있던 것). 계획 검증 단계에서 사용자가 "FE 완화 + 실측 후 판단"을 선택해 아래로 보완했다:

1. 복원 위치까지(포함) 등장하는 이미지 전부를 모아 `img.decode()`로 로드를 기다리되, 이미지 1장당 2초 상한(`RESTORE_IMAGE_TIMEOUT_MS`)을 둔다 - 상한이 없으면 깨진 이미지 하나가 복원 자체를 막는다.
2. 상한 안에 로드가 끝나면 그 시점에 `scrollIntoView`.
3. 그 이미지들에 `load` 리스너를 **effect가 정리될 때까지 계속** 붙여둔다(한 번만 듣고 떼는 게 아니라 상시) - `img.complete`가 이미 true였거나 `img.decode()`가 성공으로 착각했더라도, `onerror` 폴백의 콘텐츠 재요청으로 `src`가 나중에 바뀌어 실제로 다시 로드되면 `load`가 다시 발생한다. 그 사실 하나에만 의존해 재-앵커한다 - 완벽한 정확도 대신 "대부분의 경우 정확, 늦어도 스스로 보정"을 택했다.
4. 사용자가 스크롤(`scroll`/`wheel`/`touchmove`)을 직접 시작하면 이후의 모든 자동 스크롤(최초 복원·재-앵커)을 즉시 취소한다 - 프로그램적 스크롤과 사용자 스크롤을 플래그(`programmaticScrollRef`)로 구분해 판별한다. 이 플래그와 "사용자가 스크롤했다" 자체(`userScrolledRef`)는 컴포넌트 마운트 시점부터 별도 effect로 켜둔다 - 복원 effect 안에서만 감지를 시작하면 `getProgress` 응답을 기다리는 동안(느린 연결) 이미 시작된 스크롤을 놓치고, 응답이 늦게 와서야 위치를 되돌려버리는 문제가 있었다(2026-07-26 xhigh 코드 리뷰 CONFIRMED, 수정 완료).

CLS(레이아웃 시프트) 자체는 여전히 남는다(이미지가 로드되며 문서 높이가 자란다) - 이번 보완은 "복원 위치 정확도"만 다루고, CLS 실측은 결정 6의 회차당 바이트 실측과 함께 사용자 수동 확인으로 남긴다.

### 2026-07-26 xhigh 코드 리뷰 (Workflow 기반)

이 보완 자체를 대상으로 `/code-review ultra`(xhigh)를 돌려 14건 검증(10건 리포트, 0건 기각). CONFIRMED 6건은 모두 반영했다:

1. 위 §7 "복원 위치 정확도" 항목 3·4(재-앵커 상시화, 스크롤 감지 마운트 시점 이전화)로 세 가지가 한 번에 해소됨 - (a) `getProgress` 대기 중 스크롤을 못 보던 마운트 타이밍 공백, (b) 이미 로드 완료(`img.complete`)였던 이미지가 `onerror` 폴백으로 재로드돼도 재-앵커가 안 걸리던 문제, (c) `img.decode().catch(() => undefined)`가 `src` 교체로 인한 `EncodingError`를 로드 성공으로 오인하던 문제.
2. per-image `load` 리스너가 effect 자체 cleanup에서 추적·제거되지 않던 누수 - `once: true` + 수동 `setTimeout` 제거 대신 `detachFns` 배열로 추적해 effect cleanup에서 일괄 해제.
3. 이 표(§6)의 "해소" 표기가 같은 문단의 "완화" 서술과 자기모순이었던 문서 정확성 문제 - "대폭 완화(완전 해결 아님)"로 정정 + 잔여 PLAUSIBLE 4건을 §6에 추가.
4. `docs/guides/GUIDE_ASTRO.md`에 `data-astro-reload` 델타 미기록 - 추가 완료.

PLAUSIBLE 4건(§6 표 참조 - stale 클로저·진행도 중간값 저장·rAF 타이밍 레이스·wheel/touchmove 불필요 게이트)은 실제로 일어나는지 확신이 낮고 타이밍에 의존적이라 이번 스코프에서는 반영하지 않고 후속으로 이연했다.

### 검증

- `pnpm --filter frontend test`(vitest run): 28 passed (회귀 없음, 신규 유닛 테스트는 추가하지 않음 - 순수 DOM 타이밍 로직이라 vitest 기본 환경 대상이 아니라 수동 확인 대상)
- `pnpm --filter frontend astro check`: 0 errors / 0 warnings / 1 hint(기존, 무관)
- 수동 e2e(스크롤 중 복원 위치 확인, 이전/다음 화 이동 시 아일랜드 재마운트 확인)는 **사용자가 직접 확인**(Playwright 미도입 결정 유지)

---

## 8. 긴 단일 이미지 내부 추적·복원 (2026-08-14)

### 문제

`398x5400`처럼 여러 웹툰 패널을 한 파일에 합친 원고는 화면상 많은 패널을 지나도 최상위 문서 블록은 이미지 1개다. 기존 `IntersectionObserver`는 그 이미지가 계속 뷰포트와 교차하는 동안 callback을 다시 호출하지 않고, 저장값도 같은 블록 인덱스에 머물러 재진입 시 이미지 시작으로 돌아갔다.

### 구현

- observer는 현재 보이는 블록 후보만 관리한다.
- passive `scroll` 이벤트를 `requestAnimationFrame`당 한 번으로 제한해 뷰포트 상단을 포함하는 블록의 `getBoundingClientRect()`를 다시 읽는다.
- `clamp(-rect.top / rect.height, 0, 1) * 10000`을 정수 `block_offset_bp`로 저장한다.
- 복원 시 대상 이미지까지 로드·decode를 기다린 뒤 `blockDocumentTop + blockHeight * offset`으로 이동한다. 늦은 이미지 `load`에도 같은 상대 지점으로 재앵커한다.
- 회차 전체 `scrollHeight`를 분모로 쓰지 않으므로 이 값은 M3의 전체 진행률이나 완독 상태가 아니다.

### 자동 검증

`viewer.test.ts`는 5400px 블록을 3240px 지나면 6000bp가 되고, 현재 렌더 높이에서 같은 상대 Y로 복원되는지와 0..10000 클램프를 검사한다. DOM 스크롤·이미지 로드 타이밍은 프로젝트 원칙대로 사용자 브라우저에서 확인했다.

2026-08-15 리뷰에서 느린 진행도 GET보다 초기 observer PUT이 먼저 실행될 수 있는 경쟁을 발견했다. 복원 판정 전에는 위치 계산만 하고 저장을 잠그며, GET 결과 없음·사용자 선행 스크롤·복원 완료 중 하나로 판정된 뒤에만 PUT한다. jsdom 컴포넌트 테스트가 GET을 2초 지연해 그동안 PUT이 0회인지 검사한다. `putProgress` 요청 body에 두 위치 값이 함께 실리는지도 API mock으로 고정했다. 사용자 브라우저에서는 긴 이미지 중간에서 작품 상세로 나갔다 재진입해 같은 패널 부근으로 돌아오는 것을 확인했다.

---

## 9. 콘텐츠 요청 실패 복구 (#116, 2026-08-17)

### 문제와 원인

`getEpisodeContent`는 404만 `null`로 바꾸고 네트워크 오류와 5xx는 throw한다. 기존 `Viewer`는 초기 요청과 이미지 `onError`의 콘텐츠 재요청에 `then`만 연결해 rejection을 처리하지 않았다. 초기 실패는 `content=undefined`를 영구히 유지해 무한 로딩이 됐고, 이미지 재발급 실패는 unhandled rejection으로 남았다.

### 구현

- 콘텐츠 요청 상태를 `loading / success / notFound / error` 판별 유니온으로 분리했다. 404 `null`은 기존 notFound 안내를 유지하고, rejection은 오류 안내와 `다시 시도` 버튼으로 종료한다.
- 초기 요청, 수동 재시도, 이미지 URL 재발급을 하나의 요청 effect로 통합했다. effect cleanup의 `cancelled`가 늦은 성공과 실패를 모두 무시한다.
- 이미지 `onError` 재발급 중에는 기존 콘텐츠를 유지해 문서 높이와 스크롤 위치가 무너지지 않게 한다. 콘텐츠 재발급 요청 자체가 실패하면 전체 오류 상태로 전환하며 회차당 자동 재요청은 1회로 제한한다.
- 실기능 확인에서 재발급 성공 뒤 새 이미지 URL도 실패하면 `alt=""` 이미지가 조용히 접혀 페이지 누락을 독자가 모르는 공백을 발견했다. 자동 재발급 중 함께 도착한 옛 URL의 추가 error는 무시하고, 새 URL도 실패한 최상위 이미지 블록만 `×` 아이콘과 오류 문구가 있는 최소 높이 placeholder로 교체한다. 이미지별 버튼은 두지 않으며 사용자는 필요하면 페이지를 새로고침한다.
- boto3 SigV4는 같은 초에 같은 키를 다시 서명하면 기존과 동일한 URL을 반환할 수 있다. React가 같은 key와 `src`의 `<img>`를 재사용하면 새 요청과 두 번째 error가 모두 사라지므로, 성공한 콘텐츠 응답마다 이미지 렌더 세대를 올리고 이를 `<img>` key에 포함한다. 재발급 요청을 시작한 시점이 아니라 응답이 DOM에 반영되는 시점에만 재마운트해 pending 중 옛 이미지 error 무시도 유지한다.
- 상태에 `episodeId`를 함께 저장하고 회차가 바뀌면 콘텐츠, 오류, 이미지 재시도, 복원·저장 관련 ref와 타이머를 초기화한다. 이전 회차의 늦은 응답은 새 회차를 덮어쓰지 못한다.
- 진행도 GET 실패 시 PUT을 열지 않는 fail-closed 동작과 `getEpisodeContent`의 404/null, 그 외 throw 계약은 변경하지 않았다.

### 자동 검증

- `Viewer.test.tsx`: 초기 reject 오류 UI, 수동 재시도 성공, 404 notFound, 이미지 재발급 reject, 재발급 중 복수 옛 이미지 실패의 단일 요청, 새 URL과 동일 URL 재발급 뒤의 개별 이미지 placeholder, 회차별 retry·placeholder 초기화, 이전 회차 늦은 resolve 무시, 언마운트 뒤 reject 처리를 검증한다.
- `viewer.test.ts`: 404를 `null`로 변환하고 5xx·네트워크 오류를 그대로 전파하는 API 계약을 검증한다.
- `pnpm --filter frontend test`: 9 files, 92 tests 통과.
- `pnpm --filter frontend astro check`: 0 errors, 0 warnings, 기존 hint 1건.
- `pnpm --filter frontend build`: 성공. Sentry auth token 미설정과 기존 sourcemap 경고만 남았다.
- 정상, 404, 네트워크 실패, 다시 시도, 이미지 재발급 실패, 새 URL도 실패한 이미지 placeholder 흐름의 브라우저 확인은 프로젝트 원칙대로 사용자가 수행한다.

---

## 10. 비로그인 기기 로컬 진행도 (#117, 2026-08-18)

### 저장 계약

비로그인은 `dweb:viewer-progress:v1:{episodeId}` key에 `{ pageNo, blockOffsetBp, updatedAt }`만 저장한다. `pageNo`는 0..INT32_MAX 정수, `blockOffsetBp`는 0..10000 정수, `updatedAt`은 0 이상의 safe integer epoch milliseconds다. JWT, 사용자 ID, 이미지 key·URL, 구매·완독 상태는 저장하지 않는다.

`guestProgress.ts`는 JSON과 범위를 검증하는 순수 로직, 주입된 Storage를 다루는 함수, `window.localStorage` 획득 자체의 SecurityError까지 삼키는 브라우저 어댑터로 나뉜다. 손상된 현재 버전 레코드는 다음 정상 저장 시 제거하고, 유효 레코드는 `updatedAt` 오름차순으로 최근 100개만 유지한다. 시각이 같으면 key 정렬로 제거 결과를 결정적으로 만들고, 작품 CTA의 최근 회차는 작가 지정 공개 순서에서 뒤쪽 회차를 tie-breaker로 사용한다.

### Viewer 상태 경계

복원 effect가 먼저 `login_hint`를 한 번 판별해 저장 대상을 ref에 고정한다. 로그인은 서버 GET/PUT, 비로그인은 로컬 read/write 중 하나만 사용한다. 로컬 복원도 기존 `canSaveProgress` gate를 거쳐 저장값 판정 전에 초기 `(0, 0)`을 덮어쓰지 않으며, 기존 이미지 load 대기·재앵커와 본문 축소 시 block clamp를 그대로 재사용한다. debounce와 `visibilitychange` flush도 선택된 저장 대상 하나만 호출한다.

로컬 값은 렌더 허용 범위에 관여하지 않는다. 본문은 계속 서버가 절단한 B2 응답만 렌더하고 `has_paid_part` 잠금 placeholder도 그대로 표시한다. 따라서 사용자가 localStorage를 수정해도 스크롤 복원 위치만 달라질 뿐 유료 구간 key나 URL을 얻을 수 없다.

### 자동 검증

- guest storage: 유효 저장·읽기, 손상 JSON, 음수·초과·비정수, 구버전 key, SecurityError, quota 예외, 손상 레코드 제거, 101번째 저장의 최오래 항목 제거, 공개 회차 교집합과 최신 시각 선택.
- Viewer: 비로그인 API 호출 0회와 로컬 저장, 로그인 localStorage 접근 0회와 서버 저장, 본문 축소 clamp + 블록 내부 위치 복원, 유료 경계 유지, episodeId 전환 격리.
- 사용자 브라우저 확인 완료(2026-08-18): 비로그인 스크롤·재진입, 긴 이미지 내부 복원, 로그인 서버 경로, paywall 유지, storage 차단 환경이 정상 동작한다.

---

## 11. 스크롤 방향 반응형 상하단 컨트롤 (#121, 2026-08-20)

### 셸과 상태 소유권

정상 뷰어는 BaseLayout의 전역 Navbar·Footer를 렌더하지 않고 Viewer 안의 고정 상단 헤더와 하단 회차 이동 컨트롤을 사용한다. SSR 셸은 공개 작품·현재 회차·인접 회차 메타만 island prop으로 넘기고 스크린리더용 h1은 HTML에 유지한다. 작품 상세 오류·404에서는 Viewer가 마운트되지 않으므로 기존 전역 chrome을 그대로 표시한다.

컨트롤을 별도 아일랜드로 분리하지 않았다. Viewer의 진행도 복원이 프로그램적으로 스크롤하므로, 같은 컴포넌트에서 복원 목표 Y를 컨트롤 scroll reducer의 기준점으로 먼저 동기화해야 자동 복원을 하향 읽기로 오인하지 않는다. 컨트롤 listener와 기존 진행도 listener는 관심사와 rAF를 분리하되 각각 cleanup한다.

### 노출 상태와 접근성

- 최초·문서 최상단·최하단은 visible이다.
- 같은 방향의 하향 이동 48px 누적 시 hidden, 상향 이동 24px 누적 시 visible이다.
- 방향 전환은 누적 거리를 새 방향 기준으로 다시 센다. 작은 상하 흔들림은 임계값에 도달하지 않는다.
- fixed + transform·opacity 전환만 사용해 본문 레이아웃을 밀지 않는다. safe-area inset을 상단 padding과 하단 bottom에 더한다.
- `motion-reduce:transition-none`으로 이동 애니메이션을 제거한다. hidden surface는 `inert`, `aria-hidden`, pointer 차단을 함께 적용한다.

### 이동과 공유

상단은 작품 상세, 작품·회차 제목과 부제, 공유, 작품 상세 `#episodes` 목록으로 연결하며 제목 옆 잠금 표시는 노출하지 않는다. 플로팅 하단과 본문 끝 제목형 nav는 공개 배열의 실제 인접 회차 링크를 쓰며 `data-astro-reload`를 유지한다. 첫·마지막 회차에서 플로팅 컨트롤의 없는 방향은 아이콘 위치를 유지한 disabled button과 `aria-disabled`로 표현한다.

공유는 `navigator.share`가 있으면 제목과 현재 URL을 전달하고, 미지원 또는 취소 외 실패이면 `navigator.clipboard.writeText`로 폴백한다. 성공·복사·최종 실패는 `aria-live="polite"` status로 알린다. 사용자 취소는 오류로 표시하지 않는다.

### 자동 검증

- `viewerControls.test.ts`: 47/48px 하향, 23/24px 상향, 방향 전환, 미세 흔들림, 상하단 경계, 프로그램적 기준 동기화.
- `ViewerControls.test.tsx`: 작품·목록·인접 회차 경로, 전체 새로고침 속성, 긴 제목 말줄임, 경계 disabled·aria, hidden inert, Web Share와 clipboard fallback·실패 안내.
- `Viewer.test.tsx`: 상하단 동시 전환, 진행도 자동 복원 뒤 최초 visible, unmount listener·rAF 정리와 기존 진행도·paywall 회귀.
- Frontend 전체 gate: lint 통과, Astro check 0 errors와 기존 무관 hint 1건, 13 files·132 tests 통과, build 성공. Sentry token·sourcemap 경고는 기존 baseline이다.
- 사용자 브라우저 확인 완료(2026-08-20): 데스크톱·모바일에서 집중 모드 컨트롤과 본문 끝 회차 이동을 포함한 실기능이 정상 동작한다.
