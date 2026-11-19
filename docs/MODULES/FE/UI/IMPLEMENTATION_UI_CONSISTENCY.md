# U1 독자 공통 UI 통일

## 목표와 범위

2026-11-15 후속 UI 목표 U1. shadcn/ui Base UI의 버튼·페이지네이션 구조를 참고하고 기존 ink·hover·control 토큰을 사용한다. 추가 의존성, API·DB·인증·가격·권한 변경은 없다.

## 구현

- `controlStyles.ts`에 버튼 공통 상태, ghost, 페이지 목록·현재 페이지 스타일을 둔다. Astro와 React가 같은 문자열을 재사용한다.
- 최소 44px 대상, 둥근 모서리, 회색 ghost hover, 키보드 focus-visible, 비활성 상태를 통일한다. primary/secondary의 채움·외곽선 의미는 유지한다.
- `Button.astro`의 ghost를 밑줄에서 회색 배경으로 바꾸고 disabled href는 탐색·포커스 대상 링크로 만들지 않는다.
- 작품 목록과 구매내역은 nav > ul > li, 현재 페이지 aria-current·테두리, 이전/다음 ghost 컨트롤을 사용한다. 작품은 SSR 링크·태그·페이지 URL을, 구매내역은 controlled 버튼·기존 쿼리/해시·깊은 빈 페이지·MAX_PAGE 상한을 유지한다.
- 구매내역 로그인·재시도·영수증, 뷰어 재시도, 결제 복귀·상태 재확인·재시도와 이메일 인증 이동의 동작형 요소에도 같은 스타일을 적용한다. 영수증과 새 창 로그인 링크의 target·rel, 인증 요청과 상태 전이는 보존한다.
- 공개 SSR 뷰어의 본문 끝 이전·다음 링크에도 남아 있던 밑줄 hover를 제거한다. 기존 client-only fallback과 회차 전체 이동·상태 초기화 경계는 유지한다.
- 인증 제출·이메일 인증·구글 로그인과 구매 제출은 기존 주요 버튼 의미를 유지하면서 최소 크기·focus·disabled 상태를 공유한다.

콘텐츠 본문의 일반 링크, 웹툰 원고 밑줄 서식, 작품 카드의 제목 링크를 기계적으로 재작성하지 않는다. 계정 메뉴·브랜드 색·원고 렌더러를 새로 만들거나 전체 SPA로 바꾸지 않는다. 관리자 변경은 별도 U2다.

## 완료 증거

- Frontend lint 통과.
- Astro check 92 files: 오류·경고 0, 기존 works/index의 unused import hint 1건 유지.
- Vitest 24 files·269 tests 통과. 구매 페이지의 첫/마지막/상한 버튼은 추가 요청이 없고, 페이지 이동 시 다른 쿼리·해시와 현재 페이지 의미를 유지한다.
- production build 통과. 기존 Sentry token 미설정 및 transitions sourcemap 경고는 유지한다.
- SSR/DOM 13 tests 통과. 검증은 작품 첫/중간/마지막 페이지의 태그·페이지 링크·비활성 이전/다음·현재 페이지 의미와 기존 공개 캐시·계정 표시·구매 권한 셸을 확인한다. 브라우저 E2E나 실제 포인터·키보드 조작을 실행한 것으로 보지 않는다.

## 공통 알림 모달 (2026-11-16)

`components/ui/NoticeDialog.tsx`는 shadcn Base UI Dialog 구성을 참고한 알림 전용 컴포넌트다. `open`, `onOpenChange`, `message`를 전달하고 `title`(기본 알림), `confirmLabel`(기본 확인), `returnFocus`를 필요에 따라 바꾼다. 확인과 우상단 X, 바깥 클릭, Escape가 같은 닫기 경로를 사용한다. React 문자열로 본문을 렌더하고 포커스 제한·배경 비활성·복원은 기존 @base-ui/react 1.9.0에 맡긴다.

프로필 저장 성공에 연결했으며 닫힌 뒤 입력란으로 포커스를 복원한다. 독립6개 회귀로 모든 닫기 동작·내용 클릭 유지·다른 메시지 재개방·HTML 비삽입·초기/복원 포커스를 검증했다. 기존 결제/관리자 모달을 이 알림 컴포넌트로 대체하는 변경은 포함하지 않는다.

## 근거

- [UI 결정](../../../DECISIONS.md)
- [디자인 기준](../../../DESIGN.md)
- [구매내역 계약](../Payment/IMPLEMENTATION_PURCHASE_HISTORY.md)
- [shadcn Pagination](https://ui.shadcn.com/docs/components/base/pagination)
- [shadcn Button](https://ui.shadcn.com/docs/components/base/button)
