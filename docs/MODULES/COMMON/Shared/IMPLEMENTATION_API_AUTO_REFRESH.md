# IMPLEMENTATION - 공용 fetch 래퍼 401 자동 refresh (#67)

관련 이슈: #67 (401 자동 refresh 없음), #69 (자동 로그인 - #67로 함께 종결)
브랜치: `common/fix/api-401-auto-refresh`
관련 결정: `docs/DECISIONS.md` "세션 유지: 401 자동 refresh + 관리자 자동 로그인"

---

## Background / Context

- access 토큰은 15분 만료인데 `createApi`의 `request()`에 갱신 로직이 없어, 만료 후 첫 요청이 401로 그대로 실패했다. refresh 토큰(7일)이 있어도 활용되지 않아 실질 세션이 15분이었다.
- M1.5 E1 수동 e2e 중 이 문제를 "JWT_SECRET 불일치"로 오진한 삽질 기록이 발단(#67 본문).
- F3(에피소드 업로드 화면)는 준비·업로드에 15분을 쉽게 넘겨, 방치 시 업로드 도중 401로 작업물이 깨지는 직접 피해가 예상돼 F3 전에 처리했다.

## Decision

### 401 → refresh 1회 → 원요청 재시도 (packages/shared/src/lib/api.ts)

- 기존 `request()`를 `rawRequest()`로 두고, `createApi` 클로저 안의 새 `request()`가 401을 잡아 `POST /auth/refresh` 후 원요청을 **딱 1회** 재시도한다. 재시도가 또 401이면 그대로 전파(무한루프 없음).
- **in-flight 공유**: 클로저의 `refreshPromise` 하나를 공유해 동시 401에도 refresh는 1회만 나간다. settle 후 `finally`에서 null로 되돌린다 - 안 되돌리면 settle된 promise가 캐시로 남아 다음 만료 때 서버 호출 없이 stale 결과를 돌려줘 자동 갱신이 죽는다.
- **refresh 실패 시 원요청의 401을 전파**: refresh의 에러가 아니라 원래 `ApiError`를 던져 각 앱 인증 가드의 기존 계약(401 → 로그인 화면)이 그대로 유지된다.
- **재시도 제외 경로** `NO_RETRY_PREFIXES`: `/auth/refresh`(자기 자신), `/auth/login`, `/admin/login`, `/admin/2fa`. 이 경로의 401은 만료가 아니라 자격 증명 거부·pending 만료라는 의미고, 자동 재시도하면 틀린 비밀번호·TOTP를 재전송하게 된다.

### Web Locks로 탭 간 refresh 직렬화

- `refreshPromise` 공유는 탭 하나 안에서만 유효하다(탭마다 JS 컨텍스트 별개). 두 탭이 동시에 같은 refresh 토큰(쿠키는 브라우저 공유)을 제출하면, 백엔드 `rotate_refresh`의 재사용 탐지가 이를 탈취로 오분류해 **전 세션 revoke**(`revoke_all`)할 수 있다 - 커밋 전 리뷰에서 Major로 발견.
- `navigator.locks.request('dweb-auth-refresh', ...)`로 같은 오리진의 탭 간 직렬화. 락을 기다린 탭은 앞 탭이 회전해 둔 새 쿠키로 갱신하므로 성공한다(회전이 한 번 더 일어날 뿐).
- MDN 확인(2026-07-15): 2022-03부터 widely available, 콜백(async)이 끝나야 락 해제, secure context 필수(**localhost 포함**). 미지원 환경은 직접 호출 폴백 = 기존 동작(악화 없음).

### owner도 `/auth/refresh` 사용 (백엔드 변경 0)

- B3 "owner 세션 발급 지점 봉쇄"의 불변식은 **발급**에 대한 것이고, refresh는 TOTP로 열린 세션의 **연장**이다. owner의 refresh 토큰은 TOTP 경로에서만 생기므로 refresh 성공 자체가 TOTP 통과의 증명 - `rotate_refresh`에 role 체크가 없는 것은 버그가 아니라 의도다(막으면 관리자만 15분마다 재로그인). 절대 cap 30일이 재인증을 강제한다.

### 테스트는 admin 패키지에

- shared엔 vitest가 없고, shared 코드 테스트를 `admin/src/lib/api.test.ts`에 두던 선례를 따라 `admin/src/lib/api.refresh.test.ts`에 6케이스 배치(신규 인프라 0).

## Caution

- **새 로그인/2FA 경로를 추가하면 `NO_RETRY_PREFIXES`에도 추가할 것** (예: M2 카카오 OAuth 콜백). 빠뜨리면 로그인 실패 401에 자격 증명이 자동 재전송된다.
- **API를 경로 프리픽스 뒤로 프록시하지 말 것**: refresh 쿠키가 `Path=/auth/refresh`라, API를 `도메인/api/...`처럼 프리픽스 뒤에 두면 쿠키 Path와 호출 URL이 어긋나 refresh에 쿠키가 안 실린다. 현 구조(api 서브도메인 직결)에선 일치.
- Web Locks는 secure context 전용이라 http LAN 접속 같은 환경에선 폴백으로 떨어져 멀티탭 race가 이론상 남는다. dev(localhost)·운영(https)은 모두 커버.
- Astro **빌드 타임** fetch가 401을 받으면 쿠키 없는 node 환경에서 refresh를 1회 헛시도한다. 실패 후 원 401 전파라 동작은 정확, 비용은 빌드당 요청 1개 수준.

## Test Plan

- [x] `pnpm --filter admin test` 30 passed (신규 6: 재시도 성공+body 재직렬화 / 동시 401 refresh 1회 / refresh 실패 원401 전파·재시도 없음 / 로그인 경로 제외 / 재401 전파·2회 재시도 없음 / 탭 간 락 직렬화)
- [x] 직렬화 테스트는 락을 임시 우회해 **실제로 실패함**을 확인 후 복구
- [x] `pnpm --filter admin lint` / `build`, `pnpm --filter frontend build` 그린
- [ ] 수동(사용자): dev 로그인 후 access 쿠키만 삭제 → 관리자 조작이 로그아웃 없이 이어지는지 + devtools Network에서 `/auth/refresh` 요청에 refresh 쿠키 실림 확인
