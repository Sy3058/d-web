# Frontend - Astro 독자용 사이트

## Astro 작업 규칙 (먼저 읽기)

Astro 관련 작업(페이지·SSR/`prerender`·env·라우팅·설정·통합) 시작 전 **반드시 `@docs/guides/GUIDE_ASTRO.md`를 먼저 확인**한다. 현재 Astro 7의 버전 민감한 API는 공식 문서를 WebFetch로 재확인하고 새로 발견한 델타는 그 문서에 누적한다.

---

## 스택 결정 (왜?)

| 항목 | 선택 | 이유 |
|------|------|------|
| 프레임워크 | Astro | SEO (정적 HTML) + 모바일 로딩 성능 핵심. React 아일랜드로 인터랙션 분리. |
| 인터랙션 | React | Astro 안에서 필요한 부분만 섬 단위로 사용. |
| 스타일 | Tailwind | 모바일 중심, 빠른 프로토타이핑. |
| 폼 | react-hook-form + Zod | 타입 안전, 가벼움. 결제 폼 검증 필수. |
| 페칭 | fetch | TanStack Query는 섬 단위로 작아서 불필요. fetch만으로 충분. |

---

## 프로젝트 구조

```
frontend/src/
├── pages/                    # Astro 파일 라우팅
│   ├── index.astro           # 홈 (SSR, 최근 등록 작품 + admin 편집 문구/커미션)
│   ├── commission.astro      # 커미션 안내 (SSR)
│   ├── works/
│   │   ├── index.astro       # 작품 목록 (SSR, 단기 HTTP 캐시)
│   │   └── [id].astro        # 작품 상세 (SSR, 단기 HTTP 캐시)
│   ├── works/[id]/episodes/[episodeId].astro  # 뷰어 (SSR)
│   ├── auth/
│   │   └── login.astro       # 로그인 + 구글 버튼 (SSG). 구글 콜백은 백엔드 수신(BFF), 프론트 콜백 페이지 없음. ?error=로 실패 표시
│   ├── my/purchases.astro    # 구매 내역 (SSR, 로그인 필수)
│   └── api/
│       ├── auth/logout.ts    # POST 엔드포인트 (백엔드 경유)
│       ├── purchase.ts       # POST (포트원 검증, 백엔드 경유)
│       └── viewer/progress.ts # POST (진행도 저장, 백엔드 경유)
├── components/
│   ├── viewer/EpisodeViewer.tsx    # 세로 스크롤 뷰어 (React, client:idle)
│   ├── auth/LoginForm.tsx          # 로그인 폼 (React, client:load)
│   ├── auth/GoogleButton.tsx       # 구글 로그인 버튼 → 백엔드 /auth/login/google 로 이동(BFF)
│   ├── payment/PurchaseButton.tsx  # 결제 (React, client:idle)
│   ├── community/CommentForm.tsx   # 댓글 (React, client:idle)
│   ├── common/Navbar.astro         # 네비게이션 (Astro)
│   └── common/Footer.astro         # 푸터 (Astro)
├── layouts/BaseLayout.astro        # 공통 레이아웃
├── lib/
│   ├── api.ts                      # fetch 래핑
│   ├── auth.ts                     # 인증 헬퍼
│   └── validation.ts               # Zod 스키마
├── styles/globals.css              # Tailwind + 글로벌
└── env.d.ts                        # 환경변수 타입
```

---

## 이 프로젝트 특수 패턴

### 1. Astro vs React 섬 분리

**규칙**
- `.astro` = 정적 콘텐츠, 레이아웃 (SSG/SSR 페이지)
- `.tsx` = 클라이언트 인터랙션만 (React 섬)

**지시어**
- `client:load` - 로그인, 결제, OAuth (페이지 로드 직후 필수)
- `client:idle` - 댓글, 하트, 후원 (유휴 시간에 수화)
- `client:visible` - 하단 위젯 (뷰포트 진입 시)

### 2. 쿠키 처리 (HttpOnly 기반)

**Astro 페이지 (SSG/SSR)**
```
로그인 상태: 쿠키 자동 포함
→ Astro.request.headers로 접근 가능
```

**React 섬 (클라이언트)**
```
결제/댓글: credentials: 'include' 명시
→ fetch 자동으로 HttpOnly 쿠키 전달
```

**localStorage 금지**
- JWT는 절대 localStorage에 저장 X
- 항상 HttpOnly 쿠키만 사용

### 3. 데이터 페칭 전략

**SSG (정적 생성)**
- 배포 사이에 변하지 않는 페이지에만 사용

**SSR (동적 렌더링, 선택적)**
- `export const prerender = false`로 명시
- admin에서 편집하는 작품·문구·커미션, 로그인 후 페이지에 사용
- 공개 조회 성공은 단기 HTTP 캐시를 적용하고 장애 응답과 최초 미저장 문구는 `no-store`로 둔다
- 구글 OAuth 콜백은 백엔드가 받으므로 프론트 SSR 콜백 페이지 없음(BFF)

**클라이언트 페칭 (React 섬)**
- 댓글, 하트 같은 실시간 데이터
- fetch 또는 필요하면 TanStack Query

### 4. 뷰어 (EpisodeViewer) 핵심 사항

**Signed URL만 사용**
- 백엔드에서 검증 후 발급
- 미결제 유저는 절대 이미지 URL 받으면 X

**진행도 저장 = 페이지 번호**
- % 기반은 이미지 크기 편차로 부정확
- 숫자 기반이 정확하고 DB 저장도 단순

**콘텐츠 보호**
- CSS `select-none` + `onContextMenu 차단` + `onDragStart 차단`
- 완벽 차단 아님 (UX 우선), 기본 차단만

---

## 절대 금지

❌ **localStorage에 JWT** - HttpOnly 쿠키만

❌ **클라이언트에서 결제 금액 조정** - imp_uid만 전달, 검증은 백엔드

❌ **미결제 유저에게 이미지 URL 노출** - Signed URL 필수

❌ **Astro에서 SECRET_* 접근** - 빌드 타임에 HTML에 노출됨

❌ **React 섬 남용** - 정말 필요한 부분만 인터랙티브하게

❌ **fetch 대신 xmlHttpRequest** - 표준 API 사용

---

## 코드 리뷰

커밋 전 Opus 4.8 검증: `@docs/reviews/CODE_REVIEW_FE.md` (+ 원칙은 `@docs/reviews/GUIDE_REVIEW.md`)
