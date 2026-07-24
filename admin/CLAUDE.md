# Admin - Vite React SPA 관리자 페이지

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
│   ├── api.gen.ts               # openapi-typescript 생성물 - 손으로 고치지 말 것.
│   │                            #   백엔드 스키마 변경 후 `pnpm --filter admin generate:types`로 재생성
│   └── index.ts                 # api.gen.ts 위 별칭 레이어 (UserRead 등 짧은 이름 재수출)
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

**파일 업로드 흐름** (D3 확정 계약 - presigned PUT 미사용, 백엔드 경유 변환)
```
1. 이미지 드래그 → 클라이언트에서 미리보기·순서 조정 (아직 전송 안 함)
2. POST /admin/works/{workId}/episodes          (JSON 메타 → draft 생성, is_published=false)
   → 회차번호 중복(409)이 업로드 전에 즉시 걸린다
3. 각 이미지 → POST .../episodes/{id}/images    (multipart 단건, 장당 1요청)
   → 백엔드가 800px WebP 변환 후 R2 업로드 + image_keys에 원자 append
4. PUT .../episodes/{id}                        (순서 재배열 · 썸네일 선택 · 공개/예약 전환)
5. 성공 → 목록으로 리다이렉트
```
⚠️ **클라이언트가 R2로 직접 올리지 않는다** (M1.5 결정 1: 서버가 바이트를 봐야 변환·규격 보장 가능).
⚠️ **순수 메타 수정 PUT에 `is_published`를 에코하지 말 것** - `false`가 실리면 서버가 `published_at`을
무조건 NULL로 밀어 미래 예약이 조용히 풀린다. 예약 설정은 `published_at`만 전송(E1 인계 계약).
⚠️ **공개 회차의 임시저장은 `content`가 아니라 `draft` 봉투(`{title, subtitle, content}`)를 PUT** (#86).
공개 회차에 `is_published` 없이 `content`를 보내면 서버가 409로 거부한다(발행본은 발행 액션만 덮는다).
수정 반영 = `content` + `is_published: true` (서버가 남은 draft를 소진). draft와 content 동시 전송은 422.

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

❌ **로그인 상태를 localStorage에 저장** - HttpOnly 쿠키만

❌ **클라이언트에서 권한 확인** - 라우트 가드 + 백엔드 API 검증

❌ **이미지 업로드 후 URL 신뢰** - 항상 백엔드에서 검증

❌ **2FA 토큰 노출** - TOTP는 메모리에서만, 저장 금지

❌ **환불/삭제 버튼 무조건 활성화** - 백엔드 상태 확인 후 가능/불가 표시

❌ **API 에러를 무시** - 항상 try-catch + 사용자에게 알림

---

## 테스트 (M1.5 F1 도입)

```bash
pnpm --filter admin test    # vitest run (jsdom + @testing-library/react)
```

- 설정은 `vitest.config.ts`(vite.config.ts와 분리 - 테스트에 tanstackRouter 플러그인이 불필요하고, 실행마다 `routeTree.gen.ts`를 다시 쓰는 부작용을 피한다)
- 라우트 가드는 라우터를 띄우지 않고 `Route.options.beforeLoad`를 직접 호출해 검증한다 (`src/routes/_auth.test.tsx` 참조)
- `api` 모듈을 `vi.mock`으로 갈아끼우고 `QueryClient`를 테스트마다 새로 만든다

## 코드 리뷰

커밋 전 Opus 4.8 검증: `@docs/CODE_REVIEW_ADMIN.md` 참조
