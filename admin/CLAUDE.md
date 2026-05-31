# Admin — Vite React SPA 관리자 페이지

## 스택 결정 (왜?)

| 항목 | 선택 | 이유 |
|------|------|------|
| 프레임워크 | Vite + React | SPA (SEO 불필요), 동적 화면 중심. 번들 빠름. |
| 라우팅 | TanStack Router | 타입 안전, 라우트 가드 (관리자 인증) 쉬움. |
| 상태관리 | TanStack Query | API 캐싱/로딩/에러 자동 처리. Zustand 불필요. |
| 폼 | react-hook-form + Zod | 타입 안전, 검증 간단. 이미지 업로드도 폼으로. |
| 스타일 | Tailwind | 프론트와 동일, 일관성. |
| 페칭 | fetch | TanStack Query가 관리, 래핑만. |

---

## 프로젝트 구조

```
admin/src/
├── routes/                       # TanStack Router 파일 기반
│   ├── __root.tsx               # 루트 레이아웃 (Navbar, 사이드바)
│   ├── login.tsx                # /login (2FA까지)
│   ├── dashboard.tsx            # / (로그인 필수)
│   ├── episodes/
│   │   ├── index.tsx            # /episodes (목록)
│   │   └── upload.tsx           # /episodes/upload (폼)
│   ├── analytics.tsx            # /analytics (수익, 통계)
│   ├── community/
│   │   ├── comments.tsx         # /community/comments (신고 목록)
│   │   └── refunds.tsx          # /community/refunds (환불)
│   └── _404.tsx
├── components/
│   ├── auth/
│   │   ├── LoginForm.tsx        # 이메일/비번 입력
│   │   └── TotpInput.tsx        # 2FA 코드 입력
│   ├── episodes/
│   │   ├── UploadForm.tsx       # 에피소드 등록 폼
│   │   ├── ImageUploader.tsx    # Drag-drop 이미지 업로드
│   │   └── EpisodeList.tsx      # 에피소드 목록 테이블
│   ├── dashboard/
│   │   ├── SalesChart.tsx       # 매출 차트
│   │   ├── Stats.tsx            # KPI 카드
│   │   └── RecentActivity.tsx   # 최근 활동
│   ├── community/
│   │   ├── CommentReport.tsx    # 신고된 댓글 테이블
│   │   └── RefundTable.tsx      # 환불 요청 테이블
│   ├── layout/
│   │   ├── Navbar.tsx           # 상단 네비
│   │   ├── Sidebar.tsx          # 좌측 메뉴
│   │   └── ProtectedLayout.tsx  # 로그인 필수 래퍼
│   └── common/
│       ├── Modal.tsx            # 확인 모달
│       ├── Loading.tsx          # 로딩 스피너
│       └── ErrorAlert.tsx       # 에러 메시지
├── hooks/
│   ├── useAuth.ts              # 로그인/로그아웃, TOTP 입력 (메모리에서만 임시, localStorage X)
│   ├── useEpisodes.ts          # GET/POST 에피소드 (TanStack Query)
│   ├── useSales.ts             # 매출 통계
│   ├── useComments.ts          # 신고된 댓글
│   └── useRefunds.ts           # 환불 처리
├── lib/
│   ├── api.ts                  # fetch 래핑 + 에러 처리
│   ├── validation.ts           # Zod 스키마 (폼)
│   └── auth.ts                 # HttpOnly 쿠키 유효성 확인 (⚠️ TOTP 저장 금지, 메모리만)
├── types/
│   └── index.ts                # API 응답 타입 (openapi-typescript)
├── main.tsx
└── index.css                   # Tailwind
```

---

## 이 프로젝트 특수 패턴

### 1. 관리자 인증 (라우트 가드)

**로그인 필수**
```
TanStack Router beforeLoad에서
→ 토큰 없으면 /login으로 리다이렉트
→ 토큰 있으면 진행
```

**2FA (TOTP) 검증**
```
로그인 폼 제출 후
→ 이메일/비번 검증 (백엔드)
→ 2FA 코드 입력 화면 (TotpInput.tsx)
→ TOTP 코드 제출 (백엔드 검증)
→ 최종 토큰 발급
```

**토큰 저장**
- 클라이언트: HttpOnly 쿠키 (백엔드가 자동 설정)
- 상태: 필요하면 Context (로그인 상태 표시)

### 2. 에피소드 업로드 (핵심)

**폼 + 다중 이미지**
- react-hook-form으로 메타데이터 (제목, 공개일시 등)
- ImageUploader는 별도 컴포넌트 (drag-drop)
- 이미지는 섹션별로 관리

**파일 업로드 흐름**
```
1. 이미지 드래그 → FormData에 추가
2. 각 이미지 → presigned PUT 요청 (R2)
3. 메타데이터 + 이미지 순서 → POST /episodes (백엔드)
4. 성공 → 목록으로 리다이렉트
```

**예약 공개**
```
공개일시 지정 → published=false로 저장
→ 백엔드 스케줄러가 시간 도달 시 published=true
```

### 3. TanStack Query 사용 패턴

**API 호출 → hooks로 정의**
```
useEpisodes() → {data, isLoading, error}
useSales() → {data, isLoading}
```

**백그라운드 새로고침**
```
staleTime 설정 → 일정 시간 후 자동 refetch
```

**낙관적 업데이트**
```
환불 승인 클릭 → 즉시 UI 업데이트
→ 백엔드 응답 후 재확인
```

### 4. 대시보드 (Analytics)

**데이터**
- 일/주/월 매출 (차트)
- 작품별 매출
- 결제 수단별 매출
- 가입자, MAU, 환불율

**캐싱 전략**
- 일일 통계는 staleTime 1시간 (자주 변하지 않음)
- 실시간 통계는 항상 refetch

### 5. 신고 & 환불 관리

**신고된 댓글**
```
목록 조회 → 삭제/유지 선택 → POST /comments/[id]/review
```

**환불 요청**
```
대기중 목록 → 승인/거부 → 포트원 cancel API (백엔드 경유)
```

---

## 절대 금지

❌ **로그인 상태를 localStorage에 저장** — HttpOnly 쿠키만

❌ **클라이언트에서 권한 확인** — 라우트 가드 + 백엔드 API 검증

❌ **이미지 업로드 후 URL 신뢰** — 항상 백엔드에서 검증

❌ **2FA 토큰 노출** — TOTP는 메모리에서만, 저장 금지

❌ **환불/삭제 버튼 무조건 활성화** — 백엔드 상태 확인 후 가능/불가 표시

❌ **API 에러를 무시** — 항상 try-catch + 사용자에게 알림

---

## 코드 리뷰

커밋 전 Opus 4.8 검증: `@docs/CODE_REVIEW_ADMIN.md` 참조
