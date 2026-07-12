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

## GitHub Actions / CI

- 액션을 `@vN`(메이저만)으로 박기 전에 그 메이저 **무빙 태그가 실제 있는지** 확인할 것
  → `astral-sh/setup-uv`는 v8부터 무빙 메이저 태그(`v8`)를 안 만든다 → `@v8`은 "Set up job"에서 `Unable to resolve action ... unable to find version v8`로 즉사(3초컷, 테스트 도달 못 함)
  → `actions/checkout`은 `v6` 무빙 태그가 있어 `@v6` OK. **액션마다 태그 정책이 다름**
  → 확인: `gh api repos/<owner>/<repo>/tags --jq '.[].name'`로 실제 태그를 본 뒤 정확한 버전(`@v8.2.0`)으로 핀. WebSearch 요약("v8 있다더라")만 믿고 박지 말 것 (실제 사고: 첫 CI가 그래서 두 번 빨강)
  → 정확한 버전 핀은 워크어라운드가 아니라 공급망 보안상 권장(무빙 태그는 같은 이름이 다른 커밋을 가리킬 수 있음). 다음 단계는 SHA 핀

- 커밋 타입 `ci`/`build`는 GUIDE_COMMIT.md엔 있지만 **commit-msg 훅이 거부**한다
  → 훅 허용 타입: `feat|fix|refactor|test|docs|style|chore|perf` 만
  → CI/인프라 변경은 `[INFRA] chore:`로 (실제 사고: `[INFRA] ci:`가 훅에 막혀 커밋 실패)

- commit-msg 훅은 제목(`type: ` 뒤 부분)이 **50자를 넘어도 거부**한다
  → 한글 제목에 괄호로 상세를 달면 금방 넘음. 짧게 쓰고 상세는 PR 본문/커밋 본문으로
  → 실제 사고: `[COMMON] docs: A1 후속(bundle_discount_rate C1 설정·idx_tags_name UNIQUE 대체)`(50자 초과) 거부 → `[COMMON] docs: A1 후속(할인율 C1 설정·idx_tags_name 정리)`로 줄여 재커밋

---

## FastAPI

- 고정 비싼 값(타이밍 평탄화 더미 해시 등 비번과 무관한 상수)은 **import 시 eager 생성**할 것
  → lazy 캐시(`global X; if X is None: X = bcrypt(...)`)로 미루면 첫 호출 때 bcrypt(~300ms)가 **이벤트 루프를 동기 블로킹**
  → 비용은 프로세스당 1회라 어차피 한 번 냄. lazy는 그 1회를 부팅(요청 안 받음, 무해)에서 요청 처리 중(유해)으로 옮길 뿐 → 손해
  → 모듈 로드 시 1회 생성(루프 없어 무해)이 정답. 실제 사고: M1 C `_dummy_hash` lazy → Opus 리뷰 Major

<!-- 예시:
- SQLModel 관계 lazy loading N+1 → selectinload 명시
- 포트원 webhook 금액 검증 누락 → 서버에서 금액 재검증
-->

## JWT / PyJWT

- 위조(forged) 토큰 테스트용 "틀린 시크릿"을 짧은 문자열로 쓰면 `InsecureKeyLengthWarning` 노이즈 발생
  → PyJWT는 HS256 서명 키가 32바이트 미만이면 경고를 낸다. `"wrong-secret"`(12자) 같은 값은 테스트 의도(서명 불일치 → 401)엔 문제없지만 경고가 낀다
  → 32바이트 이상의 임의 문자열(예: `"wrong-secret-0123456789abcdef0123456789abcdef"`)로 늘려서 해결. 실제 사고: M1.5 B2 `test_setup_forged_cookie_401`. B3의 `/admin/login/totp` pending 쿠키 위조 테스트에서도 동일 패턴 재발 가능성 높음

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

- env 값 존재 확인에 `sed 's/=.*/=<값 있음>/'` 식 마스킹을 쓰지 말 것 - **빈 값(`KEY=`)도 `=<값 있음>`으로 치환**돼 "채워짐"으로 오판
  → 실제 사고: M1.5 D 착수 시 R2 자격증명이 비어 있는데 "전부 채워져 있다"고 보고(블로커 해소 오판)
  → 값 자체를 노출하지 않고 확인하려면 길이/형식 검사로: `awk -F= '{print $1, length($2)}'` 또는 파이썬으로 `len(v)` 출력

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

- PR 머지 확인 시 "머지됨"만 보지 말고 **로컬 마지막 커밋이 머지분에 포함됐는지**까지 대조할 것
  → push와 추가 커밋이 엇갈리면(커밋 → 사용자 push → 추가 커밋 → 머지) 마지막 커밋이 빠진 채 머지될 수 있음
  → 확인법: pull 시 머지 diff 파일 목록에 마지막 커밋 산출물이 있는지, 또는 `git log origin/<브랜치> -1` tip == 로컬 tip 대조. 브랜치 삭제는 그 뒤에
  → 복구: 빠진 커밋은 main 워킹트리에 `git cherry-pick -n <sha>`(+`git reset`)로 미커밋 복원 후 다음 브랜치 편승 (main 직접 커밋/push 금지)
  → 실제 사고: C1 마지막 docs 커밋(6464e06)이 PR #60에서 빠짐 - 머지 diff 파일 목록 대조로 발견, cherry-pick -n으로 복구

- `gh` CLI는 이제 설치·인증돼 있음 (`/usr/bin/gh`, 2026-06-14 확인. 과거 "미설치"는 옛 환경)
  → `gh issue view`, `gh pr view/list`로 이슈·PR 상태 직접 조회 가능. 이슈 닫기/코멘트는 외부 동작이라 사용자 확인 후
  → 단 빈/에러 출력을 "없음"으로 단정하는 일반 함정은 여전히 주의. 머지는 `gh`로도 `git log origin/main`(squash 커밋 `... (#PR)`)으로도 교차 확인

- Bash 호출 간 작업 디렉터리(cwd)가 리셋될 수 있음 - 지속을 보장하지 말 것
  → backend 명령은 항상 `cd /home/ash99/project/d-web/backend && uv run ...` 형태로 경로를 명시
  → cwd 가정 시 `Failed to spawn: ruff`(루트엔 venv 없음)·`ModuleNotFoundError: No module named 'src'`로 깨짐. 실제 사고: 같은 `uv run`이 한 번은 되고 다음 호출엔 cwd가 루트로 돌아가 실패

- `ruff check --fix`를 파일 인자 없이 돌리면 **프로젝트 전체**가 대상이라 범위 밖 파일까지 고친다
  → 실제 사고: E1 작업 중 `uv run ruff check --fix`가 이미 커밋·DB 적용된 마이그레이션 파일의 import까지 정렬 → 커밋 스코프 오염(무관 파일 11건 중 9건이 그 마이그레이션)
  → 변경한 파일만 지정(`ruff check --fix <path...>`)하거나, 전체로 돌렸으면 직후 `git status`로 범위 밖 변경을 확인하고 `git checkout -- <파일>`로 되돌릴 것
  → 이미 DB 적용된 마이그레이션은 import 정렬뿐이라도 건드리지 말 것(위 "Alembic" 규칙과 연결)

- 계획 단계에서 사용자 승인 전에 파일 편집(코딩)으로 건너뛰지 말 것
  → 실제 사고: E1에서 "계획 세우자" 단계인데 `config.py`를 바로 Edit하기 시작 → 사용자가 두 번 제지("지금은 계획 세우는 단계야")
  → 계획(Opus)은 "무엇을·어떻게"와 변경 파일 목록까지만. 파일 쓰기는 사용자가 계획에 OK한 뒤 코딩 단계에서. 순서: 계획 → (승인) → 코딩 → 검증 → 커밋

- diff 조각만 보고 "버그"라 단정하기 전에 각 심볼의 실제 정의를 모듈별로 확인할 것
  → 실제 사고: #27 포맷 diff에서 `routers/auth.py`의 `detail=_UNAUTHORIZED`를 "HTTPException 객체를 detail에 넣은 버그"라 FYI 보고 → 허위 이슈 등록 직전까지 감
  → 원인: `_UNAUTHORIZED`가 두 모듈에 동명 존재(`routers/auth.py:52`=문자열 메시지, `lib/auth.py:145`=HTTPException 객체). diff 두 조각을 모듈 맥락 없이 한 화면에서 보다 한 바인딩으로 뭉침
  → 교훈: cross-module 동명 심볼은 같은 게 아님. grep/Read로 각 모듈의 실제 정의를 확인한 뒤에야 버그 단정. squash-merge repo라 허위 이슈는 노이즈만

- 본문 답변과 AskUserQuestion(퀴즈 등)을 같은 턴에 섞지 말 것
  → 도구 호출 **앞에** 쓴 텍스트는 사용자 화면에서 가려질 수 있음.
  → 답변이 턴의 최종 메시지가 되게 하고, 퀴즈/질문 도구는 다음 턴에. 또는 도구를 먼저 호출하고 결과 받은 뒤 최종 메시지에 본문을 담기

- `git diff HEAD`는 **untracked 신규 파일을 안 보여준다** - 리뷰/diff 스코프에서 신규 파일이 통째로 빠짐
  → 실제 사고: D3 코드 리뷰 스코프 산출 시 신규 3파일(서비스·라우터·테스트)이 diff에 누락됨을 --stat 합계로 발견
  → 신규 파일이 있으면 `git add -N <파일>`(intent-to-add, 내용 스테이징 아님) 후 diff. 또는 `git status --short`로 `??` 항목을 먼저 대조

- 401 디버깅은 **토큰 수명(발급 후 경과 시간)부터** 확인할 것 - 원거리 가설(시크릿 불일치 등)은 그 다음
  → access 토큰 수명 15분: 미리 발급해 둔 토큰으로 나중에 테스트하면 그 사이 만료된다 (스케줄러 틱 대기 등으로 시간이 잘 감)
  → 실제 사고: E1 수동 e2e에서 만료 토큰 401을 "서버가 다른 JWT_SECRET으로 떠 있다"로 오진, 임시 서버까지 띄운 뒤에야 갓 발급 토큰으로 원인 확정
  → 토큰은 쓰기 직전에 발급하고, 401이면 iat/exp 경과부터 계산

- `pkill -f <패턴>`을 컴파운드 명령 안에서 쓰면 **자기 셸도 패턴에 매칭**돼 사살될 수 있다 - 뒤 단계가 통째로 증발
  → 컴파운드 명령 전체 문자열이 프로세스 커맨드라인에 남아 `-f` 매칭에 걸린다 (실제 사고: D3 수동 테스트 정리에서 `pkill -f uvicorn && 후속작업`이 자기 셸을 죽여 후속작업 미실행)
  → 브래킷 트릭으로 자기 제외: `pkill -f "[u]vicorn"` (패턴 문자열 자체는 `[u]vicorn`이라 자기 커맨드라인과 불일치, 실행 중인 uvicorn은 매칭)
  → 또는 pkill을 단독 명령으로 분리하고 후속 단계는 별도 호출로

- 세션 시작 시 브랜치·PR 상태를 메모리/ledger 기록만으로 단정하지 말 것 (세션 밖에서 진행됐을 수 있음)
  → 실제 사고: 메모리에 "미푸시·PR 대기"로 남아 있었지만 실제로는 사용자가 세션 밖에서 push·PR 머지까지 완료 → 이미 머지된 잔재 브랜치 위에서 새 세션 시작
  → `git status -sb` + `gh pr list --head <브랜치> --state all`로 원격 상태를 확정. 머지된 잔재면 main 복귀 + 로컬 삭제부터. "PR 푸시 후 main 복귀" 규칙은 세션 밖 머지를 커버 못 하니 세션 시작 점검으로 보완

## Pillow / 이미지 처리

- P(팔레트) 모드 이미지의 resize는 **LANCZOS를 지정해도 조용히 NEAREST로 강제**된다
  → 픽셀값이 색이 아니라 팔레트 인덱스라 보간 산술이 무의미하기 때문(Pillow resize 소스에 명시)
  → 모드 정규화(convert RGB/RGBA)를 **리사이즈 앞에** 둘 것. 뒤에 두면 팔레트 원고가 계단 현상으로 뭉개짐
  → 실제 사고: M1.5 D2 초안이 정규화를 리사이즈 뒤에 둠(리뷰 발견, 체커보드 실측으로 확인)

- 16비트 그레이스케일(mode I/I;16*)에 `convert("RGB")` 직행하면 **0~65535가 스케일링 없이 255로 클리핑**돼 백지가 된다
  → `point(lambda v: v * (255 / 65535))`로 선형 스케일 후 `convert("L")` (스캔 원고 PNG/TIFF 경로)
  → 실제 사고: M1.5 D2 초안 - 중간 회색(32768)이 순백(255)으로 저장돼 검증 통과(리뷰 실측)

- `img.draft()`(JPEG DCT 축소 디코드, 장당 ~2.8배 가속)는 **EXIF 회전(5~8)과 2배 여유**를 같이 처리해야 한다
  → 회전 이미지는 transpose 후 축이 바뀌므로 '유효 가로'를 회전 후 기준으로 계산(안 하면 결과 폭이 목표 미달)
  → 목표의 2배를 요청해야 마지막 LANCZOS가 항상 실제로 일어남(딱 맞게 요청하면 draft의 거친 축소가 최종 품질이 됨 - thumbnail의 reducing_gap=2와 같은 관행)

- 애니메이션 이미지(GIF/APNG/animated WebP)는 일반 변환 경로에서 **에러 없이 첫 프레임만 남는다**
  → 조용한 콘텐츠 손실 - `getattr(img, "is_animated", False)`로 명시 거부(또는 의도적 처리)할 것

## R2 / boto3

- R2_ENDPOINT에 버킷 경로가 붙으면(`https://acct.r2...com/dweb`) **에러 없이 성공하면서 모든 키가 어긋난다**
  → S3 호환 path-style: boto3가 endpoint 경로 뒤에 `/<버킷>/<키>`를 또 붙임 → R2가 첫 세그먼트를 버킷으로 해석, 나머지 전부가 키(`dweb/works/...`)로 정상 저장됨 - 서버 입장에선 유효한 요청이라 에러 불가
  → 대시보드 '버킷 Settings > S3 API' 주소는 끝의 `/버킷명`을 빼고 넣을 것. 코드는 `urlparse(endpoint).path` 검사로 첫 사용 시 거부(M1.5 D1)

- boto3 클라이언트 첫 생성은 콜드 ~60ms(botocore 서비스 정의 JSON 파싱) - **async 경로에서 루프 위 직접 호출 금지**
  → lazy 싱글턴이라도 획득 호출 자체를 to_thread 안으로(M1.5 D1 `_put_object_sync` 패턴)

## SQLAlchemy / AsyncSession

- `session.rollback()`은 `expire_on_commit=False`여도 **세션의 모든 객체를 만료**시킨다 (그 설정은 이름대로 commit 전용)
  → 만료 객체의 속성 접근·관계 대입은 AsyncSession에서 동기 lazy load를 트리거해 `MissingGreenlet` 500
  → 부분 실패 복구(get-or-create UNIQUE 충돌 등)는 전체 rollback 말고 `async with session.begin_nested()`(SAVEPOINT)로 격리할 것 - **되돌리는 범위 = 만료시키는 범위**
  → 실제 사고: C1 태그 경합 폴백의 rollback이 로드된 work를 만료시켜 `work.tags` 대입에서 크래시(리뷰 발견, 테스트 미커버 경로)

- 서버 계산 컬럼(`onupdate=func.now()`)은 UPDATE 후 만료로 남는다 - `eager_defaults` 기본 `"auto"`는 **INSERT만** RETURNING(PK를 어차피 받아야 해서)
  → update 경로가 있는 모델은 `__mapper_args__ = {"eager_defaults": True}`로 UPDATE도 RETURNING. 콜사이트별 `session.refresh(obj, attribute_names=[...])` 열거는 다음 함수에서 하나 빠뜨리면 재발하는 땜질
  → 실제 사고: C1 PUT 응답 직렬화가 만료된 updated_at을 읽다 MissingGreenlet (처음엔 refresh 땜질 → 리뷰에서 매퍼 정책으로 일반화)

- 다대다 **연결만** 바뀌면 부모 행 UPDATE 자체가 안 나가 onupdate가 발화하지 않는다
  → 부모 updated_at을 갱신하려면 `obj.updated_at = func.now()` 명시 대입으로 행을 일부러 dirty로 만들 것 (대입의 목적은 값이 아니라 UPDATE 유발 - func.now()는 SQL 표현식이라 항상 변경으로 기록)

- Pydantic 부분 업데이트 스키마(`X | None = None`)는 **명시적 JSON null**이 검증을 통과하고 `exclude_unset` dump에도 살아남는다
  → NOT NULL 컬럼이면 setattr → commit에서 미처리 500. `model_fields_set`(요청에 실제 등장한 필드 집합)으로 명시적 null을 422 거부할 것 (실제 사고: C1 WorkUpdate, 리뷰 발견)

## Alembic 마이그레이션

- 이미 DB에 적용(upgrade)된 마이그레이션 파일을 직접 편집하지 말 것
  → 파일을 고쳐도 DB는 옛 버전이라 `downgrade`/`check`가 어긋나 깨짐 (파일의 drop_index가 없는 인덱스를 지우려다 실패 등)
  → 아직 미커밋·로컬 단계면: `alembic downgrade base` → 파일 수정 → `alembic upgrade head`로 깨끗하게 재적용
  → 이미 커밋·푸시됐으면: 기존 파일 두고 **새 마이그레이션**으로 변경분만 추가 (forward-only)

- psql로 직접 `DROP/CREATE TABLE` 하지 말 것 (guard가 차단함)
  → 스키마 변경은 항상 alembic 경유. DB 리셋이 필요하면 `alembic downgrade base`

- 마이그레이션 작업 후엔 반드시 `alembic check`로 모델↔DB 동기화 확인
  → "No new upgrade operations detected"가 나와야 정상. 떠 있는 diff가 있으면 모델/마이그레이션 불일치

- VARCHAR 컬럼에 enum을 담을 땐 **StrEnum + 명시적 `sa_column=Column(String(n))`** 로 정의할 것
  → 필드 타입만 Python `Enum`으로 두고 sa_column을 안 주면 SQLModel/SA가 **네이티브 PG ENUM 타입**을 생성한다 → 프로젝트 결정("VARCHAR + 앱 enum, 네이티브 PG enum 아님") 위반 + 새 값마다 DB 마이그레이션 강제
  → `class X(StrEnum)`(ruff UP042: `(str, Enum)`→`StrEnum` 권장) + `sa_column=Column(String(20), server_default=text("'ongoing'"))`. StrEnum은 str 서브클래스라 멤버 값이 컬럼에 그대로 저장됨
  → M1.5 A1 `works.status`에 적용, B1 `users.role`도 동일 패턴

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

- autouse 픽스처의 **teardown은 테스트의 monkeypatch 원복보다 먼저 돌 수 있다** (finalizer LIFO - autouse가 먼저 setup되면 나중에 teardown)
  → teardown에서 monkeypatch로 바뀐 객체를 원형이라 가정하면 AttributeError (실제 사고: M1.5 D1 - lambda로 교체된 lru_cache 함수에 cache_clear() 호출)
  → 애초에 teardown 정리가 필요한지부터 의심할 것 - setup 쪽 정리만으로 격리가 충분하면 teardown은 죽은 코드(리뷰에서 setup-only로 단순화)

- 엔드포인트+DB 통합 테스트는 `TestClient` 대신 httpx `ASGITransport`를 쓸 것
  → `TestClient`(동기, 자체 루프)는 session-scope async `db_session`(asyncpg)과 루프가 어긋나 `got Future ... different loop`
  → 해결: `AsyncClient(transport=ASGITransport(app=app), base_url=...)` + `app.dependency_overrides[get_session]`로 같은 루프에서 앱 실행, 비동기 `await client.post(...)`
  → 쿠키를 **수동으로 jar에 set**할 때(요청별 `cookies=`는 deprecated)는 base_url 호스트를 점 있는 이름(`http://test.example`) + `cookies.set(..., domain="test.example")`. 점 없는 호스트(`test`)는 cookiejar가 `.local`을 붙여 도메인 매칭이 깨져 쿠키 미전송
