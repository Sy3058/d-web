# 에피소드 결제 intent 생명주기 (M3 그룹 D)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Payment |
| 관련 마일스톤 | [M3](../../../milestones/M3_foundation.md) 그룹 D |
| 구현일 | 2026-10-26 |
| 상태 | 서버 intent API, 복구 가능한 preparing -> ready 전이, 30분 재사용과 race 검증 완료 |
| 선행 구현 | [결제 schema와 PortOne adapter](./IMPLEMENTATION_PAYMENT_FOUNDATION.md) |

이 그룹은 결제창을 열기 직전의 서버 주문까지만 책임진다. 외부 자금 상태 동기화, webhook, 구매 권한 발급, 브라우저 SDK와 실제 테스트 채널 write는 후속 E와 F 및 M3 외부 gate 범위다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/schemas/payment.py` | intent 요청, 결제수단 allowlist, 성공 config와 `checkout_changed` 응답 schema |
| `backend/src/routers/payments.py` | `POST /payments/episode-intents`, 이메일 인증, IP당 10회/분, 모든 정상·HTTP 오류의 `no-store` 처리 |
| `backend/src/services/payment_intent_service.py` | 서버 snapshot, 주문 생성·재사용·만료, PortOne 사전등록 복구와 잠금 후 상태 반영 |
| `backend/src/config.py` | 결제 활성화 시 세 channel key가 서로 달라야 한다는 fail-closed 검증 |
| `backend/tests/test_payment_intents.py` | PostgreSQL 기반 생명주기, 장애 복구, 동시 요청과 콘텐츠 변경 race 검증 |
| `admin/src/types/api.gen.ts` | FastAPI OpenAPI에서 공식 스크립트로 재생성한 요청·응답 타입 |

`payment_id`는 정본 계약대로 서버가 `pay_<uuidhex>` 형식으로 만든다. 결제 config의 Store, channel, KRW 금액, 주문명과 SDK `payMethod`도 서버 값만 반환하며 클라이언트 입력을 금액 원천으로 쓰지 않는다.

---

## 2. API와 검증 경계

요청은 다음 값만 허용한다.

- `episode_id`: UUID
- `expected_amount`: bool, 문자열, 실수를 받지 않는 양수 int32
- `payment_method`: `card|kakaopay|tosspay`
- `checkout_notice_version`: 현재 `episode-immediate-v1`
- `immediate_supply_consented`: 명시적 `true`

서버는 작품과 회차가 공개·미삭제인지, 실제 paywall 뒤 유료 콘텐츠가 있는지, 실효 가격이 양수인지, 같은 환경의 활성 구매가 없는지를 다시 확인한다. 성공 config는 요청 확인 금액, 현재 서버 가격, 선택된 주문의 `expected_amount`, 요청 수단에 대한 서버 channel, 현재 고지 버전이 모두 맞을 때만 반환한다.

불일치 응답은 409 `checkout_changed`이며 현재 `episode_id`, 제목, 금액, 통화, 고지 버전만 포함한다. `payment_id`, Store, channel 같은 결제 config는 포함하지 않는다. 비공개·삭제 대상은 존재를 숨긴 404, 이미 구매·무료·0원·paywall 없음은 409로 닫는다. provider 원문, secret, DB 오류 문자열은 일반 응답으로 전달하지 않는다.

`PAYMENTS_ACCEPT_NEW=false`는 신규 intent만 503으로 막는다. 이 서비스 밖의 webhook, 대사, 기존 구매 열람과 환불 경로에는 이 조건을 두지 않는다. 활성화 시 Store, API·webhook secret, 세 channel, 공개 HTTPS URL이 모두 필요하고 channel key 중복도 기동 단계에서 거부한다.

---

## 3. transaction과 복구 순서

잠금 순서는 `Work -> Episode -> open PaymentOrder -> Purchase`다.

1. 서버 상태와 기존 열린 주문을 잠가 검증한다.
2. 신규 주문은 `preparing`과 30분 `expires_at`, 즉시 대사 가능한 `next_reconcile_at`을 먼저 commit한다.
3. DB transaction이 없는 상태에서 기존 `payment_id` GET 또는 pre-register를 호출한다.
4. 외부 결과 뒤 새 transaction에서 작품, 회차, 주문과 구매를 다시 잠근다.
5. 상태와 snapshot이 그대로 유효할 때만 `ready`로 바꾸고 `next_reconcile_at=expires_at`을 기록한다.

pre-register timeout·실패나 성공 뒤 로컬 commit 실패가 나도 `preparing` 행과 같은 `payment_id`가 남는다. 재요청은 먼저 provider를 조회하며, `READY` 신원이 맞으면 로컬 `ready`를 복구하고 typed not-found면 같은 ID와 같은 금액으로 pre-register를 다시 호출한다. `PAID`, 취소, pending, unknown, `FAILED`, 조회 장애와 신원 불일치는 이 그룹에서 `ready`로 승격하거나 새 checkout을 만들지 않는다.

Provider `READY`는 결제수단 선택 전이라 channel type, channel key와 method가 없을 수 있다. 존재하는 필드는 주문의 Store·금액·통화·환경·channel과 맞춰 검증한다. method가 있으면 카드의 `PaymentMethodCard`, 간편결제의 `PaymentMethodEasyPay`와 `KAKAOPAY|TOSSPAY`까지 서버 channel capability와 일치해야 한다. [PortOne 공식 V2 결제 API](https://developers.portone.io/api/rest-v2/payment)가 `PaymentMethod`를 여러 타입의 union으로 정의하고 조회 결과의 `method`를 선택 필드로 두므로, 누락은 READY에서만 제한적으로 허용하고 다른 타입은 상태 변경 근거로 사용하지 않는다.

가격·수단·channel·고지가 달라졌거나 30분이 지났을 때는 provider가 해당 주문의 비승인 `READY`, typed not-found 또는 신원이 모두 일치하는 `FAILED`임을 확인하고 현재 행 version이 그대로일 때만 기존 주문을 `expired`로 닫는다. `FAILED`는 Store·금액·통화·환경·channel·method를 모두 정확히 확인한다. 조회 장애, 승인·pending 상태, 신원 불일치와 상태 race에서는 강제 만료하지 않는다.

---

## 4. 동시성 증거

- 같은 사용자·회차·환경의 동시 요청은 partial UNIQUE와 동일 잠금 순서로 주문 1행만 남긴다.
- 첫 pre-register가 끝나기 전 두 번째 GET이 not-found여도 두 write가 같은 `payment_id`와 server amount를 사용하고 결과 config도 같은 ID다.
- initial read가 winner를 놓쳐 INSERT가 UNIQUE 위반으로 끝난 경우 winner를 다시 잠근 뒤 수단, 양방향 가격 변경, 고지를 각각 재검증한다.
- 외부 호출 중 회차·작품 비공개, soft delete, 가격 변경 또는 주문 상태 변경이 먼저 commit되면 fresh lock이 이를 관측한다. 콘텐츠가 사라진 주문은 `expired/content_unavailable`, 가격 변경은 `expired/checkout_changed`가 되고 config와 구매는 0건이다.
- 외부 조회 뒤 주문 version이 바뀌면 stale 응답으로 강제 만료하거나 상태를 되돌리지 않는다.

이 검증은 독립 PostgreSQL session과 fake PortOne adapter를 사용한다. 실제 PortOne 사전등록 write와 브라우저 결제창은 수행하지 않았다.

---

## 5. 검증 결과

2026-10-26 기준:

- 결제 intent, 모델, adapter, config focused 검증: `143 passed`
- Backend 전체 gate: Ruff format check·lint 통과, `678 passed`
- Admin OpenAPI 생성물 검증: lint 통과, Vitest `115 passed`, production build 통과
- `git diff --check` 통과
- 독립 보안·동시성 리뷰에서 provider method·환경 누락 검증과 만료된 `FAILED` checkout 고착 finding을 수정하고 회귀 테스트를 추가했다.

실제 PortOne write, 카드·카카오페이·토스페이 브라우저 결제창, 모바일 redirect와 공개 HTTPS webhook은 NOT RUN이다. 이 자동 검증으로 외부 P0 gate를 대체하지 않는다.

---

## 6. 후속 그룹 인계

| 항목 | 이동처 |
|------|--------|
| browser complete, webhook, scheduler, owner가 공유하는 단조 `sync_payment` | 그룹 E |
| `FAILED` 로그, expired 포함 지속 대사와 늦은 `PAID` 권한·보상 수렴 | 그룹 E |
| 결제 고지 UI, `checkout_changed` 재확인, PortOne browser SDK와 redirect | 그룹 F |
| 활성 구매 전문과 비공개 구매 내역 direct link | 그룹 F |
| 실제 세 테스트 channel과 공개 HTTPS 스모크 | M3 외부 P0 gate |
