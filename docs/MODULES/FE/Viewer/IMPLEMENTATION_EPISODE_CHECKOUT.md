# M3 회차 결제 UI와 복귀

## 범위

2026-11-10, M3 F의 최소 결제 UI를 기존 구매자 뷰어에 연결했다. 사용자 후속 요청에 따라 공개 회차의 유료 preview 경계에는 `유료 회차 구매하기` 버튼만 두고, 클릭하면 회차명·금액·결제수단·즉시 제공 고지를 확인하는 모달을 연다. 명시적 동의 후 서버 주문과 PortOne 결제창을 요청한다. 구매 내역·영수증·사용자 환불·매출 도구는 M3 후속이며 F 그룹 전체 완료는 아니다.

## 진입과 동의

구매 모달은 상단의 `구매하기`·X 닫기 버튼과 본문 사이를 구분선으로 나눈다. 본문의 회차 제목은 크게 굵게 표시하고, 직접 결제 금액·결제수단·즉시 제공 동의·결제 버튼을 배치한다. 2026-11-10 사용자 참조 화면의 헤더·제목 계층을 반영했다.

- `works/[id]/[publicId].astro`는 공개 catalog의 가격과 회차 경로·작품 ID를 무료 회차에도 Viewer에 전달한다. 공유 SSR 캐시에는 개인 구매 상태·주문·본문·서명 URL을 추가하지 않는다. 비공개 구매 진입의 bootstrap 계약은 유지한다.
- 리뷰 보완: 무료 SSR 가격이 캐시된 동안 유료로 전환돼 content API가 preview를 반환하면, 유효 가격이 없는 구매 진입은 공개 `/works/{id}/episodes`를 `cache: no-store`로 한 번 조회해 현재 회차의 제목·양수 정수 가격을 복구한다. 로딩·부재/무료·장애를 구분하고 장애는 명시적 재시도로 복구한다. 메타 조회만으로 모달·intent·SDK를 시작하지 않으며 전문 응답에서는 조회하지 않는다. 작품·회차 변경과 unmount의 늦은 결과를 버린다.
- Viewer는 content API가 `has_paid_part=true`를 반환한 preview에만 `EpisodeCheckout`을 표시한다. 전문을 받은 구매자에게 결제 폼을 표시하지 않는다.
- 초기 화면과 SSR에는 구매 버튼만 있고 모달 열기 자체는 인증·intent·SDK를 요청하지 않는다. 모달은 body portal로 렌더하고 제목·dialog 역할, 최초 포커스·Tab 순환·닫기 뒤 포커스 복귀, 배경 inert·스크롤 잠금을 제공한다. 닫기 버튼·Escape·배경 클릭으로 닫으며 다시 열 때 동의를 해제한다. 서버 요청 중에는 닫기를 차단하고, SDK 실행 중에는 모달·inert·포커스 제한·스크롤 잠금을 해제해 외부 결제창 조작을 막지 않는다. SDK 실패 시 모달과 상태 확인 링크를 복원하고 재동의를 요구한다. 언마운트 시 배경 상태와 이벤트를 정리한다.
- 고지 문구는 M3 foundation 결정 3의 테스트 문구와 `episode-immediate-v1`에 대응한다. 체크는 기본 미선택이며 `결제하고 바로 보기`를 클릭해야 인증 확인과 intent 요청을 시작한다. 로그인·이메일 인증은 서버가 다시 검증한다. 현재 로그인 화면은 회차 자동 복귀를 지원하지 않아 로그인 후 원래 회차로 돌아오도록 안내한다.
- 동의 후 `POST /payments/episode-intents`에 확인 금액·수단·고지 버전을 전달한다. 서버가 현재 가격과 검증한 주문 금액만 SDK로 전달하며, 응답 금액과 화면 확인 금액이 달라도 SDK를 호출하지 않는다. 중복 클릭과 언마운트 뒤의 늦은 응답을 차단한다.
- 409 `checkout_changed`의 회차·제목·KRW 정수 금액을 검증해 새 정보를 표시하고 체크를 해제한다. 사용자가 다시 동의하고 클릭하기 전에는 intent 재요청이나 SDK 호출을 하지 않는다. 알 수 없는 새 고지 버전은 기존 문구로 대신 동의받지 않고 결제를 차단한다. 일반 문자열 409와 장애를 가격 변경으로 추측하지 않는다.

## SDK와 서버 검증

공식 npm 배포 `@portone/browser-sdk@0.1.13`의 V2 모듈을 동적으로 불러온다. Store·channel·payment ID·금액·주문명은 서버 intent 응답을 사용하며 카드와 카카오페이·토스페이를 지원한다. 서버 `KRW`는 SDK `CURRENCY_KRW`로 변환한다. 간편결제는 `EASY_PAY`와 선택 수단의 provider를 함께 지정한다. secret이나 개인 결제 결과를 클라이언트 저장소에 보관하지 않는다.

`forceRedirect=true`와 동일 origin의 `/payments/return?returnTo=...`로 PC·모바일 복귀를 통일한다. SDK가 Promise로 성공을 반환하는 경우에도 SDK 응답의 식별자 대신 서버 intent의 payment ID로 같은 복귀 페이지를 연다. SDK 실패·undefined·예외는 provider 원문 없이 안내하고 생성된 주문의 `결제 상태 확인` 링크를 제공한다. 이 링크는 `data-astro-reload`로 결제 결과 아일랜드의 이전 상태를 재사용하지 않는다.

복귀 페이지는 on-demand SSR과 `Cache-Control: no-store`, `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex`를 사용한다. SSR은 query의 주문 ID나 PG 문구를 HTML에 넣거나 개인 API를 호출하지 않고 로딩 셸만 렌더한다. `PaymentReturn`의 effect가 payment ID를 읽고 인증된 `POST /payments/{payment_id}/complete`를 호출한다. URL의 code·message는 성공 판정과 화면에 사용하지 않는다.

서버의 주문 소유권·현재 환경·결제 snapshot 검증을 통과해 `status=paid`일 때만 원래 회차로 자동 이동한다. Viewer는 기존 세션 복구·content API를 다시 거쳐 권한 확인과 첫 전문 발급을 수행한다. 복귀 경로는 UUID 작품 ID와 8자리 public ID인 내부 회차 경로만 허용하고 외부 URL·query 포함 경로는 자동 이동하지 않는다. 이 경로 자체는 권한 근거가 아니다.

준비·미확정·만료·보상 취소 중·취소 완료·확인 필요 상태를 결제 성공과 구분한다. 오류·미수렴 상태는 사용자 버튼으로만 재확인하고 자동 반복 요청하지 않는다. 최종 401은 로그인 안내, refresh 장애는 상태 확인 오류로 남긴다. 언마운트 뒤 늦은 응답으로 이동하거나 결과를 갱신하지 않는다.

## 검증

2026-11-10 로컬 자동 검증:

- Frontend lint 통과.
- Astro check: 82 files, 오류·경고 0, 기존 `buildWorksUrl` 미사용 hint 1개.
- 모달·구매 배지·리뷰 후속 포함 Frontend Vitest: 21 files, **241 passed**. 동의·인증·중복 클릭·금액 불일치·가격 변경 재동의·알 수 없는 고지·SDK 오류·주문 ID 신뢰 경계·미확정 결과·refresh·재확인·외부 경로 차단·late 응답·preview/full 구매 버튼 노출, 모달 포커스·닫기·배경 복원·SDK 실행 중 모달 해제와 캐시된 무료 가격의 현재 가격 복구를 검증한다.
- Frontend build 통과. 기존 Sentry auth token 미설정과 Astro transitions sourcemap 경고 유지.
- 빌드 후 SSR HTTP 검증 **9 passed**. 기존 공개 캐시·비공개 메타 차단, 결제 복귀 no-store·query 비노출과 작품 목록 SSR 개인 상태 비노출, 무료 회차 SSR의 구매 복구 경로 전달을 실제 Node adapter 응답으로 확인한다. 임시 loopback 서버가 필요해 포트 접근이 허용된 환경에서 실행했다.

브라우저는 실행하지 않았다. 외부 주문 생성·실제 PortOne 테스트 결제창·공개 HTTPS 복귀·webhook 실수신·첫 전문 자동 표시는 사용자 브라우저 확인이 남는다. 카드·카카오페이·토스페이의 PC·모바일 외부 P0 gate와 F 전체 완료를 자동 테스트 통과로 대체하지 않는다. 결제 모달은 FE 변경이며 별도 [구매 배지 보완](../Catalog/IMPLEMENTATION_PURCHASE_BADGES.md)에서 Backend·Admin 타입을 변경했다. 별도 refresh-cookie-cleanup worktree는 수정하지 않았다.

모달 구현 근거: [React createPortal](https://react.dev/reference/react-dom/createPortal), [WAI-ARIA modal dialog 패턴](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/).

공식 근거: [PortOne 인증 결제 연동](https://developers.portone.io/opi/ko/integration/start/v2/checkout), [requestPayment 형식과 forceRedirect](https://developers.portone.io/sdk/ko/v2-sdk/payment-request?v=v2), [Astro on-demand 렌더링](https://docs.astro.build/en/guides/on-demand-rendering/).
