# M3 구매 권한·가격·공개 계약 정합성

2026-11-11, `be/fix/m3-quality-consistency`. [M3 코드 품질 후속 작업](../../../milestones/M3_foundation.md#m3-quality-followups) Q1~Q4의 Backend 범위를 구현한다. Q2의 Admin 입력 검증과 Q3의 FE 수기 타입·fixture 정리는 이 BE 변경이 main에 머지된 뒤 영역별 브랜치에서 진행한다.

## 원인과 수정

### Q1. 비공개 구매 회차의 진행도

본문과 viewer-bootstrap은 중앙 access 정책으로 활성 구매자의 일반 비공개 회차 열람을 허용하지만, `upsert_progress`는 공개 여부만 검사해 저장을 거부했다. Frontend가 부가 기능의 저장 실패를 무시하므로 본문은 읽혀도 다음 방문에 위치를 복원하지 못했다.

저장 전에 `resolve_episode_access(user_id, episode_id, session)`를 사용하고 `unavailable`만 거부한다. 공개 preview의 기존 위치 저장은 유지하고, 현재 환경의 활성 구매자는 작품·회차의 일반 비공개 뒤에도 저장할 수 있다. 다른 사용자·환경·비활성 구매·삭제·손상된 비공개 문서는 저장 권한을 얻지 못한다. 호출부가 없어진 `catalog_service.public_episode_exists`는 제거했다.

권한 판정과 진행도 저장은 본문 요청·presign·`first_viewed_at` 변경을 수행하지 않는다. 기존 page_no·block_offset_bp 저장·조회, 생략된 오프셋의 구버전 보존, GET의 본인 위치 조회와 작품별 공개 목록 필터는 유지한다. 완독 저장이나 preview 범위 확대를 추가하지 않는다.

### Q2. 가격 입력의 DB 정수 상한

작품·회차의 생성·수정 스키마 네 곳이 가격 하한만 검사해 `2_147_483_648`원도 DB까지 전달했다. PostgreSQL Integer 범위를 넘으면 입력 오류 대신 드라이버 예외가 발생했다.

`schemas/work.py`의 `PRICE_MAX=2_147_483_647`을 네 필드의 상한으로 사용해 초과 입력을 422로 거부한다. 기존 500원 기본값, 회차별 가격, 가격 생략과 null 상속은 이번 변경에서 보존한다. 0원 기본 정책 정리는 Q5이며 별도 migration 대상이다. 결제 intent의 양수·서버 금액 snapshot 검증은 변경하지 않는다.

### Q3. 공개 구매 placeholder의 서버 계약

공개 `EpisodeSummary.is_purchased`는 실제 구매와 무관하게 항상 false여서 개인 구매 상태로 오용할 수 있었다. DTO와 조립 코드에서 제거하고 OpenAPI 기반 Admin 타입을 재생성했다. 작품 상세·회차 목록 API는 익명과 구매자에게 같은 공개 응답을 반환하며 조회가 최초 전문 열람을 기록하지 않는다.

실제 구매 표시는 기존 no-store progress의 `purchased_episode_ids`와 `WorkExperience`를 사용한다. FE 런타임은 이미 공개 placeholder를 읽지 않으므로 서버 필드 제거에 의존하는 화면 동작 변경은 없다. `frontend/src/lib/catalog.ts`의 수기 필드와 두 fixture의 잔여 필드는 BE 머지 후 FE 후속에서 제거한다. Q3 전체 완료 표시는 그 후속 검증 뒤에 한다.

### Q4. 보호 대상 구매 상태

재구매 차단, 중복 승인 승자 조회, 작품·회차 삭제 보호가 같은 세 상태를 각자 나열했다. `models/payment.py`의 `PROTECTED_PURCHASE_STATUSES`를 세 서비스가 공유한다.

- 보호 대상: `active`, `refund_pending`, `review_required`.
- 보호 대상 제외: `refunded`.
- 열람 권한: 기존 중앙 정책의 `active`만 인정한다. 보호 대상 전체를 전문 열람 허용으로 사용하지 않는다.

각 조회의 환경 범위·잠금·트랜잭션 순서는 유지한다. 주문 생성은 현재 배포 환경, sync는 해당 주문의 환경, 삭제 보호는 기존처럼 모든 환경의 남은 구매를 검사한다. DB 모델의 컬럼·인덱스·제약은 바꾸지 않아 migration은 없다.

## 검증

- 집중 테스트: progress·Admin 작품/회차·catalog·access·intent·sync·삭제 보호 **428 passed**.
- 신규 회귀 34개: 비공개 조합별 위치 저장·재조회와 최초 열람값 보존 6개, 거부 조건 8개, 공개 preview 저장 1개, 작품·회차 가격 HTTP 경계 2개, 공개 응답의 구매자 비개인화 1개, intent·sync의 상태 4종과 환경 2종 조합 16개.
- Backend Ruff format/check: 전체 통과.
- Admin 타입 재생성·lint·**115개 테스트**·build: 통과.
- Backend 전체: **1,093 passed**, 83.38초. Ruff 전체 format/check와 함께 통과했다.
- Frontend 호환성: lint·Astro check·**241개 테스트**·build 통과. 기존 미사용 import hint 1개, Sentry auth token 미설정에 따른 release/source map 업로드 생략, Astro transitions의 source map 경고가 남아 있다. 이 BE 작업에서 해당 설정·소스를 변경하지 않았다.

브라우저는 실행하지 않는다. 비공개 구매 회차를 읽고 재진입했을 때의 실제 화면 복원은 사용자 확인 대상이다. 현재 작업은 커밋·push·외부 결제 write를 포함하지 않는다.
