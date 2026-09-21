# 결제 schema와 PortOne adapter (M3 그룹 C)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Payment |
| 관련 마일스톤 | [M3](../../../milestones/M3_foundation.md) 그룹 C |
| 작성 시점 | M3 C (2026-09-01) |
| 리뷰 보강 | 2026-09-05 적대적 결제 무결성 리뷰, 2026-09-11 금액 불일치 보상 취소 제약 수정 |
| 상태 | 결제 schema, migration, async REST·webhook adapter 구현 완료. Backend 전체 gate와 scratch migration 왕복 통과 |
| 관련 문서 | DB_SCHEMA.md §3, DECISIONS.md "결제 구조 결정", MISTAKES.md, DB_GUIDE.md |

PortOne의 실제 자금 상태와 로컬 주문, 열람 권한을 서로 다른 진실로 유지하기 위한 기반이다. 이 그룹은 주문 생성 API나 결제 상태 동기화를 열지 않고, 다음 그룹들이 안전하게 사용할 DB 제약과 외부 adapter 계약까지만 구현한다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/models/payment.py` | `PaymentOrder`, `Purchase`, `PaymentWebhookReceipt`, `PaymentLog`와 VARCHAR 기반 enum |
| `backend/migrations/versions/20260901_1030_payment_foundation.py` | 결제 테이블 4개, CHECK, partial unique, FK, 조회 index |
| `backend/src/config.py` | `PAYMENT_ENVIRONMENT`, `SecretStr` API·webhook secret |
| `backend/src/services/portone_rest.py` | `httpx.AsyncClient` 기반 V2 pre-register·단건 조회·취소 adapter |
| `backend/src/services/portone_webhook.py` | `portone-server-sdk` 기반 raw body 서명 검증과 allowlist 추출 |
| `backend/tests/test_payment_models.py` | DB CHECK, 환경별 열린 주문·구매 partial unique 검증 |
| `backend/tests/test_portone_adapter.py` | timeout, retry, unknown 응답, 취소 snapshot, webhook, secret 비노출 검증 |
| `backend/.env.example` | 서버 소유 Store·channel과 secret, 결제 환경 설정 안내 |

`frontend/.env.example`의 `PUBLIC_PORTONE_*`는 제거했다. Store ID와 channel key 자체는 비밀이 아니지만, 서버가 현재 환경과 허용 결제수단을 검증한 뒤 intent 응답으로 선택해 주는 값이다. 프론트 배포 설정에 복제하면 서버 설정과 서로 다른 값으로 표류할 수 있다.

---

## 2. DB 경계

### 자금, 주문, 권한의 분리

- `payment_orders`: 서버가 만든 `pay_<uuidhex>` 주문과 Store·channel·금액·환경 snapshot, 마지막 동기화 상태
- `purchases`: 전문 열람 권한의 기준. `payment_order_id`당 최대 1행
- `payment_webhook_receipts`: 서명이 검증된 webhook의 durable 수신 기록. raw body와 header는 저장하지 않음
- `payment_logs`: 제한된 상태와 failure code만 저장하는 감사 로그. 원시 PortOne 응답과 PII는 저장하지 않음

FK는 결제·계약 기록을 5년 보존하도록 `RESTRICT`다. 기존 사용자·작품·회차 soft delete 정책과 결제 기록을 함께 유지하며, 구매가 남은 회차의 실제 삭제는 후속 그룹의 서비스 규칙에서 409로 막는다.

`Purchase`의 주문 참조는 ID 하나만 보지 않는다. 주문 ID·사용자·고정된 `episode_purchase` kind·회차·환경·금액·결제 시각 7개를 composite FK로 묶는다. 따라서 존재하는 다른 주문을 참조하더라도 사용자, 회차, test/live 환경, 금액, `paid_at` 중 하나가 다르거나 donation 주문이면 권한 행을 만들 수 없다. 부모의 같은 열에는 명시적 composite UNIQUE를 두며, 구매 생성 뒤 해당 provenance 변경도 `ON UPDATE RESTRICT`로 거부한다. 취소 과정에서 바뀌어야 하는 주문 `status`는 FK에 넣지 않고, 구매 생성 시 `paid` 확인은 후속 공통 sync transaction이 책임진다.

### 상태와 대상 CHECK

`kind`, 주문·구매 `status`, `environment`, `currency`는 앱 enum만 믿지 않고 DB CHECK로도 제한한다. 구매 주문은 회차, 결제 고지 버전, 즉시 제공 동의 시각이 필수다. 후원 주문은 작가 후원이면 회차가 없고 에피소드 후원이면 회차가 있으며, 결제 고지 버전과 즉시 제공 동의 시각은 두 경우 모두 없어야 한다. 금액과 대사 횟수도 음수 상태를 허용하지 않는다.

같은 사용자·회차의 열린 구매 주문과 활성 구매는 `environment`를 포함한 partial unique로 제한한다. 따라서 test 구매가 있어도 같은 사용자·회차의 live 주문과 live 구매를 막지 않는다.

취소 사유, 멱등 키, exact request snapshot은 모두 NULL이거나 모두 존재해야 하고 `cancel_pending`에서는 필수다. 사유는 `system_verification|system_unavailable|system_duplicate|customer_refund` allowlist만 받는다. 취소 묶음에는 양수 `provider_total_amount`도 필요하다. DB는 snapshot이 주문의 Store, 사유, provider 총액 기준 전액 `amount`·`currentCancellableAmount`, 사유별 `requester`로 재구성한 정확한 5-key JSONB인지 비교하므로 추가 키나 개인정보를 저장할 수 없다. 시스템 사유 requester는 `ADMIN`, 고객 환불은 `CUSTOMER`다. 키는 DB에서도 16~256자 printable ASCII를 검사한다. adapter의 `PortOneCancelRequest`는 DB에서 읽은 허용 문자열을 enum으로 정규화하는 frozen 값 객체이고 매 호출마다 같은 allowlist JSON을 만든다. 후속 환불·보상 서비스는 최초 사유·key·snapshot을 조건부로 한 번만 저장하고 재시도에서 그 값을 다시 읽어야 한다.

2026-09-11 리뷰에서 주문 예상 금액 500원과 외부 승인 총액 700원이 다르면 기존 CHECK가 전액 취소 snapshot과 700원 취소 결과 모두를 거부하는 문제가 확인됐다. 서버 주문·구매 provenance인 `expected_amount`를 고쳐 맞추지 않고, 인증된 PortOne 단건 조회의 `amount.total`을 담는 nullable 양수 `provider_total_amount`를 분리했다. 이는 `amount.paid`가 아니며, 클라이언트나 webhook 알림의 금액을 신뢰하지 않는다. 취소 snapshot의 두 금액은 provider 총액과 같고, 취소 결과는 `0 < cancelled_amount <= provider_total_amount`여야 한다. 취소 묶음·결과에서 provider 총액의 `IS NOT NULL`도 명시해 SQL CHECK의 NULL 통과를 막는다. 조회·동기화 서비스에서 이 값을 채우는 경로는 그룹 E 범위다.

수정 전 개발 DB가 직전 revision `b8d1f4e9a2c7`이고 그룹 C migration은 미커밋·미적용임을 확인했다. 따라서 별도 forward migration을 추가하지 않고 신규 그룹 C migration에 같은 컬럼과 CHECK를 반영한다. 공유 개발 DB를 초기화하거나 stamp하지 않는다.

### JSON `null`과 SQL `NULL`

초기 DB 테스트에서 정상 주문의 `cancel_request_snapshot=None`이 PostgreSQL JSONB 값 `null`로 저장돼 `IS NULL` CHECK를 깨뜨렸다. SQLAlchemy JSONB 기본 직렬화는 Python `None`을 JSON `null`로 취급하기 때문이다. 컬럼을 `JSONB(none_as_null=True)`로 선언해 "취소 요청 없음"이 SQL `NULL`이라는 DB 의미와 일치하게 했다.

---

## 3. PortOne REST adapter

공식 V2 API hostname인 `https://api.portone.io`와 `Authorization: PortOne <V2 API Secret>` 형식을 사용한다. V2는 API 제품 버전이며 URL에 `/v2` prefix를 붙이지 않는다. timeout은 `connect=5`, `read=65`, `write=10`, `pool=5`초다. PortOne의 최소 read timeout 60초 권고보다 짧지 않다.

재시도 정책은 메서드의 멱등성에 따라 분리한다.

- 단건 GET: connect·pool 오류와 일시적 429·5xx만 jitter 뒤 1회 재시도
- read timeout: 같은 조회를 inline 재시도하지 않고 후속 대사로 넘김
- pre-register·cancel: adapter 자동 재시도 0회
- 단건 GET 404: 오류 JSON의 `type`이 정확히 `PAYMENT_NOT_FOUND`일 때만 미존재 `None`; HTML이나 다른 404는 API 오류
- cancel 재시도: 호출자가 DB에서 읽은 같은 16~256자 ASCII key와 같은 exact snapshot으로만 명시 호출
- `409 IDEMPOTENCY_OUTSTANDING_REQUEST`: 비terminal·재시도 가능으로 분류하되 POST를 adapter가 자동 재시도하지 않음
- cancel request: `amount`와 `currentCancellableAmount`가 같은 전액 취소만 허용

응답은 원시 dict를 반환하지 않는다. 결제 ID, 상태, Store, channel, 금액, 통화, 주문명, 결제수단, 영수증 URL과 시각만 frozen snapshot으로 옮긴다. 새 필드와 새 oneOf는 무시하고, 모르는 자금 상태는 `UNKNOWN`으로 격리한다. API 오류도 HTTP status와 제한된 ASCII error type만 남겨 provider message의 secret·PII가 예외 문자열이나 로그로 전파되지 않게 한다.

---

## 4. Webhook adapter

`portone-server-sdk==0.21.0`을 정확히 고정했다. 2026-09-01 확인 시 최신 정식 버전이며, 공식 문서가 0.x 업데이트의 코드 호환 변경 가능성을 명시하므로 자동 범위 업데이트를 허용하지 않는다.

SDK는 raw body와 Standard Webhooks header를 이용한 로컬 서명 검증에만 쓴다. SDK의 네트워크 client는 FastAPI event loop에서 사용하지 않는다. 검증 성공 뒤에도 반환하는 값은 다음 세 가지뿐이다.

- `webhook-id`
- event `type`
- `data.paymentId`가 유효한 길이의 문자열일 때 그 값

알 수 없는 event도 서명이 맞으면 receipt로 보존할 수 있고, 후속 worker가 `ignored_at`으로 종결한다. secret, signature, raw body, email 같은 데이터는 반환값과 DB에 남지 않는다.

공식 근거:

- [PortOne REST API V2](https://developers.portone.io/api/rest-v2)
- [PortOne 결제 API](https://developers.portone.io/api/rest-v2/payment?v=v2)
- [PortOne Python Server SDK](https://pypi.org/project/portone-server-sdk/)

---

## 5. 검증

자동 검증 결과 (2026-09-12 최종 확인):

- PortOne adapter·webhook 단위 테스트 20개 통과
- 주문 provenance 불일치, donation 기반 구매, 취소 snapshot의 자유 문자열 사유·불완전한 묶음·PII 거부, 과소·정상·과다 승인 전액 취소와 provider 총액 제약을 포함한 결제 모델 PostgreSQL 통합 테스트 23개 통과
- 새 scratch DB에서 전체 migration `upgrade head` 통과
- `alembic check`에서 모델과 migration 차이 0건
- 그룹 C를 직전 revision으로 downgrade한 뒤 재-upgrade·재-check 통과
- Backend `ruff format --check`, `ruff check`, 전체 `pytest` 578개 통과 (2026-09-12 최종 자동검증; focused 43개는 adapter 20개 + model 23개)
- 2026-09-11 신규 scratch DB에서 `upgrade head → check → downgrade b8d1f4e9a2c7 → upgrade → check` 모두 통과. Alembic으로 만든 schema에서 취소 금액 300·500·700 3건과 snapshot 금액 불일치·provider 없는 JSON null snapshot·provider 없는 취소 결과·취소 상한 초과 4건 거부를 확인했다. 검증 뒤 해당 임시 DB를 삭제했으며 공유 개발 DB는 변경하지 않았다.
- 설정된 테스트 V2 API secret으로 존재하지 않는 임의 `paymentId`를 실제 조회해 인증된 `PAYMENT_NOT_FOUND` 404가 `None`으로 변환되는 것을 확인. 같은 요청의 가짜 secret은 401이어서 인증 경계도 비교 확인

검증 시 test 구매와 같은 사용자·회차의 live 열린 주문이 공존하고, 같은 환경의 두 열린 주문은 unique violation으로 막히는 것을 확인했다. test·live 활성 구매도 각각 한 행씩 공존하며 같은 환경의 두 활성 권한은 막힌다. 또한 구매와 주문의 사용자·회차·환경·금액·결제 시각 중 하나라도 다르거나 참조 주문이 donation이면 DB가 구매 생성을 거부하고, 구매 뒤 주문 provenance 변경은 막되 `paid -> cancel_pending -> cancelled` 상태 전이는 허용함을 확인했다.

실제 PortOne 서버의 읽기 전용 단건 조회로 hostname과 API secret은 2026-09-01에 검증했다(이번 최종 자동검증에서는 재실행하지 않음). Store를 쓰는 pre-register, 카드·카카오페이·토스페이 브라우저 결제, webhook 공개 HTTPS 수신은 intent·공통 sync·최소 UI가 붙는 D~F에서 실제 테스트 채널 스모크로 검증한다.

---

## 6. 후속 그룹 인계

| 항목 | 이동처 |
|------|--------|
| preparing 주문 생성, pre-register crash 복구, 30분 재사용·만료, 신규 결제 kill switch | 그룹 D |
| browser·webhook receipt worker·scheduler·owner 공통 `sync_payment`와 보상 취소, GET cancellations typed allowlist 매핑·현재 취소 ID 매칭, key 발급 시각·발송 token CAS | 그룹 E |
| 결제 고지 UI, redirect, 구매 권한 resolver, 비공개 구매 회차 전문 | 그룹 F |
| `refund_requests`, 시도 번호별 환불 key 교체, 기본 매출 | 그룹 G (취소 key·snapshot 최초 저장과 발송 token CAS는 E 제공, G 재사용) |
| `donations` 결과 테이블과 후원 UI | 그룹 H |

그룹 C에는 router와 외부 호출 중 DB transaction을 여는 서비스가 없다. GET `payment`의 `cancellations` typed allowlist와 현재 취소 ID 매칭, 취소 key 발급 시각·발송 token CAS는 그룹 E 선행 작업이며 C snapshot에는 구현되지 않았다. 시스템 보상에 필요한 취소 key·snapshot 최초 저장 CAS도 E가 제공하고 G가 재사용한다. G는 확인된 최종 실패 뒤 새 시도 번호에서 새 key를 만들되 exact body는 유지한다. 이후 그룹도 PortOne I/O 전후의 짧은 DB transaction을 분리해야 한다.
