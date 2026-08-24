# IMPLEMENTATION - pnpm workspace + packages/shared (B8)

관련 마일스톤: M0 B8 (`docs/milestones/M0_foundation.md`)
브랜치: `common/feat/shared-package`

---

## Background / Context

- frontend(`lib/api.ts`, `lib/validation.ts`)와 admin이 동일한 fetch 래퍼, Zod 스키마, API 응답 타입을 필요로 한다.
- B6(Astro 골격), B7(Vite React SPA 골격) 완료 후 각자 독립 패키지 상태였고, 공통 코드가 없었다.
- DECISIONS.md "FE/Admin 공유 코드" 결정: pnpm workspace + `packages/shared`로 공통 코드 분리.

## Decision

### createApi 팩토리 패턴

공유 API 래퍼를 `createApi(baseUrl)` 팩토리 함수로 설계했다.

Astro(frontend)와 Vite(admin)의 환경변수 접두사가 다르기 때문:
- Astro: `import.meta.env.PUBLIC_API_BASE_URL`
- Vite: `import.meta.env.VITE_API_BASE_URL`

shared 패키지가 어떤 환경변수를 읽어야 할지 알 수 없으므로 baseUrl을 외부에서 주입받는다.

```typescript
// packages/shared/src/lib/api.ts
export function createApi(baseUrl: string) { ... }

// frontend/src/lib/api.ts
export const api = createApi(import.meta.env.PUBLIC_API_BASE_URL ?? 'http://localhost:8000');

// admin/src/lib/api.ts
export const api = createApi(import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000');
```

### ApiError - 파라미터 프로퍼티 대신 명시적 필드

admin의 `tsconfig.app.json`에 `erasableSyntaxOnly: true` 설정이 있어 파라미터 프로퍼티(`public status: number`) 사용 불가. 필드 명시 + 직접 할당으로 작성.

### exports 필드로 TypeScript 소스 직접 참조

빌드 단계 없이 TypeScript 소스를 직접 export. Vite/Astro가 TypeScript를 처리하므로 별도 컴파일 불필요.

```json
{
  "exports": { ".": "./src/index.ts" }
}
```

### Vite 버전 통일 (7 임시 고정에서 8로 migration)

pnpm workspace 설정 후 `@tailwindcss/vite@4.3.0`의 Rust 네이티브 바인딩 버그로 frontend 빌드 실패.

- 원인: admin의 vite@8 의존성으로 인해 pnpm이 workspace 전체에서 `@tailwindcss/vite`를 vite@8 바인딩으로 resolve. Astro(vite@7) 환경에서 실행 시 `tsconfigPaths` 필드 누락 에러.
- 당시 해결: admin을 `vite@^7` + `@vitejs/plugin-react@^5`로 낮추고, frontend `package.json`에 `vite@^7` devDep을 명시해 peer 해석 고정.
- 최종 해결(2026-08-24): frontend를 Astro 7로 올리고 admin을 `vite@^8` + `@vitejs/plugin-react@^6`으로 전환했다. frontend의 직접 Vite 고정을 제거하고 `pnpm why`로 양쪽이 `vite@8.2.2` 하나를 해석함을 확인했다.

## Why

- 팩토리 패턴: 환경변수 의존성을 shared에서 분리, 각 패키지가 자신의 컨텍스트에 맞게 인스턴스 생성.
- exports에 `.ts` 직접 참조: 별도 빌드 파이프라인 없이 단순하게 유지. 향후 OpenAPI 자동 생성 타입 추가 시에도 동일 패턴 유지 가능.

## Caution

- 의존성 잠금의 단일 진실은 저장소 루트 `pnpm-lock.yaml`이다. frontend/admin 하위 `package-lock.json`은 두지 않으며 명령은 workspace 루트에서 pnpm으로 실행한다.
- frontend는 Astro가 Vite 버전을 관리하므로 별도 Vite devDep을 두지 않는다. 다시 직접 고정해야 한다면 workspace 전체의 peer 해석을 먼저 확인한다.
- admin은 Vite 8과 `@vitejs/plugin-react@^6`을 함께 유지한다. 한 앱의 Vite major만 바꾸지 말고 `pnpm why --filter <패키지> vite`로 실제 해석을 검증한다.
- packages/shared의 zod 스키마 (`loginSchema`)는 v3 호환 문법 유지 중. zod v4 권장형(`z.email()`)으로 전환은 M1 인증 폼 작업 시 진행.

## Test Plan

- [x] `pnpm --filter frontend run build` 통과
- [x] `pnpm --filter admin run build` 통과
- [x] Astro 7/Vite 8 migration 후 frontend lint, Astro check, 테스트, 빌드 통과 (2026-08-24)
- [x] Vite 8 migration 후 admin lint, 테스트, 빌드 통과 (2026-08-24)
- [ ] `pnpm --filter frontend dev` 실행 후 `/` 200 응답 확인 (빌드 통과로 대체)
