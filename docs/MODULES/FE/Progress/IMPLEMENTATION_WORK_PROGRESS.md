# 작품 단위 진행도 (M2 그룹 E4 FE)

| 항목 | 내용 |
|------|------|
| 모듈 | Frontend / Progress (작품 상세 개인화 섬) |
| 관련 마일스톤 | [M2](../../../milestones/M2_foundation.md) 그룹 E4 |
| 작성 시점 | M2 E4 FE (2026-08-12), 비로그인 로컬 진행도 확장 (2026-08-18) |
| 상태 | 로그인 서버 + 비로그인 기기 로컬 진행도 구현·자동 검증·사용자 브라우저 확인 완료 |
| 관련 문서 | DECISIONS "독자 회차 목록 UX: 날짜·정렬·진행률", BE Viewer `IMPLEMENTATION_VIEWER_PROGRESS.md` |

독자는 첫 방문에 첫 화 CTA를 보고, 로그인 진행도가 있으면 다음 화 CTA, 비로그인 로컬 기록이 있으면 가장 최근에 연 공개 회차의 이어 보기 CTA와 작품 진행률을 본다. 개인 진행도는 공개 캐시 HTML과 분리된 React 섬이 hydration 뒤 조회한다.

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `frontend/src/lib/workProgress.ts` | BE 계약 타입, 401 처리, 비율 clamp, 첫 화·다음 화·완독 CTA 선택 |
| `frontend/src/lib/workProgress.test.ts` | 계약 오류, 비율, 첫 방문·다음 화·완독·stale SSR 테스트 |
| `frontend/src/lib/guestProgress.ts`, `guestProgress.test.ts` | 비로그인 localStorage 계약, 공개 회차 교집합·최근 회차 선택, 손상·예외·100개 정리 테스트 |
| `frontend/src/components/works/WorkProgress.tsx` | `client:idle` 개인화 섬, 본문 진행률 바, 화면 하단 고정형 2단 CTA |
| `frontend/src/components/works/WorkProgress.test.tsx` | 공개 첫 화 SSR, 비로그인, 401, 빈 진행도, 다음 화 링크, unmount 경쟁 테스트 |
| `frontend/src/pages/works/[id].astro`, `layouts/BaseLayout.astro` | 공개 회차 props 전달 + Footer 뒤 실제 문서 최하단 예약 공간 opt-in |

신규 dependency와 DB migration은 없다.

## 2. 캐시와 인증 경계

작품 상세 SSR은 성공 시 `public, max-age=60`이므로 개인 값을 Astro frontmatter에서 조회하지 않는다. `WorkProgress`에는 페이지에 이미 공개된 작품 ID와 회차 ID·공개 ID·제목만 props로 전달한다. 초기 SSR은 공개 첫 화 CTA만 렌더한다. hydration 뒤 `login_hint`가 있으면 `GET /works/{id}/progress`, 없으면 현재 공개 회차 ID로 localStorage를 조회한다. 따라서 서버 렌더 결과에는 서버·로컬 읽은 ID, 개인 진행률, 개인화된 CTA 선택이 없다.

`login_hint`는 저장소 선택과 요청 생략을 위한 표시 힌트일 뿐 인가 근거가 아니다. 실제 인증은 shared API가 `credentials: 'include'`로 보내는 HttpOnly 쿠키를 서버가 검증한다. 힌트가 남았지만 refresh까지 만료된 401은 로컬로 폴백하지 않고 부가 UI만 숨긴다. 404와 5xx도 0% 성공 상태로 바꾸지 않는다. 로그인 경로는 localStorage 접근 0회, 비로그인 경로는 진행도 API 호출 0회를 유지한다.

## 3. 공개 SSR과 개인 API의 시차

SSR 회차 목록은 최대 60초 캐시되고 개인 API는 no-store라 두 응답의 시점이 다를 수 있다. `summarizeWorkProgress`는 읽은 UUID 중복을 제거한 뒤 분자를 SSR의 전체 공개 회차 수로 clamp해 `읽은 수 > 전체 수`와 100% 초과를 막는다. 이는 표시 방어이며 서버의 공개 회차 필터를 대신하지 않는다.

## 4. 렌더 상태

- 비로그인 + 로컬 기록 없음: API 요청 없이 hydration 뒤 `0/N화`와 첫 화 CTA 표시
- 비로그인 + 로컬 기록 있음: 현재 공개 회차와 교집합인 읽은 수를 표시하고 `updatedAt`이 가장 최신인 공개 회차 자체를 `이어 보기`로 표시
- 로딩, 401, 보조 API 오류: 공개 첫 화 CTA로 폴백
- 로그인 + 진행도 0건: `0/N화`와 0% progressbar, 첫 화 CTA 표시
- 로그인 + 진행도 있음: 마지막으로 읽은 회차의 다음 회차에 `다음 화 보기`와 제목 표시
- 마지막 회차까지 읽음: `마지막 화 다시 보기`와 마지막 회차 제목 표시
- SSR 캐시에 마지막 읽은 회차가 없음: 개인 API의 회차로 `이어 보기` 폴백
- 전체 회차 0건: 작품 상세가 섬을 마운트하지 않음

진행률 바는 `role="progressbar"`와 `aria-valuemin`, `aria-valuemax`, `aria-valuenow`를 제공한다. 회차 내부 스크롤 퍼센트는 M3 범위라 포함하지 않는다.

## 5. 하단 고정 CTA와 예약 공간

CTA는 진행률 카드 내부가 아니라 viewport 하단에 `position: fixed`로 띄운다. 모바일 홈 인디케이터와 겹치지 않도록 하단 패딩에 `env(safe-area-inset-bottom)`을 더한다. `BaseLayout`은 opt-in된 작품 상세에서 Footer 뒤 실제 문서 최하단에 `calc(5rem + env(safe-area-inset-bottom))` 높이의 정상 흐름 공간을 둔다. 목록 안에 두면 Footer가 다시 버튼 아래로 들어가므로 반드시 Footer 뒤여야 한다. 이 공간으로 마지막 회차와 Footer까지 버튼 위로 스크롤할 수 있다.

고정 컨테이너는 `pointer-events-none`, 실제 링크만 `pointer-events-auto`로 두어 버튼 바깥의 화면 조작을 막지 않는다. CTA는 최대 너비를 제한해 데스크톱에서 지나치게 늘어나지 않게 한다.

## 6. 검증

- #117 집중 Vitest: guest storage + Viewer + WorkProgress 3 files, 39 tests 통과
- `pnpm --filter frontend astro check`: 0 errors, 0 warnings, 기존 hint 1건
- `pnpm --filter frontend lint`: 통과
- `pnpm --filter frontend test`: 11 files, 115 tests 통과
- `pnpm --filter frontend build`: 성공
- 자동 검증: React `renderToString` 초기 결과에는 공개 첫 화 CTA만 있고 서버·로컬 개인 진행도와 개인화된 선택은 없음을 단언
- 사용자 확인 완료(2026-08-18): 비로그인 저장·재진입과 최근 회차 이어 보기, 로그인 서버 경로, paywall 유지, storage 차단 환경이 정상 동작한다. 기존 긴 제목·모바일 safe-area·마지막 회차 비가림 확인 항목도 유지한다.

## 7. 비로그인 로컬 확장 (#117)

작품 상세는 SSR이 전달한 현재 공개 회차 ID만 localStorage 조회 대상으로 사용한다. 삭제·비공개·다른 작품 회차의 로컬 key가 남아 있어도 읽은 수와 CTA 대상에 포함되지 않는다. 같은 시각의 기록은 작가 지정 순서에서 뒤쪽 공개 회차를 선택해 결과를 결정적으로 유지한다.

비로그인 작품 진행률도 M2의 로그인 표시와 같은 임시 의미인 `열어 본 공개 회차 수 / 전체 공개 회차 수`다. M3가 전체 완독 판정을 추가하면 서버의 완료 회차 의미로 전환하지만, 조작 가능한 로컬 값은 구매·완독 상태로 승격하지 않는다. 로그인 전환 시 자동 병합과 기기 간 동기화도 이 범위에서 제외한다.

초기 `renderToString` 테스트는 localStorage 어댑터가 호출되지 않고 공개 첫 화 CTA만 포함됨을 단언한다. hydration 테스트는 비로그인 0%, 최근 회차 이어 보기와 로그인 localStorage 미접근을 고정한다.
