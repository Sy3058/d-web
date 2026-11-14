# M3 F 구매 내역 API

## 범위와 인계

로그인 사용자의 현재 결제 환경 구매 내역을 `GET /my/purchases`로 조회한다. 일반 비공개 구매 회차도 내역에 유지하고 중앙 열람 정책이 허용한 활성 구매에는 기존 뷰어로 이동할 상대 경로를 제공한다. BE 계약과 생성 타입을 먼저 반영했고, PR #153 main 머지 뒤 최신 main의 별도 `fe/` 브랜치에서 [FE 구매 내역 화면·네비게이션](../../FE/Payment/IMPLEMENTATION_PURCHASE_HISTORY.md)을 연결했다(2026-11-13 로컬 구현·자동 검증 완료). 실제 결제·복귀·영수증의 브라우저 확인은 사용자 검증으로 남는다. F 전체 완료를 뜻하지 않는다.

환불 요청·승인·거부와 환불 자격 판정은 G 범위다. 이번 응답은 현재 구매 상태와 이미 저장된 환불 시각·금액만 표시한다. 조회 결과로 환불 가능 여부나 전문 발급 권한을 새로 만들지 않는다.

## 응답 계약

`get_current_user` 인증을 사용하며 이메일 재인증을 구매 이력 조회의 추가 조건으로 삼지 않는다. 현재 `payment_environment`와 소유자를 서버에서 제한한다. `page`는 기본 1, 범위 1~2,147,483,647이며 페이지 크기는 20으로 고정한다. 구매 결제 시각 내림차순, 구매 UUID 내림차순으로 정렬한다. 빈 페이지에서도 전체 구매 건수를 반환한다.

응답은 `items`, `total`, `page`, `page_size`를 갖는다. 항목은 구매 `id`, `payment_id`, 주문 당시 `item_title`·`order_name`, 구매 `amount`·주문 `currency`, `paid_at`, 구매 `status`, `first_viewed_at`, `refunded_at`, `refund_amount`, `receipt_url`, `viewer_path`로 제한한다. 현재 카탈로그 제목이나 가격으로 주문 snapshot을 덮지 않는다. 다른 사용자·환경의 내역과 원고·이미지 키·결제 설정·취소 발송 정보는 반환하지 않는다.

영수증은 서버 주문에 저장된 URL을 읽되 정상적인 HTTPS URL만 반환한다. 사용자 정보가 포함되거나 공백·제어문자·잘못된 host/port가 있는 값과 과도하게 긴 값은 null로 투영한다. URL을 서버에서 호출하거나 저장 값을 정규화해 갱신하지 않는다. FE는 링크를 새 창에 열 때 `rel="noopener noreferrer"`를 적용하고 원문 HTML로 삽입하지 않는다.

성공과 인증·검증 오류에 `Cache-Control: no-store`를 적용한다. FE는 기존 공용 API wrapper로 access 만료를 refresh하고 최종 401과 네트워크·서버 장애를 구분해야 한다. 개인 내역을 SSR 공유 캐시에 넣지 않는다.

## 결제에서 영수증 저장 (2026-11-12 리뷰 보완)

초기 구매 내역 테스트는 `PaymentOrder.receipt_url`을 직접 채워 조회만 확인했으므로, E2 공통 sync가 PortOne의 `receiptUrl`을 저장하지 않는 연결 누락을 놓쳤다. 실제 결제 승인에서 구매 생성까지 진행한 뒤 구매 내역을 조회하면 영수증이 있어도 null인 것을 재현했다. 아래 경로를 보완하고 결제 sync부터 실제 ASGI 구매 내역 응답까지 검증한다.

정상 PAID 신규 구매 확정 transaction에서 provider snapshot의 안전한 HTTPS URL을 주문에 함께 저장한다. 쓰기와 읽기는 `lib/payment_receipt.py`의 같은 URL 검증을 사용한다. 이미 paid인 주문도 기존 complete·owner 재조회·결제 상태 재확인의 공통 sync를 거칠 때 영수증을 보완한다. 현재 응답이 PAID이고 주문 identity·KRW·금액·channel·환경·수단이 snapshot과 일치하며, 결제 시각과 저장된 transaction ID가 있는 경우 해당 ID도 일치할 때만 적용한다.

재조회에 URL이 없거나 안전하지 않으면 기존 영수증을 지우지 않는다. 조회 장애·불일치·비승인·미확정 응답에서 영수증을 갱신하지 않는다. 과거 주문에서 필수 snapshot을 찾을 수 없으면 추측 복원하지 않는다. 구매 내역 GET은 계속 DB만 읽으며 PortOne을 직접 호출하지 않는다. provider가 영수증을 제공하지 않은 경우에는 null이 정상이다.

기존 lock 순서·version 검사·외부 I/O 경계와 구매·첫 열람·환불 상태의 의미는 유지한다. 실제 기존 거래를 자동 일괄 조회하는 backfill이나 마이그레이션은 수행하지 않는다.

## 이력 보존과 열람

조회 기준은 `Purchase`이며 공개 catalog에 의존하지 않는다. 작품·회차의 일반 비공개나 삭제 상태, 구매의 환불 대기·환불 완료·검토 상태 때문에 구매 내역 자체를 누락시키지 않는다. 주문을 통해 당시 정보를 읽고 회차·작품은 외부 조인으로 조회한다.

목록의 메타와 중앙 `episode_access_columns` 권한 입력은 같은 SELECT snapshot에서 읽어 `evaluate_episode_access`로 판정한다. 해당 항목이 active이고 삭제되지 않은 문서에 대해 중앙 정책이 같은 구매의 full을 허용할 때만 `/works/{work_id}/{public_id}`를 제공한다. 일반 비공개 active 구매에는 링크가 있고 inactive·삭제·손상 문서에는 null이다. content API는 실제 진입 때 다시 인가한다. 목록 링크는 지속되는 권한 증명으로 사용하지 않는다.

전체 건수와 페이지를 조회하며 항목별 추가 SQL이나 외부 I/O는 없다. 원고가 권한 검증에 내부적으로 사용되더라도 응답에는 포함하지 않는다. presign·commit·`first_viewed_at` 갱신과 PortOne 조회를 수행하지 않는다. 두 SELECT 사이 데이터가 바뀌면 전체 건수와 페이지 수는 일시적으로 다를 수 있으며, 권한과 항목 메타는 페이지 SELECT 하나의 snapshot으로 고정한다.

## 검증

2026-11-12 실제 TCP HTTP 추가 확인:

- PID별 격리 테스트 DB, localhost Uvicorn과 빌드된 Astro standalone 서버를 사용했다. 실제 로그인 쿠키로 구매 목록을 요청하고 반환된 링크를 독자 서버에 요청했다. 초기 경로의 불필요한 `/episodes/` 때문에 404가 발생하는 연결 오류를 재현했다. 서비스와 테스트 기대값을 실제 Astro `[id]/[publicId].astro` 경로에 맞춰 고친 뒤 반환 링크 200을 확인했다. 기존 테스트도 같은 잘못된 경로를 기대해 놓친 오류였다. Backend bootstrap API 경로는 별개이므로 변경하지 않았다.
- 로그인 쿠키 HttpOnly, 익명 내역 401, 인증 내역 200, 잘못된 page 422와 no-store를 확인했다. 구매자 비공개 bootstrap·본문은 200, 미구매자는 모두 404이고 다른 사용자 내역은 빈 목록이다. SSR에는 비공개 제목·유료 본문이 없고 목록 조회는 첫 열람을 기록하지 않으며 전문 요청 후에만 기록한다.
- 링크 수정 후 Backend Ruff format **116 files**, Ruff check, pytest 전체 **1,147 passed**(72.10초). API schema와 FE·Admin 코드는 변경하지 않았다.
- 영수증은 합성 PAID provider 응답에서 실제 sync·DB 저장·HTTP 응답까지 확인했다. 외부 PortOne은 호출하지 않았다. 기존 개발 DB에서 transaction ID와 PAID 상태가 있는 test 환경 주문은 0건이어서 실제 거래 영수증 확인 근거가 없다.
- 브라우저 클릭·hydration·실제 결제·외부 영수증 페이지 열기는 미검증이다. 임시 서버와 테스트 DB는 확인 후 정리했다. 결과와 기존 의존성 보안 발견은 [추가 점검 기록](../../INFRA/Security/REVIEW_ADDITIONAL_CHECKS_2026_11_12.md)에 구분한다.

2026-11-12 리뷰 보완 검증 결과:

- 신규 `tests/test_payment_receipts.py` 21개를 추가했다. 최초 결제 sync부터 실제 ASGI 구매 내역까지 URL 저장·반환을 확인하고, 기존 paid 주문의 URL 복구·저장 transaction ID 유무·기존 첫 열람 시각 보존을 검증한다. 누락·unsafe URL, payment ID·Store·통화·금액·channel·환경·수단·결제 시각·transaction ID 불일치, 비승인·미확정·조회 실패가 기존 URL을 지우거나 바꾸지 않는 것도 확인한다. 구매는 한 건이고 최초 열람을 새로 기록하지 않는다.
- 수정 전 신규 회귀가 실제 DB에서 `receipt_url is None`으로 실패하는 것을 확인한 뒤 수정했다. 결제·구매 내역 집중 테스트 **136 passed**(6.22초) 뒤 첫 열람 기록 보존과 transaction ID 없는 정상 재조회를 보강했고 최종 전체 gate에 포함했다.
- Backend `uv run ruff format --check .` **116 files**, `uv run ruff check .`, `uv run pytest --tb=short` **1,147 passed**(85.12초).
- 최종 diff와 결제 검증·stale version·transaction·개인 응답 경로를 다시 검토했고, 이번 영수증 수정에 남은 머지 차단 발견은 없었다. 초기 자체 리뷰의 발견 없음 판정은 영수증 생산 경로를 놓친 불완전한 판정이었으며 아래 초기 검증만으로 영수증 기능 완료를 증명하지 못했다.
- API schema·Admin 생성 타입·Frontend/Admin 동작 변경이 없어 해당 gate를 반복하지 않았다. 아래 Admin 119개와 생성 타입은 앞선 구매 내역 API 계약 검증 결과다. 실제 PortOne 호출·기존 거래 backfill·사용자 브라우저 확인·마이그레이션은 수행하지 않았다.

2026-11-11 초기 검증 결과:

- 신규 `tests/test_purchase_history.py` 33개가 전체 gate에서 통과했다. 인증 401·page 422·DB 장애 503의 no-store, 소유자·환경 격리, 20건 페이지와 정렬 tie·빈 페이지, 작품·회차 비공개 조합, inactive·삭제·손상 이력과 링크 차단, 영수증 검증·원본 보존, 주문 snapshot과 오래된 ORM identity map, 최초/기존 열람 시각 보존을 확인했다. 응답 필드 allowlist와 presign 호출 0, 구매 조회 SELECT 2건도 단언한다.
- Backend `uv run ruff format --check .` 114 files, `uv run ruff check .`, `uv run pytest` **1,126 passed**(80.53초).
- `pnpm --filter admin generate:types`로 OpenAPI 생성 타입을 갱신했다. Admin lint·**119 tests**·build 통과. 새 화면 동작은 추가하지 않았다.
- `fable-review` 기준으로 실제 중앙 정책·인증·조회·응답 경로를 독립 검토했고 머지를 막을 발견은 없었다. 목록의 viewer 경로가 실제 전문 API의 재인가를 대체하지 않는 점을 확인했다.
- 추가로 PID별 임시 테스트 DB에 구매 300건(조회 사용자 30건, 다른 사용자 270건)을 생성해 서비스가 실제 실행한 건수·페이지 SELECT의 `EXPLAIN ANALYZE`를 확인했다. 두 쿼리는 `idx_purchases_user_id`를 사용했고 페이지는 소유자 30건을 정렬한 뒤 20건을 반환했다. 해당 소규모 표본의 실행 시각은 건수 0.041ms·목록 0.651ms였다. 운영 부하나 대용량 성능을 보장하는 수치는 아니다. 임시 DB는 확인 직후 정리했다.

초기 통합 테스트는 PostgreSQL 연결 거부로 실행하지 못했다. Docker Desktop과 기존 PostgreSQL 서비스를 시작한 뒤 PID별 테스트 DB에서 검증을 완료했다. 내역 SQL 개수 단언은 인증의 `session.get`이 identity map에서 끝나는 경우를 구분하도록 수정했다. 구매 조회 자체의 SELECT 두 건 제한은 유지한다. pnpm 실행은 기존 저장소·CI와 같은 10 계열을 사용했다([공식 설치 안내](https://pnpm.io/10.x/installation)). 저장소 dependency·lockfile·모델·migration 변경은 없다.

Frontend 코드는 변경하지 않아 FE gate는 실행하지 않았다. 실제 PortOne 호출·영수증 열기·사용자 브라우저 실기능 확인과 대용량 구매 이력의 실행계획·성능 측정은 이번 검증에 포함하지 않았다. FE 목록·영수증·네비는 위 별도 FE 작업으로 연결했다. 실제 결제 후 자동 전문 진입과 영수증의 사용자 브라우저 확인이 남아 F 전체는 미완료다.

## 독자용 구매 카드 메타데이터 (2026-11-13)

독자 화면에서 내부 주문명 대신 작품·회차·썸네일을 표시할 수 있도록 기존 응답에 nullable `work_title`과 `thumbnail_url`을 추가했다. 작품명·회차의 썸네일 여부/갱신 시각·작품 표지/갱신 시각은 기존 페이지 SELECT에 포함하며 쿼리는 계속 두 건이다. 공개 catalog로 재조회하거나 구매 이력을 필터링하지 않는다. 회차 썸네일은 기존 catalog와 같은 공개 파생 키로 URL을 만들고, 미선택 시 작품 표지로 대체한다. 원고 `image_keys`나 원본 thumbnail key를 공개 URL로 사용하지 않으며 presign·외부 I/O도 없다. 삭제된 작품·회차는 썸네일 null이다.

내부 주문명·금액·영수증 등 기존 서버 계약은 보존하고, FE가 주문명·상태·열람 상세를 숨기고 카드에 금액·결제 일시·영수증 진입을 표시한다. 추가 회귀 5건을 포함해 Backend Ruff format116·Ruff check·전체1,152개(74.62초), Admin 타입 생성·lint·119 tests·build를 통과했다. 실제 삭제·소장본 보존 정책은 이번 변경에 포함하지 않는다.
