# 관리자 로그인 + TOTP 2FA 화면 (M1.5 그룹 F - F1)

| 항목 | 내용 |
|------|------|
| 모듈 | Admin / Auth |
| 관련 마일스톤 | [M1.5](../../../milestones/M1.5_foundation.md) 그룹 F - F1 (ADM-01 프런트) |
| 작성 시점 | M1.5 F1 (2026-07-14) |
| 상태 | 구현 + 수동 e2e(QR 등록 → 대시보드 진입 확인) + Opus 코드 리뷰(/code-review xhigh, **13건 발견 전부 수정**). `pnpm --filter admin test` 18 passed(신규), build·lint 클린. **백엔드 변경 0** |
| 관련 문서 | `TROUBLESHOOTING_TOTP_QR_STUCK_PENDING.md`(QR 영구 정지 - 진단 경로 포함), B2·B3 백엔드 계약(PR #58), M1.5_foundation.md F1, MISTAKES.md "TanStack Query" |

B2/B3에서 완성된 관리자 인증 API를 소비하는 첫 프런트 화면. 백엔드는 한 줄도 건드리지 않았다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `admin/src/routes/login.tsx` | 신설. stage 상태머신(credentials → totp \| totp_setup) + pending 만료 복구 + 로그인된 owner의 재진입 차단 |
| `admin/src/routes/_auth.tsx` | 신설. pathless 레이아웃 가드(`beforeLoad` → `/auth/me` → role 확인) |
| `admin/src/routes/_auth/index.tsx` | 기존 `routes/index.tsx` 이동. 대시보드 placeholder(닉네임 + 로그아웃) |
| `admin/src/components/auth/{LoginForm,TotpInput,TotpEnroll}.tsx` | 신설. RHF + Zod 폼, QR(qrcode.react) 등록 |
| `admin/src/hooks/useAuth.ts` | 신설. me 쿼리 + login/loginTotp/setup/confirm/logout |
| `admin/src/lib/api.ts` | `describeAuthError`·`isSessionExpired` 추가, **환경변수명 정정**(아래 §2) |
| `admin/src/lib/validation.ts` | 신설. TOTP 코드 스키마(이메일/비번은 shared `loginSchema` 재사용) |
| `admin/src/types/index.ts` | 신설. 백엔드 응답 타입 **수기 미러링**(openapi-typescript 도입은 F2 전으로 이연) |
| `admin/src/main.tsx`·`__root.tsx` | QueryClientProvider 배선 + `createRootRouteWithContext`(가드가 queryClient를 쓰기 위함) |
| `packages/shared/src/lib/api.ts` | `extractDetail` 이관(frontend와 중복 제거), zod → peerDependency |
| `admin/vitest.config.ts`·`src/**/*.test.*` | **admin 최초 테스트 인프라**(vitest + jsdom + testing-library), 18개 |

새 의존성: `@tanstack/react-query@5.101.2`, `react-hook-form@7.81.0`, `@hookform/resolvers@5.4.0`, `qrcode.react@4.2.0`, `zod@4.4.3` (+ dev: vitest·jsdom·testing-library).

---

## 2. 주요 결정

### 가드는 `__root`가 아니라 pathless 레이아웃 `_auth.tsx`에
마일스톤 문구는 "`__root.tsx` 가드"였으나 `/login`도 `__root` 아래라 리다이렉트 루프 예외를
따로 파야 한다. TanStack Router 표준(공식 문서 authenticated-routes)대로 `_auth.tsx`에
`beforeLoad`를 두고 보호 라우트를 그 아래에 넣었다. `/login`은 `_auth` 밖이라 루프가 구조적으로 불가능.

### 가드는 `ensureQueryData`가 아니라 `fetchQuery` (코드 리뷰 Critical)
`ensureQueryData`는 **캐시가 있으면 staleTime과 무관하게 그 값을 그대로 반환**한다
(query-core `queryClient.js`: `if (cachedData !== undefined) return Promise.resolve(cachedData)`).
즉 만료·강등된 세션이 캐시만으로 가드를 영구 통과한다. `fetchQuery`는 `isStaleByTime`을
확인하므로 `staleTime: 0`과 함께 쓰면 라우트 진입마다 서버에 세션을 되묻는다.

### 로그아웃은 `queryClient.clear()` (코드 리뷰 Critical)
`setQueryData(key, undefined)`는 캐시를 지우지 않는다 - TanStack이 undefined를
"업데이트 안 함" 신호로 보고 bail-out하는 **no-op**이다(`if (data === void 0) return void 0`).
이걸 모르고 쓰면 로그아웃 후에도 유저가 캐시에 남아 뒤로가기 시 가드가 통과한다(실측 재현).
`clear()`는 남은 TOTP 시크릿(QR) 캐시까지 함께 폐기해 두 문제를 한 번에 닫는다.

### TOTP setup은 mutation이 아니라 **query** (e2e에서 실증된 함정)
> 진단 과정 전문: `TROUBLESHOOTING_TOTP_QR_STUCK_PENDING.md`

"마운트 시 QR을 받아 표시"를 `useEffect` + `mutate()`로 구현하면 StrictMode의
mount→cleanup→mount에서 observer가 mutation과 분리돼 **성공 알림이 유실**된다
(TanStack/query#8512) - 요청은 200으로 성공하는데 화면은 "생성 중"에 영구히 멈춘다.
중복 방지용 ref 가드는 "두 번째 mutate가 우연히 상태를 풀어주는" 경로까지 막아 오히려
멈춤을 고정시켰다. 시맨틱상으로도 이건 조회라 `useQuery`가 맞다(재구독·dedupe 정상 처리).
`staleTime: Infinity`로 포커스 복귀 시 시크릿 재발급을 막는다.

### 환경변수명 정정: `VITE_API_BASE_URL` → `VITE_API_URL` (코드 리뷰 Critical)
`.env`/`.env.example`이 정의한 이름은 `VITE_API_URL`인데 코드는 `VITE_API_BASE_URL`을
읽고 있었다(스캐폴드 시점부터의 잠복 버그). dev에서는 하드코딩 폴백이 우연히 실제 주소와
같아 안 드러나지만, **프로덕션 빌드에선 관리자 SPA가 사용자 브라우저의 localhost를 호출**하게 된다.
F1이 admin의 첫 실제 API 호출을 도입하면서 활성화됐다.

### 로컬 `Stage`에 백엔드의 `complete`를 넣지 않는다
백엔드 `stage`는 "다음에 뭘 할지"(totp/totp_setup/complete), 프런트 `Stage`는 "뭘 그릴지"
(credentials/totp/totp_setup)라 값 집합이 일치하지 않는다. `complete`(신뢰 기기 → 이미 쿠키
발급됨)는 렌더 대상이 아니라 즉시 이탈 신호이므로 조기 분기 후 navigate한다. 이 분기가
타입 좁히기 역할도 해 `setStage(res.stage)`가 캐스팅 없이 통과한다.

### pending 쿠키(10분) 만료 복구
1→2단계 운반 쿠키가 만료되면 코드 제출이 401이 된다. 에러 문구만 띄우면 사용자는 통과할 수
없는 폼에 갇힌다(새로고침 외 탈출구 없음) → `isSessionExpired`(401)면 stage를 credentials로
되돌리고 안내한다. TotpEnroll의 setup 401도 같은 경로로 복구.

---

## 3. 백엔드 계약(변경 없음, 소비만)

| 엔드포인트 | 요청 | 응답 |
|---|---|---|
| `POST /admin/login` | `{email, password}` | `{stage: totp \| totp_setup \| complete}` (실패 generic 401) |
| `POST /admin/2fa/setup` | - | `{otpauth_uri}` (시크릿 원문은 이 URI 안에만) |
| `POST /admin/2fa/confirm` | `{code, remember_device}` | `UserRead` (성공 시 즉시 세션) |
| `POST /admin/login/totp` | `{code, remember_device}` | `UserRead` |
| `GET /auth/me` | - | `UserRead`(role 포함, 가드용) |
| `POST /auth/logout` | - | `MessageResponse` |

전부 5회/분 rate limit(429 detail에 완결 문구). 401/400/429 모두 detail에 한국어 메시지가
실려 오므로 `describeAuthError`는 detail을 그대로 신뢰하고, **ApiError가 아닌 실패**(fetch가
TypeError로 reject하는 네트워크 장애·CORS 차단)만 별도 문구로 구분한다.

---

## 4. 리뷰

**코드 리뷰**(Opus, /code-review xhigh): **13건 발견 → 전부 수정**.
- Critical 3: 로그아웃 캐시 no-op / 가드의 무기한 캐시 재사용 / 환경변수명 불일치 (위 §2)
- Major~Minor 10: 로그아웃 실패 무알림(admin/CLAUDE.md "API 에러 무시 금지" 위반), pending
  만료 시 갇힘, TOTP 시크릿 캐시 잔류, `extractDetail` frontend와 중복(→shared 이관),
  네트워크 에러 타입 거짓말(`describeAuthError(unknown)` + instanceof), 세션 만료 시 대시보드
  잔류(useMe 에러 → /login), 로그인된 owner에게 /login 재노출, 수기 타입 경고, zod peerDep화

**테스트 유효성 검증**: 수정을 되돌리면 해당 테스트가 실제로 실패함을 확인했다
(logout 캐시 2건, 가드 만료세션 1건). 통과만 시키는 테스트가 아님을 실측.

---

## 5. 이연 / 후속

| 항목 | 이동처 |
|------|--------|
| `openapi-typescript` codegen 도입(현재 `types/index.ts`는 수기 미러링 - 백엔드 스키마 변경 시 컴파일러가 못 잡음) | F2 착수 전 |
| 401 자동 refresh 재시도(access 15분 만료 시 재로그인 필요) | 이슈 #67 |
| 독자 로그인 폼에 "관리자 로그인" 링크(owner는 독자 폼으로 로그인 불가 - 비열거 401이라 혼란) | 선택, frontend 작업 |
| Sidebar·Navbar 레이아웃(화면이 2개뿐이라 아직 네비게이션 대상이 없음) | F2 |
| 대시보드 실내용(현재 닉네임 + 로그아웃 버튼뿐인 placeholder) | F2~F4 |

## 6. 참고: owner 세션은 독자 사이트에서도 유효하다

백엔드가 막는 것은 **owner 세션의 *발급* 경로**뿐이다(`requires_totp_login` - 독자 로그인·구글
OAuth 둘 다 owner면 generic 401). 발급된 세션 자체는 독자 사이트에서도 정상 동작한다:
인증 쿠키는 API 호스트 앞으로 하나만 발급되고 독자·관리자 사이트가 같은 API를 호출하며
same-site라 쿠키가 실린다(실측: 독자 origin에서 `/auth/me` 200 + `role: owner`).
즉 **계정 하나, 로그인 한 번**(관리자 사이트 TOTP)이면 양쪽 다 로그인 상태다.
