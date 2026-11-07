# M3 E4 결제 상태 재확인과 owner 재조회

## 범위와 호출 경계

`payment_reconciliation_service.py`의 scheduler worker와 `POST /admin/payments/{order_id}/sync`를 기존 `sync_payment`에 연결한다. `order_id`는 로컬 `PaymentOrder.id` UUID이며 provider payment ID는 저장된 주문에서만 읽는다. 응답은 `payment_id`, `status`만 반환한다. owner와 2FA 확인, 분당 20회 제한, 성공·실패의 `Cache-Control: no-store`를 적용한다. 존재하지 않는 주문은 404, 상태 경합은 409, 조회·저장 장애는 비민감 503이다.

신규 결제 kill switch는 두 경로를 중단하지 않는다. 현재 Store·환경으로 과거 주문을 걸러내지 않으며 저장 당시 `store_id`로 조회한다. 따라서 test에서 live로 설정을 교체해도 과거 test 미종결 주문을 추적한다. 단, 이전 Store 접근 권한이 있는 API secret은 계속 필요하다. secret 폐기·테스트 계정 retire는 별도의 자금 종결 확인 뒤 수행한다.

인증 session과 주문 조회 session을 외부 GET 전에 닫는다. 외부 I/O 뒤 기존 Work→Episode→Order→Purchase 잠금과 snapshot/version 검증을 그대로 사용한다. 신규 dependency·schema·migration은 없다. G 사용자 환불·권한 복원, F 결제 UI, P1 후원과 관리자 결제 상태 재확인 화면은 제외한다.

## Bounded 처리와 재시작

- nonexpired pool은 `preparing|ready|cancel_pending|review_required`와 `paid_at >= now - 192시간`인 `paid`를 선택한다. `cancelled`는 자동 selector에서 제외한다.
- expired pool은 나이·시도 횟수에 관계없이 `expired`를 선택한다. `not found|READY|PENDING|PAY_PENDING|FAILED`를 자금 종결로 해석하지 않는다.
- 두 pool은 각각 기본 25건·180초, 최대 100건·300초의 독립 예산을 가진다. 한 pool의 시간 초과 뒤에도 다른 pool은 자기 예산으로 처리한다. 두 pool을 합친 한 틱의 상한은 200건·600초다.
- `next_reconcile_at IS NULL OR <= now`인 주문을 예약 시각 NULL 우선·시각·UUID 순으로 `FOR UPDATE SKIP LOCKED` 선점한다. 한 틱에서 이미 선점한 UUID는 다시 선택하지 않는다.
- 외부 I/O 전에 `reconcile_attempts + 1`과 다음 예약을 commit한다. claim lease는 최대 pool 시간보다 긴 330초와 지수 backoff 중 큰 값이다. 중단 뒤 lease가 지나면 다시 선점한다. lease가 끝나도 취소 발송 token을 해제하지 않는다.
- sync는 선점 세대를 조회 전과 주문 잠금 뒤에 확인한다. 새 선점·complete·webhook·owner가 이긴 뒤 오래된 응답은 상태·구매·감사 로그를 적용하지 않는다. 정상 sync에서는 선점 횟수를 중복 증가시키지 않는다.
- 조회 결과 반영 시 60초에서 시작해 최대 1시간의 지수 backoff로 재예약한다. adapter 장애·typed not found도 재예약하며 임의 retry 상한으로 주문을 버리지 않는다. 취소 발송은 기존 E1의 별도 1분 재예약과 key 보장 창을 유지한다.

기존 APScheduler에 30초 interval, 기동 직후 실행과 `max_instances=1`인 잡을 추가한다. 재시작은 DB의 다음 예약을 이어 받으며, 다른 프로세스와의 선점은 DB가 방어한다. worker의 예상하지 못한 실패는 주문 UUID만 로깅한다.

## 발송 token의 통제된 복구

유실 token의 시각·TTL·프로세스 재시작, 단순 `PAID`나 cancellation `FAILED`는 token 해제·새 key·두 번째 POST의 근거가 아니다. scheduler와 owner sync는 이런 주문을 GET으로 계속 추적하고 token과 기존 취소 snapshot을 보존한다. 현재 cancellation의 실패는 기존 E1 규칙을 따른다.

같은 payment ID·Store·KRW·저장된 전체 승인 금액과 일치하는 최신 `CANCELLED`를 확인하면 시스템 보상 주문을 `cancelled`로 확정하고 token·시각을 함께 지운다. 또한 `cancel_pending` 시스템 보상의 최신 결제가 `PAID`여도, 저장된 현재 cancellation ID가 목록에서 정확히 한 번 매칭되고 `SUCCEEDED`·전체 취소 금액까지 일치하면 같은 종결을 수행한다. 과거·중복·미상 ID, 누락·부분 금액은 이 증거가 아니다. `review_required`의 `PAID`를 이 경로로 자동 해제하거나 G 사용자 환불로 확장하지 않는다.

이는 다시 발송하기 위한 lease 회수가 아니라, 재발송할 필요가 없는 전체 취소의 종결이다. `cancel_dispatch_recovered` 감사 로그와 일반 sync 로그를 같은 transaction에 기록하고 실제 조회의 provider status를 보존한다. 이미 `cancelled`인 시스템 보상도 owner 재조회로 같은 성공 근거를 확인할 수 있다. 진행 중이던 발송자의 늦은 응답은 token CAS에서 탈락한다.

전체 취소 증거가 없으면 자동 복구를 강행하지 않는다. owner는 기존 sync로 재조회하고, 계속 미수렴하면 PortOne 고객 응대와 외부 자금 상태 확인이 필요하다. 이 API는 token 강제 해제·새 취소 시도·G 환불 승인 기능을 제공하지 않는다.

[PortOne V2 공식 문서](https://developers.portone.io/api/rest-v2/overview)의 멱등성 보장 기간은 3시간이며 변경 가능하다(2026-11-07 확인). 기존 key의 발급 시각·동일 body·GET 선행 조건을 유지하고 보장 창 밖 자동 POST를 만들지 않는다. [PostgreSQL SELECT 공식 문서](https://www.postgresql.org/docs/17/sql-select.html)의 queue 소비자용 `SKIP LOCKED`를 짧은 선점 transaction에 사용한다.

## 검증

자동 검증 시나리오:

- `test_payment_reconciliation.py`: 모든 selector 상태·192시간 경계, batch 상한·독립 시간 예산, 선점 경쟁·재시작 lease·최대 backoff, 과거 test Store 추적, not found/FAILED 뒤 늦은 PAID, 중복 승인 보상의 다음 worker 전체 취소 종결, 유실 token 보존·전체 취소 복구, 민감하지 않은 실패 로그.
- `test_payment_sync.py`: 4 source 동시 구매 단일 승자, 새 claim 전/조회 중 세대 fencing, claim 횟수 1회와 1시간 backoff, token 복구의 ID·Store·통화·총액 검증, terminal 복구와 진행 중 POST의 늦은 FAILED 응답 경합. 리뷰 회귀는 4 source와 token 유무에서 PAID+현재 전액 SUCCEEDED 종결, 1시간 뒤 재조회 시 취소 시각 불변, 과거·중복 ID·실패·미상·부분 금액의 token 보존을 확인한다. provider fake는 현재 task의 DB connection이 열린 외부 I/O를 실패시킨다.
- `test_admin_payments.py`: owner·2FA·UUID·no-store·rate limit, 과거 환경과 kill switch false, 비민감 503·stale 409, 기존 key/body의 보상 재시도와 유실 token의 terminal 종결.
- `test_scheduler.py`: 시작 즉시 30초 결제 상태 재확인 잡 등록, secret 부재 시 미실행·kill switch false에서도 기존 후처리 실행.

리뷰 보강 후 최종 자동 gate(2026-11-07)는 Backend `uv run ruff format --check .`, `uv run ruff check .`, `uv run pytest` 945개(64.71초, warning 0)가 통과했다. 공통 sync focused 75개(2.85초)와 원본 리뷰 재현 2개(0.42초)도 통과했다. 이전 결제 상태 재확인 focused 20개·owner API 15개는 전체 gate에 포함된다. Admin의 OpenAPI 타입 재생성·lint·115개 테스트·build는 앞선 통과 결과를 유지한다. 이번 보강은 API 계약·생성 타입을 바꾸지 않았다. 주 실행자가 실제 정의·호출 경로·diff·테스트를 재확인했고, 리뷰에서 발견한 전액 SUCCEEDED의 token 복구 누락을 해결했다.

실제 PortOne write·공개 HTTPS webhook·브라우저 결제 확인은 실행하지 않으며 M3 외부 P0 gate에 남긴다. 이 문서의 자동 검증은 fake provider와 실제 PostgreSQL을 사용한다.
