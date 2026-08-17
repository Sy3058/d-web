# 기술 스택 & 기획 결정 기록

이 문서는 프로젝트 초기 기획 단계에서 내린 결정들과 그 이유를 기록한다.
스택 선택 이유, 기능 범위, 보류된 것들을 추적하기 위한 문서.

---

## 서비스 개요

1인 웹툰 작가의 개인 판매 플랫폼.
- 작품 열람 + 유료 결제 + 팬 소통 기능을 갖춘 미니 웹툰 플랫폼
- 상업 플랫폼(네이버, 카카오)이 아닌 작가 직영 사이트
- 모바일 웹 위주, 누적 사용자 5천명 규모 목표
- 1인 운영, TypeScript + Python 기반

### 단일 작가 개인 홈 - 의도적 범위 결정

**이 플랫폼은 특정 1인 작가의 개인 홈이다. 다작가 플랫폼으로의 확장은 목표가 아니다.**

- `users.role`(owner/moderator 등 관리자 권한), R2 버킷, 작가 프로필 등 모든 설계가 1인 기준
- 여러 작가를 지원하려면 `작가` 엔티티 분리, 권한 모델 재설계, 콘텐츠 격리 등 아키텍처 전면 재설계가 필요 - 단순 확장이 아님
- 따라서 다작가 지원을 위한 추상화나 유연성을 미리 넣지 않는다

### 에피소드 가격 정책

**가격은 작가가 업로드 시 회차별로 설정한다. 기본값은 무료(0원).**

- `episodes.price` 필드로 회차별 개별 설정 가능
- `works.episode_base_price`로 작품 단위 기본값 설정 가능 (회차에서 오버라이드)
- 무료 공개분 → 유료 전환은 작가 재량
- 코드에 특정 가격이 하드코딩되어선 안 됨 - 금액은 항상 DB에서 읽어야 함

---

## 프론트엔드 스택 결정

### 결정: Astro (독자용) + Vite React SPA (관리자)

**이유**
- 서비스 성격이 콘텐츠 중심 (작품 목록, 에피소드, 작가 소개)
- SEO와 모바일 초기 로딩이 핵심 - Astro의 정적 HTML 서빙이 최적
- 인터랙티브 기능(결제, 댓글, 후원)은 React 아일랜드로 처리 가능한 수준
- 관리자 페이지는 SEO 불필요 + 동적 화면 중심 → SPA가 적합
- React 경험 활용 가능 (Astro 안에서 React 아일랜드로 그대로 사용)

**탈락한 후보들**
- Next.js: 이 프로젝트엔 과함. 복잡한 앱 기능이 독자용 사이트에 없음
- Vite+React SPA 단독: SEO 약해서 검색 유입 불가
- SvelteKit/React Router v7: 한국 자료/결제 가이드 부족

### Vite 버전: 7 (workspace 통일) - Astro 7 출시 시 8로 업그레이드

**현재 상태 (2026-05-31)**
- Astro 6는 Vite 7 사용 (`vite@^7.3.2`)
- admin도 Vite 7로 맞춰 workspace 전체를 vite@7으로 통일 (`@vitejs/plugin-react@^5`)
- `@tailwindcss/vite@4.3.0`이 Vite 8 네이티브 바인딩에서 `tsconfigPaths` 누락 버그 있어 Vite 8 혼용 불가
- frontend/package.json에 `vite@^7`을 devDep으로 명시해 pnpm peer 해석 고정

**Astro 7 stable 출시 시 일괄 업그레이드 항목**
- `frontend`: `astro@7`, devDep `vite` 고정 제거
- `admin`: `vite@^8`, `@vitejs/plugin-react@^6`
- `build.rollupOptions` -> `build.rolldownOptions` 이름 변경 여부 확인

### Node 버전: 24 LTS

**이유**
- Node 20은 2026-04-30 EOL (이미 만료)
- Node 22 (LTS, 2027-04까지) / Node 24 (Active LTS, 더 긴 지원 + npm 11 + 최신 V8) 중 새 프로젝트는 24 권장
- 26은 2026-10에 LTS 승격 예정이므로 현 시점 선택 X
- frontend lint 도구의 하한에 맞춰 `frontend.engines.node`는 `>=24.16.0`으로 둔다. CI의 Node 24 채널과 `node:24-alpine`은 이 하한 이상의 최신 24.x를 사용한다.

### 관리자 라우터: TanStack Router

**이유**
- 타입 안전 라우팅 + search params 스키마 검증이 빌트인 → 관리자 페이지의 폼·필터·페이지네이션 처리에 강함
- loader 패턴으로 데이터 페칭과 라우팅 결합 명확
- React Router v7도 후보였으나 search params 타입 처리는 TanStack이 우위

### FE/Admin 공유 코드: pnpm workspace + `packages/shared`

**이유**
- `lib/api.ts` (fetch 래퍼, `credentials: 'include'`), `lib/validation.ts` (Zod 스키마), BE 응답 타입이 양쪽에서 동일하게 필요
- 복붙은 한쪽 수정 누락 사고가 잦음 (특히 Zod 스키마/API 응답 타입)
- 사설 npm 패키지는 1인 프로젝트에 publish 사이클 오버스펙
- pnpm: 디스크·속도 우위, monorepo 표준

**구조**
```
/
├── package.json          # workspace 루트
├── pnpm-workspace.yaml
├── packages/shared/      # api 래퍼, zod 스키마, 공통 타입
├── frontend/             # Astro
└── admin/                # Vite React
```

향후 FastAPI OpenAPI → TS 타입 자동 생성으로 발전 가능.

### 린트/포맷: ESLint로 통일 (biome 미채택, 2026-06-20)

**결정: frontend·admin 모두 ESLint를 쓴다. biome는 채택하지 않는다.**

- admin은 Vite `react-ts` 스캐폴드가 ESLint(flat config)를 기본 포함 - 이미 동작 중(`admin/eslint.config.js`).
- frontend(Astro)는 스캐폴드에 린트가 없어 `eslint-plugin-astro` 기반 ESLint 10 flat config를 별도 도입했다(2026-08-18). `.astro`는 CLI glob에 확장자를 명시하고 플러그인 권고대로 minor preset drift를 막기 위해 `eslint-plugin-astro`를 tilde 고정한다.
- **biome 탈락 이유**: (a) `.astro` 파일 린트/포맷 지원이 제한적, (b) admin이 이미 ESLint라 통일 시 추가 마이그레이션 불필요. Rust 속도 이점보다 일관성·생태계를 우선.
- 명령은 pnpm 워크스페이스로 통일: `pnpm --filter <pkg> lint`.
- frontend lint는 JS/TS/Astro recommended와 React Hooks recommended를 적용한다. type-aware lint, Prettier, JSX a11y, import/style 규칙은 별도 범위다. `astro check`는 프로젝트 단위 타입 검사를 위해 그대로 유지한다.

---

## 백엔드 스택 결정

### 결정: FastAPI + SQLModel + PostgreSQL

**이유**
- FastAPI: Python 기반, 비동기 처리, 자동 API 문서, AI 기능 확장 용이
- SQLModel: FastAPI 제작자가 만든 ORM. 코드 중복 없이 DB 모델을 API 응답 타입으로 재사용
- PostgreSQL: 안정적, FastAPI 궁합 좋음, VPS 안에서 직접 운영

### Python 버전: 3.12

**이유**
- 3.13도 안정화됐지만 일부 C 확장(asyncpg, pydantic-core 등) 휠 배포·호환성이 3.12가 더 안전
- FastAPI/SQLModel/Alembic 전부 3.12에서 가장 검증됨
- 3.13의 free-threaded/JIT 기능은 이 프로젝트에서 필요 없음

### 패키지 매니저: uv

**이유**
- 2026 기준 새 Python 프로젝트의 사실상 디폴트 (poetry 대비 10~100× 빠름)
- 가상환경 + 의존성 + Python 버전 + lockfile을 한 도구로 관리
- Docker 이미지 빌드 시간·이미지 크기 모두 작음
- 이 프로젝트 의존성(FastAPI, SQLModel, asyncpg, pydantic) 모두 휠 잘 배포되어 uv의 약점(C 확장)과 무관

**탈락한 후보**
- poetry: publish 워크플로우만 약간 우위, 그 외 모든 면에서 uv 우위
- pip + venv 수동: lockfile/재현성 약함

---

## 인프라 결정

### VPS: Hetzner 싱가포르

**이유**
- 월 $8~10으로 압도적으로 저렴
- AWS 서울 대비 응답속도 20~40ms 느리지만 Cloudflare CDN으로 이미지/정적 파일은 보완
- API 호출만 싱가포르 거치는 구조라 체감 차이 크지 않음
- 나중에 사용자 늘면 서울로 이전 가능 (Docker라 이전 쉬움)

**탈락한 후보들**
- AWS Lightsail 서울: 서울 리전 장점 있으나 월 $20~25로 2.5배 비쌈
- DigitalOcean 싱가포르: Hetzner와 위치 동일한데 2배 비쌈
- NCP: 가격 대비 이점 없음

### 이미지 스토리지: Cloudflare R2

**이유**
- S3보다 저렴한 egress 비용
- Cloudflare CDN과 세트라 이미지 서빙 속도 자동 최적화
- Signed URL 지원 → 유료 콘텐츠 보호 가능

### 표지 서빙: 표지 전용 공개 버킷 분리 (2026-07-15 확정, 구현은 M2)

**결론**: 표지(`cover.webp`)는 **별도의 공개 버킷 + 커스텀 도메인**으로 서빙한다. 원고(에피소드 이미지)가 든 `dweb` 버킷에는 **커스텀 도메인을 붙이지 않는다**.

**이유**
- ⚠️ **R2의 공개 설정은 객체 단위가 아니라 버킷 단위다.** 지금은 표지와 원고가 같은 `dweb` 버킷에 키 prefix로만 구분돼 있어(`works/{id}/cover.webp` vs `works/{id}/episodes/...`), `dweb`에 커스텀 도메인을 붙이면 **미공개·유료 원고까지 서명 없이 받아진다**. 키가 UUID라 추측은 어렵지만 그건 보안이 아니라 요행이고, 공개 URL은 만료가 없어 한 번 새면 영구히 풀린다 → 루트 CLAUDE.md "미결제 유저에게 이미지 URL 내려주기 금지" 위반.
- 표지는 로그인 없이도 보여줄 공개 자산이라 서명이 불필요하다. 공개 버킷이면 URL이 고정이라 브라우저·CDN 캐시가 완전히 동작하고(서명 URL은 매 요청 문자열이 달라져 캐시 미스 + `<img src>` 교체로 재로드), egress도 무료다.
- 원고는 계속 비공개 버킷 + presigned URL. 두 방식은 독립적 - presigned를 쓰는 데 버킷 공개는 전혀 필요 없다. (관리자 미리보기용 발급은 F3에서 앞당김 - 아래 "원고 presigned GET" 참조. 독자용 결제 검증 잠금은 M3)

**미채택**: `dweb`에 커스텀 도메인 연결(위 위험), 표지에 presigned URL(공개 자산에 만료 URL은 캐시를 깨고, 응답마다 URL이 바뀌어 이미지가 재로드된다 - 관리자 화면 한정 임시방편으로는 가능하나 결국 공개 버킷으로 옮겨야 함)

**M1.5 F2 시점**: 표지 서빙 경로가 없어 관리자 목록/폼은 placeholder를 렌더링한다(업로드·저장은 정상 동작). 실제 표시는 M2에서 공개 버킷과 함께.

### 원고 presigned GET: 관리자 미리보기용은 F3에서 앞당김 (2026-07-15)

**결론**: 원고(에피소드 페이지)의 presigned GET 발급을 M3(결제·잠금)에서 통째로 기다리지 않고, **관리자 업로드 화면용 발급 경로만 M1.5 F3에서 먼저 구현**한다. `GET /admin/works/{id}/episodes/{id}/image-urls`(`require_owner`) + `r2_service.presign_get_urls()`(만료 600초).

**이유**
- F3의 draft 재진입 화면에서 업로드된 페이지를 보여줄 방법이 없으면 재배열·썸네일 선택이 키 번호 목록으로 전락한다(웹툰 워크플로에서 반쪽).
- "미결제 유저에게 이미지 URL 금지" 원칙과 충돌하지 않는다 - 발급 엔드포인트가 `require_owner` 뒤에만 있고, 관리자에겐 이미 `AdminEpisodeRead`로 R2 키 자체가 노출된다.
- M3는 이 발급 함수를 재사용해 **독자용 결제 검증 경로**만 얹으면 된다(중복 구현 없음).

**규칙**: presigned URL은 만료되는 일회성 값 - 서버·클라 어디서도 캐시하지 않는다(매 요청 발급, 프론트 쿼리는 staleTime/gcTime 0).

### 뷰어 이미지 로딩: 즉시 전량 요청 + `fetchpriority` (2026-07-19 확정, 구현은 M2 F1)

**결론**: 뷰어 본문 이미지는 **lazy load하지 않고 페이지 진입 시 전부 요청**한다. 앞 2~3장에 `fetchpriority="high"`, 나머지에 `low`. presigned 만료 대응(`onerror` → content 재요청)은 **폴백**으로만 남긴다.

**이유**
- **만료 회피가 구조적으로 된다.** presigned는 이미지가 아니라 **URL**이 만료되고, 검사는 *새 요청*에만 걸린다 - 위험한 건 스크롤로 나중에 받는 하단 이미지다. lazy면 천천히 읽는 독자의 하단 이미지가 403이 나고, 한 번에 발급한 세트라 그 시점 이후 전부가 동시에 죽는다. 즉시 전량 요청하면 모든 GET이 발급 후 수 초 안에 끝나 **만료 구간에 진입하지 않는다**. TTL 600초와 캐시 금지 규칙(위 "원고 presigned GET")을 그대로 둔 채 문제만 사라진다.
- **독자는 진입 지연보다 읽는 중 끊김에 훨씬 민감하다.** lazy는 만료 주기마다 빈 칸 → 재요청 왕복(403 → content 재요청 → 재다운로드)이 반복된다.
- R2는 egress가 무료라 전량 요청의 **우리 쪽 대역폭 비용이 사실상 0**이다. 남는 비용은 독자의 모바일 데이터와 초기 로딩 시간뿐.

**규칙**: `fetchpriority`는 곁다리가 아니라 성립 조건이다. 요청이 동시에 나가도 대역폭은 하나라, 수십 장이 HTTP/2 다중화로 경쟁하면 첫 이미지도 지분만큼만 받아 **첫 화면이 lazy보다 느려진다**(순서 대기가 아닌 대역폭 경쟁이라 눈에 덜 띄지만 지연은 실재). **우선순위 없는 eager는 채택안이 아니다.**

**재검토 조건**: 회차당 총 전송 바이트는 **미실측**이다(장수는 작가 입력에 달렸고, 콘텐츠 모델이 글+이미지 혼합이라 순수 웹툰 50장 형태가 아닐 수 있다). M2 F1 DoD에 실측 기록을 넣는다. 모바일에서 5MB를 크게 넘겨 진입이 무거우면 답은 **lazy 복귀가 아니라 서명 쿠키**(아래)다.

**미채택**
- **lazy load**: 위 만료 문제의 원인 제공자. 이 프로젝트에선 presigned와 상극이다.
- **서명 쿠키(고정 URL + 경로 단위 권한)**: 파일 많고 세션 긴 뷰어의 정석이고 캐시·깜빡임 면에서 최선이지만, **Cloudflare엔 네이티브 기능이 없다**(공식 문서 확인 2026-07-19). 공개 버킷 보호 수단은 ① **Zero Trust Access**(문서상 "teammates만 접근할 버킷용" - IdP 전제라 불특정 독자 불가) ② **WAF Token Authentication**(`is_timed_hmac_valid_v0()` - 토큰이 **쿠키가 아니라 URL 쿼리 파라미터**라 결국 서명 URL이고 캐시 안정성 이득이 안 온다 + **Pro 플랜 이상** 필요) ③ **Worker 직접 구현**(시크릿 공유·배포 파이프라인·요청당 과금이 붙는 인프라 신설) 셋뿐이다. M2는 무료 구간만 서빙해 보안 경계가 URL이 아니라 **서버 절단**이라 불필요 → **M3에서 재검토**(회차 크기 실측 + 구매자 스코프가 생기는 시점).
- **무료 구간 이미지를 공개 버킷에 복사**: "무료니까 공개해도 되지 않나"의 답. **유료 경계는 작가가 언제든 옮길 수 있는 가변 값**이라, 복사본이 나중에 유료 구간이 되면 **만료 없이 영구히 새어 있다**(위 "표지 서빙"의 버킷 단위 공개 함정과 같은 계열 - 공개 버킷 사고는 되돌릴 수 없다).
- **TTL 장기화**: 캐시 금지·짧은 만료 규칙과 긴장(새면 오래 유효).

**사실 기록(공식 문서, 2026-07-19)**: presigned URL은 **커스텀 도메인에서 쓸 수 없다** - *"Presigned URLs work with the S3 API domain and cannot be used with custom domains."* 원고 이미지는 항상 `<account-id>.r2.cloudflarestorage.com`에서 온다(우리 도메인이 아니다). 표시용 `<img>`는 CORS 대상이 아니라 실사용엔 무관하지만, "원고에도 커스텀 도메인을 붙여 통일"은 애초에 성립하지 않는다(붙여도 presigned가 안 먹고, 붙이는 것 자체가 버킷 단위 공개라 금지).

### 에피소드 콘텐츠 모델: 문서형(TipTap JSON) + 회차 내 유료 경계 (2026-07-15, F3 재설계)

**결론**: 회차 본문을 "이미지 배열(image_keys)"에서 **스키마 제한 JSON 문서(`episodes.content`, TipTap/ProseMirror 포맷)**로 재설계한다. 글+이미지 혼합 본문이며, 문서 최상위의 `paywall` 노드(최대 1개)가 유료 경계 - 경계 앞 = 무료 미리보기, 뒤 = 유료(포스타입식 부분공개). `is_free`는 직접 입력을 폐지하고 경계 위치에서 서버가 파생한다. image_keys는 업로드 매니페스트(소유 키 전량)로 의미 축소.

**이유**
- 에피소드 화면은 네이버 블로그·포스타입식 게시글 에디터여야 하고, 유료 시작 지점은 작가가 본문 안에서 드래그로 정한다(2026-07-15 확정: 경계 = 회차 내 콘텐츠 경계, 글도 쓰는 에디터, 미니멀 툴바 - 굵게·기울임·밑줄·취소선·링크·구분선).
- **HTML을 저장하지 않는다** - 노드·마크 화이트리스트(`lib/content_doc`)가 곧 방어선이라 임의 태그·속성이 존재할 수 없고(XSS 원천 차단), 링크 href는 http(s)만.
- TipTap 채택 근거(실측): `@tiptap/react` 주간 다운로드 10,499,722 vs `lexical` 3,884,165 (api.npmjs.org, 2026-07-08~14 집계). MIT. `@tiptap/core`의 `generateHTML`이 React 없이 동작해 M2 Astro 뷰어의 서버 렌더에 그대로 쓸 수 있다. paywall은 custom node(draggable 내장).
- 뷰어(M2)가 미착수라 지금이 문서형으로 바꿀 마지막 싼 시점 - 기존 행 백필은 image_keys를 image 노드로 나열(+유료 회차면 paywall 선행 = "전체 유료" 의미 보존)로 끝난다.

**규칙**: 상한 노드 3,000·텍스트 100,000자·깊이 20(DoS 가드). content의 image 키 ⊆ image_keys(임의 키 주입 차단). 유의미 내용 없는 문서는 `EMPTY_DOC`으로 정규화(스케줄러 SQL 가드의 성립 조건). 공개 요건 = 본문에 유의미 콘텐츠(글/이미지 - 글만 있는 회차도 공개 가능). 미구매 독자 응답은 **서버가 경계 이전 노드만 잘라 반환**(클라 숨김 금지 원칙). ⚠️ 이 절단은 원래 M3 소관으로 적었으나 **M2로 앞당겨 2026-07-21 구현 완료**(부분 무료를 M2에서 보이게 하려면 절단이 M2 소관 - M2_foundation 결정 1). M3는 여기에 구매 검증 + 경계 뒤 포함 반환만 얹는다.

**미채택**: HTML 저장(새니타이저 의존 + XSS 면적), 회차 단위 유료 유지(경계 맨 앞 배치 = 전체 유료라 상위 호환인데 표현력만 잃음), Lexical(다운로드 열세 + 프레임워크 종속 심함), is_free 직접 입력 유지(경계 위치와 이중 진실 - 불일치 버그 온상).

**여파**: 글 작성이 본문 모델에 내장돼 "소설 뷰어" 보류의 전제 일부가 해소되지만, 전용 소설 뷰어(뷰어 설정·이어보기 UX 등)는 여전히 보류 항목으로 유지. `viewer_progress.page_no`는 M2에서 블록 인덱스로 재해석 예정.

**발행본/편집본 분리 (2026-07-23, #86)**: "임시저장 = `is_published=false`"라는 등식을 폐지한다. 공개 회차에서 임시저장이 `content`를 덮으면 미완성 원고가 즉시 라이브 반영되는 사고 경로였다(발행된 회차에선 '임시'가 아니었음). `episodes.draft`(JSONB, nullable)에 **편집본 봉투** `{"title", "subtitle", "content"}`를 저장하고(본문만 담으면 공개 회차의 제목 수정이 여전히 즉시 반영되는 반쪽 분리라 메타 포함), 서버 불변식으로 고정한다: ① draft·content 동시 전송 422 ② **공개 회차의 content는 `is_published` 동반 요청(발행 액션)만 덮을 수 있다**(위반 409 + 조건부 UPDATE `WHERE is_published=false`로 스케줄러 공개 전환 race까지 원자 봉쇄) ③ content 쓰기는 draft를 항상 NULL로 소진(발행 = 승격, 별도 promote 엔드포인트 없음 - 에디터가 항상 최신 문서를 들고 있어 stale draft 승격 혼동이 없다) ④ draft 검증은 발행본과 동일(`validate_content` + image_keys 부분집합, 매니페스트 축소가 draft 참조 키를 지우면 422). draft는 owner 전용 `AdminEpisodeRead`에만 노출 - 독자 DTO 금지(미발행 원고 유출). 신규 회차는 기존대로 `content` 직접 편집(비공개라 그 자체가 draft - "아직 발행 안 함"과 "임시저장"은 문구만 분리). **미채택**: 스냅샷 테이블(버전 이력 - 1인 작가·단일 편집 세션에 과함), stateless promote 엔드포인트.

**⚠️ 저장 스키마 ≠ 독자 응답 스키마 (2026-07-21, M2 B2 구현에서 확정)**: 화이트리스트는 서버·에디터·뷰어 3곳이 동일해야 하지만 **image 노드의 attrs만 의도적 예외**다. 저장은 `attrs={"key": R2키}`, 독자 응답은 `attrs={"src": presigned URL}`로 **교체**해 내보낸다(key를 남긴 채 src를 더하면 원본 키가 응답에 실린다). 저장 스키마는 "무엇을 받아들일까"(입력 검증·XSS 방어선), 응답은 "무엇을 보여줄까"의 계약이라 원래 다른 것이고, R2 키는 내보낼 수 없는데 뷰어는 URL 없이 렌더할 수 없다. **M2 그룹 F 렌더러는 `src` 기준**으로 구현할 것. 노드·마크 화이트리스트 자체는 동일하다.

### 웹서버: Caddy

**이유**
- HTTPS 자동 처리 (Let's Encrypt 연동 자동)
- 설정 파일이 Nginx보다 훨씬 단순
- 1인 개발 초기에 설정 실수 줄이기 위해 선택
- 나중에 Nginx 전환 가능 (Docker 컨테이너만 교체하면 됨)

### 결제: 포트원

**이유**
- 한국 개발자 자료 최다
- SDK 하나로 카드/카카오페이/토스페이 한 번에 연동
- FastAPI 연동 예제 존재

---

## 기능 범위 결정

### 확정 기능

**콘텐츠/뷰어**
- 작품 목록 → 에피소드 목록 → 뷰어 3단계 구조
- 세로 스크롤 웹툰 뷰어
- N화까지 무료, 이후 Signed URL 잠금
- 드래그/복사 차단, 이미지 우클릭 저장 차단
- 랜딩(`/`) 히어로 + 커미션 홍보 (M2 공개 SSR, 옛 "작가 소개 페이지" 재정의 - 아래 결정 참조)

**결제**
- 에피소드 개별 구매 / 전편 구매
- 카드, 카카오페이, 토스페이 (포트원)
- 구매 내역 확인

**계정**
- 회원가입/로그인 + 소셜 (카카오, 구글)
- 구매 목록
- 알림 설정 (새 에피소드 / 새 커뮤니티 게시글 / 댓글 답글)

**소통**
- 하트 + 댓글 + 답글
- 후원 기능
- 커뮤니티 게시판 (근황, Q&A, 투표)

**관리자**
- 에피소드 업로드/관리
- 수익 확인
- 독자 통계
- 업로드 리마인더 알림
- 커미션 접수(신청 폼 + 관리 화면, 정적 홍보는 M2로 분리 - 아래 결정 참조)

### 랜딩 페이지 구성 + 커미션 단계 분리 (2026-07-26 확정, 구현은 M2 그룹 G)

**결론**: 메인 랜딩(`/`, 현재 빈 플레이스홀더)을 **등록 최신순 작품 중앙 캐러셀 + 소형 작가 프로필 스트립 + 커미션 홍보**로 재설계한다. `works`에는 대표작 지정 필드가 없고 공개 목록은 등록 최신순이므로 첫 작품을 최초 중앙에 놓는다. 모바일은 중앙과 양옆 최대 3개, `sm` 이상은 최대 5개를 단계형으로 배치하고 버튼·카드·키보드 방향키·도트 인디케이터로 순환한다. 별도 작품 그리드는 두지 않는다. 프로필 스트립은 독립된 admin 작가 프로필 화면에서 편집하는 소개용 작가명·업로드 이미지·Twitter URL·Postype URL과 `landing_intro` 문구를 사용하며, 소개 문구가 비어 있으면 영역을 숨긴다. 소개용 작가명은 이 스트립 안에서만 사용하고 Navbar·Footer·문서 제목·SEO 문구의 전역 브랜드명 `도군`은 고정한다. 프로필 설정 행이 없을 때만 기존 화면과 같은 기본 소개명과 서비스 홈 URL을 제공한다. 랜딩 커미션은 작가 지정 순서의 앞 4개를 작은 썸네일 그리드로 보여준다. 커미션은 `/commission` 상세 페이지로 분리하되 **이번 단계는 가격·일정·예시·모집 상태와 신청 기능 준비 안내까지만** 제공하고, 실제 내부 신청 폼·이메일 접수는 M5에서 얹는다. 소개 분량이 많아지면 그때 별도 `/about`을 재검토한다.

**이유**
- 작가가 연재와 커미션을 함께 운영한다 - 랜딩 하나가 독자·의뢰인 두 관객에 매핑돼야 발견성이 산다. 빈 플레이스홀더로 두면 이 매핑이 안 생긴다.
- COMM-13(`/commission`, PRD)은 원래 "가격·일정·예시 + 신청 폼"이 한 덩어리라 M5 전체를 기다려야 했다. 정적 홍보와 접수 시스템(신청 폼 이메일 발송 + admin 관리 화면)을 층으로 나누면 정적 부분만 앞당길 수 있다 - M2 결정 1의 "절단(무료 구간)은 M2, 구매 검증은 M3"와 같은 층 분리 패턴.
- 별도 "작가 소개" 페이지보다 랜딩 히어로 + 커미션 페이지가 이미 bio·SEO 표면을 제공한다 - 페이지를 하나 더 만드는 것은 지금 시점에 과함(YAGNI). 소개 분량이 늘어나면 그때 분리 재검토.

**구현 전환(2026-08-13)**: 작가는 리포 파일을 직접 편집하지 않으므로 마크다운 content collection 방식을 폐기했다. M2 G 선행 PR에서 `commission_items`·`site_texts`와 owner 전용 admin 편집 화면, 공개 조회 API를 이미 구현했다. `/`와 `/commission`은 이 값을 재배포 없이 반영하도록 Astro SSR + 60초 공개 캐시로 렌더한다. 일부 조회가 실패하거나 아직 저장되지 않은 문구가 404이면 빈 상태가 첫 저장 뒤 남지 않도록 해당 페이지 응답은 `no-store`다.

**외부 CTA 폐기(2026-08-13)**: 외부 커미션 플랫폼·메일 링크를 임시 신청 경로로 두지 않는다. 우리 사이트의 카드·가격·샘플·모집 상태와 외부 플랫폼을 이중 관리하면 값이 어긋나고, 잠깐 쓰고 버릴 URL 설정 계약이 생긴다. M2는 신청 기능 준비 안내까지만 제공하고, M5에서 `CommissionItem.id`와 연결된 내부 신청 폼을 단일 신청 경로로 연다.

**미채택**: 랜딩을 그대로 빈 페이지로 두고 그룹 G를 원안(`/about`)대로 진행 - 커미션 발견 경로가 없어 위 이유 1과 충돌. 커미션 신청 폼까지 M2에 통째로 앞당기기 - 접수 시스템(이메일 발송·admin 관리 화면)은 결제·운영 도구와 붙어 있어 M5 스코프 확장이 더 크다(COMM-13은 P1이지 P0가 아님). 외부 CTA를 임시로 두기 - 위 이중 관리와 폐기 비용 때문에 채택하지 않는다.

**적용 범위**: `/`·`/commission` 공개 SSR 페이지 = M2 그룹 G(재정의, `M2_foundation.md` 참조). `/commission`에 내부 신청 폼 추가 + BE 이메일 발송 + admin 접수 관리 화면 = M5(README 커미션 항목).

### 보류/나중에 추가

| 기능 | 보류 이유 |
|------|----------|
| 멤버십/구독 | 초기 에피소드 개별 구매로 시작, 수요 확인 후 추가 |
| 묶음 할인 | 기본 구조 완성 후 추가 |
| 무통장 입금 | 가상계좌 운영 복잡도, 나중에 추가 |
| 소설 뷰어 | 웹툰 우선, 뷰어 타입 선택 구조만 열어둠 |
| 포렌식 워터마크 | VPS 성능 이슈 + 포스타입도 미적용, 나중에 연구 |
| Grafana | 초기엔 Hetzner 콘솔로 충분, 트래픽 늘면 추가 |
| 관리자 IP 화이트리스트 | 안정화 후 추가 |

### 제외 결정

| 기능 | 제외 이유 |
|------|----------|
| 다크모드 | 불필요하다고 판단 |
| 다운로드 소장 | 불법 유포 위험 |

---

## 콘텐츠 보호 전략 결정

**채택: 드래그/복사 차단 + 이미지 저장 차단 + Signed URL**

**검토했으나 제외한 방식들**

| 방식 | 제외 이유 |
|------|----------|
| Visible 워터마크 | 작품 감상 방해, 포스타입도 미사용 |
| 포렌식 워터마크 | VPS 성능 이슈, JPEG 압축 시 픽셀 파괴 |
| EXIF 메타데이터 | 카카오톡 전송만 해도 자동 삭제됨 |
| 다운로드 파일 제공 | 불법 유포 위험 |

**참고: 포스타입의 현재 방식**
- 드래그/복사 차단, 이미지 저장 차단
- Invisible 워터마크는 연구 단계, 미적용

---

## 보안 결정

### 관리자 로그인: 2FA(TOTP) 적용

**이유**
- 관리자 계정은 결제 데이터, 독자 개인정보, 콘텐츠 업로드 권한을 모두 보유
- 관리자 IP 화이트리스트는 안정화 후로 보류 → 그동안 비번 단독 보호는 위험
- TOTP는 무료(Google Authenticator 등) + 구현 단순 (시크릿 + 6자리 코드 검증)

**구현 방향**
- 흐름: 이메일/비번 검증 → TOTP 코드 검증 → JWT 발급
- 시크릿은 DB에 저장, 클라이언트에 절대 노출 금지
- 백업 코드는 1차 구현에서는 제외 (시크릿 분실 시 DB 직접 조작으로 복구)
- ⚠️ 2026-07-06(M1.5 B2) 구현 확정: `/admin/2fa/confirm`(TOTP 등록 후 첫 코드 검증) 성공 시 **재로그인 없이 즉시 인증쿠키 발급**. 그 시점엔 비번(1단계 pending 쿠키로 증명)과 TOTP 코드가 모두 검증된 상태라 2단계 로그인과 동등하기 때문. 상세: `docs/milestones/M1.5_foundation.md` B2.
- ⚠️ 2026-07-08(M1.5 B3) 구현 확정: **owner 세션 발급 지점 봉쇄** - owner의 세션(인증 쿠키)은 TOTP 경로(`/admin/login`→`/admin/login/totp`, `/admin/2fa/confirm`)로만 열린다. 일반 `/auth/login`·구글 OAuth는 owner면 generic 거부 → "owner의 유효 세션 = 전부 TOTP 통과" 불변식. 판정은 `auth_service.requires_totp_login` **단일 헬퍼** - **새 로그인 경로(카카오 등)를 추가하면 세션 발급 전 반드시 이 헬퍼를 통과시킬 것**. 승격 스크립트는 기존 세션 전부 revoke + 비번 없는(소셜 전용) 계정 승격 거부(락아웃 방지). `require_role`은 owner인데 TOTP 미활성이면 403(승격 직후 잔존 access 차단). 승격 표식(JWT 클레임/refresh 컬럼) 대안은 마이그레이션·JWT 최소설계 위반·FE 표면 확대로 탈락.
- **신뢰 기기**("이 기기에서 30일간 2단계 인증 생략", 2026-07-08 사용자 요청): TOTP 검증 성공 시 `remember_device` 옵트인으로 발급. DB `trusted_devices`(opaque 토큰의 HMAC 해시, revoke 가능) + HttpOnly 쿠키(Path=/admin, SameSite=Strict), **절대 만료 30일**(슬라이딩 없음). 비밀번호는 여전히 필수 - 쿠키는 TOTP(2차 요소)만 대체. `created_at >= totp_confirmed_at`인 행만 유효 → TOTP 재등록(분실 복구) 시 옛 기기 신뢰 자동 실효. stateless 서명 쿠키는 30일 크리덴셜인데 revoke 불가라 탈락(장수명 크리덴셜 = DB+해시 패턴 일관). ⚠️ 비밀번호 변경 기능(P1) 도입 시 신뢰 기기 일괄 revoke 규칙을 함께 구현할 것.
- ⚠️ 2026-07-22(#56) **TOTP 코드 replay 방지**: `users.totp_last_step`에 성공 검증된 time-step을 기록하고 **엄격 증가(매칭 step > last_step)만 통과** - valid_window(±30s) 창 안의 같은/이전 코드 재제출을 거부한다(RFC 6238 verifier 요구). 전진은 **조건부 UPDATE**(refresh 회전 선점과 같은 rowcount 패턴)로 원자화 - 같은 코드 동시 제출(실시간 릴레이 race)도 한쪽만 승자. `lib/totp.verify_code`는 매칭 step 반환으로 재구현(pyotp `verify()`는 bool만), setup 재등록 시 last_step 리셋(수동 복구 잔재 자가치유 - step은 시크릿이 아니라 시각 기반이라 이월됨). 상세: `docs/MODULES/BE/Auth/IMPLEMENTATION_ADMIN_2FA_LOGIN.md` §3.

**탈락한 후보들**
- SMS 2FA: SIM 스와핑 위험 + 발송 비용
- 이메일 OTP: 메일 계정 탈취되면 무력화
- WebAuthn: 1인 운영 초기엔 과함, TOTP만으로 충분

### 이메일 인증 필수

**이유**
- 환불 처리 시 정상 이메일로 안내해야 함 → 가짜 이메일로 가입하면 환불 통지 불가
- 결제 영수증 발송, 비밀번호 재설정 등 핵심 플로우가 이메일 의존
- 소셜 가입(카카오/구글)은 이미 검증된 이메일이라 별도 인증 생략 가능

**구현 방향**
- 일반 가입: 가입 후 인증 메일 발송, 유효 기간 1시간 토큰
- 미인증 상태에서도 무료분 열람은 가능하되, 결제는 인증 후에만 허용
- `users.is_email_verified` + `email_verifications` 테이블로 관리
- 토큰은 DB에 HMAC at-rest 해시로만 저장(원문은 메일 링크에만), 검증은 `POST /auth/verify-email`(상태 변경 + 메일 스캐너 GET prefetch의 일회용 토큰 소비 차단), 실패는 무효/만료/사용됨 비구분 단일 메시지

### 환경 베이스 URL: config.py에서 조립

**이유**
- OAuth 콜백 URI, CORS 허용 도메인, Signed URL 생성 등 동일한 베이스 URL이 여러 곳에서 필요
- env에 평면적으로 두면 환경(dev/prod) 이동 시 4~5군데 동시 수정 필요 → 누락 사고 잦음

**구현 방향**
- env: `APP_BASE_URL`(독자 사이트), `ADMIN_BASE_URL`(관리자), `API_BASE_URL`(백엔드) 세 개 정의
- `config.py`에서 `CORS_ORIGINS`는 app/admin 베이스로, `KAKAO_REDIRECT_URI`/`GOOGLE_REDIRECT_URI`는 **`API_BASE_URL`**(백엔드)로 조립
- env에 콜백 URI/CORS 직접 박지 않음
- ⚠️ 2026-06-14(D1) 정정: OAuth redirect_uri는 **백엔드 주소(`API_BASE_URL`)** 기준. 아래 "구글 OAuth: BFF" 참조. (초기엔 `APP_BASE_URL` 기준이었으나 콜백 수신 주체를 백엔드로 확정하며 변경)

### 구글 OAuth: 백엔드가 콜백 수신 (BFF 표준, M1 D1, 2026-06-14 확정)

**결정: authorization code flow를 백엔드가 받는다(BFF). 프론트는 "구글로 로그인" 버튼만.**

- 업계 표준(NextAuth/Django allauth/Spring Security/Passport)이 전부 백엔드 콜백 수신. IETF "OAuth 2.0 for Browser-Based Apps" BCP도 BFF 권장(토큰을 JS에 두지 말 것).
- "프론트가 콜백 받기"의 표준형은 브라우저(JS)가 토큰을 직접 교환·보관하는 것이라 우리 규칙(HttpOnly만, JWT localStorage 금지)과 충돌. 초기 문서(`callback.astro`)는 이 점을 놓친 설계라 폐기.
- `__Host-` host-only 인증 쿠키는 **API 호스트(백엔드)가 자기 응답에서 Set-Cookie** 해야 하므로 백엔드 콜백 수신과 자연 정합.
- 흐름: `GET /auth/login/google`(state·nonce 쿠키 set + 구글로 302) → 구글 → `GET /auth/callback/google`(백엔드: code 교환·id_token 검증·유저 처리·인증 쿠키 set) → `APP_BASE_URL` 홈으로 302.

**검증/방어 (공식 문서 기준: identity/protocols/oauth2/web-server + openid-connect)**
- id_token은 `google-auth`로 서명(JWKS)·`iss`·`aud`·`exp` 검증, `nonce`는 수동 대조. JWKS fetch는 sync라 `anyio.to_thread` 오프로드.
- `state`(CSRF) + `nonce`(replay)를 단명 서명 JWT 쿠키(`oauth_tx`, SameSite=Lax)로 stateless 운반.
- **PKCE 제외**: 공식 server-side 플로우는 state 기반이고, 컨피덴셜 클라이언트(client_secret 보유)라 코드 탈취돼도 secret 없이는 교환 불가 → PKCE 이득 미미. (원하면 방어심도로 추가 가능)
- `access_type=offline` 미설정(구글 API 지속 호출 불필요, 로그인엔 id_token만 필요).
- **자동 병합 금지(Q6)**: 같은 이메일의 비-소셜 계정이 있으면 병합 안 하고 안내. **open redirect 차단**: 복귀경로 파라미터 미지원(홈 고정).

### 비밀번호 해싱: bcrypt pre-hash + pepper (M1 B1, 2026-06-02 확정)

**라이브러리: `bcrypt` 직접 (5.x)**
- passlib 탈락: 마지막 릴리스 2020, 사실상 미유지보수 + bcrypt 5.0.0에서 passlib bcrypt 백엔드가 깨짐. 단일 알고리즘 확정이라 다중 해시 추상화 불필요.
- argon2id 아닌 bcrypt cost=12: 소형 VPS(Hetzner CX22) 메모리 제약 - argon2id는 메모리 하드라 동시 로그인 시 압박 + 파라미터 낮추면 오히려 약해질 위험. OWASP도 work factor ≥10 허용.

**해싱 구조: OWASP pre-hash**
```
bcrypt( base64( hmac_sha384(password, key=PASSWORD_PEPPER) ), gensalt(cost=12) )
```
- 한 구조로 (a) bcrypt 72바이트 한도 제거(긴 비번 허용, base64 출력 64자<72), (b) pepper 적용, (c) password shucking·null 바이트 방어를 동시 해결.
- HMAC은 raw `digest()`(48B)→base64. `hexdigest`(96자)는 72바이트 초과로 truncate되니 금지.
- bcrypt는 ~250~350ms CPU 블로킹이라 `anyio.to_thread.run_sync`로 오프로드(이벤트 루프 비블로킹).

**pepper 키 관리**
- `PASSWORD_PEPPER`(비번 pre-hash) / `TOKEN_PEPPER`(refresh·이메일 토큰 post-hash, B2)를 **분리**. JWT 서명용 `JWT_SECRET`과도 별개. (키 분리 원칙 + pre/post-hash 성질 차이)
- pepper는 DB 밖(env/`SecretStr`)에 보관, 로그 마스킹. default 없는 필수 설정(미설정 시 기동 실패).
- **제약: pre-hash pepper는 로테이션 불가** - 교체하려면 원문 비번이 필요해 전 유저 비번 재설정 강제. (토큰 pepper는 post-hash라 재-HMAC으로 로테이션 가능)
- 상세 원리: study `secret-hashing`, 계획: `docs/milestones/M1_foundation.md` B1.

### 네비 로그인 표시: 비-HttpOnly 힌트 쿠키 + pre-paint 인라인 스크립트 (2026-06-21 확정)

**결정: 인증 쿠키와 나란히 표시 전용 `login_hint`(비-HttpOnly) 쿠키를 발급하고, 네비 라벨을 React 섬이 아니라 정적 `<a>` + 페인트 전 동기 인라인 스크립트로 채워, 로그인/닉네임을 네트워크 왕복·깜빡임 없이(0프레임) 그린다.**

- **문제**: 네비 라벨은 SSG라 빌드 HTML에 로그인 상태가 없다. `getMe()` 왕복으로 채우면 콜드 로드마다 "빈 칸 → 닉네임" 깜빡임이 보인다.
- **라벨 출처 = 리프레시 수명**: `getMe` 401은 access(15분) 만료일 수 있어 로그아웃과 구분되지 않는다 → 라벨 gate에 못 쓴다. 라벨은 리프레시 토큰 수명(7일)과 함께 가는 힌트 쿠키가 출처여야 한다.
- **왜 비-HttpOnly가 안전한가**: 표시용(비민감 닉네임)이라 노출/위조돼도 인가에 영향이 없다. 서버는 이 값을 인증/인가에 전혀 쓰지 않는다(진짜 인증은 HttpOnly JWT 그대로). FE가 `document.cookie`로 동기로 읽어야 하므로 HttpOnly면 목적 자체가 불가능.
- **속성**: `Path=/`, `SameSite=Lax`, `Secure`는 env 분기, `Max-Age`=리프레시 수명. `__Host-` 프리픽스는 미사용(JS가 dev/운영 무관하게 고정 이름으로 읽게).
- **인젝션 차단**: 닉네임은 `quote(nickname, safe="")`로 URL 인코딩 후 set, FE는 `decodeURIComponent`로 복원. 쿠키/헤더 인젝션(`;`·CRLF) 방어.
- **set/clear는 인증 쿠키와 한 함수**(`set_auth_cookies`/`clear_auth_cookies`)에서 → 둘이 항상 함께 발급/제거되어 desync(한쪽 누락) 구조적 차단.
- **표시 방식 = pre-paint 인라인 스크립트(React 섬 제거)**: 쿠키+useEffect(React 섬)는 네트워크 왕복은 없애도 첫 페인트가 빈 칸이고 하이드레이션 1틱 뒤에야 닉네임이 채워져 "빈 칸→이름" 레이아웃 시프트가 남는다. 그래서 라벨을 React 섬에서 빼 순수 `<a id="nav-user">`로 두고, 바로 뒤 `<script is:inline>`(동기·파서 차단)가 **첫 페인트 전에** 쿠키를 읽어 보정한다 → 0프레임. (study no-flash-inline-script: 인라인 스크립트는 순수 HTML 대상일 때 빛난다.) **네비 SSR화는 탈락** - SSG/CDN 캐시를 포기해야 해 과함.
- **제약(stale)**: 닉네임 변경 시 다음 refresh/login 전까지 옛 닉네임 표시(표시용이라 허용. 닉네임 변경 기능 자체 미구현).
- 구현: BE는 `set_auth_cookies`(로그인/갱신/OAuth)·`clear_auth_cookies`(로그아웃/refresh 재사용)에서 발급/제거. FE는 `Navbar.astro`의 정적 `<a id="nav-user">` + pre-paint `is:inline` 스크립트가 쿠키를 읽어 보정(React 섬 `NavUser.tsx`는 제거). study `astro-auth-ui-state`, `no-flash-inline-script`.

### 관리자 권한 분리: 3-역할 RBAC (reader/owner/moderator) - M1.5 owner 단독 빌드 (2026-07-01 확정)

**결정: `users.role`(VARCHAR(16), default `reader`)로 권한을 나눈다. 값은 `reader`(일반)·`owner`(작가)·`moderator`(커뮤니티 운영) 셋. authz 진실 소스는 JWT claim이 아니라 DB `user.role`. 모델은 3-역할로 열어두되, M1.5에서 실제 빌드·프로비저닝하는 역할은 `owner` 하나뿐이다(moderator는 M4 커뮤니티에서 도입). 빈 껍데기 계정은 만들지 않는다.**

배경: 사이트를 운영(돈 받고 작품 판매)하는 작가와 게시글·문의를 관리하는 운영자가 다른 사람일 수 있다. 권한을 처음부터 역할로 설계하되 각 역할은 그 역할의 in-product 엔드포인트가 생길 때 프로비저닝한다.

**역할별 권한·도입 시점**

| 역할 | 권한 | 도입 | product 계정 |
|------|------|------|------|
| `reader` | 일반 열람·구매(기본값) | 지금(전 유저) | 모든 유저 |
| `owner` | 콘텐츠·매출·정산·환불 + 모더레이션 | **M1.5**(콘텐츠+2FA) | 부트스트랩 스크립트 |
| `moderator` | 게시글 삭제·문의 답변만(매출·콘텐츠 차단) | **M4**(커뮤니티) | owner가 런타임 부여 |

- **모델 = `role` VARCHAR(16)** (네이티브 PG enum 아님, `is_admin` boolean 폐기). VARCHAR이라 **후속 역할 추가(moderator M4 등)는 Python enum 값 + 가드만 추가, DB 마이그레이션 0**. M1.5 B1 마이그레이션은 기존 `is_admin=true`→`owner` 매핑 후 컬럼 제거(기존 `users` ALTER, 새 테이블 아님).
- **authz = DB `user.role` (JWT claim 아님)**: `get_current_user`가 이미 매 요청 `User` row를 DB 로드하므로(`lib/auth.py`) `user.role` 읽기는 추가 쿼리 0이고 항상 최신(강등/권한 회수 즉시 반영, 토큰 만료 대기 없음). JWT는 `sub`만 담는 최소 설계 유지(`create_access_token` "PII payload 포함 금지"와 일관). FE 가드용으로 `/auth/me`가 `role`을 노출(인가가 아니라 표시·라우팅용 - `login_hint` 철학과 동형).
- **가드 = `require_role(*roles)` 팩토리**. M1.5는 `require_owner`만 사용(콘텐츠·매출·정산·환불). 모더레이션 엔드포인트는 M4에서 `require_role(OWNER, MODERATOR)`(owner ⊇ moderator). 일반 열람·구매는 role이 아니라 "인증됨"으로 게이팅하므로 moderator도 정상 유저로 동작.
- **moderator는 owner가 런타임 부여**(owner 전용 엔드포인트, 예: `PATCH /admin/users/{id}/role`). 부트스트랩 스크립트로 박는 owner와 달리 관리자가 부여하는 첫 역할 = 진짜 RBAC. M4 소관.
- **개발자는 product 역할이 아니다 (developer 역할 미도입)**: 개발자 ≠ 운영자(작가)는 실재하는 분리지만, 개발자 일(에러·로그·헬스)은 전부 외부 도구(Sentry·UptimeRobot·Hetzner, 모니터링 결정) + 인프라 계층이라 product 계정·엔드포인트가 없다. product 안에 자체 관측 대시보드를 두는 건 전문 도구 재발명이라 미채택 → `developer`를 역할로 만들지 않는다. 정말 in-product 개발자 엔드포인트가 필요해지면 그때 값을 추가(VARCHAR라 DB 변경 없음).
- **2FA**: owner는 TOTP 필수(M1.5). moderator 2FA 여부는 M4 결정(권한이 좁아 blast radius 작음). 부트스트랩 `scripts/promote_admin.py`로 owner 승격(공개 관리자 가입 경로 없음).
- **⚠️ "개발자 매출 차단"의 실체 = 인프라 계층, product 역할 아님 (정직성)**: 운영 인프라(VPS·DB 자격증명)를 **개발자가 통제하는 현 구조**에서 라우트 가드는 *앱 경로*만 막는다 - DB 직접 `SELECT`는 못 막는다. 그래서 "개발자가 매출을 못 본다"는 product 역할이 아니라 **자격증명/도구 소유권**으로 친다(owner가 결제도구·DB 로그인을 쥐고 개발자는 발급받지 않음). **진짜 정보 장벽**(개발자조차 매출 불가)은 작가가 DB 자격증명을 쥐고 개발자가 prod DB 접근이 없을 때 성립 → **M7 배포 인프라 결정으로 보류**.
- **다중 계정 / 단수 정산**: `role`은 N명이 같은 역할을 가질 수 있다(owner 여러 명 가능, singleton 제약 없음). 단 **정산/지급 대상은 owner 계정 수에서 파생되지 않는다** - 돈 받는 주체는 단수 "작가" 정체성(1인 작가 결정)에 묶고, owner 역할은 관리 권한으로만(M5 정산 시 적용).
- 적용 범위: 역할 모델·`require_owner`는 M1.5 그룹 B, moderator·부여 UI는 M4, 매출 엔드포인트 가드는 M5. 상세 `docs/milestones/M1.5_foundation.md` 그룹 B + 결정 4.

### 세션 유지: 401 자동 refresh + 관리자 자동 로그인 (2026-07-15 확정, #67·#69)

**결정: 공용 fetch 래퍼(`packages/shared`)가 401 시 `POST /auth/refresh`를 1회 자동 호출 후 원요청을 재시도한다. 이로써 독자·관리자 모두 refresh 수명(사용 시 +7일 슬라이딩, 절대 cap 30일) 동안 세션이 유지된다. 관리자도 독자와 동일 적용(별도 제한 없음).**

- **관리자 자동 로그인 허용 근거** (2026-07-14 판단): 지갑/포인트가 없어 정산은 작가 계좌 직행 - 관리자 세션 탈취의 실익은 "절도"가 아니라 "파괴·유출"이고, 그 방어는 세션 수명이 아니라 2FA·신뢰 기기·revoke가 담당한다. 신뢰 기기(30일, TOTP만 생략)와 겹쳐도 절대 cap 30일 + 로그인 시 비밀번호 필수는 유지된다. #69의 "관리자는 결정 전 구현 금지" 항목 해소.
- **owner의 `/auth/refresh` 사용은 의도다**: B3 봉쇄 불변식("owner의 유효 세션 = 전부 TOTP 통과")은 세션 **발급**에 대한 것. owner의 refresh 토큰은 TOTP 경로에서만 발급되므로 refresh 성공 = TOTP 통과 세션의 **연장**이고 불변식이 유지된다. `rotate_refresh`에 role 체크가 없는 것을 버그로 오인해 막지 말 것 - 막으면 관리자만 15분마다 재로그인하는 #67 원상태로 돌아간다.
- **멀티탭은 Web Locks로 직렬화**: 탭마다 JS 컨텍스트가 별개라 in-flight 공유가 탭 안에서만 유효한데, 두 탭이 같은 refresh 토큰을 동시 제출하면 회전 재사용 탐지가 탈취로 오분류해 전 세션 revoke될 수 있다 → `navigator.locks`로 오리진 내 직렬화(미지원 환경 폴백). 상세: `docs/MODULES/COMMON/Shared/IMPLEMENTATION_API_AUTO_REFRESH.md`.
- **재시도 제외**: `/auth/refresh`·`/auth/login`·`/admin/login`·`/admin/2fa`의 401은 만료가 아니라 자격 거부/pending 만료 의미 → 자동 재시도 금지(틀린 비밀번호·TOTP 재전송 방지). **새 로그인 경로 추가 시 제외 목록에도 추가할 것.**
- **미채택: "로그인 유지" 체크박스** (2026-07-15): ① 체크(수명 연장) 쪽 가치는 회전+cap으로 이미 대부분 존재(활성 사용자는 최대 30일) ② 미체크(세션 쿠키, 공용 PC 보호) 쪽은 브라우저 "세션 복원" 기능이 세션 쿠키를 살려내 약속이 안 지켜짐 - 확실한 수단은 로그아웃 ③ 구현은 회전 시 선택 승계가 필요해 `refresh_tokens` 컬럼 추가(마이그레이션)급. 독자 수요 신호가 생기면 재검토.

---

## 결제 구조 결정

### PG = 포트원 확정 + 결제 최후순위 재배치 (2026-07-03)

**결정 1: PG는 처음부터 포트원. "개발은 토스 샌드박스, 출시 시 포트원 교체"(구 PRD Q4)는 폐기.**
- 포트원은 사업자 등록 없이 가입 즉시 **테스트 채널**로 연동 개발 가능(실결제 전환 시에만 사업자 정보 + 가맹점 심사 필요) → 토스 경유의 존재 이유(사업자 없이 개발 시작)가 소멸하고, PG 교체 재작업 리스크도 제거.
- 결제 식별자 용어는 포트원 기준(V1 `imp_uid` / V2 `paymentId`, SDK 버전은 M3 착수 시 결정).

**결정 2: 결제(M3)를 실행 순서 마지막(M5·M6 뒤, M7 직전)으로 재배치.**
- 결제 없이 완결되는 사이트(무료 열람 + 커뮤니티 + 관리자 + 알림)를 먼저 완성하고 결제를 마지막에 붙인다.
- 이유: (a) **사업자 등록을 최대한 지연** - 사업자가 필요한 항목(포트원 실키 심사·카카오 비즈앱·통신판매업 신고)이 전부 M3~M7 구간으로 몰리고, 그 전 단계는 전부 사업자 불필요. (b) 법무(약관·청약철회, Q1/Q7)와 결제 화면이 M7 직전에 붙어 자연 연계. (c) 결제 외 기능이 결제 일정에 블로킹되지 않음.
- 동반 이동: 후원(M4→M3), 수익·환불·후원 운영 도구(M5→M3). 마일스톤 번호는 식별자로 유지(재부여 없음), 실행 순서는 milestones README 다이어그램 기준.

### 기본 구조

- 에피소드별 개별 구매 (500원 예정)
- 전편 구매 옵션 추가
- 충전식 코인 방식 채택 안 함 (개인 사이트 신뢰도 문제)
- 카카오페이/토스페이 수수료가 카드보다 낮음 (1.5~2% vs 2.5~3.5%)
- 소액 결제 마찰 줄이기 위해 카카오페이/토스페이 우선 노출

### 결제 내역 보관 기간: 5년

**이유**
- 전자상거래법상 대금 결제 및 재화 공급 기록은 5년 보관 의무
- 회원 탈퇴 시에도 `purchases`, `payment_logs`, `donations` 테이블 데이터는 유지
- 탈퇴 유저는 `users.deleted_at` 기록 + `nickname` 익명화로 처리, 결제 레코드는 user_id FK 유지

---

## 커뮤니티 결정

### 댓글 작성 조건: 없음

> 2026-07-03 재확인: PRD Q13("가입 7일 제한 유지")과 충돌 발견 → 사용자 확인으로 **이 결정(조건 없음)을 유지**, PRD Q13은 폐기 처리.

**이유**
- 1인 운영 + 초기 사용자 규모 → 가입 직후 바로 댓글 가능
- "가입 N일 이후" 같은 제약은 사용자 경험만 해침, 스팸은 신고 기능으로 대응
- 스팸/어뷰징 문제 발생하면 그때 다시 검토

### 댓글에도 좋아요 가능

**이유**
- 게시글/에피소드 좋아요와 동일하게 댓글에도 반응 가능
- `likes.target_type`에 `'episode' | 'post' | 'comment'` 모두 포함

---

## 브랜치 전략 결정

### GitHub Flow + 영역 prefix (area-first)

**흐름**
```
main (항상 배포 가능 상태)
  └── be/feat/auth-jwt
  └── be/fix/payment-webhook
  └── fe/feat/episode-viewer
  └── fe/fix/viewer-scroll
  └── admin/feat/upload-form
  └── common/docs/code-review
  └── common/chore/env-setup
```

**브랜치 패턴**

| 타입 | 패턴 | 예시 |
|------|------|------|
| 기능 | `{영역}/feat/{기능}` | `be/feat/auth-jwt` |
| 버그 | `{영역}/fix/{내용}` | `fe/fix/viewer-scroll` |
| 리팩토링 | `{영역}/refactor/{내용}` | `be/refactor/test-fixtures` |
| 공통/설정/문서 | `common/{type}/{내용}` | `common/docs/code-review` |
| 긴급 핫픽스 | `{영역}/hotfix/{내용}` | `be/hotfix/payment-duplicate` |

영역: `be` (백엔드), `fe` (프론트), `admin`, `common`

**이유**
- 1인 프로젝트 → GitFlow 오버스펙, GitHub Flow가 적합
- 영역 prefix를 맨 앞에 두고 area-first로 구성
  - `git branch`에서 `be/`, `fe/`, `admin/`, `common/` 별로 자동 그룹화
  - 어느 영역 작업인지 한눈에 확인, 영역별 진행 상황 파악 용이

---

## 모니터링 결정

| 도구 | 역할 |
|------|------|
| UptimeRobot | 사이트 다운 감지 + 알림 (무료) |
| Sentry | 코드 에러 추적, 프론트/백엔드 (무료 플랜) |
| Hetzner 콘솔 | CPU/메모리/디스크 기본 확인 |
| Grafana | 나중에 추가 (Docker로 쉽게 붙일 수 있음) |

---

## 프론트엔드 도구 결정

### admin API 타입: openapi-typescript codegen 도입 (M1.5 F2 선행, 2026-07-14 확정)

**결정: `admin/src/types/index.ts`(수기 미러링)를 폐기하고, 백엔드 `app.openapi()` → `openapi-typescript` → `admin/src/types/api.gen.ts`(생성물, 커밋됨) 파이프라인으로 교체. `index.ts`는 그 위 얇은 별칭 레이어(`UserRead` 등 짧은 이름 재수출)만 남긴다.**

- **왜 F1이 아니라 F2인가**: F1은 타입 표면이 작아(`UserRead`/`AdminLoginResponse`/`TotpSetupResponse` 4개) 수기로도 버틸 만해 의도적으로 미뤘다. F2(작품 CRUD)부터 Work/Tag/Episode 요청·응답 스키마가 한꺼번에 들어와 표면이 커지고, F3·F4도 이어 붙는 시점이라 지금이 도입 분기점.
- **문제**: 수기 미러링은 백엔드 스키마가 바뀌어도 `tsc`가 못 잡는다(둘 다 독립된 텍스트라 컴파일러 관점에서 드리프트가 안 보임) - 런타임에 `undefined`로만 드러난다. F1에서 `types/index.ts` 주석에 이미 "RoleEnum 값이 바뀌면 role 가드가 조용히 오작동" 경고를 남겨둔 상태였다.
- **채택**: `backend/scripts/export_openapi.py`(서버 기동 없이 `app.openapi()` 덤프) + `scripts/generate-api-types.sh`(루트, JSON 중간산출물 생성→`openapi-typescript`→삭제) + `admin package.json`의 `generate:types` 스크립트. 생성물(`api.gen.ts`)은 `routeTree.gen.ts`와 동일하게 **커밋**(FE/admin CI job이 아직 없어 빌드 시 재생성을 강제할 수 없음 - CI/CD 결정 "후속" 참조).
- **탈락**: `@hey-api/openapi-ts`·`orval` 등 경쟁 도구도 검토했으나 openapi-typescript가 카테고리 다운로드 1위(주간 ~400만, 2026-07-14 npm 확인)이자 가장 얇음(타입만 생성, 런타임 클라이언트 강제 없음 - 기존 `packages/shared`의 `createApi` 래퍼를 그대로 유지).
- **규칙**: `api.gen.ts`는 손으로 고치지 않는다. 스키마 변경 후 `pnpm --filter admin generate:types` 재실행 → `index.ts` 별칭이 여전히 유효한지 확인.

---

## CI/CD 결정

### CI: GitHub Actions, 백엔드 우선 (2026-06-22)

**결정: M0 F1을 백엔드 CI부터 구현한다. PR(→main)·main 푸시 시 ruff + format + pytest를 GitHub Actions로 돌린다. CD/배포(F2~F3)와 FE/admin job은 후속.**

- **범위 = 백엔드 우선**: 결제·인증·Signed URL 등 데이터 무결성 리스크가 BE에 집중 → 가장 비싼 회귀부터 막는다. FE/admin(eslint+tsc)은 frontend ESLint 셋업 선행 필요라 분리.
- **도구**: `astral-sh/setup-uv`(캐시) + `uv sync --locked`(lockfile 재현성) + `actions/checkout`. Python은 `uv python install`이 `requires-python`(3.12)으로 자동 설치.
- **검사 범위 = be.md PR 템플릿 게이트와 일치**: `ruff check src/`, `ruff format --check src/ tests/`. `migrations/`는 alembic 자동생성 + DB 적용 + forward-only라 의도적 제외(손대면 안 됨).
- **테스트 DB**: GitHub Actions `postgres:16` 서비스. conftest가 `SQLModel.metadata.create_all`로 스키마를 직접 만들어 CI에 alembic 스텝 불필요. 필수 env(`PASSWORD_PEPPER` 등)는 테스트 전용 더미값 주입(실제 비밀 아님).
- **`paths` 필터 미적용**: required check로 걸면 path-skip이 "pending"으로 남아 머지를 막는 트레이드오프 + 1인 저PR 볼륨이라 Actions 분 절약 한계효용 낮음.
- **⚠️ CI 효력의 전제 = branch protection (정정 2026-07-02: 무료 플랜 불가)**: 게이트의 실제 효력은 YAML이 아니라 서버 규칙(branch protection/ruleset)에 있다(`/council` 5렌즈 공통 맹점). 그러나 `backend`를 required status check로 등록하려면 branch protection 또는 ruleset이 필요한데, **무료 private repo는 둘 다 불가**(`branches/main/protection`·`repos/.../rulesets` API 모두 403 "Upgrade to Pro or make public"). 따라서 CI가 빨강이어도 서버가 머지를 강제로 막지 못한다 - 원래 "후속 P0(branch protection 등록)"는 이 플랜에선 실행 불가. 대신 **로컬 훅 `.githooks/pre-push`로 main 직접 push를 차단**해 PR 흐름(브랜치 → PR → squash-merge → `git pull`)을 강제한다(B1이 PR 없이 main 직행한 사고 대응). 단 이 훅은 "직접 push 금지"만 강제하고 **CI-그린은 강제하지 못한다**(클라 훅은 CI 상태를 못 봄) → CI 준수는 수동 규율. 진짜 서버 게이트가 필요하면 Pro 업그레이드 또는 repo 공개.
- **후속**: `alembic upgrade head`+`alembic check` 게이트(모델↔마이그레이션 표류 차단), 액션 SHA 핀(공급망), CD(F2~F3).
- **완료된 후속**: HIBP 외부호출 테스트 격리(hermetic, 2026-06-24) - conftest autouse 전역 stub(`_stub_hibp`)으로 어떤 테스트도 `api.pwnedpasswords.com`에 실제 요청을 못 보내게 함(per-test mock 의존 제거). 실제 함수 본문 raise sabotage로 미도달 입증. FE/admin job(2026-07-23, #98) - pnpm 10 + Node 24 셋업, frontend job(astro check/build/vitest)·admin job(eslint/tsc·vite build/vitest) 전 job 그린. frontend ESLint(2026-08-18) - ESLint 10 flat config와 Astro/TS/React Hooks recommended를 추가하고 frontend job에서 astro check 전에 실행한다.

---

## 회차 식별/URL 결정

### 회차 번호 폐기: 랜덤 공개 ID URL + 작가 지정 정렬 (2026-07-28, 구현 완료 2026-08-03)

**결정: `episode_no`(순번) 개념을 없앤다. 독자 URL은 포스타입식 랜덤 8자리 숫자 ID(전역 유니크)로, 목록 정렬은 `created_at`(올린 순서)으로. 구현은 #85 머지 후 별도 PR.**

- 식별은 이미 UUID(PK)가 한다. 번호의 실제 역할은 ①독자 URL ②정렬 ③"N화" 표기 셋이었는데 - 표기는 불필요(제목만 노출, 사용자 결정), URL은 랜덤 ID로, 정렬은 created_at으로 각각 대체된다.
- **#85의 "번호 소진(재사용 불가)" 결정은 이 결정으로 대체된다.** 소진은 번호 기반 URL(`/works/{작품}/{번호}`)이 전제였다 - 전제가 사라지므로 함께 소멸. #85에 넣은 소진 UX(확인창 경고·409 안내 문구·max+1 삭제분 카운트)는 새 PR에서 제거한다.
- **시점 근거**: 출시 전이라 북마크를 가진 독자가 없다 - URL 스킴 변경 비용이 최소인 지금 확정. 출시 후엔 리다이렉트 없이 못 바꾼다.
- **created_at 정렬 근거**: 내렸다 재공개해도 원래 자리를 유지한다(published_at 정렬이면 재공개 시 맨 뒤로 밀림 - #85의 "내리기"와 조합 시 순서가 흔들림). admin에 번호 입력 UI가 원래 없어 실사용 순서 = 올린 순서였고, 그 동작이 그대로 보존된다.
- **랜덤 8자리**(1억 공간): 1인 작가 규모에서 생일 충돌 무시 가능. UNIQUE 제약이 백스톱, 충돌 시 재생성.
- 영향 범위: FE `[episodeNo].astro` 라우트, BE 읽기·카탈로그·스키마, admin "N화" 표기, 마이그레이션 1건(공개 ID 추가+백필, episode_no 제거).
- **구현에서 확정(2026-07-29)**: 컬럼명은 `public_id`(결정문의 "1억 공간·선행 0" 대신 선행 0 없는 `INTEGER 10_000_000~99_999_999`, 9천만 공간 - 정규화 문제 회피). URL 계층은 `/works/{workId}/{publicId}` 유지(단독 `/e/{publicId}`는 회차→작품 역조회 엔드포인트가 새로 필요해 기각). 생성은 앱단 `secrets.randbelow` + IntegrityError 재시도(최대 5회, 시도마다 새 ORM 인스턴스). soft delete는 유지하되 근거를 재정의 - "번호 재사용 방지"가 사라진 자리를 "M3 `purchases.episode_id`가 `ON DELETE` 없이(RESTRICT) 참조해 구매 기록이 걸린 회차는 하드 삭제 자체가 불가"로 대체(`docs/DB_SCHEMA.md` §purchases). 마이그레이션(`f3a43b32fcfb`)은 upgrade/downgrade 왕복 실측 완료(9행). 상세: `docs/MODULES/BE/Works/IMPLEMENTATION_EPISODE_PUBLIC_ID.md`.
- **정렬 정정(2026-07-30, 코드 리뷰 반영)**: 결정문의 "정렬은 created_at"은 **불충분했다**. 번호는 정렬 기준 역할도 겸했는데, `created_at`만 남기면 프롤로그를 나중에 끼워넣거나 잘못 올린 순서를 되돌릴 수단이 아예 없어진다(admin에 번호 입력 UI가 없었다는 근거는 "순서를 못 바꿔도 된다"가 아니라 "번호를 직접 칠 필요가 없다"였다). `episodes.sort_order`(작품 스코프, 작가 지정, 기본 `max+1`)를 추가하고 정렬을 `sort_order → created_at → id`로 확정한다. **UNIQUE는 걸지 않는다** - 유일 제약이 `episode_no`가 409를 뱉던 원인이고, 표시 순서는 동점이어도 tie-breaker가 깨준다. 재배열 API는 컬렉션 PUT(`PUT /admin/works/{workId}/episodes`)에 살아있는 회차 전량을 순서대로 전송(집합 불일치 = 409 = 낙관적 동시성 검사), admin UI는 ↑↓ 버튼(드래그앤드롭 의존성 도입 안 함). 마이그레이션 `a7c91d05e3b4`의 백필이 직전 정렬과 동일 순번이라 전환으로 순서가 바뀌지 않는다.
- **제목 필수화 동반(2026-07-30)**: `EpisodeCreate.title`의 서버 기본값 `'무제'`를 제거한다(빈 제목 = 422). 번호가 사라지면서 목록·액션 메뉴·뷰어 네비의 식별자가 **제목 하나로** 줄어, `'무제'` 행이 둘 이상이면 구분이 불가능해졌기 때문. admin의 "제목 필수"(`ensureTitle`) 결정은 원래 있었지만 **이미지 업로드가 만드는 지연 draft**만 예외로 서버 기본값을 타고 있었고(`IMPLEMENTATION_EPISODE_EDITOR.md`의 명시적 예외), 그 예외를 이번에 닫았다.
- **드래그 재배열 정정(2026-08-03, 사용자 결정)**: 위 "admin UI는 ↑↓ 버튼(드래그앤드롭 의존성 도입 안 함)"을 **뒤집는다**. `@dnd-kit`(`core` 6.3.1 + `sortable` 10.0.0)을 도입해 드래그로도 순서를 바꿀 수 있게 한다. 네이티브 HTML5 DnD는 **터치에서 이벤트 자체가 발생하지 않아** 태블릿에서 무반응이고 키보드로도 못 쓴다 - 의존성 0의 대가가 "특정 기기에서 기능이 아예 없음"이라 기각. 채택 근거는 실측: `@dnd-kit/core` 주간 다운로드 22,364,808건(2026-07-27~08-02), 같은 기간 `react-dom` 153,656,463건 대비 약 14.6%. **↑↓ 버튼은 존치**한다(드래그가 안 되는 상황의 대체 수단). 서버 API는 이미 "정렬된 id 목록 전량"을 받으므로 **백엔드 변경 없음** - 순수 admin 프론트 작업이고 별도 PR로 분리한다.

---

### 독자 회차 목록 UX: 날짜·정렬·진행률 (2026-08-03)

**결정: 작품 상세에 ①회차별 공개 날짜 ②최신순/등록순 정렬 토글(기본 최신순) ③첫 화 보기 ④이어 보기 + 작품 단위 진행률 바를 넣는다. 회차 내부 진행률(%)은 M2에 넣지 않고 M3로 미룬다.**

배경: 회차 번호 폐기(2026-07-28)로 독자가 "몇 화까지 봤다"를 기억할 수단이 사라졌다. 기본 정렬까지 최신순이면 돌아온 독자는 제목만 스무 개 늘어선 목록에서 진도를 알 수 없다. 번호가 하던 그 역할을 진행률이 대신한다.

- **날짜는 `first_published_at`**: 공개 시각이 독자에게 의미 있는 값이고 `created_at`은 작가가 draft를 만든 시각이라 무관하다. 구현 전 실측에서 #85의 "내렸다 재공개" 시 `published_at`이 새 공개 시각으로 갱신됨을 확인했으므로, 독자 표시 전용 최초 공개 시각 컬럼을 분리한다. 최초 즉시 공개와 예약 공개에서 한 번만 스탬프하고 재공개에서는 유지한다. 예약 공개는 목표 시각(`published_at`)이 아니라 DB가 실제 공개 상태로 전환한 시각을 기록한다 - 빈 본문 등으로 공개가 지연되면 두 시각이 달라질 수 있다. 기존 공개 회차는 마이그레이션에서 당시 `published_at`으로 백필한다.
- **정렬은 프론트에서 뒤집는다**: 회차 목록은 페이지네이션이 없어(M2 결정 5) 전량이 이미 응답에 있다. 서버 정렬은 `sort_order` 오름차순 그대로 두고 프론트가 역순으로 그린다(서버 왕복 0). 상태는 URL 쿼리(`?order=`)에 둔다 - 새로고침·공유에 남고 캐시 키도 자동으로 갈라진다.
- **첫 화 보기는 정렬 토글과 무관**: 항상 `sort_order` 기준 첫 회차. 최신순으로 보는 중에 "첫 화 보기"가 마지막 화로 가면 안 된다. 기본이 최신순이라 1화가 목록 맨 아래로 밀리므로 이 버튼의 역할이 더 커진다.
- **이어보기는 로그인 전용 + 클라이언트 섬**: `viewer_progress`가 `user_id` 기반이라 비로그인은 대상이 아니다(뷰어도 `isLoggedIn` 체크 후에만 저장한다). **절대 SSR HTML에 넣지 않는다** - 작품 상세는 성공 시 `Cache-Control: public, max-age=60`(`lib/http.ts`)이라 HTML이 60초간 모든 독자에게 공유된다. 개인 진행도를 HTML에 넣으면 남의 진도가 그대로 새어나간다.
- **작품 단위 바만 넣는 이유**: `읽은 회차 수 / 전체 회차 수`는 회차가 이산 단위라 왜곡이 없고, 이어보기가 어차피 조회할 데이터라 추가 비용이 0이다.

**회차 내부 진행률(%)을 M2에서 뺀 근거 (2026-08-03 코드 검증)**

지금 구조로는 정확한 회차 내 퍼센트를 만들 수 없다. 두 방식 다 **단독으로는 성립하지 않는다**.

- **서버 픽셀 누적은 원리적으로 불가능하다**: 본문 화이트리스트에 `paragraph`가 있어 글과 이미지가 섞인다(`lib/content_doc.py`, "글만 있는 회차도 공개 가능" - #76). 서버는 글 블록이 화면에서 차지할 높이를 알 수 없다(뷰포트 폭·폰트·줄바꿈 의존). 이미지 높이를 전부 저장해도 글 섞인 회차에선 계산이 반쪽이다.
- **클라이언트 스크롤 비율도 지금은 못 쓴다**: 뷰어가 이미지에 크기를 주지 않는다(`Viewer.tsx`의 `w-full h-auto` - `width`/`height` 속성도 `aspect-ratio`도 없음). 로드 전 높이가 0이라 `scrollHeight`가 계속 변하고, M2 결정 6("즉시 전량 요청")이라 수십 장이 동시에 들어와 변동이 더 크다. 이 상태로 비율을 저장하면 **믿을 수 없는 값이 쌓이고, 나중에 고쳐도 그 값들은 재활용할 수 없다**.
- **둘은 경쟁이 아니라 의존 관계다**: 이미지 높이 저장 → 뷰어 공간 예약 → `scrollHeight` 확정 → 그 위에서 스크롤 비율이 신뢰 가능해진다. 순서를 건너뛸 수 없다.

**복원 앵커 보강 (2026-08-14 사용자 결정, 2026-08-15 리뷰 보완)**: 위 판단은 회차 전체 진행률과 완독 판정에는 그대로 유효하지만, 복원까지 블록 인덱스만 쓰는 것은 실제 원고에서 충분하지 않았다. `398x5400`처럼 한 이미지 파일 안에 여러 패널이 들어가면 독자가 이미지 중간까지 읽어도 같은 블록 1개로만 기록돼 재진입 때 이미지 시작으로 돌아간다. M2는 `viewer_progress.page_no`와 함께 `block_offset_bp`(현재 블록 내부 0..10000)를 저장하고, 현재 렌더 높이에 같은 비율을 적용해 복원한다. 이 값은 회차 전체 분모를 쓰지 않으므로 이미지 공간 미예약 상태에서도 다른 블록의 로드 순서에 영향을 받지 않는다. 전체 진행률 표시, 완독 판정, 구매 후 CTA는 여전히 M3다. 복원 GET이 끝나기 전에는 초기 observer 값을 저장하지 않으며, 구버전 요청이 같은 블록을 다시 저장하면 기존 오프셋을 보존하고 블록이 바뀔 때만 0으로 초기화한다.

**M3 순서(구매 회차 진행률을 만들 때)**: ① 이미지 높이 저장(변환 시 Pillow가 이미 `img.height`를 계산하고 있다 - `image_service.py`, 저장만 안 할 뿐이라 계산 비용은 0. 비싼 건 스키마 변경과 기존 이미지 백필) → ② 뷰어가 크기로 공간 예약 → ③ 회차 전체 스크롤 비율과 완독 상태 추가. M2의 하이브리드 앵커는 복원용으로 유지하고, M3 값은 진행률 표시·완독 판정에 쓴다. 그 위에서 미구매 회차의 가격 표시 자리를 구매 후 진행률 바로 교체한다(`is_purchased`는 이미 `EpisodeSummary`에 있다). 구매 회차는 전체 본문을 받으므로 분모가 하나뿐이라, 무료 절단으로 생기던 분모 불일치가 이 범위에선 발생하지 않는다.

**M3 CTA 완료 판정 추가 결정 (2026-08-12)**: 작품 상세의 플로팅 CTA는 "최근에 연 회차"만으로 다음 회차를 고르지 않는다. 회차별 진행도를 조회해 현재 회차가 100% 완료됐을 때만 `다음 화 보기`로 전환하고, 100% 미만이면 `보던 회차 이어 보기`와 현재 회차 제목을 표시한다. 최초 진입은 기존처럼 `첫 화 보기`, 마지막 회차 완독 뒤에는 `마지막 화 다시 보기`다.

- **100%는 실제 끝 도달 이벤트로 확정한다**: 표시용 비율을 반올림해 100으로 보이게 하거나 `99% 이상` 같은 임계값을 쓰지 않는다. 공간 예약으로 `scrollHeight`가 안정된 뒤, 뷰어가 제공받은 전문의 마지막 최상위 블록 끝에 실제로 도달했을 때만 저장값을 정확히 100%로 고정한다. 중간 진행률은 표시용이며 복원 기준은 `viewer_progress.page_no + block_offset_bp`다.
- **부분 유료 미구매 회차는 무료 경계가 끝이 아니다**: 서버가 절단한 미리보기의 마지막 블록에 닿아도 회차 전문을 완독한 것이 아니므로 100%로 저장하지 않고 다음 화 CTA를 노출하지 않는다. 구매 검증 뒤 전문을 받은 상태에서 실제 끝에 도달해야 완료된다. 클라이언트가 보낸 완료값만 믿지 않고, 서버는 해당 사용자의 회차 열람 권한과 응답 범위를 기준으로 완료 저장 가능 여부를 검증한다.
- **작품 단위 진행률 의미도 맞춘다**: M2의 `읽은 회차 수 / 전체 회차 수`는 열어 본 회차 수도 읽은 것으로 세는 임시 계약이다. M3부터 분자를 `100% 완료 회차 수`로 바꿔, CTA의 완료 판정과 진행률 바가 같은 의미를 사용하게 한다.
- **검증 가능한 상태 전이**: 진행도 없음 → 첫 화, 현재 회차 0~100% 미만 → 현재 회차 이어 보기, 현재 회차 100% + 다음 회차 있음 → 다음 화, 현재 회차 100% + 다음 회차 없음 → 마지막 화 다시 보기. 이미지 로드 전후에도 비율이 역행하지 않고, 잠금 경계 도달만으로 완료되지 않는 테스트를 포함한다.

이미지 높이 저장의 진짜 가치는 진행률이 아니라 **레이아웃 안정성**이다. 공간 예약이 없어 이미지가 로드될 때마다 콘텐츠가 튀고, 진행도 복원이 흔들린 이력도 있다(`50767af` 뷰어 진행도 복원 안정화). 진행률 정확도는 그 기반 작업의 부산물로 따라온다. ⚠️ **미검증**: 실제 CLS 수치는 측정하지 않았다 - 코드 구조에 근거한 추론이다.
