# M3 E2 공통 결제 동기화

## 범위와 완료 조건

E2는 서버 주문의 결제 상태와 구매 권한을 반영하는 내부 서비스다. E1의 시스템 취소 준비·발송을 재사용한다. browser·webhook·reconcile·admin은 호출 출처이며, 실제 complete API와 webhook inbox·worker는 E3, scheduler selector·bounded batch와 owner 재조회 API는 E4에서 연결한다. G 사용자 환불 시도·권한 복원과 P1 후원 결과는 이 작업에 포함하지 않는다.

완료 조건은 다음과 같다.

- PortOne GET은 DB transaction·connection 밖에서 수행한다.
- 서버 주문 snapshot과 조회 결과의 payment ID·Store·KRW·금액·channel·환경·수단·결제 시각을 검증한다.
- 정상 또는 만료 뒤 늦은 PAID는 주문 paid·구매·감사 로그를 원자적으로 기록한다.
- 동일 주문의 재전송·동시 호출은 구매 한 건으로 수렴한다. 다른 주문의 이중 승인은 구매 하나와 loser의 전액 시스템 보상으로 수렴한다.
- commit 시점 공개·미삭제·판매 가능성을 재확인하고, 불일치·판매 불가는 구매 없이 E1 보상으로 넘긴다.
- stale 응답으로 주문 상태를 회귀시키지 않는다. 외부 취소 확정은 구매 권한도 회수하고 지원하지 않는 자금 상태는 격리한다.
- 구매와 catalog 변경은 Work→Episode→Order→Purchase 잠금 순서를 공유한다. 보호 대상 구매가 있으면 작품·회차 soft delete는 409다.
- 실제 PostgreSQL 독립 session 경합·rollback·외부 I/O 연결 미보유 테스트와 Backend 전체 gate를 통과한다.

## 구현 계약

`payment_sync_service.sync_payment(session_factory, adapter, payment_id, source)`는 내부 호출 경계다. 인증·주문 소유권 확인은 이후 공개 호출자가 담당한다. 반환값은 현재 주문 상태 또는 `not_found|stale`이며 원문·PII를 반환하지 않는다. 공개 API 요청·응답 schema 변경은 없다. 리뷰 보강에서 내부 주문 snapshot schema와 migration을 추가했다. 관리자 삭제의 구매 보호 409 매핑을 추가했다.

조회 시작 시 주문 status·updated_at을 기록하고, 외부 GET 뒤 부모부터 잠근 현재 주문이 달라졌으면 응답을 적용하지 않는다. fresh 재호출과 stale 호출을 구분하며 순차 재조회에는 감사 로그가 추가될 수 있지만 구매 생성은 한 번이다. GET 실패는 만료 근거로 쓰지 않고 재조회를 예약한다. expired는 자금 종결이 아니며 nonpaid 뒤에도 다음 조회를 유지한다. E4의 bounded selector·backoff는 아직 연결하지 않았다.

KRW 외 통화·알 수 없는 자금 상태는 격리한다. 검증된 CANCELLED는 주문과 기존 구매를 함께 닫는다. cancel_pending 시스템 주문은 E1의 최신 GET·발송 token·동일 key/body 정책으로 처리하고 사용자 환불 복원은 수행하지 않는다. 정상 승인에는 검증된 비민감 ID·수단을 저장하며 receipt URL 저장은 생략한다. 후원 주문은 성공 결과를 만들지 않고 운영 확인 대상으로 남긴다.

catalog는 Work 부모 잠금으로 sync와 직렬화한다. 작품 삭제는 부모 잠금 아래 하위 회차 구매를 검사한다. 회차 수정은 기존 content·thumbnail·manifest CAS를 보존하며, 회차 삭제는 부모 뒤 회차를 다시 잠근다. 일반 비공개는 구매 권한을 유지하고 열린 주문만 expired로 닫아 재조회를 예약한다.

## 검증 상태

2026-11-07 최종 검증:

- `uv run ruff format --check .`, `uv run ruff check .`, `uv run pytest -q`: **815 passed**, 68.14초.
- 신규 sync·catalog focused 실행 **46 passed**. 동일 주문 네 출처 경쟁은 조회 barrier로 최초 상태를 고정해 구매·전이 로그 한 건을 확인한다. 순차 재조회 로그 증가와 동시 경쟁을 혼동하지 않는다.
- 이중 승인 구매 하나·loser POST 하나, 500원 주문/700원 승인 전액 보상, 통화·환경·수단·시각 불일치, 취소 뒤 권한 회수와 stale PAID 복원 차단을 검증했다.
- 독립 session stale 응답·구매 commit과 삭제 경합, 감사 로그 insert 실패 시 주문·구매 rollback, 외부 GET/POST 중 현재 task의 DB connection 미보유를 검증했다.
- nonpaid 5종과 ready·expired·paid 조합, 조회 장애 재예약, 지원하지 않는 자금 상태의 권한 격리와 후속 CANCELLED 수렴, 판매 불가 4종 보상을 검증했다.
- 메인 fable-review에서 lock 순서·stale version·취소 묶음 보존·원자 commit·PII allowlist를 확인했다. `git diff --check` 통과.

리뷰 보강 migration `f2a7b8c9d0e1`의 검증 결과는 아래 기록을 따른다. 새 dependency와 Frontend/Admin 변경은 없다. OpenAPI 요청·응답 schema 변화가 없어 타입 재생성도 해당 없음. 테스트의 PostgreSQL 접근은 sandbox 연결 timeout 뒤 승인된 외부 실행으로 검증했으며 실제 PortOne write는 수행하지 않았다.

실제 PortOne write·브라우저·공개 webhook 검증은 기존 M3 외부 P0 gate에 남는다. E2 내부 서비스 완료만으로 그룹 E 전체를 완료하지 않는다.

## 공식 근거

[PortOne V2 REST API](https://developers.portone.io/api/rest-v2)를 2026-11-07 확인했다. E1에 고정한 동일 취소 요청·멱등 키 재사용과 3시간 재생 창을 유지한다.

## 리뷰 수정 (2026-11-07)

- `requested_payment_method`·`requested_easy_pay_provider`를 신규 intent에서 저장하고 sync와 intent의 provider 검사에 사용한다. channel key 교체·비활성 뒤에도 기존 주문의 정상 승인은 유지한다. 조회 결과 메타데이터로 요청 snapshot을 덮어쓰지 않는다.
- legacy 요청 수단은 추측 복원하지 않는다. 재사용은 checkout_changed로 닫고 PAID는 missing_payment_method_snapshot으로 격리한다. 자동 구매·자동 취소는 생성하지 않는다. migration은 legacy NULL을 보존하며 잘못된 수단 조합을 CHECK로 거부한다.
- 통화·자금 상태·snapshot 이상은 commit 이후 ERROR 로그를 발행한다. Sentry 기본 LoggingIntegration으로 이벤트가 생성되며 비민감 주문 ID·사유·이전/다음 상태만 추가한다. E1 dispatch가 새로 격리한 경우도 발송 commit 뒤 보고한다. 동일 격리 사유는 반복 보고하지 않는다.
- 채널 교체 3수단, legacy 격리·재사용 차단, DB rollback 시 알림 0건, commit 이후 이상 로그, 중복 억제와 외부 전송 없는 Sentry 이벤트 검증을 추가했다.

최종 검증: Ruff format/check와 Backend **827 passed** (62.06초), `git diff --check` 통과. intent·model focused **114 passed**, sync focused 최초 **39 passed** 뒤 3수단·rollback·dispatch 격리 보강을 전체 gate에 포함했다. 초기 sync focused에서 전역 asyncio mark와 동기 Sentry 테스트의 경고가 발생해 async 테스트로 수정했으며 최종 gate에는 경고가 없다.

scratch DB에서 `upgrade e1f6a7b8c9d0 -> legacy insert -> upgrade head -> check -> downgrade e1f6a7b8c9d0 -> upgrade head -> check` 통과. legacy NULL 보존, 잘못된 조합 5종 거부·정상 조합 3종 허용, downgrade 컬럼 제거와 자체 scratch 정리를 확인했다. 개발 DB에는 적용하지 않았으므로 이 코드로 서버 실행 전 `uv run alembic upgrade head`가 필요하다.

메인 재검토에서 현재 channel 설정 의존 제거, snapshot과 조회 메타데이터 구분, legacy 자동 취소 차단, commit 이후 알림, E1 CAS 승자만 격리 알림을 발행하는 경로를 확인했다. 실제 PortOne write·브라우저·Sentry 원격 전송은 수행하지 않았다. Sentry는 before_send에서 이벤트를 수집 후 폐기해 네트워크 없이 검증했다.

- 알림 근거: [Sentry Python LoggingIntegration 공식 소스](https://getsentry.github.io/sentry-python/_modules/sentry_sdk/integrations/logging.html). ERROR 레코드 이벤트 수집을 SDK 실제 테스트로 확인했다.
