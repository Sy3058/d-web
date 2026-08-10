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

- **정수 필드 검증은 하한만 걸지 말고 DB 컬럼 타입의 상한도 걸 것** (2026-07-20 C1)
  → `Field(ge=0)`만 두면 `2147483647` 초과 값이 Pydantic을 통과해 DB까지 가고, 4바이트 `Integer` 컬럼에서 asyncpg가 `DataError: value out of int32 range`를 던진다. 핸들러가 없으면 **422가 아니라 500**(+ Sentry 이벤트)
  → "상한값은 의미상 제한할 필요가 없다"는 판단(예: 진행도 페이지 번호)과 **저장 타입의 물리적 한계는 별개**다. 의미 상한이 없어도 `le=2_147_483_647`은 걸어야 클라이언트가 깨끗한 422를 받는다
  → 실제 사고: C1 진행도 `page_no`. 계획 리뷰에서 "과대값 피해는 본인 진행도뿐이라 안전"으로 넘어갔다가 코드 리뷰에서 500으로 발견(임시 테스트로 실측 확정)

- **브라우저의 "No Access-Control-Allow-Origin" 에러는 CORS 설정 문제가 아닐 수 있다 - 처리 안 된 500이 똑같이 보인다** (#85 수동 검증, 2026-07-28)
  → 처리되지 않은 예외의 500 응답(Starlette ServerErrorMiddleware)에는 CORSMiddleware가 관여하지 못해 CORS 헤더가 안 붙는다. 브라우저는 헤더 부재만 보고 "blocked by CORS policy"로 표시 → 콘솔만 보면 CORS 설정 오류·서버 다운으로 오진한다. 실제 사고: dev DB에 마이그레이션 미적용 → admin 목록 진입 시 UndefinedColumnError 500 → 콘솔엔 CORS 에러만. 진짜 원인은 uvicorn 로그 traceback에 그대로 있었다
  → 재현·검증은 브라우저와 **같은 조건**으로: 쿠키 없는 curl은 인증 단계에서 401(정상 처리 경로, CORS 헤더 있음)로 끝나 문제 지점(인증 통과 뒤 DB 쿼리)에 도달하지 못한다. 같은 URL이라도 로그인 여부로 완전히 다른 경로를 밟는다 - 인증 뒤 구간 디버깅은 쿠키를 실어 보내거나, 그 전에 서버 로그부터 볼 것
  → 패턴 인식: "CORS 에러인데 특정 화면·특정 계정에서만 난다"면 CORS가 아니라 그 요청만 밟는 서버 오류를 의심할 것(CORS 설정 문제면 오리진 전체가 일관되게 막힌다)

<!-- 예시:
- SQLModel 관계 lazy loading N+1 → selectinload 명시
- 포트원 webhook 금액 검증 누락 → 서버에서 금액 재검증
-->

## JWT / PyJWT

- 위조(forged) 토큰 테스트용 "틀린 시크릿"을 짧은 문자열로 쓰면 `InsecureKeyLengthWarning` 노이즈 발생
  → PyJWT는 HS256 서명 키가 32바이트 미만이면 경고를 낸다. `"wrong-secret"`(12자) 같은 값은 테스트 의도(서명 불일치 → 401)엔 문제없지만 경고가 낀다
  → 32바이트 이상의 임의 문자열(예: `"wrong-secret-0123456789abcdef0123456789abcdef"`)로 늘려서 해결. 실제 사고: M1.5 B2 `test_setup_forged_cookie_401`. B3의 `/admin/login/totp` pending 쿠키 위조 테스트에서도 동일 패턴 재발 가능성 높음

- **같은 머신이라도 시계는 단조가 아니다 - jwt.decode에는 leeway가 필수** (#85 조사, 2026-07-27)
  → 실제 사고: 전체 pytest가 ~17회 중 3회, 매번 **다른** 테스트 1개가 401로 죽고 다음 테스트는 전부 정상. 원인은 WSL2/NTP 시계 역점프(~1.9초 실측) - 토큰 발급 직후 시계가 뒤로 가면 `iat`가 "미래"가 돼 PyJWT(2.6+)가 ImmatureSignatureError로 거부한다. 발급·검증이 같은 프로세스여도 일어난다. 수정: jwt.decode 전부에 `leeway=JWT_LEEWAY_SECONDS(10)` + 회귀 테스트 2건(iat 5초 미래 토큰 - test_token 단위 + test_admin_login stage2 통합)
  → 원인 확정 방법: 실패 순간을 못 잡으면 가설만 쌓인다(3회 헛발질 후 계측 전환). 401 분기별 임시 진단 print + PG `log_statement='mod'`를 심고, 재현 루프가 첫 실패에서 pytest 출력·PG 로그·접속 스냅샷을 자동 수집하게 했다. 결정타는 **PG 순차 로그의 타임스탬프 역행**(연속 두 줄이 56.4초 → 54.6초)과 "iat를 미래로 박은 토큰"의 결정적 재현
  → 패턴 인식: "매번 다른 테스트 1개만 실패 + 직후 전부 정상 + 실행 시간이 긴 파일에 실패 편중"은 임의 시점 일회성 **환경 이벤트**(시계·디스크·네트워크)의 서명이다. 코드 경로를 아무리 읽어도 안 나온다

## Astro / React

- **`@tiptap/core`의 `generateHTML`은 브라우저 전용 - Node(vitest 기본 `environment: node`) 환경에서 `ReferenceError: window is not defined`** (M2 F1, 2026-07-25)
  → ProseMirror `DOMSerializer.serializeFragment`가 실제 DOM을 요구한다(공식 문서의 "browser-only" 서술과 실측 일치). 서버(Node)에서도 렌더해야 하면 `@tiptap/html`(브라우저+Node 겸용)을 쓴다
  → 렌더 스키마 회귀 테스트에서 `generateHTML`을 직접 호출하려면 그 테스트 파일에만 `// @vitest-environment jsdom` 지정 + devDep `jsdom` 추가(전역 환경은 그대로 `node`로 두고 파일 단위로만 예외)
  → 이 제약은 뷰어 아일랜드를 `client:load`가 아니라 `client:only="react"`로 마운트해야 하는 이유와 같은 뿌리다 - 서버가 이 컴포넌트를 미리 렌더 시도하면 그 자리에서 죽는다

<!-- 예시:
- React 아일랜드에 client: 지시자 누락 → hydration 안 됨
- Signed URL 만료 시간 너무 짧게 설정 → 뷰어 로딩 중 만료
-->

## Vite / Astro

- `VITE_*` 환경변수는 **서버 시작 시점에 번들로 주입**된다
  -> `.env` 생성 전에 `pnpm dev`를 먼저 띄우면 env가 undefined로 뜬다
  -> **정정(2026-07-18 실측)**: "고쳐도 반영 안 되니 수동 재시작"이라고 적어뒀었는데, Vite 7.3은
     `.env` 변경을 감지해 `[vite] .env changed, restarting server...` 로그와 함께 **스스로 재시작**한다
  -> 다만 자동 재시작이 없는 경로(이미 만든 빌드 산출물, 다른 셸이 물고 있는 서버)에서는 여전히 수동 재시작이 필요

- **`import.meta.env.X`의 이름 오타는 에러 없이 폴백으로 조용히 떨어진다** (M1.5 F1, 2026-07-14)
  -> admin 코드가 `VITE_API_BASE_URL`을 읽는데 `.env`가 정의한 이름은 `VITE_API_URL`이었다
  -> dev에선 하드코딩 폴백(`?? 'http://localhost:8000'`)이 우연히 실제 주소와 같아 몇 달간 안 드러남
  -> 프로덕션 빌드에서 관리자 SPA가 **사용자 브라우저의 localhost**를 호출하는 버그가 됐을 것
  -> 예방: env를 읽는 줄과 `.env.example`을 **같이 열어 이름을 대조**. 폴백은 오타를 감춘다

- **소스 트리에 tsc 산출물 `.js`가 생기면 그 뒤 `.tsx` 수정이 전부 무시된다** (M2 admin 토글, 2026-07-18)
  -> 원인은 `pnpm exec tsc -b --noEmit false` 같은 **CLI로 noEmit 덮어쓰기**. tsconfig의 noEmit이 꺼져 `src/` 전체에 컴파일된 `.js` 수십 개가 쏟아진다(정상 빌드 산출물은 `dist/`로만 간다)
  -> Vite의 확장자 해석 순서는 **`.js`가 `.tsx`보다 앞**이라 `import './WorkForm'`이 옛 `.js`를 잡는다 -> 화면·테스트가 편집 이전 코드를 계속 실행
  -> **증상이 캐시 문제로 위장한다**: 소스는 분명 맞고 `tsc -b`도 클린인데 렌더 결과만 옛것. `node_modules/.vite` 삭제, `vitest --clearCache`, `--no-cache`, `touch`(mtime 갱신) 전부 무효다(캐시가 아니라 실재 파일이 이기는 것이라 당연)
  -> **30초 진단**: `find src -name "*.js"` - 하나라도 나오면 이 함정이다. 보조 확인은 `Component.toString()`에 방금 추가한 문자열이 있는지, 그리고 `import('./X.tsx?t='+Date.now())`로 확장자를 명시하면 새 코드가 나오는지(나오면 확정)
  -> **정리는 `git status --short --untracked-files=all | grep '\.js$'`로 전수 확인 후 삭제**한다. untracked만 잡히니 `eslint.config.js` 같은 추적 원본은 자동으로 걸러지고, `src/`만 훑다가 놓치기 쉬운 **`vite.config.js`(설정 파일도 `.js`가 `.ts`보다 우선 로드된다)** 까지 잡힌다(실제로 이걸 놓쳐 두 번 밟았다)
  -> 예방: 타입 검사는 package.json 스크립트(`pnpm --filter admin build`) 그대로 쓰고 **tsc 옵션을 CLI로 덮어쓰지 말 것**

## TanStack Query (v5)

- **`setQueryData(key, undefined)`는 캐시를 지우지 않는다 - no-op이다** (M1.5 F1, 2026-07-14)
  -> query-core `queryClient.js`: `const data = functionalUpdate(...); if (data === void 0) return void 0;`
  -> undefined를 "업데이트 안 함" 신호로 보고 bail-out한다. `null`은 타입 에러라 undefined로 바꾸기 쉬운데 그게 함정
  -> 로그아웃에서 이걸 쓰면 유저가 캐시에 남아 **뒤로가기 시 라우트 가드가 통과**한다(실측 재현)
  -> 캐시를 비우려면 `removeQueries({ queryKey })` 또는 `clear()`
  -> clear는 **로그아웃 버튼만이 아니라 인증 영역을 떠나는 모든 경로**에 걸어야 한다 - 라우트 가드의 401 자동 리다이렉트·권한 부족 bounce도 포함(#91). 한 곳만 clear하면 나머지 경로에 잔상·계정 간 캐시 누수가 남는다

- **`ensureQueryData`는 staleTime을 무시하고 캐시를 무조건 반환한다** (M1.5 F1)
  -> `if (cachedData !== undefined) return Promise.resolve(cachedData)` - `revalidateIfStale`을 주지 않으면 배경 재검증도 안 한다
  -> 라우트 가드(`beforeLoad`)에서 쓰면 **만료·강등된 세션이 캐시만으로 영구 통과**한다
  -> 세션을 실제로 재검증해야 하는 가드에는 `fetchQuery`(+`staleTime: 0`)를 쓴다. `isStaleByTime`을 확인해 실제로 재요청한다

- **`useEffect`에서 `mutate()`를 호출하면 StrictMode에서 성공 알림이 유실된다** (M1.5 F1, TanStack/query#8512)
  -> mount→cleanup→mount 과정에서 mutation observer가 분리돼, 요청은 200으로 성공하는데 컴포넌트는 `pending`에 영구히 멈춘다
  -> 중복 방지용 `useRef` 가드를 달면 "두 번째 mutate가 우연히 상태를 풀어주는" 경로까지 막아 **멈춤을 고정**시킨다(F1에서 실제로 겪음)
  -> "마운트 시 표시할 데이터를 가져온다"는 POST여도 **`useQuery`가 맞다**(재구독·dedupe 정상 처리, effect·ref 가드 불필요)
  -> 진단 순서: 백엔드 curl 격리 → 콘솔 raw fetch → mutationFn 안에 로그(start/resolved) → resolved는 찍히는데 렌더 status가 안 바뀌면 이 함정

- **`invalidateQueries`/`removeQueries`는 기본이 prefix 매칭이다 - 목록 키를 다른 키의 앞부분으로 만들지 말 것** (M1.5 F2, 2026-07-15)
  -> 목록 `['admin','works']` + 상세 `['admin','works',id]` 구조에서 목록 하나를 무효화하면 **상세·하위 쿼리가 전부 재요청**된다(작품 N개면 요청 N+1건)
  -> `exact: true`로 막을 수는 있지만 구조가 남아 다음 사람이 같은 덫을 밟는다 → 키를 세그먼트로 분리(`['admin','works','list']` / `['admin','works','detail',id]`)
  -> 회귀 테스트는 "무관한 쿼리의 `isInvalidated`가 false"로 고정. 옛 구조로 되돌려 **실제로 실패하는지 확인**할 것

## TanStack Router

- **admin build는 `tsc -b`가 먼저 돌아, 라우트 파일 추가/이동 직후엔 낡은 routeTree.gen.ts 기준 타입 에러가 쏟아진다** (M1.5 F3, 2026-07-15)
  → 라우트 트리는 vite 플러그인이 dev/build 중에 재생성하는데, build 스크립트에선 tsc가 그 앞에서 죽어 재생성 지점까지 못 간다
  → 새 라우트 작업 후엔 `pnpm --filter admin exec vite build`(esbuild라 타입 검사 없음)로 트리부터 재생성 → 그다음 `pnpm --filter admin build`

## TipTap 에디터

- **커스텀 노드의 React 노드뷰를 확장 정의와 한 파일에 두면 `react-refresh/only-export-components` lint 에러** (M1.5 F3, 2026-07-17)
  → `.tsx`가 컴포넌트(노드뷰)와 비컴포넌트(`Node.create` 확장·옵션 타입)를 함께 export하면 Vite react-refresh 규칙(에러 게이트)이 막는다
  → 노드뷰 컴포넌트는 별도 `.tsx`(예: `ImageNodeView.tsx`)로 빼고 확장 정의는 `.ts`에 둔다. 순환 import 방지로 노드뷰는 확장이 아니라 공용 타입/store만 참조
- **StarterKit v3는 v2와 달리 Link·Underline까지 포함한다** (M1.5 F3, 2026-07-17)
  → 서버 화이트리스트 밖 노드(heading·목록·codeBlock·code 마크)는 툴바 버튼만 빼면 안 되고 `configure({ heading:false, ... })`로 **확장 자체를 꺼야** 마크다운 단축키(`# `·`- `·` ``` `)·붙여넣기로도 안 만들어진다(안 그러면 저장 시 서버 422)
  → `getSchema(extensions)`로 뷰(ReactNodeViewRenderer) 없이 스키마만 뽑아 허용/비허용 노드·마크·attrs를 서버와 1:1 회귀 테스트
- **`editor.view.posAtCoords`는 레이아웃(`document.elementFromPoint`)에 의존해 jsdom 테스트에서 던진다** (M1.5 F4, 2026-07-17)
  → 이미지 드롭 지점 계산에 posAtCoords를 쓰면 jsdom엔 `elementFromPoint`가 없어 `TypeError`로 테스트가 깨진다(실제 브라우저에서도 좌표 해석은 상황에 따라 실패 가능)
  → try/catch로 감싸 실패 시 현재 커서 위치로 폴백(프로덕션 견고성 겸용) - 좌표를 못 구해도 삽입 자체는 되게 둔다
- **`insertContent`는 현재 selection을 "대체"한다 - atom 노드를 넣으면 삽입 직후 selection이 그 노드의 NodeSelection이 된다** (M2 admin fix, 2026-07-26)
  → 이미지(atom) 여러 장을 루프에서 `insertContent`로 넣으면 삽입 직후 selection이 방금 넣은 노드를 잡아 다음 장이 직전 장을 덮어써 **마지막 1장만** 남는다. 편집 모드에서 선택 영역(기존 이미지·텍스트)이 잡혀 있으면 첫 장이 그 선택을 지운다
  → 삽입 지점을 명시하는 `insertContentAt(pos, node)`로 넣고(대체가 아니라 그 지점 삽입), 위치는 매 삽입 직전 `editor.state.selection.to`를 라이브로 읽는다. await(업로드) 중 절대 위치를 캐시하면 동시 편집으로 stale·범위초과(throw)가 나므로 업로드 동안 `editor.setEditable(false)`로 본문 편집을 잠근다(유료 경계 반대편 삽입 방지 겸용)

## openapi-typescript codegen

- **기본값(default)이 있는 요청 필드를 openapi-typescript가 required(`?` 없음)로 뽑는다** (M1.5 F3, 2026-07-17)
  → Pydantic `title: str = Field(default="무제")`는 서버에선 생략 가능인데 생성된 TS는 `title: string`(필수)이 돼 `mutateAsync({})`가 TS 에러
  → 호출부에서 값을 명시해 넘기거나(예: 현재 입력값) 생략이 정말 필요하면 스키마/codegen을 조정. "서버 기본값 = 클라 선택"이 자동으로 성립하지 않는다
- **응답 스키마 필드를 `dict`(무형 JSON)로 두면 codegen이 `{[key: string]: unknown}`으로 뽑아 클라 속성 접근이 전부 tsc 에러** (M2 #86, 2026-07-23)
  → `AdminEpisodeRead.draft: dict | None`로 뒀더니 admin에서 `draft.title` 접근이 "Property 'title' does not exist" 5건(실측)
  → 클라이언트가 내부 구조를 읽는 필드는 Pydantic 정타입 모델(예: `EpisodeDraft`)로 선언 - 쓰기 경로가 같은 스키마로 검증하면 저장 형태도 보장돼 타입이 거짓말하지 않는다

## 폼 / CSS

- **Chrome은 native `<select>` 화살표에 `padding-right`를 적용하지 않는다** (M1.5 F2)
  -> `pr-8`을 줘도 화살표가 테두리에 딱 붙어 있다(브라우저마다 다르게 렌더)
  -> `appearance-none` + 직접 그린 SVG 화살표(`absolute right-3`, `pointer-events-none`)로 위치를 잡는다. 모양도 브라우저 간 통일되는 부수효과

- **`z.preprocess`를 RHF+zodResolver 폼 스키마에 쓰면 `useForm<T>` 제네릭과 타입이 어긋난다** (M1.5 F3)
  → preprocess는 해당 필드의 입력 타입을 unknown으로 만들어 스키마의 input≠output이 되고, SubmitHandler가 TS2345로 거부된다(실측)
  → 값 변환(빈 문자열 → null 등)은 스키마가 아니라 `register`의 `setValueAs`로 옮기고, 스키마는 `nullable()`만 남긴다

- **RHF `watch('name')` 호출은 React Compiler `react-hooks/incompatible-library` 경고를 낸다** (M1.5 F4, 2026-07-17)
  → `watch()`는 렌더 중 호출돼 메모이즈 불가한 값을 반환해, 컴파일러가 "stale UI 위험"으로 그 컴포넌트 메모이제이션을 건너뛴다(eslint 경고 - 에러 아님이나 clean 목표면 제거)
  → 폼 값을 렌더에 반영하려면 `watch` 대신 훅 `useWatch({ control, name })`로 구독한다(경고 없음)

- **`register(name, { valueAsNumber: true })`는 빈 입력을 `NaN`으로 넘긴다** (M1.5 F2)
  -> zod `z.number()`는 NaN을 타입 에러로 거부하는데, 메시지를 안 주면 **영문 기본 문구**("expected number, received NaN")가 한국어 UI에 그대로 뜬다
  -> `z.number({ error: '숫자를 입력해 주세요.' })`로 타입 에러 문구를 지정할 것(zod 4는 `message`/`invalid_type_error`가 `error`로 통합)

- **boolean 필드를 `<select>`로 받을 때 `register`+`setValueAs`만 쓰면 수정 폼이 기존 값을 반영하지 못한다** (M2 admin 공개 토글, 2026-07-18)
  -> `setValueAs`는 **입력 방향(문자열 -> boolean)만** 처리한다. 반대로 `defaultValues`의 boolean을 select DOM에 써넣는 출력 방향은 못 메꿔서, 서버가 `true`를 줘도 화면은 늘 첫 옵션(또는 "비공개")으로 뜬다
  -> 조용한 버그다: 등록은 멀쩡히 동작하고 **수정 화면에서만** 값이 틀리며, 그대로 저장하면 사용자가 의도치 않게 공개를 꺼버린다
  -> `Controller`로 양방향을 명시한다: `value={field.value ? 'true' : 'false'}` + `onChange={e => field.onChange(e.target.value === 'true')}`
  -> 회귀 테스트는 "`defaultValues`에 `true`를 주고 아무 조작 없이 제출 -> `true`가 그대로 나오는가"로 고정(이 케이스가 실제로 실패를 잡았다)

- **CSS 주석 안에서 `*` 바로 뒤 `/`가 오면 주석이 조기 종료된다** (M2 E, globals.css, 2026-07-22)
  -> `/* leading-*/tracking-* ... */`처럼 설명에 `-*/`를 쓰면 앞의 `*/`가 주석 종료 토큰이라 주석이 거기서 끊긴다. 남은 텍스트(`tracking-* ... */`)가 CSS 규칙으로 파싱돼 Tailwind가 `Missing opening (` 에러를 내는데, **스택트레이스가 tailwindcss 내부라** 실제 소스 줄을 안 가리켜 원인 추적이 오래 걸린다
  -> 이분 탐색으로 격리(주석 전량 제거 후 하나씩 복원 -> 토큰이 아니라 주석이 원인). 주석에 유틸리티 클래스 나열 시 슬래시 대신 쉼표(`leading, tracking, font`)를 쓴다

- **Tailwind v4는 `.flex`가 `[hidden]` 속성을 안 덮는다(v3와 다름)** (M2 E, 2026-07-22)
  -> "`<div hidden class="flex">`는 flex가 이겨 안 숨겨진다"는 v3의 유명한 함정인데, v4 preflight는 `[hidden]:where(...) { display: none !important }`로 `!important`를 붙여 utilities 레이어의 일반 `display:flex`를 이긴다(`node_modules/tailwindcss/preflight.css`)
  -> v3 지식으로 "hidden 대신 .hidden 클래스 써야 한다"고 단정하지 말 것. v4에선 `hidden` 속성이 정상 동작한다(코드 리뷰가 이걸 v3 기준으로 오탐한 사례)

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

- **`git branch -d`의 "머지됨" 안전판은 upstream 기준이라 main 머지를 보장하지 않는다** (M1.5, 2026-07-15)
  → upstream이 설정된 브랜치는 HEAD가 아니라 **자기 upstream(origin/<branch>)에 머지됐는지만** 검사한다 - push만 돼 있으면 main에 안 들어간 작업도 통과·삭제된다
  → squash-merge 워크플로에선 원 커밋이 어차피 main에 없으므로 이 안전판에 기대지 말 것
  → 정리 전 PR 머지 상태(`gh pr view`)를 확인하고 지울 것. 이 확인을 거쳤다면 `-D`가 오히려 정직하다

- 이미 push된 커밋을 rewrite(`reset --soft`/rebase/amend)하면 로컬과 origin이 갈라진다(divergence)
  → 히스토리 재작성 전 push 여부 확인: `git status -sb`(ahead/behind) 또는 `git rev-parse origin/<branch>`
  → 이미 pushed면 (1) 새 커밋으로 fix-forward가 기본, (2) 굳이 정리하면 `--force-with-lease` 필요함을 먼저 고지
  → 이 repo는 squash-merge라 중간 커밋은 어차피 합쳐지므로 정리 목적 rewrite는 대개 불필요

- **커밋 훅이 메시지를 거부해도 스테이징은 그대로 남는다 - 잔재가 다음 커밋에 쓸려 들어감** (2026-07-23)
  → 실제 사고: 영역 분리 2연속 커밋 중 1번째([INFRA] ci: - type 불허)가 훅에 거부됐는데, 이어진 2번째 docs 커밋이 스테이징에 남은 ci.yml까지 3파일을 한 커밋으로 흡수 - 커밋 메시지와 내용 불일치
  → 훅 거부는 커밋만 실패시키고 `git add`는 유효하게 남는다. 한 Bash 블록에서 add·commit을 순차 나열하면 앞 커밋 실패 시 뒤 커밋이 전부 쓸어간다
  → 대응: 연속 커밋은 `&&`로 연결해 앞 실패 시 중단시키거나, 훅 거부 후 `git status`로 스테이징 확인 뒤 재시도. 이 repo는 브랜치명·커밋 형식 훅이 있어 거부가 드물지 않다

- 코딩 완료 후 커밋 전 반드시 Opus 검증 단계 거칠 것
  → 순서: 계획(Opus) → 코딩(Sonnet) → 검증(Opus) → 커밋
  → Opus 없이 바로 `git commit`으로 넘어가지 말 것

- **한 곳을 고쳤으면 같은 성질의 형제 위치를 반드시 훑을 것** (M2 B, 2026-07-21 - 한 세션에 2회 반복)
  → 1회차: `routers/episodes.py`의 404에 `no-store`를 붙이고 **같은 PR에서 새로 만든** `routers/works.py`의 404를 빠뜨림. "기존 공유 코드라 범위 밖"이라 판단했으나 그 엔드포인트도 이번에 추가한 신규 코드였다
  → 2회차: 위를 고치며 `backend/CLAUDE.md`의 규칙만 갱신하고 **루트 `CLAUDE.md`의 같은 규칙**을 또 빠뜨림(하필 매 세션 자동 로드되는 "절대 하면 안 되는 것들" 섹션)
  → 둘 다 코드 리뷰가 최상위 발견으로 잡아냈다. 즉 **리뷰가 없었으면 그대로 머지됐을 종류**다
  → 체크: 규칙·상수·헬퍼·에러 응답을 고쳤으면 `grep`으로 **같은 문자열·같은 패턴의 다른 출현부**를 먼저 세고 시작한다. 특히 CLAUDE.md는 루트/영역별로 **중복 서술**되므로 한쪽만 고치면 두 문서가 서로 모순된다
  → "이건 범위 밖"이라는 판단은 그 코드가 **이번 diff에서 새로 생긴 것인지** 확인한 뒤에만 유효하다

- **리뷰 지적을 고칠 때 그 수정이 새로 들이는 비용을 확인할 것** (M2 B, 2026-07-21)
  → `KeyError` 500을 없애려 노드를 조용히 폐기 → **관측성 상실**(이미지가 사라져도 서버가 모름). 로그를 함께 넣어야 했다
  → `defer()`로 불필요 컬럼 로딩을 막음 → **MissingGreenlet 잠재 위험**(지연 컬럼을 나중에 누가 읽으면 async 밖 lazy load). 필요한 컬럼만 `select`하는 쪽이 지연 속성 자체를 안 만든다
  → 둘 다 다음 리뷰 라운드에서 잡혔다. 수정은 "지적이 사라졌는가"가 아니라 **"무엇을 대가로 지불했는가"**까지 보고 끝낸다

- **open 이슈를 "미구현"의 증거로 삼지 말 것** (M2, 2026-07-22)
  → PR 본문에 `Closes #N` 키워드가 없으면 구현이 머지돼도 이슈가 열린 채 남는다. 이슈 목록만 보고 착수하면 이미 있는 기능을 재구현하게 됨
  → 실제 니어미스: #82(공개 태그 API)·#83(실효가)이 PR #81로 구현·머지됐는데 open으로 남아 "지금 당장 처리"로 추천 - 마일스톤 문서의 ✅ 마킹과 코드 grep 대조로 착수 직전에 발견
  → 착수 전 확인: 관련 마일스톤 문서 완료 마킹 + 코드 심볼 grep. 예방: pr_body.md에 해결하는 이슈의 `Closes #N`을 반드시 포함

- **"유지된다"를 검증하는 테스트는 시작값과 기대값이 다르게 짜야 한다 - 같으면 판별력이 0** (#84, 2026-07-26)
  → 실제 사고: "완결/휴재로 바꿔도 공개 상태를 건드리지 않는다"를 `is_published: true`로 시작해 `true`를 단언했다. 값을 **보존하는 구현**도, 무조건 **공개로 강제하는 구현**도 똑같이 통과한다 - 막으려던 회귀를 그대로 통과시켰고 CI는 계속 그린이었다
  → 보존 계약은 양방향으로 고정한다: 공개→공개 **와** 비공개→비공개. 한쪽만 두면 "무조건 그 값"으로 바뀌는 회귀를 못 잡는다
  → 확인법은 **변이 실험**이다. 고친 코드에 회귀를 일부러 심어 테스트가 빨강이 되는지 보고, 원복 후 그린을 재확인한다. "테스트가 통과한다"와 "계약이 고정됐다"는 다른 말이다
  → 같은 사고의 짝: 어떤 필드를 단언하지 않으면 그 필드의 회귀는 안 잡힌다. 폼 제출 테스트가 `is_published`만 보고 `status`를 안 봐서, `register` 래핑이 RHF change 핸들러를 삼키는 회귀에 무방비였다

- **폼의 기본값과 "상태 → 다른 필드" 자동 연동 규칙이 서로 모순되면, 사용자가 아무것도 안 건드려도 결과가 갈린다** (#84, 2026-07-26)
  → 실제 사고: 폼 기본값이 `status=ongoing` + `is_published=false`(새 작품은 비공개)인데 "ongoing이면 공개" 연동을 넣었다. 등록 화면에서 상태를 골랐다 **되돌리기만 해도**(값은 원래 기본값과 동일) 공개가 켜져 빈 작품이 독자에게 노출됐다. 최종 선택이 같은 두 사용자가 드롭다운을 흔들었는지 여부로 반대 결과를 얻는다
  → 연동을 넣기 전에 "이 규칙을 폼 초기 상태에 적용하면 초기값과 같은가?"를 확인한다. 다르면 그 모순이 곧 버그다
  → 되돌릴 수 없는 방향(노출·공개·전송)은 자동화하지 않는다. 자동 연동은 fail-closed 방향(숨김)에만 걸고, 여는 쪽은 사용자가 직접 누르게 한다
  → 리뷰에서도 놓치기 쉽다: 수정 폼 경로만 보고 "머지 가능"으로 판정했다가 등록 폼 경로에서 걸렸다. **같은 컴포넌트를 쓰는 create/edit 두 진입점을 각각 확인할 것**

## Claude 작업 효율 (셸/검증 패턴)

- env 값 존재 확인에 `sed 's/=.*/=<값 있음>/'` 식 마스킹을 쓰지 말 것 - **빈 값(`KEY=`)도 `=<값 있음>`으로 치환**돼 "채워짐"으로 오판
  → 실제 사고: M1.5 D 착수 시 R2 자격증명이 비어 있는데 "전부 채워져 있다"고 보고(블로커 해소 오판)
  → 값 자체를 노출하지 않고 확인하려면 길이/형식 검사로: `awk -F= '{print $1, length($2)}'` 또는 파이썬으로 `len(v)` 출력

- **게이트 검증은 CI와 똑같은 명령·인자로 돌릴 것** (#85, 2026-07-28)
  → 실제 사고: `ruff check .`로 돌려 에러 85건을 보고할 뻔했다. CI 게이트는 `ruff check src/`고, migrations/ 등은 **의도적 제외**(alembic 자동생성이라 정규화 대상 아님 - DECISIONS CI 절). 반대로 CI보다 좁게 돌리면 빨강을 초록으로 오판한다
  → 게이트 명령의 단일 진실은 `.github/workflows/`다. 기억으로 재구성하지 말고 워크플로 파일에서 복사해 돌릴 것

- **같은 브랜치를 워크트리 두 개에서 동시에 체크아웃 못한다 - `git checkout main`이 다른 워크트리 점유로 막힌다** (2026-07-28, `common/docs/g-redefine-episode-id` PR #106 준비 중)
  → 실제 상황: `d-web-m2`가 이미 `main`을 체크아웃 중이라 `d-web`에서 `git checkout main`이 `fatal: 'main' is already used by worktree`로 실패
  → 해법: 로컬 `main`을 거치지 말고 `git checkout -b <새브랜치> origin/main`으로 **원격 참조를 베이스로 직접 새 브랜치**를 판다 - local main 포인터를 건드릴 필요가 없다
  → 다른 워크트리의 미커밋 변경을 가져올 땐 `git -C <경로> diff -- <파일...> > patch.diff` 후 이 저장소에서 `git apply patch.diff`(같은 저장소라 파일 상대경로 그대로 적용됨). 적용 전 `git apply --check`로 드라이런
  → 정리 시 주의: **squash-merge된 브랜치는 `git merge-base --is-ancestor`가 "머지 안 됨"으로 오판**한다(원본 커밋이 squash 커밋의 조상이 아니라서). 진짜 근거는 `gh pr list --state all`의 PR state - MERGED 확인 후 `git branch -D`(force, `-d`는 이 경우 거부됨)

- 셸 출력이 지연되면 빈 결과를 "사실"로 오판하지 말 것 (이번 세션 최악의 실수 원인)
  → 한 명령의 결과가 비어 있거나 늦게 와도, 그걸 근거로 "파일 없음 / 깨끗함 / 성공"이라 단정 금지
  → 특히 파괴적 작업(rm, 삭제, downgrade) 전엔 상태를 한 번 더 확정 후 진행
  → 실제 사고: 이미 존재하던 `DB_SCHEMA.md`를 빈 read 결과 보고 "없음"으로 오판해 삭제 (git에서 복구함)

- 같은 확인 명령을 5~6번 반복하지 말 것
  → 출력이 늦으면 `flush`용 echo를 난사하는 대신, 결과를 파일로 redirect(`> /tmp/x.txt 2>&1`)하고 Read로 한 번에 읽기
  → 여러 검증을 한 번에: sentinel(`echo START ... echo END`)로 감싸 한 블록으로 확인

- **Bash 도구의 cwd는 호출 간 유지된다 - 상대경로가 빗나가면 삭제·부재를 의심하기 전에 cwd부터 의심할 것** (M2 A 후속 2026-07-19, M2 D 사고 추가 2026-07-21)
  → 호출마다 새 셸이 아니라 **세션 내내 유지되는 하나의 지속 셸**이다. `cd backend && ...`를 한 번 돌리면 되돌아 나오는 `cd`를 넣지 않는 한 **완전히 별개의 다음 호출도** `backend/`에서 시작한다
  → 빗나가는 방식이 두 가지고 **둘 다 조용하다**: (a) `No such file or directory` - "파일이 없다"와 구별이 안 됨, (b) 이중 경로(`backend/backend/...`)로 **에러 없이 빈 출력** - "차이 없음"으로 오판
  → 실제 사고 1(M2 A): `docs/milestones/M2_foundation.md`가 없다고 3번 연속 오판. `cd <root> && grep` 조합조차 다음 호출엔 안 남아 또 실패
  → 실제 사고 2(M2 D): `git diff <A> <B> -- backend/services/catalog_service.py`를 `backend/` 안에서 실행해 빈 결과 → **"겹치는 파일 없음"으로 오판**(브랜치 base 동기화 사고로 이어질 뻔). 별개로 `cd admin`에서 안 나온 채 `git add compose.yml`이 `pathspec did not match`로 실패
  → 해법: **항상 절대경로**, 또는 서브디렉터리 명령은 `(cd sub && cmd)` 서브셸로 격리해 cwd를 안 남긴다. 상대경로 명령 전엔 `pwd` 확인(시스템 프롬프트 자체가 "cd 대신 절대경로"를 지침으로 명시)
  → 특히 "없음"·"차이 없음"을 근거로 무언가를 만들거나 지우기 직전엔 절대경로로 재확인(위 "빈 결과를 사실로 오판" 항목과 같은 부류)

- **ruff는 CI와 같은 범위로 돌릴 것 - `.` 전체는 CI가 의도적으로 뺀 파일까지 잡는다** (M2 A 후속, 2026-07-19)
  → CI 게이트는 `ruff check src/` + `ruff format --check src/ tests/`다(`.github/workflows`, "migrations/는 alembic 자동생성 + DB 적용 + forward-only라 의도적으로 제외" 주석 명시)
  → `ruff format --check .`로 돌리면 migrations 12개가 "reformat 필요"로 떠서, 내 변경분이 깬 것처럼 보인다. 실제로 main에서도 동일하게 뜨는 기존 상태
  → 내 변경이 게이트를 깼는지 판단할 땐 **CI와 동일한 경로 인자**로 돌릴 것. 범위가 넓어서 나온 노이즈를 고치려 들면 무관한 파일을 커밋에 끌어들인다

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

- `pkill -f "패턴"`은 **자기 자신(그 pkill을 실행 중인 셸)까지 매칭**해 명령을 죽인다
  → 실제 사고(M1.5 G teardown): 백그라운드 서버를 `pkill -f -- "--port 8099"`로 종료하려 했는데 teardown 셸의 argv에도 그 문자열이 있어 셸이 죽고(exit 144) 뒤따르던 DB drop·파일 정리가 안 돎
  → 백그라운드 프로세스는 PID(`kill <pid>`)나 harness 백그라운드 태스크로 종료. 굳이 pkill이면 자기 argv에 안 나올 패턴 사용

- e2e로 로컬 서버를 띄우기 전에 **그 포트에 이미 다른 서버가 떠 있는지** 확인할 것
  → 실제 사고(M1.5 G): 8000에 사용자 dev 서버가 이미 떠 있어 내 uvicorn이 `[Errno 98] address already in use`로 종료. 남의 서버에 e2e를 쏘면 그 서버의 DB(dev)를 오염시킨다
  → 다른 포트(8099 등)로 띄우고 e2e BASE를 그 포트로. `ss -ltnp | grep :PORT`로 점유 확인

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

- 같은 턴에 병렬로 던진 Bash 호출들은 **직전 호출이 남긴 cwd를 그대로 이어받는다** - "매번 새 셸"로 가정하면 상대경로 `cd`가 깨진다
  → 실제 사고: `cd admin && pnpm build` 실행 후 cwd가 `admin/`으로 남은 채, 같은 턴에 병렬로 `cd admin && pnpm lint` / `cd admin && pnpm test`를 또 보내 `cd: admin: No such file or directory`
  → 병렬 호출에서 상대경로 `cd`를 반복하지 말 것. 절대경로로 고정하거나(`cd /repo/admin && ...`), `pnpm --filter admin <script>`처럼 cwd 무관 실행형을 우선 사용

- stale 문구를 `grep -v`로 걸러 찾을 때 **방금 새로 쓴 문장이 제외 패턴에 걸려 진짜 stale을 가린다**
  → 실제 사고(M2 결정 6 개정): `lazy` 잔재를 훑으며 `grep -v "결정 6\|lazy 아님\|..."`로 정상 문구를 제외했는데, **아직 안 고친 F1 DoD 줄에도 같은 줄에 "결정 6"을 덧붙여 놨던 탓**에 그 줄이 통째로 결과에서 빠짐 - diff를 눈으로 읽다 뒤늦게 발견(못 봤으면 계획서에 모순이 남음)
  → 개정 직후 잔재 탐색은 **제외 패턴 없이 전량 출력**해 눈으로 판별하거나 파일을 좁혀서 볼 것. 필터는 출력이 감당 안 될 때만, 그리고 "내가 방금 쓴 문구"는 필터에 넣지 말 것

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

- 미커밋 변경을 들고 브랜치를 옮길 때, 충돌 여부는 `origin/<브랜치>`가 아니라 **옮겨갈 로컬 ref**와 비교해야 한다
  → `git diff <현재> origin/main -- <파일>`이 비어 있어도, **로컬 `main`이 아직 pull 안 된 상태면** checkout이 `local changes would be overwritten`으로 거부된다. 원격이 최신인 것과 이동 대상이 최신인 것은 별개 - checkout이 보는 건 로컬 ref다
  → 실제 사고(2026-08-04): 머지 후 main 복귀에서 `origin/main`과 비교해 "차이 0이라 안전"이라고 사용자에게 보고했는데 checkout이 그대로 거부됨. 로컬 main이 2커밋 뒤처져 있었다
  → 순서를 바꾸면 애초에 안 생긴다: **pull이 먼저, 이동이 나중**. 이동해야만 pull이 되는 상황이면 짧은 stash로 옮긴 뒤 곧바로 pop할 것 - 이때의 stash는 **이동 수단**이지 보관함이 아니다(장기 보관용 stash는 `git status`에 안 잡혀 잊힌다 - 같은 날 M0 시절 stash 1건이 실제로 방치된 채 발견됨)

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

- ⚠️ **`eager_defaults=True`는 `column_property`를 커버하지 않는다** (위 항목을 "이제 다 해결됐다"로 읽으면 당한다)
  → column_property는 컬럼이 아니라 **SQL 표현식**이라 (a) INSERT/UPDATE RETURNING에 실리지 않고 (b) flush 후 값이 달라졌을 수 있다고 보고 **만료**된다 → 응답 직렬화가 읽는 순간 또 MissingGreenlet
  → 커밋을 수반하는 **모든** 경로에서 `session.refresh(obj, attribute_names=["그_속성"])`로 다시 로드할 것. 여기선 콜사이트 열거가 땜질이 아니라 유일한 수단이다(매퍼 정책으로 못 덮는다)
  → 실제 사고: F2 `Work.episode_count`(에피소드 개수 상관 서브쿼리) 도입 시 생성 경로만 refresh했다가 **수정·표지 업로드 응답이 전부 500**(테스트 8개 실패로 검출)

- **`sqlalchemy.select`로 단일 엔티티를 select하면 `session.exec().first()`가 Work 대신 Row를 반환한다** (M2 A, 2026-07-17)
  → sqlmodel의 `session.exec()`는 `sqlmodel.select()`가 만드는 `SelectOfScalar`를 인식해야 단일 엔티티를 자동 스칼라 언랩한다. `sqlalchemy.select()`로 같은 모양(`select(Work).where(...).options(selectinload(...))`)을 만들면 언랩이 안 돼 `.first()`가 `Row(Work,)`를 주고, `row.id` 접근이 `AttributeError: id`(Row의 컬럼-키 fallback)로 죽는다
  → 다중 컬럼 select(`select(Work, count_subq)`)는 두 select 모두 어차피 Row 튜플이라 이 차이가 안 드러나 파묻히기 쉽다 - 실제로 목록 API는 우연히 통과하고 상세 API에서만 터짐
  → 이 프로젝트 관례(work_service.py 등)대로 **엔티티를 직접 select해 session.exec()에 넘길 때는 반드시 `from sqlmodel import select`**. 서브쿼리·column_property 구성용 select(자체는 exec에 안 넘김)는 `sqlalchemy.select`도 무방
  → 부수 함정: `sqlmodel.select`의 단일 컬럼 select(`select(func.count(...))`)는 exec 결과가 이미 `ScalarResult`라 `.scalar_one()`이 아니라 `.one()`을 써야 한다(`.scalar_one()`은 AttributeError). `sqlalchemy.select`였다면 반대로 `.one()`이 `Row(n,)`를 주므로 `.scalar_one()`이 필요했다 - 어느 select를 썼는지에 따라 짝이 바뀐다

- 다대다 **연결만** 바뀌면 부모 행 UPDATE 자체가 안 나가 onupdate가 발화하지 않는다
  → 부모 updated_at을 갱신하려면 `obj.updated_at = func.now()` 명시 대입으로 행을 일부러 dirty로 만들 것 (대입의 목적은 값이 아니라 UPDATE 유발 - func.now()는 SQL 표현식이라 항상 변경으로 기록)

- Pydantic 부분 업데이트 스키마(`X | None = None`)는 **명시적 JSON null**이 검증을 통과하고 `exclude_unset` dump에도 살아남는다
  → NOT NULL 컬럼이면 setattr → commit에서 미처리 500. `model_fields_set`(요청에 실제 등장한 필드 집합)으로 명시적 null을 422 거부할 것 (실제 사고: C1 WorkUpdate, 리뷰 발견)

- **bulk `update()` 후 같은 세션에서 재조회하면 옛 값이 나온다** (`expire_on_commit=False` 조합, 2026-08-03)
  → `synchronize_session=False`는 인메모리 인스턴스를 **의도적으로** 안 맞추고, 세션이 `expire_on_commit=False`(lib/db.py)라 commit도 만료시키지 않는다. 이 상태로 다시 SELECT하면 identity map이 **로드된 옛 속성을 그대로 둔 채** 기존 인스턴스를 돌려준다
  → 무서운 건 증상 모양이다: 행 **순서**는 SQL `ORDER BY`가 정하니 맞고 **값만** 옛것이라, 순서로 렌더링하는 UI에선 화면상 완전히 정상으로 보인다
  → 커밋 후 명시 갱신할 것 - 단건은 `session.refresh(obj)`, N건은 `session.expire(obj)` 루프(만료만 표시하면 뒤따르는 SELECT 한 번이 채우므로 refresh N번보다 쿼리가 적다)
  → 실제 사고: 회차 재배열 `PUT .../episodes` 응답이 순서는 `[c,a,b]`로 맞는데 `sort_order`가 `[3,1,2]`(옛값). 어드민이 배열 순서로 그려 눈으로는 안 잡혔고, **테스트가 없었으면 그대로 머지**됐다

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

- 여러 워크트리가 **같은 dev DB를 공유**하면 한 브랜치의 마이그레이션이 dev DB를 스탬프해 다른 브랜치의 `alembic check`가 깨진다
  → 실제 사고(M1.5 G 검증): dev DB(`dweb`)가 M2 워크트리(`d-web-m2`)의 마이그레이션 `726b16a759b3`으로 앞서 있어 main 워크트리에서 `alembic check`가 `Can't locate revision '726b16a759b3'`로 실패. **main 마이그레이션 자체는 정상**(그 리비전은 main에 없음, head `2a9ae60edceb` 위 정상 체인)
  → 검증은 **신규/스크래치 DB**에서: `docker exec ... psql -c "CREATE DATABASE dweb_scratch"` → `DATABASE_URL=<scratch> uv run alembic upgrade head && alembic check`(→ "No new upgrade operations detected") → `DROP DATABASE dweb_scratch WITH (FORCE)`. 다른 워크스트림이 쓰는 dev DB는 re-stamp 금지

- **스크래치 DB 검증 통과 ≠ dev DB 적용됨 - 그 브랜치 코드로 dev 서버를 돌릴 거면 dev DB에도 `upgrade head`** (#56, 2026-07-22)
  → 마이그레이션을 스크래치 DB(`dweb_scratch`)에서 `upgrade`+`check`로 검증하고 드롭하면, 모델·pytest(PID 전용 임시 DB)는 새 컬럼을 알지만 **실제 dev DB(`dweb`)는 옛 스키마 그대로**다. 그 상태로 dev 서버를 띄우면 SELECT가 `column ... does not exist`로 500 (실제 사고: `totp_last_step` 추가 후 `/auth/login`이 `UndefinedColumnError`)
  → 바로 위 "워크트리 공유 dev DB re-stamp 금지"와 충돌 아님: 그건 **검증(`alembic check`)** 은 스크래치에서 하라는 것이고, 이건 그 브랜치로 **dev 서버를 실행**할 거면 dev DB에도 `uv run alembic upgrade head`를 적용해야 한다는 것. 두 DB(pytest 임시·스크래치 vs dev)가 별개라 pytest·check가 다 그린이어도 dev 서버는 깨질 수 있다. nullable 컬럼 추가는 dev DB에 적용해도 안전(락·데이터 손실 없음)
  → asyncpg는 **prepare 단계에서 터진 statement는 캐시하지 않으므로** 컬럼 추가 후 서버 재시작 없이 다음 요청부터 통과한다. 단 이미 성공 캐시된 statement가 스키마 변경으로 깨지는 경우만 `InvalidCachedStatementError` → 그때만 dev 서버 재시작

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

- **테스트 DB를 세션 두 개가 공유하면 서로를 파괴한다** (2026-07-20 C1, 해결됨)
  → 증상: 전체 스위트가 **실행할 때마다 다른 테스트**가 실패/에러. 개별 파일 단독 실행은 전부 통과
  → 원인: 워크트리 두 개(`d-web`, `d-web-m2`)에서 **동시에 pytest**를 돌리면 고정 DB `dweb_test` 하나를 공유한다. `db_session` teardown이 매 테스트마다 전 테이블을 DELETE하므로 **상대가 방금 만든 행이 상대 테스트 도중 사라진다**
  → 파생 증상: `DELETE FROM users`가 FK 위반(내가 works를 지운 직후 상대가 works를 INSERT) → teardown 중단 → 데이터 잔류 → 다음 실행에서 회차에 이미 이미지가 있어 길이-가드 UPDATE가 409 → `KeyError: 'image_keys'`. **원래 원인과 무관한 파일에서 터진다**
  → 해결(도입됨): conftest `test_engine`이 **PID 전용 DB**(`dweb_test_<pid>`)를 CREATE/DROP한다. `CREATE/DROP DATABASE`는 트랜잭션 안에서 불가라 `isolation_level="AUTOCOMMIT"` 연결로 실행. 검증 = pytest 2개 동시 실행 → 양쪽 337 passed
  → ⚠️ 정리 시 **다른 PID의 DB는 건드리지 말 것** - 동시 실행 중인 세션 것일 수 있다. 비정상 종료 잔재만 수동 정리
  → 진단 교훈: 실패가 매번 다르면 그 실패 지점을 디버깅하지 말고 **상태 오염을 먼저 의심**한다. 그리고 "지금 관측되지 않음"을 "없음"으로 단정하지 말 것 - 이번 건은 동시 접속을 몇 번 샘플링해 0으로 나오자 동시성 가설을 기각했는데, 상대 세션이 그 순간 쉬고 있었을 뿐이었다(사용자 제보로 확정)

- 정렬 테스트는 **생성 순서 = 기대 순서면 판별력이 0**이다 (2026-07-30)
  → `ORDER BY`를 통째로 지워도 통과한다 - 삽입 순서가 우연히 답을 맞히기 때문
  → 정렬 키와 tie-breaker를 **서로 반대 방향**으로 깔아야 "진짜 그 컬럼을 보는지"가 잡힌다. 정렬 키가 둘 이상이면(예: `sort_order` → `created_at`) 셋 다 다른 방향으로
  → 실제 사고: 같은 계약을 검증하는 자매 테스트 두 개 중 `test_catalog.py`는 역전시켜 뒀는데 `test_admin_episodes.py`만 순방향으로 새로 써서 한쪽만 판별력 0이 됐다(코드 리뷰에서 발각). **같은 계약을 여러 파일에서 검증할 땐 강한 쪽에 맞출 것**

## vitest (admin / frontend 테스트)

- `mockResolvedValueOnce` 큐는 `vi.clearAllMocks()`로 **안 비워진다** - 엉뚱한 테스트가 대신 깨진다 (2026-07-30)
  → 증상: A 테스트를 깨뜨렸더니 무관한 B 테스트가 같이 빨강. B를 `-t`로 단독 실행하면 통과
  → 원인: A가 큐에 쌓아둔 once 응답을 **소비하지 못하고** 끝나면(가드에 막혀 요청 자체를 안 보냄) 그 응답이 B의 첫 호출로 밀린다. `clearAllMocks`는 호출 **기록**만 지우고 큐는 남긴다(큐까지 비우려면 `mockReset`)
  → 실제 사고: 회차 제목 필수 가드를 넣자 이미지 테스트 2개가 업로드를 건너뛰었고, 무관한 "여러 장 삽입" 테스트가 "3장 기대인데 1장"으로 깨졌다
  → 판별법: **단독 실행이 통과하면 앞 테스트의 잔재를 의심**한다. 실패한 그 테스트를 고치려 들지 말 것
