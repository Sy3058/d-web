# 뷰어 - 콘텐츠 문서 렌더러 (M2 그룹 F1)

| 항목 | 내용 |
|------|------|
| 모듈 | Frontend / Viewer (독자 열람 경로 - 콘텐츠 문서 렌더러) |
| 관련 마일스톤 | [M2](../../../milestones/M2_foundation.md) 그룹 F (F1, WORK-05~08) |
| 작성 시점 | M2 F1 (2026-07-25), 후속 보완 (2026-07-26 - §7), 긴 블록 복원 보강 (2026-08-14 - §8) |
| 상태 | 구현 + 리뷰 반영. 긴 단일 이미지 내부 추적·복원 자동 테스트와 사용자 브라우저 재진입 확인 통과(2026-08-15). M2 전체 수동 e2e는 그룹 H의 나머지 항목 확인 대기 |
| 관련 문서 | M2_foundation.md 그룹 F·결정 1/3/6, IMPLEMENTATION_FREE_CONTENT_API.md(B2 계약 원본), IMPLEMENTATION_VIEWER_PROGRESS.md(C1 계약), IMPLEMENTATION_CATALOG_PAGES.md(E, SSR 셸/캐시 정책 원본), IMPLEMENTATION_EPISODE_CONTENT_MODEL.md(#76, 서버 스키마 원본) |

비로그인 독자가 `/works/{id}/{publicId}`에서 회차 본문(글+이미지 혼합 TipTap 문서)을 읽는 페이지. B2가 절단·presigned 치환한 무료 구간을 아일랜드가 fetch해 렌더하고, 유료 경계가 있으면 말미에 잠금 placeholder를 보여준다. 로그인 상태면 읽은 위치(블록 인덱스 + 블록 내부 상대 위치)를 저장·복원한다(C1). 유료 구간 반환·결제 검증은 M3.

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

진행도 GET/PUT을 비로그인 상태에서 아예 안 쏘기 위한 게이트. 401을 받은 뒤 처리하는 대신 요청 자체를 막는다 - `Navbar.astro`의 네비 로그인 표시와 동일한 판별 원천(`lib/auth.py:90 LOGIN_HINT_COOKIE_NAME`)을 재사용해 두 판정이 어긋나지 않는다.

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

- `pnpm --filter frontend astro check`: 0 errors / 0 warnings / 1 hint(기존, 무관)
- `pnpm --filter frontend test`(vitest run): 79 passed
- 수동 e2e는 사용자가 직접 확인한다. 로그인 긴 이미지 내부 저장·재진입 복원은 2026-08-15 통과했다. 스크롤 중 이미지 재요청, Network 탭 fetchPriority/no-store, SSR 응답 본문 부재, 드래그·우클릭 차단과 회차당 전송 바이트·이미지 장수 등 M2 전체 항목은 그룹 H 결과를 따른다.

---

## 6. 이연 / 후속

| 항목 | 이동처 | 근거 |
|------|--------|------|
| 회차당 전송 바이트 실측 결과 반영 | 사용자 확인 후 | 결정 6 재검토 조건(5MB 크게 초과 시 lazy 복귀가 아니라 서명 쿠키를 M3로) |
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
