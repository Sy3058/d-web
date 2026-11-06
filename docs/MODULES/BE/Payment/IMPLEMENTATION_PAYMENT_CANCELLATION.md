# M3 E1 시스템 보상 취소 기반

## 범위

E1은 공통 sync가 사용할 취소 조회·최초 취소 준비·발송 선점 서비스다. 공개 API, webhook worker, 대사 scheduler와 연결하지 않는다. 구매 생성·권한 복원, G 사용자 환불은 후속 범위다.

- `portone_rest.py`: GET payment의 optional `cancellations`와 현재 ID 매칭.
- `payment.py`, revision `e1f6a7b8c9d0`: key 발급 시각과 발송 token·시각, DB CHECK.
- `payment_cancellation_service.py`: 호출자 transaction의 취소 준비와 독립 session으로 수행하는 발송.

## 조회와 최초 준비

현재 판매는 KRW만 지원하며 intent의 클라이언트 통화 입력은 거부한다. 동일 payment ID·Store의 `PAID`가 비KRW 또는 통화 누락이면 최초 준비 단계에서 `review_required/unsupported_payment_currency`로 격리한다. 구매·취소 요청을 생성하지 않고 외화 총액을 KRW 금액으로 저장하지 않는다. 발송 직전 GET에서도 비KRW가 관측되면 같은 사유로 격리하고 저장된 취소 묶음은 보존한다. USD 등 다중 통화는 후속 범위이며 서버 가격·금액 단위·PG capability·provenance·취소·매출을 함께 설계한 뒤 추가한다.

GET 취소 항목에는 `id`, enum으로 정규화한 `status`, 정수인 `totalAmount`만 보존한다. reason·고객 정보·원시 status를 보존하지 않는다. 현재 ID가 목록에서 정확히 한 번 나타날 때만 매칭한다. 목록 누락·빈 목록·미매칭·중복 ID는 실패 확정 증거가 아니며 알 수 없는 상태는 UNKNOWN이다. 잘못된 non-null 목록은 UNKNOWN 항목으로 남겨 신규 발송을 막는다.

`prepare_system_cancellation`은 호출자의 transaction 안에서만 동작하고 commit하지 않는다. E2는 판매 가능성·중복 구매 판단과 공통 lock 순서를 확정한 뒤 같은 transaction에서 이 함수를 호출해야 한다. 인증된 GET의 PAID, payment ID·Store·KRW와 양수 int32 총액을 확인하고 `preparing|ready|expired`의 취소 묶음이 없는 주문만 CAS로 선점한다.

반환값은 `CancellationPreparationResult`로 구분한다. `PREPARED`는 KRW 취소 준비 완료, `REVIEW_REQUIRED`는 비지원 통화 격리 완료, `UNCHANGED`는 선점 실패 또는 준비 불가다. 호출자는 격리 결과를 취소 준비 성공이나 단순 race로 해석하지 않는다.

시스템 사유, 주문 UUID에서 파생한 멱등 키, 발급 시각, 정확한 5-key 요청 snapshot과 `cancel_pending`을 함께 저장한다. 예상 500원·실제 승인 700원이면 `expected_amount=500`을 보존하고 `provider_total_amount=700`과 700원 취소 요청을 저장한다. 기존 취소 묶음은 덮어쓰지 않는다.

## 발송과 복구

1. 짧은 session에서 주문 snapshot을 읽고 session을 닫는다. token이 있거나 시스템 보상이 아니면 발송하지 않는다.
2. transaction·connection 없이 PortOne GET을 호출한다.
3. 현재 상태·key·취소 ID·요청 snapshot과 주문 변경 시각을 CAS로 확인한다. 이미 다른 worker가 처리한 오래된 GET은 적용하지 않는다.
4. 재생 허용 시간 안에서 token NULL을 새 UUID로 바꾸고 commit한다. POST 직전에도 시간 경계를 재확인한다.
5. transaction·connection 없이 동일 key·동일 body로 POST한다.
6. 같은 token·key인 응답만 반영하고 token을 해제한다. POST 결과의 ID는 기록하되 성공 응답만으로 취소를 확정하지 않고 다음 GET을 예약한다.

현재 취소 ID의 FAILED는 시스템 보상을 `review_required`로 격리한다. 전체 금액 SUCCEEDED 또는 검증된 CANCELLED는 취소를 확정한다. REQUESTED·UNKNOWN·금액 누락·현재 ID 미매칭은 잠금을 유지하고 재조회한다. 명시된 성공 취소 금액의 불일치나 지원하지 않는 자금 상태는 격리한다. 시스템 보상에서는 구매를 생성하거나 복원하지 않는다.

timeout·outstanding 409는 미종결이다. 다음 실행은 최신 GET부터 시작하며 `issued_at <= now < issued_at + 3시간` 안에서만 같은 요청을 재생한다. 창이 닫혀도 조회를 예약한다. task 취소·프로세스 종료·결과 commit 실패로 남은 token은 TTL로 회수하지 않는다. 운영자의 통제된 복구 절차와 scheduler 연결은 후속 E 범위다.

## DB와 migration

취소 사유·key·snapshot·발급 시각은 함께 존재해야 하며 token·발송 시각도 함께 존재해야 한다. token은 취소 묶음 없이는 저장할 수 없다. 발송 선점은 `cancel_pending`에서만 허용하지만 DB는 종결·격리 상태의 token 보존도 허용한다. 자금 상태를 되돌리거나 token을 성급히 지워 발송 소유권을 잃지 않기 위해서다.

기존 취소 묶음에는 `created_at`을 보수적 key 발급 시각으로 채운다. migration 실행 시각으로 재생 창을 연장하지 않는다. downgrade는 이전 CHECK와 컬럼 구조로 복원한다.

## 검증

2026-11-07 최종 검증:

- Backend 전체 gate: `uv run ruff format --check .`, `uv run ruff check .`, `uv run pytest -q` 통과, **769 passed**.
- 취소 서비스·intent focused 검증: **125 passed**. 비KRW·통화 누락 격리, 원본 금액·취소 묶음 보존, caller rollback, 경쟁한 paid/cancelled/cancel_pending 보존과 클라이언트 USD·JPY 입력 422·주문 0건을 포함한다. schema·adapter focused 검증 **82 passed**도 전체 gate에 포함됐다.
- 독립 session 동시 최초 준비와 동시 발송의 단일 승자, 발송 중 다른 worker 차단, stale GET·key·token·상태 변경 응답 방어를 검증했다.
- timeout·outstanding 409의 동일 key/body 재생, 정확히 3시간인 경계와 선점 후 POST 전 경계 초과를 검증했다. POST 재생 성공만으로 취소를 확정하지 않는다.
- task 취소와 결과 commit 실패 뒤 token 보존, 하루가 지나도 자동 회수·추가 POST 0건을 검증했다. pool checkout/checkin 소유 task를 추적해 각 GET/POST에서 호출 task가 DB connection을 보유하지 않음을 확인했다.
- scratch DB에서 이전 revision에 기존 취소 묶음을 삽입한 뒤 `upgrade head -> check -> downgrade d0c3a4b5e6f7 -> upgrade head -> check` 통과. `created_at` backfill, 잘못된 묶음 4건 거부, token 보존 상태 3종 허용과 downgrade의 기존 CHECK 복원도 확인했다. 검증이 만든 scratch DB만 정리했으며 개발 DB에는 migration을 적용하지 않았다.
- 메인 `fable-review` 검토와 `git diff --check` 통과. API 계약 변화가 없어 OpenAPI 타입 재생성·Frontend/Admin gate는 해당 없음.

실제 PortOne write·브라우저·공개 webhook 검증은 수행하지 않으며 기존 M3 외부 P0 gate에 남는다. E1 완료는 그룹 E 전체 완료를 의미하지 않는다.

## 공식 근거

- [PortOne V2 REST 멱등 정책](https://developers.portone.io/api/rest-v2): 동일 요청 재생, 3시간 보장, outstanding 409.
- [PaidPayment 타입](https://portone-io.github.io/server-sdk/js/types/Payment.PaidPayment.html): optional cancellations.

2026-11-06 확인. 라이브 호출 대신 fake adapter와 실제 PostgreSQL 독립 session으로 복구·경합을 검증한다.
