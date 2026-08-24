# d-web 독자 사이트

Astro 기반 독자용 frontend이다. 의존성은 저장소 루트의 pnpm workspace와 `pnpm-lock.yaml`로 관리한다.

## 명령

모든 명령은 저장소 루트에서 실행한다.

| 명령 | 용도 |
| :--- | :--- |
| `pnpm install --frozen-lockfile` | workspace 의존성 설치 |
| `pnpm --filter frontend dev` | 로컬 개발 서버 실행 |
| `pnpm --filter frontend lint` | ESLint 검사 |
| `pnpm --filter frontend astro check` | Astro 타입 및 템플릿 검사 |
| `pnpm --filter frontend test` | 단위 테스트 실행 |
| `pnpm --filter frontend build` | 프로덕션 빌드 |
| `pnpm --filter frontend preview` | 빌드 결과 미리보기 |
