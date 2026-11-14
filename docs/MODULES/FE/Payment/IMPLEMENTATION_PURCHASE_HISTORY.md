# M3 F 구매 내역 화면

## 범위

`/my/purchases`는 로그인한 독자의 현재 결제 환경 구매 내역을 표시한다. Astro는 `prerender = false`와 `Cache-Control: no-store`, `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex`를 적용한 개인 정보 없는 셸을 렌더하고 React `PurchaseHistory`가 클라이언트에서 목록을 조회한다. SSR에서 계정·구매 API를 요청하거나 쿠키·개인 query를 HTML에 넣지 않는다.

## 카드 표시와 이동

카드에는 작품명·구매 당시 회차명·공개 파생 썸네일을 표시하며 내부 `order_name`은 DOM에 넣지 않는다. 회차 썸네일이 없으면 작품 표지, 둘 다 없거나 이미지가 실패하면 placeholder를 표시한다. BE는 nullable `work_title`·`thumbnail_url`만 추가했고 원고 키나 서명 URL은 반환하지 않는다. 목록 API는 기존 두 SELECT 제한을 유지한다.

2026-11-14 사용자 요청으로 기존 상태 배지 위치에는 서버 결제 금액을 표시한다. 카드 하단의 접힌 `결제 정보` 영역을 없애고 같은 위치에 서울 시간대 결제 일시를 회색 `time` 요소로 표시한다. 상태·첫 열람·환불 금액·환불 일시는 화면에서 제거하며 API 계약과 권한 판정에는 그대로 둔다. 안전한 영수증 링크는 유지한다.

열람 링크는 서버의 `viewer_path`가 활성 구매이며 `/works/{work_id}/{public_id}` 허용 형식일 때만 제공한다. 비활성 구매나 null·unsafe 경로는 카드 링크로 만들지 않는다. 상태 문구를 숨겨도 환불·삭제 회차 권한을 열지 않는다. 링크 진입 후 기존 뷰어가 서버에서 다시 인가한다. `data-astro-reload`로 회차 상태 경계를 유지한다. 영수증은 HTTPS·사용자 정보 없는 안전한 URL에만 `target="_blank" rel="noopener noreferrer"`를 적용한다.

## 조회와 오류 처리

`getPurchaseHistory`는 공용 API wrapper와 `cache: no-store`를 사용한다. 인증된 브라우저 요청은 쿠키를 포함하며 최종 401은 로그인 안내, refresh 503·네트워크 장애는 일시 오류와 명시적인 재시도로 구분한다. 응답 원문이나 내부 네트워크 오류를 노출하지 않는다.

page는 1부터 2,147,483,647까지의 정수만 허용한다. 페이지 크기는 서버의 20개를 사용하며 이전·다음 경계는 서버 total과 page로 판단한다. 빈 첫 페이지와 깊은 빈 페이지를 구분하고 범위 밖 페이지를 임의로 첫 페이지로 바꾸지 않는다. 페이지 이동·재시도 중 이전 목록을 숨기고 이탈·교체된 요청의 늦은 성공과 실패를 무시한다. 단일 페이지 조회 뒤 page 상태 갱신으로 중복 GET을 만들지 않는다.

## 공통 계정 메뉴

일반 Navbar와 뷰어는 `AccountMenu`를 공유한다. 닉네임 클릭으로 마이페이지·구매내역·설정·로그아웃에 진입하며 shadcn/ui Base UI 예제를 참고한 `@base-ui/react@1.9.0` 메뉴의 포털·키보드·포커스 동작을 사용한다. 메뉴 hover는 회색 배경, 로그아웃·실제 삭제는 빨간 글씨를 사용한다. 닉네임 title 툴팁은 제거하고 접근성 이름은 유지한다.

구매 내역 상단의 마이페이지 링크와 마이페이지의 중복 구매·설정·로그아웃 영역은 제거했다. 설정은 인증된 `/my/settings`로 기존 알림 준비 안내를 옮긴 상태다. 비밀번호·닉네임·이미지 편집은 추가하지 않았다.

2026-11-13 메뉴 통합 중 pre-paint 보정을 제거해 생긴 로그인 라벨 깜빡임은 2026-11-14 보완했다. `AccountMenuEntry.astro`의 client-only fallback만 인라인 스크립트로 보정하고 실제 React 메뉴는 layout effect로 이어받는다. 서버 HTML에 개인 닉네임을 넣거나 React 소유 DOM을 외부 스크립트로 수정하지 않는다. 포커스 복귀·뷰어 표시 변경 때 힌트를 갱신한다. 전체 사이트 SPA 전환이나 회차 이동 초기화 제거는 하지 않았다.

## 검증 기록

- 2026-11-13 구매 메타데이터 추가: Backend Ruff format 116 files·Ruff check·1,152 tests, Admin 타입 생성·lint·119 tests·build 통과. 모델·migration·삭제 정책 변경 없음.
- 2026-11-14 메뉴 초기 표시 보완: Frontend lint·Astro check(91 files, 오류·경고 0, 기존 hint 1)·267 tests·production build 통과. Admin lint·119 tests·build 통과.
- SSR/DOM 12 tests는 공개 캐시·비공개 셸·구매 내역 SSR 요청 0·설정 인증·장애 구분을 확인한다. 실제 fallback 스크립트를 DOM에서 실행해 한글·HTML 형태 닉네임·잘못된 인코딩과 서버 개인 정보 미노출을 확인했다. 키보드 탐색·Escape 포커스 복원·바깥 클릭·뷰어 숨김·로그아웃 API 호출은 컴포넌트 테스트로 확인한다.
- 기존 Sentry token 미설정·Astro transitions sourcemap 빌드 경고와 무관 unused import hint는 유지한다.

브라우저 페인트·모바일 조작·실제 외부 결제·영수증 열기는 사용자 확인 대상이며 자동 검증으로 수행했다고 간주하지 않는다.

## 후속 작업과 개발 캐시

내 서재·결제 내역 별도 화면, 숨기기·복원, 작가 삭제 후 구매 원고 보존·소장본 열람과 프로필 편집은 [M3 후속 합의](../../../milestones/M3_foundation.md#구매-내역계정-후속-합의-2026-11-13-구현-보류)에 남긴다. 기존 삭제 차단과 삭제 콘텐츠 열람 차단은 유지한다.

localhost:4321의 `504 Outdated Optimize Dep`는 개발 서버 정상 종료·기존 최적화 캐시 백업·재시작으로 정리했다. 실제 변환된 뷰어 모듈의 TipTap 의존성 URL이 모두 200임을 확인했다. 데모 config에는 별도 Vite cacheDir을 지정했고 열린 브라우저의 이전 청크는 강력 새로고침으로 교체한다.

## 근거

- [BE 구매 내역 계약](../../BE/Payment/IMPLEMENTATION_PURCHASE_HISTORY.md)
- [뷰어 계정 이동 구현](../Viewer/IMPLEMENTATION_VIEWER_ISLAND.md)
- [공통 UI와 로그인 표시 결정](../../../DECISIONS.md)
