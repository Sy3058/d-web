# IMPLEMENTATION - 관리자 Vite React SPA 골격 (B7)

관련 마일스톤: M0 B7 (`docs/milestones/M0_foundation.md`)
브랜치: `admin/chore/vite-spa-scaffold`

---

## Background / Context

- `admin/`은 5/23에 기본 Vite + React 템플릿만 생성된 상태였고, B7 산출물 요구사항인 **Tailwind**와 **TanStack Router**가 빠져 있었다.
- 이 골격 위에 M1.5(관리자 로그인/2FA, 작품·에피소드 업로드)가 올라가므로, 라우팅·스타일 토대를 먼저 정확히 깔아야 했다.

## Decision

- **Tailwind v4** - `@tailwindcss/vite` 플러그인 + `src/index.css`의 `@import "tailwindcss"`. 프론트(Astro)와 동일 버전·방식으로 통일.
- **TanStack Router 파일 기반 라우팅** - `@tanstack/router-plugin/vite`(`target: 'react'`, `autoCodeSplitting: true`) + `src/routes/`(`__root.tsx`, `index.tsx`). 생성물 `src/routeTree.gen.ts`.
- **`routeTree.gen.ts`는 커밋한다** (gitignore 하지 않음). 이유는 Caution 참조.
- **Vite 플러그인 순서**: `tanstackRouter()` → `react()` → `tailwindcss()`. router 플러그인이 react 플러그인보다 먼저여야 함(TanStack 문서).
- **devtools**(`TanStackRouterDevtools`)는 `__root.tsx`에서 무조건 렌더. 패키지가 프로덕션에서 `() => null` no-op이라 번들에서 트리셰이킹됨(Test Plan에서 검증).
- **TanStack Query / react-hook-form은 이번 범위에서 제외** - admin/CLAUDE.md엔 등장하지만 기능(M1.5) 작업 시 추가. 골격 단계엔 불필요.
- 기존 Vite 보일러플레이트(`App.tsx/css`, `assets/`, 데모용 `public/icons.svg`) 제거. `index.html` lang=ko + 제목 한글화.

## Why

- 파일 기반 라우팅: M1.5에서 로그인 가드(`beforeLoad`)·중첩 라우트·loader가 붙을 때 타입 안전 라우트 트리가 자동 생성되어 유리. 코드 기반 수동 트리보다 유지보수 단순.
- Tailwind v4 통일: FE/admin이 같은 설정 방식이라 컨텍스트 전환 비용이 낮음.

## Caution

변경 시 깨질 수 있는 전제 - 특히 CI(F1/F2) 구성 시 주의.

1. **`routeTree.gen.ts` ↔ `tsc -b` chicken-egg**
   - `build` 스크립트가 `tsc -b && vite build` 순서라 tsc가 **먼저** 돈다. 그런데 이 파일은 vite(플러그인)가 생성한다.
   - 따라서 파일이 없는 fresh checkout / CI에서 tsc가 `Cannot find module './routeTree.gen'`로 실패 → **반드시 커밋**해 둬야 함. **gitignore 추가 금지.**
   - 파일 헤더에 `@ts-nocheck` + `/* eslint-disable */`가 있어 tsc/eslint는 안전하나, **biome 도입(F1) 시 포맷 대상이 될 수 있으니 ignore 등록** 필요.

2. **eslint `react-refresh/only-export-components` false positive**
   - 라우트 파일은 `export const Route` + 로컬 컴포넌트(`function Home`) 구조라 이 룰이 error를 낸다.
   - **직관적 수정인 `allowExportNames: ['Route']`는 안 통한다.** 룰 로직상 `Route`는 비컴포넌트 export 목록에서 빠지지만, 컴포넌트가 *export 안 된 로컬*(`localComponents`)이라 별도 경로로 계속 걸린다.
   - **정답: `eslint.config.js`에서 `src/routes/**`에 한해 룰 off.** HMR은 router 플러그인이 처리하므로 실제 fast-refresh는 정상.

3. **devtools가 devDependency인데 프로덕션 소스에서 import**
   - 일반 빌드(`npm ci`로 devDep 포함)는 정상이고 프로덕션 번들엔 빠진다.
   - 단, CI가 `npm ci --omit=dev` 후 빌드하면 모듈 해석 실패. **F2 빌드 워크플로우는 devDep 포함 빌드를 유지**할 것.

## Test Plan

- `npm run lint` → exit 0
- `npm run build`(tsc + vite) → exit 0, Tailwind CSS 컴파일 확인
- `npm run dev` → `GET /` 200 (B7 DoD)
- 프로덕션 번들에 devtools 미포함 검증: `grep -rl "RouterDevtools" dist/assets/*.js` → 결과 없음
