# 반복 실수 패턴

작업 중 실수가 발생하면 여기에 추가.
사용법: `@docs/MISTAKES.md 참고해서 [작업] 해줘`

---

## 사용 예시

```
@docs/MISTAKES.md 참고해서 결제 API 구현해줘
@docs/MISTAKES.md 참고해서 FastAPI 라우터 작성해줘
```

---

## FastAPI

<!-- 실수 발생 시 여기에 추가 -->
<!-- 예시:
- SQLModel 관계에서 lazy loading으로 N+1 발생
  → selectinload 명시적으로 써야 함
- 포트원 webhook 금액 검증 누락
  → 결제 API는 항상 서버에서 금액 재검증
-->

## Astro / React

<!-- 실수 발생 시 여기에 추가 -->
<!-- 예시:
- React 아일랜드에 client: 지시자 누락 → hydration 안 됨
- Signed URL 만료 시간 너무 짧게 설정 → 뷰어 로딩 중 만료
-->

## Vite / Astro

- Vite dev 서버 시작 후 `.env` 파일을 생성/수정해도 반영 안 됨
  -> `VITE_*` 환경변수는 서버 시작 시점에 번들에 주입됨
  -> `.env` 생성 전에 `pnpm dev`를 먼저 띄우면 env가 undefined로 뜸
  -> 해결: `.env` 작성 후 dev 서버 재시작

## 공통

- pnpm workspace에서 `@tailwindcss/vite` peer dep 충돌
  → admin이 vite@8을 쓰면 workspace 전체에서 `@tailwindcss/vite`가 vite@8 바인딩으로 resolve됨
  → Astro 6 (vite@7) 환경에서 `tsconfigPaths` 누락 에러 발생
  → 해결: 각 패키지에 peer 고정 (`frontend`에 `vite@^7` devDep 명시)
  → 근본 해결은 Astro 7 (vite@8) 출시 후 일괄 업그레이드 (DECISIONS.md 참조)

- pnpm workspace 추가 후 lockfile이 구버전 peer 해석을 캐싱할 수 있음
  → `pnpm install --force` 또는 `rm pnpm-lock.yaml && pnpm install`로 강제 재계산
  → `pnpm why --filter <패키지> <dep>` 으로 실제 resolve 경로 확인

- 백엔드 Python 실행 시 `python` 대신 `uv run python` 사용
  → `python` 명령은 PATH에 없음. `uv run python`, `uv run uvicorn`, `uv run pytest` 형태로 실행할 것

- 이미 push된 커밋을 rewrite(`reset --soft`/rebase/amend)하면 로컬과 origin이 갈라진다(divergence)
  → 히스토리 재작성 전 push 여부 확인: `git status -sb`(ahead/behind) 또는 `git rev-parse origin/<branch>`
  → 이미 pushed면 (1) 새 커밋으로 fix-forward가 기본, (2) 굳이 정리하면 `--force-with-lease` 필요함을 먼저 고지
  → 이 repo는 squash-merge라 중간 커밋은 어차피 합쳐지므로 정리 목적 rewrite는 대개 불필요

- 코딩 완료 후 커밋 전 반드시 Opus 검증 단계 거칠 것
  → 순서: 계획(Opus) → 코딩(Sonnet) → 검증(Opus) → 커밋
  → Opus 없이 바로 `git commit`으로 넘어가지 말 것

## Claude 작업 효율 (셸/검증 패턴)

- 셸 출력이 지연되면 빈 결과를 "사실"로 오판하지 말 것 (이번 세션 최악의 실수 원인)
  → 한 명령의 결과가 비어 있거나 늦게 와도, 그걸 근거로 "파일 없음 / 깨끗함 / 성공"이라 단정 금지
  → 특히 파괴적 작업(rm, 삭제, downgrade) 전엔 상태를 한 번 더 확정 후 진행
  → 실제 사고: 이미 존재하던 `DB_SCHEMA.md`를 빈 read 결과 보고 "없음"으로 오판해 삭제 (git에서 복구함)

- 같은 확인 명령을 5~6번 반복하지 말 것
  → 출력이 늦으면 `flush`용 echo를 난사하는 대신, 결과를 파일로 redirect(`> /tmp/x.txt 2>&1`)하고 Read로 한 번에 읽기
  → 여러 검증을 한 번에: sentinel(`echo START ... echo END`)로 감싸 한 블록으로 확인

- 파일을 만들기 전에 "없다"고 가정하지 말 것
  → 새로 만들/지울 파일은 먼저 `git ls-files`나 Read로 존재 여부 확정
  → autogenerate(alembic 등)가 만든 파일명/리비전 ID를 추측해서 쓰지 말 것. 실제 생성된 파일을 Read로 확인 후 사용

- AskUserQuestion 답을 받기 전에 진행하지 말 것
  → 도구 호출이 guard/취소로 무산되면 답을 못 받은 것. "받은 척" 후속 작업 금지

- 한 가지 변경을 두 가지 방법으로 동시에 하지 말 것 (방법 하나만 택일)
  → 실제 사고: 인덱스 추가를 (1) 기존 마이그레이션 파일 직접 수정 + (2) `alembic revision --autogenerate`로 새 파일 생성, 둘 다 해서 인덱스가 중복 생성 → `DuplicateTableError`
  → 변경 전에 "기존 파일 수정 vs 새 마이그레이션" 중 하나를 먼저 정하고, 그 하나만 실행

- "셸 지연 해결됐다"고 단정하지 말 것
  → 지연은 해결된 게 아니라 우회(`sleep` + 파일 redirect + Read)하는 것일 뿐. 상태를 낙관적으로 보고하지 말 것

- 브랜치 머지 여부를 `git branch --merged`로만 판단하지 말 것 (이 repo는 squash-merge)
  → squash-merge는 원본 커밋이 main에 그대로 안 남아 `--merged`에 안 잡힘 → "안 머지됨"으로 오판
  → 실제 사고: 이미 PR로 squash-merge된 브랜치를 "작업 안 끝남"이라 잘못 보고함
  → 확인법: `git fetch` 후 `git log origin/main --oneline`에 squash 커밋(`... (#PR번호)`) 있는지, 또는 PR 상태 직접 확인

- 이 환경엔 `gh` CLI가 설치돼 있지 않음 (`gh: command not found`)
  → `gh pr status` 등이 빈/에러 출력을 내도 "PR 없음"으로 단정 금지 (빈 셸 출력 오판 패턴의 변종)
  → PR 상태는 사용자가 알려주는 GitHub 화면 정보나 `git log origin/main`으로 교차 확인

## Alembic 마이그레이션

- 이미 DB에 적용(upgrade)된 마이그레이션 파일을 직접 편집하지 말 것
  → 파일을 고쳐도 DB는 옛 버전이라 `downgrade`/`check`가 어긋나 깨짐 (파일의 drop_index가 없는 인덱스를 지우려다 실패 등)
  → 아직 미커밋·로컬 단계면: `alembic downgrade base` → 파일 수정 → `alembic upgrade head`로 깨끗하게 재적용
  → 이미 커밋·푸시됐으면: 기존 파일 두고 **새 마이그레이션**으로 변경분만 추가 (forward-only)

- psql로 직접 `DROP/CREATE TABLE` 하지 말 것 (guard가 차단함)
  → 스키마 변경은 항상 alembic 경유. DB 리셋이 필요하면 `alembic downgrade base`

- 마이그레이션 작업 후엔 반드시 `alembic check`로 모델↔DB 동기화 확인
  → "No new upgrade operations detected"가 나와야 정상. 떠 있는 diff가 있으면 모델/마이그레이션 불일치

## pytest / 비동기 DB 테스트

- session-scope async 엔진 픽스처를 쓰면 루프 스코프를 **둘 다** 맞춰야 한다
  → `pyproject.toml [tool.pytest.ini_options]`에 `asyncio_default_fixture_loop_scope = "session"` **그리고** `asyncio_default_test_loop_scope = "session"` 둘 다 필요
  → 하나만 하면 테스트 함수는 function 루프, 엔진은 session 루프라 asyncpg 커넥션이 `RuntimeError: got Future ... attached to a different loop`
  → 실제 사고: fixture 스코프만 session으로 바꾸고 "됐겠지" 했다가 그대로 깨짐. test 스코프까지 맞춰야 통과

- 테스트 DB(`dweb_test`)는 첫 실행 전에 직접 생성해야 함
  → 없으면 `asyncpg.exceptions.InvalidCatalogNameError: database "dweb_test" does not exist`
  → 이 환경엔 `psql`이 없으니 컨테이너 경유: `docker exec d-web-postgres-1 psql -U postgres -c "CREATE DATABASE dweb_test;"`
  → 컨테이너 이름은 `docker ps --format "{{.Names}}"`로 확인 (compose 기본값 `d-web-postgres-1`)

- FK 있는 모델을 INSERT하는 테스트는 부모 행을 먼저 만들 것
  → 랜덤 `uuid.uuid4()`를 FK 컬럼에 넣으면 `ForeignKeyViolationError` (`refresh_tokens.user_id` → `users.id`)
  → 부모(User) 픽스처를 만들고 그 `.id`를 쓴다

- 서비스가 `session.commit()`을 직접 호출하면 rollback-격리 픽스처와 충돌
  → conftest의 "트랜잭션 begin → 끝에 rollback" 격리 방식은 service가 commit하면 `InterfaceError: another operation is in progress`
  → 해결: `async_sessionmaker`로 세션 주고, 테스트 후 `metadata.sorted_tables`를 reversed 순으로 DELETE해 정리
