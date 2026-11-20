# FE·Admin import 경로 별칭

## 적용 기준

2026-11-20 사용자 요청으로 독자 Astro 앱과 관리자 Vite React 앱에 같은 import 규칙을 적용했다. 깊은 상대경로의 가독성과 파일 이동 시 경로 수정 부담을 줄이는 것이 목적이다.

```ts
import PageContainer from '@/components/layout/PageContainer.astro';
import { api } from '@/lib/api';
import ProfileEditor from './ProfileEditor';
```

- 다른 폴더의 앱 내부 모듈: 앱별 `src` 기준 `@/` 별칭.
- 같은 폴더의 파일: `./` 상대경로.
- `@d-web/shared`, `astro:*`, 외부 패키지와 HTTP URL은 기존 식별자를 유지한다.
- 테스트 mock·동적 import·import 타입·재수출도 같은 대상을 가리키도록 바꾼다.
- 자동 생성된 Admin `routeTree.gen.ts`, `api.gen.ts`는 직접 고치지 않는다. 생성기가 관리하는 상대경로는 허용한다.
- Node가 직접 실행하는 SSR 검증 스크립트나 앱 루트 설정 파일의 경로는 `src` 내부 import 규칙의 대상이 아니다.
- CSS 내부 `@import`·자산 URL은 CSS 파일 기준의 상대경로를 유지한다. JS/TS/Astro의 side-effect CSS import에는 모듈 경로 규칙을 적용한다.

## 설정의 원본

| 앱/실행 경계 | 설정 |
| --- | --- |
| FE TypeScript·Astro | `frontend/tsconfig.json`의 `paths: { "@/*": ["./src/*"] }` |
| FE Vitest | `resolve.tsconfigPaths: true`로 같은 tsconfig 읽기 |
| Admin TypeScript | `admin/tsconfig.app.json`의 같은 paths 정의 |
| Admin Vite·Vitest | `resolve.tsconfigPaths: true`, 루트 tsconfig의 references를 통해 앱 설정 읽기 |

별도 라이브러리를 설치하지 않고 기존 Vite 8의 경로 해석을 활용했다. 앱의 소스 경로를 Vite·Vitest 설정에 다시 하드코딩하지 않는다. 기본 JSX/렌더링·플러그인 순서·환경변수·인증·API 계약은 유지한다. 새 코드도 같은 규칙을 사용하도록 Frontend·Admin `AGENTS.md`에 기록했다.

공식 근거: [Astro aliases](https://docs.astro.build/en/guides/imports/#aliases), [Vite tsconfigPaths](https://vite.dev/config/shared-options.html#resolve-tsconfigpaths), [Vite tsconfig references](https://vite.dev/guide/features.html#typescript-compiler-options), [Vitest 설정](https://vitest.dev/config/).

## 검증 범위

Frontend lint·Astro check·전체 단위 테스트·build·production SSR HTTP 검증과 Admin lint·전체 단위 테스트·build를 수행한다. 설정 변경 후 실제 dev 홈을 포함한 적용 페이지와 뷰어·Admin 모듈의 변환 응답도 확인한다. 브라우저 실기능 확인은 사용자가 수행한다.

2026-11-20 결과:

- TypeScript AST로 모듈 specifier만 변경했다. FE 55개 파일·182건, Admin 57개 파일·160건을 전환하고 같은 폴더 참조·일반 문자열·생성 파일을 보존했다.
- Frontend lint, Astro check(115 files·오류/경고 0·기존 hint 1), 테스트 377개, build와 SSR HTTP 19개 통과.
- Admin lint, 테스트 139개, TypeScript 검사 포함 build 통과.
- 기존 Astro dev는 변경 전 별칭 설정을 유지해 `Cannot find module '@/...'`로 500을 응답했다. 실제 로그를 확인하고 해당 서버만 정상 종료·재시작하여 홈을 포함한 적용 경로를 확인했다. 별칭 설정과 소스 경로 변경은 시작 시점의 resolver에도 반영해야 한다.
- 실제 dev 홈·계정 5개·인증 3개·작품·커미션 11개 경로, live Viewer와 TipTap 의존성, Admin `main.tsx`·`WorkForm.tsx` 변환 요청이 모두 HTTP 200이었다.
- dependency·lockfile·API 계약은 변경하지 않았다. 기존 Sentry 토큰 미설정·transitions sourcemap 빌드 경고는 유지된다.
