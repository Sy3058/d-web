# 웹툰 작가 개인 사이트

독자용 Astro 사이트, Vite + React 관리자 SPA, FastAPI API로 구성된 1인 작가의 웹툰 판매·열람 플랫폼이다.

## 작업 원칙

- 사용자에게는 한국어로 설명한다.
- 현재 Git 상태와 저장소 문서를 과거 대화나 AI 메모보다 우선한다. 시작 전 `git status --short`, 현재 브랜치, 관련 구현과 문서를 확인한다.
- 사용자의 기존 변경을 덮어쓰거나 되돌리지 않는다. 이 저장소는 여러 worktree와 병렬 브랜치를 사용할 수 있다.
- 라이브러리·API·프로토콜의 버전 민감한 사실은 공식 문서에서 확인한다.
- 모든 파일에서 em dash(U+2014)를 쓰지 않고 hyphen(-)을 쓴다.
- 신규 `CHANGELOG`는 만들지 않는다. 출시 전 변경 기록은 `docs/DECISIONS.md`, 마일스톤 문서와 태그로 관리한다.
- 브라우저 실기능 확인은 사용자가 수행한다. Playwright E2E는 도입하지 않고 정적 검사·단위/통합 테스트까지만 실행한다.

## 보안 불변조건

- 결제 금액과 구매 권한은 서버에서 검증한다. 클라이언트 값만 믿지 않는다.
- 미구매 사용자에게 유료 구간 이미지 키나 URL을 반환하지 않는다. 무료 콘텐츠도 서버에서 paywall 경계로 절단한 뒤 허용된 키만 서명한다.
- JWT를 localStorage에 저장하지 않는다. HttpOnly 쿠키를 사용한다.
- CORS `*`, 환경변수 하드코딩, 원시 SQL 문자열 조합을 금지한다.
- TOTP 시크릿과 개인정보를 클라이언트나 로그에 노출하지 않는다.

## 문서 확인 시점

- 계획·설계 또는 기존 결정 변경 전: `docs/DECISIONS.md`
- 구현·마이그레이션·테스트·CI 전: `docs/MISTAKES.md`의 관련 영역
- 브랜치·커밋·PR·세션 종료 작업 전: `docs/guides/GUIDE_WORKFLOW.md`
- 커밋 메시지 작성 전: `docs/guides/GUIDE_COMMIT.md`
- 코드 리뷰 전: `docs/reviews/GUIDE_REVIEW.md`와 영역별 리뷰 문서
- goal ledger 또는 `task_harness.local` 작업 전: `docs/guides/GUIDE_TASK_HARNESS.md`
- `study/` 작성·복습 전: `docs/guides/GUIDE_STUDY.md`
- 현재 범위와 완료 상태 판단: `docs/milestones/README.md`와 해당 `*_foundation.md`

## 구현과 검증

- Python 명령은 backend 환경에서 `uv run`으로 실행한다. 예: `cd backend && uv run pytest`.
- Backend 기본 게이트: `cd backend && uv run ruff format --check . && uv run ruff check . && uv run pytest`.
- Frontend 기본 게이트: `pnpm --filter frontend astro check && pnpm --filter frontend test && pnpm --filter frontend build`.
- Admin 기본 게이트: `pnpm --filter admin lint && pnpm --filter admin test && pnpm --filter admin build`.
- 변경 범위에 맞는 최소 게이트부터 실행하고, 완료 전 관련 전체 게이트를 실행한다. 실행하지 못한 검증은 이유와 함께 명시한다.
- 의미 있는 구현은 `docs/MODULES/.../IMPLEMENTATION_*.md` 작성 대상인지 확인하고, 완료된 작업은 관련 마일스톤과 결정 문서에 반영한다. 사소한 수정은 생략할 수 있다.
- 현재 학습용 `LEARN:` 주석은 추가하지 않는다. 기존 방지 훅은 남은 마커가 커밋되는 것을 막기 위해 유지한다. `study/`와 `blog.md`는 gitignore된 로컬 자료다.

## Git 작업

- 브랜치를 임의로 만들거나 바꾸지 않는다. 새 작업 브랜치는 사용자의 확인을 받고 항상 최신 main에서 분기한다.
- 커밋 전에 diff와 메시지 초안을 보여주고 사용자의 명시적 승인을 받는다. push와 tag는 각각 별도 승인을 받는다.
- 커밋 메시지는 한 줄 `[PREFIX] type: 제목` 형식을 기본으로 하고 AI 생성 문구나 공동 작성자 표기를 넣지 않는다.
- main 직접 push는 금지된다. `.githooks`의 보호 규칙을 유지한다.

## Codex workflows

- 계획·설계에는 `$fable-plan`, 구현·디버깅에는 `$fable-exec`, 리뷰에는 `$fable-review`를 사용한다.
- 중요한 아키텍처·마일스톤 계획을 여러 관점으로 검증할 때 `$council-review`를 사용한다.
- 현재 모델보다 높은 품질 설정이 필요한 DB·동시성·보안·아키텍처 작업은 착수 전에 사용자에게 권장 모델과 reasoning 수준 변경을 요청한다.

## 범위 제외

멤버십/구독, 묶음 할인 신규 구현, 무통장 입금, 소설 뷰어, 포렌식 워터마크, Grafana, 관리자 IP 화이트리스트는 현재 문서에서 명시적으로 착수하지 않는 한 구현하지 않는다.
