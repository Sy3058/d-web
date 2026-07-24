# 뷰어 - 콘텐츠 문서 렌더러 (M2 그룹 F1)

| 항목 | 내용 |
|------|------|
| 모듈 | Frontend / Viewer (독자 열람 경로 - 콘텐츠 문서 렌더러) |
| 관련 마일스톤 | [M2](../../../milestones/M2_foundation.md) 그룹 F (F1, WORK-05~08) |
| 작성 시점 | M2 F1 (2026-07-25) |
| 상태 | 구현 + Opus 코드 리뷰(CODE_REVIEW_FE + GUIDE_REVIEW) 완료(Critical 0, Major 1 반영, FYI 3 반영). `astro check` 0 errors / 0 warnings / 1 hint(기존, 무관) + `vitest` 28/28 통과. **수동 e2e(브라우저 실기능)·회차당 전송 바이트 실측은 사용자 확인 대기**(Playwright 등 브라우저 자동화 미도입 결정에 따름) |
| 관련 문서 | M2_foundation.md 그룹 F·결정 1/3/6, IMPLEMENTATION_FREE_CONTENT_API.md(B2 계약 원본), IMPLEMENTATION_VIEWER_PROGRESS.md(C1 계약), IMPLEMENTATION_CATALOG_PAGES.md(E, SSR 셸/캐시 정책 원본), IMPLEMENTATION_EPISODE_CONTENT_MODEL.md(#76, 서버 스키마 원본) |

비로그인 독자가 `/works/{id}/{episodeNo}`에서 회차 본문(글+이미지 혼합 TipTap 문서)을 읽는 페이지. B2가 절단·presigned 치환한 무료 구간을 아일랜드가 fetch해 렌더하고, 유료 경계가 있으면 말미에 잠금 placeholder를 보여준다. 로그인 상태면 읽은 위치(블록 인덱스)를 저장·복원한다(C1). 유료 구간 반환·결제 검증은 M3.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `frontend/package.json` | `@tiptap/core`·`@tiptap/starter-kit`·`@tiptap/extension-link`·`@tiptap/pm` 3.27.4 고정(admin과 버전 통일 - 스키마 패리티), devDep `jsdom` 추가(테스트 전용 - §3) |
| `frontend/src/pages/works/[id]/[episodeNo].astro` | SSR 셸(`prerender = false`) - 회차 메타·이전/다음 네비만. 본문은 `client:only="react"` 아일랜드가 담당 |
| `frontend/src/components/viewer/Viewer.tsx` | 아일랜드 - B2 fetch, 최상위 블록 분할 렌더(image는 React `<img>` 직접 제어, 나머지는 `generateHTML` 조각), 잠금 placeholder, 진행도 저장·복원, 콘텐츠 보호 |
| `frontend/src/components/viewer/extensions.ts` | 뷰어 전용 TipTap 렌더 스키마(서버 화이트리스트·admin 에디터와 1:1, image attrs만 `src` 예외) |
| `frontend/src/components/viewer/extensions.test.ts` | `getSchema` 스키마 대조 테스트 + `generateHTML` 렌더 동작 테스트(rel/target 강제 확인) |
| `frontend/src/lib/viewer.ts` | B2/C1 계약 타입 + `getEpisodeContent`/`getProgress`/`putProgress` + 순수 로직(`imageFetchPriority`/`clampBlockIndex`/`isLoggedIn`) |
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
- `pnpm --filter frontend test`(vitest run): 28 passed
- 수동 e2e(브라우저 실기능 - 스크롤 중 이미지 재요청 여부, Network 탭 fetchPriority/no-store, SSR 응답 본문 부재, 로그인 진행도 저장/복원, 드래그·우클릭 차단 등)와 회차당 전송 바이트·이미지 장수 실측(결정 6 재검토 조건, 5MB 초과 여부)은 **사용자가 직접 확인** - 프로젝트가 Playwright/chromium-cli 등 브라우저 자동화를 도입하지 않기로 한 결정에 따름. 결과가 오면 본 문서·M2_foundation.md에 반영 예정.

---

## 6. 이연 / 후속

| 항목 | 이동처 | 근거 |
|------|--------|------|
| 회차당 전송 바이트 실측 결과 반영 | 사용자 확인 후 | 결정 6 재검토 조건(5MB 크게 초과 시 lazy 복귀가 아니라 서명 쿠키를 M3로) |
| `scrollIntoView` 복원 오차(이미지 로딩 중 레이아웃 성장) 개선 | 후속 | 알려진 한계로만 기록, 즉시 전량 요청이라 대부분 빠르게 안정 |
| `visibilitychange` flush의 keepalive 미보장 유실 | 후속 | C1 결정(저장 실패 조용히 무시)상 허용 범위 |
| 유료 구간(경계 뒤) 렌더·구매 검증 | M3 | B2와 동일 이연 사유 |
