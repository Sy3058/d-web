# Astro 작업 가이드 (현재 Astro 7.x)

> **목적**: 버전별 Astro API 차이와 이 프로젝트의 Astro 컨벤션을 한 곳에 모아 반복 조사를 줄인다.
>
> **사용 규칙 (read-through 캐시)**
> 1. Astro 작업 전 루트와 `frontend/AGENTS.md`, 이 문서를 함께 읽는다.
> 2. 아래 내용은 확인 날짜와 현재 설치 버전을 함께 본다.
> 3. 버전 민감한 API는 **사용 시점에 Astro 공식 문서로 재확인**하고, 새 차이를 찾으면 근거와 날짜를 이 문서에 반영한다.
>
> **현재 스택**: `astro@^7.2.4`, Astro 내장 `vite@8.2.2`, `@astrojs/node@^11.1.4`, `@astrojs/react@^6.0.4`, `@tailwindcss/vite@4`, Node `>=24.16`. 실제 설치 범위는 `frontend/package.json`과 lockfile을 우선한다.

---

## 확인된 API와 프로젝트 적용

### 1. 렌더링 모드 - 기본은 static, adapter가 있어도 안 바뀐다

- `output` 기본값 = `'static'` → **사이트 전체가 기본적으로 프리렌더(SSG)** 된다.
- **adapter를 추가해도 기본 렌더 모드는 그대로 static.** adapter는 온디맨드 렌더링을 *가능*하게만 한다 (자동으로 SSR로 바뀌지 않음).
- 페이지 단위로 모드 전환:
  ```js
  // 기본 static 사이트에서 이 페이지만 SSR
  export const prerender = false;
  ```
- `'hybrid'` 출력 모드는 **폐지**됨(static에 흡수). `output: 'hybrid'` 쓰지 말 것.
- 참고: `output: 'server'`로 두면 반대로 전부 SSR이 기본이 되고 `export const prerender = true`로 페이지를 프리렌더. **이 프로젝트는 `output` 미설정(=static)** 이 정석.
- **이 프로젝트 적용**: `astro.config.mjs`에 `output` 없음(=static). 로그인 후 페이지(`my/*`)·뷰어 SSR은 페이지마다 `export const prerender = false` 명시. 구글 OAuth 콜백은 백엔드 BFF 수신이라 프론트 SSR 콜백 페이지 없음.
- 출처: https://docs.astro.build/en/guides/on-demand-rendering/

### 2. 타입 세이프 환경변수 `astro:env` (신규 API)

- 기존 방식은 그대로 유효: `import.meta.env.PUBLIC_*`(클라+서버 노출) / `PUBLIC_` 없는 변수(서버 전용).
- 추가로 스키마 기반 `astro:env`:
  ```js
  // astro.config.mjs
  import { defineConfig, envField } from "astro/config";
  export default defineConfig({
    env: {
      schema: {
        PUBLIC_API_URL: envField.string({ context: "client", access: "public" }),
        API_SECRET:     envField.string({ context: "server", access: "secret" }),
      },
    },
  });
  ```
  - import: `astro:env/client`(client·public), `astro:env/server`(server public/secret).
  - `access: "secret"`은 server 전용. **client secret은 불가**(보안 차단). 동적 조회는 `getSecret("X")`.
- **주의 1**: `astro:env/server`에서 무엇이든 import하면 *스키마의 모든 secret이 검증*된다. `validateSecrets` 설정과 배포 환경 주입을 공식 문서에서 확인한다.
- **주의 2**: `astro:env`는 Astro 컨텍스트(컴포넌트·라우트·엔드포인트·미들웨어)에서만. `astro.config.mjs`·외부 스크립트에선 못 씀 → `process.env` / Vite `loadEnv()`.
- **이 프로젝트 적용**: 브라우저 공개 주소는 `PUBLIC_API_URL`, Node SSR 내부 주소는 `API_INTERNAL_URL`을 사용한다. `PUBLIC_`이 아닌 값은 클라이언트 코드나 렌더된 HTML에 노출하지 않는다. `.astro`라는 확장자만으로 안전하다고 가정하지 말고 렌더링 모드와 번들 경계를 확인한다.
- **Node SSR 런타임(2026-08-13 확인)**: `@astrojs/node` standalone의 런타임 환경변수는 `process.env.API_INTERNAL_URL`로 읽는다. 이 adapter는 `.env`를 런타임에 자동 로드하지 않으므로 self-hosted Docker/compose의 `environment`에서 직접 주입한다. `import.meta.env.SSR` 분기 안에서만 `process.env`를 참조해 클라이언트 번들에 내부 주소가 들어가지 않게 한다. 브라우저용 `PUBLIC_API_URL`과 SSR용 `API_INTERNAL_URL`을 같은 값으로 강제하지 않는다.
- 출처: https://docs.astro.build/en/guides/environment-variables/

### 3. 프리렌더 페이지엔 쿼리 파라미터가 없다 (검증 2026-07-19)

- 공식 문서 원문: "On prerendered pages, `request.url` does **not** contain search parameters, like `?type=new`, as it's not possible to determine them ahead of time during static builds. However, `request.url` **does** contain search parameters for pages rendered on-demand."
- `Astro.url`은 `request.url`에서 파생되므로 **정적 페이지에서 `Astro.url.searchParams`는 항상 비어 있다.** 빌드 시점엔 미래의 요청 쿼리를 알 수 없기 때문이라 우회가 없다.
- ⇒ **규칙: 쿼리 파라미터를 서버에서 읽어야 하면 그 페이지는 `export const prerender = false`.** 클라이언트에서 `location.search`로 읽는 우회는 가능하나, 그 값으로 DOM을 바꾸면 하이드레이션 후 삽입이라 레이아웃 시프트가 생긴다(없던 블록이 생기는 배너류에서 특히).
- **이 프로젝트 적용**: `auth/login.astro`가 SSR인 이유가 이것(구글 OAuth BFF 실패 시 백엔드가 `?error=`로 리다이렉트 → 첫 페인트에 배너). M2 E1(작품 목록)도 `?page=`·`?tag=`를 서버에서 읽으므로 **신선도 근거와 무관하게 SSR이 강제**된다.
- 출처: https://docs.astro.build/en/reference/api-reference/

### 4. 클라이언트 라우팅 컴포넌트 - `<ClientRouter />` (구 `<ViewTransitions />`)

- `<ViewTransitions />`는 **옛 이름**. 현재는 **`<ClientRouter />`**.
  ```astro
  ---
  import { ClientRouter } from "astro:transitions";
  ---
  <head>
    <ClientRouter />
  </head>
  ```
- `transition:persist`, `transition:name` 등 디렉티브는 그대로. 뷰 트랜지션 스캐폴딩 시 옛 이름 쓰지 말 것.
- 출처: https://docs.astro.build/en/guides/view-transitions/

### 5. 뷰 트랜지션 건너뛰기 - `data-astro-reload` (검증 2026-07-26)

- `<a>` 또는 `<form>`에 `data-astro-reload` 속성을 붙이면 `<ClientRouter />`가 그 탐색을 무시하고 **브라우저 기본 전체 페이지 새로고침**을 강제한다(공식 문서 원문 확인).
- `client:only` 아일랜드가 있는 페이지 사이를 이동할 때, ClientRouter의 DOM morph가 그 자리의 `astro-island`를 제거·재생성하지 않고 attrs만 갈아 끼울 가능성을 실측 없이 배제할 수 없다면(React 루트가 새 props로 재마운트되지 않아 이전 페이지 상태가 새 페이지로 새어 들어갈 위험), 그 이동 경로의 링크에 `data-astro-reload`를 붙이는 것이 가장 값싼 구조적 예방책이다 - 트레이드오프는 그 이동이 SPA 전환보다 느려진다는 것.
- **이 프로젝트 적용**: `works/[id]/[publicId].astro`의 이전/다음 화 네비 `<a>`에 사용한다. `Viewer`가 `client:only="react"` 아일랜드라 회차 간 상태 누수를 구조적으로 차단한다(M2 F1 후속 보완, 2026-07-26).
- 출처: https://docs.astro.build/en/guides/view-transitions/

### 6. Astro 7 migration 기준선 (검증 2026-08-24)

- Astro 7은 Vite 8과 Rolldown을 사용한다. 현재 프로젝트에는 `build.rollupOptions`나 Vite 내부 API를 쓰는 사용자 설정이 없어 설정 이름 변경이 필요하지 않았다.
- `.astro` Rust 컴파일러는 닫히지 않은 태그를 오류로 처리하고 무효 HTML을 자동 교정하지 않는다. 현재 템플릿은 `astro check`와 production build를 통과했다.
- `compressHTML` 기본값은 `'jsx'`다. 인라인 요소 사이의 개행이 자동 공백이 되지 않으므로 문장 안의 요소 경계에는 명시적 공백을 둔다. 현재 인접 인라인 요소는 flex gap이나 구분점으로 배치되어 텍스트 공백 의존이 없음을 정적 확인했다.
- Markdown과 MDX의 기본 처리기는 Sätteri다. 현재 프로젝트는 Markdown/MDX와 remark/rehype 플러그인을 사용하지 않아 추가 migration이 없다.
- `src/fetch.ts`와 `src/fetch.js`는 advanced routing 예약 파일명이다. 현재 같은 이름의 파일이 없다.
- Node adapter는 기본 세션 드라이버를 제공하지만 이 프로젝트는 FastAPI HttpOnly 쿠키만 사용한다. `session: false`를 유지해 Astro 파일시스템 세션과 세션 런타임을 끈다.
- 출처: https://docs.astro.build/en/guides/upgrade-to/v7/ , https://docs.astro.build/en/guides/sessions/

---

## 이 프로젝트 Astro 컨벤션 (공식 문서에 없음)

- **Tailwind는 `@tailwindcss/vite` 플러그인**(`vite.plugins`)으로 연결. 구 `@astrojs/tailwind` 통합 아님.
- **현재는 Astro 7 + Vite 8을 사용한다.** frontend는 Astro가 Vite를 관리하므로 별도 Vite devDep을 두지 않고, admin도 Vite 8로 맞춘다. [Astro 7 공식 발표](https://astro.build/blog/astro-7/)
- adapter: `@astrojs/node`, `mode: 'standalone'`, `session: false`. integrations: `react()`, `sentry()`.
- 섬 지시어 규칙: 로그인·결제·OAuth=`client:load`, 댓글·하트·후원=`client:idle`, 하단 위젯=`client:visible`.
- 쿠키: `.astro`(SSR)는 `Astro.request.headers`로, React 섬은 `fetch(..., { credentials: 'include' })`. JWT localStorage 금지.

---

## dev 함정

- **`504 (Outdated Optimize Dep)`**: 실행 중인 `pnpm dev` 상태에서 의존성이나 CSS `@import`를 추가·제거하면 Vite 최적화 캐시가 무효화되고 브라우저가 옛 청크 URL을 들고 있어 504가 난다(Astro 런타임 파일에 떠도 원인은 Vite 캐시).
  → 해결: dev 중지 → `rm -rf node_modules/.vite` → 재시작 → 브라우저 하드 리프레시(Ctrl+Shift+R).
- `.env`는 dev 시작 시점에 주입된다. 수정 후 dev를 재시작한다(`docs/MISTAKES.md`).

---

## 사용 시점에 공식 문서로 재확인할 것 (아직 미검증)

아래 항목은 도입 시 설치된 Astro 버전의 공식 문서로 확인하고 결과를 위 절에 추가한다.

- 콘텐츠 컬렉션 / Content Layer (`loader`, `glob()`): 작품·에피소드를 파일 기반 CMS로 둘 경우. https://docs.astro.build/en/guides/content-collections/
- Actions / Sessions: 폼 액션·서버 세션 도입 시. https://docs.astro.build/en/guides/actions/ , https://docs.astro.build/en/guides/sessions/
- 이미지 (`astro:assets`): 정적 이미지 최적화 시(웹툰 본문은 R2 Signed URL이라 별개). https://docs.astro.build/en/guides/images/
- 미들웨어: 인증 가드를 프론트에 둘 경우. https://docs.astro.build/en/guides/middleware/
