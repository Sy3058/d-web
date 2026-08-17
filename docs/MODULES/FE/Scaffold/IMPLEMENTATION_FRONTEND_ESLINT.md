# Frontend ESLint 구현

## 상태

- 구현일: 2026-08-18
- 범위: Astro 독자용 frontend의 `.astro`, `.js`, `.ts`, `.tsx`와 루트 설정 파일
- 제외: type-aware lint, Prettier, JSX a11y, import 정렬, 스타일 규칙

## 구성

`frontend/eslint.config.js`는 ESLint 10 flat config로 다음 preset을 조합한다.

- `@eslint/js` recommended
- `typescript-eslint` recommended
- `eslint-plugin-astro` recommended
- `eslint-plugin-react-hooks` flat recommended

공통 JS/TypeScript/React Hooks config의 파일 범위에도 `.astro`를 포함하고, 뒤에 오는 Astro preset이 최종 parser를 `astro-eslint-parser`로 설정한다. 그 내부 TypeScript parser는 `parserOptions.parser`로 연결한다. 따라서 Astro 전용 규칙뿐 아니라 frontmatter의 일반 JS/TypeScript 오류도 같은 명령에서 검사한다.

Astro 플러그인은 minor 버전에서도 recommended preset이 바뀔 수 있다는 공식 정책에 따라 `~3.0.1`로 고정했다. `.astro`는 ESLint CLI 기본 탐색 대상이 아니므로 `package.json`의 lint glob에 확장자를 직접 포함한다. 플러그인의 Node 24 요구와 package engine은 모두 24.16.0 이상으로 맞춘다. `dist`, Astro 생성 디렉터리 `.astro`, coverage는 검사에서 제외한다.

`src/env.d.ts`의 triple-slash reference는 Astro가 생성한 타입을 연결하는 엔트리라 해당 파일에서만 TypeScript ESLint 규칙을 제외한다. Viewer의 진행도 복원 effect는 GET 완료 전에 저장을 막는 fail-closed 게이트를 동기 초기화해야 하므로 해당 한 줄에만 `react-hooks/set-state-in-effect` 예외와 근거를 둔다.

frontend와 admin은 `typescript-eslint` 8.67 계열을 함께 사용해 pnpm lockfile에 같은 lint 도구의 중복 버전을 남기지 않는다. 최초 frontmatter 전체 적용에서 발견한 `tags`의 불필요한 초기 대입은 동작 변경 없이 제거했다. lint 대응으로 바뀐 로그인 성공 이동과 이메일 토큰 초기화는 jsdom 회귀 테스트로 `/my` 이동과 쿼리 토큰 API 전달을 고정한다.

## CI와 검증

GitHub Actions frontend job은 의존성 설치 후 `pnpm --filter frontend lint`를 `astro check`보다 먼저 실행한다. 로컬 기본 게이트도 lint, astro check, test, build 순으로 확인한다. 대표 Astro, TS, TSX 파일에는 `eslint --print-config`로 실제 flat config 적용 여부를 확인하며, Astro 결과에는 `astro-eslint-parser`, 내부 TypeScript parser와 `@typescript-eslint/no-unused-vars`가 모두 있어야 한다.
