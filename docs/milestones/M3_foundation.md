# M3. 결제 + 유료 콘텐츠 잠금 + 후원 - 세부

| 항목 | 내용 |
|------|------|
| 문서 버전 | v0.6 (2026-08-30, 완료 증거 계층과 간편결제 테스트 채널 정정) |
| 상위 마일스톤 | [M3](./README.md#m3-결제--유료-콘텐츠-잠금--후원) |
| 예상 기간 | 약 6~8주 + 외부 채널·법무 일정 |
| P0 완료 기준 | `결제 전 고지·동의 → 서버 주문 → 검증된 결제 → 구매 권한 1건 → 전문 자동 발급 → 환불·장애 복구 → 기본 매출 확인`이 PortOne 테스트 채널에서 끝까지 작동한다. |
| M3 완료 기준 | P0 위에 이미지 공간 예약·완독/CTA, 작가·에피소드 후원, 상세 수익·운영 화면까지 동작한다. |
| 선행 마일스톤 | [M2](./M2_foundation.md) - 공개 카탈로그, paywall 절단, presigned 본문, 뷰어·복원 앵커 완료 |
| 다음 마일스톤 | [M4](./README.md#m4-커뮤니티-후원은-m3로-이동) - 커뮤니티 |

> **2026-08-26 실행 순서 변경**: 사용자의 최신 지시로 M3를 M2 다음에 착수한다. 2026-07-03의 "M5·M6 뒤, M7 직전" 결정은 이 결정으로 대체한다. 개발은 사업자 등록이 필요 없는 PortOne 테스트 채널로 진행하고, 실채널 전환·약관 법무 검토는 M7 출시 게이트로 유지한다. M4 게시글이 아직 없으므로 M3 후원 대상은 작가·에피소드로 제한하고 게시글 후원은 만들지 않는다.

> **2026-08-27 계정 경계 확정**: M3는 개발자 본인 소유의 임시 PortOne 고객사·테스트 Store에서 진행한다. 실제 판매가 필요해지면 작가가 별도 PortOne Owner 계정과 실판매 Store를 만들고 개발자를 Dev로 초대한다. 개발자 계정을 작가 사업자로 전환하거나 외부 테스트 거래를 이관하지 않으며, 애플리케이션은 Store·channel·secret 설정만 교체한다.

> **2026-08-27 즉시 열람 UX 확정**: 결제 전에 즉시 제공과 단순 변심 청약철회 제한을 명시적으로 확인받고, 검증된 결제 복귀 뒤 full content를 자동 요청한다. 결제 후 `전문 이어보기` 버튼은 두지 않는다. 결제 성공 자체가 아니라 실제 첫 full 응답 발급만 `first_viewed_at`을 기록한다.

> **범위 우선순위**: P0는 판매 가능한 최소 수직 경로이며 P1 기능 때문에 첫 판매 경로를 늦추지 않는다. 이미지 치수·완독, 후원, 전환율·상세 breakdown은 M3 안에서 완료하지만 P0 gate 뒤에 진행한다. 범위는 PRD **PAY-01~06, 08, 10**, **WORK-06~07**, **ADM-05·08**가 P0이고, **PAY-09**, **WORK-09**, **ADM-10**과 상세 분석이 P1이다.

---

## 보안·정합성 불변조건

1. 결제 ID, 대상, 금액, 통화, Store, channel은 서버가 확정한다. 클라이언트 값은 권한 부여 근거로 쓰지 않는다.
2. PortOne 조회가 `PAID`이고 주문 snapshot의 Store·환경·통화·금액·대상·허용 channel과 모두 일치할 때만 구매 권한이나 후원 결과를 만든다.
3. 브라우저 복귀 값과 webhook payload는 알림일 뿐이다. 둘 다 PortOne 결제 단건 조회 결과로 재검증한다.
4. PortOne은 실제 자금 상태의 원천, `payment_orders`는 서버 주문과 마지막 검증 결과의 로컬 동기화 상태, `purchases`는 열람 권한의 원천이다.
5. 모든 외부 `PAID`는 정확히 하나의 종결점으로 수렴한다. 정상 주문이면 권한·후원 결과를 만들고, 금액 불일치나 중복 승인 건이면 전액 보상 취소한다. 돈만 빠지고 어느 쪽도 남지 않는 상태를 허용하지 않는다.
6. 브라우저 완료·webhook·대사 잡이 동시에 같은 주문을 처리해도 결과는 하나다. 서로 다른 주문이 같은 회차에 모두 `PAID`여도 한 구매만 남기고 나머지는 보상 취소한다.
7. 미구매 응답은 paywall 뒤 텍스트와 이미지 key·URL을 포함하지 않는다. 개인 구매 상태는 공유 캐시 가능한 카탈로그·SSR에 섞지 않는다.
8. PortOne API나 R2 호출 중 DB transaction·connection을 잡지 않는다. 외부 성공 뒤 DB 반영 실패는 같은 ID·멱등 키·webhook·대사로 복구한다.
9. 환불 승인과 첫 전문 발급은 같은 `purchases` 행의 조건부 UPDATE로 경합시켜 한쪽만 이긴다. 환불 처리 중과 검토 필요 상태에서는 전문 권한을 닫는다.
10. API Secret·webhook secret·원시 PortOne 응답·개인정보를 로그나 일반 응답에 남기지 않는다. 금융·개인 응답은 모두 `Cache-Control: no-store`다.
11. `test|live`는 계정 소유자가 아니라 서버 결제 환경과 검증된 채널이 결정하는 불변 snapshot이다. 주문과 구매 권한의 환경이 현재 배포 환경과 모두 일치할 때만 전문을 열며 test 승인은 live 권한·매출·중복 구매 제약에 영향을 주지 않는다.
12. 회차 구매 성공은 `payment_orders.paid`와 `purchases.active`가 같은 transaction에 commit된 때다. 그 뒤 일반 비공개가 되어도 구매자는 full을 유지한다. 비공개·soft delete가 먼저 commit되면 이후 확인된 `PAID`는 구매 성공으로 표시하지 않고 전액 보상 취소한다. 성공했는데 비공개 때문에 열람만 실패하는 종결점은 허용하지 않는다.
13. access 쿠키는 15분 만료이므로 그 401만으로 로그아웃 처리하지 않는다. refresh 수명과 함께 갱신되는 `login_hint`는 표시·세션 복구 시도용 힌트일 뿐 권한 근거가 아니며, React island는 hydration 뒤 `useEffect`에서 읽는다.

---

## 단계와 의존성

```text
[0] 정본 문서 동기화 + 외부 준비
  ↓
[C] 주문·구매 schema + PortOne adapter
  ↓
[D] intent 생명주기
  ↓
[E] 공통 sync + webhook + 대사
  ↓
[F] 구매 권한 + 전문 + 최소 결제 UI
  ├──→ [G] 환불 + 기본 구매 매출 ──→ P0 gate
  ├──→ [A] 이미지 metadata ──→ [B] 완독 + 작품 경험
  └──→ [H] 후원 ─────────────→ [I] 상세 수익·운영
                                      ↓
                                  M3 완료
```

- 0은 이 foundation PR에서 끝낸다. 실행 순서·PortOne V2·DB 초안을 H까지 미루지 않는다.
- A의 metadata·백필은 외부 키와 무관해 C~G와 병렬 가능하지만, 완독 B는 F의 `access_scope`가 선행한다.
- C~G가 P0 임계 경로다. H와 B는 P1이며 첫 판매 경로를 막지 않는다.
- E의 모든 진입점은 같은 `sync_payment(payment_id, source)`를 호출한다. owner는 상태를 직접 덮어쓰지 않고 이 동기화 또는 보상 취소 재시도만 실행한다.

---

## Day 0 외부 선행조건

| 항목 | 현재 상태 | 착수 조건 |
|------|-----------|-----------|
| 개발자 테스트 고객사 이용 자격 | 개발자 명의 테스트 고객사 생성, 이용 조건 확인 기록은 미완료 | PortOne의 고객사 정의는 사업체와 타 고객사 결제를 개발하는 에이전시 예외를 둔다. 개발자 본인 정보로 사실대로 가입하고, 현재 협업 형태가 테스트 고객사 이용 조건에 맞는지 공개 실연동 전 PortOne에 확인한다. |
| 개발자 소유 PortOne 테스트 Store ID, V2 API Secret, webhook secret | 발급·backend 로컬 설정 완료, V2 API secret 읽기 전용 실조회 완료, Store·webhook 통신 미검증 | 작가 사업자·대표자·계좌 정보를 입력하지 않고 두 secret은 `SecretStr`로 다룬다. D~F 공개 실연동에서 Store와 secret 조합을 검증한다. |
| 카드 테스트 channel key·최소 결제 금액 | 테스트 channel 생성·backend 로컬 설정 완료, 최소 금액·브라우저 스모크 미검증 | 카드 1종은 M3 공개 HTTPS E2E 필수다. 확인된 테스트 하한을 M3 결제 하한으로 고정한다. |
| 카카오페이·토스페이 channel key | `TC0ONETIME`·`tosstest` channel 생성과 backend 로컬 설정 완료, 브라우저 스모크 미검증 | M3 공개 HTTPS에서 실제 브라우저 스모크한다. 계약·심사를 거친 실 MID 검증만 M7 gate다. |
| 공개 frontend·API·webhook HTTPS 주소 | 미검증 | 모바일 redirect, HttpOnly 쿠키, CORS, webhook 실수신 스모크에 필요하다. 로컬 fixture는 이를 대체하지 않는다. |
| 결제 운영 스위치 | 미구현 | `payments_accept_new=false`면 신규 intent만 503으로 닫고 webhook·대사·기존 구매 열람·환불은 계속 작동하게 한다. |
| 환불·만 14세 약관 문구 | 법무 미검토 | 테스트 UI는 즉시 제공·단순 변심 청약철회 제한·계약 불일치 예외를 결제 전에 고지한다. 168시간 정책과 문구는 잠정이며 실결제는 M7 Q1·Q7 승인 없이는 차단한다. |

Day 0 증거에는 개발자 소유 테스트 고객사·Store·channel 식별자, 공개 URL, 카드·카카오페이·토스페이 브라우저 종료, webhook 재전송, 취소 timeout의 스모크 결과를 기록한다. secret 원문과 결제 개인정보는 기록하지 않는다.

---

## 설계 결정

### 결정 1: PortOne V2와 async REST adapter를 사용한다

- 프론트는 `@portone/browser-sdk/v2`의 `requestPayment`를 사용한다. 2026-08-30 npm registry 확인 버전은 `0.1.9`이며 구현 직전에 공식 최신 릴리스를 다시 확인하고 정확 버전을 pin한다.
- 백엔드의 pre-register·단건 조회·취소는 `httpx.AsyncClient` 기반 V2 REST adapter로 구현한다. timeout은 `connect=5초`, `read=65초`, `write=10초`, `pool=5초`로 명시한다. PortOne이 권고하는 최소 read timeout 60초보다 짧게 두지 않고, 존재하지 않는 `total` 옵션으로 설정됐다고 오인하지 않는다.
- 단건 GET은 connect·pool·일시적 429/5xx에 한해 jitter를 둔 1회 inline 재시도 뒤 대사로 넘긴다. 취소 같은 write는 adapter가 임의 재시도하지 않고, 호출자가 DB에 저장한 동일 멱등 키·동일 request snapshot으로만 재시도한다. 응답은 typed allowlist로 검증하되 새 필드·enum·oneOf가 추가돼도 crash하지 않고 알 수 없는 자금 상태로 격리한다.
- `portone-server-sdk`는 raw webhook 서명 검증에만 사용한다. 이 검증은 raw body와 헤더를 입력으로 하는 짧은 로컬 연산이다. SDK의 동기 네트워크 client를 async FastAPI event loop에서 직접 호출하지 않는다.
- `payment_id`는 서버가 `pay_<uuidhex>`로 만든다. 브라우저는 새 ID를 만들거나 금액을 덮어쓰지 않는다.
- 결제창 전 서버는 V2 pre-register에 `payment_id`, Store ID, KRW 금액을 등록한다. 결제 뒤 단건 조회 검증은 반드시 별도로 수행한다.
- 모바일 단일 흐름은 `redirectUrl`과 `forceRedirect=true`를 사용한다. 복귀 페이지는 query의 성공 문구를 믿지 않고 `payment_id`만 완료 API에 전달한다.
- `order_name`은 서버 전용 정규화 함수가 선택한 PG의 UTF-8 byte 상한·금지 문자를 적용해 만든다. 작품·회차 표시 snapshot은 별도 필드로 보관한다.
- 공식 근거: [V2 결제 연동](https://developers.portone.io/opi/ko/integration/start/v2/checkout), [V2 webhook](https://developers.portone.io/opi/ko/integration/webhook/readme-v2?v=v2), [V2 REST API](https://developers.portone.io/api/rest-v2), [V2 결제 요청](https://developers.portone.io/sdk/ko/v2-sdk/payment-request?v=v2), [Python SDK](https://pypi.org/project/portone-server-sdk/).

### 계정 경계: 개발자 테스트 고객사와 작가 실판매 고객사를 분리한다

- M3 테스트 고객사·Store의 Owner는 개발자다. 개발자 본인 정보와 테스트 채널만 사용하고, 작가의 사업자등록증·대표자 정보·정산계좌를 입력하거나 실채널을 신청하지 않는다.
- M7에서 작가가 새 PortOne Owner 계정과 실판매 Store를 만들고 사업자 인증·전자결제 신청·정산계좌 등록을 직접 수행한다. 개발자는 비밀번호·secret을 공유받지 않고 작가가 생성한 Dev 계정으로 연동 업무만 수행한다.
- 개발자 테스트 고객사를 작가 고객사로 이름만 바꾸거나 외부 테스트 거래를 이관하지 않는다. `PAYMENT_ENVIRONMENT`, Store ID, channel key, API·webhook secret은 배포 설정으로 분리하고 주문에는 비밀이 아닌 당시 Store·channel·환경만 snapshot한다.
- staging과 production은 같은 migration을 쓰되 DB와 secret set을 분리한다. staging은 `test`, production은 `live`만 새 주문에 허용한다. 계정 소유자 이메일을 환경 판정 근거로 사용하지 않는다.
- 작가 계정의 테스트·실채널 스모크가 끝난 뒤 개발자 테스트 고객사의 신규 intent를 닫는다. `preparing|ready|cancel_pending|review_required`가 0이고 최근 paid 대사 창이 끝났는지 확인한 다음 webhook·scheduler를 중단하고 secret을 폐기한다. 그 뒤에만 개발자 테스트 계정을 삭제한다.
- PortOne Owner 탈퇴는 종속 Store·계정을 함께 삭제하고 이후 외부 재조회가 불가능해질 수 있으므로 먼저 삭제하지 않는다. 출시 후에도 테스트 결제는 회귀 검증에 필요하므로 계정은 삭제 대신 retired 테스트 계정으로 보관할 수 있다.
- `test|live`는 임시 기능 flag가 아니라 결제 승인과 권한의 영구 provenance다. production 행이 모두 `live`여도 컬럼과 제약을 제거하지 않는다.
- 공식 근거: [전자결제 신청 전 개발 연동 테스트](https://developers.portone.io/opi/ko/console/guide/reg?v=v2), [Owner·Dev 계정과 탈퇴 영향](https://developers.portone.io/opi/ko/console/guide/account), [카카오페이 테스트 channel](https://help.portone.io/content/kakaopay), [토스페이 테스트 channel](https://help.portone.io/content/tosspay).

### 결정 2: 주문 생성·재시도·만료를 복구 가능한 상태 머신으로 둔다

```text
preparing ──pre-register 확인──→ ready ──검증 PAID──→ paid
    │                              │                    └── 환불·보상 ─→ cancel_pending ─→ cancelled
    └── pre-register 재시도 ───────┘
                                   └── 만료 전 재조회 ─→ expired ──늦은 PAID──→ paid

cancel_pending 실패 확정 ─→ paid (사용자 환불) | review_required (시스템 보상)
부분 취소·해석 불가 상태 ─→ review_required
```

- 주문은 DB에 `preparing`으로 먼저 commit한 뒤 transaction 밖에서 pre-register하고 `ready`로 바꾼다. pre-register 성공 뒤 DB 반영 실패는 같은 `payment_id`로 안전하게 재시도한다.
- 동일 사용자·회차·환경의 `preparing|ready` 주문은 하나만 허용한다. `ready` 재사용 창은 생성 후 30분이다. 만료 시 PortOne을 한 번 재조회해 미결제임을 확인한 뒤 `expired`로 바꾸며 다음 주문은 새 가격 snapshot을 쓴다.
- `FAILED`는 주문 terminal 상태가 아니라 결제 시도별 감사 이벤트다. 같은 `payment_id`에 후속 시도가 `PAID`가 될 수 있으므로 만료·실패 뒤에도 늦은 `PAID` 조회는 정상 검증 경로로 수렴시킨다.
- `preparing`, 오래된 `ready`, `cancel_pending`, `review_required`와 환불 창 168시간 + 여유 24시간인 최근 192시간의 `paid`를 bounded batch로 대사한다. `next_reconcile_at`, 횟수, 지수 backoff를 저장한다. 돈이 걸린 `cancel_pending`은 임의 retry 상한으로 버리지 않는다.
- 외부 조회를 시작할 때 본 로컬 상태는 전이 근거가 아니다. 응답을 받은 뒤 짧은 transaction에서 주문을 다시 읽고 허용된 from-status CAS만 실행한다. CAS loser는 현재 행을 다시 읽어 아래 표를 재평가하며, 늦게 도착한 외부 응답으로 상태를 회귀시키거나 이전 side effect를 재실행하지 않는다.

| 현재 로컬 상태 | 최신 PortOne 조회 | 다음 상태와 side effect |
|----------------|----------------------|-------------------------|
| `preparing|ready` | `not found|READY|PENDING|PAY_PENDING|FAILED` | 만료 전에는 현재 상태 유지·재대사한다. `FAILED`는 로그만 남긴다. `expires_at <= now`이면 같은 조회가 비승인을 확인한 때만 `expired`로 닫는다. |
| `expired` | `not found|READY|PENDING|PAY_PENDING|FAILED` | `expired` 유지. 새 주문과 합치지 않는다. |
| `preparing|ready|expired` | snapshot 일치 `PAID` + commit 시점 판매 가능 | 구매는 작품·회차·주문을 공통 lock 순서로 선점해 `paid` + 결과 1건을 같은 transaction에 commit한다. donation은 대상 공개성을 같은 transaction에서 재확인한다. |
| `preparing|ready|expired` | `PAID`지만 snapshot 불일치·비공개·판매 중지·삭제 | 결과를 만들지 않고 `cancel_pending(system_verification|system_unavailable)`으로 전환해 전액 보상 취소한다. 이 상태를 결제 성공 UI로 표시하지 않는다. |
| `preparing|ready|expired` | `CANCELLED` | `cancelled`, 구매·후원 결과 0건. |
| `paid` | `not found|READY|PENDING|PAY_PENDING|FAILED|PAID` | `paid` 유지. stale 응답으로 `ready|expired`로 회귀하거나 결과를 재삽입하지 않는다. 반복 불일치는 새 조회를 예약한다. |
| `paid` | `CANCELLED` | `cancelled`로 전환하고 존재하는 purchase를 `refunded`로 만든다. donation 행은 승인 감사 기록으로 남기고 order 취소가 refund 집계 사실이 된다. 환불 요청이 없어도 권한을 회수한다. |
| `cancel_pending` | `CANCELLED` 또는 전액 `SUCCEEDED` cancellation | `cancelled`; 사용자 환불이면 purchase/refund request까지 확정하고 시스템 보상이면 결과 0건을 확인한다. |
| `cancel_pending` | `PAID|READY|PENDING|PAY_PENDING|FAILED|not found` 또는 cancellation `REQUESTED` | `cancel_pending` 유지, 외부 현재 상태 재조회·동일 취소 재시도를 예약한다. `paid`로 자동 회귀하지 않는다. |
| `cancel_pending(user_refund)` | cancellation 실패 확정 + 최신 payment `PAID` | 명시적 예외로 `paid`, purchase `active`, refund request `action_required`를 함께 확정한다. timeout·outstanding은 실패 확정이 아니다. |
| `cancel_pending(system_*)` | cancellation 실패 확정 | `review_required`; 권한을 만들거나 `paid`로 되돌리지 않고 owner 고객 응대로 넘긴다. |
| `cancelled` | 어떤 값 | `cancelled` 유지. `PAID`가 반복 관측되면 자동 복구하지 않고 불변식 위반으로 owner·Sentry에 알린다. |
| 모든 비terminal 상태 | `PARTIAL_CANCELLED|VIRTUAL_ACCOUNT_ISSUED` 또는 알 수 없는 자금 상태 | `review_required`, purchase가 있으면 `review_required`로 닫고 owner에게 알린다. M3가 지원하지 않는 값을 성공으로 해석하지 않는다. |
| `review_required` | `CANCELLED` | `cancelled`, 존재하는 purchase를 `refunded`로 확정한다. |
| `review_required` | `CANCELLED` 외 값 | 자동으로 `paid` 복귀하지 않고 owner 수동 판단까지 격리한다. |

- `paid`와 `cancelled`는 위 표의 명시적 취소 전이를 제외하면 단조 상태다. 특히 stale `READY` 뒤 `paid → ready`, stale `PAID` 뒤 `cancelled → paid`, 시스템 보상 `cancel_pending → paid`는 금지한다. 사용자 환불의 취소 실패가 확정된 행만 표의 예외 전이를 허용한다.
- 서로 다른 주문 두 건이 같은 회차에서 모두 `PAID`면 활성 구매 UNIQUE의 loser 주문을 `cancel_pending(system_duplicate)`으로 commit한 뒤 안정적인 시스템 멱등 키로 전액 취소한다.
- 사용자에게는 `결제 확인 중`, `취소 확인 중`, `운영자 확인 필요`를 구분해 보여주며 확인 중에는 중복 재결제를 권하지 않는다.

### 결정 3: 가격·수단·환경은 서버 주문 snapshot으로 고정한다

- intent는 공개·미삭제·판매 중인 회차와 작품을 조회해 `episodes.price ?? works.episode_base_price`를 계산한다. paywall이 없는 회차는 주문을 만들지 않는다.
- 결제 확인 UI는 회차와 표시 금액, 즉시 제공·단순 변심 청약철회 제한·계약 불일치 예외를 보여준다. 동의 항목은 기본 미선택이며, 선택 뒤 `결제하고 바로 보기`를 눌러야 구매 intent를 만든다. 테스트 문구는 "결제 완료 후 전체 내용이 즉시 제공됩니다. 전체 내용 제공이 시작되면 단순 변심에 따른 청약철회가 제한됩니다. 콘텐츠가 표시·광고와 다르거나 계약 내용대로 제공되지 않은 경우는 제외됩니다."로 둔다.
- intent 요청의 확인 금액은 서버가 다시 계산한 현재 가격과 같을 때만 통과시키며, 클라이언트 금액을 결제 금액의 원천으로 쓰지 않는다. 구매 주문에는 서버가 선택한 `checkout_notice_version`과 `immediate_supply_consented_at`을 기록한다. M3 테스트 고지 버전은 `episode-immediate-v1`로 시작하고 문구가 바뀌면 새 버전을 쓰며 기존 주문 snapshot은 갱신하지 않는다. 후원 주문에는 두 값을 두지 않는다.
- paywall이 있는 회차의 실효 가격은 Day 0에 확인한 카드 테스트 하한 이상이어야 한다. 기존 0원 데이터는 M3 활성화 전 진단 쿼리로 찾고, admin 공개·수정 검증과 intent가 같은 하한을 적용한다. 0원 paywall을 구매나 무료 전문으로 암묵 처리하지 않는다.
- 기존 주문은 `expected_amount`와 30분 만료까지 가격을 보존한다. 이후 주문부터 새 가격을 사용한다.
- pre-register 뒤 `ready`로 바꾸는 transaction도 작품·회차가 여전히 공개·미삭제·판매 중인지 다시 확인한다. 그 사이 비공개·판매 중지·삭제가 이겼으면 결제 config를 반환하지 않고 주문을 `status='expired', needs_action_reason='content_unavailable'`로 닫는다. 이미 열린 결제창에서 늦은 `PAID`가 오면 상태 전이표의 시스템 보상 경로로 간다.
- intent의 결제수단은 `card|kakaopay|tosspay` allowlist이면서 현재 배포의 활성 capability여야 한다. 서버가 대응 channel key를 고르고, 조회 결과의 Store·`test|live`·currency·amount·channel·method를 snapshot과 대조한다. M3 test 환경은 세 수단 channel을 모두 구성해야 P0를 통과하며, channel이 빠진 수단은 UI와 intent에서 fail-closed로 닫고 M3 미완료로 남긴다. live capability는 M7의 작가 계약 MID 스모크 뒤 설정으로 연다.
- `PAID` 불일치는 권한을 만들지 않고 곧바로 `cancel_pending(system_verification)`으로 전환한다. 같은 주문 ID에서 파생한 멱등 키로 전액 취소하고, timeout·`REQUESTED`는 대사가 종결할 때까지 유지한다.
- 금액 불일치 보상에서도 서버 주문의 `expected_amount`는 바꾸지 않는다. 인증된 PortOne 단건 조회의 `amount.total`을 `provider_total_amount`에 기록하고 이를 전액 취소 snapshot과 취소 완료 금액의 기준으로 삼는다. 클라이언트 값이나 `amount.paid`는 이 총액의 대체 출처가 아니며, 양수 총액을 확인할 수 없으면 취소 금액을 추측하지 않고 `review_required`로 격리한다. 최초 snapshot은 재시도에서 다시 계산하지 않는다.
- 시스템 보상 취소가 최종 실패하면 주문을 `paid`로 되돌리지 않고 `review_required`로 격리한다. 돈은 결제됐지만 권한을 줄 수 없는 건으로 owner가 수동 PortOne 확인·고객 응대를 끝낼 때까지 남긴다.
- 취소를 시작할 때 16~256자 ASCII 멱등 키와 개인정보 없는 exact request snapshot을 주문에 한 번 저장한다. 재시도는 같은 키를 RFC 8941 quoted string으로 보내고 snapshot을 다시 계산하거나 다른 body에 재사용하지 않는다. `IDEMPOTENCY_OUTSTANDING_REQUEST` 409와 timeout은 비terminal이다. 매 재시도 전, 특히 PortOne 보장 창 3시간이 지난 뒤에는 결제를 먼저 재조회해 이미 전액 취소면 로컬만 확정하고 아직 취소 가능한 승인일 때만 같은 요청을 보낸다.
- `environment='test'` 주문은 수익·전환율 기본 집계에서 제외한다. owner가 `environment=test`를 명시한 화면에서만 TEST 배지와 함께 본다. 환경은 생성 뒤 바꾸지 않으며 계정 교체 때 기존 행을 live로 갱신하지 않는다.

### 결정 4: 결제 동기화는 모든 외부 성공을 닫힌 루프로 만든다

- 브라우저 complete, 서명 검증된 webhook, scheduler 대사, owner 재조회가 모두 `sync_payment(payment_id, source)`를 호출한다.
- 함수는 transaction 밖에서 PortOne을 조회하고, 짧은 transaction에서 주문 상태 CAS와 `purchases` 또는 `donations` insert, 감사 로그를 함께 commit한다.
- PortOne webhook의 connection/read timeout은 각각 30초지만 결제 REST 조회는 read 60초 이상이 권고되므로 webhook 요청 안에서 조회 완료를 기다리지 않는다. raw body·헤더 서명을 먼저 검증하고 `payment_webhook_receipts.webhook_id` UNIQUE와 `processed_at=NULL`인 durable receipt를 짧은 transaction에 commit한 뒤 2xx를 보낸다. commit 전에는 2xx를 보내지 않는다.
- scheduler는 미처리 webhook receipt를 bounded batch로 읽어 `sync_payment(..., source='webhook')`를 호출한다. 상태 전이와 receipt `processed_at`은 같은 transaction에서 commit하며, 조회 실패·crash면 NULL이 남아 다음 틱에 재시도된다. 중복 webhook은 기존 receipt를 확인하고 2xx, 알 수 없는 이벤트는 서명 검증 뒤 `ignored_at`을 기록하고 2xx다. 이 결제 전용 durable inbox는 범용 queue 도입이 아니다.
- 회차 구매의 활성 권한 UNIQUE가 충돌하면 외부 승인을 rollback으로 지우려 하지 않는다. loser 주문을 보상 취소 대상으로 commit한 뒤 외부 취소를 수행한다.
- webhook 유실 대비로 nonterminal 주문과 최근 `paid`를 주기적으로 재조회한다. PortOne 콘솔 직접 취소는 금지하고, 긴급 사용 시 즉시 owner 재조회를 실행한다. owner 화면의 수동 동작도 "PortOne 재조회"와 "보상 취소 재시도"뿐이며 임의 `paid/cancelled` 입력은 제공하지 않는다.
- 공식 webhook 최대 5회 재전송과 0·1·4·16·64·256분 backoff는 추가 복구선일 뿐 유일한 전달 보장이 아니다. 브라우저와 webhook 도달 순서를 가정하지 않고 durable receipt·scheduler·최근 paid 대사를 함께 둔다.
- 일반 카드 거절·사용자 취소는 감사 로그와 사용자 안내만 남긴다. 금액 불일치, sync 불변식 위반, 장기 `cancel_pending`, 알 수 없는 상태만 구조화 로그와 Sentry에 비민감 ID·이전/다음 상태 tag로 보낸다.

### 결정 5: 구매 권한과 공유 카탈로그를 분리한다

- `resolve_episode_access(user, episode)`를 단일 권한 서비스로 두고 content 반환, 완독 저장, 작품 개인 상태, 환불 중 잠금을 모두 같은 `unavailable|preview|full` 판정으로 통일한다.
- `full`은 paywall이 없는 공개 회차 또는 `purchases.status='active'`이고 purchase·order 환경이 현재 `PAYMENT_ENVIRONMENT`와 일치하는 구매자다. 활성 구매자는 작품·회차의 일반 `is_published=false` 뒤에도 full을 유지한다. 공개 paywall 회차에 같은 환경의 활성 구매가 없으면 `preview`, 비구매 비공개·soft delete·긴급 운영 차단이면 `unavailable`이다.
- `GET /works/{id}`와 Astro SSR은 지금처럼 공개 데이터만 반환하고 60초 공유 캐시를 유지한다. 항상 false인 공개 `EpisodeSummary.is_purchased`는 제거한다.
- 작품 상세의 구매 배지·진행률만을 위한 새 개인화 endpoint는 만들지 않는다. 기존 로그인 전용 `GET /works/{id}/progress`의 no-store 응답을 `purchased_episode_ids`, `completed_episode_ids`, 마지막 회차 진행률까지 확장한다. 아래 viewer-bootstrap은 공개 catalog에서 숨겨진 기존 구매의 route 해석용이며 작품 목록 개인화 API가 아니다.
- 작품 상세는 공개 회차 목록을 SSR하는 하나의 `WorkExperience` React island가 hydration 뒤 개인 상태를 한 번만 조회해 구매 배지·진행률·CTA를 함께 갱신한다. `login_hint` 판별은 서버 렌더나 `useState` initializer가 아니라 `useEffect` 안에서 `document.cookie`를 읽어 수행한다. N개 회차별 요청과 SSR 개인 데이터 삽입을 금지한다.
- `GET /episodes/{id}/content`는 optional auth를 사용하고 `access_scope: unavailable|preview|full`을 반환한다. access 쿠키가 없거나 만료·무효이면 이 endpoint 자체는 익명으로 안전하게 투영하며, 유효 사용자로 확인되지 않은 요청에는 절대 full을 주지 않는다. 안전 투영 뒤 실제 응답에 남은 image key만 presign한다.
- 뷰어의 첫 content 요청은 `useEffect`에서 `login_hint`를 읽은 뒤 분기한다. 힌트가 없으면 익명 content를 바로 요청한다. 힌트가 있으면 기존 보호 API `GET /auth/me`를 공용 API wrapper로 먼저 호출해 401에서 refresh 1회와 원요청 재시도를 끝낸 뒤 content를 요청한다. access 15분 만료 + 유효 refresh는 새 access·refresh·`login_hint`를 받고 full로 이어지며 로그아웃시키지 않는다.
- `/auth/me`의 refresh까지 최종 401이면 `/auth/refresh` 응답이 기존 `clear_auth_cookies`로 access·refresh·`login_hint`를 함께 만료시키고, 뷰어는 content를 익명으로 한 번 요청해 preview로 폴백한다. access 만료만으로는 이 clear 경로를 타지 않는다. 위조·stale `login_hint`는 refresh 시도만 유발할 뿐 인가 근거가 아니며 full을 열지 못한다. 로그인 라벨의 수명 원천은 계속 access가 아닌 refresh와 함께 가는 힌트 쿠키다.
- 현재 Astro 뷰어 page는 공개 catalog로 episode UUID를 먼저 찾으므로 resolver만 바꾸면 비공개 구매가 island mount 전에 404가 된다. `GET /works/{work_id}/episodes/{public_id}/viewer-bootstrap` no-store를 추가해 공개 회차 또는 같은 환경의 활성 구매자에게만 최소 episode UUID·표시 snapshot을 반환한다. 비구매 비공개·soft delete는 본문과 존재를 숨긴 404이며, 비공개 응답은 다른 비공개 회차 navigation을 노출하지 않는다.
- Astro route는 공개 catalog 성공 시 기존 SSR shell을 유지한다. 공개 조회 404이면 작품·회차 메타를 넣지 않은 client-only fallback shell만 렌더하고, island가 `useEffect` 세션 복구 뒤 viewer-bootstrap을 호출한다. `/my/purchases`의 작품·회차 URL은 이 경로로 직접 연결되어 일반 비공개 뒤에도 full에 도달한다. 공유 캐시 HTML에는 구매 여부·비공개 메타가 없다.
- M2의 객체별 presigned URL TTL 600초, 진입 시 전량 요청, 만료 URL 재발급 계약을 유지한다. 구매자라는 이유로 TTL을 늘리거나 고정 공개 URL·서명 쿠키를 도입하지 않는다.
- 결제 복귀에서 구매 상태가 active로 검증되면 뷰어는 별도 후속 버튼 없이 full content를 자동 요청한다. 결제 완료나 purchase 생성만으로 열람 처리하지 않는다. 복귀가 끊겼거나 content 요청 전 실패하면 `first_viewed_at`은 NULL로 남는다.
- 자동 full 요청은 결제 복귀 뒤 활성 뷰어 또는 사용자가 직접 진입한 회차 뷰어에서만 시작한다. 링크 prefetch, 공유 SSR, 작품 개인화 조회와 백그라운드 polling은 content endpoint를 호출하거나 `first_viewed_at`을 바꾸지 않는다.
- full 문서의 presign 성공 뒤 응답 직전에 purchase가 active인지 다시 확인한다. `first_viewed_at`이 이미 있으면 active 상태에서 재열람을 허용한다. 처음이면 `status='active' AND first_viewed_at IS NULL` 조건부 UPDATE로 발급을 기록하고, 이 UPDATE의 rowcount가 0이면 만들어 둔 full 문서와 URL을 버리고 409를 반환한다. DB commit 실패 때도 full 응답을 보내지 않는다. 첫 발급 commit 뒤 클라이언트 연결이 끊긴 경우는 재열람으로 복구한다.

### 결정 6: 판매 후 콘텐츠 제공 계약을 보존한다

- `episodes.sales_paused_at`을 추가한다. 판매 중지는 신규 intent만 막고 공개 preview와 기존 활성 구매의 전문은 유지한다.
- 일반 비공개는 공개 카탈로그·preview·신규 intent만 닫고 기존 활성 구매의 direct viewer·구매 내역 full은 유지한다. soft delete는 route 자체를 없애므로 `active|refund_pending|review_required` 구매가 하나라도 있으면 409로 막는다. 긴급 법적 차단은 해당 구매의 환불·고객 고지와 함께 별도 M7 운영 SOP로 처리하며 M3에서 조용히 권한을 없애지 않는다.
- 구매 확정과 판매 중지·일반 비공개·soft delete는 DB에서 단일 승자를 정한다. 모든 경로는 `works → episodes → payment_orders → purchases` 순서로 필요한 행을 잠근다. 작품 비공개·삭제는 Work를, 회차 판매 중지·비공개·삭제는 Work 다음 Episode를 먼저 잠근다. 구매 sync도 같은 순서로 잠근 뒤 판매 가능성을 다시 검사하고 purchase를 만든다.
- 판매 중지·비공개·삭제 transaction이 먼저 이기면 해당 범위의 `preparing|ready` 구매 주문을 `status='expired', needs_action_reason='content_unavailable'`로 바꾸고 즉시 대사를 예약한다. 뒤늦게 외부 `PAID`가 확인되면 purchase 0건 + `cancel_pending(system_unavailable)` 전액 보상으로 간다. 구매 transaction이 먼저 이기면 이후 판매 중지·일반 비공개는 허용하되 그 purchase의 full은 유지하고, soft delete는 409다.
- 가격·제목·본문 수정은 기존 주문 금액과 구매 권한에 영향을 주지 않는다. 구매 내역은 주문 시점 제목·금액 snapshot을 표시한다.
- 완독은 회차 identity 기준이라 발행본 수정 뒤에도 유지한다. 콘텐츠 버전별 완독과 구매 snapshot 원고는 만들지 않는다.

### 결정 7: 환불은 같은 권한 행의 단일 승자로 처리한다

- 잠정 자격은 `now < paid_at + 168 hours`, `first_viewed_at IS NULL`, `purchases.status='active'`다. 정확히 168시간 경계부터 불가다. 표시는 KST로 하되 계산은 UTC instant로 한다. 이 정책은 M7 법무 검토 전 테스트 계약이다.
- 결제 전에는 "전체 내용 제공이 시작되면 단순 변심에 따른 청약철회가 제한됨"을 명시하고, 구매 내역의 환불 요청 UI는 이미 전문이 발급된 구매가 테스트 환불 대상이 아님을 안내한다. 요청 시와 owner 승인 시 자격을 다시 확인한다. 계약 불일치·미제공 등 법정 예외를 포괄적인 `환불 불가` 문구로 막지 않는다.
- 전문 첫 발급은 `active → active + first_viewed_at`, 환불 승인은 `active + first_viewed_at NULL → refund_pending`을 같은 purchase 행에서 조건부 UPDATE한다. 둘이 동시에 시작해도 PostgreSQL이 같은 행을 직렬화하고 loser는 rowcount 0으로 끝난다.
- 승인 transaction은 `refund_requests.pending → processing`, `purchases.active → refund_pending`, `payment_orders.paid → cancel_pending` CAS를 함께 commit한다. reject는 `pending → rejected`만 허용하며 processing 이후에는 이길 수 없다.
- PortOne 취소 중 DB transaction을 잡지 않는다. 최초 요청과 재시도는 `refund_requests.id`에서 파생한 16~256자 ASCII `Idempotency-Key`와 주문에 고정한 exact request snapshot을 쓴다. timeout·`IDEMPOTENCY_OUTSTANDING_REQUEST`·3시간 보장 창 경계는 결정 3의 선조회 후 재시도 계약을 따른다.
- 전액 취소 확인 뒤 주문 cancelled, 구매 refunded, 요청 approved를 한 transaction에서 확정한다. 취소 실패가 확정되면 주문 paid·구매 active로 되돌리고 요청은 `action_required`로 남긴다. timeout·REQUESTED는 cancel_pending/refund_pending을 유지한다.
- 결과 메일은 환불 DB 확정 transaction에서 `notification_status=pending`으로 예약하고, commit 뒤 즉시 1회 시도한다. 실패해도 성공한 환불을 5xx로 바꾸지 않으며 scheduler가 `next_notification_at` 기준 bounded batch로 재시도한다. 성공은 `sent + notified_at`, 반복 실패는 `action_required`로 owner 목록에 남기고 같은 메일의 수동 재시도를 제공한다. 범용 알림 outbox는 만들지 않는다.
- 부분 환불, 읽은 회차 환불, 후원 환불 자동화, chargeback 자동 대응은 제외한다.

### 결정 8: 이미지 치수와 완독은 P1 경험 계층이다

- `episodes.image_keys`는 업로드 소유권 매니페스트, `content`는 표시 구성이라는 현재 의미를 유지하고 `episode_images(episode_id, key, width, height, byte_size)`를 추가한다.
- 새 업로드는 변환된 WebP bytes의 width·height·byte_size를 R2 성공 뒤 image_keys 변경과 같은 DB transaction에 저장한다.
- 기존 데이터 백필은 공개·비공개·draft를 포함해 `episodes.image_keys`가 참조하는 모든 key가 대상이다. R2 다운로드 중 transaction을 열지 않고 bounded concurrency 4, batch upsert, 재실행 가능, 누락·손상 key 목록과 성공/실패 합계를 출력하며 실패가 있으면 non-zero로 끝낸다.
- 백필 완료 전 응답의 width·height는 선택 필드로 두고 기존 렌더를 유지한다. 환경별 100% 검증 뒤 frontend 공간 예약을 기본으로 켠다. `episode_images.episode_id` FK 삭제 인덱스를 둔다.
- 로그인 사용자의 `viewer_progress`에 `progress_bp(0..10000)`와 `completed_at`을 추가한다. 복원용 `page_no + block_offset_bp`는 유지하고 진행률은 `greatest`로 역행을 막는다.
- `completed=true`는 `access_scope=full`인 문서의 마지막 최상위 블록 끝 도달일 때만 저장한다. 무료 전문은 로그인·게스트 모두 가능하고 유료 preview 끝은 불가능하다.
- 게스트 localStorage에도 `progressBp`, `completed`를 하위 호환 기본값과 함께 추가한다. 로그인 전환 시 자동 병합하지 않으며 보안·권한 근거로 쓰지 않는다.
- 작품 진행률 분자는 완독 회차 수다. 최근 회차가 미완독이면 이어 보기, 완독이고 다음 화가 있으면 다음 화, 마지막 회차 완독이면 마지막 화 다시 보기다.

### 결정 9: 후원은 같은 자금 파이프라인에서 권한과 분리한다

- 로그인·이메일 인증 사용자가 1,000원, 3,000원, 5,000원 중 하나를 고른다. 금액은 서버 allowlist로 검증한다.
- 대상은 작가 또는 공개 에피소드 하나다. 게시글 후원, 공개 피드, visibility는 만들지 않는다.
- 메시지는 최대 500자이며 owner 전용이다. 주문 snapshot과 검증된 `PAID`를 기준으로 `donations`를 한 번 insert하고 구매 권한은 바꾸지 않는다.
- 진입점은 작품 상세의 작가 후원과 full 회차 완독 지점의 에피소드 후원 두 곳으로 제한한다.

### 결정 10: 매출은 승인·취소 사실과 환경을 분리해 집계한다

- 금액은 정수 KRW다. `gross`는 검증된 승인 시점의 구매·후원, `refund`는 확인된 전액 취소, `net=gross-refund`다. `cancel_pending`은 승인 사실을 지우지 않으므로 취소 확인 전까지 gross에 남고 refund에는 들어가지 않는다.
- P0 화면은 구매 gross/refund/net과 대사 필요 주문만 제공한다. P1에서 후원, 작품·회차·결제수단 breakdown과 첫 구매 전환율을 확장한다.
- 기본 query는 `environment=live`이며 test 주문을 제외한다. 테스트 환경은 명시적 filter와 TEST 배지로만 조회한다. 전환율도 test를 제외한다.
- 일/주/월 경계는 Asia/Seoul을 UTC half-open 범위로 바꿔 조회한다. PG 수수료·정산 입금·세금은 표시하지 않는다.
- 매출·환불·후원·구매내역 API와 대응 SSR은 모두 no-store다. admin은 `require_owner`이며 reader·moderator는 403이다.

---

## 데이터 모델 초안

### `episode_images`

| 컬럼 | 계약 |
|------|------|
| `id` | UUID PK |
| `episode_id` | episodes FK, `ON DELETE CASCADE`, 삭제 조회 index |
| `key` | TEXT UNIQUE, R2 원고 key |
| `width`, `height` | INTEGER NOT NULL, `> 0` |
| `byte_size` | BIGINT NOT NULL, `> 0` |
| `created_at`, `updated_at` | UTC timestamptz |

### `payment_orders`

| 컬럼 | 계약 |
|------|------|
| `id`, `payment_id` | UUID PK, VARCHAR(64) UNIQUE 서버 ID |
| `user_id` | users FK RESTRICT, 5년 보존 |
| `kind`, `episode_id` | `episode_purchase|donation`, 구매면 episode 필수 |
| `expected_amount`, `currency` | INTEGER `> 0`, `KRW` CHECK |
| `provider_total_amount` | nullable INTEGER `> 0`, 인증된 PortOne 조회의 `amount.total`. 주문 예상 금액과 분리한 실제 총액 |
| `store_id`, `requested_channel_key`, `environment` | 주문 시 Store·channel·`VARCHAR(8) CHECK test|live` immutable snapshot |
| `order_name`, `item_title` | PG 안전 표시명, 사용자 표시 snapshot |
| `checkout_notice_version`, `immediate_supply_consented_at` | 구매 시 서버가 선택한 결제 고지 버전과 즉시 제공 동의 시각, donation은 NULL |
| `donation_message` | donation에서만 nullable VARCHAR(500) |
| `status` | `preparing|ready|expired|paid|cancel_pending|cancelled|review_required` |
| `provider_status`, `transaction_id`, `cancellation_id` | 마지막 검증 응답의 비민감 ID·상태 |
| `pg_provider`, `payment_method`, `easy_pay_provider` | 검증된 결제수단 breakdown snapshot |
| `receipt_url` | 검증된 URL만 저장 |
| `cancel_reason`, `cancel_idempotency_key`, `cancel_request_snapshot`, `cancelled_amount` | 보상·환불 수렴 정보. reason은 개인정보 없는 내부 code allowlist이고 exact JSONB·key와 함께 immutable |
| `expires_at`, `next_reconcile_at`, `reconcile_attempts`, `last_synced_at` | 생명주기·대사 |
| `needs_action_reason` | nullable 제한 enum/code, 원시 응답 금지 |
| `prepared_at`, `paid_at`, `cancelled_at`, `created_at`, `updated_at` | UTC timestamptz |

주요 제약:

- 구매는 `episode_id NOT NULL AND donation_message IS NULL`, 후원은 `episode_id`와 message가 각각 nullable인 kind CHECK
- 구매는 `checkout_notice_version`과 `immediate_supply_consented_at`이 NOT NULL이고 후원은 둘 다 NULL인 kind CHECK
- 취소 사유는 `system_verification|system_unavailable|system_duplicate|customer_refund`만 허용한다. 사유·멱등 키·snapshot은 모두 NULL이거나 모두 존재하고 `cancel_pending`에서는 필수다. 취소 묶음은 양수 `provider_total_amount`를 요구하며 snapshot은 Store·사유·해당 총액 기준 `amount`·`currentCancellableAmount`·사유별 requester의 정확한 5-key JSONB
- `cancelled_amount`는 NULL이거나 provider 총액이 존재하면서 `0 < cancelled_amount <= provider_total_amount`. 과다 승인 보상도 원래 `expected_amount`를 바꾸지 않고 전액 취소를 기록
- 구매 권한의 composite FK 대상인 `(id, user_id, kind, episode_id, environment, expected_amount, paid_at)` UNIQUE
- `(user_id, episode_id, environment) WHERE kind='episode_purchase' AND status IN ('preparing','ready')` partial unique
- `(environment, status, next_reconcile_at)`, `(user_id, environment, created_at DESC)`, `(episode_id)` index

### `purchases`

| 컬럼 | 계약 |
|------|------|
| `id`, `payment_order_id` | UUID PK, payment_orders composite FK의 선두 열이며 주문당 UNIQUE |
| `user_id`, `episode_id` | FK RESTRICT |
| `payment_order_kind` | `episode_purchase` 고정 CHECK. purchase 유형이 아닌 FK provenance discriminator |
| `environment` | 주문에서 복사한 `VARCHAR(8) CHECK test|live` immutable snapshot |
| `status` | `active|refund_pending|refunded|review_required` |
| `amount`, `paid_at` | 주문 snapshot |
| `first_viewed_at` | 최초 full 응답 발급 시각 |
| `refunded_at`, `refund_amount` | 전액 취소 확인 뒤 기록 |

`(payment_order_id, user_id, payment_order_kind, episode_id, environment, amount, paid_at)` composite FK가 참조 주문의 ID·사용자·`episode_purchase` kind·회차·환경·금액·결제 시각과 모두 일치하는 권한만 허용한다. 주문 `status`는 취소 전이를 위해 FK에서 제외하고, purchase 생성 시 `paid` 확인은 공통 sync transaction이 강제한다. `(user_id, episode_id, environment) WHERE status IN ('active','refund_pending','review_required')` partial unique가 같은 환경의 중복 권한과 환불 중 재구매를 막는다. test 구매는 live 재구매를 막지 않는다. 권한 조회는 purchase와 order 환경이 모두 현재 배포 환경과 일치하는지 확인한다. 전편 구매용 `purchase_type`, `bundle_id`는 만들지 않는다.

### `payment_webhook_receipts`

| 컬럼 | 계약 |
|------|------|
| `id`, `webhook_id` | UUID PK, 검증된 Standard Webhooks `webhook-id` UNIQUE |
| `payment_id`, `event_type` | nullable 결제 ID와 길이 제한 event명. 알려진 결제 event만 sync하고 원시 body 저장 금지 |
| `received_at`, `processed_at`, `ignored_at` | 수신·sync 완료·알 수 없는 event 처리 시각 |
| `attempts`, `next_attempt_at` | bounded scheduler claim·backoff |

서명 검증과 receipt insert가 끝나기 전에는 2xx를 반환하지 않는다. 처리 중 crash면 `processed_at`이 NULL이라 재시작 뒤 다시 잡히고, 상태 전이 commit과 처리 완료 표시는 같은 transaction이다.

### `payment_logs`

| 컬럼 | 계약 |
|------|------|
| `id`, `payment_order_id` | UUID PK, payment_orders FK |
| `webhook_receipt_id` | nullable receipt FK, webhook source 감사 추적 |
| `source` | `browser|webhook|reconcile|admin` |
| `event_type`, `from_status`, `to_status`, `provider_status` | 비민감 상태 |
| `failure_code` | nullable 제한 code, PII·원시 payload 금지 |
| `created_at` | UTC timestamptz |

### `refund_requests`

| 컬럼 | 계약 |
|------|------|
| `id`, `purchase_id`, `requested_by` | UUID PK와 FK |
| `reason`, `detail` | enum + 최대 1,000자 |
| `status` | `pending|processing|approved|rejected|action_required` |
| `resolved_by`, `admin_note` | nullable owner FK + 최대 1,000자 |
| `notification_status` | `none|pending|sent|action_required` CHECK |
| `notification_attempts`, `next_notification_at`, `notified_at` | 결과 메일 재시도·확정 시각 |
| `requested_at`, `resolved_at`, `updated_at` | UTC timestamptz |

한 구매의 `pending|processing|action_required` 요청은 하나만 허용한다. 승인·거부 확정 때 메일 상태를 `pending`으로 같은 transaction에 기록하고, 실패한 발송은 환불 결과와 분리해 재시도한다.

### `donations`

| 컬럼 | 계약 |
|------|------|
| `id`, `payment_order_id` | UUID PK, payment_orders FK UNIQUE |
| `user_id`, `episode_id` | user FK, nullable episode FK |
| `amount`, `message`, `paid_at` | allowlist 금액, owner 전용 500자, UTC 시각 |

### 기존 테이블 확장

- `episodes.sales_paused_at TIMESTAMPTZ NULL`
- `viewer_progress.progress_bp INTEGER NOT NULL DEFAULT 0 CHECK 0..10000`
- `viewer_progress.completed_at TIMESTAMPTZ NULL`

결제·계약 레코드는 5년 보존한다. 탈퇴 사용자는 기존 정책대로 익명화하고 FK는 유지한다. `payment_logs`는 원시 응답 저장소가 아니다.

---

## API 계약 초안

| Method | Path | 권한·캐시 | 역할 |
|--------|------|-----------|------|
| POST | `/payments/episode-intents` | 이메일 인증, 10회/분, no-store | 확인 금액·즉시 제공 동의 검증 + 서버 snapshot + pre-register + 결제 config |
| POST | `/payments/donation-intents` | 이메일 인증, 10회/분, no-store | allowlist 후원 snapshot |
| POST | `/payments/{payment_id}/complete` | 주문 소유자, 20회/분, no-store | PortOne 재조회·멱등 sync |
| POST | `/payments/webhooks/portone` | 공개, raw 서명 필수 | durable receipt commit 뒤 2xx, scheduler가 같은 sync 호출 |
| GET | `/works/{work_id}/progress` | 로그인, no-store | 기존 진행 응답 + 구매·완독 상태 |
| GET | `/works/{work_id}/episodes/{public_id}/viewer-bootstrap` | optional auth, no-store | 공개 또는 활성 구매 회차의 최소 viewer 식별·표시 정보, 비구매 비공개 404 |
| GET | `/episodes/{episode_id}/content` | optional auth, no-store | 무효 access는 익명 처리, unavailable·preview·full 안전 문서 |
| PUT | `/episodes/{episode_id}/progress` | 로그인, no-store | 복원 앵커·비역행 진행률·완독 |
| GET | `/my/purchases` | 로그인, no-store, 20건 페이지 | 주문 snapshot·권한·환불·영수증 |
| POST | `/purchases/{id}/refund-requests` | 구매자, no-store | 168시간·미발급 조건 요청 |
| GET | `/admin/refund-requests` | owner, no-store | 상태별 환불 요청 목록 |
| POST | `/admin/refund-requests/{id}/approve` | owner, no-store | request·purchase·order CAS 뒤 취소 시작 |
| POST | `/admin/refund-requests/{id}/reject` | owner, no-store | pending 요청만 거부 |
| POST | `/admin/refund-requests/{id}/retry` | owner, no-store | 같은 멱등 키로 미수렴 취소 재시도 |
| GET | `/admin/revenue` | owner, no-store | 환경·기간·group별 gross/refund/net |
| GET | `/admin/donations` | owner, no-store | 후원·메시지 페이지 |
| POST | `/admin/payments/{id}/sync` | owner, no-store | PortOne 재조회 또는 보상 취소 재시도 |

공통 오류는 401 로그인, 403 이메일·소유권·owner·full 권한, 404 존재 은닉, 409 상태 race·이미 구매·구매가 남은 soft delete, 422 지원하지 않는 값, 502/503 PortOne 장애다. optional content의 인증 부재·만료 자체는 401이 아니라 안전한 익명 투영이며, 보호 API의 401만 공용 wrapper가 refresh한다. 장애 응답은 로컬 상태를 재시도 가능하게 남긴다.

---

## 구현 그룹과 완료 증거

### 0. 정본 문서·외부 준비

- 이 PR에서 `DECISIONS.md`, `PRD.md`, `DB_SCHEMA.md`, 마일스톤 README와 M2 인계를 동기화한다.
- 개발자 소유 PortOne 테스트 key와 카드·카카오페이·토스페이 channel, 결제 하한, 공개 HTTPS 경로는 C 실연동 전에 확인한다. 세 수단의 직연동 테스트 channel과 redirect를 M3에서 검증하고 계약·심사를 거친 실 MID만 M7 gate로 넘긴다.
- 완료 증거: 정본 간 실행 순서·V2 용어·schema·범위 제외 충돌 0건.

### A. 이미지 metadata

- `episode_images`와 업로드 저장, 전 데이터 백필, 선택적 width·height·byte_size 응답을 구현한다.
- 완료 증거: 재실행 0중복, 모든 image_keys 대응 metadata, 누락·손상 시 non-zero, R2 I/O 중 열린 transaction 0.

### B. 완독·작품 경험

- A와 F 뒤 `progress_bp/completed_at`, guest 호환, `WorkExperience` 단일 island, CTA를 구현한다.
- 완료 증거: 무료 full·구매 full만 완독, preview 미완독, 진행률 비역행, 개인화 요청 작품당 1회, SSR 개인 데이터 0.

### C. 결제 schema·PortOne adapter

- 주문·구매·webhook receipt·로그 모델과 첫 migration, SecretStr config, async REST·webhook adapter를 만든다. refund·donation 테이블은 G·H에서 각각 추가한다.
- 완료 증거: kind·status·environment CHECK와 partial unique, 작가·에피소드 후원 target, Purchase-order 7열 provenance FK, migration 왕복, test 구매 뒤 같은 사용자·회차 live 주문 허용, 세 REST endpoint의 정확한 URL, typed·일반 404 분리, outstanding 409 분류, `read=65초`·unknown response fake, 취소 key·snapshot 고정, secret 노출 0, 설정된 V2 API secret의 읽기 전용 실제 GET.
- **완료 (2026-09-01, 2026-09-03·09-05 리뷰 보강, 2026-09-11 금액 불일치 수정, 2026-09-12 최종 자동검증)**: 결제 테이블 4개와 revision `d0c3a4b5e6f7`, `httpx` REST adapter, raw webhook verifier를 구현했다. PostgreSQL 통합 테스트 23개와 adapter 단위 테스트 20개, scratch DB `upgrade → check → downgrade → upgrade → check`, Backend 전체 gate 578개가 통과했다. 리뷰에서 실제 API hostname과 에피소드 후원 target CHECK를 바로잡은 뒤, Purchase-order provenance composite FK, typed 404·outstanding 409 분류, 복구 가능한 `cancel_pending` bundle과 PII 없는 exact snapshot을 보강했다. 2026-09-11 `provider_total_amount` 금액 분리와 취소 금액 범위 CHECK를 보강했다. 상세는 [IMPLEMENTATION_PAYMENT_FOUNDATION.md](../MODULES/BE/Payment/IMPLEMENTATION_PAYMENT_FOUNDATION.md)를 따른다.

### D. intent 생명주기

- preparing→ready, pre-register crash 복구, 30분 재사용·만료, 가격·수단·channel 검증, fail-closed kill switch를 구현한다. `payments_accept_new` 기본은 false이고 true인데 Store·channel·secret·공개 URL이 빠지면 기동을 거부한다. false여도 webhook·대사·열람·환불은 계속 돈다.
- 완료 증거: 오래된 가격 주문 미재사용, 0원 paywall 차단, 동일 intent race 1행, pre-register 성공 뒤 DB 실패 복구, 비공개가 먼저 이긴 ready 응답·구매 0건.

### E. 공통 sync·webhook·대사

- 브라우저·webhook receipt worker·scheduler 대사·owner 공통 sync와 보상 취소를 구현한다.
- 완료 증거: 같은 payment_id 4경로 1결과, 서로 다른 payment_id 동시 PAID는 1구매+1취소, webhook receipt commit 전 2xx 0·commit 뒤 crash 재처리, stale 외부 응답 상태 회귀 0, 앱 재시작 뒤 cancel_pending 수렴.

### F. 구매 권한·전문·최소 UI

- 결제 전 즉시 제공 고지·동의 snapshot, 중앙 access resolver, private-purchase viewer bootstrap, optional auth content, `useEffect` 세션 복구, 자동 첫 전문 발급 CAS, 결제 redirect·구매 내역을 구현한다.
- 완료 증거: 미동의 intent 422, 표시 금액 stale 시 결제창 0, 미구매 paid key presign 0, 환불 winner일 때 full 문서·URL 응답 0, 구매 복귀 뒤 추가 클릭 없는 자동 전문 발급, access 만료 + refresh 유효면 full·쿠키 clear 0, stale hint + refresh 만료면 세 쿠키 clear·preview·full 0, 일반 비공개 뒤 구매 내역 direct link full·비구매 HTML/API 메타 0, 개인 SSR no-store.

### G. 환불·기본 매출

- refund_requests, 사용자 요청, owner CAS 승인·거부·취소 복구·지속 가능한 결과 메일, 구매 gross/refund/net·대사 목록을 구현한다.
- 완료 증거: 첫 발급·승인 단일 승자, approve·reject 단일 승자, 168시간 경계, cancel timeout·outstanding·3시간 경계 재시도, 메일 실패·재시작 뒤 sent 또는 action_required 수렴, test 기본 제외.

### H. 후원

- donations, 두 진입점, 세 금액·메시지·owner 목록을 구현한다.
- 완료 증거: payment_id당 1행, 구매 권한 무변경, 메시지 로그·비owner 응답 노출 0.

### I. 상세 수익·운영·M3 종료

- 후원 합산, 작품·회차·수단 breakdown, 전환율, TEST filter와 전체 문서·gate를 마감한다.
- 완료 증거: `gross-refund=net`, cancel_pending 중 gross 유지, KST half-open 경계, owner 외 전 endpoint 403.

---

## 권장 PR 순서

1. 현재 docs PR: foundation과 정본 동기화
2. `be/feat/m3-payment-schema-adapter`: C
3. `be/feat/m3-payment-intents`: D
4. `be/feat/m3-payment-sync`: E
5. `common/feat/m3-purchase-access`: F
6. `common/feat/m3-refunds-revenue`: G, 여기서 P0 gate
7. `be/feat/m3-image-metadata`: A, 외부 key 준비와 무관해 2~6 사이 병렬 가능
8. `common/feat/m3-viewer-completion`: B
9. `common/feat/m3-donations`: H
10. `common/feat/m3-revenue-ops`: I

스택 PR은 사용하지 않는다. 선행 PR이 main에 머지된 뒤 최신 main에서 다음 브랜치를 만든다. 각 PR은 해당 `IMPLEMENTATION_*.md`, API 타입 생성물과 영향받는 backend/frontend/admin gate를 함께 갱신한다.

---

## 검증 게이트

### 자동 gate

```bash
cd backend && uv run ruff format --check . && uv run ruff check . && uv run pytest
pnpm --filter frontend lint && pnpm --filter frontend astro check && pnpm --filter frontend test && pnpm --filter frontend build
pnpm --filter admin lint && pnpm --filter admin test && pnpm --filter admin build
```

마이그레이션 PR은 scratch DB에서 `upgrade head → alembic check → downgrade <직전 revision> → upgrade head`를 수행한다. admin API 변경 PR은 `generate:types`와 생성물 diff를 확인한다.

환경 경계 테스트는 같은 사용자·회차에 test·live 활성 구매가 각각 1행 공존하는지, live resolver가 test purchase·order를 무시하는지, 주문 생성 뒤 환경 변경이 거부되는지, 설정 Store·channel과 조회 환경 불일치가 권한 0·보상 취소로 끝나는지를 확인한다. staging과 production은 같은 migration을 적용하고 다른 DB·secret set을 쓰는 배포 구성을 검증한다.

동시성 테스트는 반드시 독립 DB session 두 개를 사용한다. 각 코루틴이 선행 SELECT를 끝낸 뒤 위험한 조건부 UPDATE 직전 Barrier에 도착하고, 둘 다 도착한 뒤 UPDATE를 동시에 시작하게 한다. 같은 session의 순차 실행이나 SELECT 전에 둔 Barrier는 race 증거가 아니다. 최소 시나리오는 다음과 같다.

- 동일 주문의 browser·webhook `ready → paid`
- 서로 다른 주문의 같은 회차 `PAID` 두 건
- 같은 회차의 `PAID` sync와 작품·회차 일반 비공개 전환을 각각 검증: sync 선점이면 purchase active + 비공개 뒤에도 full, 비공개 선점이면 purchase 0 + `cancel_pending(system_unavailable)`
- 같은 회차의 `PAID` sync와 작품·회차 soft delete를 각각 검증: sync 선점이면 delete 409, delete 선점이면 purchase 0 + 전액 보상
- `purchases.active + first_viewed_at NULL`에서 전문 첫 발급과 환불 승인
- 같은 refund request의 approve와 reject
- cancel 성공 뒤 DB 실패와 앱 재시작 대사

상태 전이 테스트는 외부 adapter 응답 순서를 고정해 `stale READY after paid`, `PAID after expired`, `stale PAID after cancelled`, `CANCELLED after paid`, `PAID와 CANCELLED 조회 동시 완료`, 알 수 없는 새 enum을 각각 검증한다. 기대값은 단조 상태, 허용된 늦은 승인, 권한 회수·격리 중 하나이며 stale 응답으로 상태가 되돌아가는 경우는 0건이어야 한다.

### 사용자 브라우저 확인

- 공개 HTTPS PC 카드 결제창 완료와 모바일 redirect 복귀
- 카카오페이 `TC0ONETIME`·토스페이 `tosstest` 직연동 테스트 channel의 PC 결제창 완료와 모바일 redirect 복귀. 작가 계약 실 MID 스모크만 M7에서 확인
- 결제 전 비선택 동의·고지 문구·서버 금액과 `결제하고 바로 보기`, 결제 뒤 추가 클릭 없는 전문 자동 표시
- 결제 성공 뒤 복귀·content 요청 실패에서는 `first_viewed_at` 미기록, 새로고침·다른 탭 직접 진입에서는 전문 발급과 권한 유지
- access 15분 만료 뒤 새로고침에서 refresh가 자동 회전하고 로그인 라벨·구매 full이 유지되며 로그인 화면으로 이동하지 않음. refresh까지 만료된 stale hint는 full 없이 익명 preview로 폴백
- 미구매·로그아웃의 유료 구간 Network 응답·presign 부재
- 결제 완료 뒤 작품·회차 일반 비공개에서도 구매 내역 direct viewer full 유지, 비공개가 먼저 끝난 열린 결제는 성공 UI 없이 취소 확인 중으로 수렴
- 첫 전문 발급 전 환불 가능, 발급 뒤 불가, owner 승인 뒤 잠금·재구매
- 결제 확인 중·취소 확인 중·운영자 확인 필요와 TEST 배지
- 긴 이미지 공간 예약, guest/login 완독, preview 미완독, CTA
- 작가·에피소드 후원과 owner 메시지, 수익 환경·기간 filter

---

## 완료 체크리스트

### 완료 판정 규칙

- 마일스톤 체크리스트는 통합 결과를 판정하는 지도다. 각 구현 그룹을 시작할 때 `task_harness.local`에 현재 단일 goal의 세부 단계와 DONE EVIDENCE를 적고 검증한다.
- 체크 항목은 관련 그룹 ledger의 DONE EVIDENCE가 모두 통과한 뒤에만 완료한다. `PARTIAL`, `BROKEN`, 사유와 후속 판정이 없는 `NOT RUN`이 하나라도 남으면 체크하지 않는다.
- ledger는 gitignore되고 다음 goal에서 교체되므로 영구 완료 증거가 아니다. 교체 전 테스트 수·핵심 시나리오·실패와 예외를 관련 `IMPLEMENTATION_*.md`, PR·CI 기록에 남기고, 마일스톤에는 M2처럼 날짜와 최종 결과를 요약한다.
- P0는 0·C~G의 DONE EVIDENCE와 P0 gate가 모두 통과해야 한다. M3 완료는 A~I의 DONE EVIDENCE, P0 gate, M3 완료 체크리스트가 모두 통과해야 한다.

### P0 gate

- [ ] **0·C 외부 연동**: 개발자 소유 PortOne V2 Store·API/webhook secret, 카드·카카오페이·토스페이 테스트 channel과 공개 FE/API/webhook HTTPS 준비
- [ ] **0·C 브라우저 결제**: 카드·카카오페이 `TC0ONETIME`·토스페이 `tosstest`의 PC 결제창 완료와 모바일 redirect 복귀, 서버 사후 검증 스모크
- [x] **C schema·adapter**: CHECK·partial unique와 test/live 공존, 작가·에피소드 후원 target, Purchase-order provenance FK, 복구 가능한 cancel bundle·PII 없는 exact snapshot, migration 왕복, 정확한 REST endpoint, typed 404·outstanding 409, SecretStr·65초 read timeout·unknown 응답 격리·secret 노출 0, 실제 API 읽기 전용 GET *(2026-09-01 완료, 2026-09-03·09-05 리뷰 보강, 2026-09-11 provider_total_amount 금액 분리와 취소 금액 CHECK 보강, 2026-09-12 최종 자동검증: pytest 578·focused 43, scratch 왕복·취소 3건/거부 4건)*
- [ ] **D 주문·intent**: 서버 가격·고지 snapshot, pre-register·사후 조회, 30분 재사용·만료와 오래된 가격·0원 paywall 차단
- [ ] **D fail-closed**: 결제 중지 중 신규 intent 차단·기존 후처리 유지, 필수 Store·channel·secret·공개 URL 누락 시 기동 거부, 동일 intent와 비공개 전환 race 단일 결과
- [ ] **E 공통 sync**: browser·webhook·reconcile·owner 4경로의 동시·재전송 1결과와 서로 다른 이중 `PAID`의 1구매·loser 보상 취소
- [ ] **E webhook·복구**: 서명 검증·durable receipt·30초 내 ack, commit 뒤 crash 재처리, 단조 상태 전이와 `cancel_pending`·timeout·외부 취소 복구 또는 격리
- [ ] **F 콘텐츠 권한**: 중앙 access resolver가 미구매·환불 처리 중 paid key·presign·full 문서를 반환하지 않고 개인 응답을 no-store로 유지
- [ ] **F 구매 경험·세션**: 결제 전 고지·비선택 동의 snapshot, 구매 unlock·전문 자동 발급·구매 내역·영수증, `useEffect` 힌트 복구와 access 만료 자동 refresh·stale hint 익명 폴백
- [ ] **F 비공개 구매 열람**: 일반 비공개 뒤 구매 내역 direct viewer full 유지, 비구매 HTML·bootstrap·content는 메타와 full 없이 404
- [ ] **D·E·F 판매 상태 race**: `PAID` sync·판매 중지·일반 비공개·soft delete가 단일 승자로 끝나고, 구매가 먼저면 full 유지·삭제 409, 비공개·삭제가 먼저면 구매 0·보상 취소
- [ ] **G 환불 race**: 첫 전문 발급·환불 승인과 같은 요청의 approve·reject가 각각 단일 승자로 끝남
- [ ] **G 환불 수명주기**: 잠정 168시간 전문 미발급 환불, timeout·outstanding·3시간 경계 복구, 지속 가능한 결과 메일과 승인 뒤 잠금·재구매
- [ ] **G 기본 매출·대사**: live 기본 구매 gross/refund/net, 미수렴 대사 화면, test 기본 제외
- [ ] **C~G 환경 격리**: test 구매가 live 전문을 열거나 live 주문·구매를 막지 않고, 계정·Store 교체가 데이터 이관 없이 설정 변경으로 끝남

### M3 완료

- [ ] 기존·신규 이미지 metadata 100%와 공간 예약
- [ ] 로그인·게스트 완독, 작품 진행률·CTA 의미 통일
- [ ] 작가·에피소드 후원과 owner 메시지
- [ ] 후원 포함 상세 breakdown·전환율·TEST filter
- [ ] backend/frontend/admin 전체 자동 gate
- [ ] 결제·세션·권한·환불·완독·후원·수익 사용자 브라우저 확인
- [ ] 관련 IMPLEMENTATION·DECISIONS·DB_SCHEMA·PRD·마일스톤 동기화와 날짜·검증 결과 영구 기록

---

## M3에서 의도적으로 제외

- 전편 구매, 묶음 할인, `bundle_id`, 일괄 환불
- 멤버십·구독, 빌링키, 저장 결제수단
- 무통장 입금·가상계좌·부분 환불·chargeback 자동화
- 게시글 후원·공개 후원 피드·후원 환불 자동화
- 범용 회계 ledger·outbox·queue·다중 PG 추상화
- PG 수수료·실정산액·세금계산서·다작가 분배
- 포렌식 워터마크, Cloudflare Worker 서명 쿠키
- 콘텐츠 버전별 구매·완독 snapshot
- 작가 Owner 계정 생성·실키 전환·사업자 심사·약관 법무 승인 자체(M7)
