# M3 E3 결제 완료 API와 webhook inbox

## 범위와 계약

`POST /payments/{payment_id}/complete`는 로그인한 주문 소유자와 현재 결제 환경을 확인한 뒤 E2 `sync_payment(..., source='browser')`를 호출한다. 응답은 `payment_id`와 서버에서 확인한 주문 `status`만 포함한다. 클라이언트 body는 상태·금액의 근거가 아니다. 본인 주문이 아니거나 환경이 다르면 404, 인증 부재는 401, 동기화 경합은 409, provider 조회 불가·DB 저장 실패는 503이다. IP당 20회/분과 오류를 포함한 `Cache-Control: no-store`를 적용한다. intent 생성과 달리 이미 생성된 주문의 확인에는 이메일 인증을 다시 요구하지 않는다.

인증 SELECT의 session도 외부 GET 전에 닫는다. 서비스는 session factory로 짧은 조회와 반영 transaction을 분리하고 E2의 구매·보상 검증을 그대로 사용한다.

`POST /payments/webhooks/portone`는 최대 64KiB raw body와 Standard Webhooks 서명을 기존 SDK adapter로 검증한다. 검증된 최소 필드만 receipt에 저장하고 transaction commit 뒤 204를 반환한다. 저장 실패는 503, 검증 실패는 400, secret 미설정은 503이다. webhook 요청에서 PortOne을 조회하지 않는다.

검증된 `webhook-id` UNIQUE와 PostgreSQL `ON CONFLICT DO NOTHING`으로 중복 수신을 처리하고 기존 receipt를 덮어쓰지 않는다. 알려지지 않은 이벤트나 결제 ID 없는 이벤트는 `ignored_at`을 기록한다. 원시 body·서명·개인정보는 저장하지 않는다.

## worker와 원자성

worker는 짧은 transaction에서 due receipt 하나를 `FOR UPDATE SKIP LOCKED`로 선점한다. `attempts` 증가와 `next_attempt_at` 예약을 먼저 commit하고 외부 GET 중에는 DB connection을 보유하지 않는다. 재시도는 30초부터 지수 증가하며 최대 1시간이다. 선점 세대를 `attempts`로 검증해 이전 worker의 늦은 응답이 새 처리 결과를 덮어쓰지 못하게 한다.

sync 반영 transaction은 receipt를 잠그고 ID·payment ID·세대·미완료 조건을 확인한다. 주문 상태, 구매 권한, receipt FK를 포함한 감사 로그와 `processed_at`을 함께 commit한다. 조회 실패·not found·stale 응답·transaction 실패면 receipt는 미처리로 남는다. 프로세스 재시작 뒤 예약 시간이 지나면 다시 처리할 수 있다.

시스템 보상은 `cancel_pending`과 receipt 완료를 함께 commit한 다음 기존 E1 dispatch를 호출한다. 이 사이 중단되거나 발송 token이 남는 경우의 결제 상태 재확인·통제된 복구는 E4 계약을 따른다. receipt 완료가 실제 자금 종결을 뜻하지는 않는다.

worker는 기본 한 틱에 25건·180초, 설정 상한 100건·300초를 적용한다. 전체 시간 제한이나 종료 취소가 외부 POST 도중 발생하면 기존 발송 token 보존 규칙을 유지한다.

기존 APScheduler에 15초 interval, 기동 직후 실행, `max_instances=1`인 receipt 잡을 연결했다. 결제 상태 재확인 selector와 owner API는 E4 범위다. 새 dependency·schema·migration은 없다.

## 검증

2026-11-07 최종 검증:

- `uv run ruff format --check .`, `uv run ruff check .`, `uv run pytest -q`: **876 passed**, 66.10초, 경고 없음.
- webhook·sync 집중 **70 passed**. 실제 commit 직전 receipt 완료와 주문·구매·감사 로그 변경을 함께 실패시켜 rollback을 확인했다. 선점 예약은 보존되고, 예약 시각 뒤 재처리가 성공한다.
- API·scheduler 집중 **33 passed**. 실제 HMAC 서명, 변조·오래된 timestamp 거부, 중복 ID, unknown 이벤트, commit 실패 시 503을 확인했다. webhook 수신 중 provider 호출은 없다.
- complete 소유권·환경·인증·20회/분·no-store·응답 allowlist와 provider 재검증을 확인했다. 클라이언트 성공 입력에도 provider FAILED이면 구매를 생성하지 않는다.
- 실제 complete API와 receipt worker를 barrier로 경합시켜 구매 1개와 미완료 receipt의 후속 재처리를 확인했다. 독립 worker 경합, 잠긴 receipt 건너뛰기, 오래된 claim 세대·주문 version 응답 차단, bounded batch·최대 backoff·timeout·task 취소와 재시작 복구를 검증했다.
- provider GET 중 현재 task의 DB connection 미보유를 실제 checkout/checkin 이벤트로 확인했다.
- OpenAPI에서 Admin API 타입을 재생성했다. `pnpm --filter admin lint`, `pnpm --filter admin test` (**115 passed**), `pnpm --filter admin build` 통과.
- 메인 `fable-review`에서 소유권·환경·서명 경계, receipt→Work→Episode→Order→Purchase 잠금 순서, 세대 fencing, 원자 commit과 로그 비민감 필드만 사용하는 경로를 확인했다. 추가 Critical/Major 발견 없음. `git diff --check` 통과.

첫 DB 실행은 로컬 PostgreSQL이 중지돼 setup에 실패했다. 기존 컨테이너 시작 후 PID별 격리 DB로 재실행했다. 초기 전체 gate는 875 passed였고 SQLModel execute 경고를 수정하고 commit 실패·잠금 테스트를 보강한 뒤 위 최종 gate를 통과했다. 개발 DB schema와 데이터는 변경하지 않았다.

실제 PortOne write·공개 HTTPS webhook·브라우저 스모크는 사용자 검증 대상이다. 새 migration은 없으나 서버 실행 전 기존 E1/E2 migration 적용 상태는 확인해야 한다. E4 결제 상태 재확인·owner API 및 자금 종결 검증은 이번 완료 판정에 포함하지 않는다.

## 공식 근거

[PortOne V2 webhook 연동 문서](https://developers.portone.io/opi/ko/integration/webhook/readme-v2?v=v2)를 2026-11-07 확인했다. 알려진 Transaction 이벤트 allowlist, 알 수 없는 이벤트 무시, raw 서명 검증과 결제 재조회를 적용했다.
